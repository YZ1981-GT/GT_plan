/**
 * useG6SppiReconciliation — G6-10 盘点倒轧表（18列→2区段Tab）
 *
 * 公式口径（formulaVersion=2）：
 * - changeQuantity = 两日之间持仓净增加（买入为正、卖出/到期/转让为负）
 * - 期后盘点(backward)：报表日 = 盘点日 − 净增加
 * - 期前盘点(forward)：报表日 = 盘点日 + 净增加
 * - 同日：报表日 = 盘点日
 *
 * 旧数据（无 formulaVersion）：将手工增减取反迁移到新口径。
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  calcInventoryRollForwardByDirection,
  calcInventoryVariance,
  parseNum,
  signedRollForwardChangeQty,
  resolveRollForwardDirection,
  migrateLegacyChangeToNetIncrease,
  type RollForwardDirection,
} from '@/composables/useG6SppiFormulaEngine'
import { normalizeG6InvestName } from './g6CrossHelpers'
import type { InventoryItem } from './useG6SppiInventory'

export const CURRENT_FORMULA_VERSION = 2
export type ChangeConvention = 'period_net_increase' | 'legacy_count_to_bs_adjust'
export type ChangeSource = 'manual' | 'detailDerived'

export interface ReconciliationHeader {
  countDate: string
  balanceSheetDate: string
}

export interface ReconciliationItem {
  id: string
  seq: number
  securitiesName: string
  /** 证券代码（优先匹配键） */
  securitiesCode?: string
  /** 来源盘点行 ID（G6-9 item.id） */
  sourceItemId?: string
  countDateQuantity: number
  /** 两日之间持仓净增加；可由 Tab2 自动汇总 */
  changeQuantity: number
  reportDateQuantity: number
  bookQuantity: number
  variance: number
  varianceReason: string
  varianceConclusion: string
  indexRef: string
  remark: string
  /** 增减来源：有明细时 detailDerived；否则 manual */
  changeSource?: ChangeSource
}

export interface ChangeDetailItem {
  id: string
  securitiesName: string
  securitiesCode?: string
  /** 关联 Tab1 行 id */
  linkedItemId?: string
  date: string
  transactionType: 'buy' | 'sell' | 'mature' | 'transfer' | 'transfer_in' | 'transfer_out' | ''
  quantity: number
  amount: number
  voucherNo: string
  handler: string
  remark: string
}

export interface ReconciliationData {
  formulaVersion?: number
  changeConvention?: ChangeConvention
  header?: ReconciliationHeader
  activeTab: 'rollForward' | 'changeDetail'
  selectedRowIndex: number
  items: ReconciliationItem[]
  changeDetails: ChangeDetailItem[]
  /** @deprecated 结论已独立存 G6-10-audit-conclusion；保留兼容读取 */
  auditConclusion?: string
}

export type InventorySourceItem = Pick<
  InventoryItem,
  'id' | 'securitiesName' | 'securitiesCode' | 'countQuantity' | 'bookQuantity' | 'indexRef'
>

/** 账面数量种子（G6-2 / G6-9） */
export type BookQuantitySeed = {
  id?: string
  securitiesName: string
  securitiesCode?: string
  bookQuantity: number
}

export const TRANSACTION_TYPE_OPTIONS = [
  { value: 'buy', label: '买入' },
  { value: 'sell', label: '卖出' },
  { value: 'mature', label: '到期' },
  { value: 'transfer_in', label: '转入' },
  { value: 'transfer_out', label: '转出' },
  { value: 'transfer', label: '转让(转出)' },
] as const

export const VALID_TX_TYPES = new Set(
  TRANSACTION_TYPE_OPTIONS.map((o) => o.value).filter((v) => v !== 'transfer'),
)

/** 归一化证券代码 */
export function normalizeSecuritiesCode(code: string | undefined | null): string {
  return String(code || '').trim().replace(/\s+/g, '').toUpperCase()
}

/**
 * 证券匹配键：代码 > 来源/关联ID > 名称
 * 用于 Tab1↔Tab2 汇总与导入对齐
 */
export function securityMatchKey(parts: {
  securitiesCode?: string
  sourceItemId?: string
  linkedItemId?: string
  id?: string
  securitiesName?: string
}): string {
  const code = normalizeSecuritiesCode(parts.securitiesCode)
  if (code) return `code:${code}`
  const src = String(parts.sourceItemId || parts.linkedItemId || '').trim()
  if (src) return `src:${src}`
  const name = normalizeG6InvestName(parts.securitiesName || '')
  return name ? `name:${name}` : ''
}

