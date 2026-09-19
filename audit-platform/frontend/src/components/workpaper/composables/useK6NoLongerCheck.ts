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
import { calcSubtotal } from './useK6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查状态 */
export type CheckStatus = 'compliant' | 'non_compliant' | 'na' | ''

/** 分类：非流动资产 / 处置组资产 / 处置组负债（对齐源模板行结构） */
export type NoLongerCategory = 'asset_noncurrent' | 'asset_group' | 'liability_group'

export interface K6NoLongerCheckItem {
  rowId: string
  seqNo: number
  category: NoLongerCategory    // 分类
  groupName: string             // 处置组/主体（子公司A等）
  assetName: string             // 项目/资产名称
  // ─── 源模板 ①②③④ 净额分解（CAS42 第22条(a)）───
  preClassBookValue: number     // ① 被划归为持有待售之前的账面价值
  assumedDepreciation: number   // ② 假设未划归原应确认的折旧、摊销
  assumedImpairment: number     // ③ 假设未划归原应确认的减值准备
  netValue: number              // ④ 净额 = ① - ② - ③（公式）
  recoverableAmount: number     // 决定不再出售之日的可收回金额（CAS42 第22条(b)）
  recoverableMethod: string     // 可收回金额确定方法（CAS8：公允净额/使用价值/评估报告）
  adjustedBookValue: number     // 调整后账面价值（公式：min(④净额, 可收回金额)，孰低）
  currentBookValue: number      // 当前持有待售账面（从K6-2或手工录入）
  adjustmentDiff: number        // 调整差额（公式：调整后账面 - 现账面，计入当期损益）
  noLongerReason: string        // 不再满足原因
  reclassificationDate: string  // 重分类日期
  decisionRef: string           // 不再处置决议（索引）
  agreementRef: string          // 不再处置协议（索引）
  status: CheckStatus           // 合规/不合规/不适用
  voucherRef: string            // 凭证/抽凭
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
    // ① 兼容历史字段 assumedBookValue（旧模型的单一"假设未分类账面"→映射为①被划归前账面）
    const preClassBookValue = Number(raw.preClassBookValue ?? raw.assumedBookValue) || 0
    const assumedDepreciation = Number(raw.assumedDepreciation) || 0
    const assumedImpairment = Number(raw.assumedImpairment) || 0
    const netValue = preClassBookValue - assumedDepreciation - assumedImpairment
    const recoverableAmount = Number(raw.recoverableAmount) || 0
    // 调整后账面 = min(④净额, 可收回金额)（孰低，Req 7.2）
    const adjustedBookValue = _calcAdjusted(netValue, recoverableAmount)
    const currentBookValue = Number(raw.currentBookValue) || 0
    const adjustmentDiff = adjustedBookValue - currentBookValue
    const category: NoLongerCategory =
      raw.category === 'asset_group' || raw.category === 'liability_group'
        ? raw.category
        : 'asset_noncurrent'

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      category,
      groupName: raw.groupName ?? '',
      assetName: raw.assetName ?? '',
      preClassBookValue,
      assumedDepreciation,
      assumedImpairment,
      netValue,
      recoverableAmount,
      recoverableMethod: raw.recoverableMethod ?? '',
      adjustedBookValue,
      currentBookValue,
      adjustmentDiff,
      noLongerReason: raw.noLongerReason ?? '',
      reclassificationDate: raw.reclassificationDate ?? '',
      decisionRef: raw.decisionRef ?? '',
      agreementRef: raw.agreementRef ?? '',
      status: (raw.status || '') as CheckStatus,
      voucherRef: raw.voucherRef ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc（④=①-②-③；调整后账面=min(④,可收回金额)） ──────────────────

  /** 调整后账面 = min(净额, 可收回金额)；两者均为0时返回0 */
  function _calcAdjusted(netValue: number, recoverableAmount: number): number {
    if (netValue === 0 && recoverableAmount === 0) return 0
    if (recoverableAmount === 0) return netValue
    if (netValue === 0) return recoverableAmount
    return Math.min(netValue, recoverableAmount)
  }

  function _recalcItem(item: K6NoLongerCheckItem): void {
    item.netValue = item.preClassBookValue - item.assumedDepreciation - item.assumedImpairment
    item.adjustedBookValue = _calcAdjusted(item.netValue, item.recoverableAmount)
    item.adjustmentDiff = item.adjustedBookValue - item.currentBookValue
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

  // ─── 分区小计（资产合计 / 负债合计） ──────────────────────────────────────

  const subtotals: ComputedRef<{
    assetPreClass: number; assetNet: number; assetAdjusted: number; assetCount: number
    liabilityPreClass: number; liabilityNet: number; liabilityAdjusted: number; liabilityCount: number
  }> = computed(() => {
    const items = checkItems.value
    const assets = items.filter(i => i.category === 'asset_noncurrent' || i.category === 'asset_group')
    const liabs = items.filter(i => i.category === 'liability_group')
    return {
      assetPreClass: calcSubtotal(assets.map(i => i.preClassBookValue)),
      assetNet: calcSubtotal(assets.map(i => i.netValue)),
      assetAdjusted: calcSubtotal(assets.map(i => i.adjustedBookValue)),
      assetCount: assets.length,
      liabilityPreClass: calcSubtotal(liabs.map(i => i.preClassBookValue)),
      liabilityNet: calcSubtotal(liabs.map(i => i.netValue)),
      liabilityAdjusted: calcSubtotal(liabs.map(i => i.adjustedBookValue)),
      liabilityCount: liabs.length,
    }
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

  async function addItem(category: NoLongerCategory = 'asset_noncurrent'): Promise<void> {
    let name = ''
    try {
      const { ElMessageBox } = await import('element-plus')
      const catLabel =
        category === 'asset_noncurrent' ? '不再满足的非流动资产'
        : category === 'asset_group' ? '处置组资产'
        : '处置组负债'
      const { value } = await ElMessageBox.prompt(
        `请输入项目名称（${catLabel}）`,
        '新增检查项',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: category === 'liability_group' ? '例如：应付账款' : '例如：固定资产 / 长期股权投资-联营企业',
          inputValidator: (val: string) => (!val?.trim() ? '名称不能为空' : true),
        },
      )
      name = value?.trim() ?? ''
    } catch {
      return
    }
    if (!name) return

    checkItems.value.push(_normalizeItem({ category, assetName: name }, checkItems.value.length))
    checkItems.value.forEach((r, i) => { r.seqNo = i + 1 })
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
    subtotals,
    auditConclusion,
    updateCell,
    recalcAll,
    addItem,
    removeItem,
    importItems,
    saveConclusion,
  }
}
