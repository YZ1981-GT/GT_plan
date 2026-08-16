<script setup lang="ts">
/**
 * E1TabDisclosure.vue — 附注 (variant: listed/soe)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.18
 *
 * - Props: variant detected from sheetName (includes('上市')→'listed', includes('国企')→'soe')
 * - Listed: project rows × 期末数/期初数, from E1-adj-total-* cross-sheet
 * - SOE: adds "受限制货币资金明细" dynamic table
 * - 提示折叠区 (<details> style)
 * - 说明 textarea (editable, bidirectional)
 * - Dual mode support (el-segmented structured/online-edit)
 * - Storage: 'E1-disclosure-{variant}-*'
 *
 * Requirements: 15.1-15.6
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import {
  buildE1SyncPayload,
  E1_DISCLOSURE_SHEET_NAME,
  E1_NOTE_SECTION,
  type E1DisclosureSnapshot,
} from '../composables/e1NoteSectionMap'
import { buildE1FxSyncPayload, E1_FX_NOTE_SECTION } from '../composables/e1FxNoteSectionMap'
import {
  buildRestrictedAssetsPayloads,
  RESTRICTED_ASSETS_NOTE_SECTION,
  RESTRICTED_ASSETS_OWNERS,
  summarizeRestrictedRows,
} from '../composables/restrictedAssetsNoteSectionMap'
// fail closed 提示文案单一真源（含**为什么**，不只是哪张表）
import { rowScopeFailureMessage } from '../composables/shared/rowScopeFailure'
import {
  E1_DEFAULT_CURRENCIES,
  E1_FX_GROUPS,
  E1_FX_SIMPLE_GROUP_LABEL,
  e1BaseCurrencyLabel,
  e1ForeignCurrencies,
} from '../composables/e1CurrencyScope'
import {
  e1LegacyNoteKey,
  e1MainColumns,
  e1MainRows,
  e1NoteTextKey,
  e1NoteTexts,
  e1SummableRows,
} from '../composables/e1DisclosureScope'
import {
  isE1MainRowDeducted,
  isE1MainRowSlotPrefilled,
  resolveE1MainRowAmount,
} from '../composables/e1MainRowPrefill'
import WpAmountInput from '../shared/WpAmountInput.vue'
import WpDisclosureConsistencyPanel from '../shared/disclosure/WpDisclosureConsistencyPanel.vue'
import {
  buildE1MisstatementPayload,
  computeE1Consistency,
} from '../composables/e1DisclosureConsistency'
import {
  E1_UNRESTRICTED,
  customBucketKey,
  // 稳定序号：持久化单调计数器（禁 length/max+1，见该模块 nextRestrictedSeq 注释）
  e1RestrictedSeqKey,
  nextRestrictedSeq,
  parseRestrictedSeq,
  e1RestrictedMapKey,
  e1RestrictedRowId,
  normalizeRestrictedPrefill,
  parseManualMap,
  pendingUnclassified,
  // 待归类面板分区（R8.4）：父科目行与真明细行语义不同，处理方式也不同
  partitionUnclassified,
  resolveRestrictedRows,
  restrictedTotals,
  serializeManualMap,
  unrestrictedLeaves,
  type E1RestrictedManualMap,
  type E1RestrictedRow,
  // L2：E1-3 逐户受限归集（与 L1 并存，不互相覆盖 —— 见该模块 L2 段注释）
  E1_BANK_DETAIL_ROWS_KEY,
  parseBankDetailRowsForL2,
  summarizeRestrictedFromAccounts,
  buildRestrictedReasonText,
  type E1BankDetailRowLike,
} from '../composables/e1RestrictedScope'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'
import { useAuditContext } from '@/composables/useAuditContext'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { useHostApplicableStandards } from '../composables/hostApplicableStandards'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  variant?: 'listed' | 'soe'
  /**
   * render-config 的 `html_data`（**snake_case**）。
   * 🔴 必须由宿主显式传入 —— 漏传会让 `restricted_prefill` 恒 undefined、
   * 受限资金四表取数静默失效（N2 已踩过同款「宿主漏传 :html-data」）。
   */
  htmlData?: Record<string, any> | null
  /**
   * 适用准则（`soe_standalone` / `listed_consolidated` …）。
   * 决定同步载荷的 `current_standard` —— 漏传会让它永远退化成 `*_standalone`，
   * 合并报表项目的附注被按个别报表口径写入。
   */
  applicableStandards?: string[]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
/**
 * 适用准则：`props.applicableStandards` > 本 sheet 的 `html_data.project_context` > runtime。
 * 🔴 必须在 setup 顶层调用（内部 `inject`）。
 */
const applicableStandards = useHostApplicableStandards({
  explicit: () => props.applicableStandards,
  htmlData: () => props.htmlData,
})

/**
 * 变体适用性门控（Property 14/15）：
 * - 准则列表含本变体前缀 → 适用，渲染录入区
 * - 不含 → 不适用，渲染提示页，三个同步入口全部不写入
 * - 空数组 → fail-open 放行（解析不出不误杀）
 * 只判 entity 维度（listed、soe 前缀），scope 差异（standalone/consolidated）不触发
 * 🔴 本行原写 `listed*` + `/` + `soe*`，其中的 `*` `/` 组合**提前闭合了本块注释**
 *    → 整个 SFC 编译失败（Vite transform 500 / 披露 Tab 在浏览器打不开），
 *    而 `get_diagnostics` 与 vitest 全绿（守卫只把本文件当文本读、不挂载组件）。
 *    平台铁律：JSDoc 里禁写含注释定界符的内容。
 * @spec e1-orphan-components-wiring — Task 10
 */
const variantApplicable = computed<boolean>(() => {
  const list = applicableStandards.value
  if (!list || !list.length) return true // fail-open
  const prefix = (props.variant || 'listed') === 'listed' ? 'listed' : 'soe'
  return list.some((s: string) => String(s).toLowerCase().startsWith(prefix))
})

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)
const router = useRouter()
// 审计年度（单一真源 projectStore），用于同步到附注时定位正确年度的附注记录，
// 避免后端按服务器当前年默认导致同步到错误年度的附注（附注模块显示审计年度记录）。
const { year: auditYear } = useAuditContext()

// 保存后自动同步到附注（防抖/非阻塞/失败静默/只读 gate；与手动按钮同源 syncToDisclosureNotes）
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())
// 🔴 自动同步的 watch 注册在文件末尾（syncToDisclosureNotes 之后）——不能放在这里：
// `<script setup>` 的 const 有 TDZ，watch 的依赖数组在 setup 期即求值，若引用
// disclosureRows / restrictedRows / noteText / variant 这些后面才声明的 const
// 会抛 ReferenceError 导致整个披露 Tab 挂载失败（get_diagnostics 查不出）。
// 守卫：composables/__tests__/e1SetupOrder.spec.ts

// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
// 上市→五、1 / 国企→八、1，可自由切换上市↔国企
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId, 'E1', target)
  if (!route) {
    ElMessage.warning('未找到对应的货币资金附注章节')
    return
  }
  router.push(route)
}

// DisclosureVariant 由 noteDisclosureReverseJump 统一导出（见文件头 import），
// 此处不再本地重复声明，避免同名类型双真源。

const variant = computed<DisclosureVariant>(() => {
  if (props.variant) return props.variant
  const name = props.sheetName || ''
  if (name.includes('国企')) return 'soe'
  return 'listed'
})

const storagePrefix = computed(() => `E1-disclosure-${variant.value}`)

// ─── Project Row Items (Listed) ──────────────────────────────────────────────

interface DisclosureRow {
  key: string
  label: string
  crossKey: string  // allResponses key for 期末
  endingAmount: number
  openingAmount: number
}

// 披露主表行与列头的**单一真源** = composables/e1DisclosureScope.ts
// （行标签逐字取自源 xlsx 并带 sourceRef，供后端守卫做三向比对；
//  改造前此处内联两套 ITEMS，且 overseas 行写的是缩写「其中：存放境外」
//  与源模板/附注的「其中：存放在境外的款项总额」不一致）
//
// 🔴 本表**完全数据驱动**（行集 = 真源数组，合计 = e1SummableRows 按 isTotal/isMemo 判定）
//    ⇒ 真源加/删行无需改本组件；「其中：」备注行两变体走同一条渲染路径，不要另造分支。
//    soe 侧的「其中：存放在境外的款项总额」行（附注 docx 有、底稿源 xlsx 无）已在真源里补齐。
// 🔴 底稿 UI 用**源 xlsx 字面**（soe 首行是 A8 的原字），推送附注时由
//    e1NoteSectionMap.mainRow() 按 noteLabel ?? label 投影成 docx 字面 —— 双口径，
//    别在此处把 label 改成附注字面（会与源模板/导出模板分叉）。
const disclosureItems = computed(() => e1MainRows(variant.value))

const endingLabel = computed(() => e1MainColumns(variant.value).ending)
const openingLabel = computed(() => e1MainColumns(variant.value).opening)
const itemColumnLabel = computed(() => e1MainColumns(variant.value).label)

// 审计目标（按版本）
const objective = computed(() =>
  variant.value === 'soe'
    ? '审计目标：确认货币资金附注披露（含受限资金）完整、准确，与审定表及报表勾稽一致。'
    : '审计目标：确认货币资金附注披露完整、准确，境外及受限款项披露充分，与审定表及报表勾稽一致。',
)

// ─── Cross-Sheet + Opening Data ──────────────────────────────────────────────

const openingMap = ref<Record<string, number>>({})

function loadOpenings(): void {
  const key = `${storagePrefix.value}-openings`
  const resp = props.allResponses.get(key)
  if (resp?.remark) {
    try { openingMap.value = JSON.parse(resp.remark) } catch { openingMap.value = {} }
  }
}
loadOpenings()