/** 一行可能对应的全部匹配键（便于明细只填名称时仍能对上有代码的主表行） */
export function securityMatchKeysForItem(item: ReconciliationItem): string[] {
  const keys: string[] = []
  const code = normalizeSecuritiesCode(item.securitiesCode)
  if (code) keys.push(`code:${code}`)
  if (item.sourceItemId) keys.push(`src:${item.sourceItemId}`)
  if (item.id) keys.push(`src:${item.id}`)
  const name = normalizeG6InvestName(item.securitiesName)
  if (name) keys.push(`name:${name}`)
  return keys
}

/** 按匹配键汇总期间净增加 */
export function aggregateNetChangeByKey(
  details: ChangeDetailItem[],
): Map<string, number> {
  const map = new Map<string, number>()
  for (const d of details) {
    const key = securityMatchKey(d)
    if (!key) continue
    const signed = signedRollForwardChangeQty(d.transactionType, d.quantity)
    map.set(key, (map.get(key) || 0) + signed)
  }
  return map
}

/** @deprecated 兼容旧调用：按名称汇总 */
export function aggregateNetChangeByName(
  details: ChangeDetailItem[],
): Map<string, number> {
  const map = new Map<string, number>()
  for (const d of details) {
    const key = normalizeG6InvestName(d.securitiesName)
    if (!key) continue
    const signed = signedRollForwardChangeQty(d.transactionType, d.quantity)
    map.set(key, (map.get(key) || 0) + signed)
  }
  return map
}

export interface DetailValidationIssue {
  detail: ChangeDetailItem
  index: number
  reasons: string[]
}

export function isDateInRollForwardPeriod(
  date: string,
  countDate: string,
  balanceSheetDate: string,
): boolean {
  const d = String(date || '').trim()
  const c = String(countDate || '').trim()
  const b = String(balanceSheetDate || '').trim()
  if (!d) return false
  if (!c || !b) return true // 日期未齐时不拦
  const dv = new Date(`${d}T00:00:00`).getTime()
  const cv = new Date(`${c}T00:00:00`).getTime()
  const bv = new Date(`${b}T00:00:00`).getTime()
  if (Number.isNaN(dv) || Number.isNaN(cv) || Number.isNaN(bv)) return false
  const lo = Math.min(cv, bv)
  const hi = Math.max(cv, bv)
  return dv >= lo && dv <= hi
}

