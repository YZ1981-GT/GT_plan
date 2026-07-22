/**
 * useH4Adjustment — H4-3 工程物资调整分录汇总
 *
 * 编制逻辑（对齐 Excel「工程物资调整分录汇总表 H4-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 /
 *    附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注
 * 2. 「账项调整」→ AJE 影响审定数；「报表调整」→ RJE 仅列报；「其他」按 AJE
 * 3. 仅列示与工程物资相关的审计调整；完整分录通常多行（1605 + 对方科目）且整表借贷平衡
 * 4. 索引交叉引用来源底稿（H4-4/5/6/7/8/9）；H4-7 可推送减值补提草稿
 * 5. 与中央调整分录模块双向同步（含 1605 的完整分录组）；可推送 A13；1605 净额可回写 H4-1
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
import { calcSubtotal } from './useH4FormulaEngine'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import { mergeH42AjeIntoH43, isH42AjeAutoRow } from './h4AjeSyncModel'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H4AdjCategory = '账项调整' | '报表调整' | '其他'

export interface H4AdjustmentRow {
  rowId: string
  seq: number
  /** 调整事项说明（Excel A 列） */
  description: string
  /** 类别：账项调整 / 报表调整 / 其他（Excel B 列） */
  category: H4AdjCategory | string
  /** 派生：账项/其他→AJE，报表→RJE（供 H4-1 / A13 / 中央模块） */
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