// allResponses 的 remark 读取器（供 e1MainRowPrefill 纯函数消费）
const remarkGetter = (key: string): string | null | undefined =>
  props.allResponses.get(key)?.remark

// 单项期末数：审定表跨 sheet 审定数（`E1-adj-total-{code}`）只读取数。
// 🔴 三个无科目码行（finance_co / accrued / digital）走**语义槽键**
//    `E1-adj-slot-{key}`，并从 bank/other_mf 里扣减以避免双算 —— 口径与依据见
//    `composables/e1MainRowPrefill.ts` 文件头（本组件不复现取数逻辑）。
//    取不到值时纯函数返 null，此处按 0 参与合计但由 `endingResolved` 区分「空白 vs 0」。
function effEnding(item: { key: string; crossKey: string }): number {
  return resolveE1MainRowAmount(item, remarkGetter) ?? 0
}
// 单项期初数：手工覆盖优先（openingMap 显式含该 key），否则自动预填审定表期初审定数
// （`E1-adj-total-{code}-opening` 或槽键的 -opening，本年期初=上年年末）。
function effOpening(item: { key: string; crossKey: string }): number {
  if (item.key in openingMap.value) return Number(openingMap.value[item.key]) || 0
  return resolveE1MainRowAmount(item, remarkGetter, 'opening') ?? 0
}
// 某项期初是否自动预填（无手工覆盖且取到了非 0 预填值）——供 UI 标注
function isOpeningPrefilled(item: { key: string; crossKey: string }): boolean {
  if (item.key in openingMap.value) return false
  return (resolveE1MainRowAmount(item, remarkGetter, 'opening') ?? 0) !== 0
}

const disclosureRows = computed<(DisclosureRow & { openingPrefilled: boolean })[]>(() => {
  const items = disclosureItems.value
  return items.map(item => {
    let endingAmount = effEnding(item)
    let openingAmount = effOpening(item)
    // 合计行 = 参与合计的行之和（排除合计行自身与「其中：」备注行，
    // 由 e1SummableRows 按真源的 isTotal/isMemo 判定，不在此处硬编码 key）
    if (item.isTotal) {
      const subs = e1SummableRows(variant.value)
      endingAmount = subs.reduce((sum, i) => sum + effEnding(i), 0)
      openingAmount = subs.reduce((sum, i) => sum + effOpening(i), 0)
    }
    return {
      key: item.key,
      label: item.label,
      crossKey: item.crossKey,
      endingAmount,
      openingAmount,
      openingPrefilled: item.isTotal ? false : isOpeningPrefilled(item),
      // 🔴 「本项目无此科目」与「余额为 0」必须可区分：纯函数返 null 即前者，
      //    此时期末列显示「—」而不是 0.00（Property 35）。合计行恒为已解析。
      endingResolved:
        item.isTotal || resolveE1MainRowAmount(item, remarkGetter) !== null,
      // 该行是否由语义槽预填（供「预填」标记）
      endingSlotPrefilled: isE1MainRowSlotPrefilled(item, remarkGetter),
      // 该行金额是否已扣除单独列示项（供 tooltip 说明，避免用户以为数字错了）
      endingDeducted: isE1MainRowDeducted(item, remarkGetter),
    }
  })
})

// ─── Foreign Currency Tables (简版 / 详细版，两种披露版本共用) ────────────────

type ForeignCurrencyMode = 'simple' | 'detailed'
type ForeignAmountField = 'endForeign' | 'endRate' | 'endRmb' | 'openForeign' | 'openRate' | 'openRmb'

interface ForeignCurrencyRow {
  id: string
  groupId: string
  item: string
  currency: string
  isGroup: boolean
  indent: boolean
  endForeign: number
  endRate: number
  endRmb: number
  openForeign: number
  openRate: number
  openRmb: number
}

// 币种与外币分组的**单一真源** = composables/e1CurrencyScope.ts
// （改造前此处内联三份常量，违反「避免硬编码」铁律；E 类无账龄维度，
//  币种与受限类别就是本循环对应的枚举维度）
const BASE_CURRENCY_LABEL = e1BaseCurrencyLabel()
/** 简版：只列外币（源模板 R25「外币性货币项目」派生表不含记账本位币） */
const SIMPLE_CURRENCIES = e1ForeignCurrencies().map((c) => c.label)
/** 详细版：源模板 R35 原币表逐币种列示（含记账本位币） */
const DETAILED_CURRENCIES = E1_DEFAULT_CURRENCIES.map((c) => c.label)
/** 详细版分组 = 源模板 R38/R44/R50/R56 四段 */
const DETAILED_PROJECTS = E1_FX_GROUPS.map((g) => g.label)

function createCurrencyRow(groupId: string, currency: string, suffix: string): ForeignCurrencyRow {
  const isRmb = currency === BASE_CURRENCY_LABEL
  return {
    id: `fc-currency-${suffix}`,
    groupId,
    item: currency,
    currency,
    isGroup: false,
    indent: true,
    endForeign: 0,
    endRate: isRmb ? 1 : 0,
    endRmb: 0,
    openForeign: 0,
    openRate: isRmb ? 1 : 0,
    openRmb: 0,
  }
}

function createDefaultForeignRows(mode: ForeignCurrencyMode): ForeignCurrencyRow[] {
  const stamp = Date.now()
  const projects = mode === 'detailed' ? DETAILED_PROJECTS : [E1_FX_SIMPLE_GROUP_LABEL]
  const currencies = mode === 'detailed' ? DETAILED_CURRENCIES : SIMPLE_CURRENCIES
  return projects.flatMap((item, projectIndex) => {
    const groupId = `fc-group-${mode}-${stamp}-${projectIndex}`
    const group: ForeignCurrencyRow = {
      id: groupId,
      groupId,
      item: `${item}：`,
      currency: '',
      isGroup: true,
      indent: false,
      endForeign: 0,
      endRate: 0,
      endRmb: 0,
      openForeign: 0,
      openRate: 0,
      openRmb: 0,
    }
    return [group, ...currencies.map((currency, currencyIndex) =>
      createCurrencyRow(groupId, currency, `${mode}-${stamp}-${projectIndex}-${currencyIndex}`))]
  })
}

// 默认「详细版」：源模板「附注披露信息(上市公司)」外币表即按 库存现金/银行存款/
// 银行存款中：财务公司存款/其他货币资金 × 人民币/美元/日元/澳元/欧元 逐项列示。
const foreignCurrencyMode = ref<ForeignCurrencyMode>('detailed')
const simpleForeignCurrencyRows = ref<ForeignCurrencyRow[]>([])
const detailedForeignCurrencyRows = ref<ForeignCurrencyRow[]>([])
const foreignCurrencyRows = computed(() =>
  foreignCurrencyMode.value === 'detailed' ? detailedForeignCurrencyRows.value : simpleForeignCurrencyRows.value,
)

function normalizeForeignRows(rows: any[]): ForeignCurrencyRow[] {
  let currentGroupId = ''
  return rows.map((raw: any, index: number) => {
    const isGroup = !!raw.isGroup
    const id = String(raw.id || `fc-migrated-${Date.now()}-${index}`)
    if (isGroup) currentGroupId = id
    const currency = isGroup ? '' : String(raw.currency || raw.item || '').replace(/^其中[：:]?/, '').trim()
    const groupId = isGroup ? id : String(raw.groupId || currentGroupId)
    const endForeign = Number(raw.endForeign) || 0
    const endRate = Number(raw.endRate) || 0
    const openForeign = Number(raw.openForeign) || 0
    const openRate = Number(raw.openRate) || 0
    return {
      id,
      groupId,
      item: isGroup ? String(raw.item || `${E1_FX_SIMPLE_GROUP_LABEL}：`) : currency,
      currency,
      isGroup,
      indent: !isGroup,
      endForeign,
      endRate,
      endRmb: endForeign * endRate,
      openForeign,
      openRate,
      openRmb: openForeign * openRate,
    }
  })
}

function loadForeignCurrency(): void {
  foreignCurrencyMode.value = 'detailed'
  simpleForeignCurrencyRows.value = createDefaultForeignRows('simple')
  detailedForeignCurrencyRows.value = createDefaultForeignRows('detailed')
  const resp = props.allResponses.get(`${storagePrefix.value}-foreign-currency`)
  if (!resp?.remark) return
  try {
    const parsed = JSON.parse(resp.remark)
    // 兼容已保存的旧数组结构：旧数据即上市公司简版。
    if (Array.isArray(parsed) && parsed.length > 0) {
      simpleForeignCurrencyRows.value = normalizeForeignRows(parsed)
      return
    }
    if (parsed && typeof parsed === 'object') {
      foreignCurrencyMode.value = parsed.mode === 'detailed' ? 'detailed' : 'simple'
      if (Array.isArray(parsed.simpleRows) && parsed.simpleRows.length > 0) {
        simpleForeignCurrencyRows.value = normalizeForeignRows(parsed.simpleRows)
      }
      if (Array.isArray(parsed.detailedRows) && parsed.detailedRows.length > 0) {
        detailedForeignCurrencyRows.value = normalizeForeignRows(parsed.detailedRows)
      }
    }
  } catch {}
}
loadForeignCurrency()

function setActiveForeignRows(rows: ForeignCurrencyRow[]): void {
  if (foreignCurrencyMode.value === 'detailed') detailedForeignCurrencyRows.value = rows
  else simpleForeignCurrencyRows.value = rows
}

function updateForeignMode(mode: ForeignCurrencyMode): void {
  if (props.isReadonly) return
  foreignCurrencyMode.value = mode
  scheduleSave()
}

