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
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { eventBus } from '@/utils/eventBus'

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

const disclosureRows = computed<DisclosureRow[]>(() => {
  const items = disclosureItems.value
  return items.map(item => {
    let endingAmount = 0
    if (item.crossKey) {
      const resp = props.allResponses.get(item.crossKey)
      endingAmount = Number(resp?.remark) || 0
    }
    // Total row: sum of above items (excluding overseas)
    if (item.key === 'total') {
      endingAmount = items
        .filter(i => !['total', 'overseas'].includes(i.key))
        .reduce((sum, i) => {
          if (!i.crossKey) return sum
          const r = props.allResponses.get(i.crossKey)
          return sum + (Number(r?.remark) || 0)
        }, 0)
    }
    return {
      key: item.key,
      label: item.label,
      crossKey: item.crossKey,
      endingAmount,
      openingAmount: openingMap.value[item.key] || 0,
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
const DETAILED_PROJECTS = ['库存现金', '银行存款', '财务公司存款', '其他货币资金']

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

const foreignCurrencyMode = ref<ForeignCurrencyMode>('simple')
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
  foreignCurrencyMode.value = 'simple'
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

function foreignCurrencySummary({ columns, data }: any): string[] {
  const leafRows = (data as ForeignCurrencyRow[]).filter(row => !row.isGroup)
  return columns.map((column: any, index: number) => {
    if (index === 0) return '合 计'
    const prop = column.property as ForeignAmountField
    if (!['endForeign', 'endRmb', 'openForeign', 'openRmb'].includes(prop)) return ''
    const total = leafRows.reduce((sum, row) => sum + (Number(row[prop]) || 0), 0)
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
        <p>1. 期末数取自 E1-1 审定表各科目审定数（跨sheet自动取数，灰色底纹列不可手工录入）。</p>
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
        <el-table-column :label="openingLabel" width="180" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.openingAmount"
              :disabled="isReadonly"
              :controls="false"
              size="small"
              @change="(val: number) => updateOpening(row.key, val ?? 0)"
            />
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
        <el-table :data="foreignCurrencyRows" border size="small" style="width:100%; max-width:900px" show-summary :summary-method="foreignCurrencySummary">
          <el-table-column prop="item" label="项 目" width="180" fixed>
            <template #default="{ row }">
              <span :class="{ 'font-bold': row.isGroup, 'indent-row': row.indent }">{{ row.item }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" align="center">
            <el-table-column label="外币金额" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isGroup && !isReadonly" :model-value="row.endForeign" :controls="false" size="small" style="width:100%" @change="(v: number) => updateFcCell(row.id, 'endForeign', v ?? 0)" />
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
                <span class="computed-cell">{{ row.endRmb ? displayPrefs.fmtAmount(row.endRmb) : '-' }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="外币金额" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isGroup && !isReadonly" :model-value="row.openForeign" :controls="false" size="small" style="width:100%" @change="(v: number) => updateFcCell(row.id, 'openForeign', v ?? 0)" />
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
                <span class="computed-cell">{{ row.openRmb ? displayPrefs.fmtAmount(row.openRmb) : '-' }}</span>
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
              <el-input-number :model-value="row.openingAmount" :disabled="isReadonly"
                :controls="false" size="small" style="width:100%"
                @change="(val: number) => updateRestrictedCell(row.id, 'openingAmount', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="150" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.endingAmount" :disabled="isReadonly"
                :controls="false" size="small" style="width:100%"
                @change="(val: number) => updateRestrictedCell(row.id, 'endingAmount', val ?? 0)" />
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
