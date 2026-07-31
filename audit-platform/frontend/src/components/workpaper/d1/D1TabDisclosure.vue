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
import { ElMessage, ElMessageBox } from 'element-plus'
import { Lock, Delete, Plus } from '@element-plus/icons-vue'
import {
  useD1Disclosure,
  DISCLOSURE_GUIDANCE,
  type DisclosureVariant,
} from '../composables/useD1Disclosure'
// 比率一律用共享纯函数按当前金额现算（口径 F4-25 / F4-12），禁止透传持久化值或相加
import { ratioOf } from '../composables/useD1FormulaEngine'
import {
  buildD1SyncPayload,
  D1_NOTE_SECTION,
  D1_MAIN_SUBTABLE,
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
// 披露内部勾稽校验（规则源 = 应收票据校验预设 F4-1~F4-30）
import { runD1DisclosureChecks } from '../composables/d1DisclosureConsistency'
import D1DisclosureConsistencyPanel from './D1DisclosureConsistencyPanel.vue'
// 证据附件（复用平台 ItemAttachment 通道，不新建后端）
import D1SheetAttachments from './D1SheetAttachments.vue'
// 🔴 可编辑金额千分符只能用 el-input 接管（EP 的 input-number 无 formatter prop）
import WpAmountInput from '../shared/WpAmountInput.vue'
// 金额格式单一真源（与 D1 其余 15 个 Tab 同款 provide/inject + store 兜底）
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

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
/**
 * 说明文本域子节键 —— **必须覆盖 `sectionOrder` 的全部子节**。
 *
 * 🔴 漏一个子节 = 该段说明无处录入、AI 无处落笔、附注 `text_content` 永远缺这一节
 * （同 D2 `portfolio` 缺文本域那类缺陷）。原先只有 5 个键，而 sectionOrder 是
 * 6 段（上市）/ 7 段（国企）—— `transfer` 与 `badDebtMovement` 无文本域：
 * 源模板 R27 括注要求 transfer 段披露「终止确认的金额及相关利得损失」，
 * R43/R90 要求变动区说明「按组合计提坏账准备的原因」。
 * 注：`categorySummary`（国企主表）与上市顶部汇总表共用 `top`（= 应收票据总体说明），
 * 故键集不含 `categorySummary`。
 * 守卫：`__tests__/d1NoteTextSections.spec.ts`（键集 ⊇ sectionOrder ∪ 'top'）。
 */
const NOTE_SECTION_KEYS = [
  'top', 'pledged', 'endorsed', 'transfer',
  'badDebtClass', 'badDebtMovement', 'writeOff',
] as const
const aiLoadingSection = ref<string>('')
const isSyncing = ref(false)
const openReviewDialog = inject<any>('openReviewDialog', null)
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

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

/**
 * 🔴 同一批次不得重复提交相同 `item_id` —— 后端会**整批拒绝**，该批全部数据丢失。
 *
 * 本页每张动态表整表存成一个 JSON item（`class-end-rows` 等），2 秒防抖窗口内对同一张表
 * 改两个格子就必然产生两条同 id 记录。2026-07-30 浏览器实测中招：连改
 * 商承/银承 的账面余额与坏账准备共 4 次 → 4 条 `D1-disc-soe-class-end-rows` 同批提交 →
 * 整批被拒、`catch` 静默吞掉，界面看着有值但库里根本没有这个键。
 *
 * 按 item_id 去重，**后写覆盖先写**（累积顺序即时间顺序，最后一条是最新整表快照）。
 */
function dedupeByItemId(items: any[]): any[] {
  const byId = new Map<string, any>()
  for (const it of items) {
    const key = String(it?.item_id ?? '')
    if (!key) continue
    byId.set(key, it)
  }
  return [...byId.values()]
}

const debouncedSave = useDebounceFn(async () => {
  if (pendingSaveItems.value.length === 0) return
  const items = dedupeByItemId(pendingSaveItems.value)
  pendingSaveItems.value = []
  if (items.length === 0) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
    // 保存成功后自动同步到附注（防抖/非阻塞/失败静默）
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  } catch (err) {
    // 保存失败必须让用户知道（旧实现完全静默 → 数据丢了没人发现）
    ElMessage.warning('披露表保存失败，请检查网络后重新编辑该单元格')
    // eslint-disable-next-line no-console
    console.error('[D1TabDisclosure] checklist-responses 保存失败', err)
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
  addPortfolioPairRow, renamePortfolioPair, fillPortfolioAgingBandsPair, removePortfolioPairRow,
  movementRows, movementTotal, reversalDetailRows, reversalDetailTotal,
  addReversalRow, removeReversalRow,
  movementDetailRows, movementDetailTotal, hasMovementDetail,
  addMovementDetailRow, removeMovementDetailRow,
  writeOffAmount, writeOffDetailRows, writeOffDetailTotal,
  addWriteOffRow, removeWriteOffRow,
  categorySummaryRows, categorySummaryTotal, canEditCategorySummary,
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

// ─── 上市版按组合计提坏账准备（源模板 R76~R89，双期并列）────────────────────
// 源模板每个票据种类一张表，「名  称」列的红字占位是「出票人类型或账龄」，
// 期末余额 / 上年年末余额 各 3 列（应收票据 / 坏账准备 / 预期信用损失率(%)）。
// 附注侧由 `mergePortfolio` 按名称把两期对齐，故这里也按名称合并成一行展示，
// 新增 / 改名 / 按段生成全部走成对操作，避免两期错位产生孤儿行。

interface ListedPortfolioViewRow {
  name: string
  endRowId?: string
  priorRowId?: string
  endBalance: number
  endProvision: number
  endLossRate: number
  priorBalance: number
  priorProvision: number
  priorLossRate: number
}

function buildListedPortfolioRows(type: 'bank' | 'commercial'): ListedPortfolioViewRow[] {
  const end = type === 'bank' ? bankPortfolioEndRows.value : commercialPortfolioEndRows.value
  const prior = type === 'bank' ? bankPortfolioPriorRows.value : commercialPortfolioPriorRows.value
  const names: string[] = []
  for (const r of [...end, ...prior]) {
    const n = String(r.drawerTypeOrAging || '')
    if (!names.includes(n)) names.push(n)
  }
  return names.map((n) => {
    const e = end.find(r => String(r.drawerTypeOrAging || '') === n)
    const p = prior.find(r => String(r.drawerTypeOrAging || '') === n)
    return {
      name: n,
      endRowId: e?.rowId,
      priorRowId: p?.rowId,
      endBalance: e?.balance || 0,
      endProvision: e?.provision || 0,
      endLossRate: ratioOf(e?.provision || 0, e?.balance || 0),
      priorBalance: p?.balance || 0,
      priorProvision: p?.provision || 0,
      priorLossRate: ratioOf(p?.provision || 0, p?.balance || 0),
    }
  })
}

const bankPortfolioViewRows = computed(() => buildListedPortfolioRows('bank'))
const commercialPortfolioViewRows = computed(() => buildListedPortfolioRows('commercial'))

/** 上市版两个组合计提项目区块（顺序同源模板：先银行承兑，后商业承兑）。 */
const listedPortfolioBlocks = computed(() => [
  { type: 'bank' as const, title: '银行承兑汇票', rows: bankPortfolioViewRows.value },
  { type: 'commercial' as const, title: '商业承兑汇票', rows: commercialPortfolioViewRows.value },
])

function portfolioViewTotal(rows: ListedPortfolioViewRow[]): ListedPortfolioViewRow {
  const sum = (k: keyof ListedPortfolioViewRow) => rows.reduce((s, r) => s + Number(r[k] || 0), 0)
  const endBalance = sum('endBalance')
  const endProvision = sum('endProvision')
  const priorBalance = sum('priorBalance')
  const priorProvision = sum('priorProvision')
  return {
    name: '合计',
    endBalance, endProvision,
    endLossRate: ratioOf(endProvision, endBalance),
    priorBalance, priorProvision,
    priorLossRate: ratioOf(priorProvision, priorBalance),
  }
}

/** 新增组合明细行：先取名（源模板占位为「出票人类型或账龄」），再向两期各插一行。 */
async function onAddPortfolioPair(type: 'bank' | 'commercial'): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入出票人类型或账龄（如「1年以内（含1年）」「AAA 级银行」）',
      `新增${type === 'bank' ? '银行' : '商业'}承兑汇票组合明细`,
      { confirmButtonText: '新增', cancelButtonText: '取消', inputPlaceholder: '出票人类型或账龄' },
    )
    if (addPortfolioPairRow(type, String(value ?? ''))) ElMessage.success('已新增（期末 + 上年年末各一行）')
    else ElMessage.info('该名称已存在或为空，未新增')
  } catch { /* 用户取消 */ }
}

