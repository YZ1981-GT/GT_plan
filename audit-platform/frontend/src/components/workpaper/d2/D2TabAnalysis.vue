<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D2TabAnalysis — 分析程序D2-5
 * 完整5区段分析：
 * (一) 重要指标分析 (二) 借方发生额与收入核对
 * (三) 贷方发生额分析 (四) 期末前十名分析 (五) 近两年账龄结构分析
 */
import { computed, inject, ref, watch, toRef, onBeforeUnmount, type Ref } from 'vue'
import { useD2Analysis } from '../composables/useD2Analysis'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useD2SaveInject } from '../composables/useD2SaveInject'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useAgingConfig, PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import type { useD2CrossSheet } from '../composables/useD2CrossSheet'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
// 🔴 真源是 `src/composables/useExcelIO.ts`（平台级 Excel IO 单一入口），
// **不在** `components/workpaper/composables/` 下 —— 上一行的 `../composables/displayPrefsKey`
// 才是那个目录。写成 `../composables/useExcelIO` 会让 Vite 解析失败（transform 500），
// 该 tab 是 defineAsyncComponent 动态载入 ⇒ 点开 D2-5 直接崩「页面渲染出错：
// Failed to fetch dynamically imported module」。其余三个调用方都用下面这个别名路径。
import { createExcelJsWorkbook, loadExcelJsWorkbook } from '@/composables/useExcelIO'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const { saveItems } = useD2SaveInject()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const {
  indicators,
  turnoverDaysWarning,
  dataSource,
  remark,
  updateMetaField,
} = useD2Analysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-5',
)

function fmtPct(v: number): string {
  return (v * 100).toFixed(2) + '%'
}
function fmtDays(v: number): string {
  return v === 0 ? '-' : v.toFixed(1) + '天'
}
function fmtRate(v: number): string {
  return v === 0 ? '-' : v.toFixed(2)
}

const crossSheet = inject<ReturnType<typeof useD2CrossSheet> | null>('d2CrossSheet', null)

/**
 * 账龄分布：手工录入优先；否则按**项目账龄配置段**（枚举账龄）从 D2-2 明细汇总。
 * 段 key 由 crossSheet.agingFromDetail.segments 提供，无需 label→key 手工映射
 * （旧映射表既有 3 套措辞，且「三年以上」映到不存在的 over3 → 3 年段项目金额恒 0）。
 */
const displayAging = computed(() => {
  if (indicators.value.agingDistribution.length > 0) return indicators.value.agingDistribution
  const src = crossSheet?.agingFromDetail.value
  const segments = src?.segments ?? []
  if (!src || segments.length === 0) {
    return agingBands.value.map(band => ({ band, amount: 0, ratio: 0 }))
  }
  const bands = segments.map(seg => ({
    band: seg.label,
    amount: Number(src.audited?.[seg.key]) || 0,
    ratio: 0,
  }))
  const total = bands.reduce((s, b) => s + b.amount, 0)
  return bands.map(b => ({ ...b, ratio: total === 0 ? 0 : b.amount / total }))
})

const { generateAndConfirm, aiAvailable } = useD2AiGenerate(toRef(props, 'wpId'))

async function onAiAnalysisNote(): Promise<void> {
  const content = await generateAndConfirm('analysis-note', remark.value, {
    turnoverRate: indicators.value.turnoverRate,
    turnoverDays: indicators.value.turnoverDays,
    badDebtRate: indicators.value.badDebtRate,
    top5Concentration: indicators.value.top5Concentration,
  }, 'AI 生成分析程序备注')
  if (content) updateMetaField('remark', content)
}

async function onAiProcess(): Promise<void> {
  const content = await generateAndConfirm('analysis-process', auditProcess.value, {
    turnoverRate: indicators.value.turnoverRate,
    turnoverDays: indicators.value.turnoverDays,
    badDebtRate: indicators.value.badDebtRate,
    top5Concentration: indicators.value.top5Concentration,
  }, 'AI 生成审计过程')
  if (content) {
    auditProcess.value = content
    updateMetaField('process', content)
  }
}

// ─── (二) 借方发生额与收入核对 ────────────────────────────────────────────
export interface DebitReconRow {
  project: string
  amount: number | null
  dataSource: string
  remark: string
  isFormula?: boolean
}

const debitReconRows = ref<DebitReconRow[]>([
  { project: '本期主营业务收入', amount: null, dataSource: '利润表', remark: '' },
  { project: '增值税率', amount: 0.13, dataSource: '', remark: '一般纳税人13%' },
  { project: '收入价税合计', amount: null, dataSource: '', remark: '', isFormula: true },
  { project: '本期应收账款借方发生额合计', amount: null, dataSource: '应收账款总账', remark: '' },
  { project: '收入价税合计与应收账款借方发生额差异', amount: null, dataSource: '', remark: '', isFormula: true },
])
const debitReconDiffReason = ref('')

