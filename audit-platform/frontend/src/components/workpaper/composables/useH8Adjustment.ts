/**
 * useH8Adjustment — H8-3 使用权资产调整分录汇总
 *
 * 编制逻辑（对齐 Excel「使用权资产调整分录汇总表 H8-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 /
 *    附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注
 * 2. 「账项调整」→ AJE 影响审定数；「报表调整」→ RJE 仅列报；「其他」按 AJE
 * 3. 仅列示与使用权资产相关的审计调整；完整分录通常多行（原值/累计折旧 + 对方科目）且整表借贷平衡
 * 4. 索引交叉引用来源底稿（H8-2/H8-6/H8-8/H8-10/H8-12 等）
 * 5. 与中央调整分录模块双向同步（含原值科目的完整分录组）；可推送 A13；原值/折旧净额可回写 H8-1
 * 6. 兼容旧存档：adjustType AJE|RJE、summary、counterAccount、debit/credit
 *
 * 🔴 科目码单一真源 = `hCycleAccountScope.h8Scope`（H8 真实族 1641/1642/1643）。
 *    历史实现写死 `1901/1902/1903`（1901 实为待处理财产损溢）与 `2205`（合同负债，
 *    租赁负债真值 2601）→ 调整分录会记到错科目名下。禁在本文件再写科目码字面量。
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
import { calcSubtotal } from './useH8FormulaEngine'
import { h8Scope, h9Scope } from './hCycleAccountScope'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H8AdjCategory = '账项调整' | '报表调整' | '其他'

export interface H8AdjustmentRow {
  rowId: string
  seq: number
  /** 调整事项说明（Excel A 列） */
  description: string
  /** 类别：账项调整 / 报表调整 / 其他（Excel B 列） */
  category: H8AdjCategory | string
  /** 派生：账项/其他→AJE，报表→RJE（供 H8-1 / A13 / 中央模块） */
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
  /** @deprecated 旧 adjustType */
  adjustType?: 'AJE' | 'RJE'
  /** 来自/已推送至中央调整模块时的 entry_group_id */
  sourceGroupId?: string
}

/** 借贷平衡状态（兼容旧 UI balanceCheck） */
export interface BalanceCheck {
  debitTotal: number
  creditTotal: number
  diff: number
  isBalanced: boolean
  warning: string
}

export type H8BalanceStatus = BalanceCheck

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-3-rows'
const AJE_NET_KEY = 'H8-3-aje-net'
const RJE_NET_KEY = 'H8-3-rje-net'
const DEP_AJE_NET_KEY = 'H8-3-dep-aje-net'
const DEP_RJE_NET_KEY = 'H8-3-dep-rje-net'
const NOTE_KEY = 'H8-3-audit-note'
const WP_CODE = 'H8'
const BALANCE_TOLERANCE = 0.01

/** 科目码单一真源（不写字面量，全部取自 scope 声明） */
function slotCode(scope: typeof h8Scope, slotKey: string, index = 0): string {
  return scope.def.slotFallbacks[slotKey]?.[index] ?? scope.def.grossFallback
}

/** 使用权资产原值 / 累计折旧 / 减值准备 */
export const H8_ROU_COST_CODE = slotCode(h8Scope, 'gross')
export const H8_ROU_DEP_CODE = slotCode(h8Scope, 'accum_dep')
export const H8_ROU_IMP_CODE = slotCode(h8Scope, 'impairment')
/** 租赁负债侧对方科目（H9 循环真源） */
const H9_LEASE_LIABILITY_CODE = slotCode(h9Scope, 'gross')
const H9_UNEARNED_FINANCE_CODE = slotCode(h9Scope, 'unearned_finance')
/** 财务费用（非 H 循环科目，无 scope 声明，作对方科目常量） */
const FINANCE_EXPENSE_CODE = '6603'

/** 中央模块同步：分录组内含这些科目前缀即视为使用权资产相关候选 */
const H8_RELATED_PREFIXES = [
  H8_ROU_COST_CODE,
  H8_ROU_DEP_CODE,
  H8_ROU_IMP_CODE,
  H9_LEASE_LIABILITY_CODE,
  H9_UNEARNED_FINANCE_CODE,
  FINANCE_EXPENSE_CODE,
]

export const H8_CATEGORY_OPTIONS: readonly H8AdjCategory[] = ['账项调整', '报表调整', '其他']