function onRenamePortfolioPair(type: 'bank' | 'commercial', oldName: string, next: string): void {
  if (renamePortfolioPair(type, oldName, next) === 0) ElMessage.info('名称未变更或已被占用')
}

function onFillAgingBandsPair(type: 'bank' | 'commercial'): void {
  const added = fillPortfolioAgingBandsPair(type, agingBandLabels.value)
  if (added > 0) ElMessage.success(`已按账龄段成对补齐 ${added} 行（期末 + 上年年末）`)
  else ElMessage.info('账龄段已齐备，无需新增')
}

function onRemovePortfolioPair(type: 'bank' | 'commercial', name: string): void {
  const removed = removePortfolioPairRow(type, name)
  if (removed > 0) ElMessage.success(`已删除 ${removed} 行`)
}

// ─── Formatters ──────────────────────────────────────────────────────────────

/**
 * 只读金额格式化。
 *
 * 🔴 平台级铁律：金额格式单一真源 = `stores/displayPrefs` 的 `fmtAmount()`
 * （千分符 + 2 位小数 + 默认「元」+ localStorage 持久化）。本 Tab 曾是 D1 十六个 Tab 里
 * 唯一自带 `toLocaleString` 实现的，导致披露表金额不带单位、不跟随用户偏好。
 * 与其余 15 个 Tab 保持同一封装（负数括号 + `.negative-amount` 红字）。
 */
