/**
 * useK4Check — K4-4 其他流动负债检查表
 *
 * ⚠️ DEPRECATED: 此 composable 是旧版 4 项 radio 合规性检查清单。
 * K4TabCheck.vue 已按源模板重建为凭证级测试（复用 useK1VoucherCheck），
 * 本文件中的 4 项检查不再被任何 .vue 文件渲染消费。
 * 保留仅为向后兼容旧持久化数据（K4-4-check-items），新功能请勿使用。
 *
 * @deprecated 使用 K4TabCheck.vue + useK1VoucherCheck 替代
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/
 * Task: 3.4
 * Requirements: 4.1-4.3
 *
 * 职责：
 * - 逐项检查：分类正确性 / 流动性判断 / 完整性(反向截止) / 合规性
 * - Per-item conclusion: "合规" | "不合规" | "不适用"
 * - Red summary warning when any "不合规" exists
 * - Integration: 行级抽凭 (voucher sampling engine) + 行级OCR
 * - Save with prefix "K4-4-"
 *
 * 科目：2245 其他流动负债（**贷方/负债类**）
 * ⚠️ 完整性认定为主（负债易少计）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type K4ComplianceState = '合规' | '不合规' | '不适用'

export interface K4CheckItem {
  id: string
  seq: number
  label: string                // 检查项
  description: string          // 检查内容/标准
  compliance: K4ComplianceState | null
  evidence: string             // 审计证据
  voucherRef: string           // 抽凭凭证号（行级抽凭）
  ocrAttachment: string        // OCR附件路径（行级OCR）
  remark: string
}

export interface K4NonComplianceSummary {
  count: number
  hasNonCompliant: boolean
  items: Array<{ id: string; label: string; detail: string }>
}

export interface UseK4CheckParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_CHECK_ITEMS = 'K4-4-check-items'

// ─── Default K4-4 检查项模板（Req 4.1: 分类正确性/流动性判断/完整性/合规性）──────

const DEFAULT_CHECK_ITEMS: Omit<K4CheckItem, 'compliance' | 'evidence' | 'voucherRef' | 'ocrAttachment' | 'remark'>[] = [
  {
    id: 'K4-4-01',
    seq: 1,
    label: '分类正确性',
    description: '其他流动负债科目分类恰当，未混入应付账款/预收账款/合同负债等，核实各项目是否符合其他流动负债定义',
  },
  {
    id: 'K4-4-02',
    seq: 2,
    label: '流动性判断',
    description: '所有项目均为流动负债（预计在一个营业周期内偿付），非流动项目已重分类至其他非流动负债',
  },
  {
    id: 'K4-4-03',
    seq: 3,
    label: '完整性（反向截止）',
    description: '通过期后偿付/到期倒查确认期末已充分入账所有其他流动负债，不存在少计/漏计（完整性认定）',
  },
  {
    id: 'K4-4-04',
    seq: 4,
    label: '合规性',
    description: '各项目符合相关法规要求，预提费用有充分依据，代扣代缴及时足额，待转销项税额处理正确',
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK4Check(params: UseK4CheckParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const checkItems = ref<K4CheckItem[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const item = allResponses.value.get(ITEM_ID_CHECK_ITEMS)
    const raw = item?.remark ?? item?.conclusion ?? null
    if (!raw) {
      // 使用默认模板
      checkItems.value = DEFAULT_CHECK_ITEMS.map((t): K4CheckItem => ({
        ...t,
        compliance: null,
        evidence: '',
        voucherRef: '',
        ocrAttachment: '',
        remark: '',
      }))
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        checkItems.value = parsed.map(_normalizeCheckItem)
      } else {
        checkItems.value = DEFAULT_CHECK_ITEMS.map((t): K4CheckItem => ({
          ...t, compliance: null, evidence: '', voucherRef: '', ocrAttachment: '', remark: '',
        }))
      }
    } catch {
      checkItems.value = DEFAULT_CHECK_ITEMS.map((t): K4CheckItem => ({
        ...t, compliance: null, evidence: '', voucherRef: '', ocrAttachment: '', remark: '',
      }))
    }
  }

  function _normalizeCheckItem(raw: any, idx?: number): K4CheckItem {
    return {
      id: raw.id ?? `K4-4-${String((idx ?? 0) + 1).padStart(2, '0')}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      label: raw.label ?? '',
      description: raw.description ?? '',
      compliance: raw.compliance ?? null,
      evidence: raw.evidence ?? '',
      voucherRef: raw.voucherRef ?? '',
      ocrAttachment: raw.ocrAttachment ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── 不合规摘要 (Req 4.3: Red summary warning when any "不合规") ──────────────

  const nonComplianceSummary: ComputedRef<K4NonComplianceSummary> = computed(() => {
    const items: K4NonComplianceSummary['items'] = []

    for (const item of checkItems.value) {
      if (item.compliance === '不合规') {
        items.push({
          id: item.id,
          label: item.label,
          detail: item.evidence || item.remark || '无补充说明',
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
  function updateCompliance(itemId: string, compliance: K4ComplianceState): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.compliance = compliance
      _persist()
    }
  }

  /** 更新检查项证据 */
  function updateEvidence(itemId: string, evidence: string): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.evidence = evidence
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

  /** 行级OCR：设置OCR附件路径 */
  function setOcrAttachment(itemId: string, path: string): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.ocrAttachment = path
      _persist()
    }
  }

  // ─── 统计方法 ─────────────────────────────────────────────────────────────

  /** 获取"不合规"项目数 */
  function getNonCompliantCount(): number {
    return nonComplianceSummary.value.count
  }

  /** 是否全部已完成判定 */
  function isAllChecked(): boolean {
    return checkItems.value.every(item => item.compliance !== null)
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_CHECK_ITEMS, { remark: JSON.stringify(checkItems.value) })
  }

  // ─── 保存全部 ──────────────────────────────────────────────────────────────

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
    updateCompliance,
    updateEvidence,
    updateRemark,
    setVoucherRef,
    setOcrAttachment,
    getNonCompliantCount,
    isAllChecked,
    saveAll,
  }
}
