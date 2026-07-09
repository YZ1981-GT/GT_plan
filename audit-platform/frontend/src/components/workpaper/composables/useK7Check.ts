/**
 * useK7Check — K7-5 递延收益检查表 composable（30行×18列）
 *
 * Spec: .kiro/specs/k7-deferred-income/
 * Task: 3.4
 * Requirements: 5.1-5.3
 *
 * 职责：
 * - 逐项检查：补助真实性/批文合规/相关类型判断正确性/分摊方法适当性/计入科目正确性
 * - Per-item: { checkPoint, result: '合规'|'不合规'|'不适用', voucherRef, ocrRef, remark }
 * - 行级抽凭 + 行级OCR（批文）
 * - Summary: count of "不合规" items → red warning
 * - Save with prefix "K7-5-"
 *
 * 科目：2401 递延收益
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type K7ComplianceState = '合规' | '不合规' | '不适用'

export interface K7CheckItem {
  id: string
  seq: number
  checkPoint: string           // 检查项
  description: string          // 检查内容/标准
  result: K7ComplianceState | null
  voucherRef: string           // 抽凭凭证号（行级抽凭）
  ocrRef: string               // OCR附件路径（行级OCR：批文）
  remark: string
}

export interface K7NonComplianceSummary {
  count: number
  hasNonCompliant: boolean
  items: Array<{ id: string; checkPoint: string; detail: string }>
}

export interface UseK7CheckParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_CHECK_ITEMS = 'K7-5-check-items'

// ─── Default K7-5 检查项模板（Req 5.1） ──────────────────────────────────────

const DEFAULT_CHECK_ITEMS: Omit<K7CheckItem, 'result' | 'voucherRef' | 'ocrRef' | 'remark'>[] = [
  {
    id: 'K7-5-01',
    seq: 1,
    checkPoint: '补助真实性',
    description: '核实政府补助是否真实发生，是否有对应的拨款文件/银行到账记录/财政拨付凭证，金额与批文一致',
  },
  {
    id: 'K7-5-02',
    seq: 2,
    checkPoint: '批文合规',
    description: '核查补助批文是否为合法有效的政府文件，来源渠道合规，拨款条件是否已满足，是否存在附带条件',
  },
  {
    id: 'K7-5-03',
    seq: 3,
    checkPoint: '相关类型判断正确性',
    description: '检查企业将补助划分为"与资产相关"或"与收益相关"是否恰当，是否符合CAS16及补助文件约定用途',
  },
  {
    id: 'K7-5-04',
    seq: 4,
    checkPoint: '分摊方法适当性',
    description: '核实分摊方法（直线法/工作量法/一次性计入）是否合理，分摊期限是否匹配相关资产寿命或费用期间',
  },
  {
    id: 'K7-5-05',
    seq: 5,
    checkPoint: '计入科目正确性',
    description: '检查分摊金额计入科目是否正确：与日常活动相关→其他收益(6117)；与日常活动无关→营业外收入(6301)',
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK7Check(params: UseK7CheckParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const checkItems = ref<K7CheckItem[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const item = allResponses.value.get(ITEM_ID_CHECK_ITEMS)
    const raw = item?.remark ?? item?.conclusion ?? null
    if (!raw) {
      // 使用默认模板
      checkItems.value = DEFAULT_CHECK_ITEMS.map(_createDefaultItem)
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        checkItems.value = parsed.map(_normalizeCheckItem)
      } else {
        checkItems.value = DEFAULT_CHECK_ITEMS.map(_createDefaultItem)
      }
    } catch {
      checkItems.value = DEFAULT_CHECK_ITEMS.map(_createDefaultItem)
    }
  }

  function _createDefaultItem(
    t: Omit<K7CheckItem, 'result' | 'voucherRef' | 'ocrRef' | 'remark'>,
  ): K7CheckItem {
    return { ...t, result: null, voucherRef: '', ocrRef: '', remark: '' }
  }

  function _normalizeCheckItem(raw: any, idx?: number): K7CheckItem {
    return {
      id: raw.id ?? `K7-5-${String((idx ?? 0) + 1).padStart(2, '0')}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      checkPoint: raw.checkPoint ?? '',
      description: raw.description ?? '',
      result: raw.result ?? null,
      voucherRef: raw.voucherRef ?? '',
      ocrRef: raw.ocrRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── 不合规摘要 (Req 5.3: Red summary when any "不合规") ───────────────────

  const nonComplianceSummary: ComputedRef<K7NonComplianceSummary> = computed(() => {
    const items: K7NonComplianceSummary['items'] = []

    for (const item of checkItems.value) {
      if (item.result === '不合规') {
        items.push({
          id: item.id,
          checkPoint: item.checkPoint,
          detail: item.remark || '无补充说明',
        })
      }
    }

    return {
      count: items.length,
      hasNonCompliant: items.length > 0,
      items,
    }
  })

  // ─── 操作方法 ──────────────────────────────────────────────────────────────

  /** 更新检查项合规状态 */
  function updateResult(itemId: string, result: K7ComplianceState): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.result = result
      _persist()
    }
  }

  /** 更新检查项备注 */
  function updateRemark(itemId: string, remark: string): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.remark = remark
      _persist()
    }
  }

  /** 行级抽凭：设置凭证号引用 (Integration: voucher sampling engine) */
  function setVoucherRef(itemId: string, voucherRef: string): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.voucherRef = voucherRef
      _persist()
    }
  }

  /** 行级OCR：设置OCR附件路径（批文OCR） */
  function setOcrRef(itemId: string, ocrRef: string): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.ocrRef = ocrRef
      _persist()
    }
  }

  // ─── 统计方法 ──────────────────────────────────────────────────────────────

  /** 获取"不合规"项目数 */
  function getNonCompliantCount(): number {
    return nonComplianceSummary.value.count
  }

  /** 是否全部已完成判定 */
  function isAllChecked(): boolean {
    return checkItems.value.every(item => item.result !== null)
  }

  /** 获取完成进度（百分比） */
  function getProgress(): number {
    if (checkItems.value.length === 0) return 0
    const done = checkItems.value.filter(i => i.result !== null).length
    return Math.round((done / checkItems.value.length) * 100)
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_CHECK_ITEMS, { remark: JSON.stringify(checkItems.value) })
  }

  // ─── Save All ──────────────────────────────────────────────────────────────

  function saveAll(): void {
    _persist()
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    checkItems,
    nonComplianceSummary,
    initFromResponses,
    updateResult,
    updateRemark,
    setVoucherRef,
    setOcrRef,
    getNonCompliantCount,
    isAllChecked,
    getProgress,
    saveAll,
  }
}
