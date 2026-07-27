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
import { buildE1SyncPayload, E1_NOTE_SECTION, type E1DisclosureSnapshot } from '../composables/e1NoteSectionMap'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'
import { useAuditContext } from '@/composables/useAuditContext'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'

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
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)
const router = useRouter()
// 审计年度（单一真源 projectStore），用于同步到附注时定位正确年度的附注记录，
// 避免后端按服务器当前年默认导致同步到错误年度的附注（附注模块显示审计年度记录）。
const { year: auditYear } = useAuditContext()

// 保存后自动同步到附注（防抖/非阻塞/失败静默/只读 gate；与手动按钮同源 syncToDisclosureNotes）
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

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

type DisclosureVariant = 'listed' | 'soe'

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

// 上市公司披露项目（对照源模板"附注披露信息(上市公司)"）
const LISTED_ITEMS = [
  { key: 'cash', label: '库存现金', crossKey: 'E1-adj-total-1001' },
  { key: 'bank', label: '银行存款', crossKey: 'E1-adj-total-1002' },
  { key: 'finance_co', label: '存放财务公司款项', crossKey: '' },
  { key: 'other_mf', label: '其他货币资金', crossKey: 'E1-adj-total-1012' },
  { key: 'accrued', label: '存款应计利息', crossKey: '' },
  { key: 'digital', label: '数字货币', crossKey: '' },
  { key: 'total', label: '合计', crossKey: '' },
  { key: 'overseas', label: '其中：存放境外', crossKey: '' },
]

// 国企披露项目（对照源模板"附注披露信息(国企)"：现金/银行存款/其他货币资金/数字货币/合计）
const SOE_ITEMS = [
  { key: 'cash', label: '现金', crossKey: 'E1-adj-total-1001' },
  { key: 'bank', label: '银行存款', crossKey: 'E1-adj-total-1002' },
  { key: 'other_mf', label: '其他货币资金', crossKey: 'E1-adj-total-1012' },
  { key: 'digital', label: '数字货币', crossKey: '' },
  { key: 'total', label: '合计', crossKey: '' },
]

const disclosureItems = computed(() => (variant.value === 'soe' ? SOE_ITEMS : LISTED_ITEMS))

// 列标签（上市：期末数/期初数；国企：期末余额/年初余额）
const endingLabel = computed(() => (variant.value === 'soe' ? '期末余额' : '期末数'))
const openingLabel = computed(() => (variant.value === 'soe' ? '年初余额' : '期初数'))

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

// 单项期末数：从审定表跨sheet审定数（E1-adj-total-{code}）只读取数
function effEnding(item: { crossKey: string }): number {
  if (!item.crossKey) return 0
  return Number(props.allResponses.get(item.crossKey)?.remark) || 0
}
// 单项期初数：手工覆盖优先（openingMap 显式含该 key），否则自动预填审定表期初审定数
// （E1-adj-total-{code}-opening，本年期初=上年年末）。仅在 openingMap 未显式设置时预填。
function effOpening(item: { key: string; crossKey: string }): number {
  if (item.key in openingMap.value) return Number(openingMap.value[item.key]) || 0
  if (item.crossKey) return Number(props.allResponses.get(`${item.crossKey}-opening`)?.remark) || 0
  return 0
}
// 某项期初是否自动预填（无手工覆盖且有科目映射且预填值非0）——供 UI 标注
function isOpeningPrefilled(item: { key: string; crossKey: string }): boolean {
  return !(item.key in openingMap.value) && !!item.crossKey
    && (Number(props.allResponses.get(`${item.crossKey}-opening`)?.remark) || 0) !== 0
}