function updateFcCell(id: string, field: ForeignAmountField, value: number): void {
  if (props.isReadonly) return
  const rows = foreignCurrencyRows.value
  const idx = rows.findIndex(row => row.id === id)
  if (idx < 0 || rows[idx].isGroup) return
  const row = { ...rows[idx], [field]: Number(value) || 0 }
  row.endRmb = row.endForeign * row.endRate
  row.openRmb = row.openForeign * row.openRate
  setActiveForeignRows([...rows.slice(0, idx), row, ...rows.slice(idx + 1)])
  scheduleSave()
}

function groupRmb(row: ForeignCurrencyRow, field: 'endRmb' | 'openRmb'): number {
  return foreignCurrencyRows.value
    .filter(item => !item.isGroup && item.groupId === row.id)
    .reduce((sum, item) => sum + item[field], 0)
}

// 合计行：按列序号汇总叶子行（嵌套表头列无 prop，故按 index 映射；折算率列不合计）。
// 列序：0项目 1期末原币 2期末折算率 3期末人民币 4期初原币 5期初折算率 6期初人民币
const FC_SUMMARY_FIELD_BY_INDEX: Record<number, ForeignAmountField> = {
  1: 'endForeign', 3: 'endRmb', 4: 'openForeign', 6: 'openRmb',
}
function foreignCurrencySummary({ columns }: any): string[] {
  const leafRows = foreignCurrencyRows.value.filter(row => !row.isGroup)
  return columns.map((_column: any, index: number) => {
    if (index === 0) return '合 计'
    const field = FC_SUMMARY_FIELD_BY_INDEX[index]
    if (!field) return ''
    const total = leafRows.reduce((sum, row) => sum + (Number(row[field]) || 0), 0)
    return total ? displayPrefs.fmtAmount(total) : '-'
  })
}

function isPromptCancel(error: unknown): boolean {
  return error === 'cancel' || error === 'close' || ['cancel', 'close'].includes(String((error as any)?.action || ''))
}

