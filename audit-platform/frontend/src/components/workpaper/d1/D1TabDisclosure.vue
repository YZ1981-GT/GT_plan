<script setup lang="ts">
/**
 * D1TabDisclosure.vue — 附注披露（上市+国企）专属组件
 *
 * Spec: .kiro/specs/d1-disclosure-note/
 * Tasks: 6.1~6.8
 *
 * 通过 variant='listed'|'soe' 区分上市/国企版本。
 * 每个子节用 el-card 折叠卡片渲染对应 el-table。
 */
import { ref, computed, watch, inject } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import { Lock, Delete, Plus } from '@element-plus/icons-vue'
import {
  useD1Disclosure,
  DISCLOSURE_GUIDANCE,
  type DisclosureVariant,
} from '../composables/useD1Disclosure'
import {
  buildD1SyncPayload,
  D1_NOTE_SECTION,
  type D1DisclosureSnapshot,
} from '../composables/d1NoteSectionMap'
import type { ChecklistResponse } from '../composables/useD1FormData'
import type { Ref } from 'vue'
import { useAgingConfig, PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import GtIndexChip from '../GtIndexChip.vue'
import http from '@/utils/http'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant as NoteVariant } from '@/views/composables/noteDisclosureReverseJump'
import { getDisclosureNoteDetail } from '@/services/auditPlatformApi'
import { useAuditContext } from '@/composables/useAuditContext'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  variant: DisclosureVariant
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly?: boolean
}>(), { isReadonly: false })

// ─── State ───────────────────────────────────────────────────────────────────

// Note textareas per section
const sectionNotes = ref<Record<string, string>>({})
const NOTE_SECTION_KEYS = ['top', 'pledged', 'endorsed', 'badDebtClass', 'writeOff'] as const
const aiLoadingSection = ref<string>('')
const isSyncing = ref(false)
const openReviewDialog = inject<any>('openReviewDialog', null)

function loadSectionNotes() {
  const prefix = `D1-disc-${props.variant}-note-`
  const next: Record<string, string> = {}
  for (const key of NOTE_SECTION_KEYS) {
    const resp = props.allResponses.get(`${prefix}${key}`)
    if (resp?.remark) next[key] = resp.remark
  }
  sectionNotes.value = next
}

watch(() => props.allResponses, loadSectionNotes, { immediate: true, deep: true })

// ─── Persistence (debounced) ─────────────────────────────────────────────────

const router = useRouter()

/** 跳转回附注模块对应章节 */
function jumpToNote(target?: NoteVariant): void {
  const v = target || props.variant as NoteVariant
  const route = buildNoteJumpRoute(props.projectId, 'D1', v)
  if (route) router.push(route)
}

const pendingSaveItems = ref<any[]>([])

const debouncedSave = useDebounceFn(async () => {
  if (pendingSaveItems.value.length === 0) return
  const items = [...pendingSaveItems.value]
  pendingSaveItems.value = []
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
    // 保存成功后自动同步到附注（防抖/非阻塞/失败静默）
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  } catch {
    // silently fail - data is already in allResponses map
  }
}, 2000)

async function saveWithDebounce(items: any[]): Promise<void> {
  pendingSaveItems.value.push(...items)
  debouncedSave()
}

// ─── 自动同步 ─────────────────────────────────────────────────────────────────
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses) as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const projectIdRef = computed(() => props.projectId) as unknown as Ref<string>
const isReadonlyRef = computed(() => props.isReadonly) as unknown as Ref<boolean>

const {
  sectionOrder, isLoading, crossSheetData, crossSheetStatus,
  pledgedRows, pledgedTotal, addPledgedRow, removePledgedRow,
  endorsedRows, endorsedTotal, addEndorsedRow, removeEndorsedRow,
  transferRows, transferTotal, addTransferRow, removeTransferRow,
  classEndRows, classEndTotal, classPriorRows, classPriorTotal,
  individualEndRows, individualPriorRows, addIndividualRow, removeIndividualRow,
  bankPortfolioEndRows, bankPortfolioPriorRows,
  commercialPortfolioEndRows, commercialPortfolioPriorRows,
  addPortfolioRow, removePortfolioRow, fillPortfolioAgingBands,
  movementRows, movementTotal, reversalDetailRows, reversalDetailTotal,
  addReversalRow, removeReversalRow,
  writeOffAmount, writeOffDetailRows, writeOffDetailTotal,
  addWriteOffRow, removeWriteOffRow,
  categorySummaryRows, categorySummaryTotal,
  updateCell,
} = useD1Disclosure({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  variant: props.variant,
  saveImmediate: saveWithDebounce,
  isReadonly: isReadonlyRef,
})

// ─── 账龄枚举（3年段 / 5年段 / 自定义，项目账龄配置为唯一真源）────────────────
// 国企版组合计提分表行本就是账龄段（附注模板 八、4「按组合计提坏账准备的应收票据」），
// 故名称列改为按项目账龄段枚举点选（仍允许自定义出票人类型），并支持按段一键生成行。
const { segments: d1AgingSegments, preset: d1AgingPreset } = useAgingConfig(projectIdRef, 'D1')
const agingBandLabels = computed<string[]>(() => {
  const list = d1AgingSegments.value
  if (Array.isArray(list) && list.length > 0) return list.map((seg) => seg.label)
  return PRESET_SEGMENTS.FIVE_YEAR.map((seg) => seg.label)
})
const AGING_PRESET_LABEL: Record<string, string> = {
  THREE_YEAR: '3 年段',
  FIVE_YEAR: '5 年段',
  CUSTOM: '自定义',
}
const agingPresetLabel = computed(() => AGING_PRESET_LABEL[d1AgingPreset.value] ?? '5 年段')

