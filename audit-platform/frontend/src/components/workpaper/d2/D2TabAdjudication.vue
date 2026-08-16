<script setup lang="ts">
/**
 * D2TabAdjudication — 审定表 D2-1（模板结构版）
 * 按 Excel 模板恢复区块样式，并支持账龄段枚举口径（3年段 / 5年段 / 自定义）
 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import { PRESET_SEGMENTS, type AgingPreset, type AgingSegment } from '@/composables/useAgingConfig'
import { Download } from '@element-plus/icons-vue'
import { useD2Adjudication, type AdjudicationRow } from '../composables/useD2Adjudication'
import { useD2CrossSheet } from '../composables/useD2CrossSheet'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { getChangeRate } from '../composables/useD2FormulaEngine'
import { useD2SaveInject } from '../composables/useD2SaveInject'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpFourTableSourcePanel from '@/components/workpaper/shared/WpFourTableSourcePanel.vue'
import {
  pickDTbSourceCodes,
  normalizeDSlots,
  dCycleBasisLabel,
} from '../composables/dCycleAccountScope'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /**
   * render 下发的本 sheet `html_data`（含 `tb_source_codes` / `parent_check`）。
   *
   * 🔴 必须由宿主显式传入 —— 漏传不会报错、只会让四表取数溯源恒 `undefined`
   * （Vue 对未声明的属性会静默落到根元素当 HTML 属性，`get_diagnostics`/vitest/
   * Vite transform 四层全绿），平台已登记该范式为「漏传 prop = 静默锁死」。
   */
  htmlData?: Record<string, any> | null
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const baseOpts = {
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
}

const {
  adjudicationRows,
  totalRow,
  trialBalanceDiff,
  updateCell,
  isChangeRateWarning,
  sumifStatus,
  detailCrossValidation,
  eclCrossValidation,
} = useD2Adjudication(baseOpts)

const crossSheet = useD2CrossSheet({ allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>> })

// ─── 从集中登记带入调整（1122 应收账款，资产借方；带入期末 AJE/RJE） ────────────
const bringInRows = computed(() =>
  adjudicationRows.value
    .filter((r) => r.rowKey !== 'total')
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.currentAje, rje: r.currentRje })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1122',
  direction: 'debit',
  subjectCode: '1122',
  wpCode: 'D2',
  subjectLabel: '应收账款(1122)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'current-rje' : 'current-aje', value),
  totalAudited: () => totalRow.value.currentAudited,
})

const { generateAndConfirm, aiAvailable } = useD2AiGenerate(toRef(props, 'wpId'))

const { saveItems } = useD2SaveInject()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-1',
)

const auditNote = ref('')
const auditConclusion = ref('')

function loadAuditTexts(): void {
  auditNote.value = props.allResponses.get('D2-adj-audit-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D2-adj-audit-conclusion')?.remark || ''
}

watch(() => props.allResponses, loadAuditTexts, { immediate: true, deep: true })

function saveAuditField(field: 'note' | 'conclusion', value: string): void {
  const id = field === 'note' ? 'D2-adj-audit-note' : 'D2-adj-audit-conclusion'
  props.allResponses.set(id, { item_id: id, conclusion: null, remark: value })
  void saveItems([{ item_id: id, conclusion: null, remark: value }])
}

const loading = computed(() => sumifStatus.value === 'computing')

interface SectionRow {
  rowKey: string
  label: string
  priorAudited: number
  currentAudited: number
  change: number
  changeRate: number | ''
  isFromCrossSheet?: boolean
  isEditable?: boolean
}
interface ExcelMainRow {
  key: string
  label: string
  level: 0 | 1 | 2
  rowType: 'section' | 'data' | 'subtotal' | 'placeholder'
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
  change: number
  changeRate: number | ''
  reasonAnalysis: string
}

