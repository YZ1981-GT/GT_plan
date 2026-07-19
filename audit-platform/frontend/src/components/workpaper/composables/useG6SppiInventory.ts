/**
 * useG6SppiInventory — G6-9 有价证券盘点表
 *
 * 职责：
 * - 盘点行模型 + 差异公式（盘点 − 账面）
 * - 差异原因必填校验
 * - 盘点元数据（盘点日 / 是否报表日 / 参加人员 / 托管机构）
 * - 权属与受限字段
 * - 从 G6-2 种子合并（代码优先、名称兜底）
 * - flattenRows 供 Excel IE 双写
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { parseNum } from '@/composables/useG6SppiFormulaEngine'
import { normalizeG6InvestName } from './g6CrossHelpers'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

export type InventoryRestrictionType =
  | ''
  | 'none'
  | 'pledge'
  | 'freeze'
  | 'restricted'
  | 'other'

export const INVENTORY_RESTRICTION_OPTIONS: Array<{ value: InventoryRestrictionType; label: string }> = [
  { value: 'none', label: '无受限' },
  { value: 'pledge', label: '质押' },
  { value: 'freeze', label: '冻结' },
  { value: 'restricted', label: '限售' },
  { value: 'other', label: '其他受限' },
]

export interface InventoryItem {
  id: string
  seq: number
  securitiesName: string
  securitiesCode: string
  faceValue: number
  countQuantity: number
  bookQuantity: number
  variance: number
  varianceReason: string
  varianceConclusion: string
  indexRef: string
  /** 权属主体（账户名/登记主体） */
  ownershipEntity: string
  /** 受限类型 */
  restrictionType: InventoryRestrictionType
  /** 受限说明 */
  restrictionNote: string
  /** 证据索引（托管对账单等） */
  evidenceIndex: string
}

export interface InventoryMeta {
  /** 盘点日 YYYY-MM-DD */
  inventoryDate: string
  /** 是否资产负债表日；null 表示未选择 */
  isBalanceSheetDate: boolean | null
  /** 参加人员 */
  participants: string
  /** 第三方托管机构 */
  custodyInstitution: string
  /** 覆盖范围说明 */
  coverageNote: string
}

export interface SecuritiesInventoryData {
  items: InventoryItem[]
  auditConclusion: string
  meta?: InventoryMeta
}

export type InventoryFlatRow = Omit<InventoryItem, 'variance' | 'seq'> & { seq?: number }

export interface InventorySeed {
  id?: string
  securitiesName: string
  securitiesCode?: string
  faceValue?: number
  bookQuantity?: number
  indexRef?: string
}

export function emptyInventoryMeta(): InventoryMeta {
  return {
    inventoryDate: '',
    isBalanceSheetDate: null,
    participants: '',
    custodyInstitution: '',
    coverageNote: '',
  }
}