function createEmptyItem(name: string, seq: number, extra?: Partial<ReconciliationItem>): ReconciliationItem {
  return {
    id: `recon-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    securitiesName: name,
    securitiesCode: '',
    sourceItemId: '',
    countDateQuantity: 0,
    changeQuantity: 0,
    reportDateQuantity: 0,
    bookQuantity: 0,
    variance: 0,
    varianceReason: '',
    varianceConclusion: '',
    indexRef: '',
    remark: '',
    changeSource: 'manual',
    ...extra,
  }
}

function directionLabel(dir: RollForwardDirection): string {
  switch (dir) {
    case 'backward': return '期后盘点·倒推'
    case 'forward': return '期前盘点·顺推'
    case 'sameDay': return '同日盘点·无需倒轧'
    default: return '日期未齐·默认倒推'
  }
}

export function useG6SppiReconciliation() {
  const items = ref<ReconciliationItem[]>([])
  const changeDetails = ref<ChangeDetailItem[]>([])
  const activeTab = ref<'rollForward' | 'changeDetail'>('rollForward')
  const selectedRowIndex = ref(0)
  /** 本地草稿结论（正式持久化走独立 key，见页面层） */
  const auditConclusion = ref('')
  const header = ref<ReconciliationHeader>({ countDate: '', balanceSheetDate: '' })
  const formulaVersion = ref(CURRENT_FORMULA_VERSION)
  const changeConvention = ref<ChangeConvention>('period_net_increase')
  const migratedFromLegacy = ref(false)
  const _suppressAggregate = ref(false)

  const rollDirection = computed(() =>
    resolveRollForwardDirection(header.value.countDate, header.value.balanceSheetDate),
  )

  const periodHint = computed(() => {
    const dir = rollDirection.value
    const label = directionLabel(dir)
    const c = header.value.countDate || '（盘点日未填）'
    const b = header.value.balanceSheetDate || '（报表日未填）'
    if (dir === 'sameDay') return `${label}：${c}`
    if (dir === 'forward') return `${label}：${c} → ${b}`
    if (dir === 'backward') return `${label}：${b} → ${c}`
    return `${label}：请填写盘点日与资产负债表日`
  })

  function recalcRow(row: ReconciliationItem): void {
    row.reportDateQuantity = calcInventoryRollForwardByDirection(
      parseNum(row.countDateQuantity),
      parseNum(row.changeQuantity),
      rollDirection.value,
    )
    row.variance = calcInventoryVariance(
      row.reportDateQuantity,
      parseNum(row.bookQuantity),
    )
  }

  function recalcAll(): void {
    for (const row of items.value) recalcRow(row)
  }

  /** 明细 → 主表行：优先 linkedItemId，再代码/来源ID/名称 */
  function findItemForDetail(d: ChangeDetailItem): ReconciliationItem | undefined {
    const linked = String(d.linkedItemId || '').trim()
    if (linked) {
      const byId = items.value.find((row) => row.id === linked)
      if (byId) return byId
    }
    const dk = securityMatchKey(d)
    if (dk) {
      const byKey = items.value.find((row) => securityMatchKeysForItem(row).includes(dk))
      if (byKey) return byKey
    }
    const nk = normalizeG6InvestName(d.securitiesName)
    if (!nk) return undefined
    return items.value.find((row) => securityMatchKeysForItem(row).includes(`name:${nk}`))
  }

  /** 回写明细与主表的代码/关联 ID */
  function bindDetailToItem(d: ChangeDetailItem, item: ReconciliationItem): void {
    d.linkedItemId = item.id
    if (item.securitiesCode && !d.securitiesCode) d.securitiesCode = item.securitiesCode
    if (d.securitiesCode && !item.securitiesCode) item.securitiesCode = d.securitiesCode
  }

  /** 全量重绑明细关联（加载/导入后调用） */
  function relinkDetailsToItems(): number {
    let n = 0
    for (const d of changeDetails.value) {
      const matched = findItemForDetail(d)
      if (!matched) continue
      const before = d.linkedItemId
      bindDetailToItem(d, matched)
      if (d.linkedItemId !== before) n += 1
    }
    return n
  }

  /**
   * Tab2 → Tab1 汇总（按代码/来源ID/名称匹配到具体行后按行累计）。
   */
  function syncChangeQuantityFromDetails(): number {
    if (_suppressAggregate.value) return 0

    const netByItemId = new Map<string, number>()
    for (const d of changeDetails.value) {
      const matched = findItemForDetail(d)
      if (!matched) continue
      bindDetailToItem(d, matched)
      const signed = signedRollForwardChangeQty(d.transactionType, d.quantity)
      netByItemId.set(matched.id, (netByItemId.get(matched.id) || 0) + signed)
    }

    let updated = 0
    for (const row of items.value) {
      if (netByItemId.has(row.id)) {
        const next = netByItemId.get(row.id) || 0
        if (parseNum(row.changeQuantity) !== next || row.changeSource !== 'detailDerived') {
          row.changeQuantity = next
          row.changeSource = 'detailDerived'
          updated += 1
        }
      } else if (row.changeSource === 'detailDerived') {
        row.changeQuantity = 0
        row.changeSource = 'manual'
        updated += 1
      }
      recalcRow(row)
    }
    return updated
  }

  watch(items, () => { recalcAll() }, { deep: true })
  watch(changeDetails, () => { syncChangeQuantityFromDetails() }, { deep: true })
  watch(header, () => { recalcAll() }, { deep: true })

  function hasVariance(row: ReconciliationItem): boolean {
    return Math.abs(parseNum(row.variance)) > 0
  }

  function getVarianceCellStyle(row: ReconciliationItem): Record<string, string> {
    if (hasVariance(row)) {
      return { backgroundColor: '#fef2f2', color: '#dc2626', fontWeight: '600' }
    }
    return {}
  }

  function isVarianceReasonMissing(row: ReconciliationItem): boolean {
    return hasVariance(row) && !row.varianceReason.trim()
  }

  function isVarianceConclusionMissing(row: ReconciliationItem): boolean {
    return hasVariance(row) && !row.varianceConclusion.trim()
  }

  const itemKeySet = computed(() => {
    const set = new Set<string>()
    for (const row of items.value) {
      for (const k of securityMatchKeysForItem(row)) set.add(k)
    }
    return set
  })

  function validateChangeDetail(
    d: ChangeDetailItem,
    index: number,
  ): DetailValidationIssue | null {
    const reasons: string[] = []
    if (!String(d.securitiesName || '').trim()) reasons.push('证券名称不能为空')
    if (!d.transactionType) reasons.push('交易类型必填')
    if (parseNum(d.quantity) <= 0) reasons.push('数量须大于0')
    if (!String(d.date || '').trim()) {
      reasons.push('交易日期必填')
    } else if (
      header.value.countDate
      && header.value.balanceSheetDate
      && !isDateInRollForwardPeriod(d.date, header.value.countDate, header.value.balanceSheetDate)
    ) {
      reasons.push('交易日期须落在盘点日与资产负债表日之间')
    }
    if (!String(d.voucherNo || '').trim()) reasons.push('凭证号必填')

    const dKey = securityMatchKey(d)
    const linkedOk = Boolean(d.linkedItemId && items.value.some((r) => r.id === d.linkedItemId))
    if (dKey && itemKeySet.value.size > 0 && !itemKeySet.value.has(dKey) && !linkedOk) {
      // 名称键兜底：明细无代码时，若名称对应某主表行则放行
      const nameKey = normalizeG6InvestName(d.securitiesName)
        ? `name:${normalizeG6InvestName(d.securitiesName)}`
        : ''
      if (!nameKey || !itemKeySet.value.has(nameKey)) {
        reasons.push('证券未出现在倒轧计算表中')
      }
    }

    if (reasons.length === 0) return null
    return { detail: d, index, reasons }
  }

  const varianceValidationErrors = computed(() => {
    const issues: Array<{ row: ReconciliationItem; index: number; field: 'reason' | 'conclusion' }> = []
    for (let i = 0; i < items.value.length; i++) {
      const row = items.value[i]
      if (isVarianceReasonMissing(row)) {
        issues.push({ row, index: i, field: 'reason' })
      } else if (isVarianceConclusionMissing(row)) {
        issues.push({ row, index: i, field: 'conclusion' })
      }
    }
    return issues
  })

  const detailValidationErrors = computed(() => {
    const issues: DetailValidationIssue[] = []
    changeDetails.value.forEach((d, i) => {
      const issue = validateChangeDetail(d, i)
      if (issue) issues.push(issue)
    })
    return issues
  })

  const isVarianceValid = computed(() =>
    varianceValidationErrors.value.length === 0 && detailValidationErrors.value.length === 0,
  )

  function assertVarianceValidForSave(actionLabel = '保存审计结论'): boolean {
    if (isVarianceValid.value) return true
    const parts: string[] = []
    if (varianceValidationErrors.value.length) {
      const names = varianceValidationErrors.value
        .map((e) => `${e.row.securitiesName}(${e.field === 'reason' ? '缺原因' : '缺结论'})`)
        .slice(0, 3)
        .join('、')
      parts.push(`差异未闭环：${names}`)
    }
    if (detailValidationErrors.value.length) {
      parts.push(`增减明细校验失败 ${detailValidationErrors.value.length} 条`)
    }
    ElMessage.error(`无法${actionLabel}。${parts.join('；')}`)
    return false
  }

  function hasAutoChangeSource(rowOrName: ReconciliationItem | string): boolean {
    if (typeof rowOrName === 'string') {
      const key = normalizeG6InvestName(rowOrName)
      if (!key) return false
      return changeDetails.value.some((d) => {
        const dk = securityMatchKey(d)
        return dk === `name:${key}` || normalizeG6InvestName(d.securitiesName) === key
      })
    }
    const keys = new Set(securityMatchKeysForItem(rowOrName))
    return changeDetails.value.some((d) => {
      const dk = securityMatchKey(d)
      if (dk && keys.has(dk)) return true
      const nk = normalizeG6InvestName(d.securitiesName)
      return nk && keys.has(`name:${nk}`)
    })
  }

  function updateHeader(patch: Partial<ReconciliationHeader>): void {
    header.value = { ...header.value, ...patch }
    recalcAll()
  }

  async function addItem(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增倒轧计算行',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '证券名称不能为空',
          inputPlaceholder: '例如：XX公司债券',
        },
      )
      if (!value?.trim()) return
      items.value.push(createEmptyItem(value.trim(), items.value.length + 1))
      syncChangeQuantityFromDetails()
      selectedRowIndex.value = items.value.length - 1
      ElMessage.success(`已新增"${value.trim()}"`)
    } catch { /* cancel */ }
  }

  async function removeItem(id: string): Promise<void> {
    const row = items.value.find(r => r.id === id)
    if (!row) return
    try {
      await ElMessageBox.confirm(
        `确认删除"${row.securitiesName}"？`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      items.value = items.value.filter(r => r.id !== id)
      items.value.forEach((r, i) => { r.seq = i + 1 })
      if (selectedRowIndex.value >= items.value.length) {
        selectedRowIndex.value = Math.max(0, items.value.length - 1)
      }
      ElMessage.success(`已删除"${row.securitiesName}"`)
    } catch { /* cancel */ }
  }

  async function addChangeDetail(): Promise<void> {
    try {
      const selected = items.value[selectedRowIndex.value]
      const defaultName = selected?.securitiesName || ''
      const { value } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增增减明细',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '证券名称不能为空',
          inputPlaceholder: '例如：XX公司债券',
          inputValue: defaultName,
        },
      )
      if (!value?.trim()) return
      const name = value.trim()
      const matched = items.value.find(
        (r) => normalizeG6InvestName(r.securitiesName) === normalizeG6InvestName(name),
      ) || (selected && normalizeG6InvestName(selected.securitiesName) === normalizeG6InvestName(name) ? selected : undefined)
      changeDetails.value.push({
        id: `cd-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        securitiesName: name,
        securitiesCode: matched?.securitiesCode || '',
        linkedItemId: matched?.id || '',
        date: '',
        transactionType: '',
        quantity: 0,
        amount: 0,
        voucherNo: '',
        handler: '',
        remark: '',
      })
      ElMessage.success(`已新增增减明细"${name}"`)
    } catch { /* cancel */ }
  }

  async function removeChangeDetail(id: string): Promise<void> {
    const detail = changeDetails.value.find(r => r.id === id)
    if (!detail) return
    try {
      await ElMessageBox.confirm(
        `确认删除"${detail.securitiesName}"的增减明细？`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      changeDetails.value = changeDetails.value.filter(r => r.id !== id)
      ElMessage.success(`已删除增减明细"${detail.securitiesName}"`)
    } catch { /* cancel */ }
  }

  /**
   * 从 G6-9 同步：仅带入盘点日数量、证券代码、来源ID。
   * 不覆盖账面数量。
   */
  function syncFromInventory(
    inventoryItems: InventorySourceItem[],
  ): { added: number; updated: number } {
    let added = 0
    let updated = 0
    const byKey = new Map<string, ReconciliationItem>()
    for (const row of items.value) {
      for (const k of securityMatchKeysForItem(row)) {
        if (!byKey.has(k)) byKey.set(k, row)
      }
    }

    for (const inv of inventoryItems || []) {
      const name = (inv.securitiesName || '').trim()
      if (!name) continue
      const invKey = securityMatchKey({
        securitiesCode: inv.securitiesCode,
        sourceItemId: inv.id,
        securitiesName: name,
      })
      const existing = (invKey && byKey.get(invKey))
        || byKey.get(`name:${normalizeG6InvestName(name)}`)
      if (existing) {
        existing.countDateQuantity = parseNum(inv.countQuantity)
        if (inv.securitiesCode && !existing.securitiesCode) {
          existing.securitiesCode = String(inv.securitiesCode)
        }
        if (inv.id && !existing.sourceItemId) existing.sourceItemId = String(inv.id)
        if (inv.indexRef && !existing.indexRef) existing.indexRef = inv.indexRef
        if (!existing.indexRef) existing.indexRef = 'G6-9'
        recalcRow(existing)
        updated += 1
      } else {
        const row = createEmptyItem(name, items.value.length + 1, {
          securitiesCode: String(inv.securitiesCode || ''),
          sourceItemId: String(inv.id || ''),
          countDateQuantity: parseNum(inv.countQuantity),
          bookQuantity: 0,
          indexRef: inv.indexRef || 'G6-9',
          remark: inv.securitiesCode ? `代码:${inv.securitiesCode}` : '',
        })
        recalcRow(row)
        items.value.push(row)
        for (const k of securityMatchKeysForItem(row)) byKey.set(k, row)
        added += 1
      }
    }
    items.value.forEach((r, i) => { r.seq = i + 1 })
    syncChangeQuantityFromDetails()
    return { added, updated }
  }

  function importFromInventory(
    inventoryItems: InventorySourceItem[] | null | undefined,
  ): { added: number; updated: number } {
    if (!inventoryItems?.length) {
      ElMessageBox.alert('未找到 G6-9 盘点表数据，请先编制有价证券盘点表。', '提示')
      return { added: 0, updated: 0 }
    }
    const result = syncFromInventory(inventoryItems)
    relinkDetailsToItems()
    selectedRowIndex.value = 0
    activeTab.value = 'rollForward'
    ElMessage.success(
      `已从 G6-9 带入盘点日数量：新增 ${result.added} 行，更新 ${result.updated} 行（账面数量请按报表日另行填写）`,
    )
    return result
  }

  /**
   * 仅更新匹配行的账面数量（报表日口径），不改盘点日数量/增减。
   * 不新增行——应先从 G6-9 带入盘点清单。
   */
  function syncBookFromSeeds(
    seeds: BookQuantitySeed[],
  ): { updated: number; unmatched: number; zeroCount: number } {
    let updated = 0
    let unmatched = 0
    let zeroCount = 0
    const byKey = new Map<string, ReconciliationItem>()
    for (const row of items.value) {
      for (const k of securityMatchKeysForItem(row)) {
        if (!byKey.has(k)) byKey.set(k, row)
      }
    }

    for (const seed of seeds || []) {
      const name = (seed.securitiesName || '').trim()
      if (!name) continue
      const qty = parseNum(seed.bookQuantity)
      if (qty === 0) zeroCount += 1
      const seedKey = securityMatchKey({
        securitiesCode: seed.securitiesCode,
        sourceItemId: seed.id,
        securitiesName: name,
      })
      const existing = (seedKey && byKey.get(seedKey))
        || byKey.get(`name:${normalizeG6InvestName(name)}`)
      if (!existing) {
        unmatched += 1
        continue
      }
      existing.bookQuantity = qty
      if (seed.securitiesCode && !existing.securitiesCode) {
        existing.securitiesCode = String(seed.securitiesCode)
      }
      recalcRow(existing)
      updated += 1
    }
    return { updated, unmatched, zeroCount }
  }

  function importBookFromSeeds(
    seeds: BookQuantitySeed[] | null | undefined,
    sourceLabel = '明细表',
  ): { updated: number; unmatched: number; zeroCount: number } {
    if (!seeds?.length) {
      ElMessage.warning(`未从 ${sourceLabel} 取到可带入的账面数量`)
      return { updated: 0, unmatched: 0, zeroCount: 0 }
    }
    if (!items.value.length) {
      ElMessage.warning('倒轧计算表为空，请先「从 G6-9 带入盘点」')
      return { updated: 0, unmatched: 0, zeroCount: 0 }
    }
    const result = syncBookFromSeeds(seeds)
    if (result.updated === 0) {
      ElMessage.warning(
        `未能匹配任何证券。请确认 ${sourceLabel} 与倒轧表名称/代码一致。`,
      )
      return result
    }
    const extra: string[] = []
    if (result.unmatched) extra.push(`未匹配 ${result.unmatched} 项`)
    if (result.zeroCount === seeds.length) {
      extra.push(`${sourceLabel} 账面数量均为 0，请核对是否已维护持仓数量`)
    }
    ElMessage.success(
      `已从 ${sourceLabel} 带入账面数量：更新 ${result.updated} 行` +
        (extra.length ? `（${extra.join('；')}）` : ''),
    )
    return result
  }

  function selectRow(index: number): void {
    if (index >= 0 && index < items.value.length) {
      selectedRowIndex.value = index
    }
  }

  function switchTab(tab: 'rollForward' | 'changeDetail'): void {
    activeTab.value = tab
  }

  /** 旧口径迁移：无 formulaVersion 时，对手工增减取反 */
  function applyLegacyMigration(rawItems: ReconciliationItem[], rawDetails: ChangeDetailItem[]): void {
    const detailKeys = new Set(
      rawDetails.map((d) => securityMatchKey(d)).filter(Boolean),
    )
    for (const row of rawItems) {
      const keys = securityMatchKeysForItem(row)
      const hasDetail = keys.some((k) => detailKeys.has(k))
      if (!hasDetail && parseNum(row.changeQuantity) !== 0) {
        row.changeQuantity = migrateLegacyChangeToNetIncrease(row.changeQuantity)
        row.changeSource = 'manual'
      }
    }
    migratedFromLegacy.value = true
  }

  function loadData(data: ReconciliationData | null): void {
    _suppressAggregate.value = true
    migratedFromLegacy.value = false
    try {
      if (!data) {
        items.value = []
        changeDetails.value = []
        auditConclusion.value = ''
        header.value = { countDate: '', balanceSheetDate: '' }
        formulaVersion.value = CURRENT_FORMULA_VERSION
        changeConvention.value = 'period_net_increase'
        activeTab.value = 'rollForward'
        selectedRowIndex.value = 0
        return
      }

      const isLegacy =
        data.changeConvention === 'legacy_count_to_bs_adjust'
        || Number(data.formulaVersion || 0) === 1

      header.value = {
        countDate: String(data.header?.countDate || ''),
        balanceSheetDate: String(data.header?.balanceSheetDate || ''),
      }

      const mappedItems = (data.items || []).map((r, i) => {
        const item: ReconciliationItem = {
          id: r.id || `recon-${Date.now()}-${i}`,
          seq: i + 1,
          securitiesName: r.securitiesName || '',
          securitiesCode: String(r.securitiesCode || ''),
          sourceItemId: String(r.sourceItemId || ''),
          countDateQuantity: parseNum(r.countDateQuantity),
          changeQuantity: parseNum(r.changeQuantity),
          reportDateQuantity: 0,
          bookQuantity: parseNum(r.bookQuantity),
          variance: 0,
          varianceReason: r.varianceReason || '',
          varianceConclusion: r.varianceConclusion || '',
          indexRef: r.indexRef || '',
          remark: r.remark || '',
          changeSource: r.changeSource === 'detailDerived' ? 'detailDerived' : 'manual',
        }
        return item
      })

      const mappedDetails = (data.changeDetails || []).map((d, i) => ({
        id: d.id || `cd-${Date.now()}-${i}`,
        securitiesName: d.securitiesName || '',
        securitiesCode: String(d.securitiesCode || ''),
        linkedItemId: String(d.linkedItemId || ''),
        date: d.date || '',
        transactionType: d.transactionType || '',
        quantity: parseNum(d.quantity),
        amount: parseNum(d.amount),
        voucherNo: d.voucherNo || '',
        handler: d.handler || '',
        remark: d.remark || '',
      }))

      if (isLegacy) {
        applyLegacyMigration(mappedItems, mappedDetails)
      }

      items.value = mappedItems
      changeDetails.value = mappedDetails
      if (data.auditConclusion) auditConclusion.value = data.auditConclusion
      activeTab.value = data.activeTab || 'rollForward'
      selectedRowIndex.value = data.selectedRowIndex || 0
      formulaVersion.value = CURRENT_FORMULA_VERSION
      changeConvention.value = 'period_net_increase'

      for (const row of items.value) recalcRow(row)
      relinkDetailsToItems()
    } finally {
      _suppressAggregate.value = false
      syncChangeQuantityFromDetails()
    }

    if (migratedFromLegacy.value) {
      ElMessage.info('已将旧版增减口径迁移为「期间净增加」（手工增减已取反）。请复核倒轧结果。')
    }
  }

  function loadFromFlatRows(rows: Array<Record<string, any>> | null | undefined): void {
    if (!rows || !Array.isArray(rows) || rows.length === 0) {
      loadData(null)
      return
    }

    const itemsOut: ReconciliationItem[] = []
    const detailsOut: ChangeDetailItem[] = []
    const seenNames = new Set<string>()

    rows.forEach((r, i) => {
      const name = String(r.securitiesName || '').trim()
      const hasRoll =
        r.countDateQuantity != null ||
        r.changeQuantity != null ||
        r.bookQuantity != null ||
        r.varianceReason ||
        r.varianceConclusion ||
        r.indexRef

      if (name && hasRoll && !seenNames.has(name)) {
        seenNames.add(name)
        itemsOut.push({
          id: r.id || `recon-flat-${i}`,
          seq: itemsOut.length + 1,
          securitiesName: name,
          securitiesCode: String(r.securitiesCode || ''),
          sourceItemId: String(r.sourceItemId || ''),
          countDateQuantity: parseNum(r.countDateQuantity),
          changeQuantity: parseNum(r.changeQuantity),
          reportDateQuantity: 0,
          bookQuantity: parseNum(r.bookQuantity),
          variance: 0,
          varianceReason: r.varianceReason || '',
          varianceConclusion: r.varianceConclusion || '',
          indexRef: r.indexRef || '',
          remark: r.remark || '',
          changeSource: 'manual',
        })
      }

      const hasDetail =
        r.date ||
        r.transactionType ||
        (r.quantity != null && Number(r.quantity) !== 0) ||
        r.voucherNo ||
        r.handler

      if (name && hasDetail) {
        if (hasRoll && !r.transactionType && !r.date) return
        detailsOut.push({
          id: `cd-flat-${i}`,
          securitiesName: name,
          securitiesCode: String(r.securitiesCode || ''),
          linkedItemId: String(r.linkedItemId || ''),
          date: r.date || '',
          transactionType: r.transactionType || '',
          quantity: parseNum(r.quantity),
          amount: parseNum(r.amount),
          voucherNo: r.voucherNo || '',
          handler: r.handler || '',
          remark: hasRoll ? '' : (r.remark || ''),
        })
      }
    })

    loadData({
      formulaVersion: CURRENT_FORMULA_VERSION,
      changeConvention: 'period_net_increase',
      activeTab: 'rollForward',
      selectedRowIndex: 0,
      items: itemsOut,
      changeDetails: detailsOut,
    })
  }

  /** 表格持久化载荷（不含审计结论，结论独立存储） */
  function toJSON(): ReconciliationData {
    return {
      formulaVersion: CURRENT_FORMULA_VERSION,
      changeConvention: 'period_net_increase',
      header: { ...header.value },
      activeTab: activeTab.value,
      selectedRowIndex: selectedRowIndex.value,
      items: items.value.map(r => ({ ...r })),
      changeDetails: changeDetails.value.map(d => ({ ...d })),
    }
  }

  function flattenRows(): Array<Record<string, any>> {
    const out: Array<Record<string, any>> = []
    for (const r of items.value) {
      out.push({
        id: r.id,
        seq: r.seq,
        securitiesName: r.securitiesName,
        securitiesCode: r.securitiesCode,
        sourceItemId: r.sourceItemId,
        countDateQuantity: r.countDateQuantity,
        changeQuantity: r.changeQuantity,
        bookQuantity: r.bookQuantity,
        varianceReason: r.varianceReason,
        varianceConclusion: r.varianceConclusion,
        indexRef: r.indexRef,
        remark: r.remark,
        changeSource: r.changeSource,
      })
    }
    for (const d of changeDetails.value) {
      out.push({
        id: d.id,
        securitiesName: d.securitiesName,
        securitiesCode: d.securitiesCode,
        linkedItemId: d.linkedItemId,
        date: d.date,
        transactionType: d.transactionType,
        quantity: d.quantity,
        amount: d.amount,
        voucherNo: d.voucherNo,
        handler: d.handler,
        remark: d.remark,
      })
    }
    return out
  }

  const varianceCount = computed(() => items.value.filter(hasVariance).length)
  const changeDetailCount = computed(() => changeDetails.value.length)

  return {
    items,
    changeDetails,
    activeTab,
    selectedRowIndex,
    auditConclusion,
    header,
    formulaVersion,
    changeConvention,
    migratedFromLegacy,
    rollDirection,
    periodHint,
    varianceValidationErrors,
    detailValidationErrors,
    isVarianceValid,
    varianceCount,
    changeDetailCount,
    recalcRow,
    recalcAll,
    syncChangeQuantityFromDetails,
    hasVariance,
    getVarianceCellStyle,
    isVarianceReasonMissing,
    isVarianceConclusionMissing,
    assertVarianceValidForSave,
    hasAutoChangeSource,
    updateHeader,
    addItem,
    removeItem,
    addChangeDetail,
    removeChangeDetail,
    syncFromInventory,
    importFromInventory,
    syncBookFromSeeds,
    importBookFromSeeds,
    relinkDetailsToItems,
    selectRow,
    switchTab,
    loadData,
    loadFromFlatRows,
    flattenRows,
    toJSON,
  }
}

export default useG6SppiReconciliation