function fmtAmt(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
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
      // 比率按当前合计现算（F4-25 / F4-12），不透传可能过期的持久化值
      ratio: ratioOf(single?.balance || 0, total.balance),
      provision: single?.provision || 0,
      lossRate: ratioOf(single?.provision || 0, single?.balance || 0),
      bookValue: (single?.balance || 0) - (single?.provision || 0),
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
      ratio: ratioOf(bank?.balance || 0, total.balance),
      provision: bank?.provision || 0,
      lossRate: ratioOf(bank?.provision || 0, bank?.balance || 0),
      bookValue: (bank?.balance || 0) - (bank?.provision || 0),
    },
    {
      rowKind: 'fixed',
      rowId: `commercial-${period}`,
      label: '商业承兑汇票',
      source: 'commercial',
      balance: commercial?.balance || 0,
      ratio: ratioOf(commercial?.balance || 0, total.balance),
      provision: commercial?.provision || 0,
      lossRate: ratioOf(commercial?.provision || 0, commercial?.balance || 0),
      bookValue: (commercial?.balance || 0) - (commercial?.provision || 0),
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
/**
 * 国企分类表三行（单项 / 组合 / 合计）。
 *
 * 🔴 聚合行的比率必须按**聚合后的金额**重算：
 * 旧实现把银承与商承的 `ratio` 直接相加（两者分母是各自录入时点的合计）→ 实测
 * 「按组合计提坏账准备」行显示 162.50%（应 100.00%）；`lossRate` 还被硬编码为 0，
 * 附注里显示成 `-`。口径见预设 F4-25 / F4-12 / F4-11。
 */
function buildSoeClassRows(period: 'end' | 'prior') {
  const rows = period === 'end' ? classEndRows.value : classPriorRows.value
  const total = period === 'end' ? classEndTotal.value : classPriorTotal.value
  const single = rows.find(r => r.rowId === `class-${period}-individual`)
  const bank = rows.find(r => r.rowId === `class-${period}-portfolio-bank`)
  const commercial = rows.find(r => r.rowId === `class-${period}-portfolio-commercial`)
  const comboBalance = (bank?.balance || 0) + (commercial?.balance || 0)
  const comboProvision = (bank?.provision || 0) + (commercial?.provision || 0)
  return [
    {
      rowId: `soe-${period}-single`, label: '按单项计提坏账准备',
      balance: single?.balance || 0,
      ratio: ratioOf(single?.balance || 0, total.balance),
      provision: single?.provision || 0,
      lossRate: ratioOf(single?.provision || 0, single?.balance || 0),
      bookValue: (single?.balance || 0) - (single?.provision || 0),
    },
    {
      rowId: `soe-${period}-portfolio`, label: '按组合计提坏账准备',
      balance: comboBalance,
      ratio: ratioOf(comboBalance, total.balance),
      provision: comboProvision,
      lossRate: ratioOf(comboProvision, comboBalance),
      bookValue: comboBalance - comboProvision,
    },
    {
      rowId: `soe-${period}-total`, label: '合计',
      balance: total.balance, ratio: total.ratio,
      provision: total.provision, lossRate: total.lossRate, bookValue: total.bookValue,
    },
  ]
}
const soeClassEndRows = computed(() => buildSoeClassRows('end'))
const soeClassPriorRows = computed(() => buildSoeClassRows('prior'))
// 国企组合计提表小计行名逐字取自源模板 A36/A39 与附注模板 八、4[4] 的 rows
// （带「小计：」后缀），改字面量会让同步后的附注行名与模板骨架不匹配。
const SOE_PORTFOLIO_SUBTOTAL = {
  commercial: '商业承兑汇票小计：',
  bank: '银行承兑汇票小计：',
} as const

/**
 * 国企「按组合计提坏账准备的应收票据」行集：商承小计 + 商承账龄明细 +
 * 银承小计 + 银承账龄明细 + 合计（顺序同源模板 A36~A42）。
 *
 * 小计取值口径：有账龄明细时用明细汇总，无明细时回落到分类表对应组合行（可直接录入）。
 * 所有损失率一律 `ratioOf(provision, balance)` 现算 —— 合计行原先硬编码 0。
 */
const soeAgingRows = computed(() => {
  const classRowBalance = (kind: 'bank' | 'commercial', field: 'balance' | 'provision') =>
    classEndRows.value.find(r => r.rowId === `class-end-portfolio-${kind}`)?.[field] || 0

  const build = (kind: 'bank' | 'commercial') => {
    const detail = (kind === 'bank' ? bankPortfolioEndRows.value : commercialPortfolioEndRows.value)
      .map(r => ({ ...r, sourceType: kind }))
    const hasDetail = detail.length > 0
    const balance = hasDetail
      ? detail.reduce((s, r) => s + (r.balance || 0), 0)
      : classRowBalance(kind, 'balance')
    const provision = hasDetail
      ? detail.reduce((s, r) => s + (r.provision || 0), 0)
      : classRowBalance(kind, 'provision')
    return { detail, hasDetail, balance, provision }
  }

  const c = build('commercial')
  const b = build('bank')
  const detailRows = (g: ReturnType<typeof build>) => g.detail.map(r => ({
    rowKind: 'detail',
    rowId: r.rowId,
    sourceType: r.sourceType,
    name: r.drawerTypeOrAging || '',
    balance: r.balance || 0,
    provision: r.provision || 0,
    lossRate: ratioOf(r.provision || 0, r.balance || 0),
  }))
  const totalBalance = c.balance + b.balance
  const totalProvision = c.provision + b.provision

  return [
    {
      rowKind: 'subtotal', rowId: 'soe-commercial-subtotal', sourceType: 'commercial' as const,
      hasDetail: c.hasDetail, name: SOE_PORTFOLIO_SUBTOTAL.commercial,
      balance: c.balance, provision: c.provision, lossRate: ratioOf(c.provision, c.balance),
    },
    ...detailRows(c),
    {
      rowKind: 'subtotal', rowId: 'soe-bank-subtotal', sourceType: 'bank' as const,
      hasDetail: b.hasDetail, name: SOE_PORTFOLIO_SUBTOTAL.bank,
      balance: b.balance, provision: b.provision, lossRate: ratioOf(b.provision, b.balance),
    },
    ...detailRows(b),
    {
      rowKind: 'summary', rowId: 'soe-aging-total', sourceType: 'commercial' as const,
      name: '合计', balance: totalBalance, provision: totalProvision,
      lossRate: ratioOf(totalProvision, totalBalance),
    },
  ]
})
/**
 * 国企坏账变动表行集：单项 / 按组合 / 其中： / 明细… / 合计（顺序同源模板 A48~A52）。
 *
 * 预设 F4-20 要求「其中：」下方所有明细行之和 = 按组合计提行 → 有明细时按组合计提行
 * 改为**明细汇总（只读）**，从结构上保证勾稽成立；无明细时保持可直接录入。
 */
const soeMovementRowsForDisplay = computed(() => {
  const individual = movementRows.value.find(r => r.label === '按单项计提') || movementRows.value[0]
  const portfolioRaw = movementRows.value.find(r => r.label === '按组合计提') || movementRows.value[1]
  const portfolio = hasMovementDetail.value
    ? { ...movementDetailTotal.value, rowId: portfolioRaw?.rowId || 'mv-portfolio' }
    : portfolioRaw
  // 合计行 = 单项 + 组合（F4-19），组合侧取上面已按明细汇总后的口径
  const sumCol = (k: 'priorBalance' | 'provision' | 'reversal' | 'writeOff' | 'transfer' | 'other' | 'endBalance') =>
    (individual?.[k] ?? 0) + (portfolio?.[k] ?? 0)
  const total = {
    rowId: 'mv-total',
    label: '合计',
    priorBalance: sumCol('priorBalance'),
    provision: sumCol('provision'),
    reversal: sumCol('reversal'),
    writeOff: sumCol('writeOff'),
    transfer: sumCol('transfer'),
    other: sumCol('other'),
    endBalance: sumCol('endBalance'),
  }
  return [
    { rowKind: 'data', rowId: individual?.rowId || 'mv-individual', label: '单项计提预期信用损失的应收票据', sourceRow: individual, readonlyRow: false },
    { rowKind: 'data', rowId: portfolio?.rowId || 'mv-portfolio', label: '按组合计提预期信用损失的应收票据', sourceRow: portfolio, readonlyRow: hasMovementDetail.value },
    { rowKind: 'hint', rowId: 'mv-hint', label: '其中：', sourceRow: null, readonlyRow: true },
    ...movementDetailRows.value.map(r => ({
      rowKind: 'detail' as const, rowId: r.rowId, label: r.label, sourceRow: r, readonlyRow: false,
    })),
    { rowKind: 'summary', rowId: total.rowId, label: '合计', sourceRow: total, readonlyRow: true },
  ]
})

// ─── 披露内部勾稽校验（F4-1~F4-30）─────────────────────────────────────────────
// 入参与 buildD1SyncPayload 的 snapshot 同源，保证「面板显示的」= 「推给附注的」。
const consistencySummary = computed(() => {
  const classEnd = props.variant === 'soe' ? soeClassEndRows.value : badDebtEndRowsForDisplay.value
  const classPrior = props.variant === 'soe' ? soeClassPriorRows.value : badDebtPriorRowsForDisplay.value
  const classIndividual = classEndRows.value.find(r => r.rowId === 'class-end-individual')
  const bank = classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')
  const commercial = classEndRows.value.find(r => r.rowId === 'class-end-portfolio-commercial')
  // ④组合明细（期末）：国企一张表（账龄行），上市两张表（银承 + 商承）
  const portfolioEnd = props.variant === 'soe'
    ? soeAgingRows.value.filter((r: any) => r.rowKind === 'detail')
      .map((r: any) => ({ balance: r.balance, provision: r.provision }))
    : [...bankPortfolioEndRows.value, ...commercialPortfolioEndRows.value]
      .map(r => ({ balance: r.balance || 0, provision: r.provision || 0 }))
  const movementRowsForCheck = props.variant === 'soe'
    ? soeMovementRowsForDisplay.value
      .filter((r: any) => r.rowKind === 'data' || r.rowKind === 'summary')
      .map((r: any) => ({ label: r.label, ...(r.sourceRow ?? {}) }))
    : [{ label: '合计', ...listedMovementRow.value }]
  const movementPortfolio = soeMovementRowsForDisplay.value
    .find((r: any) => r.rowId === 'mv-portfolio' || r.label === '按组合计提预期信用损失的应收票据')

  return runD1DisclosureChecks({
    variant: props.variant,
    summaryRows: categorySummaryRows.value as any,
    summaryTotal: categorySummaryTotal.value as any,
    classEndRows: classEnd as any,
    classPriorRows: classPrior as any,
    classEndTotal: classEndTotal.value as any,
    classPriorTotal: classPriorTotal.value as any,
    individualEndRows: individualEndRows.value.map(r => ({ balance: r.balance, provision: r.provision })),
    portfolioEndRows: portfolioEnd,
    classEndIndividual: { balance: classIndividual?.balance || 0, provision: classIndividual?.provision || 0 },
    classEndPortfolio: {
      balance: (bank?.balance || 0) + (commercial?.balance || 0),
      provision: (bank?.provision || 0) + (commercial?.provision || 0),
    },
    movementRows: movementRowsForCheck,
    movementDetailRows: props.variant === 'soe' ? (movementDetailRows.value as any) : [],
    movementPortfolio: (movementPortfolio as any)?.sourceRow,
    movementEndTotal: props.variant === 'soe'
      ? Number((movementRowsForCheck.find((r: any) => r.label === '合计') as any)?.endBalance ?? 0)
      : Number(listedMovementRow.value.endBalance ?? 0),
    movementWriteOffTotal: props.variant === 'soe'
      ? Number((movementRowsForCheck.find((r: any) => r.label === '合计') as any)?.writeOff ?? 0)
      : Number(listedMovementRow.value.writeOff ?? 0),
    pledgedRows: pledgedRows.value.map(r => ({ amount: r.pledgedAmount })),
    pledgedTotal: pledgedTotal.value.pledgedAmount,
    endorsedRows: endorsedRows.value.map(r => ({
      derecognized: r.derecognizedAmount, notDerecognized: r.notDerecognizedAmount,
    })),
    endorsedTotal: {
      derecognized: endorsedTotal.value.derecognizedAmount,
      notDerecognized: endorsedTotal.value.notDerecognizedAmount,
    },
    transferRows: transferRows.value.map(r => ({ amount: r.transferAmount })),
    transferTotal: transferTotal.value.transferAmount,
    writeOffAmount: writeOffAmount.value,
    writeOffDetailRows: writeOffDetailRows.value.map(r => ({ amount: r.amount })),
  })
})

/**
 * 主表（分类总表）两级表头。父表头随变体：上市「期末余额 / 上年年末余额」、
 * 国企「期末数 / 期初数」（逐字取自源模板合并单元格）。
 * `derived` 列由「账面余额 − 坏账准备」推导，不可录入。
 */
const MAIN_TABLE_GROUPS = computed(() => {
  const isSoe = props.variant === 'soe'
  return [
    {
      group: isSoe ? '期末数' : '期末余额',
      cols: [
        { field: 'endBalance', label: '账面余额' },
        { field: 'endProvision', label: '坏账准备' },
        { field: 'endBookValue', label: isSoe ? '期末账面价值' : '账面价值', derived: true },
      ],
    },
    {
      group: isSoe ? '期初数' : '上年年末余额',
      cols: [
        { field: 'priorBalance', label: '账面余额' },
        { field: 'priorProvision', label: '坏账准备' },
        { field: 'priorBookValue', label: isSoe ? '期初账面价值' : '账面价值', derived: true },
      ],
    },
  ]
})

/** 国企变动表「本期变动情况」下的 4 个子列（列名逐字取自源模板 C47:F47）。 */
const SOE_MOVEMENT_CHANGE_COLS = [
  { field: 'provision', label: '计提', width: 90 },
  { field: 'reversal', label: '收回或转回', width: 110 },
  { field: 'writeOff', label: '核销', width: 90 },
  { field: 'other', label: '其他变动', width: 100 },
] as const

/** 新增「其中：」明细行 —— 需命名的动态行先 prompt 取名（平台铁律）。 */
async function onAddMovementDetail(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入组合明细名称（如「银行承兑汇票」「商业承兑汇票」或出票人类型）',
      '新增「其中：」明细行',
      { confirmButtonText: '新增', cancelButtonText: '取消', inputPlaceholder: '组合名称' },
    )
    if (addMovementDetailRow(String(value ?? ''))) {
      ElMessage.success('已新增明细行；「按组合计提」行改为按明细汇总（F4-20）')
    } else {
      ElMessage.info('名称为空，未新增')
    }
  } catch { /* 用户取消 */ }
}

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
  } else if (sectionKey === 'transfer') {
    for (const row of [...transferRows.value, transferTotal.value]) {
      lines.push(`${row.category}: 期末转应收账款金额=${row.transferAmount}`)
    }
  } else if (sectionKey === 'badDebtClass') {
    lines.push(`期末按方法分类合计: 账面余额=${classEndTotal.value.balance}, 坏账准备=${classEndTotal.value.provision}, 账面价值=${classEndTotal.value.bookValue}`)
    lines.push(`上年按方法分类合计: 账面余额=${classPriorTotal.value.balance}, 坏账准备=${classPriorTotal.value.provision}, 账面价值=${classPriorTotal.value.bookValue}`)
  } else if (sectionKey === 'badDebtMovement') {
    const m = props.variant === 'soe' ? movementTotal.value : listedMovementRow.value
    lines.push(`坏账准备变动合计: 期初=${m.priorBalance}, 计提=${m.provision}, 收回或转回=${m.reversal}, 核销=${m.writeOff}, 转销=${m.transfer}, 其他变动=${m.other}, 期末=${m.endBalance}`)
    if (props.variant === 'soe' && movementDetailRows.value.length > 0) {
      for (const r of movementDetailRows.value) {
        lines.push(`  其中 ${r.label}: 期初=${r.priorBalance}, 计提=${r.provision}, 收回或转回=${r.reversal}, 核销=${r.writeOff}, 其他变动=${r.other}, 期末=${r.endBalance}`)
      }
    }
    lines.push(`重要转回或收回明细条数=${reversalDetailRows.value.length}, 金额合计=${reversalDetailTotal.value.amount}`)
  } else if (sectionKey === 'writeOff') {
    lines.push(`本期核销总额=${writeOffAmount.value}`)
    lines.push(`重要核销明细条数=${writeOffDetailRows.value.length}`)
    lines.push(`重要核销明细金额合计=${writeOffDetailTotal.value.amount}`)
  }

  return lines.join('\n')
}

