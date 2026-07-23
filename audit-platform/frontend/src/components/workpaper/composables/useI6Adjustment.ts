/**
 * useI6Adjustment — I6-3 研发费用调整分录汇总
 *
 * 对齐致同 Excel「研发费用调整分录汇总表 I6-3」：
 * 调整事项说明 / 类别(账项·报表·其他) / 报表项目 / 科目名称 / 附注项目 /
 * 借方调整金额 / 贷方调整金额 / 索引 / 备注
 *
 * 联动：
 * - i6:adjustment-writeback → I6-1 审定表 AJE/RJE
 * - 中央调整分录模块双向同步（含 6602 的完整分录组）
 * - a13:push-misstatement（账项调整）
 * - 兼容旧存档（category=AJE/RJE, debit/credit）
 */
import {
  ref,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  getCurrentInstance,
  type Ref,
  type ComputedRef,
} from 'vue'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import {
  categoryFromLegacy,
  entryTypeFromCategory,
  isI6ExpenseAccount,
} from './i6AdjustmentModel'

export type I6AdjCategory = '账项调整' | '报表调整' | '其他'

export interface I6AdjustmentRow {
  rowId: string
  seq: number
  description: string
  category: I6AdjCategory | string
  entryType: 'AJE' | 'RJE' | ''
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 兼容旧字段 */
  debit?: number
  credit?: number
  sourceGroupId?: string
}

const ROWS_KEY = 'I6-3-rows'
export const NOTE_KEY = 'I6-3-audit-note'
export const CONCLUSION_KEY = 'I6-3-audit-conclusion'
const AJE_NET_KEY = 'I6-3-aje-net'
const RJE_NET_KEY = 'I6-3-rje-net'
const WP_CODE = 'I6'
const BALANCE_TOLERANCE = 0.01

const I6_RELATED_PREFIXES = ['6602', '5301', '5602', '1717', '1002', '2202', '2211', '1123', '1221']

export const I6_CATEGORY_OPTIONS: readonly I6AdjCategory[] = ['账项调整', '报表调整', '其他']

export const I6_ADJ_ACCOUNT_OPTIONS = [
  { code: '6602', name: '研发费用' },
  { code: '5301', name: '研发费用' },
  { code: '5602', name: '研发费用' },
  { code: '1717', name: '开发支出' },
  { code: '1002', name: '银行存款' },
  { code: '2202', name: '应付账款' },
  { code: '2211', name: '应付职工薪酬' },
  { code: '1123', name: '预付账款' },
  { code: '1221', name: '其他应收款' },
] as const