// 自动计算公式
const debitReconComputed = computed(() => {
  const rows = debitReconRows.value
  const revenue = rows[0].amount || 0
  const taxRate = rows[1].amount || 0
  const revenueTax = revenue * (1 + taxRate)
  const debitTotal = rows[3].amount || 0
  const diff = revenueTax - debitTotal
  return { revenueTax, diff }
})

// ─── (三) 贷方发生额分析 ──────────────────────────────────────────────────
export interface CreditAnalysisRow {
  project: string
  amount: number | null
  dataSource: string
  crossCheck: string
  remark: string
}

const creditAnalysisRows = ref<CreditAnalysisRow[]>([
  { project: '本期贷方发生额合计', amount: null, dataSource: '应收账款总账', crossCheck: '', remark: '' },
  { project: '其中：银行存款收回款项', amount: null, dataSource: '银行存款明细账', crossCheck: '与银行存款借方发生额核对', remark: '' },
  { project: '计入应收票据', amount: null, dataSource: '应收票据明细账', crossCheck: '与应收票据借方发生额核对', remark: '' },
  { project: '坏账核销', amount: null, dataSource: '坏账准备明细', crossCheck: '与坏账准备贷方发生额核对', remark: '' },
])
const creditDiffReason = ref('')

const creditDiffComputed = computed(() => {
  const rows = creditAnalysisRows.value
  if (rows.length < 2) return 0
  const total = rows[0].amount || 0
  const sub = rows.slice(1).reduce((s, r) => s + (r.amount || 0), 0)
  return total - sub
})

function addCreditRow(): void {
  creditAnalysisRows.value.push({
    project: '',
    amount: null,
    dataSource: '',
    crossCheck: '',
    remark: '',
  })
}
function removeCreditRow(idx: number): void {
  if (idx > 0) creditAnalysisRows.value.splice(idx, 1)
}

// ─── (四) 期末前十名分析 ──────────────────────────────────────────────────
export interface Top10Row {
  customerName: string
  endBalance: number | null
  beginBalance: number | null
  changeAmount: number | null
  changeRatio: number | null
  aging: string
  creditPeriod: string
  overdueAmount: number | null
}

function createEmptyTop10(): Top10Row {
  return { customerName: '', endBalance: null, beginBalance: null, changeAmount: null, changeRatio: null, aging: '', creditPeriod: '', overdueAmount: null }
}

const top10Rows = ref<Top10Row[]>(Array.from({ length: 3 }, () => createEmptyTop10()))

function addTop10Row(): void {
  if (props.isReadonly) return
  top10Rows.value.push(createEmptyTop10())
  onTop10Change()
}

function removeTop10Row(idx: number): void {
  if (props.isReadonly || top10Rows.value.length <= 1) return
  top10Rows.value.splice(idx, 1)
  onTop10Change()
}

const top10Total = computed(() => {
  const rows = top10Rows.value
  return {
    endBalance: rows.reduce((s, r) => s + (r.endBalance || 0), 0),
    beginBalance: rows.reduce((s, r) => s + (r.beginBalance || 0), 0),
    changeAmount: rows.reduce((s, r) => s + (r.changeAmount || 0), 0),
    overdueAmount: rows.reduce((s, r) => s + (r.overdueAmount || 0), 0),
  }
})

// auto-calc changeAmount & changeRatio per row
function calcTop10Row(row: Top10Row): void {
  const end = row.endBalance || 0
  const begin = row.beginBalance || 0
  row.changeAmount = end - begin
  row.changeRatio = begin === 0 ? null : (end - begin) / begin
}

// ─── (五) 近两年账龄结构分析 ──────────────────────────────────────────────
export interface AgingCompareRow {
  aging: string
  endBalance: number | null
  endRatio: number | null
  beginBalance: number | null
  beginRatio: number | null
  changeAmount: number | null
  changeRatio: number | null
  reason: string
}

const AGING_BANDS_DEFAULT = PRESET_SEGMENTS.FIVE_YEAR.map((seg) => seg.label)

// 从项目设置的账龄配置获取账龄段（与D2-2明细表一致）
const { segments: agingSegments, bands: agingConfigBands } = useAgingConfig(toRef(props, 'projectId'), 'D2')

// 监听项目级账龄配置变更事件（从 D2-1 审定表或项目设置触发）
const agingConfigVersion = ref(0)
function onAgingConfigChanged(): void {
  agingConfigVersion.value++
}
window.addEventListener('aging-config:changed', onAgingConfigChanged)

