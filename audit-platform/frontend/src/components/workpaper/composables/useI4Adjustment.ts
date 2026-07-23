/**
 * useI4Adjustment — I4-3 长期待摊费用调整分录汇总
 *
 * 对齐源 xlsx「长期待摊费用调整分录汇总表 I4-3」：
 * 调整事项说明 / 类别(账项·报表·其他) / 报表项目 / 科目名称 / 附注项目 /
 * 借方调整金额 / 贷方调整金额 / 索引 / 备注
 *
 * 联动：
 * - EventBus adjustment:created → I4-1 审定表 AJE/RJE（1801 净额）
 * - 中央调整分录模块双向同步（含 1801 的分录组）
 * - a13:push-misstatement（账项调整）
 * - 可从常见场景 / I4-5 异常草稿生成分录
 */
import {
  ref,
  computed,
  watch,
  type Ref,
  type ComputedRef,
} from 'vue'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'

export type I4AdjCategory = '账项调整' | '报表调整' | '其他'

export interface I4AdjustmentRow {
  rowId: string
  seq: number
  description: string
  category: I4AdjCategory | string
  entryType: 'AJE' | 'RJE' | ''
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 明细项目名（供 I4-1 / I4-2 精确匹配） */
  projectName: string
  /** 兼容旧字段 */
  summary?: string
  debit?: number
  credit?: number
  sourceGroupId?: string
}

const ROWS_KEY = 'I4-3-rows'
const NOTE_KEY = 'I4-3-audit-note'
const CONCLUSION_KEY = 'I4-3-audit-conclusion'
/** 兼容旧键 */
const LEGACY_NOTE_KEY = 'I4-adjustment-audit-note'
const LEGACY_CONCLUSION_KEY = 'I4-adjustment-audit-conclusion'
const AJE_NET_KEY = 'I4-3-aje-net'
const RJE_NET_KEY = 'I4-3-rje-net'
const WP_CODE = 'I4'
const BALANCE_TOLERANCE = 0.01

/** 中央模块：含这些科目前缀视为长期待摊相关 */
const I4_RELATED_PREFIXES = ['1801', '6602', '5602', '6401', '6402', '1002', '2202', '1123', '1221']

export const I4_CATEGORY_OPTIONS: readonly I4AdjCategory[] = ['账项调整', '报表调整', '其他']

export const I4_ADJ_ACCOUNT_OPTIONS = [
  { code: '1801', name: '长期待摊费用' },
  { code: '1461', name: '一年内到期的非流动资产' },
  { code: '6602', name: '管理费用' },
  { code: '5602', name: '管理费用（小企业）' },
  { code: '6401', name: '主营业务成本' },
  { code: '6402', name: '其他业务成本' },
  { code: '1002', name: '银行存款' },
  { code: '2202', name: '应付账款' },
  { code: '1123', name: '预付账款' },
  { code: '1221', name: '其他应收款' },
] as const