function generateRowId(): string {
  return `i6-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function parseAmt(v: unknown): number {
  if (v == null || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function isI6RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return I6_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function reportItemForAccount(code: string): string {
  if (isI6ExpenseAccount(code)) return '研发费用'
  if (code.startsWith('1717')) return '开发支出'
  return ''
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

function categoryFromEntryType(et: 'AJE' | 'RJE'): I6AdjCategory {
  return et === 'RJE' ? '报表调整' : '账项调整'
}

function resolveAccountCode(raw: any): string {
  if (raw.accountCode) return String(raw.accountCode)
  const name = String(raw.accountName || raw.account || '')
  const known = I6_ADJ_ACCOUNT_OPTIONS.find((o) => o.name === name || name.includes(o.name))
  return known?.code || '6602'
}

export function resolveI6AuditYear(opts: {
  propYear?: number | null | undefined
  allResponses?: Map<string, any> | null
  now?: Date
}): number {
  const prop = Number(opts.propYear)
  if (Number.isFinite(prop) && prop >= 1900) return Math.trunc(prop)
  if (opts.allResponses) {
    for (const key of ['I6-cutoff-date', 'I6-5-sample-criteria', 'I6-bs-date']) {
      const item = opts.allResponses.get(key)
      const raw = item?.remark ?? item?.conclusion ?? item
      if (!raw) continue
      const text = typeof raw === 'string' ? raw : JSON.stringify(raw)
      const m = text.match(/(\d{4})/)
      if (m) {
        const y = Number(m[1])
        if (Number.isFinite(y) && y >= 1900) return y
      }
    }
  }
  return (opts.now ?? new Date()).getFullYear()
}

export function useI6Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const rows = ref<I6AdjustmentRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const lastPushMsg = ref('')

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion ?? item
    if (!raw) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return String(item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '') ?? '')
  }

  function _normalizeRow(raw: any, idx: number): I6AdjustmentRow {
    const category = categoryFromLegacy(raw) as I6AdjCategory
    const entryType = entryTypeFromCategory(category)
    const accountCode = resolveAccountCode(raw)
    const known = I6_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    return {
      rowId: raw.rowId || generateRowId(),
      seq: idx + 1,
      description: String(raw.description ?? raw.summary ?? ''),
      category,
      entryType,
      reportItem: String(raw.reportItem ?? (reportItemForAccount(accountCode) || '研发费用')),
      accountCode,
      accountName: String(raw.accountName || raw.account || known?.name || '研发费用'),
      noteItem: String(raw.noteItem ?? ''),
      debitAmount,
      creditAmount,
      indexRef: String(raw.indexRef ?? raw.refIndex ?? 'I6-3'),
      remark: String(raw.remark ?? ''),
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I6AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    rows.value = Array.isArray(parsed) ? parsed.map((r, i) => _normalizeRow(r, i)) : []
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, { key: string; description: string; entryType: string; debit: number; credit: number }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || '').trim() || r.rowId
      const key = `${et}||${desc}`
      const g = groups.get(key) || { key, description: desc, entryType: et, debit: 0, credit: 0 }
      g.debit += r.debitAmount
      g.credit += r.creditAmount
      groups.set(key, g)
    }
    return [...groups.values()]
      .map((g) => ({ ...g, diff: g.debit - g.credit, isBalanced: Math.abs(g.debit - g.credit) < BALANCE_TOLERANCE }))
      .filter((g) => !g.isBalanced && (Math.abs(g.debit) > 0.005 || Math.abs(g.credit) > 0.005))
  })

  function _netsFromList(list: I6AdjustmentRow[]) {
    let ajeNet = 0
    let rjeNet = 0
    for (const r of list) {
      if (!isI6ExpenseAccount(r.accountCode, r.accountName)) continue
      const net = r.debitAmount - r.creditAmount
      if (r.category === '报表调整' || r.entryType === 'RJE') rjeNet += net
      else ajeNet += net
    }
    return { ajeNet, rjeNet }
  }

  const ajeNet = computed(() => _netsFromList(rows.value).ajeNet)
  const rjeNet = computed(() => _netsFromList(rows.value).rjeNet)

  function _writeNets(n: ReturnType<typeof _netsFromList>) {
    if (!onSave) return
    for (const [key, val] of [[AJE_NET_KEY, n.ajeNet], [RJE_NET_KEY, n.rjeNet]] as const) {
      onSave(key, val)
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, { ...existing, item_id: key, remark: String(val) })
    }
  }

  function _persist(list?: I6AdjustmentRow[]): void {
    if (!onSave) return
    const next = list ?? rows.value
    const shaped = _toPersistShape(next)
    const normalized = shaped.map((r, i) => _normalizeRow(r, i))
    rows.value = normalized
    onSave(ROWS_KEY, shaped)
    const existing = allResponses.value.get(ROWS_KEY) || { item_id: ROWS_KEY, conclusion: null, remark: null }
    allResponses.value.set(ROWS_KEY, { ...existing, item_id: ROWS_KEY, remark: JSON.stringify(shaped) })
    _writeNets(_netsFromList(normalized))
  }

  function addRow(partial?: Partial<I6AdjustmentRow>): void {
    if (isReadonly.value) return
    const category = (partial?.category as I6AdjCategory) || '账项调整'
    rows.value.push(_normalizeRow({
      rowId: generateRowId(),
      description: partial?.description || '',
      category,
      entryType: entryTypeFromCategory(category),
      reportItem: partial?.reportItem || '研发费用',
      accountCode: partial?.accountCode || '6602',
      accountName: partial?.accountName || '研发费用',
      noteItem: partial?.noteItem || '',
      debitAmount: partial?.debitAmount ?? 0,
      creditAmount: partial?.creditAmount ?? 0,
      indexRef: partial?.indexRef || 'I6-3',
      remark: partial?.remark || '',
    }, rows.value.length))
    _persist()
  }

  function addDraftRow(partial: Partial<I6AdjustmentRow> & { description: string }): void {
    if (isReadonly.value) return
    addRow({ ...partial, remark: partial.remark || '来源:检查异常一键生成' })
  }

  function importRows(rawRows: any[]): void {
    if (isReadonly.value || !rawRows?.length) return
    rows.value = rawRows.map((r, i) => _normalizeRow(r, i))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (field === 'category') {
      row.category = String(value ?? '账项调整')
      row.entryType = entryTypeFromCategory(String(row.category))
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const known = I6_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
      if (!row.reportItem) row.reportItem = reportItemForAccount(row.accountCode)
    } else if (field === 'debit' || field === 'debitAmount') {
      row.debitAmount = parseAmt(value)
    } else if (field === 'credit' || field === 'creditAmount') {
      row.creditAmount = parseAmt(value)
    } else if (field in row) {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function publishAdjustment(): void {
    const nets = _netsFromList(rows.value)
    const payload = {
      wp_code: WP_CODE,
      wpCode: WP_CODE,
      source: 'I6-3',
      rows: rows.value,
      entries: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
      ajeNet: nets.ajeNet,
      rjeNet: nets.rjeNet,
    }
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(nets.ajeNet),
        accountCode: '6602',
        accountName: '研发费用',
        description: `I6-3 研发费用账项净额 ${nets.ajeNet}`,
        ...payload,
      } as any)
      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
      window.dispatchEvent(new CustomEvent('i6:adjustment-writeback', { detail: payload }))
    } catch { /* silent */ }
  }

  function pushToA13(rowIds?: string[]): void {
    const targets = rowIds?.length
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value.filter((r) => r.category !== '报表调整' && (r.debitAmount || r.creditAmount))
    if (!targets.length) {
      lastPushMsg.value = '无可推送行（报表调整默认不推，或未填金额）'
      return
    }
    const items = targets.map((r) => ({
      wpCode: WP_CODE,
      entryType: entryTypeFromCategory(String(r.category)),
      description: r.description,
      reportItem: r.reportItem,
      accountCode: r.accountCode,
      accountName: r.accountName,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      indexRef: r.indexRef || 'I6-3',
    }))
    eventBus.emit('a13:push-misstatement', { items, wpCode: WP_CODE, source: 'I6-3', timestamp: Date.now() })
    window.dispatchEvent(new CustomEvent('a13:push-misstatement', {
      detail: { wpCode: WP_CODE, source: 'I6-3', entries: items },
    }))
    lastPushMsg.value = `已推送 ${targets.length} 行至 A13`
  }

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    if (!isBalanced.value) {
      lastSyncMsg.value = '借贷不平衡，无法推送至调整分录模块'
      return 0
    }
    const year = resolveI6AuditYear({ propYear: params.auditYear?.value, allResponses: allResponses.value })
    const pending = rows.value.filter(
      (r) => !r.sourceGroupId && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) {
      lastSyncMsg.value = '无可推送分录（可能已同步或未填金额）'
      return 0
    }

    const groups = new Map<string, I6AdjustmentRow[]>()
    for (const row of pending) {
      const key = `${row.entryType || entryTypeFromCategory(String(row.category))}||${row.description || row.rowId}`
      groups.set(key, [...(groups.get(key) || []), row])
    }

    let pushed = 0
    let list = [...rows.value]
    for (const lines of groups.values()) {
      const debit = lines.reduce((s, r) => s + r.debitAmount, 0)
      const credit = lines.reduce((s, r) => s + r.creditAmount, 0)
      if (Math.abs(debit - credit) >= BALANCE_TOLERANCE) continue
      try {
        const et = entryTypeFromCategory(String(lines[0].category))
        const res: any = await api.post(
          adjPaths.create(projectId),
          {
            adjustment_type: et === 'RJE' ? 'rje' : 'aje',
            year,
            company_code: 'default',
            description: `[I6] ${lines[0].description || '研发费用调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '6602',
              account_name: r.accountName || undefined,
              debit_amount: r.debitAmount,
              credit_amount: r.creditAmount,
            })),
          },
          { _silent: true } as any,
        )
        const groupId = res?.entry_group_id ?? res?.data?.entry_group_id ?? res?.id
        if (!groupId) continue
        const id = String(groupId)
        list = list.map((r) => lines.some((l) => l.rowId === r.rowId) ? { ...r, sourceGroupId: id } : r)
        pushed++
      } catch {
        lastSyncMsg.value = '底稿已保存，但部分分录未能同步至集中模块'
      }
    }
    if (pushed > 0) {
      _persist(list)
      publishAdjustment()
      eventBus.emit('adjustment:updated')
      lastSyncMsg.value = `已推送 ${pushed} 笔至调整分录模块`
    }
    return pushed
  }

  async function syncFromAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = resolveI6AuditYear({ propYear: params.auditYear?.value, allResponses: allResponses.value })
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: I6AdjustmentRow[] = []
      const existingGroupIds = new Set(rows.value.map((r) => r.sourceGroupId).filter(Boolean) as string[])

      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isI6RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        const hasCore = lines.some((li: any) =>
          isI6ExpenseAccount(String(li.standard_account_code || li.account_code || ''), li.account_name),
        )
        if (!hasCore) continue

        const groupId = String(item.entry_group_id || item.id || '')
        if (groupId && existingGroupIds.has(groupId)) continue

        const et = entryTypeFromModule(item.adjustment_type || item.type)
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(/^\[I6\]\s*/, '')
        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          imported.push(_normalizeRow({
            description: desc,
            category: categoryFromEntryType(et),
            entryType: et,
            accountCode,
            accountName: li.account_name || '',
            debitAmount: li.debit_amount,
            creditAmount: li.credit_amount,
            indexRef: '调整分录模块',
            remark: '来自调整分录模块',
            sourceGroupId: groupId || undefined,
            reportItem: reportItemForAccount(accountCode),
            noteItem: '研发费用',
          }, imported.length))
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无含 6602 研发费用的相关分录'
        return 0
      }
      _persist([...rows.value, ...imported])
      publishAdjustment()
      lastSyncMsg.value = `已从模块同步 ${imported.length} 行`
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败，请稍后重试'
      return 0
    } finally {
      syncing.value = false
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(text: string): void {
    auditConclusion.value = text
    onSave?.(CONCLUSION_KEY, text)
  }

  function saveAndPublish(): void {
    _persist()
    publishAdjustment()
  }

  function suggestConclusionTemplate(): string {
    if (!rows.value.length) return '本期研发费用未见需调整事项，调整分录汇总表无分录。'
    if (!isBalanced.value) return '调整分录尚未借贷平衡，请先修正后再形成结论。'
    return `上述研发费用相关调整分录依据充分、整表借贷平衡；6602 账项净额 ${ajeNet.value.toLocaleString('zh-CN')}、报表重分类净额 ${rjeNet.value.toLocaleString('zh-CN')}，已回写 I6-1 / 可推送 A13。`
  }

  function onModuleUpdated() {
    if (!isReadonly.value && params.projectId.value) void syncFromAdjustmentModule()
  }

  if (getCurrentInstance()) {
    onMounted(() => { eventBus.on('adjustment:updated', onModuleUpdated) })
    onBeforeUnmount(() => { eventBus.off('adjustment:updated', onModuleUpdated) })
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    groupBalanceIssues,
    ajeNet,
    rjeNet,
    addRow,
    addDraftRow,
    importRows,
    removeRow,
    updateCell,
    publishAdjustment,
    pushToA13,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    saveNote,
    saveConclusion,
    saveAndPublish,
    suggestConclusionTemplate,
    I6_CATEGORY_OPTIONS,
    I6_ADJ_ACCOUNT_OPTIONS,
  }
}

export default useI6Adjustment
