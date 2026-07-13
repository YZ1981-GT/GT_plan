/**
 * useK6InitialRecognition — K6-4 初始确认（CAS42五条件清单）
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.4
 * Requirements: 4.1-4.5
 *
 * 职责：
 * - CAS42五条件核对清单（每条件：满足/不满足/不适用）
 * - 分类判断结果：全满足→'classified'；否则→'not_classified'
 * - AI辅助生成分类判断结论
 * - 五条件明细说明+证据
 *
 * CAS42 五条件：
 *   ① 可立即出售（在当前状况下仅根据惯例条款即可立即出售）
 *   ② 已就出售作出决议
 *   ③ 已与购买方签订不可撤销转让协议
 *   ④ 出售预计一年内完成
 *   ⑤ 售价合理，不太可能变更/撤销
 *
 * Prefix: "K6-4-"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { classifyHeldForSale, type ClassificationResult } from './useK6ClassificationEngine'
import { calcFairValuePriority, calcFairValueNet } from './useK6ImpairmentEngine'
import { calcSubtotal } from './useK6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 条件状态：'met'满足 / 'not_met'不满足 / 'na'不适用 / ''未评估 */
export type ConditionStatus = 'met' | 'not_met' | 'na' | ''

export interface K6Condition {
  index: number
  label: string
  description: string
  status: ConditionStatus
  evidence: string       // 审计证据/说明
}

/** 估值表分类：非流动资产 / 处置组资产 / 处置组负债 */
export type ValuationCategory = 'asset_noncurrent' | 'asset_group' | 'liability_group'

/**
 * K6-4 初始确认估值表行（对照源模板 19 列）
 * 公允价值三方法确定 + 孰低净额 + CAS42 判断列（预计出售时间/即可立即出售/决议索引/协议索引）
 */
export interface K6ValuationRow {
  rowId: string
  seqNo: number
  category: ValuationCategory
  groupName: string           // 处置组/主体（如子公司A、分公司B；非流动资产可留空）
  itemName: string            // 项目（如固定资产、长期股权投资-联营企业）
  bookValue: number           // 账面价值（可从 K6-2 明细表联动）
  salesPrice: number          // 销售协议价格
  salesBasis: string          // 依据
  marketPrice: number         // 资产活跃市场价格
  marketBasis: string         // 依据
  estimatePrice: number       // 估计价格
  estimateBasis: string       // 依据
  fairValue: number           // 公允价值（公式：优先级取值）
  sellingCost: number         // 出售费用（资产处置的直接归属费用）
  fairValueNet: number        // 公允价值减去出售费用后的净额（公式）
  expectedSaleTime: string    // 预计出售时间（预计一年内完成）
  immediatelySellable: string // 当前状况即可立即出售（是/否/待定）
  decisionRef: string         // 就出售计划作出决议（索引）
  agreementRef: string        // 与受让方签订的不可撤销购买协议（索引）
}

/** 估值表分区小计 */
export interface K6ValuationSubtotals {
  assetBook: number           // 资产账面合计（非流动资产 + 处置组资产）
  assetFairNet: number        // 资产公允净额合计
  liabilityBook: number       // 负债账面合计
  liabilityFairNet: number    // 负债公允净额合计
  assetCount: number
  liabilityCount: number
}