/** 使用权资产及相关对方科目（录入下拉） */
export const H8_ADJ_ACCOUNT_OPTIONS = [
  { code: H8_ROU_COST_CODE, name: '使用权资产' },
  { code: H8_ROU_DEP_CODE, name: '使用权资产累计折旧' },
  { code: H8_ROU_IMP_CODE, name: '使用权资产减值准备' },
  { code: H9_LEASE_LIABILITY_CODE, name: '租赁负债' },
  { code: H9_UNEARNED_FINANCE_CODE, name: '未确认融资费用' },
  { code: '1002', name: '银行存款' },
  { code: '2202', name: '应付账款' },
  { code: '1221', name: '其他应收款' },
  { code: FINANCE_EXPENSE_CODE, name: '财务费用' },
  { code: '5301', name: '营业外支出' },
  { code: '6301', name: '营业外收入' },
  { code: '6115', name: '资产处置收益' },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `h8a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function categoryFromLegacy(raw: {
  category?: string
  entryType?: string
  adjustType?: string
}): H8AdjCategory {
  const cat = String(raw.category || '').trim()
  if ((H8_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat as H8AdjCategory
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

function isH8RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return H8_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function isRouCostAccount(code: string): boolean {
  const c = String(code || '')
  return c === H8_ROU_COST_CODE || c.startsWith(H8_ROU_COST_CODE)
}

function isRouDepAccount(code: string): boolean {
  const c = String(code || '')
  return c === H8_ROU_DEP_CODE || c.startsWith(H8_ROU_DEP_CODE) || /累计折旧|累计摊销/.test(c)
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

function categoryFromEntryType(et: 'AJE' | 'RJE'): H8AdjCategory {
  return et === 'RJE' ? '报表调整' : '账项调整'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
  onPublishAdjustment?: (ajeNet: number, rjeNet: number) => void
  onSyncToAdjudication?: (ajeNet: number, rjeNet: number, depAje?: number, depRje?: number) => void
}) {
  const {
    allResponses,
    onSave,
    onPublishEvent,
    onPublishAdjustment,
    onSyncToAdjudication,
  } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const rows = ref<H8AdjustmentRow[]>([])
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

  function _normalizeRow(raw: any, idx: number): H8AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const description = String(
      raw.description || raw.summary || raw.reason || '',
    ).trim()
    const code = String(raw.accountCode ?? '').trim()
    const known = H8_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
    const legacyRemark = [raw.remark, raw.counterAccount ? `对方:${raw.counterAccount}` : '']
      .filter(Boolean)
      .join('；')
    return {
      rowId: raw.rowId ?? generateRowId(),
      seq: raw.seq ?? idx + 1,
      description,
      category,
      entryType,
      reportItem: raw.reportItem ?? '使用权资产',
      accountCode: code,
      accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '',
      noteItem: raw.noteItem ?? '',
      debitAmount: parseAmt(raw.debitAmount ?? raw.debit),
      creditAmount: parseAmt(raw.creditAmount ?? raw.credit),
      indexRef: String(raw.indexRef ?? raw.refIndex ?? raw.reference ?? '').trim(),
      remark: legacyRemark,
      summary: raw.summary,
      adjustType: entryType,
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
    auditNote.value =
      _getString(NOTE_KEY) || _getString('H8-adjustment-audit-note') || ''
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

  const balanceCheck: ComputedRef<BalanceCheck> = computed(() => {
    const diff = balanceDiff.value
    const balanced = isBalanced.value
    return {
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      diff,
      isBalanced: balanced,
      warning: balanced ? '' : `借贷不平衡，差额：${diff > 0 ? '+' : ''}${diff.toFixed(2)}元`,
    }
  })

  const balanceStatus = balanceCheck

  /** 全表账项净额（借−贷，不含报表调整） */
  const ajeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const rjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /** 科目 1901 账项净额（借−贷）——供 H8-1 原值 AJE 回写 */
  const rouCostAjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isRouCostAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const rouCostRjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      if (!isRouCostAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /** 科目 1902 累计折旧净额 */
  const rouDepAjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isRouDepAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const rouDepRjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      if (!isRouDepAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

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
    rouCostAjeNet: rouCostAjeNet.value,
    rouCostRjeNet: rouCostRjeNet.value,
    rouDepAjeNet: rouDepAjeNet.value,
    rouDepRjeNet: rouDepRjeNet.value,
  }))

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _toPersistShape(list: H8AdjustmentRow[]) {
    return list.map((r, i) => ({
      rowId: r.rowId,
      seq: i + 1,
      description: r.description,
      category: r.category,
      entryType: entryTypeFromCategory(String(r.category)),
      adjustType: entryTypeFromCategory(String(r.category)),
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

  function _writeNets(costAje: number, costRje: number, depAje: number, depRje: number): void {
    if (!onSave) return
    onSave(AJE_NET_KEY, costAje)
    onSave(RJE_NET_KEY, costRje)
    onSave(DEP_AJE_NET_KEY, depAje)
    onSave(DEP_RJE_NET_KEY, depRje)
    for (const [key, val] of [
      [AJE_NET_KEY, costAje],
      [RJE_NET_KEY, costRje],
      [DEP_AJE_NET_KEY, depAje],
      [DEP_RJE_NET_KEY, depRje],
    ] as const) {
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, {
        ...existing,
        item_id: key,
        remark: String(val),
      })
    }
  }

  function _netsFromList(list: H8AdjustmentRow[]): {
    costAje: number
    costRje: number
    depAje: number
    depRje: number
  } {
    let costAje = 0
    let costRje = 0
    let depAje = 0
    let depRje = 0
    for (const r of list) {
      const net = r.debitAmount - r.creditAmount
      const isRje = r.category === '报表调整' || r.entryType === 'RJE'
      if (isRouCostAccount(r.accountCode)) {
        if (isRje) costRje += net
        else costAje += net
      }
      if (isRouDepAccount(r.accountCode)) {
        if (isRje) depRje += net
        else depAje += net
      }
    }
    return { costAje, costRje, depAje, depRje }
  }

  function _persist(list?: H8AdjustmentRow[]): void {
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
    _writeNets(nets.costAje, nets.costRje, nets.depAje, nets.depRje)
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(adjustType: 'AJE' | 'RJE' = 'AJE'): void {
    if (isReadonly.value) return
    const category = categoryFromEntryType(adjustType)
    rows.value.push({
      rowId: generateRowId(),
      seq: rows.value.length + 1,
      description: '',
      category,
      entryType: adjustType,
      reportItem: '使用权资产',
      accountCode: H8_ROU_COST_CODE,
      accountName: '使用权资产',
      noteItem: '',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: 'H8-3',
      remark: '',
      adjustType,
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

  function updateCell(rowId: string, field: keyof H8AdjustmentRow | string, value: any): void {
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
      row.adjustType = row.entryType
    } else if (field === 'entryType' || field === 'adjustType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
      row.adjustType = row.entryType
      row.category = categoryFromEntryType(row.entryType)
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const known = H8_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
    } else if (field === 'refIndex' || field === 'indexRef') {
      row.indexRef = String(value ?? '')
    } else if (field === 'summary' || field === 'description') {
      row.description = String(value ?? '')
      row.summary = row.description
    } else if (field in row) {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function updateRow(rowId: string, patch: Partial<H8AdjustmentRow>): void {
    if (isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    if (patch.category != null) {
      row.entryType = entryTypeFromCategory(String(patch.category))
      row.adjustType = row.entryType
    }
    if ((patch.entryType != null || patch.adjustType != null) && patch.category == null) {
      const et = (patch.entryType || patch.adjustType) === 'RJE' ? 'RJE' : 'AJE'
      row.entryType = et
      row.adjustType = et
      row.category = categoryFromEntryType(et)
    }
    if (patch.accountCode != null) {
      const known = H8_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(patch.accountCode))
      if (known) row.accountName = known.name
    }
    _persist()
  }

  // ─── H8-1 / EventBus ───────────────────────────────────────────────────────

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
      rouCostAjeNet: rouCostAjeNet.value,
      rouCostRjeNet: rouCostRjeNet.value,
      rouDepAjeNet: rouDepAjeNet.value,
      rouDepRjeNet: rouDepRjeNet.value,
      ajeNet: rouCostAjeNet.value,
      rjeNet: rouCostRjeNet.value,
      ajeTotals: ajeTotals.value,
      rjeTotals: rjeTotals.value,
    }
    onPublishEvent?.('adjustment:created', payload)
    onPublishAdjustment?.(rouCostAjeNet.value, rouCostRjeNet.value)
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(rouCostAjeNet.value),
        accountCode: H8_ROU_COST_CODE,
        accountName: '使用权资产',
        description: `H8-3 使用权资产账项净额 ${rouCostAjeNet.value}`,
        ...payload,
      } as any)
      window.dispatchEvent(
        new CustomEvent('adjustment:created', {
          detail: {
            wpCode: WP_CODE,
            ajeNet: rouCostAjeNet.value,
            rjeNet: rouCostRjeNet.value,
            ...payload,
          },
        }),
      )
    } catch {
      /* silent */
    }
    onSyncToAdjudication?.(
      rouCostAjeNet.value,
      rouCostRjeNet.value,
      rouDepAjeNet.value,
      rouDepRjeNet.value,
    )
  }

  function publishAndSync(): void {
    _writeNets(
      rouCostAjeNet.value,
      rouCostRjeNet.value,
      rouDepAjeNet.value,
      rouDepRjeNet.value,
    )
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
      indexRef: r.indexRef || 'H8-3',
    }))
    onPublishEvent?.('adjustment:push-to-a13', { wp_code: WP_CODE, entries: items })
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

    const groups = new Map<string, H8AdjustmentRow[]>()
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
            description: `[H8] ${lines[0].description || '使用权资产调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || H8_ROU_COST_CODE,
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

      const imported: H8AdjustmentRow[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isH8RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        // 组内须含使用权资产原值科目，避免误拉纯租赁负债（H9）调整
        const hasRouCost = lines.some((li: any) =>
          isRouCostAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRouCost) continue

        const groupId = String(item.entry_group_id || item.id || '')
        const et = entryTypeFromModule(item.adjustment_type || item.type)
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[H8\]\s*/,
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
                reportItem: isRouCostAccount(accountCode) ? '使用权资产' : '',
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
        : `调整分录模块中无含 ${H8_ROU_COST_CODE} 的相关分录`
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
    balanceCheck,
    balanceStatus,
    ajeNet,
    rjeNet,
    rouCostAjeNet,
    rouCostRjeNet,
    rouDepAjeNet,
    rouDepRjeNet,
    ajeTotals,
    rjeTotals,
    summary,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    categoryOptions: H8_CATEGORY_OPTIONS,
    accountOptions: H8_ADJ_ACCOUNT_OPTIONS,
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

export default useH8Adjustment