export interface BalanceStatus {
  debitTotal: number
  creditTotal: number
  diff: number
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-3-rows'
const NOTE_KEY = 'H4-3-audit-note'
const WP_CODE = 'H4'
const BALANCE_TOLERANCE = 0.01
/** 中央模块同步：分录组内含这些科目前缀即视为工程物资相关 */
const H4_RELATED_PREFIXES = ['1605', '1604', '6701']

export const H4_CATEGORY_OPTIONS: readonly H4AdjCategory[] = ['账项调整', '报表调整', '其他']

/** 工程物资及相关对方科目（录入下拉） */
export const H4_ADJ_ACCOUNT_OPTIONS = [
  { code: '1605', name: '工程物资' },
  { code: '1604', name: '在建工程' },
  { code: '6701', name: '资产减值损失' },
  { code: '2202', name: '应付账款' },
  { code: '1002', name: '银行存款' },
  { code: '1123', name: '预付账款' },
  { code: '1403', name: '原材料' },
  { code: '5301', name: '营业外支出' },
  { code: '6301', name: '营业外收入' },
  { code: '6602', name: '管理费用' },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `h4a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function categoryFromLegacy(raw: {
  category?: string
  entryType?: string
  adjustType?: string
}): H4AdjCategory {
  const cat = String(raw.category || '').trim()
  if ((H4_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat as H4AdjCategory
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

function isH4RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return H4_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function isEmAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1605' || c.startsWith('1605')
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

function categoryFromEntryType(et: 'AJE' | 'RJE'): H4AdjCategory {
  return et === 'RJE' ? '报表调整' : '账项调整'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Adjustment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const rows = ref<H4AdjustmentRow[]>([])
  const auditNote = ref('')
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const lastPushMsg = ref('')

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
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
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any, idx: number): H4AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const description = String(raw.description || raw.summary || raw.reason || '').trim()
    const code = String(raw.accountCode ?? '').trim()
    const known = H4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
    return {
      rowId: raw.rowId ?? generateRowId(),
      seq: raw.seq ?? idx + 1,
      description,
      category,
      entryType,
      reportItem: raw.reportItem ?? (isEmAccount(code) ? '工程物资' : ''),
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

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY) || _getString('H4-3-note')
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

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

  const balanceStatus: ComputedRef<BalanceStatus> = computed(() => ({
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
   * 科目 1605 账项净额（借−贷，资产增加为正）——供 H4-1 期末账项调整回写。
   * 减值准备贷方会使净额为负，符合审定净值口径。
   */
  const emAjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isEmAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const emRjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      if (!isEmAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /** @deprecated 兼容旧 UI/调用方命名 */
  const ajeTotalNet = emAjeNet
  const rjeTotalNet = emRjeNet

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
    emAjeNet: emAjeNet.value,
    emRjeNet: emRjeNet.value,
  }))

  /** 按调整事项说明分组（同事项多行借贷成组折叠） */
  const adjGroups = computed(() => {
    const order: string[] = []
    const map = new Map<string, H4AdjustmentRow[]>()
    for (const r of rows.value) {
      const desc = String(r.description || '').trim()
      const key = desc || `__row__:${r.rowId}`
      if (!map.has(key)) {
        map.set(key, [])
        order.push(key)
      }
      map.get(key)!.push(r)
    }
    return order.map((key) => {
      const list = map.get(key)!
      const d = calcSubtotal(list.map((r) => r.debitAmount))
      const c = calcSubtotal(list.map((r) => r.creditAmount))
      const first = list[0]
      return {
        key,
        description: String(first.description || '').trim() || '（未填写事项说明）',
        category: first.category,
        entryType: first.entryType,
        indexRef: first.indexRef,
        rows: list,
        debitTotal: d,
        creditTotal: c,
        diff: d - c,
        isBalanced: Math.abs(d - c) < BALANCE_TOLERANCE,
        lineCount: list.length,
        isAutoDraft: list.some((r) => String(r.remark || '').includes('aje-auto')),
        fromModule: list.some((r) => !!r.sourceGroupId),
      }
    })
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _toPersistShape(list: H4AdjustmentRow[]) {
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
      // 兼容旧读档 / H4-7 推送
      debit: r.debitAmount,
      credit: r.creditAmount,
      indexRef: r.indexRef,
      refIndex: r.indexRef,
      remark: r.remark,
      sourceGroupId: r.sourceGroupId,
      summary: r.summary || r.description,
    }))
  }

  function _persist(list?: H4AdjustmentRow[]): void {
    if (!options.onSave) return
    const next = list ?? rows.value
    const shaped = _toPersistShape(next)
    rows.value = shaped.map(_normalizeRow)
    options.onSave(ROWS_KEY, shaped)
    const existing = options.allResponses.value.get(ROWS_KEY) || {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: null,
    }
    options.allResponses.value.set(ROWS_KEY, {
      ...existing,
      item_id: ROWS_KEY,
      remark: JSON.stringify(shaped),
    })
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value.push({
      rowId: generateRowId(),
      seq: rows.value.length + 1,
      description: '',
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '工程物资',
      accountCode: '1605',
      accountName: '工程物资',
      noteItem: '',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: 'H4-3',
      remark: '',
    })
    _persist()
  }

  function deleteRow(rowId: string): void {
    removeRow(rowId)
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: keyof H4AdjustmentRow | string, value: any): void {
    if (options.isReadonly.value) return
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
      const known = H4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
    } else if (field === 'refIndex' || field === 'indexRef') {
      row.indexRef = String(value ?? '')
    } else if (field in row) {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function updateRow(rowId: string, patch: Partial<H4AdjustmentRow>): void {
    if (options.isReadonly.value) return
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
      const known = H4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(patch.accountCode))
      if (known) row.accountName = known.name
    }
    _persist()
  }

  // ─── H4-1 / EventBus ───────────────────────────────────────────────────────

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
      ajeTotal: emAjeNet.value,
      rjeTotal: emRjeNet.value,
      emAjeNet: emAjeNet.value,
      emRjeNet: emRjeNet.value,
      ajeTotals: ajeTotals.value,
      rjeTotals: rjeTotals.value,
      count: rows.value.length,
    }
    options.onPublishEvent?.('adjustment:created', payload)
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(emAjeNet.value),
        accountCode: '1605',
        accountName: '工程物资',
        description: `H4-3 工程物资账项净额 ${emAjeNet.value}`,
        ...payload,
      } as any)
    } catch {
      /* silent */
    }
  }

  /** @deprecated 兼容旧调用名 */
  function publishAdjustmentCreated(): void {
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
      indexRef: r.indexRef || 'H4-3',
    }))
    options.onPublishEvent?.('adjustment:push-to-a13', { wp_code: WP_CODE, entries: items })
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
    const projectId = options.projectId.value
    if (!projectId || options.isReadonly.value) return 0
    if (!isBalanced.value) {
      lastSyncMsg.value = '借贷不平衡，无法推送至调整分录模块'
      return 0
    }
    const year = Number(options.auditYear?.value)
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

    const groups = new Map<string, H4AdjustmentRow[]>()
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
            description: `[H4] ${lines[0].description || '工程物资调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '1605',
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
    const projectId = options.projectId.value
    if (!projectId || options.isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = Number(options.auditYear?.value) || new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: H4AdjustmentRow[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isH4RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        const has1605 = lines.some((li: any) =>
          isEmAccount(li.standard_account_code || li.account_code),
        )
        if (!has1605) continue

        const groupId = String(item.entry_group_id || item.id || '')
        const et = entryTypeFromModule(item.adjustment_type || item.type)
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[H4\]\s*/,
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
                reportItem: isEmAccount(accountCode) ? '工程物资' : '',
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
        : '调整分录模块中无含 1605 的相关分录'
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

  /** 从 H4-2 明细行级 AJE 生成借贷平衡草稿（替换旧 H4-2 自动行，保留手工/H4-7 等） */
  function syncAjeFromH42(): { ok: boolean; added: number; cleared: number; message: string } {
    if (options.isReadonly.value) {
      return { ok: false, added: 0, cleared: 0, message: '只读模式' }
    }
    const raw = _getJson('H4-2-rows')
    if (!Array.isArray(raw) || raw.length === 0) {
      return { ok: false, added: 0, cleared: 0, message: 'H4-2 暂无明细行' }
    }
    const hasAje = raw.some((r: any) =>
      Math.abs(Number(r.ajeBegin) || 0)
        + Math.abs(Number(r.ajeIncrease) || 0)
        + Math.abs(Number(r.ajeDecrease) || 0)
        + Math.abs(Number(r.ajeImpair) || 0) >= 0.005,
    )
    if (!hasAje) {
      return { ok: false, added: 0, cleared: 0, message: 'H4-2 明细暂无 AJE 金额' }
    }
    const { rows: merged, added, cleared } = mergeH42AjeIntoH43(rows.value, raw)
    _persist(merged)
    publishAdjustment()
    return {
      ok: true,
      added,
      cleared,
      message: `已从 H4-2 带入 ${added} 行 AJE 草稿（清除旧自动行 ${cleared}；手工分录已保留）`,
    }
  }

  function countH42AutoRows(): number {
    return rows.value.filter(isH42AjeAutoRow).length
  }

  function save(): void {
    _persist()
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function load(): void {
    initFromAllResponses()
  }

  function onModuleUpdated() {
    if (!options.isReadonly.value && options.projectId.value) {
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
    balanceStatus,
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    ajeNet,
    rjeNet,
    emAjeNet,
    emRjeNet,
    ajeTotalNet,
    rjeTotalNet,
    ajeTotals,
    rjeTotals,
    summary,
    adjGroups,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    categoryOptions: H4_CATEGORY_OPTIONS,
    accountOptions: H4_ADJ_ACCOUNT_OPTIONS,
    addRow,
    deleteRow,
    removeRow,
    updateCell,
    updateRow,
    save,
    load,
    publishAdjustment,
    publishAdjustmentCreated,
    pushToA13,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    syncAjeFromH42,
    countH42AutoRows,
    confirmAndPush,
    saveNote,
    initFromAllResponses,
  }
}

export default useH4Adjustment