/**
 * 账龄段标签 = 项目账龄配置（枚举账龄：3年段/5年段/自定义）单一真源。
 * 已删除「从 D2-1 审定表 D2-adj-aging-mode 读取」的第二套口径（措辞与段 key 都与平台不一致）。
 */
const agingBands = computed(() => {
  // 触发依赖（aging-config:changed 事件时强制重算）
  void agingConfigVersion.value
  if (agingConfigBands.value && agingConfigBands.value.length > 0) {
    return agingConfigBands.value.map((b: any) => b.label || b.name || b)
  }
  return PRESET_SEGMENTS.FIVE_YEAR.map((seg) => seg.label)
})

const agingCompareRows = ref<AgingCompareRow[]>([])

// 当账龄段配置变化时，重建行（保留已有数据）
watch(agingBands, (newBands) => {
  const existing = agingCompareRows.value
  agingCompareRows.value = newBands.map(band => {
    const found = existing.find(r => r.aging === band)
    return found || {
      aging: band,
      endBalance: null,
      endRatio: null,
      beginBalance: null,
      beginRatio: null,
      changeAmount: null,
      changeRatio: null,
      reason: '',
    }
  })
}, { immediate: true })

const agingCompareTotal = computed(() => {
  const rows = agingCompareRows.value
  const endTotal = rows.reduce((s, r) => s + (r.endBalance || 0), 0)
  const beginTotal = rows.reduce((s, r) => s + (r.beginBalance || 0), 0)
  return { endTotal, beginTotal, changeAmount: endTotal - beginTotal, changeRatio: beginTotal === 0 ? null : (endTotal - beginTotal) / beginTotal }
})

function recalcAgingRatios(): void {
  const rows = agingCompareRows.value
  const endTotal = rows.reduce((s, r) => s + (r.endBalance || 0), 0)
  const beginTotal = rows.reduce((s, r) => s + (r.beginBalance || 0), 0)
  rows.forEach(r => {
    r.endRatio = endTotal === 0 ? null : (r.endBalance || 0) / endTotal
    r.beginRatio = beginTotal === 0 ? null : (r.beginBalance || 0) / beginTotal
    const end = r.endBalance || 0
    const begin = r.beginBalance || 0
    r.changeAmount = end - begin
    r.changeRatio = begin === 0 ? null : (end - begin) / begin
  })
}

// ─── 审计过程 text ref ─────────────────────────────────────────────────────
const auditProcess = ref('')

// ─── Persistence: Load & Save table data ──────────────────────────────────
function loadTableData(): void {
  const map = props.allResponses
  // 审计过程
  const processResp = map.get('D2-analysis-process')
  if (processResp?.remark) auditProcess.value = processResp.remark

  // 借方发生额
  const debitJson = map.get('D2-analysis-debit-recon')?.remark
  if (debitJson) {
    try {
      const parsed = JSON.parse(debitJson)
      if (parsed.rows) debitReconRows.value = parsed.rows
      if (parsed.diffReason) debitReconDiffReason.value = parsed.diffReason
    } catch { /* ignore */ }
  }

  // 贷方发生额
  const creditJson = map.get('D2-analysis-credit-analysis')?.remark
  if (creditJson) {
    try {
      const parsed = JSON.parse(creditJson)
      if (parsed.rows) creditAnalysisRows.value = parsed.rows
      if (parsed.diffReason) creditDiffReason.value = parsed.diffReason
    } catch { /* ignore */ }
  }

  // 前十名
  const top10Json = map.get('D2-analysis-top10')?.remark
  if (top10Json) {
    try {
      const parsed = JSON.parse(top10Json)
      if (Array.isArray(parsed)) top10Rows.value = parsed
    } catch { /* ignore */ }
  }

  // 账龄结构
  const agingJson = map.get('D2-analysis-aging-compare')?.remark
  if (agingJson) {
    try {
      const parsed = JSON.parse(agingJson)
      if (Array.isArray(parsed)) agingCompareRows.value = parsed
    } catch { /* ignore */ }
  }
}

function saveTableData(key: string, data: any): void {
  if (props.isReadonly) return
  const jsonStr = JSON.stringify(data)
  props.allResponses.set(key, { item_id: key, conclusion: null, remark: jsonStr })
  void saveItems([{ item_id: key, conclusion: null, remark: jsonStr }])
}

