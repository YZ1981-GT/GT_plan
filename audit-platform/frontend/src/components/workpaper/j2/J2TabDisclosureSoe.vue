<script setup lang="ts">
/**
 * J2TabDisclosureSoe — J2 长期应付职工薪酬/设定受益计划净资产附注披露（国有企业）
 *
 * 对齐源模板「附注披露信息（国有企业）」全 78 行结构：
 *  A 长期应付职工薪酬汇总（期初数/本期增加/本期减少/期末数 四列增减式）
 *    - 设定受益计划净负债 / 符合设定受益计划条件的其他长期职工福利的净负债 / 一年后支付的辞退福利 / 合计
 *  B 设定受益计划情况：单张合并表，义务现值｜计划资产｜净负债 三组并列（各含本期/上期），CAS9 六要素分解
 *  C 未折现的离职后福利预计到期分析
 *  D (1) 计划资产（公允价值构成）
 *  E (2) 精算假设
 *  F (3) 敏感性分析
 *  各区块 JSON 持久化到 checklist_responses.remark（item_id J2-soe-*）。
 */
import { ref, reactive, computed, inject, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { GenerateWorkpaperAiText } from '../composables/useWorkpaperScaffold'
import GtIndexChip from '../GtIndexChip.vue'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { J2_NOTE_SECTION, J2_DISCLOSURE_SHEET_NAME } from '../composables/j2NoteSectionMap'
import { buildJ2SoeSyncPayload } from '../composables/j2DisclosureSyncPayload'
import { useAuditContext } from '@/composables/useAuditContext'

interface RespItem { item_id: string; conclusion: string | null; remark: string | null }
const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, RespItem>
  isReadonly?: boolean
  saveImmediate?: (items: RespItem[]) => Promise<void> | void
}>()
const isReadonly = computed(() => props.isReadonly ?? false)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')

const KEY = {
  summary: 'J2-soe-summary', change: 'J2-soe-change', maturity: 'J2-soe-maturity',
  assets: 'J2-soe-assets', assume: 'J2-soe-assumptions', sens: 'J2-soe-sensitivity',
  noteTerm: 'J2-soe-note-termination', noteDbp: 'J2-soe-note-dbp', noteSens: 'J2-soe-note-sensitivity',
}

