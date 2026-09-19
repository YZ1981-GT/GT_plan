/**
 * useH6Adjustment — H6-3 固定资产清理调整分录汇总
 *
 * 编制逻辑（对齐 Excel「固定资产清理调整分录汇总表 H6-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 /
 *    附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注
 * 2. 「账项调整」→ AJE 影响审定数；「报表调整」→ RJE 仅列报；「其他」按 AJE
 * 3. 仅列示与固定资产清理相关的审计调整；完整分录通常多行（1606 + 对方科目）且整表借贷平衡
 * 4. 索引交叉引用来源底稿（H6-2/H6-4、H1 处置检查等）
 * 5. 与中央调整分录模块双向同步（含 1606 的完整分录组）；可推送 A13；1606 净额可回写 H6-1
 * 6. 兼容旧存档：entryType AJE|RJE、debit/credit、summary、refIndex
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
import { calcSubtotal } from './useH6FormulaEngine'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H6AdjCategory = '账项调整' | '报表调整' | '其他'

export interface H6AdjustmentRow {
  rowId: string
  seq: number
  /** 调整事项说明（Excel A 列） */
  description: string
  /** 类别：账项调整 / 报表调整 / 其他（Excel B 列） */
  category: H6AdjCategory | string
  /** 派生：账项/其他→AJE，报表→RJE（供 H6-1 / A13 / 中央模块） */
  entryType: 'AJE' | 'RJE' | ''
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** @deprecated 旧摘要，读档并入 description */
  summary?: string
  /** 来自/已推送至中央调整模块时的 entry_group_id */
  sourceGroupId?: string
}

