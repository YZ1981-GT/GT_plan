/**
 * useG5Adjustment — G5-4 调整分录汇总
 *
 * 对齐 Excel「长期应收款调整分录汇总表」/ D4-4 / G4-3 列结构：
 * 调整事项说明 | 类别（报表调整/账项调整/其他）| 报表项目 | 科目名称 |
 * 附注项目 | 借方调整金额 | 贷方调整金额 | 索引 | 备注
 *
 * 确认回写 G5-1：按科目拆桶（原值 / 坏账 / 一年内），避免混入同一行。
 */
import { ref, computed, watch, onMounted, type Ref } from 'vue'
import { parseNum, isDebitCreditBalanced } from '@/composables/useG5FormulaEngine'
import { ElMessage } from 'element-plus'
import { G5_ACCOUNT_CODE, G5_ACCOUNT_NAME } from './g5Constants'
import { G5_ADJ_WRITEBACK_ROW_KEY } from './g5AdjudicationItems'
import { G5_ITEM_IDS, buildCanonicalPayload, readCanonicalRaw } from './g5StorageContract'
import type { ChecklistResponse } from './useF1FormData'

/** 与 Excel G5-4 / D4-4 对齐的列；含旧字段兼容 */
export interface AdjustmentEntry {
  id: string
  rowId: string
  description: string
  category: string
  reportItem: string
  accountName: string
  accountCode: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 兼容旧字段 */
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  preparedBy: string
}

const STORAGE_KEY = G5_ITEM_IDS.G5_4_ROWS
const G5_1_ROWS_KEY = G5_ITEM_IDS.G5_1_ROWS
const WRITEBACK_ROW_ID = G5_ADJ_WRITEBACK_ROW_KEY
const CATEGORY_OPTIONS = ['账项调整', '报表调整', '其他'] as const

/** 长期应收款常见相关科目（科目下拉） */
export const G5_LTR_ACCOUNTS = [
  { code: '1531', name: '长期应收款' },
  { code: '153101', name: '长期应收款——融资租赁' },
  { code: '153102', name: '长期应收款——分期收款销售商品' },
  { code: '153103', name: '长期应收款——分期收款提供劳务' },
  { code: '1532', name: '未实现融资收益' },
  { code: '1231', name: '坏账准备' },
  { code: '1481', name: '一年内到期的非流动资产' },
  { code: '6001', name: '主营业务收入' },
  { code: '6051', name: '其他业务收入' },
  { code: '6301', name: '营业外收入' },
  { code: '1002', name: '银行存款' },
] as const

export type G5WritebackBucket = 'gross' | 'provision' | 'oneYear'

export const G5_WRITEBACK_ROW_KEYS: Record<G5WritebackBucket, string> = {
  gross: G5_ADJ_WRITEBACK_ROW_KEY,
  provision: 'provision-collective-business',
  oneYear: 'gross-one-year',
}

export interface G5WritebackBucketNets {
  aje: number
  rje: number
}

export type G5WritebackNets = Record<G5WritebackBucket, G5WritebackBucketNets>