function onDebitReconChange(): void {
  saveTableData('D2-analysis-debit-recon', { rows: debitReconRows.value, diffReason: debitReconDiffReason.value })
}
function onCreditAnalysisChange(): void {
  saveTableData('D2-analysis-credit-analysis', { rows: creditAnalysisRows.value, diffReason: creditDiffReason.value })
}
function onTop10Change(): void {
  saveTableData('D2-analysis-top10', top10Rows.value)
}
function onAgingCompareChange(): void {
  recalcAgingRatios()
  saveTableData('D2-analysis-aging-compare', agingCompareRows.value)
}

// ─── 导入导出：前十名 (四) ────────────────────────────────────────────────
function exportTop10(): void {
  const headers = ['客户名称', '期末账面余额', '期初账面余额', '变动金额', '变动比例', '账龄', '信用期', '逾期金额']
  const rows = top10Rows.value.map(r => [
    r.customerName, r.endBalance ?? '', r.beginBalance ?? '',
    r.changeAmount ?? '', r.changeRatio != null ? (r.changeRatio * 100).toFixed(1) + '%' : '',
    r.aging, r.creditPeriod, r.overdueAmount ?? '',
  ])
  _exportXlsx('D2-5-前十名分析', headers, rows)
}

function importTop10(file: File): boolean {
  _importXlsx(file, (data) => {
    const parsed: Top10Row[] = data.map((row: any) => {
      const r = createEmptyTop10()
      r.customerName = String(row['客户名称'] ?? row[0] ?? '')
      r.endBalance = Number(row['期末账面余额'] ?? row[1]) || null
      r.beginBalance = Number(row['期初账面余额'] ?? row[2]) || null
      r.aging = String(row['账龄'] ?? row[5] ?? '')
      r.creditPeriod = String(row['信用期'] ?? row[6] ?? '')
      r.overdueAmount = Number(row['逾期金额'] ?? row[7]) || null
      calcTop10Row(r)
      return r
    }).filter((r: Top10Row) => r.customerName)
    if (parsed.length > 0) {
      top10Rows.value = parsed
      onTop10Change()
    }
  })
  return false
}

// ─── 导入导出：账龄结构 (五) ──────────────────────────────────────────────
function exportAgingCompare(): void {
  const headers = ['账龄', '期末账面余额', '各账龄占比', '期初账面余额', '各账龄占比', '变动金额', '变动比例', '原因分析']
  const rows = agingCompareRows.value.map(r => [
    r.aging, r.endBalance ?? '', r.endRatio != null ? (r.endRatio * 100).toFixed(1) + '%' : '',
    r.beginBalance ?? '', r.beginRatio != null ? (r.beginRatio * 100).toFixed(1) + '%' : '',
    r.changeAmount ?? '', r.changeRatio != null ? (r.changeRatio * 100).toFixed(1) + '%' : '',
    r.reason,
  ])
  _exportXlsx('D2-5-账龄结构分析', headers, rows)
}

function importAgingCompare(file: File): boolean {
  _importXlsx(file, (data) => {
    const parsed: AgingCompareRow[] = data.map((row: any) => ({
      aging: String(row['账龄'] ?? row[0] ?? ''),
      endBalance: Number(row['期末账面余额'] ?? row[1]) || null,
      endRatio: null,
      beginBalance: Number(row['期初账面余额'] ?? row[3]) || null,
      beginRatio: null,
      changeAmount: null,
      changeRatio: null,
      reason: String(row['原因分析'] ?? row[7] ?? ''),
    })).filter((r: AgingCompareRow) => r.aging)
    if (parsed.length > 0) {
      agingCompareRows.value = parsed
      recalcAgingRatios()
      onAgingCompareChange()
    }
  })
  return false
}

// ─── 通用 xlsx 导出/导入辅助 ──────────────────────────────────────────────
function _exportXlsx(filename: string, headers: string[], rows: any[][]): void {
  // 走 useExcelIO 单一入口（B5 批）。仍是 ExcelJS 引擎，建表逻辑逐行不变。
  createExcelJsWorkbook().then(({ wb, toBuffer }) => {
    const ws = wb.addWorksheet('数据')
    ws.addRow(headers)
    for (const row of rows) ws.addRow(row)
    // 列宽自适应
    headers.forEach((_, i) => { ws.getColumn(i + 1).width = 16 })
    toBuffer().then((buffer) => {
      const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${filename}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    })
  })
}