export interface UseK6InitialRecognitionParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const CAS42_CONDITIONS: Array<{ label: string; description: string }> = [
  { label: '条件①：可立即出售', description: '在当前状况下仅根据出售此类资产或处置组的惯例条款即可立即出售' },
  { label: '条件②：已作出决议', description: '企业已就出售计划作出决议（如董事会决议）' },
  { label: '条件③：已签订不可撤销转让协议', description: '已与受让方签订了不可撤销的转让协议' },
  { label: '条件④：出售预计一年内完成', description: '该项转让将在一年内完成' },
  { label: '条件⑤：售价合理不太可能变更', description: '转让价格合理，且不太可能发生重大变化或被撤回' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(map: Map<string, any>, itemId: string): string {
  const item = map.get(itemId)
  if (!item) return ''
  return item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK6InitialRecognition(params: UseK6InitialRecognitionParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const conditions = ref<K6Condition[]>(
    CAS42_CONDITIONS.map((c, i) => ({
      index: i,
      label: c.label,
      description: c.description,
      status: '' as ConditionStatus,
      evidence: '',
    }))
  )

  const classificationConclusion = ref('')

  // 估值表行
  const valuationRows = ref<K6ValuationRow[]>([])
  const auditNote = ref('')

  // ─── 从 allResponses 加载条件状态 ─────────────────────────────────────────

  function _loadConditions(): void {
    for (let i = 0; i < 5; i++) {
      const status = getVal(allResponses.value, `K6-4-cond-${i}-status`) as ConditionStatus
      const evidence = getVal(allResponses.value, `K6-4-cond-${i}-evidence`)
      conditions.value[i].status = status || ''
      conditions.value[i].evidence = evidence
    }
    classificationConclusion.value = getVal(allResponses.value, 'K6-4-conclusion')
    auditNote.value = getVal(allResponses.value, 'K6-4-audit-note')
  }

  // ─── 估值表：加载 / 归一化 / 重算 ──────────────────────────────────────────

  function _normalizeValuationRow(raw: any, idx: number): K6ValuationRow {
    const bookValue = Number(raw.bookValue) || 0
    const salesPrice = Number(raw.salesPrice) || 0
    const marketPrice = Number(raw.marketPrice) || 0
    const estimatePrice = Number(raw.estimatePrice) || 0
    const sellingCost = Number(raw.sellingCost) || 0
    const fairValue = calcFairValuePriority(salesPrice, marketPrice, estimatePrice)
    const fairValueNet = calcFairValueNet(fairValue, sellingCost)
    const category: ValuationCategory =
      raw.category === 'asset_group' || raw.category === 'liability_group'
        ? raw.category
        : 'asset_noncurrent'
    return {
      rowId: raw.rowId ?? `val-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: idx + 1,
      category,
      groupName: raw.groupName ?? '',
      itemName: raw.itemName ?? '',
      bookValue,
      salesPrice,
      salesBasis: raw.salesBasis ?? '',
      marketPrice,
      marketBasis: raw.marketBasis ?? '',
      estimatePrice,
      estimateBasis: raw.estimateBasis ?? '',
      fairValue,
      sellingCost,
      fairValueNet,
      expectedSaleTime: raw.expectedSaleTime ?? '',
      immediatelySellable: raw.immediatelySellable ?? '',
      decisionRef: raw.decisionRef ?? '',
      agreementRef: raw.agreementRef ?? '',
    }
  }

  function _loadValuation(): void {
    const item = allResponses.value.get('K6-4-valuation-rows')
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { valuationRows.value = []; return }
    try {
      let parsed = JSON.parse(raw)
      // 兼容历史双重包裹 {"remark":"[...]"}：再解一层
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && typeof parsed.remark === 'string') {
        parsed = JSON.parse(parsed.remark)
      }
      valuationRows.value = Array.isArray(parsed)
        ? parsed.map((r, i) => _normalizeValuationRow(r, i))
        : []
    } catch {
      valuationRows.value = []
    }
  }

  function _recalcValuationRow(row: K6ValuationRow): void {
    row.fairValue = calcFairValuePriority(row.salesPrice, row.marketPrice, row.estimatePrice)
    row.fairValueNet = calcFairValueNet(row.fairValue, row.sellingCost)
  }

  // ─── 分类判断结果（Req 4.2） ──────────────────────────────────────────────

  const classificationResult: ComputedRef<ClassificationResult> = computed(() => {
    // 将条件状态转为布尔数组：'met'视为true，'na'视为true（不适用=不影响判断），其他为false
    const booleans = conditions.value.map(c => {
      if (c.status === 'met') return true
      if (c.status === 'na') return true
      return false
    })
    return classifyHeldForSale(booleans)
  })

  /** 是否所有条件都已评估（非空） */
  const isFullyEvaluated: ComputedRef<boolean> = computed(() => {
    return conditions.value.every(c => c.status !== '')
  })

  /** 不满足的条件列表（用于红色提示） */
  const unmetConditions: ComputedRef<K6Condition[]> = computed(() => {
    return conditions.value.filter(c => c.status === 'not_met')
  })

  // ─── 估值表分区小计（资产合计 / 负债合计） ────────────────────────────────

  const valuationSubtotals: ComputedRef<K6ValuationSubtotals> = computed(() => {
    const rows = valuationRows.value
    const assets = rows.filter(r => r.category === 'asset_noncurrent' || r.category === 'asset_group')
    const liabs = rows.filter(r => r.category === 'liability_group')
    return {
      assetBook: calcSubtotal(assets.map(r => r.bookValue)),
      assetFairNet: calcSubtotal(assets.map(r => r.fairValueNet)),
      liabilityBook: calcSubtotal(liabs.map(r => r.bookValue)),
      liabilityFairNet: calcSubtotal(liabs.map(r => r.fairValueNet)),
      assetCount: assets.length,
      liabilityCount: liabs.length,
    }
  })

  // ─── 估值表：更新 / 新增 / 删除 / 持久化 ──────────────────────────────────

  function _persistValuation(): void {
    saveResponse('K6-4-valuation-rows', { remark: JSON.stringify(valuationRows.value) })
    saveResponse('K6-4-asset-fairnet-total', { remark: String(valuationSubtotals.value.assetFairNet) })
  }

  function updateValuationCell(rowId: string, field: keyof K6ValuationRow, value: any): void {
    const row = valuationRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcValuationRow(row)
    _persistValuation()
  }

  async function addValuationRow(category: ValuationCategory): Promise<void> {
    let name = ''
    try {
      const { ElMessageBox } = await import('element-plus')
      const catLabel =
        category === 'asset_noncurrent' ? '持有待售非流动资产'
        : category === 'asset_group' ? '处置组资产'
        : '处置组负债'
      const { value } = await ElMessageBox.prompt(
        `请输入项目名称（${catLabel}）`,
        '新增估值行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: category === 'liability_group' ? '例如：应付票据及应付账款' : '例如：固定资产 / 长期股权投资-联营企业',
          inputValidator: (val: string) => (!val?.trim() ? '名称不能为空' : true),
        },
      )
      name = value?.trim() ?? ''
    } catch {
      return
    }
    if (!name) return
    valuationRows.value.push(_normalizeValuationRow({ category, itemName: name }, valuationRows.value.length))
    valuationRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persistValuation()
  }

  function removeValuationRow(rowId: string): void {
    const idx = valuationRows.value.findIndex(r => r.rowId === rowId)
    if (idx < 0) return
    valuationRows.value.splice(idx, 1)
    valuationRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persistValuation()
  }

  async function saveAuditNote(): Promise<void> {
    await saveResponse('K6-4-audit-note', { remark: auditNote.value })
  }

  // ─── 更新条件状态 ─────────────────────────────────────────────────────────

  function updateConditionStatus(index: number, status: ConditionStatus): void {
    if (index < 0 || index >= 5) return
    conditions.value[index].status = status
    saveResponse(`K6-4-cond-${index}-status`, { remark: status })
  }

  function updateConditionEvidence(index: number, evidence: string): void {
    if (index < 0 || index >= 5) return
    conditions.value[index].evidence = evidence
    saveResponse(`K6-4-cond-${index}-evidence`, { remark: evidence })
  }

  // ─── 保存结论 ─────────────────────────────────────────────────────────────

  async function saveConclusion(): Promise<void> {
    await saveResponse('K6-4-conclusion', { remark: classificationConclusion.value })
    await saveResponse('K6-4-result', { remark: classificationResult.value })
  }

  // ─── AI 辅助绑定点（由组件调用AI端点后设值） ──────────────────────────────

  function setAiConclusion(text: string): void {
    classificationConclusion.value = text
    saveResponse('K6-4-conclusion', { remark: text })
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => {
    _loadConditions()
    _loadValuation()
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // CAS42 五条件辅助判断区
    conditions,
    classificationResult,
    classificationConclusion,
    isFullyEvaluated,
    unmetConditions,
    updateConditionStatus,
    updateConditionEvidence,
    saveConclusion,
    setAiConclusion,
    // 初始确认估值表
    valuationRows,
    valuationSubtotals,
    updateValuationCell,
    addValuationRow,
    removeValuationRow,
    // 审计说明
    auditNote,
    saveAuditNote,
  }
}
