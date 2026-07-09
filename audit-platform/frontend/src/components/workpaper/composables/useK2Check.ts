/**
 * useK2Check — K2-6 检查表 composable
 *
 * 管理检查项：分类正确性/流动性/可回收性/资本化合理性
 * 每项："合规/不合规/不适用" 选择
 *
 * 核心功能：
 * - 逐项合规判定 + 行级抽凭引擎集成
 * - 行级OCR支持（📎附件列）
 * - 红色摘要：存在任何"不合规"项时高亮
 * - 持久化到 checklist_responses（前缀 K2-6-check-xxx）
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 3.4
 * Requirements: 6.1-6.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type K2CheckResult = '合规' | '不合规' | '不适用' | ''

export interface K2CheckItem {
  key: string
  label: string
  description: string
  result: K2CheckResult
  voucherRef: string        // 抽凭引用
  ocrAttachment: string     // OCR附件路径
  evidence: string          // 审计证据描述
  remark: string            // 备注
}

export interface K2CheckSummary {
  total: number
  compliant: number
  nonCompliant: number
  notApplicable: number
  pending: number
  hasNonCompliant: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_PREFIX = 'K2-6-check'

const RESULT_OPTIONS: K2CheckResult[] = ['合规', '不合规', '不适用']

/** K2-6 检查项定义 */
const K2_CHECK_DEFINITIONS: { key: string; label: string; description: string }[] = [
  {
    key: 'classification',
    label: '分类正确性',
    description: '检查其他流动资产各项目是否正确分类，是否存在应归入其他科目的项目',
  },
  {
    key: 'liquidity',
    label: '流动性判断',
    description: '检查是否仍满足流动资产条件（预计12个月内变现/使用），是否有应转为非流动资产的项目',
  },
  {
    key: 'recoverability',
    label: '可回收性',
    description: '检查各项目的可回收性，是否存在减值迹象（对方信用恶化/合同取消/长期挂账等）',
  },
  {
    key: 'capitalization',
    label: '资本化合理性',
    description: '检查合同取得成本资本化是否满足CAS14条件（增量+可收回+直接相关），费用化处理是否恰当',
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK2Check(
  allResponses: Ref<Map<string, any>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const checkItems = ref<K2CheckItem[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadItems(): void {
    checkItems.value = K2_CHECK_DEFINITIONS.map((def) => {
      const itemId = `${ITEM_ID_PREFIX}-${def.key}`
      const resultRaw = _getVal(`${itemId}-result`)
      const result: K2CheckResult = RESULT_OPTIONS.includes(resultRaw as K2CheckResult)
        ? (resultRaw as K2CheckResult)
        : ''
      return {
        key: def.key,
        label: def.label,
        description: def.description,
        result,
        voucherRef: _getVal(`${itemId}-voucher`),
        ocrAttachment: _getVal(`${itemId}-ocr`),
        evidence: _getVal(`${itemId}-evidence`),
        remark: _getVal(`${itemId}-remark`),
      }
    })
  }

  function _getVal(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
  }

  // ─── Computed: Summary (Req 6.3) ──────────────────────────────────────────

  const summary: ComputedRef<K2CheckSummary> = computed(() => {
    const items = checkItems.value
    const total = items.length
    const compliant = items.filter((i) => i.result === '合规').length
    const nonCompliant = items.filter((i) => i.result === '不合规').length
    const notApplicable = items.filter((i) => i.result === '不适用').length
    const pending = items.filter((i) => i.result === '').length
    return {
      total,
      compliant,
      nonCompliant,
      notApplicable,
      pending,
      hasNonCompliant: nonCompliant > 0,
    }
  })

  // ─── Update Field ──────────────────────────────────────────────────────────

  function updateCheckResult(key: string, result: K2CheckResult): void {
    const item = checkItems.value.find((i) => i.key === key)
    if (!item) return
    item.result = result
    options?.onSave?.(`${ITEM_ID_PREFIX}-${key}-result`, result)
  }

  function updateCheckField(key: string, field: 'voucherRef' | 'ocrAttachment' | 'evidence' | 'remark', value: string): void {
    const item = checkItems.value.find((i) => i.key === key)
    if (!item) return
    item[field] = value
    const fieldSuffix = field === 'voucherRef' ? 'voucher' : field === 'ocrAttachment' ? 'ocr' : field
    options?.onSave?.(`${ITEM_ID_PREFIX}-${key}-${fieldSuffix}`, value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadItems(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    checkItems,
    summary,
    updateCheckResult,
    updateCheckField,
    /** 检查项定义（供UI使用） */
    CHECK_DEFINITIONS: K2_CHECK_DEFINITIONS,
    /** 结果选项 */
    RESULT_OPTIONS,
  }
}