function n(v: unknown): number { const x = typeof v === 'number' ? v : parseFloat(String(v ?? '')); return Number.isFinite(x) ? x : 0 }
function fmt(v: number | null | undefined): string { if (v === null || v === undefined || v === 0) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtPct(v: number | null | undefined): string { if (v === null || v === undefined) return '-'; return (v * 100).toFixed(2) + '%' }

// ── A 汇总表（期初/本期增加/本期减少/期末，期末=期初+增-减） ─────────────────────
interface SumRow { key: string; label: string; begin: number; increase: number; decrease: number }
const summaryRows = reactive<SumRow[]>([
  { key: 'dbp_net', label: '设定受益计划净负债', begin: 0, increase: 0, decrease: 0 },
  { key: 'other_lt_net', label: '符合设定受益计划条件的其他长期职工福利的净负债', begin: 0, increase: 0, decrease: 0 },
  { key: 'termination', label: '一年后支付的辞退福利', begin: 0, increase: 0, decrease: 0 },
])
function sumEnd(r: SumRow): number { return n(r.begin) + n(r.increase) - n(r.decrease) }
const summaryTotal = computed(() => ({
  begin: summaryRows.reduce((s, r) => s + n(r.begin), 0),
  increase: summaryRows.reduce((s, r) => s + n(r.increase), 0),
  decrease: summaryRows.reduce((s, r) => s + n(r.decrease), 0),
  end: summaryRows.reduce((s, r) => s + sumEnd(r), 0),
}))

// ── B 设定受益计划情况：单张合并表（3 组 × 本期/上期 = 6 数值列） ────────────────
type MoveCol = 'dboCur' | 'dboPrior' | 'assetCur' | 'assetPrior' | 'netCur' | 'netPrior'
interface MoveRow {
  key: string; label: string; indent: number
  kind: 'leaf' | 'sum' | 'grand'; children?: string[]; assetNa?: boolean
  dboCur: number; dboPrior: number; assetCur: number; assetPrior: number; netCur: number; netPrior: number
}
function mv(key: string, label: string, indent: number, kind: MoveRow['kind'], opts: Partial<MoveRow> = {}): MoveRow {
  return { key, label, indent, kind, dboCur: 0, dboPrior: 0, assetCur: 0, assetPrior: 0, netCur: 0, netPrior: 0, ...opts }
}
const changeRows = reactive<MoveRow[]>([
  mv('begin', '一、期初余额', 0, 'leaf'),
  mv('pl', '二、计入当期损益的设定受益成本', 0, 'sum', { children: ['pl_service', 'pl_past', 'pl_settle', 'pl_interest'] }),
  mv('pl_service', '1．当期服务成本', 1, 'leaf', { assetNa: true }),
  mv('pl_past', '2．过去服务成本', 1, 'leaf', { assetNa: true }),
  mv('pl_settle', '3．结算利得（损失以"-"表示）', 1, 'leaf', { assetNa: true }),
  mv('pl_interest', '4．利息净额', 1, 'leaf'),
  mv('oci', '三、计入其他综合收益的设定受益成本', 0, 'sum', { children: ['oci_remeasure'] }),
  mv('oci_remeasure', '设定受益计划净负债（净资产）的重新计量', 1, 'sum', { children: ['oci_actuarial', 'oci_return', 'oci_ceiling'] }),
  mv('oci_actuarial', '1．精算利得（损失以"-"表示）', 2, 'leaf', { assetNa: true }),
  mv('oci_return', '2．计划资产的回报（计入利息净额的除外）', 2, 'leaf'),
  mv('oci_ceiling', '3．资产上限影响的变动（计入利息净额的除外）', 2, 'leaf'),
  mv('other', '四、其他变动', 0, 'sum', { children: ['other_settle', 'other_paid', 'other_etc'] }),
  mv('other_settle', '1．结算时消除的负债', 1, 'leaf'),
  mv('other_paid', '2．已支付的福利', 1, 'leaf'),
  mv('other_etc', '……', 1, 'leaf'),
  mv('end', '五、期末余额', 0, 'grand'),
])
const changeMap = computed(() => { const m: Record<string, MoveRow> = {}; for (const r of changeRows) m[r.key] = r; return m })
function isAssetCol(col: MoveCol): boolean { return col === 'assetCur' || col === 'assetPrior' }
/** 递归解析单元格值：leaf 直取（asset N/A 返 null）；sum 累加子项；grand = 期初+二+三+四 */
function cellValue(row: MoveRow, col: MoveCol): number | null {
  if (row.kind === 'leaf') {
    if (row.assetNa && isAssetCol(col)) return null
    return n(row[col])
  }
  if (row.kind === 'sum') return (row.children || []).reduce((s, ck) => s + (cellValue(changeMap.value[ck], col) ?? 0), 0)
  // grand（期末余额）
  return ['begin', 'pl', 'oci', 'other'].reduce((s, ck) => s + (cellValue(changeMap.value[ck], col) ?? 0), 0)
}
function editable(row: MoveRow, col: MoveCol): boolean {
  return !isReadonly.value && row.kind === 'leaf' && !(row.assetNa && isAssetCol(col))
}

// ── C 未折现到期分析 ──────────────────────────────────────────────────────────
const maturityRows = reactive([
  { key: 'y1', label: '一年以内', amount: 0 },
  { key: 'y1_2', label: '一到两年', amount: 0 },
  { key: 'y2_5', label: '二到五年', amount: 0 },
  { key: 'y5', label: '五年以上', amount: 0 },
])
const maturityTotal = computed(() => maturityRows.reduce((s, r) => s + n(r.amount), 0))

// ── D 计划资产构成（期末/期初；权益/债务工具投资为分组小计行） ──────────────────
interface AssetRow { key: string; label: string; indent: number; group?: boolean; end: number; begin: number }
const assetCompRows = reactive<AssetRow[]>([
  { key: 'cash', label: '现金和现金等价物', indent: 0, end: 0, begin: 0 },
  { key: 'equity', label: '权益工具投资', indent: 0, group: true, end: 0, begin: 0 },
  { key: 'equity_1', label: '1、……', indent: 1, end: 0, begin: 0 },
  { key: 'equity_2', label: '2、……', indent: 1, end: 0, begin: 0 },
  { key: 'debt', label: '债务工具投资', indent: 0, group: true, end: 0, begin: 0 },
  { key: 'debt_1', label: '1、……', indent: 1, end: 0, begin: 0 },
  { key: 'debt_2', label: '2、……', indent: 1, end: 0, begin: 0 },
  { key: 'other', label: '其他', indent: 0, end: 0, begin: 0 },
])
// 合计 = 现金 + 权益工具投资(小计) + 债务工具投资(小计) + 其他（不重复计子项）
const assetCompTotal = computed(() => {
  const keys = ['cash', 'equity', 'debt', 'other']
  return {
    end: assetCompRows.filter(r => keys.includes(r.key)).reduce((s, r) => s + n(r.end), 0),
    begin: assetCompRows.filter(r => keys.includes(r.key)).reduce((s, r) => s + n(r.begin), 0),
  }
})

// ── E 精算假设 ────────────────────────────────────────────────────────────────
const assumeRows = reactive([
  { key: 'discount', label: '折现率', end: 0, begin: 0 },
  { key: 'mortality', label: '死亡率', end: 0, begin: 0 },
  { key: 'life', label: '预计平均寿命', end: 0, begin: 0 },
  { key: 'turnover', label: '职工的离职率', end: 0, begin: 0 },
  { key: 'salary', label: '薪酬的预期增长率', end: 0, begin: 0 },
])
// ── F 敏感性分析 ──────────────────────────────────────────────────────────────
const sensRows = reactive([
  { key: 'discount', label: '折现率', delta: 0, up: 0, down: 0 },
  { key: 'mortality', label: '死亡率', delta: 0, up: 0, down: 0 },
  { key: 'life', label: '预计平均寿命', delta: 0, up: 0, down: 0 },
  { key: 'turnover', label: '职工的离职率', delta: 0, up: 0, down: 0 },
  { key: 'salary', label: '薪酬的预期增长率', delta: 0, up: 0, down: 0 },
])

// ── 说明文本（源模板固定指引作 placeholder，空值时显示、输入即隐藏，无需手动删除） ──
const PH_TERM = '1、辞退福利的性质、内容及计算依据详见附注八、35；\n2、其他长期职工福利的性质及计算依据。'
const PH_DBP = '1、设定受益计划形成的原因、特征及与之相关的风险；\n2、如有对计划的修改或结算的，还应当披露修改或结算计划的有关情况；\n3、影响设定受益计划未来缴存金额的有关筹资政策和计划、下一会计年度预期将缴存的金额，设定受益义务有关到期情况的信息，如设定受益义务的加权平均期间、对有关福利支付的到期日分析等。'
const PH_SENS = '上述敏感性分析是基于一个假设发生变动而其他假设均保持不变，但实际上各种假设通常是相互关联的。上述敏感性分析在计算设定受益义务现值时也同样采用累积福利单位法。进行敏感度分析所采用的重大假设的方法和类型与以前年度比较未发生变动。（如发生变动，应进一步说明发生的具体变动及原因。）'
const noteTerm = ref('')
const noteDbp = ref('')
const noteSens = ref('')
const aiLoading = ref('')

// ── 加载 ──────────────────────────────────────────────────────────────────────
function parseJson<T>(id: string, fb: T): T { const raw = props.allResponses?.get(id)?.remark; if (!raw) return fb; try { const p = JSON.parse(raw); return (p ?? fb) as T } catch { return fb } }
function assignRows<T extends object>(target: T[], saved: unknown) {
  if (!Array.isArray(saved)) return
  for (const s of saved as Record<string, unknown>[]) { const row = target.find(r => (r as Record<string, unknown>).key === s.key); if (row) Object.assign(row, s) }
}
function load() {
  assignRows(summaryRows, parseJson(KEY.summary, null))
  assignRows(changeRows, parseJson(KEY.change, null))
  assignRows(maturityRows, parseJson(KEY.maturity, null))
  assignRows(assetCompRows, parseJson(KEY.assets, null))
  assignRows(assumeRows, parseJson(KEY.assume, null))
  assignRows(sensRows, parseJson(KEY.sens, null))
  const t = props.allResponses?.get(KEY.noteTerm)?.remark; if (t) noteTerm.value = t
  const d = props.allResponses?.get(KEY.noteDbp)?.remark; if (d) noteDbp.value = d
  const s = props.allResponses?.get(KEY.noteSens)?.remark; if (s) noteSens.value = s
  // 从审定表(J2-1-main)自动 seed 汇总表期初数（仅在汇总表全 0 时）
  const anySum = summaryRows.some(r => n(r.begin) !== 0 || n(r.increase) !== 0 || n(r.decrease) !== 0)
  if (!anySum) {
    const mainRaw = props.allResponses?.get('J2-1-main')?.remark
    if (mainRaw) {
      try {
        const main = JSON.parse(mainRaw) as Array<Record<string, unknown>>
        const beginAud = (k: string) => { const r = main.find(x => x.key === k); return r ? n(r.beginUnadj) + n(r.beginAje) : 0 }
        summaryRows.find(r => r.key === 'dbp_net')!.begin = beginAud('dbp')
        summaryRows.find(r => r.key === 'termination')!.begin = beginAud('termination')
      } catch { /* ignore */ }
    }
  }
}

// ── 保存（防抖） ──────────────────────────────────────────────────────────────
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  props.saveImmediate([
    { item_id: KEY.summary, conclusion: null, remark: JSON.stringify(summaryRows) },
    { item_id: KEY.change, conclusion: null, remark: JSON.stringify(changeRows) },
    { item_id: KEY.maturity, conclusion: null, remark: JSON.stringify(maturityRows) },
    { item_id: KEY.assets, conclusion: null, remark: JSON.stringify(assetCompRows) },
    { item_id: KEY.assume, conclusion: null, remark: JSON.stringify(assumeRows) },
    { item_id: KEY.sens, conclusion: null, remark: JSON.stringify(sensRows) },
    { item_id: KEY.noteTerm, conclusion: null, remark: noteTerm.value },
    { item_id: KEY.noteDbp, conclusion: null, remark: noteDbp.value },
    { item_id: KEY.noteSens, conclusion: null, remark: noteSens.value },
  ])
}

