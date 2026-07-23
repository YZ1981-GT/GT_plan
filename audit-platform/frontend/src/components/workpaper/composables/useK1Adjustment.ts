/**
 * useK1Adjustment — K1-4 其他应收款调整分录汇总
 *
 * 对齐致同 Excel「其他应收款调整分录汇总表 K1-4」：
 * 调整事项说明 / 类别(账项·报表·其他) / 报表项目 / 科目名称 / 附注项目 /
 * 借方调整金额 / 贷方调整金额 / 索引 / 备注
 *
 * 联动：中央调整分录模块双向同步；1221/1231 净额回写 K1-1；账项可推送 A13
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
import { applyK14NetsToK11, type K14WritebackResult } from './k1AdjK11Writeback'

export type K1AdjCategory = '账项调整' | '报表调整' | '其他'

export interface K1AdjustmentRow {
  rowId: string
  seq: number
  description: string
  category: K1AdjCategory | string
  entryType: 'AJE' | 'RJE' | ''
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  sourceKind?: string
  sourceGroupId?: string
  /** @deprecated 旧字段 */
  id?: string
  summary?: string
  preparedBy?: string
}

export interface K1BalanceCheck {
  debitTotal: number
  creditTotal: number
  diff: number
  isBalanced: boolean
  warning: string
}

const ROWS_KEY = 'K1-4-adj-entries'
const AJE_NET_KEY = 'K1-4-aje-net'
const RJE_NET_KEY = 'K1-4-rje-net'
const BD_AJE_NET_KEY = 'K1-4-bd-aje-net'
const BD_RJE_NET_KEY = 'K1-4-bd-rje-net'
const NOTE_KEY = 'K1-4-audit-note'
const LEGACY_AJE_TOTAL = 'K1-1-aje-total'
const LEGACY_RJE_TOTAL = 'K1-1-rje-total'
const WP_CODE = 'K1'
const BALANCE_TOLERANCE = 0.01

/** 中央模块同步：含这些科目前缀即视为其他应收款相关 */
const K1_RELATED_PREFIXES = ['1221', '1231', '6702', '6603', '1002', '1122', '1123', '2241']

export const K1_CATEGORY_OPTIONS: readonly K1AdjCategory[] = ['账项调整', '报表调整', '其他']

export const K1_ADJ_ACCOUNT_OPTIONS = [
  { code: '1221', name: '其他应收款' },
  { code: '1231', name: '坏账准备' },
  { code: '6702', name: '信用减值损失' },
  { code: '6603', name: '财务费用' },
  { code: '1002', name: '银行存款' },
  { code: '1122', name: '应收账款' },
  { code: '1123', name: '预付账款' },
  { code: '2241', name: '其他应付款' },
] as const

