/**
 * useK6NoLongerCheck — K6-7 不再满足持有待售检查
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.4
 * Requirements: 7.1-7.4
 *
 * 职责：
 * - 管理检查项：项目/不再满足原因/重分类日/账面价值调整/结论
 * - 不再满足时按较低者计量：min(假设未分类账面, 可收回金额)
 * - 逐项"合规/不合规/不适用"+行级抽凭
 * - 存在"不合规"项时红色摘要提示
 *
 * CAS42：不再满足持有待售条件时，按以下两者孰低计量：
 *   a) 资产在划分为持有待售类别前的账面价值（假设未分类，正常折旧/摊销后的账面）
 *   b) 可收回金额
 *
 * Prefix: "K6-7-"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查状态 */
export type CheckStatus = 'compliant' | 'non_compliant' | 'na' | ''

export interface K6NoLongerCheckItem {
  rowId: string
  seqNo: number
  assetName: string            // 项目/资产名称
  noLongerReason: string       // 不再满足原因
  reclassificationDate: string // 重分类日期
  assumedBookValue: number     // 假设未分类时的账面价值
  recoverableAmount: number    // 可收回金额
  adjustedBookValue: number    // 调整后账面价值（公式：两者取低）
  adjustment: number           // 账面价值调整金额
  status: CheckStatus          // 合规/不合规/不适用
  voucherRef: string           // 凭证/抽凭
  conclusion: string
  remark: string
}

export interface UseK6NoLongerCheckParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K6-7-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK6NoLongerCheck(params: UseK6NoLongerCheckParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const checkItems = ref<K6NoLongerCheckItem[]>([])
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadItems(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { checkItems.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        checkItems.value = parsed.map(_normalizeItem)
      } else {
        checkItems.value = []
      }
    } catch {
      checkItems.value = []
    }
  }

  function _normalizeItem(raw: any, idx?: number): K6NoLongerCheckItem {
    const assumedBookValue = Number(raw.assumedBookValue) || 0
    const recoverableAmount = Number(raw.recoverableAmount) || 0
    // 两者取低（Req 7.2）
    const adjustedBookValue = Math.min(assumedBookValue, recoverableAmount)
    const currentBook = Number(raw.currentBookValue) || 0
    const adjustment = adjustedBookValue - currentBook

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      noLongerReason: raw.noLongerReason ?? '',
      reclassificationDate: raw.reclassificationDate ?? '',
      assumedBookValue,
      recoverableAmount,
      adjustedBookValue,
      adjustment: Number(raw.adjustment) || adjustment,
      status: (raw.status || '') as CheckStatus,
      voucherRef: raw.voucherRef ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc（Req 7.2：两者取低） ──────────────────────────────────────────

  function _recalcItem(item: K6NoLongerCheckItem): void {
    // 调整后账面 = min(假设未分类账面, 可收回金额)
    if (item.assumedBookValue > 0 || item.recoverableAmount > 0) {
      item.adjustedBookValue = Math.min(item.assumedBookValue, item.recoverableAmount)
    } else {
      item.adjustedBookValue = 0
    }
  }

  function recalcAll(): void {
    for (const item of checkItems.value) _recalcItem(item)
  }

  // ─── 不合规项统计（Req 7.4：红色摘要提示） ────────────────────────────────

  const nonCompliantItems: ComputedRef<K6NoLongerCheckItem[]> = computed(() => {
    return checkItems.value.filter(i => i.status === 'non_compliant')
  })

  const hasNonCompliant: ComputedRef<boolean> = computed(() => {
    return nonCompliantItems.value.length > 0
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const item = checkItems.value.find(r => r.rowId === rowId)
    if (!item) return
    ;(item as any)[field] = value
    _recalcItem(item)
    _persist()
  }

  // ─── Dynamic Row Add ───────────────────────────────────────────────────────

  async function addItem(assetName?: string): Promise<void> {
    let name = assetName
    if (!name) {
      try {
        const { ElMessageBox } = await import('element-plus')
        const { value } = await ElMessageBox.prompt(
          '请输入资产名称',
          '新增检查项',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX资产不再满足',
            inputValidator: (val) => (!val?.trim() ? '名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return
      }
    }
    if (!name) return

    const newItem: K6NoLongerCheckItem = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: checkItems.value.length + 1,
      assetName: name,
      noLongerReason: '',
      reclassificationDate: '',
      assumedBookValue: 0,
      recoverableAmount: 0,
      adjustedBookValue: 0,
      adjustment: 0,
      status: '',
      voucherRef: '',
      conclusion: '',
      remark: '',
    }
    checkItems.value.push(newItem)
    _persist()
  }

  // ─── Remove Item ───────────────────────────────────────────────────────────

  function removeItem(idx: number): void {
    if (idx < 0 || idx >= checkItems.value.length) return
    checkItems.value.splice(idx, 1)
    checkItems.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importItems(data: any[]): void {
    checkItems.value = data.map((raw, i) => {
      const item = _normalizeItem(raw, i)
      _recalcItem(item)
      return item
    })
    _persist()
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(checkItems.value) })
  }

  // ─── Save Conclusion ───────────────────────────────────────────────────────

  async function saveConclusion(): Promise<void> {
    await saveResponse('K6-7-audit-conclusion', { remark: auditConclusion.value })
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => {
    _loadItems()
    const val = allResponses.value.get('K6-7-audit-conclusion')
    auditConclusion.value = val?.remark ?? val?.conclusion ?? ''
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    checkItems,
    nonCompliantItems,
    hasNonCompliant,
    auditConclusion,
    updateCell,
    recalcAll,
    addItem,
    removeItem,
    importItems,
    saveConclusion,
  }
}