const disclosureRows = computed<(DisclosureRow & { openingPrefilled: boolean })[]>(() => {
  const items = disclosureItems.value
  return items.map(item => {
    let endingAmount = effEnding(item)
    let openingAmount = effOpening(item)
    // Total row: sum of above items (excluding overseas)
    if (item.key === 'total') {
      const subs = items.filter(i => !['total', 'overseas'].includes(i.key))
      endingAmount = subs.reduce((sum, i) => sum + effEnding(i), 0)
      openingAmount = subs.reduce((sum, i) => sum + effOpening(i), 0)
    }
    return {
      key: item.key,
      label: item.label,
      crossKey: item.crossKey,
      endingAmount,
      openingAmount,
      openingPrefilled: item.key === 'total' ? false : isOpeningPrefilled(item),
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

const SIMPLE_CURRENCIES = ['美元', '日元', '澳元', '欧元']
const DETAILED_CURRENCIES = ['人民币', '美元', '日元', '澳元', '欧元']
// 对齐源模板「附注披露信息(上市公司)」外币性质货币资金项目分组（库存现金/银行存款/
// 银行存款中：财务公司存款/其他货币资金），详细版为源模板标准结构。
const DETAILED_PROJECTS = ['库存现金', '银行存款', '银行存款中：财务公司存款', '其他货币资金']

function createCurrencyRow(groupId: string, currency: string, suffix: string): ForeignCurrencyRow {
  const isRmb = currency === '人民币'
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
  const projects = mode === 'detailed' ? DETAILED_PROJECTS : ['货币资金']
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
      item: isGroup ? String(raw.item || '货币资金：') : currency,
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

// ─── SOE Restricted Table ────────────────────────────────────────────────────

interface RestrictedRow {
  id: string
  item: string
  openingAmount: number
  endingAmount: number
  reason: string
}

const restrictedRows = ref<RestrictedRow[]>([])

function loadRestricted(): void {
  const key = `${storagePrefix.value}-restricted`
  const resp = props.allResponses.get(key)
  if (resp?.remark) {
    try {
      const parsed = JSON.parse(resp.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        restrictedRows.value = parsed.map((r: any) => ({
          id: r.id || `restr-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          item: String(r.item || ''),
          openingAmount: Number(r.openingAmount) || 0,
          // 旧结构仅有 amount，迁移时视为期末金额。
          endingAmount: Number(r.endingAmount ?? r.amount) || 0,
          reason: String(r.reason || ''),
        }))
        return
      }
    } catch {}
  }
  // 无持久化数据时，按源模板"受限制的货币资金明细"预置标准项目行
  const defaults = [
    '银行承兑汇票保证金',
    '信用证保证金',
    '履约保证金',
    '用于担保的定期存款或通知存款',
    '存放境外且资金汇回受到限制的款项',
  ]
  restrictedRows.value = defaults.map((item, i) => ({
    id: `restr-${Date.now()}-${i}`,
    item,
    openingAmount: 0,
    endingAmount: 0,
    reason: '',
  }))
}
if (variant.value === 'soe') loadRestricted()

// ─── Note Text ───────────────────────────────────────────────────────────────

const noteText = ref('')

function loadNote(): void {
  const key = `${storagePrefix.value}-note`
  const resp = props.allResponses.get(key)
  noteText.value = resp?.remark || ''
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
  if (variant.value === 'soe') loadRestricted()
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

  // Note
  const noteKey = `${storagePrefix.value}-note`
  items.push({ item_id: noteKey, conclusion: null, remark: noteText.value })
  props.allResponses.set(noteKey, items[items.length - 1])

  // 审计说明
  const auditNoteKey = `${storagePrefix.value}-audit-note`
  items.push({ item_id: auditNoteKey, conclusion: null, remark: auditNote.value })
  props.allResponses.set(auditNoteKey, items[items.length - 1])

  // 审计结论
  const auditConcKey = `${storagePrefix.value}-audit-conclusion`
  items.push({ item_id: auditConcKey, conclusion: null, remark: auditConclusion.value })
  props.allResponses.set(auditConcKey, items[items.length - 1])

  // SOE restricted
  if (variant.value === 'soe') {
    const rKey = `${storagePrefix.value}-restricted`
    const rJson = JSON.stringify(restrictedRows.value.map(row => ({
      id: row.id,
      item: row.item,
      openingAmount: row.openingAmount,
      endingAmount: row.endingAmount,
      reason: row.reason,
    })))
    items.push({ item_id: rKey, conclusion: null, remark: rJson })
    props.allResponses.set(rKey, items[items.length - 1])
  }

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

  // P2-14: 发布附注数据变化事件，供 DisclosureEditor 订阅刷新
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'E1',
    variant: variant.value,
    projectId: props.projectId,
    sectionIds: items.map((it: any) => it.item_id),
    timestamp: Date.now(),
  })

  // 自动同步到附注（防抖/非阻塞/失败静默）
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateOpening(key: string, val: number): void {
  if (props.isReadonly) return
  openingMap.value = { ...openingMap.value, [key]: val }
  scheduleSave()
}

function updateNote(val: string): void {
  if (props.isReadonly) return
  noteText.value = val
  scheduleSave()
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

async function addRestrictedRow(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入受限制货币资金项目名称', '新增受限项目', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputValidator: input => input.trim() ? true : '项目名称不能为空',
    })
    restrictedRows.value = [...restrictedRows.value, {
      id: `restr-${Date.now()}`,
      item: value.trim(),
      openingAmount: 0,
      endingAmount: 0,
      reason: '',
    }]
    scheduleSave()
  } catch (error) {
    if (!isPromptCancel(error)) ElMessage.error('新增受限项目失败')
  }
}

function restrictedSummary({ columns }: any): string[] {
  return columns.map((column: any, index: number) => {
    if (index === 0) return '合 计'
    if (index === 1) return displayPrefs.fmtAmount(restrictedRows.value.reduce((s, r) => s + r.openingAmount, 0))
    if (index === 2) return displayPrefs.fmtAmount(restrictedRows.value.reduce((s, r) => s + r.endingAmount, 0))
    return ''
  })
}

function removeRestrictedRow(id: string): void {
  if (props.isReadonly) return
  restrictedRows.value = restrictedRows.value.filter(r => r.id !== id)
  scheduleSave()
}

function updateRestrictedCell(id: string, field: keyof Omit<RestrictedRow, 'id'>, value: string | number): void {
  if (props.isReadonly) return
  const idx = restrictedRows.value.findIndex(r => r.id === id)
  if (idx === -1) return
  const row = { ...restrictedRows.value[idx] }
  if (field === 'openingAmount' || field === 'endingAmount') row[field] = Number(value) || 0
  else row[field] = String(value)
  restrictedRows.value = [...restrictedRows.value.slice(0, idx), row, ...restrictedRows.value.slice(idx + 1)]
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
    受限资金: variant.value === 'soe' ? restrictedRows.value : [],
    附注说明: noteText.value,
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

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  try {
    // 先落盘披露表数据，确保跨sheet审定数/期初/说明为最新
    persistAll()
    const snapshot: E1DisclosureSnapshot = {
      mainRows: disclosureRows.value.map(r => ({
        key: r.key,
        label: r.label,
        endingAmount: r.endingAmount,
        openingAmount: r.openingAmount,
      })),
      restrictedRows: variant.value === 'soe'
        ? restrictedRows.value.map(r => ({
            item: r.item,
            openingAmount: r.openingAmount,
            endingAmount: r.endingAmount,
            reason: r.reason,
          }))
        : undefined,
      noteText: noteText.value,
    }
    const payload = buildE1SyncPayload(variant.value, props.wpId || '', null, snapshot)
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
  } catch (err: any) {
    // 重复点击被请求去重取消（axios cancel / ERR_CANCELED）：首个请求仍在进行，静默忽略不吓用户
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// ─── Cleanup ─────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; persistAll() }
})
</script>

<template>
  <div class="e1-tab-disclosure">
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
            <span class="computed-cell">{{ displayPrefs.fmtAmount(row.endingAmount) }}</span>
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

      <!-- Listed: 外币性质货币资金项目 -->
      <template v-if="variant === 'listed'">
        <h4 class="section-title" style="margin-top:20px">外币性质货币资金项目</h4>
        <div class="amber-context" style="margin-bottom:10px">
          <span class="amber-icon">📌</span>
          <span class="amber-text">（提示：(1) 截止202X年12月31日，人民币对汇率中间价按中国人民银行公布的汇率折算。(2) 本集团不存在抵押、质押或冻结以及存放在境外且资金汇回受到限制的款项。）</span>
        </div>
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
      </template>

      <!-- SOE: Restricted table -->
      <template v-if="variant === 'soe'">
        <h4 class="section-title">受限制货币资金明细</h4>
        <div class="amber-context" style="margin-bottom:10px">
          <span class="amber-icon">📌</span>
          <span class="amber-text">（提示：列示保证金、担保存款、冻结款项及存放境外且资金汇回受限等不符合现金及现金等价物条件或使用受限的款项，须与 E1-1 审定表"受限/境外款项"及报表附注勾稽一致。）</span>
        </div>
        <el-table :data="restrictedRows" border size="small" style="width: 100%; max-width: 780px" show-summary :summary-method="restrictedSummary">
          <el-table-column label="项目" width="220">
            <template #default="{ row }">
              <el-input :model-value="row.item" :disabled="isReadonly" size="small"
                @change="(val: string) => updateRestrictedCell(row.id, 'item', val)" />
            </template>
          </el-table-column>
          <el-table-column label="年初余额" width="150" align="right">
            <template #default="{ row }">
              <el-input :model-value="row.openingAmount" :disabled="isReadonly"
                :formatter="amountFormatter" :parser="amountParser"
                size="small" class="amt-input" style="width:100%"
                @change="(val: string) => updateRestrictedCell(row.id, 'openingAmount', Number(val) || 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="150" align="right">
            <template #default="{ row }">
              <el-input :model-value="row.endingAmount" :disabled="isReadonly"
                :formatter="amountFormatter" :parser="amountParser"
                size="small" class="amt-input" style="width:100%"
                @change="(val: string) => updateRestrictedCell(row.id, 'endingAmount', Number(val) || 0)" />
            </template>
          </el-table-column>
          <el-table-column label="受限原因" min-width="160">
            <template #default="{ row }">
              <el-input :model-value="row.reason" :disabled="isReadonly" size="small"
                @change="(val: string) => updateRestrictedCell(row.id, 'reason', val)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRestrictedRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRestrictedRow">+ 添加行</el-button>
      </template>

      <!-- 附注说明（卡片式） -->
      <el-card class="opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">附注说明</span>
            <div class="opinion-chips">
              <GtIndexChip value="wp:E1-1" :context-project-id="projectId" />
            </div>
          </div>
        </template>
        <el-input
          :model-value="noteText"
          :disabled="isReadonly"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 14 }"
          placeholder="填写货币资金附注说明（受限/境外/回收风险等）"
          @change="updateNote"
        />
      </el-card>

      <!-- 审计结论卡片下方无更多内容 -->
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
</style>