function generateRowId(): string {
  return `k1a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function parseAmt(v: unknown): number {
  if (v == null || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function calcSubtotal(nums: number[]): number {
  return nums.reduce((s, n) => s + (Number.isFinite(n) ? n : 0), 0)
}

export function categoryFromLegacy(raw: {
  category?: string
  entryType?: string
  adjustType?: string
}): K1AdjCategory {
  const cat = String(raw.category || '').trim()
  if ((K1_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat as K1AdjCategory
  if (cat === '重分类调整') return '报表调整'
  const legacy = String(raw.entryType || raw.adjustType || '').toUpperCase()
  if (legacy === 'RJE' || cat.includes('报表') || cat.includes('重分类')) return '报表调整'
  if (cat.includes('其他')) return '其他'
  return '账项调整'
}

export function entryTypeFromCategory(category: string): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

function categoryFromEntryType(et: 'AJE' | 'RJE'): K1AdjCategory {
  return et === 'RJE' ? '报表调整' : '账项调整'
}

function isK1RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return K1_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function isReceivableAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1221' || c.startsWith('1221')
}

function isBadDebtAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1231' || c.startsWith('1231') || /坏账/.test(c)
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

function parseRowsPayload(raw: unknown): any[] | null {
  if (!raw) return null
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

function _getJson(allResponses: Map<string, any>, itemId: string): any {
  const item = allResponses.get(itemId)
  if (!item) return null
  const raw = item.remark ?? item.value ?? item.conclusion
  if (Array.isArray(raw)) return raw
  return parseRowsPayload(raw)
}

function _getString(allResponses: Map<string, any>, itemId: string): string {
  const item = allResponses.get(itemId)
  return String(item?.remark ?? item?.conclusion ?? '')
}

function _readNetKey(allResponses: Map<string, any>, key: string): number {
  const item = allResponses.get(key)
  const raw = item?.remark ?? item?.value
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

export interface K14AdjustmentNets {
  rowCount: number
  receivableAjeNet: number
  receivableRjeNet: number
  badDebtAjeNet: number
  badDebtRjeNet: number
}

/** 从 K1-4 行或持久化 net key 读取 1221/1231 账项与报表调整净额 */
export function readK14AdjustmentNets(allResponses: Map<string, any>): K14AdjustmentNets {
  const rows = _getJson(allResponses, ROWS_KEY)
  if (Array.isArray(rows) && rows.length > 0) {
    let receivableAjeNet = 0
    let receivableRjeNet = 0
    let badDebtAjeNet = 0
    let badDebtRjeNet = 0
    for (const raw of rows) {
      const r = normalizeK1AdjustmentRow(raw, 0)
      const net = r.debitAmount - r.creditAmount
      const isRje = r.category === '报表调整' || r.entryType === 'RJE'
      if (isReceivableAccount(r.accountCode)) {
        if (isRje) receivableRjeNet += net
        else receivableAjeNet += net
      }
      if (isBadDebtAccount(r.accountCode)) {
        if (isRje) badDebtRjeNet += net
        else badDebtAjeNet += net
      }
    }
    return {
      rowCount: rows.length,
      receivableAjeNet,
      receivableRjeNet,
      badDebtAjeNet,
      badDebtRjeNet,
    }
  }
  return {
    rowCount: 0,
    receivableAjeNet: _readNetKey(allResponses, AJE_NET_KEY),
    receivableRjeNet: _readNetKey(allResponses, RJE_NET_KEY),
    badDebtAjeNet: _readNetKey(allResponses, BD_AJE_NET_KEY),
    badDebtRjeNet: _readNetKey(allResponses, BD_RJE_NET_KEY),
  }
}

export function normalizeK1AdjustmentRow(raw: any, idx: number): K1AdjustmentRow {
  const category = categoryFromLegacy(raw)
  const entryType = entryTypeFromCategory(category)
  const description = String(raw.description || raw.summary || raw.reason || '').trim()
  const code = String(raw.accountCode ?? '').trim()
  const known = K1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
  const reportItem = raw.reportItem
    ?? (isBadDebtAccount(code) ? '坏账准备' : '其他应收款')
  const noteItem = raw.noteItem
    ?? (isBadDebtAccount(code) ? '坏账准备' : '其他应收款')
  return {
    rowId: raw.rowId ?? raw.id ?? generateRowId(),
    seq: raw.seq ?? idx + 1,
    description,
    category,
    entryType,
    reportItem,
    accountCode: code,
    accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '',
    noteItem,
    debitAmount: parseAmt(raw.debitAmount ?? raw.debit),
    creditAmount: parseAmt(raw.creditAmount ?? raw.credit),
    indexRef: String(raw.indexRef ?? raw.refIndex ?? raw.reference ?? '').trim(),
    remark: String(raw.remark ?? '').trim(),
    sourceKind: raw.sourceKind ? String(raw.sourceKind) : undefined,
    sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    id: raw.id,
    summary: raw.summary || description,
    preparedBy: raw.preparedBy,
  }
}

export function useK1Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
  /** K1-4 保存后自动回写 K1-1 组合行 AJE/RJE */
  onSyncToK11?: () => K14WritebackResult
}) {
  const { allResponses, onSave, onPublishEvent, onSyncToK11 } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const rows = ref<K1AdjustmentRow[]>([])
  const auditNote = ref('')
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const lastPushMsg = ref('')

  function load(): void {
    const data = _getJson(allResponses.value, ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r, i) => normalizeK1AdjustmentRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(allResponses.value, NOTE_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const balanceCheck = computed<K1BalanceCheck>(() => {
    const diff = balanceDiff.value
    return {
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      diff,
      isBalanced: isBalanced.value,
      warning: isBalanced.value ? '' : `借贷不平衡，差额：${diff > 0 ? '+' : ''}${diff.toFixed(2)}元`,
    }
  })

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

  const receivableAjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isReceivableAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const receivableRjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      if (!isReceivableAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const badDebtAjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isBadDebtAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const badDebtRjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      if (!isBadDebtAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  function _toPersistShape(list: K1AdjustmentRow[]) {
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
      indexRef: r.indexRef,
      remark: r.remark,
      sourceKind: r.sourceKind,
      sourceGroupId: r.sourceGroupId,
      summary: r.description,
    }))
  }

  function _writeNetKeys(recAje: number, recRje: number, bdAje: number, bdRje: number): void {
    if (!onSave) return
    const pairs: [string, number][] = [
      [AJE_NET_KEY, recAje],
      [RJE_NET_KEY, recRje],
      [BD_AJE_NET_KEY, bdAje],
      [BD_RJE_NET_KEY, bdRje],
      [LEGACY_AJE_TOTAL, recAje],
      [LEGACY_RJE_TOTAL, recRje],
    ]
    for (const [key, val] of pairs) {
      onSave(key, typeof val === 'number' ? (key.includes('total') ? val : String(val)) : val)
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, {
        ...existing,
        item_id: key,
        remark: String(val),
        value: val,
      })
    }
  }

  function _persist(list?: K1AdjustmentRow[]): void {
    if (!onSave) return
    const next = list ?? rows.value
    const shaped = _toPersistShape(next)
    const normalized = shaped.map((r, i) => normalizeK1AdjustmentRow(r, i))
    rows.value = normalized
    onSave(ROWS_KEY, shaped)
    const existing = allResponses.value.get(ROWS_KEY) || { item_id: ROWS_KEY, conclusion: null, remark: null }
    allResponses.value.set(ROWS_KEY, {
      ...existing,
      item_id: ROWS_KEY,
      remark: JSON.stringify(shaped),
    })
    _writeNetKeys(
      receivableAjeNet.value,
      receivableRjeNet.value,
      badDebtAjeNet.value,
      badDebtRjeNet.value,
    )
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
      reportItem: '其他应收款',
      accountCode: '1221',
      accountName: '其他应收款',
      noteItem: '其他应收款',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: 'K1-4',
      remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: keyof K1AdjustmentRow | string, value: any): void {
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
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const known = K1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) {
        row.accountName = known.name
        if (isBadDebtAccount(row.accountCode)) {
          row.reportItem = '坏账准备'
          row.noteItem = '坏账准备'
        } else if (isReceivableAccount(row.accountCode)) {
          row.reportItem = '其他应收款'
          row.noteItem = '其他应收款'
        }
      }
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

  function updateRow(rowId: string, patch: Partial<K1AdjustmentRow>): void {
    if (isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    if (patch.category != null) row.entryType = entryTypeFromCategory(String(patch.category))
    if (patch.accountCode != null) {
      const known = K1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(patch.accountCode))
      if (known) row.accountName = known.name
    }
    _persist()
  }

  function publishAdjustment(): void {
    const payload = {
      wp_code: WP_CODE,
      wpCode: WP_CODE,
      accountCode: '1221',
      projectId: params.projectId.value,
      ajeTotal: receivableAjeNet.value,
      rjeTotal: receivableRjeNet.value,
      entryCount: rows.value.length,
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
      receivableAjeNet: receivableAjeNet.value,
      receivableRjeNet: receivableRjeNet.value,
      badDebtAjeNet: badDebtAjeNet.value,
      badDebtRjeNet: badDebtRjeNet.value,
    }
    onPublishEvent?.('adjustment:created', payload)
    try {
      eventBus.emit('adjustment:created', payload as any)
      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
    } catch {
      /* silent */
    }
  }

  function publishAndSync(): K14WritebackResult | undefined {
    _writeNetKeys(
      receivableAjeNet.value,
      receivableRjeNet.value,
      badDebtAjeNet.value,
      badDebtRjeNet.value,
    )
    publishAdjustment()
    const k11 = onSyncToK11?.()
    if (k11?.applied) {
      try {
        eventBus.emit('k1:adj-sync-k11', {
          wpCode: WP_CODE,
          message: k11.message,
          receivableAjeNet: receivableAjeNet.value,
          receivableRjeNet: receivableRjeNet.value,
          badDebtAjeNet: badDebtAjeNet.value,
          badDebtRjeNet: badDebtRjeNet.value,
        })
      } catch {
        /* silent */
      }
    }
    return k11
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
      indexRef: r.indexRef || 'K1-4',
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

    const groups = new Map<string, K1AdjustmentRow[]>()
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
            description: `[K1] ${lines[0].description || '其他应收款调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '1221',
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

      const imported: K1AdjustmentRow[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isK1RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        const has1221 = lines.some((li: any) =>
          isReceivableAccount(li.standard_account_code || li.account_code),
        )
        if (!has1221) continue

        const groupId = String(item.entry_group_id || item.id || '')
        const et = entryTypeFromModule(item.adjustment_type || item.type)
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[K1\]\s*/,
          '',
        )
        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          imported.push(
            normalizeK1AdjustmentRow(
              {
                rowId: `${groupId}-${imported.length}`,
                description: desc,
                category: categoryFromEntryType(et),
                entryType: et,
                reportItem: isBadDebtAccount(accountCode) ? '坏账准备' : '其他应收款',
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
        : '调整分录模块中无含 1221 的相关分录'
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

  function save(): void {
    _persist()
  }

  function onModuleUpdated(): void {
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
    ajeNet,
    rjeNet,
    receivableAjeNet,
    receivableRjeNet,
    badDebtAjeNet,
    badDebtRjeNet,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    categoryOptions: K1_CATEGORY_OPTIONS,
    accountOptions: K1_ADJ_ACCOUNT_OPTIONS,
    addRow,
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
    saveNote,
  }
}

export default useK1Adjustment