function onFillAgingBands(type: 'bank' | 'commercial'): void {
  const added = fillPortfolioAgingBands(type, 'end', agingBandLabels.value)
  if (added > 0) ElMessage.success(`已按账龄段补齐 ${added} 行`)
  else ElMessage.info('账龄段已齐备，无需新增')
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmt(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span style="color:#f56c6c">(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })})</span>`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

function fmtPct(val: number): string {
  return (val * 100).toFixed(2) + '%'
}

type BadDebtDisplayRow = {
  rowKind: 'fixed' | 'hint' | 'individual' | 'summary'
  rowId: string
  label: string
  source?: 'single' | 'bank' | 'commercial'
  balance: number
  ratio: number
  provision: number
  lossRate: number
  bookValue: number
  basis?: string
}

function ratioOf(numerator: number, denominator: number): number {
  if (!denominator) return 0
  return numerator / denominator
}

function buildBadDebtRows(period: 'end' | 'prior'): BadDebtDisplayRow[] {
  const classRows = period === 'end' ? classEndRows.value : classPriorRows.value
  const total = period === 'end' ? classEndTotal.value : classPriorTotal.value
  const individuals = period === 'end' ? individualEndRows.value : individualPriorRows.value
  const single = classRows.find(r => r.rowId === `class-${period}-individual`)
  const bank = classRows.find(r => r.rowId === `class-${period}-portfolio-bank`)
  const commercial = classRows.find(r => r.rowId === `class-${period}-portfolio-commercial`)
  const comboBalance = (bank?.balance || 0) + (commercial?.balance || 0)
  const comboProvision = (bank?.provision || 0) + (commercial?.provision || 0)
  const comboBookValue = comboBalance - comboProvision
  const comboRatio = ratioOf(comboBalance, total.balance)
  const comboLossRate = ratioOf(comboProvision, comboBalance)

  return [
    {
      rowKind: 'fixed',
      rowId: `single-${period}`,
      label: '按单项计提坏账准备',
      source: 'single',
      balance: single?.balance || 0,
      ratio: single?.ratio || 0,
      provision: single?.provision || 0,
      lossRate: single?.lossRate || 0,
      bookValue: single?.bookValue || 0,
    },
    { rowKind: 'hint', rowId: `single-hint-${period}`, label: '其中：', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
    ...individuals.map(row => ({
      rowKind: 'individual' as const,
      rowId: row.rowId,
      label: row.name || '',
      balance: row.balance,
      ratio: ratioOf(row.balance, total.balance),
      provision: row.provision,
      lossRate: row.lossRate,
      bookValue: row.balance - row.provision,
      basis: row.basis,
    })),
    {
      rowKind: 'fixed',
      rowId: `combo-${period}`,
      label: '按组合计提坏账准备',
      balance: comboBalance,
      ratio: comboRatio,
      provision: comboProvision,
      lossRate: comboLossRate,
      bookValue: comboBookValue,
    },
    { rowKind: 'hint', rowId: `combo-hint-${period}`, label: '其中：', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
    {
      rowKind: 'fixed',
      rowId: `bank-${period}`,
      label: '银行承兑汇票',
      source: 'bank',
      balance: bank?.balance || 0,
      ratio: bank?.ratio || 0,
      provision: bank?.provision || 0,
      lossRate: bank?.lossRate || 0,
      bookValue: bank?.bookValue || 0,
    },
    {
      rowKind: 'fixed',
      rowId: `commercial-${period}`,
      label: '商业承兑汇票',
      source: 'commercial',
      balance: commercial?.balance || 0,
      ratio: commercial?.ratio || 0,
      provision: commercial?.provision || 0,
      lossRate: commercial?.lossRate || 0,
      bookValue: commercial?.bookValue || 0,
    },
    {
      rowKind: 'summary',
      rowId: `total-${period}`,
      label: '合计',
      balance: total.balance,
      ratio: total.ratio,
      provision: total.provision,
      lossRate: total.lossRate,
      bookValue: total.bookValue,
    },
  ]
}

const badDebtEndRowsForDisplay = computed(() => buildBadDebtRows('end'))
const badDebtPriorRowsForDisplay = computed(() => buildBadDebtRows('prior'))
const listedMovementRow = computed(() => movementRows.value[0] ?? {
  rowId: 'mv-total',
  priorBalance: 0,
  provision: 0,
  reversal: 0,
  writeOff: 0,
  transfer: 0,
  other: 0,
  endBalance: 0,
})
const soeClassEndRows = computed(() => {
  const single = classEndRows.value.find(r => r.rowId === 'class-end-individual')
  const bank = classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')
  const commercial = classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')
  return [
    { rowId: 'soe-end-single', label: '按单项计提坏账准备', balance: single?.balance || 0, ratio: single?.ratio || 0, provision: single?.provision || 0, lossRate: single?.lossRate || 0, bookValue: single?.bookValue || 0 },
    { rowId: 'soe-end-portfolio', label: '按组合计提坏账准备', balance: (bank?.balance || 0) + (commercial?.balance || 0), ratio: (bank?.ratio || 0) + (commercial?.ratio || 0), provision: (bank?.provision || 0) + (commercial?.provision || 0), lossRate: 0, bookValue: (bank?.bookValue || 0) + (commercial?.bookValue || 0) },
    { rowId: 'soe-end-total', label: '合计', balance: classEndTotal.value.balance, ratio: classEndTotal.value.ratio, provision: classEndTotal.value.provision, lossRate: classEndTotal.value.lossRate, bookValue: classEndTotal.value.bookValue },
  ]
})
const soeClassPriorRows = computed(() => {
  const single = classPriorRows.value.find(r => r.rowId === 'class-prior-individual')
  const bank = classPriorRows.value.find(r => r.rowId === 'class-prior-portfolio-bank')
  const commercial = classPriorRows.value.find(r => r.rowId === 'class-prior-portfolio-commercial')
  return [
    { rowId: 'soe-prior-single', label: '按单项计提坏账准备', balance: single?.balance || 0, ratio: single?.ratio || 0, provision: single?.provision || 0, lossRate: single?.lossRate || 0, bookValue: single?.bookValue || 0 },
    { rowId: 'soe-prior-portfolio', label: '按组合计提坏账准备', balance: (bank?.balance || 0) + (commercial?.balance || 0), ratio: (bank?.ratio || 0) + (commercial?.ratio || 0), provision: (bank?.provision || 0) + (commercial?.provision || 0), lossRate: 0, bookValue: (bank?.bookValue || 0) + (commercial?.bookValue || 0) },
    { rowId: 'soe-prior-total', label: '合计', balance: classPriorTotal.value.balance, ratio: classPriorTotal.value.ratio, provision: classPriorTotal.value.provision, lossRate: classPriorTotal.value.lossRate, bookValue: classPriorTotal.value.bookValue },
  ]
})
const soeAgingRows = computed(() => {
  const commercial = commercialPortfolioEndRows.value.map(r => ({ ...r, sourceType: 'commercial' as const }))
  const bank = bankPortfolioEndRows.value.map(r => ({ ...r, sourceType: 'bank' as const }))
  const hasCommercialDetail = commercial.length > 0
  const hasBankDetail = bank.length > 0
  const commercialBalance = commercial.reduce((s, r) => s + (r.balance || 0), 0)
  const commercialProvision = commercial.reduce((s, r) => s + (r.provision || 0), 0)
  const bankBalance = bank.reduce((s, r) => s + (r.balance || 0), 0)
  const bankProvision = bank.reduce((s, r) => s + (r.provision || 0), 0)
  return [
    { rowKind: 'subtotal', rowId: 'soe-commercial-subtotal', sourceType: 'commercial' as const, hasDetail: hasCommercialDetail, name: '商业承兑汇票', balance: hasCommercialDetail ? commercialBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')?.balance || 0), provision: hasCommercialDetail ? commercialProvision : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')?.provision || 0), lossRate: (hasCommercialDetail ? commercialBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')?.balance || 0)) ? (hasCommercialDetail ? commercialProvision : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')?.provision || 0)) / (hasCommercialDetail ? commercialBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')?.balance || 0)) : 0 },
    ...commercial.map(r => ({ rowKind: 'detail', rowId: r.rowId, sourceType: r.sourceType, name: r.drawerTypeOrAging || '', balance: r.balance || 0, provision: r.provision || 0, lossRate: r.lossRate || 0 })),
    { rowKind: 'subtotal', rowId: 'soe-bank-subtotal', sourceType: 'bank' as const, hasDetail: hasBankDetail, name: '银行承兑汇票', balance: hasBankDetail ? bankBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')?.balance || 0), provision: hasBankDetail ? bankProvision : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')?.provision || 0), lossRate: (hasBankDetail ? bankBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')?.balance || 0)) ? (hasBankDetail ? bankProvision : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')?.provision || 0)) / (hasBankDetail ? bankBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')?.balance || 0)) : 0 },
    ...bank.map(r => ({ rowKind: 'detail', rowId: r.rowId, sourceType: r.sourceType, name: r.drawerTypeOrAging || '', balance: r.balance || 0, provision: r.provision || 0, lossRate: r.lossRate || 0 })),
    { rowKind: 'summary', rowId: 'soe-aging-total', sourceType: 'commercial' as const, name: '合计', balance: (hasCommercialDetail ? commercialBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')?.balance || 0)) + (hasBankDetail ? bankBalance : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')?.balance || 0)), provision: (hasCommercialDetail ? commercialProvision : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')?.provision || 0)) + (hasBankDetail ? bankProvision : (classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')?.provision || 0)), lossRate: 0 },
  ]
})
const soeMovementRowsForDisplay = computed(() => {
  const individual = movementRows.value.find(r => r.label === '按单项计提') || movementRows.value[0]
  const portfolio = movementRows.value.find(r => r.label === '按组合计提') || movementRows.value[1]
  const total = movementRows.value.find(r => r.label === '合计') || movementTotal.value
  return [
    { rowKind: 'data', rowId: individual?.rowId || 'mv-individual', label: '单项计提预期信用损失的应收票据', sourceRow: individual },
    { rowKind: 'data', rowId: portfolio?.rowId || 'mv-portfolio', label: '按组合计提预期信用损失的应收票据', sourceRow: portfolio },
    { rowKind: 'hint', rowId: 'mv-hint', label: '其中：', sourceRow: null },
    { rowKind: 'summary', rowId: total?.rowId || 'mv-total', label: '合计', sourceRow: total },
  ]
})

function updateBadDebtClassFixed(period: 'end' | 'prior', source: 'single' | 'bank' | 'commercial', field: 'balance' | 'provision', value: number) {
  const rowId = source === 'single'
    ? `class-${period}-individual`
    : source === 'bank'
      ? `class-${period}-portfolio-bank`
      : `class-${period}-portfolio-commercial`
  updateCell(period === 'end' ? 'classEnd' : 'classPrior', rowId, field, value)
}

// ─── Section Labels ──────────────────────────────────────────────────────────

const sectionLabels = computed<Record<string, string>>(() => {
  if (props.variant === 'soe') {
    return {
      categorySummary: '（1）应收票据分类',
      badDebtClass: '（2）按坏账准备计提方法分类披露',
      badDebtMovement: '（3）本期计提、收回或转回的应收票据坏账准备情况',
      pledged: '（4）期末已质押的应收票据',
      endorsed: '（5）期末已背书或贴现且在资产负债表日尚未到期的应收票据',
      transfer: '（6）期末因出票人未履约而将其转应收账款的票据',
      writeOff: '（7）本期实际核销的应收票据',
    }
  }
  return {
    pledged: '（1）期末已质押的应收票据',
    endorsed: '（2）期末已背书或贴现且未到期的应收票据',
    transfer: '（3）期末因出票人未履约而转为应收账款的票据',
    badDebtClass: '（4）按坏账准备计提方法分类披露',
    badDebtMovement: '（5）本期计提、收回或转回的坏账准备情况',
    writeOff: '（6）本期实际核销的应收票据情况',
    categorySummary: '（1）应收票据按票据种类分类',
  }
})

// ─── Import/Export (Task 10.2) ────────────────────────────────────────────────

async function exportTemplate() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/disclosure/export-template`,
      null,
      { params: { variant: props.variant }, responseType: 'blob' }
    )
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `D1-附注披露-${props.variant === 'listed' ? '上市' : '国企'}-模板.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function exportData() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/disclosure/export-data`,
      null,
      { params: { variant: props.variant }, responseType: 'blob' }
    )
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `D1-附注披露-${props.variant === 'listed' ? '上市' : '国企'}-数据.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

async function handleImportFile(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/disclosure/import-data`,
      formData,
      { params: { variant: props.variant }, headers: { 'Content-Type': 'multipart/form-data' } }
    )
    const data = res.data?.data ?? res.data
    if (data?.invalid_columns?.length) {
      ElMessage.error(`列名不匹配: ${data.invalid_columns.join(', ')}`)
    } else {
      ElMessage.success(`导入成功: ${data?.rowCount ?? 0}行`)
    }
  } catch { ElMessage.error('导入失败') }
}