/**
 * 调用平台 AI 生成端点。
 *
 * 🔴 请求体必须是 `{section_id, related_data, existing_content}`（后端
 * `review_dialog.AiGenerateRequest`），响应字段是 `generated_text`。
 * 历史实现发的是 `{section, context}` 且读 `res.data.text` → 必然 422 且取不到文本，
 * 被 catch 吞成「AI生成失败」，5 个披露按钮长期空转。平台正解见 `useReviewDialog.ts`。
 */
async function handleAiGenerate(sectionKey: string): Promise<void> {
  if (props.isReadonly) return
  aiLoadingSection.value = sectionKey
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/review-dialog/ai-generate`, {
      section_id: `d1-disclosure-${props.variant}-${sectionKey}-note`,
      related_data: { variant: props.variant, section: sectionKey, context: buildAiContext(sectionKey) },
      existing_content: sectionNotes.value[sectionKey] || '',
    })
    const payload = res?.data ?? res
    const text = payload?.generated_text ?? payload?.data?.generated_text ?? ''
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

/**
 * 从附注取**主表**合计行的「期末账面价值」。
 *
 * 🔴 必须按表名定位：旧实现遍历所有表取第一个非零数，实测抓到的是
 * 「期末已质押的应收票据」的合计 80000，再和本页主表期末合计（0）比较 →
 * 报「不一致（差异 80000）」，纯误报。
 *
 * 列下标按 `_sub_table_columns` 里 `end_book_value` 的位置定位（values 不含标签列，
 * 故减 1）；取不到列元数据时回退最后一个期末列。
 */
function pickNoteMainBookValue(detail: any): number | null {
  const td = detail?.table_data
  const mainName = D1_MAIN_SUBTABLE[props.variant]
  const tables: any[] = Array.isArray(td?._tables) ? td._tables : []
  const main = tables.find((t: any) => String(t?.name ?? '').trim() === mainName)
  if (!main) return null

  const rows: any[] = Array.isArray(main.rows) ? main.rows : []
  const totalRow = rows.find((r: any) => r?.is_total || String(r?.label ?? '').trim() === '合计')
  if (!totalRow) return null
  const values: any[] = Array.isArray(totalRow.values) ? totalRow.values : []
  if (values.length === 0) return null

  const defs: any[] = Array.isArray(main.columns)
    ? main.columns
    : (Array.isArray(td?._sub_table_columns?.[mainName]) ? td._sub_table_columns[mainName] : [])
  let idx = -1
  if (defs.length > 0) {
    const valueDefs = defs.filter((d: any) => !d?.is_label)
    idx = valueDefs.findIndex((d: any) => d?.key === 'end_book_value')
  }
  const raw = idx >= 0 ? values[idx] : values[2] // 回退：期末组第 3 列 = 账面价值
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

async function checkNoteConsistency(silent = false): Promise<void> {
  if (!props.projectId) return
  noteCheckState.value = { status: 'loading', message: '正在读取附注现存数据…' }
  try {
    const detail = await getDisclosureNoteDetail(props.projectId, auditYear.value, D1_NOTE_SECTION[props.variant])
    const mainName = D1_MAIN_SUBTABLE[props.variant]
    const noteValue = pickNoteMainBookValue(detail)
    const pageValue = categorySummaryTotal.value?.endBookValue ?? 0
    const pageHasData = Boolean(
      categorySummaryTotal.value?.endBalance || categorySummaryTotal.value?.endProvision,
    )
    if (noteValue === null) {
      noteCheckState.value = {
        status: 'missing',
        message: `附注「${D1_NOTE_SECTION[props.variant]}」的「${mainName}」暂无可比对的合计行（尚未同步或附注为空）`,
      }
    } else if (!pageHasData) {
      // 主表未取数（审定表 D1-1 未加载）时不得报成数据不一致
      noteCheckState.value = {
        status: 'missing',
        message: `本页「${mainName}」未取数（审定表 D1-1 数据未加载），暂无法与附注比对；附注现存期末账面价值 ${noteValue}`,
      }
    } else if (Math.abs(noteValue - pageValue) <= 0.01) {
      noteCheckState.value = {
        status: 'ok',
        message: `附注「${mainName}」合计行期末账面价值与本页一致`,
      }
    } else {
      noteCheckState.value = {
        status: 'diff',
        message: `附注「${mainName}」合计行期末账面价值 ${noteValue} 与本页 ${pageValue} 不一致（差异 ${(noteValue - pageValue).toFixed(2)}）`,
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

    <!-- 披露内部勾稽校验（F4-1~F4-30），紧凑 bar + 折叠明细 + 追溯 chip -->
    <D1DisclosureConsistencyPanel
      v-if="!isLoading"
      :summary="consistencySummary"
      :project-id="projectId"
      :is-readonly="isReadonly"
      style="margin: 0 12px"
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
            <!-- 审定表 D1-1 取到数时只读（以审定表为准）；未取到数时开放手工兜底录入 -->
            <el-table-column
              v-for="grp in MAIN_TABLE_GROUPS"
              :key="grp.group"
              :label="grp.group"
              align="center"
            >
              <el-table-column
                v-for="col in grp.cols"
                :key="col.field"
                :label="col.label"
                min-width="100"
                align="right"
              >
                <template #default="{ row }">
                  <template v-if="col.derived || row.rowType === 'summary'">
                    <span class="amount-cell" v-html="fmtAmt(row[col.field])" />
                  </template>
                  <template v-else-if="canEditCategorySummary && !isReadonly">
                    <WpAmountInput
                      :model-value="row[col.field]"
                      size="small"
                      :disabled="isReadonly"
                      :aria-label="`${grp.group} ${col.label} ${row.category}`"
                      @change="(v: number) => updateCell('categorySummary', row.rowId, col.field, v)"
                      style="width:100%"
                    />
                  </template>
                  <template v-else>
                    <el-tooltip content="取自审定表D1-1" placement="top">
                      <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row[col.field])" />
                    </el-tooltip>
                  </template>
                </template>
              </el-table-column>
            </el-table-column>
          </el-table>
          <div v-if="canEditCategorySummary" class="portfolio-methodology">
            审定表 D1-1 暂未取到数，本表已开放手工录入（账面价值按「账面余额 − 坏账准备」自动计算）；
            审定表导数后将自动改回以审定表为准并转为只读。
          </div>

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
                <el-table-column label="种类" min-width="200">
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
                      <WpAmountInput v-model="row.pledgedAmount" size="small" :disabled="isReadonly"
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
              <!-- 质押证据（质押合同 / 出质登记凭证）-->
              <D1SheetAttachments
                :project-id="projectId"
                :wp-id="wpId"
                :sheet-key="`D1-disc-${variant}-pledged`"
                label="质押证据（质押合同 / 出质登记凭证）"
              />
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
                <el-table-column label="种类" min-width="200">
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
                <el-table-column label="期末终止确认金额" min-width="160" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.derecognizedAmount)" /></template>
                    <template v-else>
                      <WpAmountInput v-model="row.derecognizedAmount" size="small" :disabled="isReadonly"
                        @change="updateCell('endorsed', row.rowId, 'derecognizedAmount', row.derecognizedAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="期末未终止确认金额" min-width="160" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.notDerecognizedAmount)" /></template>
                    <template v-else>
                      <WpAmountInput v-model="row.notDerecognizedAmount" size="small" :disabled="isReadonly"
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
              <!-- 背书贴现证据（贴现协议 / 背书记录 / 银行回单）-->
              <D1SheetAttachments
                :project-id="projectId"
                :wp-id="wpId"
                :sheet-key="`D1-disc-${variant}-endorsed`"
                label="背书贴现证据（贴现协议 / 背书记录 / 银行回单）"
              />
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
                <el-table-column label="种类" min-width="200">
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
                <el-table-column label="期末转应收账款金额" min-width="180" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.transferAmount)" /></template>
                    <template v-else>
                      <WpAmountInput v-model="row.transferAmount" size="small" :disabled="isReadonly"
                        @change="updateCell('transfer', row.rowId, 'transferAmount', row.transferAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowType === 'dynamic'" :icon="Delete" text type="danger" size="small" @click="removeTransferRow(row.rowId)" />
                  </template>
                </el-table-column>
              </el-table>
              <!-- 源模板 R33~R35 / R76~R78 留了空白行 → 两版都支持添加行 -->
              <div v-if="!isReadonly" style="margin-top:8px">
                <el-button size="small" :icon="Plus" @click="addTransferRow">添加行</el-button>
              </div>
              <details class="guidance-fold">
                <summary>📋 编制提示</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.transferIntro" :key="'transfer-intro-'+i">{{ t }}</p>
              </details>
              </div>
              <!-- 源模板 R27 括注要求披露终止确认的金额及相关利得损失 → 需说明文本域 -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['transfer'] || ''" placeholder="请输入因出票人未履约转应收账款的相关说明（含终止确认金额及相关利得或损失）..." :disabled="isReadonly" @input="(v: string) => onNoteChange('transfer', v)" />
                <div class="note-actions">
                  <el-button size="small" :loading="aiLoadingSection === 'transfer'" :disabled="isReadonly" @click="handleAiGenerate('transfer')">🤖 AI</el-button>
                  <el-button v-if="openReviewDialog" size="small" @click="handleReview('transfer')">💬 复核</el-button>
                </div>
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
                        <template v-else><WpAmountInput :model-value="row.balance" size="small" :disabled="isReadonly" @change="(v: number) =>updateCell('individualEnd', row.rowId, 'balance', v)" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="坏账准备" min-width="120" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.provision)" /></template>
                        <template v-else><WpAmountInput :model-value="row.provision" size="small" :disabled="isReadonly" @change="(v: number) =>updateCell('individualEnd', row.rowId, 'provision', v)" style="width:100%" /></template>
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
                          <WpAmountInput :model-value="row.balance" size="small" :disabled="isReadonly" @change="(v: number) =>updateBadDebtClassFixed('end', row.sourceType === 'bank' ? 'bank' : 'commercial', 'balance', v)" style="width:100%" />
                        </template>
                        <template v-else><WpAmountInput :model-value="row.balance" size="small" :disabled="isReadonly" @change="(v: number) =>updateCell(`portfolio-${row.sourceType}-end`, row.rowId, 'balance', v)" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="坏账准备" min-width="120" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'summary' || (row.rowKind === 'subtotal' && row.hasDetail)"><span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.provision)" /></template>
                        <template v-else-if="row.rowKind === 'subtotal'">
                          <WpAmountInput :model-value="row.provision" size="small" :disabled="isReadonly" @change="(v: number) =>updateBadDebtClassFixed('end', row.sourceType === 'bank' ? 'bank' : 'commercial', 'provision', v)" style="width:100%" />
                        </template>
                        <template v-else><WpAmountInput :model-value="row.provision" size="small" :disabled="isReadonly" @change="(v: number) =>updateCell(`portfolio-${row.sourceType}-end`, row.rowId, 'provision', v)" style="width:100%" /></template>
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
                <!-- 期间父表头逐字取自源模板 B38:F38 合并单元格；子列名同 R39 -->
                <el-table-column label="期末余额" align="center">
                  <el-table-column label="金额" min-width="130" align="right">
                    <template #default="{ row }">
                      <template v-if="row.rowKind === 'summary'"><b v-html="fmtAmt(row.balance)" /></template>
                      <template v-else-if="row.rowKind === 'hint'">-</template>
                      <template v-else-if="row.rowKind === 'individual'">
                        <WpAmountInput
                          :model-value="row.balance"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateCell('individualEnd', row.rowId, 'balance', v)"
                          style="width:100%"
                        />
                      </template>
                      <template v-else-if="row.source">
                        <WpAmountInput
                          :model-value="row.balance"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateBadDebtClassFixed('end', row.source, 'balance', v)"
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
                        <WpAmountInput
                          :model-value="row.provision"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateCell('individualEnd', row.rowId, 'provision', v)"
                          style="width:100%"
                        />
                      </template>
                      <template v-else-if="row.source">
                        <WpAmountInput
                          :model-value="row.provision"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateBadDebtClassFixed('end', row.source, 'provision', v)"
                          style="width:100%"
                        />
                      </template>
                      <template v-else><span v-html="fmtAmt(row.provision)" /></template>
                    </template>
                  </el-table-column>
                  <el-table-column label="预期信用损失率(%)" min-width="120" align="right">
                    <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                  </el-table-column>
                  <el-table-column label="账面价值" min-width="130" align="right">
                    <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.bookValue)" /></template>
                  </el-table-column>
                </el-table-column>
                <!-- 底稿多留的审计列：源模板把「计提依据」放在独立的「按单项计提坏账准备的
                     应收票据」表（R63~R68）。单项明细只有一处录入口，故在此就地填写，
                     同步时投影进附注该表的「计提依据」列（分类表仍是 6 列形状）。 -->
                <el-table-column min-width="160">
                  <template #header>
                    <el-tooltip content="对应附注「按单项计提坏账准备的应收票据（期末余额）」表的「计提依据」列" placement="top">
                      <span style="border-bottom:1px dashed #909399;cursor:help">计提依据</span>
                    </el-tooltip>
                  </template>
                  <template #default="{ row }">
                    <el-input
                      v-if="row.rowKind === 'individual'"
                      :model-value="row.basis || ''"
                      size="small"
                      :disabled="isReadonly"
                      placeholder="单项计提依据"
                      @input="(v: string) => updateCell('individualEnd', row.rowId, 'basis', v)"
                    />
                    <span v-else style="color:#c0c4cc">—</span>
                  </template>
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
                <!-- 期间父表头逐字取自源模板 B51:F51 合并单元格；子列名同 R52 -->
                <el-table-column label="上年年末余额" align="center">
                  <el-table-column label="金额" min-width="130" align="right">
                    <template #default="{ row }">
                      <template v-if="row.rowKind === 'summary'"><b v-html="fmtAmt(row.balance)" /></template>
                      <template v-else-if="row.rowKind === 'hint'">-</template>
                      <template v-else-if="row.rowKind === 'individual'">
                        <WpAmountInput
                          :model-value="row.balance"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateCell('individualPrior', row.rowId, 'balance', v)"
                          style="width:100%"
                        />
                      </template>
                      <template v-else-if="row.source">
                        <WpAmountInput
                          :model-value="row.balance"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateBadDebtClassFixed('prior', row.source, 'balance', v)"
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
                        <WpAmountInput
                          :model-value="row.provision"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateCell('individualPrior', row.rowId, 'provision', v)"
                          style="width:100%"
                        />
                      </template>
                      <template v-else-if="row.source">
                        <WpAmountInput
                          :model-value="row.provision"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateBadDebtClassFixed('prior', row.source, 'provision', v)"
                          style="width:100%"
                        />
                      </template>
                      <template v-else><span v-html="fmtAmt(row.provision)" /></template>
                    </template>
                  </el-table-column>
                  <el-table-column label="预期信用损失率(%)" min-width="120" align="right">
                    <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                  </el-table-column>
                  <el-table-column label="账面价值" min-width="130" align="right">
                    <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.bookValue)" /></template>
                  </el-table-column>
                </el-table-column>
                <el-table-column min-width="160">
                  <template #header>
                    <el-tooltip content="对应附注「按单项计提坏账准备的应收票据（续：上年年末余额）」表的「计提依据」列" placement="top">
                      <span style="border-bottom:1px dashed #909399;cursor:help">计提依据</span>
                    </el-tooltip>
                  </template>
                  <template #default="{ row }">
                    <el-input
                      v-if="row.rowKind === 'individual'"
                      :model-value="row.basis || ''"
                      size="small"
                      :disabled="isReadonly"
                      placeholder="单项计提依据"
                      @input="(v: string) => updateCell('individualPrior', row.rowId, 'basis', v)"
                    />
                    <span v-else style="color:#c0c4cc">—</span>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowKind === 'individual'" :icon="Delete" text type="danger" size="small" @click="removeIndividualRow(row.rowId, 'prior')" />
                  </template>
                </el-table-column>
              </el-table>

              <!-- ═══ 按组合计提坏账准备（源模板 R75~R90，双期并列）═══ -->
              <h4 style="margin:16px 0 8px">（4.3）按组合计提坏账准备</h4>
              <div class="portfolio-methodology">
                源模板占位说明：行维度为「出票人类型或账龄」。期末余额与上年年末余额按名称成对对齐，
                新增 / 改名 / 按账龄段生成均同时作用于两期，避免附注侧出现孤儿行。
              </div>
              <template v-for="pf in listedPortfolioBlocks" :key="pf.type">
                <div class="excel-hint">组合计提项目：{{ pf.title }}</div>
                <div class="table-frame" style="margin-bottom:12px">
                  <div v-if="!isReadonly" style="display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap">
                    <el-button size="small" :icon="Plus" @click="onAddPortfolioPair(pf.type)">添加行</el-button>
                    <el-button size="small" type="primary" plain @click="onFillAgingBandsPair(pf.type)">按账龄段生成</el-button>
                    <el-tag size="small" type="info" effect="plain">账龄口径：{{ agingPresetLabel }}（{{ agingBandLabels.join(' / ') }}）</el-tag>
                  </div>
                  <el-table
                    :data="[...pf.rows, portfolioViewTotal(pf.rows)]"
                    border
                    size="small"
                    style="width:100%"
                    :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35', textAlign: 'center' }"
                    :cell-style="{ padding: '3px 6px' }"
                  >
                    <el-table-column label="名称" min-width="200">
                      <template #default="{ row }">
                        <template v-if="row.name === '合计'"><b>{{ row.name }}</b></template>
                        <template v-else>
                          <el-select
                            :model-value="row.name"
                            size="small"
                            filterable
                            allow-create
                            default-first-option
                            style="width:100%"
                            :disabled="isReadonly"
                            placeholder="选择账龄段（可自定义出票人类型）"
                            @change="(v: string) => onRenamePortfolioPair(pf.type, row.name, v || '')"
                          >
                            <el-option v-for="label in agingBandLabels" :key="label" :label="label" :value="label" />
                          </el-select>
                        </template>
                      </template>
                    </el-table-column>
                    <el-table-column label="期末余额" align="center">
                      <el-table-column label="应收票据" min-width="120" align="right">
                        <template #default="{ row }">
                          <template v-if="row.name === '合计'"><b class="amount-cell" v-html="fmtAmt(row.endBalance)" /></template>
                          <template v-else>
                            <WpAmountInput :model-value="row.endBalance" size="small" :disabled="isReadonly || !row.endRowId"
                              @change="(v: number) => updateCell(`portfolio-${pf.type}-end`, row.endRowId, 'balance', v)" style="width:100%" />
                          </template>
                        </template>
                      </el-table-column>
                      <el-table-column label="坏账准备" min-width="120" align="right">
                        <template #default="{ row }">
                          <template v-if="row.name === '合计'"><b class="amount-cell" v-html="fmtAmt(row.endProvision)" /></template>
                          <template v-else>
                            <WpAmountInput :model-value="row.endProvision" size="small" :disabled="isReadonly || !row.endRowId"
                              @change="(v: number) => updateCell(`portfolio-${pf.type}-end`, row.endRowId, 'provision', v)" style="width:100%" />
                          </template>
                        </template>
                      </el-table-column>
                      <el-table-column label="预期信用损失率(%)" min-width="120" align="right">
                        <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.endLossRate) }}</span></template>
                      </el-table-column>
                    </el-table-column>
                    <el-table-column label="上年年末余额" align="center">
                      <el-table-column label="应收票据" min-width="120" align="right">
                        <template #default="{ row }">
                          <template v-if="row.name === '合计'"><b class="amount-cell" v-html="fmtAmt(row.priorBalance)" /></template>
                          <template v-else>
                            <WpAmountInput :model-value="row.priorBalance" size="small" :disabled="isReadonly || !row.priorRowId"
                              @change="(v: number) => updateCell(`portfolio-${pf.type}-prior`, row.priorRowId, 'balance', v)" style="width:100%" />
                          </template>
                        </template>
                      </el-table-column>
                      <el-table-column label="坏账准备" min-width="120" align="right">
                        <template #default="{ row }">
                          <template v-if="row.name === '合计'"><b class="amount-cell" v-html="fmtAmt(row.priorProvision)" /></template>
                          <template v-else>
                            <WpAmountInput :model-value="row.priorProvision" size="small" :disabled="isReadonly || !row.priorRowId"
                              @change="(v: number) => updateCell(`portfolio-${pf.type}-prior`, row.priorRowId, 'provision', v)" style="width:100%" />
                          </template>
                        </template>
                      </el-table-column>
                      <el-table-column label="预期信用损失率(%)" min-width="120" align="right">
                        <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.priorLossRate) }}</span></template>
                      </el-table-column>
                    </el-table-column>
                    <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                      <template #default="{ row }">
                        <el-button v-if="row.name !== '合计'" :icon="Delete" text type="danger" size="small" @click="onRemovePortfolioPair(pf.type, row.name)" />
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </template>
              <div class="portfolio-methodology">
                说明：按组合计提坏账准备的原因请在下方「说明」中填写（源模板 R90）。
                勾稽：本区两张表合计 = 上方分类表「按组合计提坏账准备」行（F4-4 / F4-5）。
              </div>
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
                  <div v-if="!isReadonly" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
                    <el-button size="small" :icon="Plus" @click="onAddMovementDetail">在「其中：」下添加明细行</el-button>
                    <el-tag v-if="hasMovementDetail" size="small" type="success" effect="plain">
                      「按组合计提」行按 {{ movementDetailRows.length }} 条明细汇总（F4-20）
                    </el-tag>
                  </div>
                  <el-table
                    :data="soeMovementRowsForDisplay"
                    row-key="rowId"
                    border
                    size="small"
                    style="width:100%;margin-bottom:12px"
                    :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
                    :cell-style="{ padding: '3px 6px' }"
                  >
                    <el-table-column label="类别" min-width="220">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'detail'">
                          <span style="padding-left:16px;color:#606266">{{ row.label }}</span>
                        </template>
                        <template v-else>
                          <span :style="row.rowKind==='summary'?'font-weight:600':''">{{ row.label }}</span>
                        </template>
                      </template>
                    </el-table-column>
                    <el-table-column label="期初数" min-width="110" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'hint'">-</template>
                        <template v-else-if="row.rowKind === 'summary' || row.readonlyRow">
                          <span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.sourceRow?.priorBalance || 0)" />
                        </template>
                        <template v-else>
                          <WpAmountInput :model-value="row.sourceRow?.priorBalance || 0" size="small" :disabled="isReadonly"
                            @change="(v: number) =>updateCell(row.rowKind === 'detail' ? 'movementDetail' : 'movement', row.sourceRow.rowId, 'priorBalance', v)" style="width:100%" />
                        </template>
                      </template>
                    </el-table-column>
                    <el-table-column label="本期变动情况" align="center">
                      <el-table-column
                        v-for="mc in SOE_MOVEMENT_CHANGE_COLS"
                        :key="mc.field"
                        :label="mc.label"
                        :min-width="mc.width"
                        align="right"
                      >
                        <template #default="{ row }">
                          <template v-if="row.rowKind === 'hint'">-</template>
                          <template v-else-if="row.rowKind === 'summary' || row.readonlyRow">
                            <span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.sourceRow?.[mc.field] || 0)" />
                          </template>
                          <template v-else>
                            <WpAmountInput :model-value="row.sourceRow?.[mc.field] || 0" size="small" :disabled="isReadonly"
                              @change="(v: number) =>updateCell(row.rowKind === 'detail' ? 'movementDetail' : 'movement', row.sourceRow.rowId, mc.field, v)" style="width:100%" />
                          </template>
                        </template>
                      </el-table-column>
                    </el-table-column>
                    <el-table-column min-width="110" align="right">
                      <template #header>
                        <el-tooltip content="期末数 = 期初数 + 计提 − 收回或转回 − 核销 − 其他变动（源模板 G48 公式，F4-7）" placement="top">
                          <span style="border-bottom:1px dashed #909399;cursor:help">期末数</span>
                        </el-tooltip>
                      </template>
                      <template #default="{ row }">
                        <template v-if="row.rowKind === 'hint'">-</template>
                        <template v-else><span :style="row.rowKind==='summary'?'font-weight:600':''" v-html="fmtAmt(row.sourceRow?.endBalance || 0)" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                      <template #default="{ row }">
                        <el-button v-if="row.rowKind === 'detail'" :icon="Delete" text type="danger" size="small" @click="removeMovementDetailRow(row.rowId)" />
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
                        <template v-else><WpAmountInput :model-value="row.amount" size="small" :disabled="isReadonly" @change="(v: number) =>updateCell('reversalDetail', row.rowId, 'amount', v)" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <!-- 源模板 C59==SUM(C55:C58) → 金额列，进合计行 -->
                    <el-table-column label="转回或收回前累计已计提坏账准备金额" min-width="210" align="right">
                      <template #default="{ row }">
                        <template v-if="row.rowType==='summary'"><b class="amount-cell" v-html="fmtAmt(row.cumulativeProvision)" /></template>
                        <template v-else><WpAmountInput :model-value="row.cumulativeProvision" size="small" :disabled="isReadonly" @change="(v: number) =>updateCell('reversalDetail', row.rowId, 'cumulativeProvision', v)" style="width:100%" /></template>
                      </template>
                    </el-table-column>
                    <el-table-column label="转回或收回原因、方式" min-width="180">
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
                        <WpAmountInput
                          :model-value="row.value"
                          size="small"
                          :disabled="isReadonly"
                          :aria-label="`坏账准备金额 ${row.label}`"
                          @change="(v: number) => updateCell('movement', listedMovementRow.rowId, row.key, v)"
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
                  <!-- 逐字取自源模板 D102 / 附注模板 五、4[11] -->
                  <el-table-column label="原确定坏账准备的依据" min-width="170">
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
                        <WpAmountInput
                          :model-value="row.amount"
                          size="small"
                          :disabled="isReadonly"
                          @change="(v: number) => updateCell('reversalDetail', row.rowId, 'amount', v)"
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
              <!-- 源模板 R43/R90「说明：按组合计提坏账准备的原因」→ 需说明文本域 -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['badDebtMovement'] || ''" placeholder="请输入坏账准备变动相关说明（含按组合计提坏账准备的原因、重要转回或收回的原因与方式）..." :disabled="isReadonly" @input="(v: string) => onNoteChange('badDebtMovement', v)" />
                <div class="note-actions">
                  <el-button size="small" :loading="aiLoadingSection === 'badDebtMovement'" :disabled="isReadonly" @click="handleAiGenerate('badDebtMovement')">🤖 AI</el-button>
                  <el-button v-if="openReviewDialog" size="small" @click="handleReview('badDebtMovement')">💬 复核</el-button>
                </div>
              </div>
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
                    <WpAmountInput
                      :model-value="row.amount"
                      size="small"
                      :disabled="isReadonly"
                      @change="(v: number) => updateCell('writeOffAmount', '', 'amount', v)"
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
                <!-- 上市源模板 B111 字面是「应收票据」，预设 F4-29 明确为「应收票据性质」→ 取预设 -->
                <el-table-column :label="variant === 'soe' ? '应收票据的性质' : '应收票据性质'" min-width="120">
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
                      <WpAmountInput
                        :model-value="row.amount"
                        size="small"
                        :disabled="isReadonly"
                        @change="(v: number) => updateCell('writeOffDetail', row.rowId, 'amount', v)"
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
                <!-- 上市源模板 F111「款项是否由关联交易产生」/ 国企 F84「是否由关联交易产生」 -->
                <el-table-column :label="variant === 'soe' ? '是否由关联交易产生' : '款项是否由关联交易产生'" min-width="150">
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
              <!-- 核销证据：源模板要求逐项披露「履行的核销程序」，须留审批与凭证 -->
              <D1SheetAttachments
                :project-id="projectId"
                :wp-id="wpId"
                :sheet-key="`D1-disc-${variant}-writeoff`"
                label="核销证据（核销审批文件 / 履行核销程序的记录）"
              />
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
                <!-- 与上市顶部汇总表共用 MAIN_TABLE_GROUPS（父表头随变体切换），
                     审定表未取数时同样开放手工兜底录入 -->
                <el-table-column
                  v-for="grp in MAIN_TABLE_GROUPS"
                  :key="grp.group"
                  :label="grp.group"
                  align="center"
                >
                  <el-table-column
                    v-for="col in grp.cols"
                    :key="col.field"
                    :label="col.label"
                    min-width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      <template v-if="col.derived || row.rowType === 'summary'">
                        <span class="amount-cell" v-html="fmtAmt(row[col.field])" />
                      </template>
                      <template v-else-if="canEditCategorySummary && !isReadonly">
                        <WpAmountInput
                          :model-value="row[col.field]"
                          size="small"
                          :disabled="isReadonly"
                          :aria-label="`${grp.group} ${col.label} ${row.category}`"
                          @change="(v: number) => updateCell('categorySummary', row.rowId, col.field, v)"
                          style="width:100%"
                        />
                      </template>
                      <template v-else>
                        <el-tooltip content="取自审定表D1-1" placement="top">
                          <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row[col.field])" />
                        </el-tooltip>
                      </template>
                    </template>
                  </el-table-column>
                </el-table-column>
              </el-table>
              <div v-if="canEditCategorySummary" class="portfolio-methodology">
                审定表 D1-1 暂未取到数，本表已开放手工录入（账面价值按「账面余额 − 坏账准备」自动计算）；
                审定表导数后将自动改回以审定表为准并转为只读。
              </div>
              <!-- 国企主表的总体说明与上市顶部汇总表共用 `top` 键（= 应收票据说明） -->
              <div class="section-note">
                <label>说明：</label>
                <details class="guidance-fold">
                  <summary>📋 编制提示</summary>
                  <p v-for="(t, i) in DISCLOSURE_GUIDANCE.top" :key="'soe-top-tip-'+i">{{ t }}</p>
                </details>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['top'] || ''" placeholder="请输入应收票据相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('top', v)" />
                <div class="note-actions">
                  <el-button size="small" :loading="aiLoadingSection === 'top'" :disabled="isReadonly" @click="handleAiGenerate('top')">🤖 AI</el-button>
                  <el-button v-if="openReviewDialog" size="small" @click="handleReview('top')">💬 复核</el-button>
                </div>
              </div>
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
:deep(.negative-amount) {
  color: #f56c6c;
}
/* 源模板红字方法论上下文（琥珀色左边线 + 浅黄背景，平台统一样式） */
.portfolio-methodology {
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  padding: 6px 10px;
  margin: 8px 0;
  font-size: 12px;
  line-height: 1.6;
  color: #7d5a1a;
}
</style>
