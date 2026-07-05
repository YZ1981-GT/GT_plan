/**
 * useG6SppiInventory — G6-9 有价证券盘点表（29行×7列）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 10.1
 * Requirements: 6.1, 6.4
 *
 * 职责：
 * - SecuritiesInventoryData / InventoryItem 数据模型管理
 * - 差异公式计算（盘点数量 - 账面数量）
 * - 动态行管理（新增ElMessageBox.prompt / 删除确认）
 * - 行字段更新 + 自动重算差异
 *
 * 列结构（7列）：序号 | 证券名称 | 证券代码 | 面值 | 数量(盘点) | 数量(账面) | 差异
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { parseNum } from '@/composables/useG6SppiFormulaEngine'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

export interface InventoryItem {
  id: string
  seq: number
  securitiesName: string
  securitiesCode: string
  faceValue: number
  countQuantity: number    // 盘点数量
  bookQuantity: number     // 账面数量
  variance: number         // 公式: 盘点 - 账面
}

export interface SecuritiesInventoryData {
  items: InventoryItem[]
  auditConclusion: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiInventory() {
  const items = ref<InventoryItem[]>([])
  const auditConclusion = ref('')

  // ─── 公式计算 ──────────────────────────────────────────────────────────────

  /** 重算指定行的差异：盘点数量 - 账面数量 */
  function recalcVariance(item: InventoryItem): void {
    item.variance = parseNum(item.countQuantity) - parseNum(item.bookQuantity)
  }

  // watch items 变化时自动重算差异
  watch(items, (newItems) => {
    for (const item of newItems) {
      recalcVariance(item)
    }
  }, { deep: true })

  // ─── 差异高亮逻辑 ─────────────────────────────────────────────────────────

  /** 判断行是否有差异需高亮 */
  function hasVariance(item: InventoryItem): boolean {
    return parseNum(item.variance) !== 0
  }

  /** 获取差异列样式（差异≠0红色高亮） */
  function getVarianceCellStyle(item: InventoryItem): Record<string, string> {
    if (hasVariance(item)) {
      return { backgroundColor: '#fef2f2', color: '#dc2626', fontWeight: '600' }
    }
    return {}
  }

  // ─── 行 CRUD ──────────────────────────────────────────────────────────────

  /** 新增行（ElMessageBox.prompt输入证券名称） */
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

      const newItem: InventoryItem = {
        id: `inv-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        seq: items.value.length + 1,
        securitiesName: value.trim(),
        securitiesCode: '',
        faceValue: 0,
        countQuantity: 0,
        bookQuantity: 0,
        variance: 0,
      }
      items.value.push(newItem)
      ElMessage.success(`已新增"${value.trim()}"`)
    } catch {
      // 用户取消
    }
  }

  /** 删除行（确认弹窗） */
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
      // 重排序号
      items.value.forEach((r, i) => { r.seq = i + 1 })
      ElMessage.success(`已删除"${item.securitiesName}"`)
    } catch {
      // 用户取消
    }
  }

  /** 更新指定行字段 */
  function updateItem(id: string, field: keyof InventoryItem, value: any): void {
    const item = items.value.find(r => r.id === id)
    if (!item) return
    ;(item as any)[field] = value
    recalcVariance(item)
  }

  // ─── 数据加载/导出 ─────────────────────────────────────────────────────────

  /** 加载外部数据 */
  function loadData(data: SecuritiesInventoryData | null): void {
    if (!data?.items?.length) {
      items.value = []
      auditConclusion.value = data?.auditConclusion || ''
      return
    }
    items.value = data.items.map((r, i) => {
      const item: InventoryItem = {
        id: r.id || `inv-${Date.now()}-${i}`,
        seq: i + 1,
        securitiesName: r.securitiesName || '',
        securitiesCode: r.securitiesCode || '',
        faceValue: parseNum(r.faceValue),
        countQuantity: parseNum(r.countQuantity),
        bookQuantity: parseNum(r.bookQuantity),
        variance: 0,
      }
      recalcVariance(item)
      return item
    })
    auditConclusion.value = data.auditConclusion || ''
  }

  /** 导出为JSON */
  function toJSON(): SecuritiesInventoryData {
    return {
      items: items.value.map(r => ({ ...r })),
      auditConclusion: auditConclusion.value,
    }
  }

  // ─── 汇总统计 ──────────────────────────────────────────────────────────────

  /** 有差异的行数 */
  const varianceCount = computed(() => items.value.filter(hasVariance).length)

  /** 总行数 */
  const totalCount = computed(() => items.value.length)

  return {
    // State
    items,
    auditConclusion,
    // Computed
    varianceCount,
    totalCount,
    // Methods
    recalcVariance,
    hasVariance,
    getVarianceCellStyle,
    addItem,
    removeItem,
    updateItem,
    loadData,
    toJSON,
  }
}

export default useG6SppiInventory