function onNoteChange(sectionKey: string, value: string) {
  sectionNotes.value[sectionKey] = value
  updateCell(`D1-disc-${props.variant}-note-${sectionKey}`, '', 'note', value)
}

function buildAiContext(sectionKey: string): string {
  const lines: string[] = [
    `工作底稿: D1 应收票据附注披露（${props.variant === 'listed' ? '上市公司版' : '国企版'}）`,
    `子节: ${sectionLabels.value[sectionKey] ?? sectionKey}`,
    `当前说明: ${sectionNotes.value[sectionKey] || '（空）'}`,
  ]

  if (sectionKey === 'top') {
    for (const row of [...categorySummaryRows.value, categorySummaryTotal.value]) {
      lines.push(`${row.category}: 期末余额=${row.endBalance}, 期末坏账=${row.endProvision}, 上年年末余额=${row.priorBalance}, 上年年末坏账=${row.priorProvision}`)
    }
  } else if (sectionKey === 'pledged') {
    for (const row of [...pledgedRows.value, pledgedTotal.value]) {
      lines.push(`${row.category}: 已质押金额=${row.pledgedAmount}`)
    }
  } else if (sectionKey === 'endorsed') {
    for (const row of [...endorsedRows.value, endorsedTotal.value]) {
      lines.push(`${row.category}: 终止确认=${row.derecognizedAmount}, 未终止确认=${row.notDerecognizedAmount}`)
    }
  } else if (sectionKey === 'badDebtClass') {
    lines.push(`期末按方法分类合计: 账面余额=${classEndTotal.value.balance}, 坏账准备=${classEndTotal.value.provision}, 账面价值=${classEndTotal.value.bookValue}`)
    lines.push(`上年按方法分类合计: 账面余额=${classPriorTotal.value.balance}, 坏账准备=${classPriorTotal.value.provision}, 账面价值=${classPriorTotal.value.bookValue}`)
  } else if (sectionKey === 'writeOff') {
    lines.push(`本期核销总额=${writeOffAmount.value}`)
    lines.push(`重要核销明细条数=${writeOffDetailRows.value.length}`)
    lines.push(`重要核销明细金额合计=${writeOffDetailTotal.value.amount}`)
  }

  return lines.join('\n')
}

async function handleAiGenerate(sectionKey: string): Promise<void> {
  if (props.isReadonly) return
  aiLoadingSection.value = sectionKey
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/review-dialog/ai-generate`, {
      section: `d1-disclosure-${sectionKey}`,
      context: buildAiContext(sectionKey),
    })
    const text = res?.data?.text ?? res?.text ?? ''
    if (!text) {
      ElMessage.warning('AI未返回内容，请重试')
      return
    }
    onNoteChange(sectionKey, text)
    ElMessage.success('AI已生成说明')
  } catch {
    ElMessage.warning('AI生成失败，请重试')
  } finally {
    aiLoadingSection.value = ''
  }
}

function handleReview(sectionKey: string): void {
  if (!openReviewDialog) return
  openReviewDialog({
    sectionId: `D1-disc-${props.variant}-note-${sectionKey}`,
    sectionLabel: sectionLabels.value[sectionKey] ?? sectionKey,
    relatedData: {
      variant: props.variant,
      note: sectionNotes.value[sectionKey] || '',
    },
  })
}

// ─── 同步到附注模块（底稿披露表 → 附注单向推送）─────────────────────────────────
// 结构化表格 + 文本框（说明）内容一并同步到附注 五、4/八、4「应收票据」，
// 保证附注模块表格与文本与披露表保持一致。

const { year: auditYear } = useAuditContext()

// ─── 校对附注一致性（只读比对，不改附注）───────────────────────────────────────────
const noteCheckState = ref<{ status: 'idle' | 'loading' | 'ok' | 'diff' | 'missing' | 'error'; message: string }>({
  status: 'idle',
  message: '',
})

function pickNoteTotal(detail: any): number | null {
  const td = detail?.table_data
  const tables: any[] = Array.isArray(td?._tables) ? td._tables : []
  const candidates = tables.length > 0
    ? tables
    : (Array.isArray(td?.rows) ? [{ rows: td.rows }] : [])
  for (const t of candidates) {
    const rows: any[] = Array.isArray(t?.rows) ? t.rows : []
    const totalRow = rows.find((r: any) => r?.is_total || String(r?.label ?? '').trim() === '合计')
    if (!totalRow) continue
    const values: any[] = Array.isArray(totalRow.values) ? totalRow.values : []
    for (const v of values) {
      const n = Number(v)
      if (Number.isFinite(n) && n !== 0) return n
    }
  }
  return null
}

async function checkNoteConsistency(silent = false): Promise<void> {
  if (!props.projectId) return
  noteCheckState.value = { status: 'loading', message: '正在读取附注现存数据…' }
  try {
    const detail = await getDisclosureNoteDetail(props.projectId, auditYear.value, D1_NOTE_SECTION[props.variant])
    const noteTotal = pickNoteTotal(detail)
    const pageTotal = categorySummaryTotal.value?.endBalance ?? 0
    if (noteTotal === null) {
      noteCheckState.value = {
        status: 'missing',
        message: `附注「${D1_NOTE_SECTION[props.variant]}」暂无可比对的合计行（尚未同步或附注为空）`,
      }
    } else if (Math.abs(noteTotal - pageTotal) <= 0.01) {
      noteCheckState.value = {
        status: 'ok',
        message: `附注现存期末合计与本页一致`,
      }
    } else {
      noteCheckState.value = {
        status: 'diff',
        message: `附注现存合计 ${noteTotal} 与本页期末合计 ${pageTotal} 不一致（差异 ${(noteTotal - pageTotal).toFixed(2)}）`,
      }
    }
    if (!silent) {
      if (noteCheckState.value.status === 'ok') ElMessage.success(noteCheckState.value.message)
      else ElMessage.warning(noteCheckState.value.message)
    }
  } catch {
    noteCheckState.value = { status: 'error', message: '读取附注数据失败（附注可能尚未生成）' }
    if (!silent) ElMessage.warning(noteCheckState.value.message)
  }
}

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  try {
    const snapshot: D1DisclosureSnapshot = {
      summaryRows: categorySummaryRows.value as any,
      summaryTotal: categorySummaryTotal.value as any,
      pledgedRows: pledgedRows.value as any,
      pledgedTotal: pledgedTotal.value as any,
      endorsedRows: endorsedRows.value as any,
      endorsedTotal: endorsedTotal.value as any,
      transferRows: transferRows.value as any,
      transferTotal: transferTotal.value as any,
      classEndRows: classEndRows.value as any,
      classPriorRows: classPriorRows.value as any,
      // 披露表实际渲染的分类展开行（上市版含「其中：」与单项明细行，与附注模板行结构一致）
      classDisplayEndRows: badDebtEndRowsForDisplay.value as any,
      classDisplayPriorRows: badDebtPriorRowsForDisplay.value as any,
      soeClassEndRows: soeClassEndRows.value as any,
      soeClassPriorRows: soeClassPriorRows.value as any,
      individualEndRows: individualEndRows.value as any,
      individualPriorRows: individualPriorRows.value as any,
      bankPortfolioEndRows: bankPortfolioEndRows.value as any,
      bankPortfolioPriorRows: bankPortfolioPriorRows.value as any,
      commercialPortfolioEndRows: commercialPortfolioEndRows.value as any,
      commercialPortfolioPriorRows: commercialPortfolioPriorRows.value as any,
      soePortfolioRows: soeAgingRows.value.map((r: any) => ({
        name: r.name,
        balance: r.balance,
        provision: r.provision,
        lossRate: r.lossRate,
        isTotal: r.rowKind === 'summary',
      })),
      movementTotal: (props.variant === 'listed' ? listedMovementRow.value : movementTotal.value) as any,
      soeMovementRows: soeMovementRowsForDisplay.value.map((r: any) => ({
        label: r.label,
        priorBalance: r.sourceRow?.priorBalance ?? 0,
        provision: r.sourceRow?.provision ?? 0,
        reversal: r.sourceRow?.reversal ?? 0,
        writeOff: r.sourceRow?.writeOff ?? 0,
        transfer: r.sourceRow?.transfer ?? 0,
        other: r.sourceRow?.other ?? 0,
        endBalance: r.sourceRow?.endBalance ?? 0,
      })),
      reversalRows: reversalDetailRows.value as any,
      reversalTotal: reversalDetailTotal.value as any,
      writeOffAmount: writeOffAmount.value,
      writeOffDetailRows: writeOffDetailRows.value as any,
      notes: { ...sectionNotes.value },
    }
    const payload = buildD1SyncPayload(props.variant, props.wpId || '', null, snapshot)
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    // 通知附注模块定向刷新（表格 + 文本框内容与披露表一致）
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'D1',
        accountCode: '1121',
        projectId: props.projectId,
        section: props.variant,
        sectionIds: [D1_NOTE_SECTION[props.variant]],
      },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D1_NOTE_SECTION[props.variant]} 应收票据」`)
    await checkNoteConsistency(true)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}