// ── AI 辅助说明 ───────────────────────────────────────────────────────────────
async function aiGen(target: 'term' | 'dbp' | 'sens') {
  if (isReadonly.value) return
  aiLoading.value = target
  try {
    const context: Record<string, string> = {
      科目: '2221 长期应付职工薪酬 / 设定受益计划净资产（国有企业附注披露）',
      设定受益计划净负债期末: fmt(sumEnd(summaryRows.find(r => r.key === 'dbp_net')!)),
      辞退福利期末: fmt(sumEnd(summaryRows.find(r => r.key === 'termination')!)),
      合计期末: fmt(summaryTotal.value.end),
      设定受益义务现值期末: fmt(cellValue(changeMap.value['end'], 'dboCur')),
      计划资产公允价值期末: fmt(cellValue(changeMap.value['end'], 'assetCur')),
      折现率: fmtPct(assumeRows.find(r => r.key === 'discount')?.end ?? 0),
      薪酬增长率: fmtPct(assumeRows.find(r => r.key === 'salary')?.end ?? 0),
    }
    const existing = target === 'term' ? noteTerm.value : target === 'dbp' ? noteDbp.value : noteSens.value
    const text = await generateAiText({
      section: `j2-soe-disclosure-${target}`, context, existingContent: existing,
    })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
    } else {
      if (target === 'term') noteTerm.value = text
      else if (target === 'dbp') noteDbp.value = text
      else noteSens.value = text
      scheduleSave()
    }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

onMounted(load)
watch(() => props.allResponses, load, { deep: false })

// ── 同步到附注 ──────────────────────────────────────────────────────────────
const { projectId: ctxProjectId, auditYear } = useAuditContext()
const { scheduleAutoSync } = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })

async function syncToDisclosureNotes() {
  if (!props.wpId || !props.projectId) return
  const payload = buildJ2SoeSyncPayload({
    summaryRows: [...summaryRows],
    changeRows: changeRows.filter(r => r.kind === 'leaf').map(r => ({
      key: r.key,
      label: r.label,
      dboCur: r.dboCur,
      dboPrior: r.dboPrior,
      assetCur: r.assetCur,
      assetPrior: r.assetPrior,
      netCur: r.netCur,
      netPrior: r.netPrior,
    })),
    maturityRows: [...maturityRows],
    assetCompRows: [...assetCompRows],
    assumeRows: [...assumeRows],
    sensRows: [...sensRows],
    noteTerm: noteTerm.value,
    noteDbp: noteDbp.value,
    noteSens: noteSens.value,
    summaryEndFn: (r) => n(r.begin) + n(r.increase) - n(r.decrease),
  })
  try {
    const { default: axios } = await import('axios')
    await axios.post(`/api/workpapers/${props.wpId}/sync-from-workpaper`, {
      project_id: props.projectId,
      year: auditYear.value,
      ...payload,
    })
  } catch { /* 失败静默 */ }
}

// Watch actual data sources for auto-sync
watch(
  [
    () => JSON.stringify(summaryRows),
    () => JSON.stringify(changeRows),
    () => JSON.stringify(maturityRows),
    () => JSON.stringify(assetCompRows),
    () => JSON.stringify(assumeRows),
    () => JSON.stringify(sensRows),
    noteTerm,
    noteDbp,
    noteSens,
  ],
  () => { scheduleAutoSync(syncToDisclosureNotes) },
)
</script>