function generateRowId(): string {
  return `i4-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function parseAmt(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function entryTypeFromCategory(category: string): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

export function categoryFromLegacy(raw: any): I4AdjCategory {
  const c = String(raw?.category ?? '')
  if (c === '报表调整' || c === '账项调整' || c === '其他') return c
  if (raw?.entryType === 'RJE') return '报表调整'
  return '账项调整'
}

function isLtpaAccount(code: string): boolean {
  return String(code || '').startsWith('1801')
}

function isI4RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return I4_RELATED_PREFIXES.some((p) => c.startsWith(p))
}

function reportItemForAccount(code: string): string {
  if (isLtpaAccount(code)) return '长期待摊费用'
  if (String(code).startsWith('6602') || String(code).startsWith('5602')) return '管理费用'
  if (String(code).startsWith('6401')) return '营业成本'
  if (String(code).startsWith('6402')) return '其他业务成本'
  return ''
}

/** 费用化重分类草稿：借费用 / 贷长期待摊 */
export function buildI4ExpenseReclassDraft(opts: {
  projectName: string
  amount: number
  expenseAccountCode?: string
  expenseAccountName?: string
  indexRef?: string
}): I4AdjustmentRow[] {
  const amt = Math.round((opts.amount || 0) * 100) / 100
  if (amt <= 0.005) return []
  const desc = `长期待摊费用化重分类-${opts.projectName || '未命名项目'}`
  const idx = opts.indexRef || 'I4-5'
  const expCode = opts.expenseAccountCode || '6602'
  const known = I4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === expCode)
  const expName = opts.expenseAccountName || known?.name || '管理费用'
  const projectName = String(opts.projectName || '').trim()
  return [
    {
      rowId: generateRowId(),
      seq: 1,
      description: desc,
      projectName,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: reportItemForAccount(expCode) || '管理费用',
      accountCode: expCode,
      accountName: expName,
      noteItem: '长期待摊费用',
      debitAmount: amt,
      creditAmount: 0,
      indexRef: idx,
      remark: '资本化不当/应费用化项目重分类',
    },
    {
      rowId: generateRowId(),
      seq: 2,
      description: desc,
      projectName,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '长期待摊费用',
      accountCode: '1801',
      accountName: '长期待摊费用',
      noteItem: '长期待摊费用',
      debitAmount: 0,
      creditAmount: amt,
      indexRef: idx,
      remark: '冲减长期待摊账面',
    },
  ]
}

/** 补提摊销草稿：借费用 / 贷长期待摊 */
export function buildI4AmortSupplementDraft(opts: {
  projectName: string
  amount: number
  indexRef?: string
}): I4AdjustmentRow[] {
  const amt = Math.round((opts.amount || 0) * 100) / 100
  if (amt <= 0.005) return []
  const desc = `补提长期待摊摊销-${opts.projectName || '未命名项目'}`
  const idx = opts.indexRef || 'I4-6'
  const projectName = String(opts.projectName || '').trim()
  return [
    {
      rowId: generateRowId(),
      seq: 1,
      description: desc,
      projectName,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '管理费用',
      accountCode: '6602',
      accountName: '管理费用',
      noteItem: '长期待摊费用',
      debitAmount: amt,
      creditAmount: 0,
      indexRef: idx,
      remark: '摊销测算与账面差异补提',
    },
    {
      rowId: generateRowId(),
      seq: 2,
      description: desc,
      projectName,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '长期待摊费用',
      accountCode: '1801',
      accountName: '长期待摊费用',
      noteItem: '长期待摊费用',
      debitAmount: 0,
      creditAmount: amt,
      indexRef: idx,
      remark: '贷记长期待摊（摊销减少账面）',
    },
  ]
}

/**
 * 一年内到期重分类 RJE 草稿：借一年内到期的非流动资产 / 贷长期待摊
 * 注：以摊销为后续计量的项目通常不强制重分类，草稿须人工确认政策后入账。
 */
export function buildI4CurrentPortionReclassDraft(opts: {
  projectName: string
  amount: number
  remainingMonths?: number
  indexRef?: string
}): I4AdjustmentRow[] {
  const amt = Math.round((opts.amount || 0) * 100) / 100
  if (amt <= 0.005) return []
  const months = opts.remainingMonths != null ? `剩余${opts.remainingMonths}月` : '剩余≤12月'
  const desc = `一年内到期重分类-${opts.projectName || '未命名项目'}`
  const idx = opts.indexRef || 'I4-2'
  const projectName = String(opts.projectName || '').trim()
  return [
    {
      rowId: generateRowId(),
      seq: 1,
      description: desc,
      projectName,
      category: '报表调整',
      entryType: 'RJE',
      reportItem: '一年内到期的非流动资产',
      accountCode: '1461',
      accountName: '一年内到期的非流动资产',
      noteItem: '长期待摊费用',
      debitAmount: amt,
      creditAmount: 0,
      indexRef: idx,
      remark: `${months}；请确认是否适用强制重分类（自然摊销消耗通常可不重分类）`,
    },
    {
      rowId: generateRowId(),
      seq: 2,
      description: desc,
      projectName,
      category: '报表调整',
      entryType: 'RJE',
      reportItem: '长期待摊费用',
      accountCode: '1801',
      accountName: '长期待摊费用',
      noteItem: '长期待摊费用',
      debitAmount: 0,
      creditAmount: amt,
      indexRef: idx,
      remark: '贷记长期待摊（报表重分类转出）',
    },
  ]
}

export function useI4Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const rows = ref<I4AdjustmentRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const lastPushMsg = ref('')

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try {
      return typeof raw === 'string' ? JSON.parse(raw) : raw
    } catch {
      return null
    }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return String(item?.remark ?? item?.conclusion ?? '')
  }

  function _normalizeRow(raw: any, idx: number): I4AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const accountCode = String(raw.accountCode ?? '1801')
    const known = I4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    const description = String(raw.description ?? raw.summary ?? '')
    return {
      rowId: raw.rowId || generateRowId(),
      seq: idx + 1,
      description,
      category,
      entryType,
      reportItem: String(raw.reportItem ?? reportItemForAccount(accountCode)),
      accountCode,
      accountName: String(raw.accountName || known?.name || ''),
      noteItem: String(raw.noteItem ?? (isLtpaAccount(accountCode) ? '长期待摊费用' : '')),
      debitAmount,
      creditAmount,
      indexRef: String(raw.indexRef ?? raw.refIndex ?? ''),
      remark: String(raw.remark ?? ''),
      projectName: String(raw.projectName ?? raw.investee ?? ''),
      summary: description,
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I4AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      summary: r.description,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY) || _getString(LEGACY_NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY) || _getString(LEGACY_CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, {
      key: string
      description: string
      entryType: string
      debit: number
      credit: number
      rowCount: number
    }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || '').trim() || r.rowId
      const key = `${et}||${desc}`
      const g = groups.get(key) || {
        key, description: desc, entryType: et, debit: 0, credit: 0, rowCount: 0,
      }
      g.debit += r.debitAmount
      g.credit += r.creditAmount
      g.rowCount += 1
      groups.set(key, g)
    }
    return [...groups.values()]
      .map((g) => {
        const diff = g.debit - g.credit
        return { ...g, diff, isBalanced: Math.abs(diff) < BALANCE_TOLERANCE }
      })
      .filter((g) =>
        !g.isBalanced && (Math.abs(g.debit) > 0.005 || Math.abs(g.credit) > 0.005),
      )
  })

  function _netsFromList(list: I4AdjustmentRow[]) {
    let ajeNet = 0
    let rjeNet = 0
    let ltpaAje = 0
    let ltpaRje = 0
    for (const r of list) {
      const net = r.debitAmount - r.creditAmount
      const isRje = r.category === '报表调整' || r.entryType === 'RJE'
      if (isRje) rjeNet += net
      else ajeNet += net
      if (isLtpaAccount(r.accountCode)) {
        if (isRje) ltpaRje += net
        else ltpaAje += net
      }
    }
    return { ajeNet, rjeNet, ltpaAje, ltpaRje }
  }

  const ajeNet = computed(() => _netsFromList(rows.value).ajeNet)
  const rjeNet = computed(() => _netsFromList(rows.value).rjeNet)
  const ltpaAjeNet = computed(() => _netsFromList(rows.value).ltpaAje)
  const ltpaRjeNet = computed(() => _netsFromList(rows.value).ltpaRje)

  const projectNameOptions = computed(() => {
    const names = new Set<string>()
    for (const r of rows.value) {
      if (r.projectName?.trim()) names.add(r.projectName.trim())
    }
    const detail = _getJson('I4-2-rows')
    if (Array.isArray(detail)) {
      for (const d of detail) {
        const n = String(d.projectName ?? d.name ?? '').trim()
        if (n) names.add(n)
      }
    }
    return [...names]
  })

  function _writeNets(n: ReturnType<typeof _netsFromList>) {
    if (!onSave) return
    onSave(AJE_NET_KEY, n.ltpaAje)
    onSave(RJE_NET_KEY, n.ltpaRje)
    for (const [key, val] of [[AJE_NET_KEY, n.ltpaAje], [RJE_NET_KEY, n.ltpaRje]] as const) {
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, { ...existing, item_id: key, remark: String(val) })
    }
  }

  function _persist(list?: I4AdjustmentRow[]): void {
    if (!onSave) return
    const next = list ?? rows.value
    const shaped = _toPersistShape(next)
    const normalized = shaped.map((r, i) => _normalizeRow(r, i))
    rows.value = normalized
    onSave(ROWS_KEY, shaped)
    const existing = allResponses.value.get(ROWS_KEY) || { item_id: ROWS_KEY, conclusion: null, remark: null }
    allResponses.value.set(ROWS_KEY, {
      ...existing,
      item_id: ROWS_KEY,
      remark: JSON.stringify(shaped),
    })
    _writeNets(_netsFromList(normalized))
    try {
      window.dispatchEvent(new CustomEvent('i4:adjustments-changed', {
        detail: { source: 'I4-3', rowCount: normalized.length },
      }))
    } catch { /* silent */ }
  }

  function addRow(partial?: Partial<I4AdjustmentRow>): void {
    if (isReadonly.value) return
    const category = (partial?.category as I4AdjCategory) || '账项调整'
    const accountCode = partial?.accountCode || '1801'
    const known = I4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    rows.value.push(_normalizeRow({
      rowId: generateRowId(),
      description: partial?.description || '',
      projectName: partial?.projectName || '',
      category,
      entryType: entryTypeFromCategory(category),
      reportItem: partial?.reportItem || reportItemForAccount(accountCode),
      accountCode,
      accountName: partial?.accountName || known?.name || '长期待摊费用',
      noteItem: partial?.noteItem || '长期待摊费用',
      debitAmount: partial?.debitAmount ?? 0,
      creditAmount: partial?.creditAmount ?? 0,
      indexRef: partial?.indexRef || '',
      remark: partial?.remark || '',
    }, rows.value.length))
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
      const known = I4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
      if (!row.reportItem) row.reportItem = reportItemForAccount(row.accountCode)
      if (isLtpaAccount(row.accountCode) && !row.noteItem) row.noteItem = '长期待摊费用'
    } else if (field === 'description' || field === 'summary') {
      row.description = String(value ?? '')
    } else if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = parseAmt(value)
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
      source: 'I4-3',
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
      ajeNet: nets.ltpaAje,
      rjeNet: nets.ltpaRje,
      totalAje: nets.ajeNet,
      totalRje: nets.rjeNet,
    }
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(nets.ltpaAje),
        accountCode: '1801',
        accountName: '长期待摊费用',
        description: `I4-3 长期待摊账项净额 ${nets.ltpaAje}`,
        ...payload,
      } as any)
      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
    } catch {
      /* silent */
    }
  }

  function saveNote(): void {
    if (!onSave) return
    onSave(NOTE_KEY, auditNote.value)
  }

  function saveConclusion(): void {
    if (!onSave) return
    onSave(CONCLUSION_KEY, auditConclusion.value)
  }

  function saveAndSync(): void {
    _persist()
    saveNote()
    saveConclusion()
    publishAdjustment()
  }

  function pushToA13(rowIds?: string[]): void {
    const targets = rowIds?.length
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value.filter(
          (r) => r.category !== '报表调整' && (r.debitAmount || r.creditAmount),
        )
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
      debit: r.debitAmount,
      credit: r.creditAmount,
      indexRef: r.indexRef || 'I4-3',
    }))
    try {
      eventBus.emit('a13:push-misstatement', {
        items,
        wpCode: WP_CODE,
        source: 'I4-3',
        timestamp: Date.now(),
      })
      window.dispatchEvent(new CustomEvent('a13:push-misstatement', {
        detail: { wpCode: WP_CODE, source: 'I4-3', entries: items },
      }))
      lastPushMsg.value = `已推送 ${targets.length} 行至 A13`
    } catch {
      lastPushMsg.value = '推送失败'
    }
  }

  function resolveAuditYear(): number | null {
    const prop = params.auditYear?.value
    if (prop != null && Number.isFinite(Number(prop)) && Number(prop) >= 1900) {
      return Number(prop)
    }
    return null
  }

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    if (!isBalanced.value) {
      lastSyncMsg.value = '借贷不平衡，无法推送至调整分录模块'
      return 0
    }
    const year = resolveAuditYear() ?? new Date().getFullYear()
    const pending = rows.value.filter(
      (r) =>
        !r.sourceGroupId
        && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) {
      lastSyncMsg.value = '无可推送分录（可能已同步或未填金额）'
      return 0
    }

    const groups = new Map<string, I4AdjustmentRow[]>()
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
            description: `[I4] ${lines[0].description || '长期待摊调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '1801',
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
        list = list.map((r) =>
          lines.some((l) => l.rowId === r.rowId) ? { ...r, sourceGroupId: id } : r,
        )
        pushed++
      } catch {
        lastSyncMsg.value = '底稿已保存，但部分分录未能同步至集中模块'
      }
    }
    if (pushed > 0) {
      _persist(list)
      publishAdjustment()
      eventBus.emit('adjustment:updated')
      const skipped = groupBalanceIssues.value.length
      lastSyncMsg.value = skipped
        ? `已推送 ${pushed} 笔；另有 ${skipped} 组「调整事项」组内不平衡已跳过`
        : `已推送 ${pushed} 笔至调整分录模块`
    } else if (groupBalanceIssues.value.length) {
      lastSyncMsg.value = `无可推送：有 ${groupBalanceIssues.value.length} 组「调整事项」组内借贷不平衡`
    }
    return pushed
  }

  async function syncFromAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = resolveAuditYear() ?? new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: I4AdjustmentRow[] = []
      const existingGroupIds = new Set(
        rows.value.map((r) => r.sourceGroupId).filter(Boolean) as string[],
      )

      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isI4RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        const hasCore = lines.some((li: any) =>
          isLtpaAccount(String(li.standard_account_code || li.account_code || '')),
        )
        if (!hasCore) continue

        const groupId = String(item.entry_group_id || item.id || '')
        if (groupId && existingGroupIds.has(groupId)) continue

        const et = String(item.adjustment_type || item.type || '').toLowerCase().includes('rje')
          ? 'RJE'
          : 'AJE'
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[I4\]\s*/,
          '',
        )
        for (const li of lines) {
          const code = String(li.standard_account_code || li.account_code || '')
          imported.push(_normalizeRow({
            description: desc,
            category: et === 'RJE' ? '报表调整' : '账项调整',
            entryType: et,
            accountCode: code,
            accountName: li.account_name || '',
            debitAmount: parseAmt(li.debit_amount ?? li.debit),
            creditAmount: parseAmt(li.credit_amount ?? li.credit),
            indexRef: '调整分录模块',
            remark: '来自调整分录模块',
            sourceGroupId: groupId || undefined,
            reportItem: reportItemForAccount(code),
            noteItem: '长期待摊费用',
          }, imported.length))
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无含 1801 长期待摊的相关分录'
        return 0
      }
      _persist([...rows.value, ...imported])
      publishAdjustment()
      lastSyncMsg.value = `已从模块同步 ${imported.length} 行`
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败'
      return 0
    } finally {
      syncing.value = false
    }
  }

  /** 从 I4-6/I4-7 摊销差异生成补提草稿（跳过已有同说明） */
  function seedFromAmortDiff(diffs: Array<{ projectName: string; amount: number; indexRef?: string }>): number {
    if (isReadonly.value) return 0
    let added = 0
    const existingDescs = new Set(rows.value.map((r) => r.description))
    for (const d of diffs) {
      const lines = buildI4AmortSupplementDraft(d)
      if (!lines.length) continue
      if (existingDescs.has(lines[0].description)) continue
      rows.value.push(...lines.map((l, i) => _normalizeRow(l, rows.value.length + i)))
      existingDescs.add(lines[0].description)
      added += lines.length
    }
    if (added) _persist()
    return added
  }

  /** 费用化重分类草稿 */
  function seedExpenseReclass(opts: {
    projectName: string
    amount: number
    indexRef?: string
  }): number {
    if (isReadonly.value) return 0
    const lines = buildI4ExpenseReclassDraft(opts)
    if (!lines.length) return 0
    if (rows.value.some((r) => r.description === lines[0].description)) return 0
    rows.value.push(...lines.map((l, i) => _normalizeRow(l, rows.value.length + i)))
    _persist()
    return lines.length
  }

  /** 从 I4-2 一年内到期候选生成 RJE 草稿 */
  function seedCurrentPortionReclass(
    candidates: Array<{ projectName: string; amount: number; remainingMonths?: number; indexRef?: string }>,
  ): number {
    if (isReadonly.value) return 0
    let added = 0
    const existingDescs = new Set(rows.value.map((r) => r.description))
    for (const c of candidates) {
      const lines = buildI4CurrentPortionReclassDraft(c)
      if (!lines.length) continue
      if (existingDescs.has(lines[0].description)) continue
      rows.value.push(...lines.map((l, i) => _normalizeRow(l, rows.value.length + i)))
      existingDescs.add(lines[0].description)
      added += lines.length
    }
    if (added) _persist()
    return added
  }

  function suggestConclusionTemplate(): string {
    if (!rows.value.length) {
      return '本期长期待摊费用未见需调整事项，调整分录汇总表无分录。'
    }
    if (!isBalanced.value) {
      return '调整分录尚未借贷平衡，请先修正后再形成结论。'
    }
    const aje = ltpaAjeNet.value
    const rje = ltpaRjeNet.value
    return `上述长期待摊相关调整分录依据充分、整表借贷平衡；1801 账项净额 ${aje.toLocaleString('zh-CN')}、报表重分类净额 ${rje.toLocaleString('zh-CN')}，已回写 I4-1 / 可推送 A13。`
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
    ltpaAjeNet,
    ltpaRjeNet,
    projectNameOptions,
    categoryOptions: I4_CATEGORY_OPTIONS,
    accountOptions: [...I4_ADJ_ACCOUNT_OPTIONS],
    addRow,
    removeRow,
    updateCell,
    saveNote,
    saveConclusion,
    saveAndSync,
    publishAdjustment,
    pushToA13,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    seedFromAmortDiff,
    seedExpenseReclass,
    seedCurrentPortionReclass,
    suggestConclusionTemplate,
    load,
  }
}

export default useI4Adjustment