function _importXlsx(file: File, onParsed: (data: any[]) => void): void {
  // 走 useExcelIO 单一入口（B5 批）。仍是 ExcelJS 引擎，解析逻辑逐行不变。
  // 原先用 FileReader 读成 ArrayBuffer 再 load，loadExcelJsWorkbook 直接收 File
  // （内部走 file.arrayBuffer()，与 readAsArrayBuffer 等价），故省掉那一层。
  loadExcelJsWorkbook(file).then((wb) => {
    const ws = wb.worksheets[0]
    if (!ws) return
    const headers: string[] = []
    const data: any[] = []
    ws.eachRow((row: any, rowNum: number) => {
      if (rowNum === 1) {
        row.eachCell((cell: any) => { headers.push(String(cell.value ?? '')) })
      } else {
        const obj: any = {}
        row.eachCell((cell: any, colNum: number) => {
          obj[headers[colNum - 1] || colNum - 1] = cell.value
          obj[colNum - 1] = cell.value
        })
        data.push(obj)
      }
    })
    onParsed(data)
  })
}

// Initial load
watch(
  () => props.allResponses.size,
  () => loadTableData(),
  { immediate: true }
)

onBeforeUnmount(() => {
  window.removeEventListener('aging-config:changed', onAgingConfigChanged)
})
</script>