function mapGrossRows(): SectionRow[] {
  return adjudicationRows.value.map(r => ({
    rowKey: r.rowKey,
    label: r.label,
    priorAudited: r.priorAudited,
    currentAudited: r.currentAudited,
    change: r.change,
    changeRate: r.changeRate,
    isFromCrossSheet: r.isFromSumif,
    isEditable: r.isEditable,
  }))
}
function getGrossByKey(rowKey: string): AdjudicationRow | null {
  return adjudicationRows.value.find((r) => r.rowKey === rowKey) || null
}
function getProvisionByKey(rowKey: string): SectionRow | null {
  return provisionRows.value.find((r) => r.rowKey === rowKey) || null
}
function getNetByKey(rowKey: string): SectionRow | null {
  return netRows.value.find((r) => r.rowKey === rowKey) || null
}
function toMainRow(
  key: string,
  label: string,
  level: 0 | 1 | 2,
  rowType: 'section' | 'data' | 'subtotal' | 'placeholder',
  src?: Partial<ExcelMainRow>,
): ExcelMainRow {
  return {
    key,
    label,
    level,
    rowType,
    priorUnadjusted: src?.priorUnadjusted || 0,
    priorAje: src?.priorAje || 0,
    priorRje: src?.priorRje || 0,
    priorAudited: src?.priorAudited || 0,
    currentUnadjusted: src?.currentUnadjusted || 0,
    currentAje: src?.currentAje || 0,
    currentRje: src?.currentRje || 0,
    currentAudited: src?.currentAudited || 0,
    change: src?.change || 0,
    changeRate: src?.changeRate ?? '',
    reasonAnalysis: src?.reasonAnalysis || '',
  }
}


const provisionRows = computed<SectionRow[]>(() => {
  const bd = crossSheet.badDebtByCategory.value
  const items = [
    { rowKey: 'individual', label: '单项计提坏账准备', data: bd.individual },
    { rowKey: 'aging', label: '账龄组合坏账准备', data: bd.aging },
    { rowKey: 'customer-type', label: '客户类型组合坏账准备', data: bd.customerType },
  ]
  const rows = items.map(({ rowKey, label, data }) => {
    const change = data.current - data.prior
    return {
      rowKey,
      label,
      priorAudited: data.prior,
      currentAudited: data.current,
      change,
      changeRate: getChangeRate(data.prior, data.current),
      isFromCrossSheet: true,
      isEditable: false,
    }
  })
  const prior = rows.reduce((s, r) => s + r.priorAudited, 0)
  const current = rows.reduce((s, r) => s + r.currentAudited, 0)
  rows.push({
    rowKey: 'total',
    label: '小计',
    priorAudited: prior,
    currentAudited: current,
    change: current - prior,
    changeRate: getChangeRate(prior, current),
    isEditable: false,
  })
  return rows
})