function matchKey(code: string, name: string): string {
  const codeKey = String(code || '').trim().replace(/\s+/g, '').toUpperCase()
  if (codeKey) return `code:${codeKey}`
  return `name:${normalizeG6InvestName(name)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiInventory() {
  const items = ref<InventoryItem[]>([])
  const auditConclusion = ref('')
  const meta = ref<InventoryMeta>(emptyInventoryMeta())

  function recalcVariance(item: InventoryItem): void {
    item.variance = parseNum(item.countQuantity) - parseNum(item.bookQuantity)
  }

  watch(items, (newItems) => {
    for (const item of newItems) recalcVariance(item)
  }, { deep: true })

  function hasVariance(item: InventoryItem): boolean {
    return parseNum(item.variance) !== 0
  }

  function getVarianceCellStyle(item: InventoryItem): Record<string, string> {
    if (hasVariance(item)) {
      return { backgroundColor: '#fef2f2', color: '#dc2626', fontWeight: '600' }
    }
    return {}
  }

  function isVarianceReasonMissing(item: InventoryItem): boolean {
    return hasVariance(item) && !(item.varianceReason || '').trim()
  }

  const varianceValidationErrors = computed(() => {
    const issues: Array<{ row: InventoryItem; index: number }> = []
    for (let i = 0; i < items.value.length; i++) {
      if (isVarianceReasonMissing(items.value[i])) {
        issues.push({ row: items.value[i], index: i })
      }
    }
    return issues
  })

  const isVarianceValid = computed(() => varianceValidationErrors.value.length === 0)

  /** 非报表日盘点 → 需编制 G6-10 */
  const needsRollForward = computed(() => meta.value.isBalanceSheetDate === false)

  function assertVarianceValidForSave(actionLabel = '保存'): boolean {
    if (isVarianceValid.value) return true
    const names = varianceValidationErrors.value
      .slice(0, 5)
      .map((e) => e.row.securitiesName)
      .join('、')
    ElMessage.warning(
      `${actionLabel}前请先填写差异原因（${varianceValidationErrors.value.length}项）：${names}`,
    )
    return false
  }

  function createEmptyItem(name: string, seq: number): InventoryItem {
    return {
      id: `inv-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq,
      securitiesName: name,
      securitiesCode: '',
      faceValue: 0,
      countQuantity: 0,
      bookQuantity: 0,
      variance: 0,
      varianceReason: '',
      varianceConclusion: '',
      indexRef: '',
      ownershipEntity: '',
      restrictionType: '',
      restrictionNote: '',
      evidenceIndex: '',
    }
  }

  async function addItem(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增盘点行',
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
      ElMessage.success(`已新增"${value.trim()}"`)
    } catch {
      // cancel
    }
  }

  async function removeItem(id: string): Promise<void> {
    const item = items.value.find(r => r.id === id)
    if (!item) return
    try {
      await ElMessageBox.confirm(
        `确认删除"${item.securitiesName}"？`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      items.value = items.value.filter(r => r.id !== id)
      items.value.forEach((r, i) => { r.seq = i + 1 })
      ElMessage.success(`已删除"${item.securitiesName}"`)
    } catch {
      // cancel
    }
  }

  function updateItem(id: string, field: keyof InventoryItem, value: any): void {
    const item = items.value.find(r => r.id === id)
    if (!item) return
    ;(item as any)[field] = value
    if (field === 'countQuantity' || field === 'bookQuantity') {
      recalcVariance(item)
    }
  }

  function updateMeta<K extends keyof InventoryMeta>(field: K, value: InventoryMeta[K]): void {
    meta.value = { ...meta.value, [field]: value }
  }

  function _normalizeItem(r: Partial<InventoryItem> | InventoryFlatRow, i: number): InventoryItem {
    const item: InventoryItem = {
      id: r.id || `inv-${Date.now()}-${i}`,
      seq: i + 1,
      securitiesName: r.securitiesName || '',
      securitiesCode: r.securitiesCode || '',
      faceValue: parseNum(r.faceValue),
      countQuantity: parseNum(r.countQuantity),
      bookQuantity: parseNum(r.bookQuantity),
      variance: 0,
      varianceReason: (r as InventoryItem).varianceReason || '',
      varianceConclusion: (r as InventoryItem).varianceConclusion || '',
      indexRef: (r as InventoryItem).indexRef || '',
      ownershipEntity: (r as InventoryItem).ownershipEntity || '',
      restrictionType: ((r as InventoryItem).restrictionType || '') as InventoryRestrictionType,
      restrictionNote: (r as InventoryItem).restrictionNote || '',
      evidenceIndex: (r as InventoryItem).evidenceIndex || '',
    }
    recalcVariance(item)
    return item
  }

  function loadData(data: SecuritiesInventoryData | InventoryItem[] | InventoryFlatRow[] | null): void {
    if (!data) {
      items.value = []
      auditConclusion.value = ''
      meta.value = emptyInventoryMeta()
      return
    }
    if (Array.isArray(data)) {
      items.value = data.map((r, i) => _normalizeItem(r, i))
      return
    }
    items.value = (data.items || []).map((r, i) => _normalizeItem(r, i))
    auditConclusion.value = data.auditConclusion || ''
    meta.value = {
      ...emptyInventoryMeta(),
      ...(data.meta || {}),
      isBalanceSheetDate:
        data.meta?.isBalanceSheetDate === true
          ? true
          : data.meta?.isBalanceSheetDate === false
            ? false
            : null,
    }
  }

  /**
   * 从 G6-2 种子合并：代码优先匹配，其次名称。
   * - 已存在：更新面值/账面数量（账面为空或 0 时写入）、补全代码
   * - 不存在：新增行（盘点数量默认=账面数量，便于报表日盘点起步）
   */
  function mergeSeedsFromDetail(seeds: InventorySeed[]): { added: number; updated: number } {
    let added = 0
    let updated = 0
    const byKey = new Map<string, InventoryItem>()
    for (const row of items.value) {
      byKey.set(matchKey(row.securitiesCode, row.securitiesName), row)
      // 也登记纯名称键，便于仅有名称的种子命中已有带代码行
      const nameOnly = `name:${normalizeG6InvestName(row.securitiesName)}`
      if (!byKey.has(nameOnly)) byKey.set(nameOnly, row)
    }

    for (const seed of seeds || []) {
      const name = (seed.securitiesName || '').trim()
      if (!name) continue
      const code = (seed.securitiesCode || '').trim()
      const primaryKey = matchKey(code, name)
      const existing = byKey.get(primaryKey) || byKey.get(`name:${normalizeG6InvestName(name)}`)

      if (existing) {
        if (code && !existing.securitiesCode) existing.securitiesCode = code
        if (seed.faceValue && !existing.faceValue) existing.faceValue = parseNum(seed.faceValue)
        const bookQty = parseNum(seed.bookQuantity)
        if (bookQty && !existing.bookQuantity) {
          existing.bookQuantity = bookQty
          if (!existing.countQuantity) existing.countQuantity = bookQty
        }
        if (seed.indexRef && !existing.indexRef) existing.indexRef = seed.indexRef
        recalcVariance(existing)
        updated += 1
      } else {
        const bookQty = parseNum(seed.bookQuantity)
        const row = createEmptyItem(name, items.value.length + 1)
        if (seed.id) row.id = String(seed.id)
        row.securitiesCode = code
        row.faceValue = parseNum(seed.faceValue)
        row.bookQuantity = bookQty
        row.countQuantity = bookQty
        row.indexRef = seed.indexRef || 'G6-2'
        recalcVariance(row)
        items.value.push(row)
        byKey.set(primaryKey, row)
        byKey.set(`name:${normalizeG6InvestName(name)}`, row)
        added += 1
      }
    }
    items.value.forEach((r, i) => { r.seq = i + 1 })
    return { added, updated }
  }

  function toJSON(): SecuritiesInventoryData {
    return {
      items: items.value.map(r => ({ ...r })),
      auditConclusion: auditConclusion.value,
      meta: { ...meta.value },
    }
  }

  function flattenRows(): InventoryFlatRow[] {
    return items.value.map(({ variance: _v, ...rest }) => ({ ...rest }))
  }

  const varianceCount = computed(() => items.value.filter(hasVariance).length)
  const totalCount = computed(() => items.value.length)
  const restrictedCount = computed(
    () => items.value.filter((r) => r.restrictionType && r.restrictionType !== 'none').length,
  )

  return {
    items,
    auditConclusion,
    meta,
    varianceCount,
    totalCount,
    restrictedCount,
    varianceValidationErrors,
    isVarianceValid,
    needsRollForward,
    recalcVariance,
    hasVariance,
    getVarianceCellStyle,
    isVarianceReasonMissing,
    assertVarianceValidForSave,
    addItem,
    removeItem,
    updateItem,
    updateMeta,
    mergeSeedsFromDetail,
    loadData,
    toJSON,
    flattenRows,
  }
}

export default useG6SppiInventory