<template>
  <div class="d2-tab-analysis">
    <!-- 标题头 -->
    <div class="tab-header">
      <h4>应收账款分析程序 D2-5</h4>
      <GtReviewTrigger section-id="D2-analysis-header" />
    </div>

    <!-- 工具栏（水平一行排列） -->
    <div class="tab-toolbar">
      <el-button-group>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" style="display:inline-block">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>

    <!-- ═══════════ 一、审计目标 ═══════════ -->
    <div class="section-title">一、审计目标</div>
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #default>
        <p>1.资产负债表中记录的应收账款是存在的。2.所有应当记录的应收账款均已记录。3. 应收账款以恰当的金额包括在财务报表中，与之相关的计价调整已恰当记录。</p>
      </template>
    </el-alert>

    <!-- ═══════════ 二、审计过程 ═══════════ -->
    <div class="section-title">
      <span>二、审计过程</span>
      <el-button v-if="aiAvailable && !isReadonly" size="small" text type="primary" @click="onAiProcess">🤖 AI生成</el-button>
      <GtReviewTrigger section-id="D2-analysis-process" />
    </div>
    <el-input
      v-model="auditProcess"
      type="textarea"
      :autosize="{ minRows: 5 }"
      :disabled="isReadonly"
      placeholder="描述分析程序的执行过程：数据来源、分析方法、比较基准、异常判定标准等..."
      @change="(v: string) => updateMetaField('process', v)"
    />

    <!-- ═══════════ (一) 应收账款重要指标分析 ═══════════ -->
    <div class="section-title subsection">
      <span>(一) 应收账款重要指标分析</span>
      <GtIndexChip value="wp:D4-6" label="见《D4-6》营业收入重要指标分析底稿" />
      <GtReviewTrigger section-id="D2-analysis-indicators" />
    </div>

    <!-- 周转天数警告 -->
    <el-alert v-if="turnoverDaysWarning" type="warning" :closable="false" class="warning-alert">
      <span>{{ turnoverDaysWarning }}</span>
      <GtIndexChip
        v-if="jumpToSection"
        value="wp:D2-1"
        label="D2-1"
        class="warn-chip"
        @click="jumpToSection('审定表D2-1')"
      />
    </el-alert>

    <!-- 指标卡片 -->
    <div class="cards-grid">
      <el-card shadow="hover" class="indicator-card">
        <template #header><span class="card-title">周转率</span></template>
        <div class="card-value">{{ fmtRate(indicators.turnoverRate) }}</div>
        <div class="card-label">应收账款周转率 = 营业收入 / 平均应收</div>
      </el-card>

      <el-card shadow="hover" class="indicator-card">
        <template #header>
          <span class="card-title">周转天数</span>
          <el-tag v-if="turnoverDaysWarning" type="warning" size="small">变动过大</el-tag>
        </template>
        <div class="card-value">{{ fmtDays(indicators.turnoverDays) }}</div>
        <div class="card-sub">上期: {{ fmtDays(indicators.priorTurnoverDays) }}</div>
        <div class="card-sub">变动: {{ (indicators.turnoverDaysChange * 100).toFixed(1) }}%</div>
      </el-card>

      <el-card shadow="hover" class="indicator-card">
        <template #header><span class="card-title">坏账率</span></template>
        <div class="card-value">{{ fmtPct(indicators.badDebtRate) }}</div>
        <div class="card-label">坏账准备 / 应收账款总额</div>
      </el-card>

      <el-card shadow="hover" class="indicator-card">
        <template #header><span class="card-title">前五大集中度</span></template>
        <div class="card-value">{{ fmtPct(indicators.top5Concentration) }}</div>
        <div class="card-label">前五大客户余额占总余额比</div>
      </el-card>

    </div>

    <!-- ═══════════ (二) 应收账款借方发生额与收入核对 ═══════════ -->
    <div class="section-title subsection">
      <span>(二) 应收账款借方发生额与收入核对</span>
      <GtReviewTrigger section-id="D2-analysis-debit-recon" />
    </div>

    <el-table :data="debitReconRows" border size="small" class="compact-table" @cell-click="onDebitReconChange">
      <el-table-column prop="project" label="项目" width="260" />
      <el-table-column label="金额" align="right" min-width="160">
        <template #default="{ row, $index }">
          <!-- 公式行：收入价税合计 -->
          <span v-if="$index === 2" class="formula-cell" title="= 本期主营业务收入 × (1 + 增值税率)">
            {{ displayPrefs.fmtAmount(debitReconComputed.revenueTax) }}
          </span>
          <!-- 公式行：差异 -->
          <span v-else-if="$index === 4" class="formula-cell" title="= 收入价税合计 - 借方发生额合计">
            {{ displayPrefs.fmtAmount(debitReconComputed.diff) }}
          </span>
          <!-- 可编辑行 -->
          <WpAmountInput
            v-else
            v-model="row.amount"
            :disabled="isReadonly"
            size="small"
            style="width: 100%"
            @change="onDebitReconChange"
          />
        </template>
      </el-table-column>
      <el-table-column prop="dataSource" label="数据来源" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.dataSource"
            :disabled="isReadonly"
            size="small"
            placeholder="数据来源"
            @change="onDebitReconChange"
          />
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            :disabled="isReadonly"
            size="small"
            placeholder="备注"
            @change="onDebitReconChange"
          />
        </template>
      </el-table-column>
    </el-table>

    <div class="diff-reason-row">
      <span class="diff-label">差异原因：</span>
      <el-input
        v-model="debitReconDiffReason"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 2 }"
        placeholder="说明收入价税合计与应收账款借方发生额差异的原因..."
        @change="onDebitReconChange"
      />
    </div>

    <!-- ═══════════ (三) 应收账款贷方发生额分析 ═══════════ -->
    <div class="section-title subsection">
      <span>(三) 应收账款贷方发生额分析</span>
      <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addCreditRow">+ 添加行</el-button>
      <GtReviewTrigger section-id="D2-analysis-credit" />
    </div>

    <el-table :data="creditAnalysisRows" border size="small" class="compact-table">
      <el-table-column label="项目" min-width="180">
        <template #default="{ row, $index }">
          <span v-if="$index === 0">{{ row.project }}</span>
          <el-input v-else v-model="row.project" :disabled="isReadonly" size="small" placeholder="项目名称" @change="onCreditAnalysisChange" />
        </template>
      </el-table-column>
      <el-table-column label="金额" align="right" min-width="140">
        <template #default="{ row }">
          <WpAmountInput
            v-model="row.amount"
            :disabled="isReadonly"
            size="small"
            style="width: 100%"
            @change="onCreditAnalysisChange"
          />
        </template>
      </el-table-column>
      <el-table-column prop="dataSource" label="数据来源" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.dataSource" :disabled="isReadonly" size="small" placeholder="数据来源" @change="onCreditAnalysisChange" />
        </template>
      </el-table-column>
      <el-table-column prop="crossCheck" label="与对方科目核对" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.crossCheck" :disabled="isReadonly" size="small" placeholder="核对说明" @change="onCreditAnalysisChange" />
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="说明" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.remark" :disabled="isReadonly" size="small" placeholder="说明" @change="onCreditAnalysisChange" />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
        <template #default="{ $index }">
          <el-button v-if="$index > 0" type="danger" link size="small" @click="removeCreditRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="credit-summary-row">
      <span>差异（合计 - 分项小计）：</span>
      <span class="formula-cell" title="= 贷方发生额合计 - 各分项之和">{{ displayPrefs.fmtAmount(creditDiffComputed) }}</span>
    </div>
    <div class="diff-reason-row">
      <span class="diff-label">差异原因：</span>
      <el-input
        v-model="creditDiffReason"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 2 }"
        placeholder="说明贷方发生额差异原因..."
        @change="onCreditAnalysisChange"
      />
    </div>

    <!-- ═══════════ (四) 期末应收账款前十名分析 ═══════════ -->
    <div class="section-title subsection">
      <span>(四) 期末应收账款前十名分析</span>
      <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addTop10Row">+ 添加客户</el-button>
      <el-button size="small" plain @click="exportTop10">导出</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="importTop10" style="display:inline-block">
        <el-button size="small" plain>导入</el-button>
      </el-upload>
      <GtReviewTrigger section-id="D2-analysis-top10" />
    </div>

    <el-table :data="top10Rows" border size="small" class="compact-table" show-summary :summary-method="getTop10Summary">
      <el-table-column label="客户名称" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.customerName" :disabled="isReadonly" size="small" placeholder="客户名称" @change="onTop10Change" />
        </template>
      </el-table-column>
      <el-table-column label="期末账面余额" align="right" min-width="120">
        <template #default="{ row }">
          <WpAmountInput v-model="row.endBalance" :disabled="isReadonly" size="small" style="width: 100%" @change="() => { calcTop10Row(row); onTop10Change() }" />
        </template>
      </el-table-column>
      <el-table-column label="期初账面余额" align="right" min-width="120">
        <template #default="{ row }">
          <WpAmountInput v-model="row.beginBalance" :disabled="isReadonly" size="small" style="width: 100%" @change="() => { calcTop10Row(row); onTop10Change() }" />
        </template>
      </el-table-column>
      <el-table-column label="变动金额" align="right" min-width="110" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= 期末 - 期初">{{ displayPrefs.fmtAmount(row.changeAmount || 0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动比例" align="right" width="90" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= (期末-期初) / 期初">{{ row.changeRatio != null ? (row.changeRatio * 100).toFixed(1) + '%' : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账龄" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.aging" :disabled="isReadonly" size="small" placeholder="账龄" @change="onTop10Change" />
        </template>
      </el-table-column>
      <el-table-column label="信用期" min-width="80">
        <template #default="{ row }">
          <el-input v-model="row.creditPeriod" :disabled="isReadonly" size="small" placeholder="信用期" @change="onTop10Change" />
        </template>
      </el-table-column>
      <el-table-column label="逾期金额" align="right" min-width="110">
        <template #default="{ row }">
          <WpAmountInput v-model="row.overdueAmount" :disabled="isReadonly" size="small" style="width: 100%" @change="onTop10Change" />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeTop10Row($index)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══════════ (五) 近两年账龄结构分析 ═══════════ -->
    <div class="section-title subsection">
      <span>(五) 近两年账龄结构分析</span>
      <span class="aging-mode-hint">
        账龄段：
        <el-tag size="small" type="info" effect="plain">{{ agingBands.join(' / ') }}</el-tag>
        <el-tooltip content="账龄段跟随 D2-1 审定表「账龄段口径」设置联动，如需修改请在 D2-1 切换" placement="top">
          <el-button size="small" text @click="jumpToSection && jumpToSection('审定表D2-1')">去修改</el-button>
        </el-tooltip>
      </span>
      <el-button size="small" plain @click="exportAgingCompare">导出</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="importAgingCompare" style="display:inline-block">
        <el-button size="small" plain>导入</el-button>
      </el-upload>
      <GtReviewTrigger section-id="D2-analysis-aging-compare" />
    </div>

    <el-table :data="agingCompareRows" border size="small" class="compact-table">
      <el-table-column prop="aging" label="账龄" width="100" />
      <el-table-column label="期末账面余额" align="right" min-width="120">
        <template #default="{ row }">
          <WpAmountInput v-model="row.endBalance" :disabled="isReadonly" size="small" style="width: 100%" @change="onAgingCompareChange" />
        </template>
      </el-table-column>
      <el-table-column label="各账龄占比" align="right" width="100" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= 本段期末 / 期末合计">{{ row.endRatio != null ? (row.endRatio * 100).toFixed(1) + '%' : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初账面余额" align="right" min-width="120">
        <template #default="{ row }">
          <WpAmountInput v-model="row.beginBalance" :disabled="isReadonly" size="small" style="width: 100%" @change="onAgingCompareChange" />
        </template>
      </el-table-column>
      <el-table-column label="各账龄占比" align="right" width="100" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= 本段期初 / 期初合计">{{ row.beginRatio != null ? (row.beginRatio * 100).toFixed(1) + '%' : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动金额" align="right" min-width="110" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= 期末 - 期初">{{ displayPrefs.fmtAmount(row.changeAmount || 0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动比例" align="right" width="90" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= (期末-期初) / 期初">{{ row.changeRatio != null ? (row.changeRatio * 100).toFixed(1) + '%' : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原因分析" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.reason" :disabled="isReadonly" size="small" placeholder="原因分析" @change="onAgingCompareChange" />
        </template>
      </el-table-column>
    </el-table>
    <!-- 合计行 -->
    <div class="aging-total-row">
      <span>合计：期末 {{ displayPrefs.fmtAmount(agingCompareTotal.endTotal) }} | 期初 {{ displayPrefs.fmtAmount(agingCompareTotal.beginTotal) }} | 变动 {{ displayPrefs.fmtAmount(agingCompareTotal.changeAmount) }}（{{ agingCompareTotal.changeRatio != null ? (agingCompareTotal.changeRatio * 100).toFixed(1) + '%' : '-' }}）</span>
    </div>

    <!-- ═══════════ 三、审计说明 ═══════════ -->
    <div class="section-title">
      <span>三、审计说明</span>
      <el-button v-if="aiAvailable && !isReadonly" size="small" type="primary" plain @click="onAiAnalysisNote">🤖 AI生成</el-button>
      <GtReviewTrigger section-id="D2-analysis-remark" />
    </div>
    <el-input
      v-model="remark"
      type="textarea"
      :autosize="{ minRows: 5 }"
      :disabled="isReadonly"
      placeholder="说明分析程序发现的异常波动原因、信用政策变化、与实质性程序的衔接..."
      @change="(v: string) => updateMetaField('remark', v)"
    />

    <!-- ═══════════ 四、审计结论 ═══════════ -->
    <div class="section-title">
      <span>四、审计结论</span>
      <GtReviewTrigger section-id="D2-analysis-conclusion" />
    </div>
    <el-input
      :model-value="dataSource"
      type="textarea"
      :autosize="{ minRows: 5 }"
      :disabled="isReadonly"
      placeholder="分析程序结论..."
      @change="(v: string) => updateMetaField('dataSource', v)"
    />

    <!-- 编制提示 -->
    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p>周转率 = 营业收入 / 平均应收账款；周转天数 = 365 / 周转率。较上期显著变动需分析原因（信用政策变化、收入确认、坏账）。</p>
      <p>借方发生额与收入核对：差异主要为非主营收入、跨期确认、预收转入等；差异过大需追查具体明细。</p>
      <p>贷方发生额分析：核对各科目对应方发生额是否一致，如银行存款借方、应收票据借方等。</p>
      <p>前十名分析：关注信用期内逾期金额占比、变动异常客户、关联方交易。</p>
      <p>账龄分布：长账龄占比上升往往预示回收风险与坏账计提不足，应与 D2-3/D2-9 交叉验证。</p>
      <p>前五大集中度过高需关注客户信用风险与关联方交易（联动 D2-6）。</p>
    </details>
  </div>
