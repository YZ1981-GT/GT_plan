/**
 * useI1Adjustment — I1-3 无形资产调整分录汇总
 *
 * 对齐源 xlsx「无形资产调整分录汇总表 I1-3」：
 * 调整事项说明 / 类别(账项·报表·其他) / 报表项目 / 科目名称 / 附注项目 /
 * 借方调整金额 / 贷方调整金额 / 索引 / 备注
 *
 * 联动：
 * - EventBus adjustment:created → I1 审定表 AJE/RJE
 * - 中央调整分录模块双向同步（1701/1702/1703 相关分录组）
 * - a13:push-misstatement（账项调整）
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

export type I1AdjCategory = '账项调整' | '报表调整' | '其他'

export interface I1AdjustmentRow {
  rowId: string
  seq: number
  description: string
  category: I1AdjCategory | string
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
  summary?: string
  debit?: number
  credit?: number
  sourceGroupId?: string
}

const ROWS_KEY = 'I1-3-rows'
const NOTE_KEY = 'I1-3-audit-note'
const CONCLUSION_KEY = 'I1-3-audit-conclusion'
const COST_AJE_KEY = 'I1-3-cost-aje-net'
const COST_RJE_KEY = 'I1-3-cost-rje-net'
const AMORT_AJE_KEY = 'I1-3-amort-aje-net'
const AMORT_RJE_KEY = 'I1-3-amort-rje-net'
const IMPAIR_AJE_KEY = 'I1-3-impair-aje-net'
const IMPAIR_RJE_KEY = 'I1-3-impair-rje-net'
const WP_CODE = 'I1'
const BALANCE_TOLERANCE = 0.01

/** 中央模块：含这些科目前缀视为无形资产相关 */
const I1_RELATED_PREFIXES = ['1701', '1702', '1703', '5601', '5602', '5301', '6115', '6602']

export const I1_CATEGORY_OPTIONS: readonly I1AdjCategory[] = ['账项调整', '报表调整', '其他']

export const I1_ADJ_ACCOUNT_OPTIONS = [
  { code: '1701', name: '无形资产' },
  { code: '1702', name: '累计摊销' },
  { code: '1703', name: '无形资产减值准备' },
  { code: '5601', name: '管理费用' },
  { code: '5602', name: '销售费用' },
  { code: '5301', name: '研发费用' },
  { code: '6602', name: '管理费用-摊销' },
  { code: '6115', name: '资产处置收益' },
  { code: '1002', name: '银行存款' },
  { code: '2202', name: '应付账款' },
  { code: '1221', name: '其他应收款' },
] as const

/** 从摊销期间截止日解析审计年度 */
export function yearFromPeriodResponses(
  allResponses?: Map<string, any> | null,
): number | null {
  if (!allResponses) return null
  for (const key of ['I1-amort-period', 'I1-11-period']) {
    const item = allResponses.get(key)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) continue
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      const end = String(parsed?.periodEnd || '')
      const m = end.match(/^(\d{4})/)
      if (m) {
        const y = Number(m[1])
        if (Number.isFinite(y) && y >= 1900) return y
      }
    } catch {
      /* continue */
    }
  }
  return null
}

/**
 * 审计年度兜底链：props.year → scaffold/runtime → 期间截止日年份 → 日历年
 */
export function resolveI1AuditYear(opts: {
  propYear?: number | null | undefined
  runtimeYear?: number | string | null | undefined
  allResponses?: Map<string, any> | null
  now?: Date
}): number {
  const prop = Number(opts.propYear)
  if (Number.isFinite(prop) && prop >= 1900) return Math.trunc(prop)

  const runtime = Number(opts.runtimeYear)
  if (Number.isFinite(runtime) && runtime >= 1900) return Math.trunc(runtime)

  const fromPeriod = yearFromPeriodResponses(opts.allResponses)
  if (fromPeriod != null) return fromPeriod

  return (opts.now ?? new Date()).getFullYear()
}

