/**
 * useK5ProvisionCheck — K5-7 综合检查表逻辑
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.4
 * Requirements: 8.3-8.5
 *
 * 职责：
 * - 综合检查表：逐项"合规/不合规/不适用"判断
 * - 红色摘要提示（存在"不合规"项时）
 * - 行级抽凭 + 行级OCR（评估报告）
 * - Save with prefix "K5-7-"
 *
 * 科目：2701 预计负债（**贷方/负债类**）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type K5ComplianceState = '合规' | '不合规' | '不适用'

export interface K5ProvisionCheckItem {
  id: string
  seq: number
  label: string                // 检查项
  description: string          // 检查内容/标准
  compliance: K5ComplianceState | null
  evidence: string             // 审计证据
  voucherRef: string           // 抽凭凭证号
  ocrAttachment: string        // OCR附件路径
  remark: string
}

export interface K5NonComplianceSummary {
  count: number
  hasNonCompliant: boolean
  items: Array<{ id: string; label: string; detail: string }>
}

export interface UseK5ProvisionCheckParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_CHECK_ITEMS = 'K5-7-check-items'

// ─── Default K5-7 检查项模板（综合检查） ─────────────────────────────────────

const DEFAULT_CHECK_ITEMS: Omit<K5ProvisionCheckItem, 'compliance' | 'evidence' | 'voucherRef' | 'ocrAttachment' | 'remark'>[] = [
  {
    id: 'K5-7-01',
    seq: 1,
    label: '或有事项识别完整性',
    description: '是否充分识别所有或有事项，包括未决诉讼、产品质量保修、亏损合同、重组义务、弃置义务等',
  },
  {
    id: 'K5-7-02',
    seq: 2,
    label: '可能性评估合理性',
    description: '对各或有事项的可能性级别判断（很可能/可能/极小可能）是否具有充分依据',
  },
  {
    id: 'K5-7-03',
    seq: 3,
    label: '最佳估计数计量',
    description: '已确认的预计负债最佳估计数计量方法（单值/区间中值/期望值）是否恰当、计算正确',
  },
  {
    id: 'K5-7-04',
    seq: 4,
    label: '时间价值折现',
    description: '涉及时间价值重大的预计负债（如弃置费用）是否按适当折现率折现，折现率是否合理',
  },
  {
    id: 'K5-7-05',
    seq: 5,
    label: '或有负债披露',
    description: '可能性级别为"可能"的或有事项是否在附注中充分披露，披露内容是否完整',
  },
  {
    id: 'K5-7-06',
    seq: 6,
    label: '跨期确认',
    description: '期末预计负债确认时点是否正确，不存在提前或延迟确认',
  },
  {
    id: 'K5-7-07',
    seq: 7,
    label: '分类正确性',
    description: '预计负债各子项目在资产负债表中分类列报正确，流动/非流动划分恰当',
  },
  {
    id: 'K5-7-08',
    seq: 8,
    label: '律师函函证一致性',
    description: '律师回函内容与管理层披露的未决诉讼信息一致，无矛盾或遗漏',
  },
  {
    id: 'K5-7-09',
    seq: 9,
    label: '期后事项',
    description: '审计报告日前是否有新的诉讼/仲裁/赔偿事项发生，是否需要调整或补充披露',
  },
  {
    id: 'K5-7-10',
    seq: 10,
    label: '关联方或有事项',
    description: '涉及关联方的担保、诉讼等或有事项是否充分识别和披露',
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5ProvisionCheck(params: UseK5ProvisionCheckParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const checkItems = ref<K5ProvisionCheckItem[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const item = allResponses.value.get(ITEM_ID_CHECK_ITEMS)
    const raw = item?.remark ?? item?.conclusion ?? null
    if (!raw) {
      checkItems.value = _buildDefaults()
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        checkItems.value = parsed.map(_normalizeCheckItem)
      } else {
        checkItems.value = _buildDefaults()
      }
    } catch {
      checkItems.value = _buildDefaults()
    }
  }

  function _buildDefaults(): K5ProvisionCheckItem[] {
    return DEFAULT_CHECK_ITEMS.map((t): K5ProvisionCheckItem => ({
      ...t,
      compliance: null,
      evidence: '',
      voucherRef: '',
      ocrAttachment: '',
      remark: '',
    }))
  }

  function _normalizeCheckItem(raw: any, idx?: number): K5ProvisionCheckItem {
    return {
      id: raw.id ?? `K5-7-${String((idx ?? 0) + 1).padStart(2, '0')}`,
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

  // ─── 不合规摘要 (Req 8.5: 红色摘要提示) ───────────────────────────────────

  const nonComplianceSummary: ComputedRef<K5NonComplianceSummary> = computed(() => {
    const items: K5NonComplianceSummary['items'] = []
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
  function updateCompliance(itemId: string, compliance: K5ComplianceState): void {
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

  /** 行级抽凭：设置凭证号引用 */
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
    saveResponse('7-check-items', { remark: JSON.stringify(checkItems.value) })
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