</template>

<script lang="ts">
// summary method for top10 table (needs to be non-setup)
function getTop10Summary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((_: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    // 期末余额(1)/期初余额(2)/变动金额(3)/逾期金额(7) 需要合计
    if ([1, 2, 3, 7].includes(index)) {
      const key = index === 1 ? 'endBalance' : index === 2 ? 'beginBalance' : index === 3 ? 'changeAmount' : 'overdueAmount'
      const total = data.reduce((s: number, row: any) => s + (row[key] || 0), 0)
      sums[index] = total === 0 ? '-' : total.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    } else {
      sums[index] = ''
    }
  })
  return sums
}
</script>


<style scoped>
.d2-tab-analysis { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }

/* Section titles */
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 20px 0 10px;
}
.section-title.subsection {
  margin-top: 24px;
  padding-left: 4px;
  border-left: 3px solid #409eff;
}
.aging-mode-hint { font-size: 12px; color: #909399; font-weight: normal; display: inline-flex; align-items: center; gap: 4px; margin-left: 8px; }

/* Audit objective */
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: var(--wp-font-size, 13px); line-height: 1.6; }

/* Warning */
.warning-alert { margin-bottom: 12px; }
.warn-chip { margin-left: 8px; vertical-align: middle; }

/* Cards */
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin-bottom: 16px; }
.indicator-card.wide { grid-column: span 2; }
.card-title { font-weight: 600; font-size: 14px; }
.card-value { font-size: 24px; font-weight: 700; color: #303133; margin-bottom: 4px; }
.card-label { font-size: 12px; color: #909399; }
.card-sub { font-size: 12px; color: #606266; }

/* Compact table */
.compact-table { font-size: var(--wp-font-size, 13px); }
:deep(.compact-table .el-table__cell) { padding: 4px 3px; }

/* Auto-calc columns */
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }

/* Formula cells */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
  padding: 0 2px;
}

/* Diff reason row */
.diff-reason-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 10px 0 16px;
}
.diff-label { white-space: nowrap; font-size: var(--wp-font-size, 13px); color: #606266; padding-top: 6px; }

/* Credit summary row */
.credit-summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

/* Aging total row */
.aging-total-row {
  margin: 8px 0 16px;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  font-weight: 500;
  padding: 6px 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

/* Toolbar */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 16px 0 12px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }

/* Guidance fold */
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
</style>