function generateRowId(): string {
  return `i1a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function categoryFromLegacy(raw: {
  category?: string
  entryType?: string
}): I1AdjCategory {
  const cat = String(raw.category || '').trim()
  if ((I1_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat as I1AdjCategory
  if (cat === '重分类调整') return '报表调整'
  const legacy = String(raw.entryType || '').toUpperCase()
  if (legacy === 'RJE' || cat.includes('报表') || cat.includes('重分类')) return '报表调整'
  if (cat.includes('其他')) return '其他'
  return '账项调整'
}

export function entryTypeFromCategory(category: string): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

function parseAmt(v: unknown): number {
  if (v == null || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function isI1RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return I1_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function isCostAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1701' || c.startsWith('1701')
}

function isAmortAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1702' || c.startsWith('1702')
}

function isImpairAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1703' || c.startsWith('1703')
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

function categoryFromEntryType(et: 'AJE' | 'RJE'): I1AdjCategory {
  return et === 'RJE' ? '报表调整' : '账项调整'
}

function reportItemForAccount(code: string): string {
  if (isCostAccount(code)) return '无形资产'
  if (isAmortAccount(code)) return '累计摊销'
  if (isImpairAccount(code)) return '无形资产减值准备'
  return ''
}

export function useI1Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const rows = ref<I1AdjustmentRow[]>([])
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

  function _normalizeRow(raw: any, idx: number): I1AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const accountCode = String(raw.accountCode ?? '')
    const known = I1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
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
      noteItem: String(raw.noteItem ?? ''),
      debitAmount,
      creditAmount,
      indexRef: String(raw.indexRef ?? raw.refIndex ?? ''),
      remark: String(raw.remark ?? ''),
      summary: description,
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I1AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
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
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  /** 按「调整事项+类型」分组的借贷平衡（与推送分组键一致） */
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
        key,
        description: desc,
        entryType: et,
        debit: 0,
        credit: 0,
        rowCount: 0,
      }
      g.debit += r.debitAmount
      g.credit += r.creditAmount
      g.rowCount += 1
      groups.set(key, g)
    }
    return [...groups.values()]
      .map((g) => {
        const diff = g.debit - g.credit
        return {
          ...g,
          diff,
          isBalanced: Math.abs(diff) < BALANCE_TOLERANCE,
        }
      })
      .filter((g) =>
        !g.isBalanced
        && (Math.abs(g.debit) > 0.005 || Math.abs(g.credit) > 0.005),
      )
  })

  function _netsFromList(list: I1AdjustmentRow[]) {
    let costAje = 0, costRje = 0, amortAje = 0, amortRje = 0, impairAje = 0, impairRje = 0
    for (const r of list) {
      const net = r.debitAmount - r.creditAmount
      const isRje = r.category === '报表调整' || r.entryType === 'RJE'
      if (isCostAccount(r.accountCode)) {
        if (isRje) costRje += net
        else costAje += net
      }
      if (isAmortAccount(r.accountCode)) {
        if (isRje) amortRje += net
        else amortAje += net
      }
      if (isImpairAccount(r.accountCode)) {
        if (isRje) impairRje += net
        else impairAje += net
      }
    }
    return { costAje, costRje, amortAje, amortRje, impairAje, impairRje }
  }

  const costAjeNet = computed(() => _netsFromList(rows.value).costAje)
  const costRjeNet = computed(() => _netsFromList(rows.value).costRje)
  const amortAjeNet = computed(() => _netsFromList(rows.value).amortAje)
  const amortRjeNet = computed(() => _netsFromList(rows.value).amortRje)
  const impairAjeNet = computed(() => _netsFromList(rows.value).impairAje)
  const impairRjeNet = computed(() => _netsFromList(rows.value).impairRje)

  function _writeNets(n: ReturnType<typeof _netsFromList>) {
    if (!onSave) return
    const pairs: [string, number][] = [
      [COST_AJE_KEY, n.costAje],
      [COST_RJE_KEY, n.costRje],
      [AMORT_AJE_KEY, n.amortAje],
      [AMORT_RJE_KEY, n.amortRje],
      [IMPAIR_AJE_KEY, n.impairAje],
      [IMPAIR_RJE_KEY, n.impairRje],
    ]
    for (const [key, val] of pairs) {
      onSave(key, val)
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, { ...existing, item_id: key, remark: String(val) })
    }
  }

  function _persist(list?: I1AdjustmentRow[]): void {
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
  }

  function addRow(adjustType: 'AJE' | 'RJE' = 'AJE'): void {
    if (isReadonly.value) return
    const category = categoryFromEntryType(adjustType)
    rows.value.push({
      rowId: generateRowId(),
      seq: rows.value.length + 1,
      description: '',
      category,
      entryType: adjustType,
      reportItem: '无形资产',
      accountCode: '1701',
      accountName: '无形资产',
      noteItem: '',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: 'I1-3',
      remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (field === 'debit' || field === 'debitAmount') {
      row.debitAmount = parseAmt(value)
    } else if (field === 'credit' || field === 'creditAmount') {
      row.creditAmount = parseAmt(value)
    } else if (field === 'category') {
      row.category = String(value)
      row.entryType = entryTypeFromCategory(String(value))
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
      row.category = categoryFromEntryType(row.entryType)
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const known = I1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
      if (!row.reportItem) row.reportItem = reportItemForAccount(row.accountCode)
    } else if (field === 'description' || field === 'summary') {
      row.description = String(value ?? '')
    } else if (field in row) {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function updateRow(rowId: string, patch: Partial<I1AdjustmentRow>): void {
    if (isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    if (patch.category != null) {
      row.entryType = entryTypeFromCategory(String(patch.category))
    }
    if (patch.accountCode != null) {
      const known = I1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(patch.accountCode))
      if (known) row.accountName = known.name
    }
    _persist()
  }

  function publishAdjustment(): void {
    const nets = _netsFromList(rows.value)
    const payload = {
      wp_code: WP_CODE,
      wpCode: WP_CODE,
      source: 'I1-3',
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
      ajeNet: nets.costAje,
      rjeNet: nets.costRje,
      costAjeNet: nets.costAje,
      costRjeNet: nets.costRje,
      amortAjeNet: nets.amortAje,
      amortRjeNet: nets.amortRje,
      impairAjeNet: nets.impairAje,
      impairRjeNet: nets.impairRje,
    }
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(nets.costAje),
        accountCode: '1701',
        accountName: '无形资产',
        description: `I1-3 无形资产账项净额 ${nets.costAje}`,
        ...payload,
      } as any)
      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
    } catch {
      /* silent */
    }
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
      indexRef: r.indexRef || 'I1-3',
    }))
    try {
      eventBus.emit('a13:push-misstatement', {
        items,
        wpCode: WP_CODE,
        source: 'I1-3',
        timestamp: Date.now(),
      })
      window.dispatchEvent(new CustomEvent('a13:push-misstatement', {
        detail: { wpCode: WP_CODE, source: 'I1-3', entries: items },
      }))
      lastPushMsg.value = `已推送 ${targets.length} 行至 A13`
    } catch {
      lastPushMsg.value = '推送失败'
    }
  }

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    if (!isBalanced.value) {
      lastSyncMsg.value = '借贷不平衡，无法推送至调整分录模块'
      return 0
    }
    const year = resolveI1AuditYear({
      propYear: params.auditYear?.value,
      allResponses: allResponses.value,
    })
    if (!Number.isFinite(year) || year < 1900) {
      lastSyncMsg.value = '缺少审计年度，无法推送至调整分录模块'
      return 0
    }

    const pending = rows.value.filter(
      (r) =>
        !r.sourceGroupId
        && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) {
      lastSyncMsg.value = '无可推送分录（可能已同步或未填金额）'
      return 0
    }

    const groups = new Map<string, I1AdjustmentRow[]>()
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
            description: `[I1] ${lines[0].description || '无形资产调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '1701',
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
      const year = resolveI1AuditYear({
        propYear: params.auditYear?.value,
        allResponses: allResponses.value,
      })
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: I1AdjustmentRow[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isI1RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        // 组内须含 1701/1702/1703，避免误拉无关费用调整
        const hasCore = lines.some((li: any) => {
          const c = String(li.standard_account_code || li.account_code || '')
          return isCostAccount(c) || isAmortAccount(c) || isImpairAccount(c)
        })
        if (!hasCore) continue

        const groupId = String(item.entry_group_id || item.id || '')
        const et = entryTypeFromModule(item.adjustment_type || item.type)
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[I1\]\s*/,
          '',
        )
        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          imported.push(
            _normalizeRow(
              {
                rowId: `${groupId}-${imported.length}`,
                description: desc,
                category: categoryFromEntryType(et),
                entryType: et,
                reportItem: reportItemForAccount(accountCode),
                accountCode,
                accountName: li.account_name || accountCode,
                debitAmount: li.debit_amount,
                creditAmount: li.credit_amount,
                indexRef: '调整分录模块',
                remark: '来自调整分录模块',
                sourceGroupId: groupId,
              },
              imported.length,
            ),
          )
        }
      }

      const manual = rows.value.filter((r) => !r.sourceGroupId)
      _persist([...manual, ...imported])
      lastSyncMsg.value = imported.length
        ? `已同步 ${imported.length} 行`
        : '调整分录模块中无含 1701/1702/1703 的相关分录'
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

  function onModuleUpdated() {
    if (!isReadonly.value && params.projectId.value) {
      void syncFromAdjustmentModule()
    }
  }

  if (getCurrentInstance()) {
    onMounted(() => {
      eventBus.on('adjustment:updated', onModuleUpdated)
    })
    onBeforeUnmount(() => {
      eventBus.off('adjustment:updated', onModuleUpdated)
    })
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    groupBalanceIssues,
    costAjeNet,
    costRjeNet,
    amortAjeNet,
    amortRjeNet,
    impairAjeNet,
    impairRjeNet,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    categoryOptions: I1_CATEGORY_OPTIONS,
    accountOptions: I1_ADJ_ACCOUNT_OPTIONS,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    load,
    saveAndPublish,
    publishAdjustment,
    pushToA13,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    saveNote,
    saveConclusion,
  }
}

export default useI1Adjustment