</script>

<template>
  <div class="d1-disclosure">
    <!-- Header: variant tag + mode switch + toolbar -->
    <div class="d1-disclosure__header">
      <el-tag :type="variant === 'listed' ? 'primary' : 'success'" effect="plain">
        {{ variant === 'listed' ? '上市公司版' : '国企版' }}
      </el-tag>
      <GtIndexChip value="附注全文" :context-project-id="projectId" />
      <div class="d1-disclosure__toolbar">
        <el-button-group size="small">
          <el-button @click="exportTemplate">导出模板</el-button>
          <el-button @click="exportData">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx"
            :auto-upload="false"
            :on-change="(f: any) => handleImportFile(f.raw)"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
        <el-button
          type="primary"
          plain
          size="small"
          :loading="isSyncing"
          :disabled="isReadonly"
          title="将披露表的表格与文本框内容同步到附注模块（五、4/八、4 应收票据）"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-dropdown split-button size="small" type="primary" plain @click="jumpToNote()" title="跳转回附注模块查看">
          ↩ 跳转回附注（{{ D1_NOTE_SECTION[variant] }}）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="jumpToNote('listed')">上市版（五、4）</el-dropdown-item>
              <el-dropdown-item @click="jumpToNote('soe')">国企版（八、4）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="checkNoteConsistency(false)" title="只读校对本页合计与附注合计是否一致">校对附注</el-button>
      </div>
    </div>

    <!-- 附注校对结果 -->
    <el-alert
      v-if="noteCheckState.status === 'ok' || noteCheckState.status === 'diff' || noteCheckState.status === 'missing'"
      :type="noteCheckState.status === 'ok' ? 'success' : (noteCheckState.status === 'diff' ? 'warning' : 'info')"
      show-icon
      :closable="true"
      style="margin: 0 12px 8px"
      :title="noteCheckState.message"
    />

    <el-skeleton v-if="isLoading" :rows="10" animated />
    <template v-else>
        <!-- 注：listed 版编制提示已内联在下方汇总表卡片的「说明」区（listed-top-note），
             此处不再重复渲染，避免同一「📋 编制提示」出现两次。 -->

        <!-- Listed top summary table (Req 11 — Excel R6-11) -->
        <el-card v-if="variant === 'listed'" class="d1-section-card listed-top-summary" shadow="never">
          <template #header>
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-weight:600">应收票据</span>
              <GtIndexChip value="D1-1" :context-project-id="projectId" />
              <el-tag v-if="crossSheetStatus === 'empty'" type="warning" size="small" effect="plain">审定表D1-1数据未加载</el-tag>
            </div>
          </template>

          <el-table
            :data="[...categorySummaryRows, categorySummaryTotal]"
            border
            size="small"
            style="width:100%"
            :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35', textAlign: 'center' }"
            :cell-style="{ padding: '3px 6px' }"
          >
            <el-table-column label="票据种类" min-width="130" fixed>
              <template #default="{ row }">
                <span :style="row.rowType === 'summary' ? 'font-weight:600' : ''">{{ row.category }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末余额" align="center">
              <el-table-column label="账面余额" min-width="100" align="right">
                <template #default="{ row }">
                  <el-tooltip v-if="row.isFixed" content="取自审定表D1-1" placement="top">
                    <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.endBalance)" />
                  </el-tooltip>
                  <span v-else class="amount-cell" v-html="fmtAmt(row.endBalance)" />
                </template>
              </el-table-column>
              <el-table-column label="坏账准备" min-width="100" align="right">
                <template #default="{ row }">
                  <el-tooltip v-if="row.isFixed" content="取自审定表D1-1" placement="top">
                    <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.endProvision)" />
                  </el-tooltip>
                  <span v-else class="amount-cell" v-html="fmtAmt(row.endProvision)" />
                </template>
              </el-table-column>
              <el-table-column label="账面价值" min-width="100" align="right">
                <template #default="{ row }">
                  <span class="amount-cell" v-html="fmtAmt(row.endBookValue)" />
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="上年年末余额" align="center">
              <el-table-column label="账面余额" min-width="100" align="right">
                <template #default="{ row }">
                  <el-tooltip v-if="row.isFixed" content="取自审定表D1-1" placement="top">
                    <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.priorBalance)" />
                  </el-tooltip>
                  <span v-else class="amount-cell" v-html="fmtAmt(row.priorBalance)" />
                </template>
              </el-table-column>
              <el-table-column label="坏账准备" min-width="100" align="right">
                <template #default="{ row }">
                  <el-tooltip v-if="row.isFixed" content="取自审定表D1-1" placement="top">
                    <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.priorProvision)" />
                  </el-tooltip>
                  <span v-else class="amount-cell" v-html="fmtAmt(row.priorProvision)" />
                </template>
              </el-table-column>
              <el-table-column label="账面价值" min-width="100" align="right">
                <template #default="{ row }">
                  <span class="amount-cell" v-html="fmtAmt(row.priorBookValue)" />
                </template>
              </el-table-column>
            </el-table-column>
          </el-table>

          <div class="section-note listed-top-note">
            <label>说明：</label>
            <details class="guidance-fold listed-guidance-fold">
              <summary>📋 编制提示</summary>
              <p v-for="(t, i) in DISCLOSURE_GUIDANCE.top" :key="'listed-top-tip-'+i">{{ t }}</p>
            </details>
            <el-input
              type="textarea"
              :rows="3"
              :model-value="sectionNotes['top'] || ''"
              placeholder="请输入应收票据相关说明..."
              :disabled="isReadonly"
              @input="(v: string) => onNoteChange('top', v)"
            />
            <div class="note-actions">
              <el-button size="small" :loading="aiLoadingSection === 'top'" :disabled="isReadonly" @click="handleAiGenerate('top')">🤖 AI</el-button>
              <el-button v-if="openReviewDialog" size="small" @click="handleReview('top')">💬 复核</el-button>
            </div>
          </div>
        </el-card>

        <!-- Sections rendered by sectionOrder -->
        <el-card
          v-for="section in sectionOrder"
          :key="section"
          class="d1-section-card"
          shadow="never"
        >
          <template #header>
            <div style="display:flex;align-items:center;justify-content:space-between">
              <span style="font-weight:600">{{ sectionLabels[section] }}</span>
              <div style="display:flex;align-items:center;gap:8px">
                <GtIndexChip v-if="section === 'badDebtClass' || section === 'badDebtMovement'" value="D1-4" :context-project-id="projectId" />
              </div>
            </div>
          </template>

          <div>

            <!-- ═══ 6.2 Pledged Section ═══ -->
            <template v-if="section === 'pledged'">
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addPledgedRow" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="[...pledgedRows, pledgedTotal]" border size="small" style="width:100%">
                <el-table-column label="票据种类" min-width="200">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b>{{ row.category }}</b></template>
                    <template v-else-if="row.isFixed">
                      <el-icon :size="12" style="margin-right:4px"><Lock /></el-icon>{{ row.category }}
                    </template>
                    <template v-else>
                      <el-input v-model="row.category" size="small" :disabled="isReadonly" @change="updateCell('pledged', row.rowId, 'category', row.category)" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="期末已质押金额" min-width="180" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.pledgedAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.pledgedAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('pledged', row.rowId, 'pledgedAmount', row.pledgedAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowType === 'dynamic'" :icon="Delete" text type="danger" size="small" @click="removePledgedRow(row.rowId)" />
                  </template>
                </el-table-column>
              </el-table>
              <!-- Note textarea for pledged -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['pledged'] || ''" placeholder="请输入质押票据相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('pledged', v)" />
                <div class="note-actions">
                  <el-button size="small" :loading="aiLoadingSection === 'pledged'" :disabled="isReadonly" @click="handleAiGenerate('pledged')">🤖 AI</el-button>
                  <el-button v-if="openReviewDialog" size="small" @click="handleReview('pledged')">💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.3 Endorsed Section ═══ -->
            <template v-if="section === 'endorsed'">
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addEndorsedRow" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="[...endorsedRows, endorsedTotal]" border size="small" style="width:100%">
                <el-table-column label="票据种类" min-width="200">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b>{{ row.category }}</b></template>
                    <template v-else-if="row.isFixed">
                      <el-icon :size="12" style="margin-right:4px"><Lock /></el-icon>{{ row.category }}
                    </template>
                    <template v-else>
                      <el-input v-model="row.category" size="small" :disabled="isReadonly" @change="updateCell('endorsed', row.rowId, 'category', row.category)" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column :label="variant === 'soe' ? '期末终止确认金额' : '终止确认金额'" min-width="160" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.derecognizedAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.derecognizedAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('endorsed', row.rowId, 'derecognizedAmount', row.derecognizedAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column :label="variant === 'soe' ? '期末未终止确认金额' : '未终止确认金额'" min-width="160" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.notDerecognizedAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.notDerecognizedAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('endorsed', row.rowId, 'notDerecognizedAmount', row.notDerecognizedAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowType === 'dynamic'" :icon="Delete" text type="danger" size="small" @click="removeEndorsedRow(row.rowId)" />
                  </template>
                </el-table-column>
              </el-table>
              <details class="guidance-fold">
                <summary>📋 编制提示</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.endorsed" :key="'endorsed-tip-'+i">{{ t }}</p>
              </details>
              <!-- Note textarea for endorsed -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['endorsed'] || ''" placeholder="请输入背书贴现相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('endorsed', v)" />
                <div class="note-actions">
                  <el-button size="small" :loading="aiLoadingSection === 'endorsed'" :disabled="isReadonly" @click="handleAiGenerate('endorsed')">🤖 AI</el-button>
                  <el-button v-if="openReviewDialog" size="small" @click="handleReview('endorsed')">💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.4 Transfer Section ═══ -->
            <template v-if="section === 'transfer'">
              <div :class="variant === 'soe' ? 'table-frame' : ''">
              <el-table :data="[...transferRows, transferTotal]" border size="small" style="width:100%">
                <el-table-column :label="variant === 'soe' ? '种类' : '票据种类'" min-width="200">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b>{{ row.category }}</b></template>
                    <template v-else-if="row.isFixed">
                      <el-icon :size="12" style="margin-right:4px"><Lock /></el-icon>{{ row.category }}
                    </template>
                    <template v-else>
                      <el-input v-model="row.category" size="small" :disabled="isReadonly" @change="updateCell('transfer', row.rowId, 'category', row.category)" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column :label="variant === 'soe' ? '期末转应收账款金额' : '转应收账款金额'" min-width="180" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.transferAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.transferAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('transfer', row.rowId, 'transferAmount', row.transferAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column v-if="variant === 'soe' && !isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowType === 'dynamic'" :icon="Delete" text type="danger" size="small" @click="removeTransferRow(row.rowId)" />
                  </template>
                </el-table-column>
              </el-table>
              <div v-if="variant === 'soe' && !isReadonly" style="margin-top:8px">
                <el-button size="small" :icon="Plus" @click="addTransferRow">添加行</el-button>
              </div>
              <details v-if="variant === 'listed'" class="guidance-fold">
                <summary>📋 编制提示</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.transferIntro" :key="'transfer-intro-'+i">{{ t }}</p>
              </details>
              </div>
            </template>

            <!-- ═══ 6.5 Bad Debt Classification (most complex) ═══ -->
            <template v-if="section === 'badDebtClass'">
              <details v-if="variant === 'listed'" class="guidance-fold">
                <summary>📋 编制提示</summary>
                <p>提示：此处披露未逾期应收票据计提的坏账准备。若票据逾期，则应转入应收账款并计提坏账准备，账龄应连续计算。</p>
              </details>
              <template v-if="variant === 'soe'">
                <div class="excel-hint">按坏账准备计提方法分类披露应收票据</div>
                <el-table :data="soeClassEndRows" border size="small" style="width:100%;margin-bottom:12px">
                  <el-table-column label="类别" min-width="200">
                    <template #default="{ row }"><span :style="row.label==='合计' ? 'font-weight:600' : ''">{{ row.label }}</span></template>
                  </el-table-column>
                  <el-table-column label="期末数" align="center">
                    <el-table-column label="账面余额" align="center">
                      <el-table-column label="金额" min-width="130" align="right"><template #default="{ row }"><span v-html="fmtAmt(row.balance)" /></template></el-table-column>
                      <el-table-column label="比例(%)" min-width="90" align="right"><template #default="{ row }">{{ fmtPct(row.ratio) }}</template></el-table-column>
                    </el-table-column>
                    <el-table-column label="坏账准备" align="center">
                      <el-table-column label="金额" min-width="130" align="right"><template #default="{ row }"><span v-html="fmtAmt(row.provision)" /></template></el-table-column>
                      <el-table-column label="预期信用损失率(%)" min-width="120" align="right"><template #default="{ row }">{{ fmtPct(row.lossRate) }}</template></el-table-column>
                    </el-table-column>
                    <el-table-column label="账面价值" min-width="130" align="right"><template #default="{ row }"><span v-html="fmtAmt(row.bookValue)" /></template></el-table-column>
                  </el-table-column>
                </el-table>

                <div class="excel-hint">按坏账准备计提方法分类披露应收票据（续）</div>
                <el-table :data="soeClassPriorRows" border size="small" style="width:100%;margin-bottom:12px">
                  <el-table-column label="类别" min-width="200">
                    <template #default="{ row }"><span :style="row.label==='合计' ? 'font-weight:600' : ''">{{ row.label }}</span></template>
                  </el-table-column>
                  <el-table-column label="期初数" align="center">
                    <el-table-column label="账面余额" align="center">
                      <el-table-column label="金额" min-width="130" align="right"><template #default="{ row }"><span v-html="fmtAmt(row.balance)" /></template></el-table-column>
                      <el-table-column label="比例(%)" min-width="90" align="right"><template #default="{ row }">{{ fmtPct(row.ratio) }}</template></el-table-column>
                    </el-table-column>
                    <el-table-column label="坏账准备" align="center">
                      <el-table-column label="金额" min-width="130" align="right"><template #default="{ row }"><span v-html="fmtAmt(row.provision)" /></template></el-table-column>
                      <el-table-column label="预期信用损失率(%)" min-width="120" align="right"><template #default="{ row }">{{ fmtPct(row.lossRate) }}</template></el-table-column>
                    </el-table-column>
                    <el-table-column label="账面价值" min-width="130" align="right"><template #default="{ row }"><span v-html="fmtAmt(row.bookValue)" /></template></el-table-column>
                  </el-table-column>
                </el-table>

                <div class="excel-hint">按单项计提坏账准备的应收票据：</div>
                <div class="table-frame">
                  <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addIndividualRow('end')" style="margin-bottom:8px">添加行</el-button>
                  <el-table :data="[...individualEndRows, { rowId: '__soe_ind_total__', rowType: 'summary', name: '合计', balance: individualEndRows.reduce((s, r) => s + (r.balance || 0), 0), provision: individualEndRows.reduce((s, r) => s + (r.provision || 0), 0), lossRate: 0, basis: '' }]" row-key="rowId" border size="small" style="width:100%;margin-bottom:12px">
                    <el-table-column label="名称" min-width="170">
                      <template #default="{ row }">
                        <template v-if="row.rowType==='summary'"><b>{{ row.name }}</b></template>
                        <template v-else><el-input :model-value="row.name" size="small" :disabled="isReadonly" @input="(v: string)=>updateCell('individualEnd', row.rowId, 'name', v)" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="账面余额" min-width="120" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.balance)" /></template>
                        <template v-else><el-input-number :model-value="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell('individualEnd', row.rowId, 'balance', Number(v ?? 0))" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="坏账准备" min-width="120" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.provision)" /></template>
                        <template v-else><el-input-number :model-value="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell('individualEnd', row.rowId, 'provision', Number(v ?? 0))" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="预期信用损失率(%)" min-width="120" align="right"><template #default="{ row }">{{ fmtPct(row.lossRate || 0) }}</template></el-table-column>
                    <el-table-column label="计提理由" min-width="160">
                      <template #default="{ row }">
                        <template v-if="row.rowType!=='summary'"><el-input :model-value="row.basis || ''" size="small" :disabled="isReadonly" @input="(v:string)=>updateCell('individualEnd', row.rowId, 'basis', v)" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="!isReadonly" label="" width="50" align="center"><template #default="{ row }"><el-button v-if="row.rowType!=='summary'" :icon="Delete" text type="danger" size="small" @click="removeIndividualRow(row.rowId, 'end')" /></template></el-table-column>
                  </el-table>
                </div>

                <div class="excel-hint">按账龄组合计提坏账准备的应收票据：</div>
                <div class="table-frame">
                  <div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap" v-if="!isReadonly">
                    <el-button size="small" :icon="Plus" @click="addPortfolioRow('commercial', 'end')">在商业承兑汇票下添加行</el-button>
                    <el-button size="small" :icon="Plus" @click="addPortfolioRow('bank', 'end')">在银行承兑汇票下添加行</el-button>
                    <el-divider direction="vertical" />
                    <el-button size="small" type="primary" plain @click="onFillAgingBands('commercial')">商业承兑按账龄段生成</el-button>
                    <el-button size="small" type="primary" plain @click="onFillAgingBands('bank')">银行承兑按账龄段生成</el-button>
                    <el-tag size="small" type="info" effect="plain">账龄口径：{{ agingPresetLabel }}（{{ agingBandLabels.join(' / ') }}）</el-tag>
                  </div>
                  <el-table :data="soeAgingRows" row-key="rowId" border size="small" style="width:100%;margin-bottom:12px">
                    <el-table-column label="名称" min-width="280">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'subtotal' || row.rowKind === 'summary'">
                          <span :style="row.rowKind === 'summary' ? 'font-weight:600' : ''">{{ row.name }}</span>
                        </template>
                        <template v-else>
                          <el-select
                            :model-value="row.name"
                            size="small"
                            filterable
                            allow-create
                            default-first-option
                            clearable
                            style="width:100%"
                            :disabled="isReadonly"
                            placeholder="选择账龄段（可自定义出票人类型）"
                            @change="(v:string)=>updateCell(`portfolio-${row.sourceType}-end`, row.rowId, 'drawerTypeOrAging', v || '')"
                          >
                            <el-option v-for="label in agingBandLabels" :key="label" :label="label" :value="label" />
                          </el-select>
                        </template>
                      </template>
                    </el-table-column>
                    <el-table-column label="账面余额" min-width="120" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'summary' || (row.rowKind === 'subtotal' && row.hasDetail)"><span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.balance)" /></template>
                        <template v-else-if="row.rowKind === 'subtotal'">
                          <el-input-number :model-value="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateBadDebtClassFixed('end', row.sourceType === 'bank' ? 'bank' : 'commercial', 'balance', Number(v ?? 0))" style="width:100%" />
                        </template>
                        <template v-else><el-input-number :model-value="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell(`portfolio-${row.sourceType}-end`, row.rowId, 'balance', Number(v ?? 0))" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="坏账准备" min-width="120" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'summary' || (row.rowKind === 'subtotal' && row.hasDetail)"><span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.provision)" /></template>
                        <template v-else-if="row.rowKind === 'subtotal'">
                          <el-input-number :model-value="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateBadDebtClassFixed('end', row.sourceType === 'bank' ? 'bank' : 'commercial', 'provision', Number(v ?? 0))" style="width:100%" />
                        </template>
                        <template v-else><el-input-number :model-value="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell(`portfolio-${row.sourceType}-end`, row.rowId, 'provision', Number(v ?? 0))" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="预期信用损失率(%)" min-width="120" align="right"><template #default="{ row }">{{ fmtPct(row.lossRate || 0) }}</template></el-table-column>
                    <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                      <template #default="{ row }">
                        <el-button v-if="row.rowKind==='detail'" :icon="Delete" text type="danger" size="small" @click="removePortfolioRow(row.rowId, row.sourceType, 'end')" />
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
                <details class="guidance-fold">
                  <summary>📋 编制提示</summary>
                  <p>提示：此处披露本期转回或收回金额重要的应收票据坏账准备。若票据逾期，则应转入应收账款并计提坏账准备，账龄应连续计算。</p>
                </details>
              </template>
              <template v-else>
              <!-- 期末分类表 -->
              <h4 style="margin:0 0 8px">（4.1）坏账准备计提情况（期末）</h4>
              <el-button
                v-if="!isReadonly"
                size="small"
                :icon="Plus"
                @click="addIndividualRow('end')"
                style="margin-bottom:8px"
              >
                在“其中”下添加行
              </el-button>
              <el-table
                :data="badDebtEndRowsForDisplay"
                row-key="rowId"
                border
                size="small"
                style="width:100%;margin-bottom:12px"
                :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                :cell-style="{ padding: '3px 6px' }"
              >
                <el-table-column label="类别" min-width="180">
                  <template #default="{ row }">
                    <template v-if="row.rowKind === 'individual'">
                      <el-input
                        :model-value="row.label || ''"
                        size="small"
                        :disabled="isReadonly"
                        placeholder="请输入单项名称"
                        @input="(v: string) => updateCell('individualEnd', row.rowId, 'name', v)"
                      />
                    </template>
                    <template v-else>
                      <span :style="row.rowKind==='summary' ? 'font-weight:600' : ''">{{ row.label }}</span>
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="账面余额" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowKind === 'summary'"><b v-html="fmtAmt(row.balance)" /></template>
                    <template v-else-if="row.rowKind === 'hint'">-</template>
                    <template v-else-if="row.rowKind === 'individual'">
                      <el-input-number
                        :model-value="row.balance"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateCell('individualEnd', row.rowId, 'balance', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else-if="row.source">
                      <el-input-number
                        :model-value="row.balance"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateBadDebtClassFixed('end', row.source, 'balance', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else><span v-html="fmtAmt(row.balance)" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="比例(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.ratio) }}</span></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowKind === 'summary'"><b v-html="fmtAmt(row.provision)" /></template>
                    <template v-else-if="row.rowKind === 'hint'">-</template>
                    <template v-else-if="row.rowKind === 'individual'">
                      <el-input-number
                        :model-value="row.provision"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateCell('individualEnd', row.rowId, 'provision', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else-if="row.source">
                      <el-input-number
                        :model-value="row.provision"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateBadDebtClassFixed('end', row.source, 'provision', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else><span v-html="fmtAmt(row.provision)" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column label="账面价值" min-width="130" align="right">
                  <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.bookValue)" /></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowKind === 'individual'" :icon="Delete" text type="danger" size="small" @click="removeIndividualRow(row.rowId, 'end')" />
                  </template>
                </el-table-column>
              </el-table>

              <!-- 上年分类表 -->
              <h4 style="margin:0 0 8px">（4.2）坏账准备计提情况（上年年末）</h4>
              <el-button
                v-if="!isReadonly"
                size="small"
                :icon="Plus"
                @click="addIndividualRow('prior')"
                style="margin-bottom:8px"
              >
                在“其中”下添加行
              </el-button>
              <el-table
                :data="badDebtPriorRowsForDisplay"
                row-key="rowId"
                border
                size="small"
                style="width:100%;margin-bottom:12px"
                :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                :cell-style="{ padding: '3px 6px' }"
              >
                <el-table-column label="类别" min-width="180">
                  <template #default="{ row }">
                    <template v-if="row.rowKind === 'individual'">
                      <el-input
                        :model-value="row.label || ''"
                        size="small"
                        :disabled="isReadonly"
                        placeholder="请输入单项名称"
                        @input="(v: string) => updateCell('individualPrior', row.rowId, 'name', v)"
                      />
                    </template>
                    <template v-else>
                      <span :style="row.rowKind==='summary'?'font-weight:600':''">{{ row.label }}</span>
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="账面余额" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowKind === 'summary'"><b v-html="fmtAmt(row.balance)" /></template>
                    <template v-else-if="row.rowKind === 'hint'">-</template>
                    <template v-else-if="row.rowKind === 'individual'">
                      <el-input-number
                        :model-value="row.balance"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateCell('individualPrior', row.rowId, 'balance', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else-if="row.source">
                      <el-input-number
                        :model-value="row.balance"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateBadDebtClassFixed('prior', row.source, 'balance', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else><span v-html="fmtAmt(row.balance)" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="比例(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.ratio) }}</span></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowKind === 'summary'"><b v-html="fmtAmt(row.provision)" /></template>
                    <template v-else-if="row.rowKind === 'hint'">-</template>
                    <template v-else-if="row.rowKind === 'individual'">
                      <el-input-number
                        :model-value="row.provision"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateCell('individualPrior', row.rowId, 'provision', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else-if="row.source">
                      <el-input-number
                        :model-value="row.provision"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateBadDebtClassFixed('prior', row.source, 'provision', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                    <template v-else><span v-html="fmtAmt(row.provision)" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column label="账面价值" min-width="130" align="right">
                  <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.bookValue)" /></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowKind === 'individual'" :icon="Delete" text type="danger" size="small" @click="removeIndividualRow(row.rowId, 'prior')" />
                  </template>
                </el-table-column>
              </el-table>
              </template>
              <details v-if="variant === 'listed'" class="guidance-fold">
                <summary>📋 编制提示</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.badDebtClassification" :key="'bdg-'+i">{{ t }}</p>
              </details>
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['badDebtClass'] || ''" placeholder="请输入坏账分类相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('badDebtClass', v)" />
                <div class="note-actions">
                  <el-button size="small" :loading="aiLoadingSection === 'badDebtClass'" :disabled="isReadonly" @click="handleAiGenerate('badDebtClass')">🤖 AI</el-button>
                  <el-button v-if="openReviewDialog" size="small" @click="handleReview('badDebtClass')">💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.6 Bad Debt Movement Section ═══ -->
            <template v-if="section === 'badDebtMovement'">
              <template v-if="variant === 'soe'">
                <div class="table-frame">
                  <el-table
                    :data="soeMovementRowsForDisplay"
                    border
                    size="small"
                    style="width:100%;margin-bottom:12px"
                    :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                    :cell-style="{ padding: '3px 6px' }"
                  >
                    <el-table-column label="类别" min-width="220">
                      <template #default="{ row }"><span :style="row.rowKind==='summary'?'font-weight:600':''">{{ row.label }}</span></template>
                    </el-table-column>
                    <el-table-column label="期初数" min-width="110" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'hint'">-</template>
                        <template v-else><span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.sourceRow?.priorBalance || 0)" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="本期变动情况" align="center">
                      <el-table-column label="计提" min-width="90" align="right">
                        <template #default="{ row }">
                          <template v-if="row.rowKind === 'hint'">-</template>
                          <template v-else-if="row.rowKind === 'summary'"><span v-html="fmtAmt(row.sourceRow?.provision || 0)" /></template>
                          <template v-else><el-input-number :model-value="row.sourceRow?.provision || 0" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell('movement', row.sourceRow.rowId, 'provision', Number(v ?? 0))" style="width:100%" /></template>
                        </template>
                      </el-table-column>
                      <el-table-column label="收回或转回" min-width="110" align="right">
                        <template #default="{ row }">
                          <template v-if="row.rowKind === 'hint'">-</template>
                          <template v-else-if="row.rowKind === 'summary'"><span v-html="fmtAmt(row.sourceRow?.reversal || 0)" /></template>
                          <template v-else><el-input-number :model-value="row.sourceRow?.reversal || 0" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell('movement', row.sourceRow.rowId, 'reversal', Number(v ?? 0))" style="width:100%" /></template>
                        </template>
                      </el-table-column>
                      <el-table-column label="核销" min-width="90" align="right">
                        <template #default="{ row }">
                          <template v-if="row.rowKind === 'hint'">-</template>
                          <template v-else-if="row.rowKind === 'summary'"><span v-html="fmtAmt(row.sourceRow?.writeOff || 0)" /></template>
                          <template v-else><el-input-number :model-value="row.sourceRow?.writeOff || 0" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell('movement', row.sourceRow.rowId, 'writeOff', Number(v ?? 0))" style="width:100%" /></template>
                        </template>
                      </el-table-column>
                      <el-table-column label="其他变动" min-width="100" align="right">
                        <template #default="{ row }">
                          <template v-if="row.rowKind === 'hint'">-</template>
                          <template v-else-if="row.rowKind === 'summary'"><span v-html="fmtAmt(row.sourceRow?.other || 0)" /></template>
                          <template v-else><el-input-number :model-value="row.sourceRow?.other || 0" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell('movement', row.sourceRow.rowId, 'other', Number(v ?? 0))" style="width:100%" /></template>
                        </template>
                      </el-table-column>
                    </el-table-column>
                    <el-table-column label="期末数" min-width="110" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'hint'">-</template>
                        <template v-else><span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.sourceRow?.endBalance || 0)" /></template>
                      </template>
                    </el-table-column>
                  </el-table>

                  <div class="detail-band">其中，本期转回或收回金额重要的应收票据坏账准备：</div>
                  <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addReversalRow" style="margin-bottom:8px">添加行</el-button>
                  <el-table
                    :data="[...reversalDetailRows, reversalDetailTotal]"
                    row-key="rowId"
                    border
                    size="small"
                    style="width:100%"
                    :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                    :cell-style="{ padding: '3px 6px' }"
                  >
                    <el-table-column label="债务人名称" min-width="140">
                      <template #default="{ row }">
                        <template v-if="row.rowType==='summary'"><b>{{ row.companyName }}</b></template>
                        <template v-else><el-input :model-value="row.companyName" size="small" :disabled="isReadonly" @input="(v:string)=>updateCell('reversalDetail', row.rowId, 'companyName', v)" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="转回或收回金额" min-width="130" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowType==='summary'"><b class="amount-cell" v-html="fmtAmt(row.amount)" /></template>
                        <template v-else><el-input-number :model-value="row.amount" :controls="false" size="small" :disabled="isReadonly" @change="(v:number|undefined)=>updateCell('reversalDetail', row.rowId, 'amount', Number(v ?? 0))" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="转回或收回前累计已计提坏账准备金额" min-width="210">
                      <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" :model-value="row.reversalBasis" size="small" :disabled="isReadonly" @input="(v:string)=>updateCell('reversalDetail', row.rowId, 'reversalBasis', v)" /></template>
                    </el-table-column>
                    <el-table-column label="转回或收回原因" min-width="160">
                      <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" :model-value="row.reversalReason" size="small" :disabled="isReadonly" @input="(v:string)=>updateCell('reversalDetail', row.rowId, 'reversalReason', v)" /></template>
                    </el-table-column>
                    <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                      <template #default="{ row }"><el-button v-if="row.rowType==='dynamic'" :icon="Delete" text type="danger" size="small" @click="removeReversalRow(row.rowId)" /></template>
                    </el-table-column>
                  </el-table>
                </div>
              </template>
              <template v-else>
                <h4 style="margin:0 0 8px">坏账准备金额</h4>
                <div>
                <el-table
                  :data="[
                    { key: 'priorBalance', label: '上年年末数', value: listedMovementRow.priorBalance },
                    { key: 'provision', label: '本期计提', value: listedMovementRow.provision },
                    { key: 'reversal', label: '本期收回或转回', value: listedMovementRow.reversal },
                    { key: 'writeOff', label: '本期核销', value: listedMovementRow.writeOff },
                    { key: 'transfer', label: '【本期转销】', value: listedMovementRow.transfer },
                    { key: 'other', label: '【其他】', value: listedMovementRow.other },
                    { key: 'endBalance', label: '期末数', value: listedMovementRow.endBalance },
                  ]"
                  border
                  size="small"
                  style="width:100%;margin-bottom:12px"
                  :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                  :cell-style="{ padding: '3px 6px' }"
                >
                  <el-table-column label="项目" min-width="220">
                    <template #default="{ row }">
                      <span :style="row.label.includes('【') ? 'color:#f56c6c' : ''">{{ row.label }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="坏账准备金额" min-width="180" align="right">
                    <template #default="{ row }">
                      <template v-if="row.key === 'endBalance'">
                        <span class="amount-cell" v-html="fmtAmt(row.value)" />
                      </template>
                      <template v-else>
                        <el-input-number
                          :model-value="row.value"
                          :controls="false"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number | undefined) => updateCell('movement', listedMovementRow.rowId, row.key, Number(v ?? 0))"
                          style="width:100%"
                        />
                      </template>
                    </template>
                  </el-table-column>
                </el-table>

                <div class="detail-band">其中：本期转回或收回金额重要的应收票据坏账准备如下：</div>
                <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addReversalRow" style="margin-bottom:8px">添加行</el-button>
                <el-table
                  :data="[...reversalDetailRows, reversalDetailTotal]"
                  row-key="rowId"
                  border
                  size="small"
                  style="width:100%"
                  :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                  :cell-style="{ padding: '3px 6px' }"
                >
                  <el-table-column label="单位名称" min-width="120">
                    <template #default="{ row }">
                      <template v-if="row.rowType==='summary'"><b>{{ row.companyName }}</b></template>
                      <template v-else>
                        <el-input
                          :model-value="row.companyName"
                          size="small"
                          :disabled="isReadonly"
                          @input="(v: string) => updateCell('reversalDetail', row.rowId, 'companyName', v)"
                        />
                      </template>
                    </template>
                  </el-table-column>
                  <el-table-column label="转回原因" min-width="110">
                    <template #default="{ row }">
                      <el-input
                        v-if="row.rowType!=='summary'"
                        :model-value="row.reversalReason"
                        size="small"
                        :disabled="isReadonly"
                        @input="(v: string) => updateCell('reversalDetail', row.rowId, 'reversalReason', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="收回方式" min-width="110">
                    <template #default="{ row }">
                      <el-input
                        v-if="row.rowType!=='summary'"
                        :model-value="row.originalMethod"
                        size="small"
                        :disabled="isReadonly"
                        @input="(v: string) => updateCell('reversalDetail', row.rowId, 'originalMethod', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="原确定坏账准备金额的依据" min-width="170">
                    <template #default="{ row }">
                      <el-input
                        v-if="row.rowType!=='summary'"
                        :model-value="row.reversalBasis"
                        size="small"
                        :disabled="isReadonly"
                        @input="(v: string) => updateCell('reversalDetail', row.rowId, 'reversalBasis', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="转回或收回金额" min-width="120" align="right">
                    <template #default="{ row }">
                      <template v-if="row.rowType==='summary'"><b class="amount-cell" v-html="fmtAmt(row.amount)" /></template>
                      <template v-else>
                        <el-input-number
                          :model-value="row.amount"
                          :controls="false"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number | undefined) => updateCell('reversalDetail', row.rowId, 'amount', Number(v ?? 0))"
                          style="width:100%"
                        />
                      </template>
                    </template>
                  </el-table-column>
                  <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                    <template #default="{ row }"><el-button v-if="row.rowType==='dynamic'" :icon="Delete" text type="danger" size="small" @click="removeReversalRow(row.rowId)" /></template>
                  </el-table-column>
                </el-table>
                </div>
              </template>
            </template>

            <!-- ═══ 6.7 Write-off Section ═══ -->
            <template v-if="section === 'writeOff'">
              <div :class="variant === 'soe' ? 'table-frame' : ''">
              <el-table
                :data="[{ label: '实际核销的应收票据', amount: writeOffAmount }]"
                border
                size="small"
                style="width:100%;margin-bottom:12px"
                :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                :cell-style="{ padding: '3px 6px' }"
              >
                <el-table-column label="项目" min-width="220">
                  <template #default="{ row }">{{ row.label }}</template>
                </el-table-column>
                <el-table-column label="核销金额" min-width="180" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="row.amount"
                      :controls="false"
                      size="small"
                      :disabled="isReadonly"
                      @change="(v: number | undefined) => updateCell('writeOffAmount', '', 'amount', Number(v ?? 0))"
                      style="width:100%"
                    />
                  </template>
                </el-table-column>
              </el-table>

              <div class="detail-band">其中，重要的应收票据核销情况如下（逐项披露）：</div>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addWriteOffRow" style="margin-bottom:8px">添加行</el-button>
              <el-table
                :data="[...writeOffDetailRows, writeOffDetailTotal]"
                row-key="rowId"
                border
                size="small"
                style="width:100%"
                :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                :cell-style="{ padding: '3px 6px' }"
              >
                <el-table-column label="单位名称" min-width="120">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b>{{ row.companyName }}</b></template>
                    <template v-else>
                      <el-input
                        :model-value="row.companyName"
                        size="small"
                        :disabled="isReadonly"
                        @input="(v: string) => updateCell('writeOffDetail', row.rowId, 'companyName', v)"
                      />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column :label="variant === 'soe' ? '应收票据的性质' : '应收票据'" min-width="110">
                  <template #default="{ row }">
                    <el-input
                      v-if="row.rowType!=='summary'"
                      :model-value="row.noteType"
                      size="small"
                      :disabled="isReadonly"
                      @input="(v: string) => updateCell('writeOffDetail', row.rowId, 'noteType', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="核销金额" min-width="110" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b class="amount-cell" v-html="fmtAmt(row.amount)" /></template>
                    <template v-else>
                      <el-input-number
                        :model-value="row.amount"
                        :controls="false"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number | undefined) => updateCell('writeOffDetail', row.rowId, 'amount', Number(v ?? 0))"
                        style="width:100%"
                      />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="核销原因" min-width="120">
                  <template #default="{ row }">
                    <el-input
                      v-if="row.rowType!=='summary'"
                      :model-value="row.reason"
                      size="small"
                      :disabled="isReadonly"
                      @input="(v: string) => updateCell('writeOffDetail', row.rowId, 'reason', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="履行的核销程序" min-width="140">
                  <template #default="{ row }">
                    <el-input
                      v-if="row.rowType!=='summary'"
                      :model-value="row.procedure"
                      size="small"
                      :disabled="isReadonly"
                      @input="(v: string) => updateCell('writeOffDetail', row.rowId, 'procedure', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="款项是否由关联交易产生" min-width="140">
                  <template #default="{ row }">
                    <el-input
                      v-if="row.rowType!=='summary'"
                      :model-value="row.relatedPartyFlag"
                      size="small"
                      :disabled="isReadonly"
                      @input="(v: string) => updateCell('writeOffDetail', row.rowId, 'relatedPartyFlag', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button v-if="row.rowType==='dynamic'" :icon="Delete" text type="danger" size="small" @click="removeWriteOffRow(row.rowId)" /></template>
                </el-table-column>
              </el-table>
              </div>
              <details v-if="variant === 'listed'" class="guidance-fold">
                <summary>📋 编制提示</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.writeOff" :key="'wog-'+i">{{ t }}</p>
              </details>
              <!-- Note textarea for writeOff -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['writeOff'] || ''" placeholder="请输入核销相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('writeOff', v)" />
                <div class="note-actions">
                  <el-button size="small" :loading="aiLoadingSection === 'writeOff'" :disabled="isReadonly" @click="handleAiGenerate('writeOff')">🤖 AI</el-button>
                  <el-button v-if="openReviewDialog" size="small" @click="handleReview('writeOff')">💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.8 Category Summary (SOE only) ═══ -->
            <template v-if="section === 'categorySummary' && variant === 'soe'">
              <el-table
                :data="[...categorySummaryRows, categorySummaryTotal]"
                border
                size="small"
                style="width:100%"
                :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35', textAlign: 'center' }"
                :cell-style="{ padding: '3px 6px' }"
              >
                <el-table-column label="票据种类" min-width="130" fixed>
                  <template #default="{ row }"><span :style="row.rowType==='summary'?'font-weight:600':''">{{ row.category }}</span></template>
                </el-table-column>
                <el-table-column label="期末数" align="center">
                  <el-table-column label="账面余额" min-width="100" align="right">
                    <template #default="{ row }">
                      <el-tooltip content="取自审定表D1-1" placement="top">
                        <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.endBalance)" />
                      </el-tooltip>
                    </template>
                  </el-table-column>
                  <el-table-column label="坏账准备" min-width="100" align="right">
                    <template #default="{ row }">
                      <el-tooltip content="取自审定表D1-1" placement="top">
                        <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.endProvision)" />
                      </el-tooltip>
                    </template>
                  </el-table-column>
                  <el-table-column label="期末账面价值" min-width="100" align="right">
                    <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.endBookValue)" /></template>
                  </el-table-column>
                </el-table-column>
                <el-table-column label="期初数" align="center">
                  <el-table-column label="账面余额" min-width="100" align="right">
                    <template #default="{ row }">
                      <el-tooltip content="取自审定表D1-1" placement="top">
                        <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.priorBalance)" />
                      </el-tooltip>
                    </template>
                  </el-table-column>
                  <el-table-column label="坏账准备" min-width="100" align="right">
                    <template #default="{ row }">
                      <el-tooltip content="取自审定表D1-1" placement="top">
                        <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.priorProvision)" />
                      </el-tooltip>
                    </template>
                  </el-table-column>
                  <el-table-column label="期初账面价值" min-width="100" align="right">
                    <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.priorBookValue)" /></template>
                  </el-table-column>
                </el-table-column>
              </el-table>
            </template>

          </div>
        </el-card>
      </template>
  </div>