function generateId(): string {
  return `g5a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function createEmptyEntry(seq = 1, description = ''): AdjustmentEntry {
  return {
    id: generateId(),
    rowId: generateId(),
    description,
    category: '账项调整',
    reportItem: G5_ACCOUNT_NAME,
    accountName: G5_ACCOUNT_NAME,
    accountCode: G5_ACCOUNT_CODE,
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G5-4',
    remark: '',
    seq,
    entryType: 'AJE',
    date: '',
    summary: description,
    preparedBy: '',
  }
}

function categoryFromLegacy(raw: any): string {
  if (raw.category) return String(raw.category)
  if (raw.entryType === 'RJE') return '报表调整'
  if (raw.entryType === 'AJE') return '账项调整'
  return '账项调整'
}

function normalizeEntry(raw: any, idx: number): AdjustmentEntry {
  const description = raw.description || raw.summary || ''
  const category = categoryFromLegacy(raw)
  const entryType: 'AJE' | 'RJE' = category === '报表调整' ? 'RJE' : 'AJE'
  const id = raw.id || raw.rowId || generateId()
  return {
    id,
    rowId: raw.rowId || id,
    description,
    category,
    reportItem: raw.reportItem || G5_ACCOUNT_NAME,
    accountName: raw.accountName || G5_ACCOUNT_NAME,
    accountCode: raw.accountCode || G5_ACCOUNT_CODE,
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: raw.indexRef || 'G5-4',
    remark: raw.remark || '',
    seq: raw.seq ?? idx + 1,
    entryType,
    date: raw.date || '',
    summary: description,
    preparedBy: raw.preparedBy || raw.preparer || '',
  }
}

function safeParseEntries(raw: string | null | undefined): AdjustmentEntry[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeEntry)
  } catch {
    return []
  }
}

function isRje(row: AdjustmentEntry): boolean {
  return row.category === '报表调整' || row.entryType === 'RJE'
}

/** 分录归属回写桶：原值 / 坏账 / 一年内 */
export function classifyG5WritebackBucket(code: string, name: string): G5WritebackBucket | null {
  const c = String(code || '').trim()
  const n = String(name || '')
  if (c) {
    if (c === '1231' || c.startsWith('1231')) return 'provision'
    if (c === '1481' || c.startsWith('1481')) return 'oneYear'
    if (c.startsWith('1531') || c.startsWith('1532')) return 'gross'
    return null // 有科目代码但不属于回写范围时，不按名称误归
  }
  if (n.includes('坏账准备')) return 'provision'
  if (n.includes('一年内到期')) return 'oneYear'
  if (n.includes('长期应收') || n.includes('未实现融资')) return 'gross'
  return null
}

/**
 * 回写符号：
 * - 原值/一年内：借−贷（资产增加为正）
 * - 坏账准备行：贷−借（贷记坏账准备增加准备余额）
 */
export function entryNetForBucket(entry: AdjustmentEntry, bucket: G5WritebackBucket): number {
  const debit = parseNum(entry.debitAmount)
  const credit = parseNum(entry.creditAmount)
  return bucket === 'provision' ? credit - debit : debit - credit
}

export function computeG5WritebackNets(entries: AdjustmentEntry[]): G5WritebackNets {
  const out: G5WritebackNets = {
    gross: { aje: 0, rje: 0 },
    provision: { aje: 0, rje: 0 },
    oneYear: { aje: 0, rje: 0 },
  }
  for (const e of entries) {
    const bucket = classifyG5WritebackBucket(e.accountCode, e.accountName)
    if (!bucket) continue
    const net = entryNetForBucket(e, bucket)
    if (isRje(e)) out[bucket].rje = Math.round((out[bucket].rje + net) * 100) / 100
    else out[bucket].aje = Math.round((out[bucket].aje + net) * 100) / 100
  }
  return out
}

function patchWritebackIntoStore(store: any, nets: G5WritebackNets): any {
  const applyTo = (target: Record<string, any>) => {
    const next = { ...target }
    for (const bucket of Object.keys(G5_WRITEBACK_ROW_KEYS) as G5WritebackBucket[]) {
      const rowKey = G5_WRITEBACK_ROW_KEYS[bucket]
      next[rowKey] = {
        ...(next[rowKey] || {}),
        closingAJE: nets[bucket].aje,
        closingRJE: nets[bucket].rje,
      }
    }
    return next
  }

  if (store?.rows && typeof store.rows === 'object' && store.version) {
    return {
      ...store,
      rows: applyTo({ ...store.rows }),
      writeback: {
        ...(store.writeback || {}),
        [WRITEBACK_ROW_ID]: { closingAJE: nets.gross.aje, closingRJE: nets.gross.rje },
        [G5_WRITEBACK_ROW_KEYS.provision]: {
          closingAJE: nets.provision.aje,
          closingRJE: nets.provision.rje,
        },
        [G5_WRITEBACK_ROW_KEYS.oneYear]: {
          closingAJE: nets.oneYear.aje,
          closingRJE: nets.oneYear.rje,
        },
      },
    }
  }
  return applyTo({ ...(store || {}) })
}

export function useG5Adjustment(opts?: {
  allResponses?: Ref<Map<string, ChecklistResponse>>
  debouncedSave?: (itemId: string, data: Partial<ChecklistResponse>) => void
  saveImmediate?: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  isReadonly?: Ref<boolean> | boolean
}) {
  const entries = ref<AdjustmentEntry[]>([])
  const isReadonly = computed(() => {
    const r = opts?.isReadonly
    if (r == null) return false
    return typeof r === 'boolean' ? r : !!r.value
  })

  const debitTotal = computed(() => entries.value.reduce((s, e) => s + parseNum(e.debitAmount), 0))
  const creditTotal = computed(() => entries.value.reduce((s, e) => s + parseNum(e.creditAmount), 0))
  const isBalanced = computed(() => isDebitCreditBalanced(
    entries.value.map((e) => e.debitAmount),
    entries.value.map((e) => e.creditAmount),
  ))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)

  const ajeTotal = computed(() => ({
    debit: entries.value.filter((e) => !isRje(e)).reduce((s, e) => s + parseNum(e.debitAmount), 0),
    credit: entries.value.filter((e) => !isRje(e)).reduce((s, e) => s + parseNum(e.creditAmount), 0),
  }))
  const rjeTotal = computed(() => ({
    debit: entries.value.filter((e) => isRje(e)).reduce((s, e) => s + parseNum(e.debitAmount), 0),
    credit: entries.value.filter((e) => isRje(e)).reduce((s, e) => s + parseNum(e.creditAmount), 0),
  }))

  const writebackNets = computed(() => computeG5WritebackNets(entries.value))

  /** 兼容旧 API：仅原值桶净额 */
  const netAjeToG5 = computed(() => writebackNets.value.gross.aje)
  const netRjeToG5 = computed(() => writebackNets.value.gross.rje)

  function readStored(): string | null | undefined {
    return readCanonicalRaw(opts?.allResponses?.value.get(STORAGE_KEY))
  }

  function loadEntries(): void {
    entries.value = safeParseEntries(readStored())
  }

  function persist(): void {
    if (isReadonly.value || !opts?.debouncedSave) return
    const payload = buildCanonicalPayload(STORAGE_KEY, entries.value)
    opts.debouncedSave(STORAGE_KEY, payload)
  }

  function loadFromArray(rows: AdjustmentEntry[]): void {
    entries.value = rows.map((e, i) => normalizeEntry(e, i))
    persist()
  }

  function addEntry(): void {
    if (isReadonly.value) return
    entries.value = [...entries.value, createEmptyEntry(entries.value.length + 1)]
    persist()
  }

  function removeEntry(id: string): void {
    if (isReadonly.value) return
    const next = entries.value.filter((e) => e.id !== id && e.rowId !== id)
    next.forEach((e, i) => { e.seq = i + 1 })
    entries.value = next
    persist()
  }

  function updateCell(id: string, field: keyof AdjustmentEntry, value: unknown): void {
    if (isReadonly.value) return
    const idx = entries.value.findIndex((e) => e.id === id || e.rowId === id)
    if (idx === -1) return
    const row = { ...entries.value[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') {
      row[field] = parseNum(value)
    } else if (field === 'category') {
      row.category = String(value ?? '账项调整')
      row.entryType = row.category === '报表调整' ? 'RJE' : 'AJE'
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
      row.category = row.entryType === 'RJE' ? '报表调整' : '账项调整'
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const acc = G5_LTR_ACCOUNTS.find((a) => a.code === row.accountCode)
      if (acc) row.accountName = acc.name
    } else if (field === 'accountName') {
      row.accountName = String(value ?? '')
      const acc = G5_LTR_ACCOUNTS.find((a) => a.name === row.accountName)
      if (acc) row.accountCode = acc.code
    } else if (field === 'description' || field === 'summary') {
      row.description = String(value ?? '')
      row.summary = row.description
    } else if (field === 'seq' || field === 'id' || field === 'rowId') {
      return
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    const next = [...entries.value]
    next[idx] = row
    entries.value = next
    persist()
  }

  /** 直接回写 G5-1-rows（审定表未挂载也能落库）+ 发事件 */
  function confirmWriteback(): boolean {
    if (isReadonly.value) return false
    if (entries.value.length === 0) {
      ElMessage.warning('暂无调整分录')
      return false
    }
    if (!isBalanced.value) {
      ElMessage.error('借贷不平衡，无法确认回写')
      return false
    }

    const nets = writebackNets.value

    if (opts?.allResponses && (opts.saveImmediate || opts.debouncedSave)) {
      try {
        const raw = readCanonicalRaw(opts.allResponses.value.get(G5_1_ROWS_KEY))
        let store: any = {}
        if (raw) {
          try { store = JSON.parse(raw) } catch { store = {} }
        }
        store = patchWritebackIntoStore(store, nets)
        const payload = buildCanonicalPayload(G5_1_ROWS_KEY, store)
        opts.allResponses.value.set(G5_1_ROWS_KEY, payload)
        if (opts.saveImmediate) {
          void opts.saveImmediate(G5_1_ROWS_KEY, payload)
        } else {
          opts.debouncedSave?.(G5_1_ROWS_KEY, payload)
        }
      } catch {
        /* silent */
      }
    }

    try {
      window.dispatchEvent(new CustomEvent('g5:adjustment-confirmed', {
        detail: {
          accountCode: G5_ACCOUNT_CODE,
          netAje: nets.gross.aje,
          netRje: nets.gross.rje,
          rowId: WRITEBACK_ROW_ID,
          writebacks: nets,
          rowCount: entries.value.length,
        },
      }))
    } catch { /* silent */ }

    const parts = [
      `原值 AJE ${nets.gross.aje.toFixed(2)}/RJE ${nets.gross.rje.toFixed(2)}`,
      `坏账 AJE ${nets.provision.aje.toFixed(2)}/RJE ${nets.provision.rje.toFixed(2)}`,
      `一年内 AJE ${nets.oneYear.aje.toFixed(2)}/RJE ${nets.oneYear.rje.toFixed(2)}`,
    ]
    ElMessage.success(`已确认回写 G5-1（${parts.join('；')}）`)
    return true
  }

  if (opts?.allResponses) {
    watch(() => readStored(), () => loadEntries(), { immediate: true })
  }

  onMounted(() => {
    if (opts?.allResponses && entries.value.length === 0) loadEntries()
  })

  return {
    entries,
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    ajeTotal,
    rjeTotal,
    writebackNets,
    netAjeToG5,
    netRjeToG5,
    addEntry,
    removeEntry,
    updateCell,
    loadFromArray,
    loadEntries,
    persist,
    confirmWriteback,
    categoryOptions: CATEGORY_OPTIONS,
    accountOptions: G5_LTR_ACCOUNTS,
    STORAGE_KEY,
    WRITEBACK_ROW_ID,
  }
}