const netRows = computed<SectionRow[]>(() => {
  const gross = mapGrossRows().filter(r => r.rowKey !== 'total')
  const prov = provisionRows.value.filter(r => r.rowKey !== 'total')
  const rows: SectionRow[] = gross.map((g, i) => {
    const p = prov[i] || { priorAudited: 0, currentAudited: 0 }
    const prior = g.priorAudited - p.priorAudited
    const current = g.currentAudited - p.currentAudited
    return {
      rowKey: g.rowKey,
      label: g.label.replace('应收账款-', '净值-'),
      priorAudited: prior,
      currentAudited: current,
      change: current - prior,
      changeRate: getChangeRate(prior, current),
      isEditable: false,
    }
  })
  const prior = rows.reduce((s, r) => s + r.priorAudited, 0)
  const current = rows.reduce((s, r) => s + r.currentAudited, 0)
  rows.push({
    rowKey: 'total',
    label: '合计',
    priorAudited: prior,
    currentAudited: current,
    change: current - prior,
    changeRate: getChangeRate(prior, current),
    isEditable: false,
  })
  return rows
})
const excelMainRows = computed<ExcelMainRow[]>(() => {
  const gIndividual = getGrossByKey('individual')
  const gAging = getGrossByKey('aging')
  const gCustomer = getGrossByKey('customer-type')
  const gTotal = getGrossByKey('total')

  const pIndividual = getProvisionByKey('individual')
  const pAging = getProvisionByKey('aging')
  const pCustomer = getProvisionByKey('customer-type')
  const pTotal = getProvisionByKey('total')

  const nIndividual = getNetByKey('individual')
  const nAging = getNetByKey('aging')
  const nCustomer = getNetByKey('customer-type')
  const nTotal = getNetByKey('total')

  return [
    toMainRow('sec-gross', '一、应收账款原值', 0, 'section'),
    toMainRow('gross-individual', '单项计提坏账准备', 1, 'data', gIndividual || undefined),
    toMainRow('gross-aging-combo', '按组合计提坏账准备', 1, 'data', gAging || undefined),
    toMainRow('gross-aging-band', '账龄组合', 2, 'data', gAging || undefined),
    toMainRow('gross-customer-band', '客户类型组合', 2, 'data', gCustomer || undefined),
    toMainRow('gross-other-band', '……组合', 2, 'placeholder'),
    toMainRow('gross-subtotal', '小计', 1, 'subtotal', gTotal || undefined),

    toMainRow('sec-provision', '二、应收账款坏账准备', 0, 'section'),
    toMainRow('provision-individual', '单项计提坏账准备', 1, 'data', pIndividual ? {
      priorAudited: pIndividual.priorAudited, currentAudited: pIndividual.currentAudited, change: pIndividual.change, changeRate: pIndividual.changeRate,
    } : undefined),
    toMainRow('provision-aging-combo', '按组合计提坏账准备', 1, 'data', pAging ? {
      priorAudited: pAging.priorAudited, currentAudited: pAging.currentAudited, change: pAging.change, changeRate: pAging.changeRate,
    } : undefined),
    toMainRow('provision-aging-band', '账龄组合', 2, 'data', pAging ? {
      priorAudited: pAging.priorAudited, currentAudited: pAging.currentAudited, change: pAging.change, changeRate: pAging.changeRate,
    } : undefined),
    toMainRow('provision-customer-band', '客户类型组合', 2, 'data', pCustomer ? {
      priorAudited: pCustomer.priorAudited, currentAudited: pCustomer.currentAudited, change: pCustomer.change, changeRate: pCustomer.changeRate,
    } : undefined),
    toMainRow('provision-other-band', '……组合', 2, 'placeholder'),
    toMainRow('provision-subtotal', '小计', 1, 'subtotal', pTotal ? {
      priorAudited: pTotal.priorAudited, currentAudited: pTotal.currentAudited, change: pTotal.change, changeRate: pTotal.changeRate,
    } : undefined),

    toMainRow('sec-net', '三、应收账款净值', 0, 'section'),
    toMainRow('net-individual', '单项计提坏账准备', 1, 'data', nIndividual ? {
      priorAudited: nIndividual.priorAudited, currentAudited: nIndividual.currentAudited, change: nIndividual.change, changeRate: nIndividual.changeRate,
    } : undefined),
    toMainRow('net-aging-combo', '按组合计提坏账准备', 1, 'data', nAging ? {
      priorAudited: nAging.priorAudited, currentAudited: nAging.currentAudited, change: nAging.change, changeRate: nAging.changeRate,
    } : undefined),
    toMainRow('net-aging-band', '账龄组合', 2, 'data', nAging ? {
      priorAudited: nAging.priorAudited, currentAudited: nAging.currentAudited, change: nAging.change, changeRate: nAging.changeRate,
    } : undefined),
    toMainRow('net-customer-band', '客户类型组合', 2, 'data', nCustomer ? {
      priorAudited: nCustomer.priorAudited, currentAudited: nCustomer.currentAudited, change: nCustomer.change, changeRate: nCustomer.changeRate,
    } : undefined),
    toMainRow('net-other-band', '……组合', 2, 'placeholder'),
    toMainRow('net-subtotal', '合计', 1, 'subtotal', nTotal ? {
      priorAudited: nTotal.priorAudited, currentAudited: nTotal.currentAudited, change: nTotal.change, changeRate: nTotal.changeRate,
    } : undefined),
  ]
})

/**
 * 账龄段（枚举账龄：3年段 / 5年段 / 自定义）统一取自**项目账龄配置**，
 * 由主入口 provide('d2AgingSegments')；本 tab 不再自建 3y/5y/custom 第二套口径
 * （旧实现 key 用 within1Year、label 用「一年以内」，与 D2-2 明细/披露/ECL 全对不上）。
 * 项目账龄配置入口：项目设置中心 → 底稿配置 → 账龄配置。
 */
const injectedAgingSegments = inject<Ref<AgingSegment[]> | null>('d2AgingSegments', null)
const injectedAgingPreset = inject<Ref<AgingPreset> | null>('d2AgingPreset', null)