async function addFcProject(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新增外币性货币资金项目名称', '新增项目', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputValidator: input => input.trim() ? true : '项目名称不能为空',
    })
    const item = value.trim().replace(/[：:]$/, '')
    const groupId = `fc-group-custom-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    setActiveForeignRows([...foreignCurrencyRows.value, {
      id: groupId,
      groupId,
      item: `${item}：`,
      currency: '',
      isGroup: true,
      indent: false,
      endForeign: 0,
      endRate: 0,
      endRmb: 0,
      openForeign: 0,
      openRate: 0,
      openRmb: 0,
    }])
    scheduleSave()
  } catch (error) {
    if (!isPromptCancel(error)) ElMessage.error('新增项目失败')
  }
}

async function addFcCurrency(groupId: string): Promise<void> {
  if (props.isReadonly) return
  const project = foreignCurrencyRows.value.find(row => row.id === groupId && row.isGroup)
  if (!project) return
  try {
    const { value } = await ElMessageBox.prompt(`请输入“${project.item.replace(/[：:]$/, '')}”下的币种名称`, '新增币种', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputValidator: input => {
        const currency = input.trim()
        if (!currency) return '币种名称不能为空'
        if (foreignCurrencyRows.value.some(row => !row.isGroup && row.groupId === groupId && row.currency === currency)) {
          return '该项目下已存在同名币种'
        }
        return true
      },
    })
    const currency = value.trim()
    const groupIndex = foreignCurrencyRows.value.findIndex(row => row.id === groupId)
    let insertIndex = groupIndex + 1
    while (insertIndex < foreignCurrencyRows.value.length && !foreignCurrencyRows.value[insertIndex].isGroup) insertIndex += 1
    const newRow = createCurrencyRow(groupId, currency, `custom-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`)
    setActiveForeignRows([
      ...foreignCurrencyRows.value.slice(0, insertIndex),
      newRow,
      ...foreignCurrencyRows.value.slice(insertIndex),
    ])
    scheduleSave()
  } catch (error) {
    if (!isPromptCancel(error)) ElMessage.error('新增币种失败')
  }
}

function removeFcRow(row: ForeignCurrencyRow): void {
  if (props.isReadonly) return
  setActiveForeignRows(foreignCurrencyRows.value.filter(item =>
    row.isGroup ? item.id !== row.id && item.groupId !== row.id : item.id !== row.id,
  ))
  scheduleSave()
}

// ─── ② 受限制的货币资金明细（两变体共用）─────────────────────────────────────
//
// 用户裁决（2026-08-01）：上市侧**也要**这张表 —— 源 xlsx 上市披露 sheet 只有
// R18/R19 文字，但校验预设 listed 侧的 F1-4/F1-5/F1-6 三条明确引用「②受限制的
// 货币资金明细表」，其中 F1-5/F1-6 是与现金流量表补充资料③表的跨科目勾稽
// （只有表格化才能自动校验）→ 按平台铁律「校验预设是列结构裁决者」补建。
//
// 🔴 取数是**动态**的：受限资金没有独立标准科目，客户各自用二级/三级子科目承载、
// 命名千差万别 → 后端按 BS-002 映射规则取货币资金三族叶子，逐叶子按科目名分类；
// 判不出来的落「待归类」面板交审计师点选，**既不静默丢弃也不臆造归属**。
// 单一真源：composables/e1RestrictedScope.ts + four_table/e1_restricted_buckets.py

/** render 下发的受限取数载荷（扁平叶子清单 + 自动分类标记 + 桶定义） */
const restrictedPrefill = computed(() =>
  normalizeRestrictedPrefill(props.htmlData?.restricted_prefill),
)

/** 人工归类 map：原始科目码 → bucketKey | '__unrestricted__' */
const restrictedManualMap = ref<E1RestrictedManualMap>({})
/** 已持久化的行（保留审计师录入的受限原因与纯手工行） */
const restrictedPersisted = ref<E1RestrictedRow[]>([])

/**
 * 自定义受限类别的**持久化单调计数器**（Property 28）。
 *
 * 🔴 不能用 `rows.length` 或「现有最大 seq + 1」—— 删掉某自定义类别再新增会**复用**
 * 已删序号，历史 cell/备注（按 row id 索引）会串到新类别上。判据见
 * `e1RestrictedScope.nextRestrictedSeq`。
 */
const restrictedSeq = ref(0)

function loadRestricted(): void {
  restrictedManualMap.value = parseManualMap(
    props.allResponses.get(e1RestrictedMapKey(variant.value))?.remark,
  )
  // 单调计数器：读回上次的最大序号（缺省 0）。不由行集派生 —— 行集里删掉的序号
  // 正是不能复用的那些（Property 28）。
  restrictedSeq.value = parseRestrictedSeq(
    props.allResponses.get(e1RestrictedSeqKey(variant.value))?.remark,
  )
  const resp = props.allResponses.get(`${storagePrefix.value}-restricted`)
  if (!resp?.remark) {
    restrictedPersisted.value = []
    return
  }
  try {
    const parsed = JSON.parse(resp.remark)
    if (!Array.isArray(parsed)) {
      restrictedPersisted.value = []
      return
    }
    restrictedPersisted.value = parsed.map((r: any, i: number) => ({
      // 兼容旧结构：旧版是 {id,item,openingAmount,endingAmount,reason}，
      // 无 bucketKey → 按 item 名建自定义类别（不丢审计师已录入的数据）
      id: String(r.id || e1RestrictedRowId(String(r.bucketKey || 'legacy'), i)),
      bucketKey: String(r.bucketKey || customBucketKey(String(r.item || ''))),
      label: String(r.label || r.item || ''),
      openingAmount: Number(r.openingAmount) || 0,
      // 更旧的结构只有 amount，迁移时视为期末金额
      endingAmount: Number(r.endingAmount ?? r.amount) || 0,
      reason: String(r.reason || ''),
      codes: Array.isArray(r.codes) ? r.codes.map((c: unknown) => String(c)) : [],
      fromFourTable: !!r.fromFourTable,
    }))
  } catch {
    restrictedPersisted.value = []
  }
}
loadRestricted()

/** ②表行 = 四表自动分类 ⊕ 人工归类 ⊕ 纯手工行（读时推导，不持久化派生值） */
const restrictedRows = computed<E1RestrictedRow[]>(() =>
  resolveRestrictedRows({
    prefill: restrictedPrefill.value,
    manualMap: restrictedManualMap.value,
    existingRows: restrictedPersisted.value,
  }),
)

/** 仍待归类的叶子（四表新增科目自动出现在这里） */
const restrictedPending = computed(() =>
  pendingUnclassified(restrictedPrefill.value, restrictedManualMap.value),
)

/**
 * 待归类叶子按「无子科目明细的父科目行 / 真明细行」分区（R8.4）。
 *
 * 两类语义完全不同、审计师的处理动作也不同（父科目行说明该科目未分户 ⇒ 通常整体
 * 判「不受限」或走 E1-3 逐户口径 L2；真明细行才逐个归类），故分两张表展示而不是
 * 混在一起。判据在 `e1RestrictedScope.partitionUnclassified`（只看码形态不看金额）。
 *
 * 🔴 两区都渲染、不隐藏任一侧 —— 隐藏父科目行会让「该科目未分户」这一事实消失，
 *    审计师看不到就不会去 E1-3 填逐户受限金额（L2 链路的入口）。
 */
const restrictedPendingParts = computed(() => partitionUnclassified(restrictedPending.value))

/** 被标「不受限」的叶子（金额进 F1-5/F1-6 勾稽差额侧，不隐藏） */
const restrictedExcluded = computed(() =>
  unrestrictedLeaves(restrictedPrefill.value, restrictedManualMap.value),
)

/** ②表合计（源 xlsx R23「合  计」；校验预设 F1-4 要求合计 = 明细之和） */
const restrictedTotal = computed(() => restrictedTotals(restrictedRows.value))

// ─── L2：E1-3 逐户受限归集（源模板 SUMIF 口径）────────────────────────────────
//
// 🔴 与上面的 L1（四表叶子按科目名分类）是**两条并存链路**，代码里不得出现
//    「取其一覆盖另一」的分支 —— 判据与依据见 e1RestrictedScope 的 L2 段注释。
//    数据源是审计师在 E1-3 手填的 AJ/AK 列（`restrictedAmount`/`restrictedReason`），
//    不是账户级取数（tb_aux_balance 没有受限金额字段）。
const bankDetailRowsForL2 = computed<E1BankDetailRowLike[]>(() =>
  parseBankDetailRowsForL2(props.allResponses.get(E1_BANK_DETAIL_ROWS_KEY)?.remark),
)

/** L2 归集结果（无受限行时 `rows` 为空、合计为 null → 勾稽 skip 而非误报）。 */
const restrictedL2 = computed(() =>
  summarizeRestrictedFromAccounts(
    bankDetailRowsForL2.value,
    restrictedPrefill.value.bucketDefs,
  ),
)

// ─── 披露内部勾稽（规则全部取自校验预设 F1-1~F1-6 + 源 xlsx 表内公式）──────────

/** 报表「货币资金」四表口径金额（render 下发 `tb_values`，拿不到则 null 不误报） */
const tbValues = computed<Record<string, number>>(
  () => (props.htmlData?.tb_values as Record<string, number>) || {},
)

const consistencyResults = computed(() =>
  computeE1Consistency({
    variant: variant.value,
    mainRows: disclosureRows.value.map((r) => {
      const def = disclosureItems.value.find((d) => d.key === r.key)
      return {
        key: r.key,
        label: r.label,
        endingAmount: r.endingAmount,
        openingAmount: r.openingAmount,
        isTotal: def?.isTotal,
        isMemo: def?.isMemo,
      }
    }),
    restrictedRows: restrictedRows.value.map((r) => ({
      label: r.label,
      endingAmount: r.endingAmount,
      openingAmount: r.openingAmount,
    })),
    reportEnding: Number.isFinite(tbValues.value.total_closing)
      ? tbValues.value.total_closing
      : null,
    reportOpening: Number.isFinite(tbValues.value.total_opening)
      ? tbValues.value.total_opening
      : null,
    // L2（E1-3 逐户）受限合计 —— 两条链路并存，不等时 warning 交审计判断
    restrictedL2Ending: restrictedL2.value.ending,
    restrictedL2Opening: restrictedL2.value.opening,
    // 外币原币表**两变体都有**（源 xlsx 逐格实证 R25~R62 逐字相同）。
    //
    // 🔴 纠正一处早先的误判：曾把 `fxRows` 限定为上市变体，理由写成「国企版没有
    // 这两张表」。真因不是源模板缺表，而是**本组件把外币区 `v-if` 到了上市变体**
    // → 国企 Tab 拿到的是未渲染的默认骨架（金额全 0）→ 源模板 B16「主表合计 =
    // 原币表人民币合计」拿 0 比主表，产出假「不一致」。根因已修（外币区两变体都渲染），
    // 故这里恢复两变体都传。国企的对应勾稽单元格是 R12 列 E
    // `=B12-'附注披露信息(上市公司)'!D62`，口径同为「主表合计 − 原币表人民币合计」。
    fxRows: foreignCurrencyRows.value.map((r) => ({
      groupSlot: r.groupId,
      currencyKey: r.currency,
      currencyLabel: r.item,
      isGroup: r.isGroup,
      endRmb: r.isGroup ? groupRmb(r, 'endRmb') : r.endRmb,
      endForeign: r.endForeign,
    })),
    // 现金及现金等价物在现金流量表补充资料③表，E1 披露表拿不到 → 传 null，
    // 引擎会 skip 并给出推算值供人工核对（不伪造）
    cashEquivalentsEnding: null,
    cashEquivalentsOpening: null,
  }),
)

/** 勾稽差异（error 级）→ A13 未更正错报汇总。skip（跨底稿取数未就绪）不推。 */
const consistencyErrorCount = computed(
  () => consistencyResults.value.filter((r) => r.level === 'error').length,
)

function pushConsistencyToA13(): void {
  const payload = buildE1MisstatementPayload(consistencyResults.value)
  if (!payload) {
    ElMessage.info('当前无超出容差的勾稽差异，无需推送错报')
    return
  }
  eventBus.emit('a13:push-misstatement', payload)
  ElMessage.success(`已推送 ${payload.items.length} 项勾稽差异到 A13 未更正错报汇总`)
}

/** 模板里用的「不受限」哨兵值（模板不能直接引 import 的常量名以外的标识） */
const E1_UNRESTRICTED_KEY = E1_UNRESTRICTED

/** 桶下拉选项（中文标签只来自后端 bucketDefs，前端不抄第二份） */
const restrictedBucketOptions = computed(() =>
  restrictedPrefill.value.bucketDefs.map((d) => ({ value: d.key, label: d.label })),
)

/** 把某叶子归入某类别 / 标记不受限（人工归类优先于自动分类） */
function assignRestricted(code: string, target: string): void {
  if (props.isReadonly || !code || !target) return
  restrictedManualMap.value = { ...restrictedManualMap.value, [code]: target }
  scheduleSave()
}

/** 撤销人工归类（回到自动分类结果 / 回到待归类） */
function resetRestrictedAssignment(code: string): void {
  if (props.isReadonly) return
  const next = { ...restrictedManualMap.value }
  delete next[code]
  restrictedManualMap.value = next
  scheduleSave()
}

/** 新建自定义受限类别（源 xlsx R22 的 `…` 即动态插行语义，须先输名称） */
async function addRestrictedRow(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入受限制货币资金项目名称', '新增受限项目', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputValidator: (input) => {
        const name = String(input || '').trim()
        if (!name) return '项目名称不能为空'
        if (restrictedRows.value.some((r) => r.label === name)) return '已存在同名类别'
        return true
      },
    })
    const name = value.trim()
    const bucketKey = customBucketKey(name)
    // 🔴 序号取**持久化单调计数器**而不是 `length` / `max+1` ——
    //    删掉 custom_保证金_3 再新增，`length`/`max+1` 都会又给 `_3`，
    //    历史 cell 与备注（按 row id 索引）会串到新类别上（Property 28）。
    //    判据与依据见 e1RestrictedScope 的 `nextRestrictedSeq`。
    const seq = nextRestrictedSeq(
      restrictedRows.value,
      props.allResponses.get(e1RestrictedSeqKey(variant.value))?.remark,
    )
    restrictedSeq.value = seq
    restrictedPersisted.value = [
      ...restrictedPersisted.value,
      {
        id: e1RestrictedRowId(bucketKey, seq),
        bucketKey,
        label: name,
        openingAmount: 0,
        endingAmount: 0,
        reason: '',
        codes: [],
        fromFourTable: false,
      },
    ]
    scheduleSave()
  } catch (error) {
    if (!isPromptCancel(error)) ElMessage.error('新增受限项目失败')
  }
}

function removeRestrictedRow(id: string): void {
  if (props.isReadonly) return
  const row = restrictedRows.value.find((r) => r.id === id)
  if (!row) return
  // 四表命中行不能直接删（它由叶子归集而来）→ 引导改用「标记不受限」
  if (row.fromFourTable) {
    ElMessage.warning('该行由四表科目归集而来，请在「待归类科目」面板把相关科目标记为不受限')
    return
  }
  restrictedPersisted.value = restrictedPersisted.value.filter((r) => r.bucketKey !== row.bucketKey)
  scheduleSave()
}

/** 更新某行的手工字段（受限原因；纯手工行还可改金额） */
function updateRestrictedCell(
  id: string,
  field: 'reason' | 'openingAmount' | 'endingAmount',
  value: string | number,
): void {
  if (props.isReadonly) return
  const row = restrictedRows.value.find((r) => r.id === id)
  if (!row) return
  if (field !== 'reason' && row.fromFourTable) return // 四表金额只读
  const idx = restrictedPersisted.value.findIndex((r) => r.bucketKey === row.bucketKey)
  const base: E1RestrictedRow =
    idx >= 0 ? { ...restrictedPersisted.value[idx] } : { ...row }
  if (field === 'reason') base.reason = String(value)
  else base[field] = Number(value) || 0
  restrictedPersisted.value =
    idx >= 0
      ? [
          ...restrictedPersisted.value.slice(0, idx),
          base,
          ...restrictedPersisted.value.slice(idx + 1),
        ]
      : [...restrictedPersisted.value, base]
  scheduleSave()
}

function restrictedSummary(): string[] {
  return [
    '合  计',
    displayPrefs.fmtAmount(restrictedTotal.value.opening),
    displayPrefs.fmtAmount(restrictedTotal.value.ending),
    '',
    '',
  ]
}

// ─── Note Text ───────────────────────────────────────────────────────────────

/**
 * 披露说明**按源模板分段**（上市 2 段 / 国企 2 段，定义见 e1DisclosureScope）。
 * 改造前是单一 `noteText` 输入框 → 附注 `text_content` 只能拿到一段。
 */
const noteTexts = ref<Record<string, string>>({})

/** 当前变体的段定义 */
const noteTextDefs = computed(() => e1NoteTexts(variant.value))

function loadNote(): void {
  const next: Record<string, string> = {}
  let anyNew = false
  for (const def of e1NoteTexts(variant.value)) {
    const v = props.allResponses.get(e1NoteTextKey(variant.value, def.key))?.remark || ''
    next[def.key] = v
    if (v) anyNew = true
  }
  // 迁移：旧版单一说明框的内容承接到首段（受限及境外款项说明），不丢已写的字
  if (!anyNew) {
    const legacy = props.allResponses.get(e1LegacyNoteKey(variant.value))?.remark || ''
    const first = e1NoteTexts(variant.value)[0]
    if (legacy && first) next[first.key] = legacy
  }
  noteTexts.value = next
}
loadNote()

// ─── 审计说明 / 审计结论（按版本分别存储） ────────────────────────────────────

const auditNote = ref('')
const auditConclusion = ref('')

function loadAuditText(): void {
  auditNote.value = props.allResponses.get(`${storagePrefix.value}-audit-note`)?.remark || ''
  auditConclusion.value = props.allResponses.get(`${storagePrefix.value}-audit-conclusion`)?.remark || ''
}
loadAuditText()

// 版本切换时重新载入全部数据（sheetName 变更场景）
watch(variant, () => {
  loadOpenings()
  loadNote()
  loadAuditText()
  loadForeignCurrency()
  loadRestricted()
})

// ─── Debounce Save ───────────────────────────────────────────────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { saveTimer = null; persistAll() }, 2000)
}

function persistAll(): void {
  const items: any[] = []
  // Openings
  const openingsKey = `${storagePrefix.value}-openings`
  const openingsJson = JSON.stringify(openingMap.value)
  items.push({ item_id: openingsKey, conclusion: null, remark: openingsJson })
  props.allResponses.set(openingsKey, items[items.length - 1])

  // 披露说明（按源模板分段，逐段独立持久化）
  for (const def of noteTextDefs.value) {
    const k = e1NoteTextKey(variant.value, def.key)
    items.push({ item_id: k, conclusion: null, remark: noteTexts.value[def.key] || '' })
    props.allResponses.set(k, items[items.length - 1])
  }

  // 审计说明
  const auditNoteKey = `${storagePrefix.value}-audit-note`
  items.push({ item_id: auditNoteKey, conclusion: null, remark: auditNote.value })
  props.allResponses.set(auditNoteKey, items[items.length - 1])

  // 审计结论
  const auditConcKey = `${storagePrefix.value}-audit-conclusion`
  items.push({ item_id: auditConcKey, conclusion: null, remark: auditConclusion.value })
  props.allResponses.set(auditConcKey, items[items.length - 1])

  // ② 受限制的货币资金明细（**两变体都存** —— 用户裁决上市侧也建该表）
  // 🔴 只持久化「手工侧」数据：受限原因 + 纯手工行的金额。四表命中行的金额是
  // 读时由叶子归集而来的派生值，不落库（平台铁律：派生列读时推导）。
  const rKey = `${storagePrefix.value}-restricted`
  const rJson = JSON.stringify(
    restrictedRows.value
      .filter(row => row.reason || !row.fromFourTable)
      .map(row => ({
        id: row.id,
        bucketKey: row.bucketKey,
        label: row.label,
        openingAmount: row.fromFourTable ? 0 : row.openingAmount,
        endingAmount: row.fromFourTable ? 0 : row.endingAmount,
        reason: row.reason,
        codes: row.fromFourTable ? [] : row.codes,
        fromFourTable: row.fromFourTable,
      })),
  )
  items.push({ item_id: rKey, conclusion: null, remark: rJson })
  props.allResponses.set(rKey, items[items.length - 1])

  // 🔴 自定义类别的**单调计数器**必须与行一起落库 —— 只存在内存里的话，
  //    刷新后 `nextRestrictedSeq` 拿不到已存计数器就退回「现有最大 + 1」，
  //    删掉末尾类别再新增又会复用旧序号（Property 28 要防的正是这条）。
  const seqKey = e1RestrictedSeqKey(variant.value)
  items.push({ item_id: seqKey, conclusion: null, remark: String(restrictedSeq.value) })
  props.allResponses.set(seqKey, items[items.length - 1])

  // 人工归类 map（叶子科目码 → 类别 / 不受限）——「各项目科目命名不同」的关键状态
  const mapKey = e1RestrictedMapKey(variant.value)
  items.push({
    item_id: mapKey,
    conclusion: null,
    remark: serializeManualMap(restrictedManualMap.value),
  })
  props.allResponses.set(mapKey, items[items.length - 1])

  // 上市与国企分别保存简版、详细版及当前模式。
  const fcKey = `${storagePrefix.value}-foreign-currency`
  const serializeForeignRows = (rows: ForeignCurrencyRow[]) => rows.map(row => ({
    id: row.id,
    groupId: row.groupId,
    item: row.item,
    currency: row.currency,
    isGroup: row.isGroup,
    indent: row.indent,
    endForeign: row.endForeign,
    endRate: row.endRate,
    openForeign: row.openForeign,
    openRate: row.openRate,
  }))
  const fcJson = JSON.stringify({
    mode: foreignCurrencyMode.value,
    simpleRows: serializeForeignRows(simpleForeignCurrencyRows.value),
    detailedRows: serializeForeignRows(detailedForeignCurrencyRows.value),
  })
  items.push({ item_id: fcKey, conclusion: null, remark: fcJson })
  props.allResponses.set(fcKey, items[items.length - 1])

  props.saveImmediate(items).catch(() => {})
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateOpening(key: string, val: number): void {
  if (props.isReadonly) return
  openingMap.value = { ...openingMap.value, [key]: val }
  scheduleSave()
}

function updateNote(sectionKey: string, val: string): void {
  if (props.isReadonly) return
  noteTexts.value = { ...noteTexts.value, [sectionKey]: val }
  scheduleSave()
}

/** 某段披露说明的 AI 生成（prompt 取自段定义，含口径与「不得虚构」约束）。 */
async function generateNoteText(def: { key: string; title: string; aiPrompt: string }): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: `e1-disclosure-${variant.value}-note-${def.key}`,
    prompt: def.aiPrompt,
    context: buildAiContext(),
    existingContent: noteTexts.value[def.key] || '',
    confirmTitle: `AI生成${def.title}`,
  })
  if (text) updateNote(def.key, text)
}

function updateAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  scheduleSave()
}

function updateAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  scheduleSave()
}

function buildAiContext(): Record<string, unknown> {
  return {
    披露版本: variant.value === 'soe' ? '国企' : '上市公司',
    货币资金披露: disclosureRows.value.map(row => ({
      项目: row.label,
      期末金额: row.endingAmount,
      期初金额: row.openingAmount,
    })),
    外币项目模式: foreignCurrencyMode.value === 'detailed' ? '详细版' : '简版',
    外币项目: foreignCurrencyRows.value.map(row => row.isGroup ? {
      项目: row.item,
      期末人民币金额: groupRmb(row, 'endRmb'),
      期初人民币金额: groupRmb(row, 'openRmb'),
    } : {
      项目: row.item,
      期末原币: row.endForeign,
      期末折算率: row.endRate,
      期末人民币: row.endRmb,
      期初原币: row.openForeign,
      期初折算率: row.openRate,
      期初人民币: row.openRmb,
    }),
    // ②表两变体都有（用户裁决）；只给类别/金额/原因，不给内部 key
    受限资金: restrictedRows.value.map(r => ({
      项目: r.label,
      期末金额: r.endingAmount,
      期初金额: r.openingAmount,
      受限原因: r.reason,
      来源科目: r.codes.join('、'),
    })),
    受限资金合计: restrictedTotal.value,
    待归类科目: restrictedPending.value.map(l => ({ 科目: `${l.code} ${l.name}`, 期末: l.closing })),
    附注说明: Object.fromEntries(
      noteTextDefs.value.map(d => [d.title, noteTexts.value[d.key] || '']),
    ),
  }
}

async function generateAuditText(kind: 'note' | 'conclusion'): Promise<void> {
  if (props.isReadonly) return
  const isNote = kind === 'note'
  const section = `e1-disclosure-${variant.value}-${kind}`
  const text = await generateText({
    section,
    prompt: isNote
      ? '根据货币资金披露主表、外币折算和受限资金数据生成审计说明。说明与E1-1勾稽、期初核对、汇率来源及受限或境外款项核查情况；仅使用已提供事实，对缺少证据的事项明确标注待核实，不得虚构审计程序或证据。'
      : '根据已提供的货币资金披露、外币和受限资金数据形成审计结论。区分核对一致、存在待跟进事项或披露需更正的情形；不得虚构已取得证据或已完成程序。',
    context: buildAiContext(),
    existingContent: isNote ? auditNote.value : auditConclusion.value,
    confirmTitle: `AI生成${isNote ? '审计说明' : '审计结论'}`,
  })
  if (!text) return
  if (isNote) updateAuditNote(text)
  else updateAuditConclusion(text)
}

// ─── 同步到附注（结构化表格 + 文本框内容 → 附注 五、1/八、1「货币资金」）──────────
// 保证附注模块表格与文本与披露表保持一致（单向推送，走 sync_from_workpaper）。
const isSyncing = ref(false)

/**
 * 外币货币性项目 → 附注 `五、73`/`八、92` 的**第二个 payload**（K6 国企侧范式）。
 *
 * 🔴 该附注表是**跨循环共享表**（货币资金/应收账款/短期借款/长期借款/应付债券 各一段），
 * 故载荷带 `_row_scope` 走平台级**行级合并** —— 只替换货币资金段（`BS-002`），
 * 段外行由服务端原样保留。段边界解析不出时服务端 fail closed 整表跳过。
 *
 * 无外币明细（或默认骨架全零）时 `buildE1FxSyncPayload` 返回 null → 不推
 * （空推送会把段恢复成模板骨架，等于清掉审计师在附注模块手填的货币资金段）。
 * 失败静默：外币段是附加推送，不能让它的失败盖掉主章节「已同步」的提示。
 */
async function syncFxSectionToNote(year: number | undefined): Promise<void> {
  if (!variantApplicable.value) return // 门控
  const fxPayload = buildE1FxSyncPayload(variant.value, props.wpId || '', applicableStandards.value, {
    fxRows: foreignCurrencyRows.value.map((r) => ({
      groupId: r.groupId,
      currency: r.currency,
      isGroup: r.isGroup,
      endForeign: r.endForeign,
      endRate: r.endRate,
      endRmb: r.endRmb,
    })),
  })
  if (!fxPayload) return
  try {
    const resp: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      year ? { ...fxPayload, year } : fxPayload,
    )
    const data = resp?.data ?? resp
    // fail closed 是静默跳过 → 必须让审计师知道哪张表没同步成功、**以及为什么**
    const failure = rowScopeFailureMessage(
      '外币货币性项目',
      data?.row_scope_unresolved,
      data?.row_scope_unresolved_reasons,
    )
    if (failure) {
      ElMessage.warning(failure)
      return
    }
    if (data && (data.success || data.section_id)) {
      eventBus.emit('disclosure:note-text-updated', {
        wpCode: 'E1',
        variant: variant.value,
        accountCode: '1001',
        projectId: props.projectId,
        sectionIds: [E1_FX_NOTE_SECTION[variant.value]],
        timestamp: Date.now(),
      })
    }
  } catch (err: any) {
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
    ElMessage.warning('外币货币性项目同步附注失败，请稍后重试')
  }
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!variantApplicable.value) return // 门控：不适用时不写入
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  try {
    const snapshot: E1DisclosureSnapshot = {
      mainRows: disclosureRows.value.map(r => ({
        key: r.key,
        label: r.label,
        endingAmount: r.endingAmount,
        openingAmount: r.openingAmount,
      })),
      // ②表**两变体都推**（用户裁决 2026-08-01：上市侧也建该表）。
      // 条件表语义：无行时不推空表，由 e1NoteSectionMap 放进 _removed_table_keys。
      restrictedRows: restrictedRows.value.map(r => ({
        item: r.label,
        openingAmount: r.openingAmount,
        endingAmount: r.endingAmount,
        reason: r.reason,
      })),
      // 按源模板分段推送（每段带中文 title，否则附注正文会渲染成英文键）
      noteSections: noteTextDefs.value.map(d => ({
        key: d.key,
        title: d.title,
        text: noteTexts.value[d.key] || '',
      })),
    }
    const payload = buildE1SyncPayload(
      variant.value,
      props.wpId || '',
      applicableStandards.value,
      snapshot,
    )
    // 显式携带审计年度，定位到项目审计年度的附注记录（否则后端默认取服务器当前年）
    const yr = Number(auditYear.value) || undefined
    const resp: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      yr ? { ...payload, year: yr } : payload,
    )
    // http.post 解析为 AxiosResponse（响应拦截器已把 {code,data} 信封解包到 resp.data）；
    // 结果字段（success/section_id）在 resp.data 上，不能直接读 resp（否则恒 undefined→误报"返回异常"）。
    const data = resp?.data ?? resp
    const sectionId = E1_NOTE_SECTION[variant.value]
    if (data && (data.success || data.section_id)) {
      ElMessage.success(`已同步到附注「${sectionId} 货币资金」`)
      // 通知附注模块刷新（若正打开该章节）
      eventBus.emit('disclosure:note-text-updated', {
        wpCode: 'E1',
        variant: variant.value,
        accountCode: '1001',
        projectId: props.projectId,
        sectionIds: [sectionId],
        timestamp: Date.now(),
      })
    } else {
      ElMessage.warning('同步附注返回异常')
    }
    await syncFxSectionToNote(yr)
    await syncRestrictedAssetsToNote(yr)
  } catch (err: any) {
    // 重复点击被请求去重取消（axios cancel / ERR_CANCELED）：首个请求仍在进行，静默忽略不吓用户
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

/**
 * 受限资产 → 附注 `五、32`（上市，双期两张表）/ `八、93`（国企）的**第三个 payload**。
 *
 * 🔴 该表也是**跨循环共享表**（货币资金/应收票据/应收账款/应收款项融资/存货/
 * 固定资产/在建工程/无形资产 各一段，owner 横跨 E1/D1/D2/D5/F2/H1/H2/I1），
 * E1 只负责 `BS-002 货币资金` 段，载荷带 `_row_scope`。
 *
 * 数据源 = 本页 ②表「受限制的货币资金明细」—— 它按受限类别分行（银行承兑保证金 /
 * 信用证保证金 / 境外受限 …），而附注该表是**按资产类别**披露 → 归纳成**一行**
 * 「货币资金」（金额求和、受限原因去重拼接），类别明细留在 `五、1`/`八、1` 的 ②表。
 *
 * 无受限资金（②表空或全零）时 `buildRestrictedAssetsPayloads` 返回 `[]` → 不推
 * （空推送会把段恢复成模板骨架，等于清掉审计师手填内容）。失败静默不盖主提示。
 */
async function syncRestrictedAssetsToNote(year: number | undefined): Promise<void> {
  if (!variantApplicable.value) return // 门控
  const payloads = buildRestrictedAssetsPayloads(
    variant.value,
    props.wpId || '',
    applicableStandards.value,
    {
      ownerRowCode: 'BS-002',
      rows: summarizeRestrictedRows(
        RESTRICTED_ASSETS_OWNERS['BS-002'],
        restrictedRows.value.map((r) => ({
          endAmount: r.endingAmount,
          priorAmount: r.openingAmount,
          reason: r.reason,
        })),
      ),
    },
    E1_DISCLOSURE_SHEET_NAME,
  )
  if (!payloads.length) return
  const sectionId = RESTRICTED_ASSETS_NOTE_SECTION[variant.value]
  for (const payload of payloads) {
    try {
      const resp: any = await http.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        year ? { ...payload, year } : payload,
      )
      const data = resp?.data ?? resp
      // fail closed 是静默跳过 → 必须让审计师知道哪张表没同步成功、**以及为什么**
      const raFailure = rowScopeFailureMessage(
        '受限资产',
        data?.row_scope_unresolved,
        data?.row_scope_unresolved_reasons,
      )
      if (raFailure) {
        ElMessage.warning(raFailure)
        continue
      }
      if (data && (data.success || data.section_id)) {
        eventBus.emit('disclosure:note-text-updated', {
          wpCode: 'E1',
          variant: variant.value,
          accountCode: '1001',
          projectId: props.projectId,
          sectionIds: [sectionId],
          timestamp: Date.now(),
        })
      }
    } catch (err: any) {
      if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
      ElMessage.warning('受限资产同步附注失败，请稍后重试')
      return
    }
  }
}

// ─── 数据变更后自动同步到附注 ─────────────────────────────────────────────────
// 🔴 必须注册在此处（全部被监听 const 与 syncToDisclosureNotes 均已声明之后）：
// `<script setup>` 的 const 有 TDZ，watch 依赖数组在 setup 期即求值，放到文件顶部
// 会抛 ReferenceError 让整个披露 Tab 挂不上（get_diagnostics/vitest/Vite 全查不出）。
// 监听源与 syncToDisclosureNotes 构建 snapshot 所用字段一致（disclosureRows /
// restrictedRows / noteTexts / variant），保证「改了什么就同步什么」。
watch(
  // `foreignCurrencyRows` 也在监听源里 —— 外币段经 `syncFxSectionToNote` 推 五、73/八、92，
  // 不加它则「改了外币不同步」（与「监听源须和载荷构建字段一致」铁律相符）
  [disclosureRows, restrictedRows, noteTexts, variant, foreignCurrencyRows],
  () => {
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)

// ─── Cleanup ─────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; persistAll() }
})
</script>

<template>
  <div class="e1-tab-disclosure">
    <!-- 变体适用性门控：不适用时显示提示页，不渲染录入区 -->
    <template v-if="!variantApplicable">
      <el-result icon="info" title="当前项目不适用此附注披露">
        <template #sub-title>
          <p>{{ variant === 'listed' ? '当前项目不适用上市公司附注披露' : '当前项目不适用国企附注披露' }}</p>
          <p style="color: var(--el-text-color-secondary); font-size: 12px;">
            项目适用准则：{{ applicableStandards?.length ? applicableStandards.join(', ') : '未配置' }}
          </p>
        </template>
      </el-result>
    </template>

    <template v-else>
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 期末数取自 E1-1 审定表各科目审定数（跨sheet自动取数，灰色底纹列不可手工录入）；期初数（上年年末余额）自动预填审定表期初审定数（标「预填」，可手工覆盖为上年附注数）。</p>
        <p>2. 上市公司版：列示库存现金/银行存款/存放财务公司/其他货币资金/应计利息/数字货币。</p>
        <p>3. 国企版：额外列示受限制货币资金明细（保证金/担保存款/境外受限）。</p>
        <p>4. 境外存款需说明汇率中间价参考来源；数字货币列报参照准则解释15号资金集中管理。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      :title="objective"
      class="objective-alert"
    />

    <!-- 工具栏：OnlyOffice 入口已由上层统一提供，此处仅保留结构化披露工具 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <!-- 同步到附注：结构化表格 + 文本框内容 → 附注 五、1/八、1「货币资金」，保证附注与披露表一致 -->
        <el-button
          type="success"
          size="small"
          class="sync-btn"
          :loading="isSyncing"
          :disabled="isReadonly"
          :title="`将披露表的表格与文本框内容同步到附注模块（${variant === 'soe' ? '八、1' : '五、1'} 货币资金）`"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <!-- 跳转回附注：默认按当前版本对应（上市↔五、1 / 国企↔八、1），下拉可自由切换上市/国企 -->
        <el-dropdown
          split-button
          type="primary"
          size="small"
          trigger="click"
          @click="jumpToNote(variant)"
          @command="jumpToNote"
        >
          ↩ 跳转回附注（{{ variant === 'soe' ? '八、1' : '五、1' }}）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="listed">上市版附注（五、1）</el-dropdown-item>
              <el-dropdown-item command="soe">国企版附注（八、1）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-tag size="small" type="info">{{ variant === 'soe' ? '国企附注' : '上市公司附注' }}</el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- Disclosure Table -->
    <el-table :data="disclosureRows" border size="small" style="width: 100%; max-width: 700px">
        <el-table-column prop="label" label="项目" width="200">
          <template #default="{ row }">
            <span :class="{ 'font-bold': row.key === 'total' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="endingLabel" width="180" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <!-- 🔴 未取到值时显示「—」而非 0.00（本项目无此科目 ≠ 余额为 0） -->
            <el-tooltip
              v-if="!row.endingResolved"
              content="本项目无此科目（审定表未取到该语义槽数据），可在审定表录入未审数后自动带入"
              placement="top"
            >
              <span class="no-account-cell">—</span>
            </el-tooltip>
            <template v-else>
              <el-tooltip
                v-if="row.endingSlotPrefilled"
                content="由审定表语义槽自动带入（准则解释 15 号单独列示项，无一级标准科目）"
                placement="top"
              >
                <el-tag size="small" type="success" effect="plain" class="prefill-tag">预填</el-tag>
              </el-tooltip>
              <el-tooltip
                v-if="row.endingDeducted"
                content="已扣除下方单独列示项（避免与「存放财务公司款项」/「数字货币」双算）"
                placement="top"
              >
                <el-tag size="small" type="warning" effect="plain" class="prefill-tag">已扣减</el-tag>
              </el-tooltip>
              <span class="computed-cell">{{ displayPrefs.fmtAmount(row.endingAmount) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column :label="openingLabel" width="200" align="right">
          <template #default="{ row }">
            <span v-if="row.key === 'total'" class="computed-cell font-bold">{{ displayPrefs.fmtAmount(row.openingAmount) }}</span>
            <div v-else class="opening-cell">
              <el-tooltip v-if="row.openingPrefilled" content="已自动预填审定表期初审定数（本年期初=上年年末），可手工覆盖" placement="top">
                <el-tag size="small" type="success" effect="plain" class="prefill-tag">预填</el-tag>
              </el-tooltip>
              <el-input
                :model-value="row.openingAmount"
                :disabled="isReadonly"
                :formatter="amountFormatter"
                :parser="amountParser"
                size="small"
                class="amt-input"
                @change="(val: string) => updateOpening(row.key, Number(val) || 0)"
              />
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!--
        外币性质货币资金项目 + 货币资金（原币）—— **两变体都有**。
        🔴 源 xlsx 逐格实证（openpyxl，2026-08-02）：「附注披露信息(上市公司)」与
        「附注披露信息(国企)」的 R25~R62 两张外币表**逐字相同**（表名/两级表头/
        四个分组/五个币种/合计公式全同），只有 R17 的汇率中间价提示块是上市侧独有。
        改造前这里写 `v-if="variant === 'listed'"` → 国企 Tab 完全没有外币录入位置，
        而国企 sheet 的勾稽单元格 R12 列 E 恰恰是 `=B12-'附注披露信息(上市公司)'!D62`
        （主表合计 − 原币表人民币合计），可见国企版同样要求填这两张表。
      -->
      <h4 class="section-title" style="margin-top:20px">外币性质货币资金项目</h4>
      <template v-if="variant === 'listed'">
        <div class="amber-context" style="margin-bottom:10px">
          <span class="amber-icon">📌</span>
          <span class="amber-text">（提示：(1) 截止202X年12月31日，人民币对汇率中间价按中国人民银行公布的汇率折算。(2) 本集团不存在抵押、质押或冻结以及存放在境外且资金汇回受到限制的款项。）</span>
        </div>
      </template>
        <!-- 版本切换：详细版=源模板结构（库存现金/银行存款/银行存款中：财务公司存款/其他货币资金 × 币种）；简版=货币资金合计 × 币种 -->
        <div class="fc-toolbar">
          <el-segmented
            :model-value="foreignCurrencyMode"
            :options="[{ label: '详细版（按项目）', value: 'detailed' }, { label: '简版（合计）', value: 'simple' }]"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateForeignMode(v as 'simple' | 'detailed')"
          />
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addFcProject">+ 新增项目</el-button>
        </div>
        <el-table :data="foreignCurrencyRows" border size="small" style="width:100%; max-width:1000px" show-summary :summary-method="foreignCurrencySummary">
          <el-table-column prop="item" label="项 目" width="200" fixed>
            <template #default="{ row }">
              <div class="fc-item-cell">
                <span :class="{ 'font-bold': row.isGroup, 'indent-row': row.indent }">{{ row.item }}</span>
                <span v-if="!isReadonly" class="fc-item-ops">
                  <el-button v-if="row.isGroup" link type="primary" size="small" @click="addFcCurrency(row.id)">+币种</el-button>
                  <el-button link type="danger" size="small" @click="removeFcRow(row)">删</el-button>
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="期末数" align="center">
            <el-table-column label="原币金额" width="120" align="right">
              <template #default="{ row }">
                <el-input v-if="!row.isGroup && !isReadonly" :model-value="row.endForeign" :formatter="amountFormatter" :parser="amountParser" size="small" class="amt-input" style="width:100%" @change="(v: string) => updateFcCell(row.id, 'endForeign', Number(v) || 0)" />
                <span v-else>{{ row.endForeign ? displayPrefs.fmtAmount(row.endForeign) : '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="折算率" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isGroup && !isReadonly" :model-value="row.endRate" :controls="false" :precision="4" size="small" style="width:100%" @change="(v: number) => updateFcCell(row.id, 'endRate', v ?? 0)" />
                <span v-else>{{ row.endRate ? row.endRate.toFixed(4) : '#N/A' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人民币金额" width="130" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="computed-cell">{{ (row.isGroup ? groupRmb(row, 'endRmb') : row.endRmb) ? displayPrefs.fmtAmount(row.isGroup ? groupRmb(row, 'endRmb') : row.endRmb) : '-' }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="原币金额" width="120" align="right">
              <template #default="{ row }">
                <el-input v-if="!row.isGroup && !isReadonly" :model-value="row.openForeign" :formatter="amountFormatter" :parser="amountParser" size="small" class="amt-input" style="width:100%" @change="(v: string) => updateFcCell(row.id, 'openForeign', Number(v) || 0)" />
                <span v-else>{{ row.openForeign ? displayPrefs.fmtAmount(row.openForeign) : '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="折算率" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isGroup && !isReadonly" :model-value="row.openRate" :controls="false" :precision="4" size="small" style="width:100%" @change="(v: number) => updateFcCell(row.id, 'openRate', v ?? 0)" />
                <span v-else>{{ row.openRate ? row.openRate.toFixed(4) : '#N/A' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人民币金额" width="130" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="computed-cell">{{ (row.isGroup ? groupRmb(row, 'openRmb') : row.openRmb) ? displayPrefs.fmtAmount(row.isGroup ? groupRmb(row, 'openRmb') : row.openRmb) : '-' }}</span>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>

      <!-- ② 受限制的货币资金明细（两变体共用；用户裁决 2026-08-01 上市侧也建该表） -->
      <h4 class="section-title">② 受限制的货币资金明细</h4>
      <div class="amber-context" style="margin-bottom:10px">
        <span class="amber-icon">📌</span>
        <span class="amber-text">（提示：列示保证金、担保存款、冻结款项及存放境外且资金汇回受限等不符合现金及现金等价物条件或使用受限的款项。校验预设 F1-4：合计 = 各明细行之和；F1-5/F1-6：本表合计 = 报表货币资金 − 现金流量表补充资料「现金及现金等价物余额」。）</span>
      </div>

      <el-table
        :data="restrictedRows"
        border
        size="small"
        style="width: 100%; max-width: 900px"
        show-summary
        :summary-method="restrictedSummary"
      >
        <el-table-column :label="itemColumnLabel" min-width="200">
          <template #default="{ row }">
            <span>{{ row.label }}</span>
            <el-tag v-if="row.fromFourTable" size="small" type="success" effect="plain" class="src-tag">四表</el-tag>
            <el-tooltip v-if="row.codes.length" :content="`来源科目：${row.codes.join('、')}`" placement="top">
              <span class="code-hint">{{ row.codes.length }} 个科目</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column :label="openingLabel" width="150" align="right">
          <template #default="{ row }">
            <span v-if="row.fromFourTable" class="derived-cell">{{ displayPrefs.fmtAmount(row.openingAmount) }}</span>
            <WpAmountInput
              v-else
              :model-value="row.openingAmount"
              :disabled="isReadonly"
              @update:model-value="(val: number) => updateRestrictedCell(row.id, 'openingAmount', val)"
            />
          </template>
        </el-table-column>
        <el-table-column :label="endingLabel" width="150" align="right">
          <template #default="{ row }">
            <span v-if="row.fromFourTable" class="derived-cell">{{ displayPrefs.fmtAmount(row.endingAmount) }}</span>
            <WpAmountInput
              v-else
              :model-value="row.endingAmount"
              :disabled="isReadonly"
              @update:model-value="(val: number) => updateRestrictedCell(row.id, 'endingAmount', val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="受限原因" min-width="180">
          <template #default="{ row }">
            <el-input
              :model-value="row.reason"
              :disabled="isReadonly"
              size="small"
              placeholder="按实际受限情形填写"
              @input="(val: string) => updateRestrictedCell(row.id, 'reason', val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!isReadonly && !row.fromFourTable"
              type="danger"
              text
              size="small"
              @click="removeRestrictedRow(row.id)"
            >删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <span class="empty-hint">暂无受限资金。四表入库后若识别不出受限科目，请在下方「待归类科目」面板点选归类。</span>
        </template>
      </el-table>
      <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRestrictedRow">+ 新增受限类别</el-button>

      <!-- 待归类科目：「各项目科目命名不同」的兜底通道 -->
      <details v-if="restrictedPending.length || restrictedExcluded.length" class="pending-details" open>
        <summary>
          🔎 待归类科目
          <el-tag size="small" type="warning" effect="plain">{{ restrictedPending.length }} 项待处理</el-tag>
          <el-tag v-if="restrictedExcluded.length" size="small" type="info" effect="plain">
            {{ restrictedExcluded.length }} 项已标为不受限
          </el-tag>
        </summary>
        <div class="pending-body">
          <div class="pending-hint">
            以下货币资金子科目按科目名判不出受限类别（各项目命名习惯不同，平台不臆造归属）。
            请逐项点选归入某类，或标记为「不受限」。已处理项不再出现在此处。
          </div>

          <!--
            R8.4：分两区展示 —— 「无子科目明细的父科目行」与「真明细行」语义不同。
            判据在 e1RestrictedScope.partitionUnclassified（只看科目码形态，不看金额）。
          -->
          <template v-if="restrictedPendingParts.details.length">
            <div class="pending-group-title" data-testid="pending-group-details">
              明细科目行
              <el-tag size="small" type="warning" effect="plain">
                {{ restrictedPendingParts.details.length }} 项
              </el-tag>
              <span class="pending-group-note">逐项归入受限类别，或标记为「不受限」。</span>
            </div>
            <el-table
              :data="restrictedPendingParts.details"
              border
              size="small"
              style="width:100%; max-width:900px"
              max-height="280"
            >
              <el-table-column label="来源科目" min-width="220">
                <template #default="{ row }">
                  <span class="ft-code">{{ row.code }}</span>
                  <span class="ft-name">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="openingLabel" width="140" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.opening) }}</template>
              </el-table-column>
              <el-table-column :label="endingLabel" width="140" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.closing) }}</template>
              </el-table-column>
              <el-table-column label="归类为" width="240">
                <template #default="{ row }">
                  <el-select
                    :disabled="isReadonly"
                    size="small"
                    placeholder="选择受限类别"
                    style="width:100%"
                    @change="(val: string) => assignRestricted(row.code, val)"
                  >
                    <el-option
                      v-for="opt in restrictedBucketOptions"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="不受限" width="90" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="!isReadonly"
                    text
                    size="small"
                    @click="assignRestricted(row.code, E1_UNRESTRICTED_KEY)"
                  >标记</el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <template v-if="restrictedPendingParts.parents.length">
            <div class="pending-group-title" data-testid="pending-group-parents">
              未分户的父科目行
              <el-tag size="small" type="info" effect="plain">
                {{ restrictedPendingParts.parents.length }} 项
              </el-tag>
              <span class="pending-group-note">
                该科目在本项目未按户设置子科目（叶子就是一级科目本身）。通常整体判「不受限」，
                或在 E1-3 按账户逐户填写受限金额与原因（下方 L2 勾稽会与本表合计对照）。
              </span>
            </div>
            <el-table
              :data="restrictedPendingParts.parents"
              border
              size="small"
              style="width:100%; max-width:900px"
              max-height="240"
            >
              <el-table-column label="来源科目" min-width="220">
                <template #default="{ row }">
                  <span class="ft-code">{{ row.code }}</span>
                  <span class="ft-name">{{ row.name }}</span>
                  <el-tag size="small" type="info" effect="plain" class="src-tag">未分户</el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="openingLabel" width="140" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.opening) }}</template>
              </el-table-column>
              <el-table-column :label="endingLabel" width="140" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.closing) }}</template>
              </el-table-column>
              <el-table-column label="归类为" width="240">
                <template #default="{ row }">
                  <el-select
                    :disabled="isReadonly"
                    size="small"
                    placeholder="选择受限类别"
                    style="width:100%"
                    @change="(val: string) => assignRestricted(row.code, val)"
                  >
                    <el-option
                      v-for="opt in restrictedBucketOptions"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="不受限" width="90" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="!isReadonly"
                    text
                    size="small"
                    @click="assignRestricted(row.code, E1_UNRESTRICTED_KEY)"
                  >标记</el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>

          <template v-if="restrictedExcluded.length">
            <div class="pending-hint" style="margin-top:10px">
              已标记为「不受限」的科目（金额仍参与 F1-5/F1-6 勾稽的差额侧，不隐藏）：
            </div>
            <el-table :data="restrictedExcluded" border size="small" style="width:100%; max-width:760px" max-height="220">
              <el-table-column label="来源科目" min-width="220">
                <template #default="{ row }">
                  <span class="ft-code">{{ row.code }}</span>
                  <span class="ft-name">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="endingLabel" width="140" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.closing) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="90" align="center">
                <template #default="{ row }">
                  <el-button v-if="!isReadonly" text size="small" @click="resetRestrictedAssignment(row.code)">撤销</el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>
        </div>
      </details>

      <!-- 披露内部勾稽：规则全部取自校验预设 F1-1~F1-6 + 源 xlsx 表内公式 -->
      <WpDisclosureConsistencyPanel
        :results="consistencyResults"
        :project-id="projectId"
        title="披露勾稽（校验预设 F1-1~F1-6）"
      />
      <div v-if="consistencyErrorCount > 0" class="consistency-actions">
        <span class="consistency-hint">
          存在 {{ consistencyErrorCount }} 项超出容差的勾稽差异，可推送到 A13 未更正错报汇总。
        </span>
        <el-button
          type="warning"
          size="small"
          plain
          :disabled="isReadonly"
          @click="pushConsistencyToA13"
        >推送差异到 A13 错报</el-button>
      </div>

      <!-- 附注说明：按源模板分段（上市 2 段 / 国企 2 段），每段配 AI 辅助 -->
      <el-card
        v-for="def in noteTextDefs"
        :key="def.key"
        class="opinion-card"
        shadow="never"
      >
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">{{ def.title }}</span>
            <div class="opinion-chips">
              <el-button
                type="primary"
                text
                size="small"
                :loading="isGenerating(`e1-disclosure-${variant}-note-${def.key}`)"
                :disabled="isReadonly"
                @click="generateNoteText(def)"
              >🤖 AI 辅助</el-button>
              <GtIndexChip value="wp:E1-1" :context-project-id="projectId" />
            </div>
          </div>
        </template>
        <!-- 源模板指引（编制提示，不进附注正文） -->
        <div class="amber-context" style="margin-bottom:8px">
          <span class="amber-icon">📌</span>
          <span class="amber-text">{{ def.guidance }}</span>
        </div>
        <el-input
          :model-value="noteTexts[def.key] || ''"
          :disabled="isReadonly"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 14 }"
          :placeholder="def.placeholder"
          @input="(val: string) => updateNote(def.key, val)"
        />
      </el-card>

      <!-- 审计结论卡片下方无更多内容 -->
    </template>
  </div>
</template>

<style scoped>
.e1-tab-disclosure {
  padding: 12px 0;
}
.e1-tab-disclosure :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-disclosure :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
/* 金额输入统一右对齐（千分符+两位由 amountFormatter 提供），折算率等 el-input-number 亦右对齐 */
.e1-tab-disclosure :deep(.amt-input .el-input__inner),
.e1-tab-disclosure :deep(.el-input-number .el-input__inner) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
/* 同步到附注按钮：实心绿底+白字，避免浅绿底浅绿字低对比"看不清" */
.e1-tab-disclosure :deep(.sync-btn) {
  background-color: var(--el-color-success, #28a745);
  border-color: var(--el-color-success, #28a745);
  color: #fff;
}
.e1-tab-disclosure :deep(.sync-btn span) { color: #fff; }
.e1-tab-disclosure :deep(.sync-btn:hover),
.e1-tab-disclosure :deep(.sync-btn:focus) {
  background-color: var(--el-color-success-light-3, #4cb85f);
  border-color: var(--el-color-success-light-3, #4cb85f);
  color: #fff;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.online-edit-placeholder {
  padding: 40px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.font-bold {
  font-weight: 700;
}
.section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.add-btn {
  margin-top: 8px;
}
/* 方法论琥珀块 */
.amber-context {
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.55;
  color: #8a6d3b;
  display: flex;
  gap: 6px;
}
.amber-context .amber-icon { flex-shrink: 0; }
.amber-context .amber-text { flex: 1; }
.indent-row { padding-left: 16px; }
.opening-cell { display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
.opening-cell .prefill-tag { flex-shrink: 0; cursor: help; }
/* 「本项目无此科目」与「余额为 0」必须可区分：前者显示 — 且置灰 */
.no-account-cell { color: var(--el-text-color-placeholder); cursor: help; }
.deducted-cell { border-bottom: 1px dashed var(--el-color-warning); cursor: help; }
.fc-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.fc-item-cell { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.fc-item-ops { display: inline-flex; align-items: center; gap: 2px; flex-shrink: 0; }
.fc-item-ops :deep(.el-button.is-link) { padding: 0 2px; height: auto; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.computed-cell { color: #909399; }
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
  max-width: 700px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.audit-note-card {
  margin-top: 16px;
  max-width: 700px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

/* ② 受限表：四表来源标记与派生只读格 */
.src-tag { margin-left: 6px; }
.code-hint {
  margin-left: 6px;
  font-size: 12px;
  color: #909399;
  cursor: help;
  border-bottom: 1px dashed #c0c4cc;
}
.derived-cell {
  color: #606266;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.empty-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}

/* 待归类科目面板 */
.pending-details {
  margin-top: 12px;
  border: 1px solid #faecd8;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 8px 12px;
}
.pending-details summary {
  cursor: pointer;
  font-weight: 600;
  color: #b88230;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.pending-body { margin-top: 10px; }
.pending-hint {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 8px;
}
/* 待归类两区标题（R8.4：父科目行 / 真明细行语义不同，视觉上分开） */
.pending-group-title {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: #b88230;
}
.pending-group-note {
  font-weight: 400;
  color: #606266;
  line-height: 1.6;
}
.ft-code { font-weight: 600; color: #303133; margin-right: 6px; }
.ft-name { color: #606266; }

/* 勾稽差异推 A13 */
.consistency-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: -4px 0 12px;
}
.consistency-hint {
  font-size: 12px;
  color: #b88230;
  line-height: 1.6;
}
</style>
