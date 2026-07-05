/**
 * useG4SppiInventory — G4-7 有价证券盘点表
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 7.1
 * Requirements: 4.1~4.8, 6.3, 6.8
 *
 * 职责：
 * - 管理 InventoryHeader 响应式数据（6字段：盘点单位/日期/会计主管/出纳/监盘人/盘点人）
 * - 管理 InventoryItem[]（seq/securitiesName/faceValue/quantity/total/couponRate/maturityDate）
 * - computed: 每行 total = calcInventoryTotal(faceValue, quantity)
 * - computed: 合计行（面值合计/数量合计/总计合计 via calcSumColumn）
 * - 动态行增删（ElMessageBox.prompt 输入证券名称）
 * - 持久化到 checklist_responses via debouncedSave
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcInventoryTotal, calcSumColumn, parseNum } from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface InventoryHeader {
  company: string
  countDate: string
  accountingSupervisor: string
  cashier: string
  observer: string
  counter: string
}

export interface InventoryItem {
  id: string
  seq: number
  securitiesName: string
  faceValue: number
  quantity: number
  total: number              // 公式: 面值 × 数量 (2dp)
  couponRate: number
  maturityDate: string
}

export interface InventorySummary {
  faceValueTotal: number
  quantityTotal: number
  totalTotal: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_HEADER = 'G4-7-header'
const STORAGE_KEY_ITEMS = 'G4-7-items'
const STORAGE_KEY_AUDIT_DESC = 'G4-7-audit-description'
const STORAGE_KEY_AUDIT_CONCLUSION = 'G4-7-audit-conclusion'

const MAX_ROWS = 200

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `g4inv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createDefaultHeader(): InventoryHeader {
  return {
    company: '',
    countDate: '',
    accountingSupervisor: '',
    cashier: '',
    observer: '',
    counter: '',
  }
}

function createEmptyItem(name: string, seq: number): InventoryItem {
  return {
    id: generateId(),
    seq,
    securitiesName: name,
    faceValue: 0,
    quantity: 0,
    total: 0,
    couponRate: 0,
    maturityDate: '',
  }
}

/** 公式链求解：每行 total = 面值 × 数量 */
function enrichItem(item: InventoryItem): InventoryItem {
  return {
    ...item,
    total: calcInventoryTotal(item.faceValue, item.quantity),
  }
}

function safeParseJson<T>(jsonStr: string | null | undefined): T | null {
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as T
  } catch {
    return null
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseG4SppiInventoryOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

export function useG4SppiInventory(opts: UseG4SppiInventoryOptions) {
  const { allResponses, debouncedSave, isReadonly } = opts

  // ─── 盘点信息头 ──────────────────────────────────────────────────────────
  const header = ref<InventoryHeader>(createDefaultHeader())

  // ─── 盘点明细 ────────────────────────────────────────────────────────────
  const items = ref<InventoryItem[]>([enrichItem(createEmptyItem('', 1))])

  // ─── 审计说明/结论 ───────────────────────────────────────────────────────
  const auditDescription = ref('')
  const auditConclusion = ref('')

  // ─── 合计行（computed） ──────────────────────────────────────────────────
  const summary = computed<InventorySummary>(() => ({
    faceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.faceValue))),
    quantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.quantity))),
    totalTotal: calcSumColumn(items.value.map((i) => i.total)),
  }))

  // ─── 从 allResponses 加载 ────────────────────────────────────────────────

  function loadFromResponses(): void {
    const headerResp = allResponses.value.get(STORAGE_KEY_HEADER)
    const headerParsed = safeParseJson<InventoryHeader>(headerResp?.remark)
    if (headerParsed) {
      header.value = headerParsed
    }

    const itemsResp = allResponses.value.get(STORAGE_KEY_ITEMS)
    const itemsParsed = safeParseJson<InventoryItem[]>(itemsResp?.remark)
    if (itemsParsed && Array.isArray(itemsParsed) && itemsParsed.length > 0) {
      items.value = itemsParsed.map(enrichItem)
    }

    const descResp = allResponses.value.get(STORAGE_KEY_AUDIT_DESC)
    auditDescription.value = descResp?.remark || ''

    const concResp = allResponses.value.get(STORAGE_KEY_AUDIT_CONCLUSION)
    auditConclusion.value = concResp?.remark || ''
  }

  // allResponses 异步加载完成后回填
  watch(
    () => allResponses.value.get(STORAGE_KEY_ITEMS)?.remark,
    () => loadFromResponses(),
    { immediate: true },
  )

  // ─── 持久化 ──────────────────────────────────────────────────────────────

  function persistHeader(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_HEADER, { remark: JSON.stringify(header.value) })
  }

  function persistItems(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_ITEMS, { remark: JSON.stringify(items.value) })
  }

  function persistAuditDescription(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_DESC, { remark: auditDescription.value })
  }

  function persistAuditConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_CONCLUSION, { remark: auditConclusion.value })
  }

  // ─── 操作 ────────────────────────────────────────────────────────────────

  function updateHeader(patch: Partial<InventoryHeader>): void {
    if (isReadonly.value) return
    header.value = { ...header.value, ...patch }
    persistHeader()
  }

  function updateItem(id: string, patch: Partial<InventoryItem>): void {
    if (isReadonly.value) return
    items.value = items.value.map((item) => {
      if (item.id !== id) return item
      const updated = { ...item, ...patch }
      return enrichItem(updated)
    })
    persistItems()
  }

  async function addItem(): Promise<void> {
    if (isReadonly.value) return
    if (items.value.length >= MAX_ROWS) {
      ElMessageBox.alert(`行数已达上限（${MAX_ROWS}行），无法继续新增。`, '提示')
      return
    }
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增盘点明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '证券名称不能为空',
        },
      )
      const seq = items.value.length + 1
      items.value = [...items.value, enrichItem(createEmptyItem(name, seq))]
      persistItems()
    } catch {
      /* cancelled */
    }
  }

  function removeItem(id: string): void {
    if (isReadonly.value || items.value.length <= 1) return
    items.value = items.value
      .filter((item) => item.id !== id)
      .map((item, idx) => ({ ...item, seq: idx + 1 }))
    persistItems()
  }

  function setAuditDescription(value: string): void {
    if (isReadonly.value) return
    auditDescription.value = value
    persistAuditDescription()
  }

  function setAuditConclusion(value: string): void {
    if (isReadonly.value) return
    auditConclusion.value = value
    persistAuditConclusion()
  }

  return {
    // 数据
    header,
    items,
    summary,
    auditDescription,
    auditConclusion,
    // 操作
    updateHeader,
    updateItem,
    addItem,
    removeItem,
    setAuditDescription,
    setAuditConclusion,
    // 加载
    loadFromResponses,
    // 持久化
    persistHeader,
    persistItems,
  }
}

export default useG4SppiInventory