const agingSegments = computed<AgingSegment[]>(() => {
  const list = injectedAgingSegments?.value
  if (Array.isArray(list) && list.length > 0) return list
  return PRESET_SEGMENTS.FIVE_YEAR
})

const AGING_PRESET_LABEL: Record<string, string> = {
  THREE_YEAR: '3 年段',
  FIVE_YEAR: '5 年段',
  CUSTOM: '自定义',
}
const agingPresetLabel = computed(() => AGING_PRESET_LABEL[injectedAgingPreset?.value ?? 'FIVE_YEAR'] ?? '5 年段')

/** 归一化账龄标签用于匹配 D2-3 旧数据（「一年以内」↔「1年以内」等中文数字/全角差异）。 */
function normalizeAgingLabel(label: string): string {
  return String(label ?? '')
    .replace(/[（）()\s]/g, '')
    .replace(/[一二三四五六七八九十]/g, (ch) => String('一二三四五六七八九十'.indexOf(ch) + 1))
    .replace(/[到至]/g, '-')
    .replace(/年以上/g, '年+')
}

const agingTableRows = computed(() => {
  const segments = agingSegments.value
  const source = crossSheet.agingFromDetail.value.audited as Record<string, number>
  const bdRows = (() => {
    try {
      const raw = props.allResponses.get('D2-bd-aging-rows')?.remark
      if (!raw) return []
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })()

  /** D2-3 账龄组合子行按标签匹配（含旧措辞兼容） */
  function resolveBdAmount(seg: AgingSegment): number {
    const target = normalizeAgingLabel(seg.label)
    return bdRows.reduce((sum: number, row: any) => {
      const label = normalizeAgingLabel(row?.label)
      const hit = Boolean(label) && (label.includes(target) || target.includes(label))
      return hit ? sum + (Number(row?.currentAudited) || 0) : sum
    }, 0)
  }

  return segments.map((seg) => {
    const gross = Number(source[seg.key]) || 0
    const provision = resolveBdAmount(seg)
    return {
      label: seg.label,
      gross,
      provision,
      net: gross - provision,
    }
  })
})

const agingTotal = computed(() => ({
  gross: agingTableRows.value.reduce((s, r) => s + r.gross, 0),
  provision: agingTableRows.value.reduce((s, r) => s + r.provision, 0),
  net: agingTableRows.value.reduce((s, r) => s + r.net, 0),
}))

function fmtRate(rate: number | ''): string {
  if (rate === '') return '-'
  return (rate * 100).toFixed(1) + '%'
}

function getCellClass(row: SectionRow | AdjudicationRow, field: string): string {
  const classes: string[] = []
  if ('isFromCrossSheet' in row && row.isFromCrossSheet && field === 'currentAudited') {
    classes.push('sumif-cell')
  }
  if ('isFromSumif' in row && row.isFromSumif && field === 'currentAudited') {
    classes.push('sumif-cell')
  }
  if (field === 'changeRate' && isChangeRateWarning(row.changeRate as number | '')) {
    classes.push('rate-warning')
  }
  return classes.join(' ')
}
function projectCellClass(row: ExcelMainRow): string {
  const cls = []
  if (row.rowType === 'section') cls.push('project-section')
  if (row.rowType === 'subtotal') cls.push('project-subtotal')
  if (row.level === 1) cls.push('project-level-1')
  if (row.level === 2) cls.push('project-level-2')
  if (row.label.includes('组合') || row.label.includes('……')) cls.push('project-red')
  return cls.join(' ')
}

async function onAiNote(section: 'adj-note' | 'adj-conclusion'): Promise<void> {
  const existing = section === 'adj-note' ? auditNote.value : auditConclusion.value
  const title = section === 'adj-note' ? 'AI 生成审计说明' : 'AI 生成审计结论'
  const content = await generateAndConfirm(section, existing, {
    grossTotal: totalRow.value.currentAudited,
    changeRate: totalRow.value.changeRate,
    badDebtTotal: crossSheet.badDebtTotal.value.current,
  }, title)
  if (section === 'adj-note') {
    auditNote.value = content
    saveAuditField('note', content)
  } else {
    auditConclusion.value = content
    saveAuditField('conclusion', content)
  }
}

// ─── 四表库取数溯源（Task 16）────────────────────────────────────────
// 🔴 落点两套并存：D1/D2/D3/D5/D6/D7 写 `html_data` 顶层、D4 写
// `project_context` —— `pickDTbSourceCodes` 两层都读，只读一层会恒 undefined。
const dTbSourceCodes = computed(() =>
  normalizeDSlots(pickDTbSourceCodes(props.htmlData)),
)
const dSourceHints = [
  '取数口径：<code>期末余额</code>；标准码查试算平衡表、客户原始码查余额表。',
  '「本项目无此科目」与「余额为 0」是两回事 —— 前者金额显示为空，后者显示 0.00。',
]

</script>

<template>
  <div class="d2-tab-adjudication">
    <!-- 四表库取数溯源（消 dead output：消费 render 下发的 tb_source_codes；
         口径 = {{ dCycleBasisLabel('D2') }}） -->
    <WpFourTableSourcePanel
      :source-codes="dTbSourceCodes"
      gross-label="应收账款原值"
      provision-label="坏账准备-应收账款"
      fallback-row-code="BS-006"
      :hints="dSourceHints"
    />
    <div class="tab-header">
      <h4>应收账款审定表 D2-1</h4>
      <GtReviewTrigger section-id="D2-adj-header" />
      <div class="toolbar-right">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small" :disabled="isReadonly">导入数据</el-button>
        </el-upload>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>汇总应收账款期初/本期变动/期末审定数，核对明细表、ECL 与试算平衡表，确认科目 1122 余额的真实、完整、准确。</p>
      </template>
    </el-alert>

    <el-alert v-if="detailCrossValidation" type="warning" :closable="false" class="cross-alert">
      {{ detailCrossValidation }}
      <GtIndexChip v-if="jumpToSection" label="D2-2" class="warn-chip" @click="jumpToSection('明细表D2-2')" />
    </el-alert>
    <el-alert v-if="eclCrossValidation" type="warning" :closable="false" class="cross-alert">
      {{ eclCrossValidation }}
      <GtIndexChip v-if="jumpToSection" label="D2-9" class="warn-chip" @click="jumpToSection('应收坏账准备测算D2-9')" />
    </el-alert>

    <el-alert v-if="!trialBalanceDiff.isZero" type="error" :closable="false" class="tb-alert">
      试算平衡表差异：{{ displayPrefs.fmtAmount(trialBalanceDiff.amount) }}（科目1122）
    </el-alert>

    <el-skeleton :loading="loading" :rows="8" animated>
      <template #default>

        <!-- 主表（按模板行结构） -->
        <div class="section-block section-gross">
          <el-table :data="excelMainRows" border stripe size="small" class="d2-main-grid">
            <el-table-column prop="label" label="项目" width="180" fixed>
              <template #default="{ row }">
                <span :class="projectCellClass(row)">{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初" align="center">
              <el-table-column label="未审" width="95" align="right">
                <template #default="{ row }">{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.priorUnadjusted) }}</template>
              </el-table-column>
              <el-table-column label="AJE" width="85" align="right">
                <template #default="{ row }">{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.priorAje) }}</template>
              </el-table-column>
              <el-table-column label="RJE" width="85" align="right">
                <template #default="{ row }">{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.priorRje) }}</template>
              </el-table-column>
              <el-table-column label="审定" width="95" align="right">
                <template #default="{ row }">{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.priorAudited) }}</template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="期末" align="center">
              <el-table-column label="未审" width="95" align="right">
                <template #default="{ row }">
                  <span>{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.currentUnadjusted) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="AJE" width="85" align="right">
                <template #default="{ row }">{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.currentAje) }}</template>
              </el-table-column>
              <el-table-column label="RJE" width="85" align="right">
                <template #default="{ row }">{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.currentRje) }}</template>
              </el-table-column>
              <el-table-column label="审定" width="95" align="right">
                <template #default="{ row }">
                  <span>{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.currentAudited) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="变动额" width="100" align="right">
              <template #default="{ row }">{{ row.rowType === 'section' ? '' : displayPrefs.fmtAmount(row.change) }}</template>
            </el-table-column>
            <el-table-column label="变动率" width="90" align="right">
              <template #default="{ row }">
                <span>{{ row.rowType === 'section' ? '' : fmtRate(row.changeRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原因分析" min-width="140">
              <template #default="{ row }">
                <span>{{ row.rowType === 'section' ? '' : (row.reasonAnalysis || '-') }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 账龄组合原值附表 -->
        <div class="section-block section-aging">
          <div class="section-title-row">
            <div class="section-title">（一）账龄组合列示（联动枚举口径）</div>
            <div class="aging-mode-tools">
              <span class="aging-mode-label">账龄段口径：</span>
              <el-tag size="small" type="primary" effect="plain">{{ agingPresetLabel }}</el-tag>
              <el-tag size="small" type="info" effect="plain">{{ agingSegments.map(s => s.label).join(' / ') }}</el-tag>
            </div>
          </div>

          <el-alert type="info" :closable="true" class="aging-usage-hint">
            <template #title>
              <span style="font-weight:500">账龄段口径说明</span>
            </template>
            <template #default>
              <ul style="margin:4px 0 0;padding-left:18px;font-size:12px;line-height:1.8;color:#606266">
                <li>账龄段统一由<b>项目账龄配置</b>决定，三种枚举：<b>3 年段 / 5 年段 / 自定义</b></li>
                <li>修改入口：项目设置中心 → 底稿配置 → 账龄配置（需项目经理及以上权限）</li>
                <li>保存后 D2-1 审定表、D2-2 明细、D2-3 坏账、D2-5 分析、ECL/政策检查、附注披露表账龄列头与取数口径同步变化</li>
                <li>本表账龄组合原值取自 D2-2 明细表期末审定账龄；坏账准备取自 D2-3 账龄组合子行</li>
              </ul>
            </template>
          </el-alert>

          <el-table :data="agingTableRows" border size="small" style="max-width: 760px">
            <el-table-column prop="label" label="账龄段" width="180" />
            <el-table-column label="账龄组合原值" align="right">
              <template #default="{ row }">
                <span class="sumif-cell">{{ displayPrefs.fmtAmount(row.gross) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账龄组合坏账准备" align="right">
              <template #default="{ row }">{{ displayPrefs.fmtAmount(row.provision) }}</template>
            </el-table-column>
            <el-table-column label="账龄组合净值" align="right">
              <template #default="{ row }"><span class="audited-cell">{{ displayPrefs.fmtAmount(row.net) }}</span></template>
            </el-table-column>
          </el-table>
          <div class="aging-total">
            小计：原值 {{ displayPrefs.fmtAmount(agingTotal.gross) }}；
            坏账准备 {{ displayPrefs.fmtAmount(agingTotal.provision) }}；
            净值 {{ displayPrefs.fmtAmount(agingTotal.net) }}
          </div>
        </div>

        <!-- 试算平衡 -->
        <div class="tb-row">
          <span>试算平衡表数（1122）：{{ displayPrefs.fmtAmount(parseFloat(String(allResponses.get('D2-adj-tb-amount')?.remark || '0')) || 0) }}</span>
          <span :class="{ 'rate-warning': !trialBalanceDiff.isZero }">
            差异：{{ displayPrefs.fmtAmount(trialBalanceDiff.amount) }}
          </span>
        </div>
      </template>
    </el-skeleton>

    <!-- 审计说明 / 结论 -->
    <div class="audit-footer">
      <el-row :gutter="16">
        <el-col :span="12">
          <div class="audit-block">
            <div class="audit-block-header">
              <span>1. 审计说明</span>
              <el-button v-if="aiAvailable && !isReadonly" size="small" text type="primary" @click="onAiNote('adj-note')">🤖 AI生成</el-button>
              <GtReviewTrigger section-id="D2-adj-audit-note" />
            </div>
            <el-input
              v-model="auditNote"
              type="textarea"
              :autosize="{ minRows: 5 }"
              :disabled="isReadonly"
              placeholder="说明应收账款变动原因..."
              @change="saveAuditField('note', auditNote)"
            />
          </div>
        </el-col>
        <el-col :span="12">
          <div class="audit-block">
            <div class="audit-block-header">
              <span>2. 审计结论</span>
              <el-button v-if="aiAvailable && !isReadonly" size="small" text type="primary" @click="onAiNote('adj-conclusion')">🤖 AI生成</el-button>
              <GtReviewTrigger section-id="D2-adj-audit-conclusion" />
            </div>
            <el-input
              v-model="auditConclusion"
              type="textarea"
              :autosize="{ minRows: 5 }"
              :disabled="isReadonly"
              placeholder="审计结论..."
              @change="saveAuditField('conclusion', auditConclusion)"
            />
          </div>
        </el-col>
      </el-row>
    </div>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1122 应收账款"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<style scoped>
.d2-tab-adjudication { padding: 12px; background: #fff; }
.tab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}
.tab-header h4 {
  margin: 0;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.toolbar-right { display: flex; gap: 8px; align-items: center; margin-left: auto; }
.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(p) { margin: 0; font-size: var(--wp-font-size, 13px); line-height: 1.6; }
.tb-alert { margin-bottom: 12px; }
.cross-alert { margin-bottom: 12px; }
.warn-chip { margin-left: 8px; vertical-align: middle; }
.section-block {
  margin-bottom: 16px;
  border-radius: 8px;
  padding: 12px;
  border: 1px solid #ebeef5;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}
.excel-header-card {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
  background: #fff;
}
.excel-title-main,
.excel-title-sub {
  text-align: center;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.excel-title-main {
  padding: 6px 8px 2px;
  font-size: 14px;
  border-bottom: 1px solid #ebeef5;
}
.excel-title-sub {
  padding: 2px 8px 6px;
  font-size: 15px;
  border-bottom: 1px solid #ebeef5;
}
.excel-meta-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 120px;
}
.meta-cell {
  min-height: 30px;
  display: flex;
  align-items: center;
  padding: 6px 8px;
  border-right: 1px solid #ebeef5;
  border-bottom: 1px solid #ebeef5;
  font-size: var(--wp-font-size, 13px);
}
.meta-cell:nth-child(4n) {
  border-right: none;
}
.meta-label {
  color: #606266;
}
.meta-value {
  color: #303133;
  font-weight: 500;
}
.section-gross,
.section-provision,
.section-net,
.section-aging {
  border-left: 3px solid #dcdfe6;
}
.section-title { font-weight: 600; font-size: var(--wp-font-size, 13px); margin-bottom: 10px; color: #303133; }
.section-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.aging-mode-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}
.aging-mode-label { color: #606266; font-size: var(--wp-font-size, 13px); }
.aging-usage-hint { margin: 8px 0 12px; }
.custom-aging-editor {
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  background: #fafcff;
  padding: 8px;
  margin-bottom: 10px;
}
.custom-aging-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.sumif-cell { background: #eef6ff; padding: 2px 6px; border-radius: 4px; color: #225b9c; }
.rate-warning { color: #f56c6c; font-weight: 600; }
.audited-cell { font-weight: 600; }
.aging-total { margin-top: 8px; font-size: var(--wp-font-size, 13px); font-weight: 600; text-align: right; padding-right: 12px; color: #606266; }
.tb-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); margin-bottom: 16px; }
.audit-footer { margin-top: 16px; }
.audit-block-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-weight: 600; font-size: var(--wp-font-size, 13px); }

:deep(.el-table th.el-table__cell) {
  background: #f7f8fa;
  color: #303133;
  font-size: var(--wp-font-size, 13px);
}
:deep(.d2-main-grid thead tr:first-child th.el-table__cell) {
  background: #eceff5;
  border-bottom-color: #cfd6e4;
  font-weight: 700;
}
:deep(.d2-main-grid thead tr:nth-child(2) th.el-table__cell) {
  background: #f5f7fb;
  font-weight: 600;
}
:deep(.d2-main-grid .el-table__row) {
  --el-table-tr-bg-color: #fff;
}
:deep(.d2-main-grid .el-table__row td:first-child .cell) {
  font-weight: 500;
}
.project-section {
  font-weight: 700;
  color: #1f2d3d;
}
.project-subtotal {
  font-weight: 700;
}
.project-level-1 {
  padding-left: 6px;
}
.project-level-2 {
  padding-left: 20px;
}
.project-red {
  color: #c0392b;
}
:deep(.el-table td.el-table__cell) {
  padding-top: 6px;
  padding-bottom: 6px;
  font-size: var(--wp-font-size, 13px);
}
:deep(.el-input__wrapper),
:deep(.el-input__inner),
:deep(.el-textarea__inner),
:deep(.el-button),
:deep(.el-alert__content),
:deep(.el-alert__title) {
  font-size: var(--wp-font-size, 13px);
}
</style>