</template>

<style scoped>
.d1-disclosure { padding: 16px; font-size: var(--wp-font-size, 13px) }
.d1-disclosure :deep(.el-table th),
.d1-disclosure :deep(.el-table td),
.d1-disclosure :deep(.el-input__inner),
.d1-disclosure :deep(.el-textarea__inner),
.d1-disclosure :deep(.el-button),
.d1-disclosure :deep(.el-tag),
.d1-disclosure :deep(.el-form-item__label) {
  font-size: var(--wp-font-size, 13px);
}
.d1-disclosure__header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap }
.d1-disclosure__toolbar { margin-left: auto }
.d1-section-card { margin-bottom: 12px }
.cross-sheet-summary { background: #ecf5ff; border-radius: 4px; padding: 12px; margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 16px; align-items: center }
.cross-sheet-summary .value { font-weight: 600; color: #409eff }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums }
.amount-negative { color: #f56c6c }
.auto-fetch-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px }
.guidance-fold { margin: 12px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266 }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff }
.guidance-fold p { margin: 6px 0; line-height: 1.6 }
.section-note { margin-top: 12px; padding: 10px 0 }
.section-note label { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; display: block; margin-bottom: 6px }
.note-actions { margin-top: 6px; display: flex; gap: 8px }
.excel-tip {
  color: #2f54eb;
  font-size: 12px;
  line-height: 1.7;
  margin: 6px 0 10px;
}
.excel-hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
  margin: 8px 0 4px;
}
.detail-band {
  margin: 10px 0 8px;
  padding: 6px 10px;
  background: #ecf5ff;
  color: #2f54eb;
  border-top: 1px solid #d9ecff;
  border-bottom: 1px solid #d9ecff;
  font-size: 12px;
  line-height: 1.5;
}
.table-frame {
  border: 1px solid #dcdfe6;
  border-radius: 2px;
  padding: 8px;
  margin: 8px 0 12px;
}
.listed-top-note {
  margin-top: 16px;
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}
.listed-guidance-fold {
  margin: 8px 0 12px;
}
</style>