/** 借贷平衡状态（兼容旧 UI） */
export interface H6BalanceStatus {
  debitTotal: number
  creditTotal: number
  diff: number
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H6-3-rows'
const AJE_NET_KEY = 'H6-3-aje-net'
const RJE_NET_KEY = 'H6-3-rje-net'
const NOTE_KEY = 'H6-3-audit-note'
const WP_CODE = 'H6'
const BALANCE_TOLERANCE = 0.01
/** 中央模块同步：分录组内含这些科目前缀即视为清理相关候选 */
const H6_RELATED_PREFIXES = ['1606', '1601', '1602', '5301', '6301', '1002']

export const H6_CATEGORY_OPTIONS: readonly H6AdjCategory[] = ['账项调整', '报表调整', '其他']

/** 固定资产清理及相关对方科目（录入下拉） */
export const H6_ADJ_ACCOUNT_OPTIONS = [
  { code: '1606', name: '固定资产清理' },
  { code: '1601', name: '固定资产' },
  { code: '1602', name: '累计折旧' },
  { code: '1603', name: '固定资产减值准备' },
  { code: '1002', name: '银行存款' },
  { code: '1221', name: '其他应收款' },
  { code: '2202', name: '应付账款' },
  { code: '2221', name: '应交税费' },
  { code: '5301', name: '营业外支出' },
  { code: '6301', name: '营业外收入' },
  { code: '6115', name: '资产处置收益' },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `h6a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function categoryFromLegacy(raw: {
  category?: string
  entryType?: string
  adjustType?: string
}): H6AdjCategory {
  const cat = String(raw.category || '').trim()
  if ((H6_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat as H6AdjCategory
  if (cat === '重分类调整') return '报表调整'
  const legacy = String(raw.entryType || raw.adjustType || '').toUpperCase()
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

function isH6RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return H6_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function isClearingAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1606' || c.startsWith('1606')
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

function categoryFromEntryType(et: 'AJE' | 'RJE'): H6AdjCategory {
  return et === 'RJE' ? '报表调整' : '账项调整'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
  onSyncToAdjudication?: (ajeNet: number, rjeNet: number) => void
}) {
  const {
    allResponses,
    onSave,
    onPublishEvent,
    onSyncToAdjudication,
  } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const rows = ref<H6AdjustmentRow[]>([])
  const auditNote = ref('')
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
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any, idx: number): H6AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const description = String(raw.description || raw.summary || raw.reason || '').trim()
    const code = String(raw.accountCode ?? '').trim()
    const known = H6_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
    return {
      rowId: raw.rowId ?? generateRowId(),
      seq: raw.seq ?? idx + 1,
      description,
      category,
      entryType,
      reportItem: raw.reportItem ?? '固定资产清理',
      accountCode: code,
      accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '',
      noteItem: raw.noteItem ?? '',
      debitAmount: parseAmt(raw.debitAmount ?? raw.debit),
      creditAmount: parseAmt(raw.creditAmount ?? raw.credit),
      indexRef: String(raw.indexRef ?? raw.refIndex ?? raw.reference ?? '').trim(),
      remark: raw.remark ?? '',
      summary: raw.summary,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const debitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map((r) => r.debitAmount)),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map((r) => r.creditAmount)),
  )

  const balanceDiff: ComputedRef<number> = computed(() => debitTotal.value - creditTotal.value)

  const isBalanced: ComputedRef<boolean> = computed(
    () => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE,
  )

  const balanceStatus: ComputedRef<H6BalanceStatus> = computed(() => ({
    debitTotal: debitTotal.value,
    creditTotal: creditTotal.value,
    diff: balanceDiff.value,
    isBalanced: isBalanced.value,
  }))

  /** 账项调整净额（全表，借−贷） */
  const ajeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /** 报表调整净额 */
  const rjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /**
   * 科目 1606 账项净额（借−贷）——供 H6-1 期末 AJE 回写。
   * 过渡科目贷方结转会使净额为负，符合审定净值口径。
   */
  const clearingAjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isClearingAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const clearingRjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      if (!isClearingAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /** @deprecated 兼容旧调用：等同 clearingAjeNet */
  const ajeTotalNet = clearingAjeNet
  /** @deprecated 兼容旧调用：等同 clearingRjeNet */
  const rjeTotalNet = clearingRjeNet

  const ajeTotals = computed(() => {
    const ajeRows = rows.value.filter((r) => r.category !== '报表调整' && r.entryType !== 'RJE')
    return {
      debit: calcSubtotal(ajeRows.map((r) => r.debitAmount)),
      credit: calcSubtotal(ajeRows.map((r) => r.creditAmount)),
    }
  })

  const rjeTotals = computed(() => {
    const rjeRows = rows.value.filter((r) => r.category === '报表调整' || r.entryType === 'RJE')
    return {
      debit: calcSubtotal(rjeRows.map((r) => r.debitAmount)),
      credit: calcSubtotal(rjeRows.map((r) => r.creditAmount)),
    }
  })

  const summary = computed(() => ({
    rowCount: rows.value.length,
    ajeCount: rows.value.filter((r) => r.category !== '报表调整' && r.entryType !== 'RJE').length,
    rjeCount: rows.value.filter((r) => r.category === '报表调整' || r.entryType === 'RJE').length,
    totalDebits: debitTotal.value,
    totalCredits: creditTotal.value,
    ajeNet: ajeNet.value,
    rjeNet: rjeNet.value,
    clearingAjeNet: clearingAjeNet.value,
    clearingRjeNet: clearingRjeNet.value,
  }))

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _toPersistShape(list: H6AdjustmentRow[]) {
    return list.map((r, i) => ({
      rowId: r.rowId,
      seq: i + 1,
      description: r.description,
      category: r.category,
      entryType: entryTypeFromCategory(String(r.category)),
      reportItem: r.reportItem,
      accountCode: r.accountCode,
      accountName: r.accountName,
      noteItem: r.noteItem,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      debit: r.debitAmount,
      credit: r.creditAmount,
      indexRef: r.indexRef,
      refIndex: r.indexRef,
      remark: r.remark,
      sourceGroupId: r.sourceGroupId,
      summary: r.summary || r.description,
    }))
  }

  function _writeNets(aje: number, rje: number): void {
    if (!onSave) return
    onSave(AJE_NET_KEY, aje)
    onSave(RJE_NET_KEY, rje)
    // 乐观写入 allResponses，供 H6-1 / CrossSheet 即时读取
    for (const [key, val] of [
      [AJE_NET_KEY, aje],
      [RJE_NET_KEY, rje],
    ] as const) {
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, {
        ...existing,
        item_id: key,
        remark: String(val),
      })
    }
  }

  function _netsFromList(list: H6AdjustmentRow[]): { aje: number; rje: number } {
    let aje = 0
    let rje = 0
    for (const r of list) {
      if (!isClearingAccount(r.accountCode)) continue
      const net = r.debitAmount - r.creditAmount
      if (r.category === '报表调整' || r.entryType === 'RJE') rje += net
      else aje += net
    }
    return { aje, rje }
  }

  function _persist(list?: H6AdjustmentRow[]): void {
    if (!onSave) return
    const next = list ?? rows.value
    const shaped = _toPersistShape(next)
    const normalized = shaped.map((r, i) => _normalizeRow(r, i))
    rows.value = normalized
    onSave(ROWS_KEY, shaped)
    const existing = allResponses.value.get(ROWS_KEY) || {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: null,
    }
    allResponses.value.set(ROWS_KEY, {
      ...existing,
      item_id: ROWS_KEY,
      remark: JSON.stringify(shaped),
    })
    const nets = _netsFromList(normalized)
    _writeNets(nets.aje, nets.rje)
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value.push({
      rowId: generateRowId(),
      seq: rows.value.length + 1,
      description: '',
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '固定资产清理',
      accountCode: '1606',
      accountName: '固定资产清理',
      noteItem: '',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: 'H6-3',
      remark: '',
    })
    _persist()
  }

  function deleteRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  const removeRow = deleteRow

  function updateCell(rowId: string, field: keyof H6AdjustmentRow | string, value: any): void {
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
      const known = H6_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
    } else if (field === 'refIndex' || field === 'indexRef') {
      row.indexRef = String(value ?? '')
    } else if (field in row) {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function updateRow(rowId: string, patch: Partial<H6AdjustmentRow>): void {
    if (isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    if (patch.category != null) {
      row.entryType = entryTypeFromCategory(String(patch.category))
    }
    if (patch.entryType != null && patch.category == null) {
      row.category = categoryFromEntryType(patch.entryType === 'RJE' ? 'RJE' : 'AJE')
    }
    if (patch.accountCode != null) {
      const known = H6_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(patch.accountCode))
      if (known) row.accountName = known.name
    }
    _persist()
  }

  // ─── H6-1 / EventBus ───────────────────────────────────────────────────────

  function publishAdjustment(): void {
    const payload = {
      wp_code: WP_CODE,
      wpCode: WP_CODE,
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
      totalAje: ajeNet.value,
      totalRje: rjeNet.value,
      clearingAjeNet: clearingAjeNet.value,
      clearingRjeNet: clearingRjeNet.value,
      ajeTotals: ajeTotals.value,
      rjeTotals: rjeTotals.value,
    }
    // 统一走 eventBus.emit（crossWpEventBridge 自动桥接到 window 供旧消费者）
    // 不再直接 onPublishEvent 避免双投双触发
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(clearingAjeNet.value),
        accountCode: '1606',
        accountName: '固定资产清理',
        description: `H6-3 固定资产清理账项净额 ${clearingAjeNet.value}`,
        ...payload,
      } as any)
    } catch {
      /* silent */
    }
    onSyncToAdjudication?.(clearingAjeNet.value, clearingRjeNet.value)
  }

  /** 兼容旧 API：保存净额 + 发布事件 + 回写 H6-1 */
  function publishAndSync(): void {
    _writeNets(clearingAjeNet.value, clearingRjeNet.value)
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
      indexRef: r.indexRef || 'H6-3',
    }))
    // 统一走 eventBus（crossWpEventBridge 桥接 window），删除 onPublishEvent 双投
    try {
      eventBus.emit('a13:push-misstatement', {
        items,
        wpCode: WP_CODE,
        timestamp: Date.now(),
      })
      lastPushMsg.value = `已推送 ${targets.length} 行至 A13`
    } catch {
      lastPushMsg.value = '推送失败'
    }
  }

  // ─── 中央调整分录模块双向同步 ──────────────────────────────────────────────

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    if (!isBalanced.value) {
      lastSyncMsg.value = '借贷不平衡，无法推送至调整分录模块'
      return 0
    }
    const year = Number(params.auditYear?.value)
    if (!Number.isFinite(year) || year < 1900) {
      lastSyncMsg.value = '缺少审计年度，无法推送至调整分录模块'
      return 0
    }

    const pending = rows.value.filter(
      (r) =>
        !r.sourceGroupId &&
        (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) {
      lastSyncMsg.value = '无可推送分录（可能已同步或未填金额）'
      return 0
    }

    const groups = new Map<string, H6AdjustmentRow[]>()
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
            description: `[H6] ${lines[0].description || '固定资产清理调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '1606',
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
      const year = Number(params.auditYear?.value) || new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: H6AdjustmentRow[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isH6RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        // 组内须含 1606，避免误拉纯固定资产（H1）调整
        const has1606 = lines.some((li: any) =>
          isClearingAccount(li.standard_account_code || li.account_code),
        )
        if (!has1606) continue

        const groupId = String(item.entry_group_id || item.id || '')
        const et = entryTypeFromModule(item.adjustment_type || item.type)
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[H6\]\s*/,
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
                reportItem: isClearingAccount(accountCode) ? '固定资产清理' : '',
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
        : '调整分录模块中无含 1606 的相关分录'
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败，请稍后重试'
      return 0
    } finally {
      syncing.value = false
    }
  }

  async function confirmAndPush(): Promise<{ ok: boolean; pushed: number }> {
    if (!isBalanced.value) return { ok: false, pushed: 0 }
    _persist()
    publishAdjustment()
    const pushed = await pushToAdjustmentModule()
    return { ok: true, pushed }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function save(): void {
    _persist()
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
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    balanceStatus,
    ajeNet,
    rjeNet,
    clearingAjeNet,
    clearingRjeNet,
    ajeTotalNet,
    rjeTotalNet,
    ajeTotals,
    rjeTotals,
    summary,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    categoryOptions: H6_CATEGORY_OPTIONS,
    accountOptions: H6_ADJ_ACCOUNT_OPTIONS,
    addRow,
    deleteRow,
    removeRow,
    updateCell,
    updateRow,
    save,
    load,
    publishAdjustment,
    publishAndSync,
    pushToA13,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    confirmAndPush,
    saveNote,
  }
}

export default useH6Adjustment