<template>
  <div class="j2-disclosure-soe">
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证设定受益计划附注披露（国有企业口径）的完整性与准确性——长期应付职工薪酬构成、设定受益计划义务现值/计划资产/净负债变动、精算假设及敏感性分析，满足 CAS 9《职工薪酬》披露要求，并与审定表（J2-1）、明细表（J2-2）勾稽一致。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="doc-title">长期应付职工薪酬/设定受益计划净资产附注披露信息（国有企业）</h3>
      <GtIndexChip value="wp:J2-1" :context-project-id="projectId" />
      <el-button size="small" type="success" plain :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
    </div>

    <!-- A 长期应付职工薪酬汇总 -->
    <h4 class="sec-title">长期应付职工薪酬（不适用的删除）</h4>
    <el-table :data="summaryRows" border size="small" class="wp-table" style="max-width: 860px">
      <el-table-column label="项  目" min-width="300">
        <template #default="{ row }">{{ row.label }}</template>
      </el-table-column>
      <el-table-column label="期初数" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.begin) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期增加" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.increase" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.increase) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期减少" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.decrease" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.decrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末数" width="130" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula-cell" title="= 期初数 + 本期增加 − 本期减少">{{ fmt(sumEnd(row)) }}</span></template>
      </el-table-column>
    </el-table>
    <div class="calc-line">合计：期初 {{ fmt(summaryTotal.begin) }} ｜ 本期增加 {{ fmt(summaryTotal.increase) }} ｜ 本期减少 {{ fmt(summaryTotal.decrease) }} ｜ 期末 {{ fmt(summaryTotal.end) }}</div>
    <div class="note-wrap">
      <div class="note-hd"><span>说明（辞退福利/其他长期职工福利的性质、内容及计算依据）</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'term'" :disabled="isReadonly" @click="aiGen('term')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="noteTerm" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" :placeholder="PH_TERM" @change="scheduleSave" />
    </div>

    <!-- B 设定受益计划情况（合并表：义务现值｜计划资产｜净负债，各含本期/上期） -->
    <h4 class="sec-title">设定受益计划情况</h4>
    <el-table :data="changeRows" border size="small" class="wp-table change-table"
      :row-class-name="({ row }) => row.kind !== 'leaf' ? 'group-row' : ''">
      <el-table-column label="项  目" min-width="300" fixed>
        <template #default="{ row }">
          <span :style="{ paddingLeft: row.indent * 16 + 'px', fontWeight: row.kind !== 'leaf' ? 600 : 400 }">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="设定受益计划义务现值" align="center">
        <el-table-column label="本期金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="editable(row, 'dboCur')" v-model="row.dboCur" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(cellValue(row, 'dboCur')) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="editable(row, 'dboPrior')" v-model="row.dboPrior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(cellValue(row, 'dboPrior')) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="计划资产的公允价值" align="center">
        <el-table-column label="本期金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="editable(row, 'assetCur')" v-model="row.assetCur" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else class="na-cell">{{ row.assetNa ? '—' : fmt(cellValue(row, 'assetCur')) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="editable(row, 'assetPrior')" v-model="row.assetPrior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else class="na-cell">{{ row.assetNa ? '—' : fmt(cellValue(row, 'assetPrior')) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="设定受益计划净负债（净资产）" align="center">
        <el-table-column label="本期金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="editable(row, 'netCur')" v-model="row.netCur" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(cellValue(row, 'netCur')) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="editable(row, 'netPrior')" v-model="row.netPrior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(cellValue(row, 'netPrior')) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
    </el-table>
    <div class="tip-block">提示：设定受益计划存在资产的，企业应当将设定受益计划义务现值减去设定受益计划资产公允价值所形成的赤字或盈余，确认为一项设定受益计划净负债或净资产。灰色分组行（二/三/四、期末余额、重新计量）为自动汇总，标"—"的计划资产单元格不适用。</div>
    <div class="note-wrap">
      <div class="note-hd"><span>说明（计划形成原因/特征/风险、修改或结算情况、筹资政策及到期分析）</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'dbp'" :disabled="isReadonly" @click="aiGen('dbp')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="noteDbp" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" :placeholder="PH_DBP" @change="scheduleSave" />
    </div>

    <!-- C 未折现到期分析 -->
    <h4 class="sec-title">未折现的离职后福利预计到期分析</h4>
    <el-table :data="maturityRows" border size="small" class="wp-table" style="max-width: 460px">
      <el-table-column prop="label" label="项  目" min-width="200" />
      <el-table-column label="金额" width="160" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.amount) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="calc-line">合计：{{ fmt(maturityTotal) }}</div>

    <!-- D (1) 计划资产 -->
    <h4 class="sec-title">（1）计划资产（公允价值构成）</h4>
    <el-table :data="assetCompRows" border size="small" class="wp-table" style="max-width: 620px"
      :row-class-name="({ row }) => row.group ? 'group-row' : ''">
      <el-table-column label="项  目" min-width="240">
        <template #default="{ row }"><span :style="{ paddingLeft: row.indent * 16 + 'px', fontWeight: row.group ? 600 : 400 }">{{ row.label }}</span></template>
      </el-table-column>
      <el-table-column label="期末数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.end" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.end) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.begin) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="calc-line">合计：期末 {{ fmt(assetCompTotal.end) }} ｜ 期初 {{ fmt(assetCompTotal.begin) }}</div>
    <div class="tip-block">提示：1、权益工具投资按行业类型或公司规模或地域等分类；2、债务工具投资按债务工具发行人类型或信用评级或地域等分类。</div>

    <!-- E (2) 精算假设 -->
    <h4 class="sec-title">（2）精算假设</h4>
    <el-table :data="assumeRows" border size="small" class="wp-table" style="max-width: 460px">
      <el-table-column prop="label" label="项  目" min-width="180" />
      <el-table-column label="期末数(%)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.end" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
          <span v-else>{{ fmtPct(row.end) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初数(%)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
          <span v-else>{{ fmtPct(row.begin) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="sec-hint">提示：假设录入小数（如折现率 4% 录入 0.04），系统按百分比展示。</div>

    <!-- F (3) 敏感性分析 -->
    <h4 class="sec-title">（3）敏感性分析</h4>
    <el-table :data="sensRows" border size="small" class="wp-table" style="max-width: 720px">
      <el-table-column prop="label" label="项目" min-width="150" />
      <el-table-column label="假设的变动幅度(%)" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.delta" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
          <span v-else>{{ fmtPct(row.delta) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对设定受益义务现值的影响" align="center">
        <el-table-column label="计划负债增加" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.up" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.up) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划负债减小" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.down" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.down) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
    </el-table>
    <div class="note-wrap">
      <div class="note-hd"><span>说明（敏感性分析方法与假设变动）</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'sens'" :disabled="isReadonly" @click="aiGen('sens')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="noteSens" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" :placeholder="PH_SENS" @change="scheduleSave" />
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》及国有企业披露要求，汇总表按"期初数 + 本期增加 − 本期减少 = 期末数"列示长期应付职工薪酬各构成项目。</p>
        <p>2. 设定受益计划情况表按义务现值、计划资产公允价值、净负债三组并列，各组分本期/上期，并按 CAS9 六要素（服务成本/利息净额/精算利得损失/计划资产回报/结算/已付福利）分解；分组行与期末余额行自动汇总。</p>
        <p>3. 净负债 = 设定受益义务现值 − 计划资产公允价值；三组期末余额须勾稽一致。标"—"的计划资产单元格为不适用项目。</p>
        <p>4. 附注金额应与审定表（J2-1）、明细表（J2-2）勾稽一致；汇总表期初数已从审定表自动带入（可覆盖）。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.j2-disclosure-soe { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.doc-title { font-size: 15px; font-weight: 600; margin: 0; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 20px 0 8px; }
.sec-hint, .tip-block { font-size: 12px; color: #909399; margin: 6px 0; }
.tip-block { background: #fdf6ec; border-left: 3px solid #e6a23c; padding: 6px 10px; border-radius: 4px; color: #b88230; }
.calc-line { padding: 4px 12px; font-weight: 600; font-size: 13px; color: #303133; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.wp-table :deep(.el-input-number) { width: 100%; }
.wp-table :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
.wp-table :deep(.group-row) { background: #f5f7fa !important; }
.change-table { max-width: 1100px; }
.na-cell { color: #c0c4cc; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.formula-cell { border-bottom: 1px dashed #409eff; cursor: help; }
.note-wrap { margin-top: 12px; }
.note-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #303133; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
