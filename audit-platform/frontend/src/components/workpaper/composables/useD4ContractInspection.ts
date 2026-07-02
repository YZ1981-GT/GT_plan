/**
 * useD4ContractInspection — D4-12 合同检查表专属 composable
 *
 * 对齐源模板真实结构：纵向20+1字段 × 横向N份合同
 * 支持OCR附件填充、覆盖率计算、AI结论生成
 *
 * Spec: .kiro/specs/d4-12-contract-inspection/
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum } from './useD4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ContractInspectionItem {
  id: string
  indexNo: string               // "D4-12-1" ~ "D4-12-N"
  label: string                 // 用户输入的备注名（如"XX公司采购合同"）
  // 基础信息
  contractNo: string
  counterparty: string
  signDate: string
  serviceContent: string
  contractAmount: number
  // 交付条款
  deliveryTime: string
  deliveryMethod: string
  settlementMethod: string
  settlementTime: string
  // 合同条款
  warrantyClause: string
  returnClause: string
  breachClause: string
  specialTerms: string
  // 签署确认
  isSigned: 'Y' | 'N' | 'NA' | ''
  isSealed: 'Y' | 'N' | 'NA' | ''
  // 收入确认
  recognitionMethod: '时段法' | '时点法' | ''
  acceptanceClause: string
  recognitionTime: string
  controlTransferDoc: string
  specialTransaction: string
  // 结论
  conclusion: 'Y' | 'N' | 'NA' | ''
  // 附件
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

/** OCR提取返回的字段映射 */
export interface OcrExtractedFields {
  contractNo?: string
  counterparty?: string
  signDate?: string
  serviceContent?: string
  contractAmount?: number
  deliveryTime?: string
  deliveryMethod?: string
  settlementMethod?: string
  settlementTime?: string
  warrantyClause?: string
  returnClause?: string
  breachClause?: string
  specialTerms?: string
  isSigned?: string
  isSealed?: string
  recognitionMethod?: string
  acceptanceClause?: string
  recognitionTime?: string
  controlTransferDoc?: string
  specialTransaction?: string
}

export interface UseD4ContractInspectionOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}

// ─── 编制提示常量 ─────────────────────────────────────────────────────────────

export const CONTRACT_GUIDANCE = [
  {
    title: '提示1：表明销售合同异常举例',
    content: `（1）销售合同未签字盖章，或者销售合同上加盖的公章并不属于合同所指定的客户。
（2）销售合同中重要条款（例如，交货地点、付款条件）缺失或含糊。
（3）销售合同中部分条款或条件不同于被审计单位的标准销售合同，或过于复杂。
（4）销售合同或发运单上的日期被更改。`,
  },
  {
    title: '提示2：第三方配合舞弊迹象',
    content: `（1）第三方配合被审计单位签订购销合同，通过"真"合同假交易虚构收入。
（2）第三方配合隐瞒相关合同条款或"抽屉"协议，如退货条款、价格保护机制等。
（3）在第三方配合下，进行显失公允的交易（如明显高于其他客户的价格向第三方销售）。
（4）在第三方配合下，构建不具有商业实质的贸易业务并确认收入。
（5）对于时段法+产出法的交易，第三方配合高估履约进度多确认收入。
（6）交易价格、交易方式或合同条款明显不同于被审计单位与其他方的交易。
（7）第三方拒绝确认注册会计师要求其确认的某些事项。`,
  },
  {
    title: '提示3：合同成立条件检查要点',
    content: `（1）分业务类型选取重要合同样本，分析合同是否成立（同时满足合同成立的五项条件）。
（2）判断被审计单位对合同所包含的各单项履约义务的评估是否恰当。
（3）合同中包含两项或多项履约义务的，测试交易价格的分摊是否正确（单独售价/折扣/可变对价）。
（4）对于与同一客户（或关联方）同时/相近时间订立的两份或多份合同，分析会计处理是否正确。
（5）确定对原始合同的修改以及增加均有签字确认，分析合同变更的会计处理是否正确。`,
  },
  {
    title: '提示4：五步法分析参考',
    content: `五步法分析、主要责任人和代理人、知识产权等可参考《营业收入五步法、主要责任人代理人、知识产权分析参考示例》。`,
  },
]

// ─── 字段分组定义 ──────────────────────────────────────────────────────────────

export const FIELD_GROUPS = [
  {
    label: '基础信息',
    fields: [
      { key: 'contractNo', label: '合同编号', type: 'text' },
      { key: 'counterparty', label: '交易对方名称', type: 'text' },
      { key: 'signDate', label: '合同签订日期', type: 'date' },
      { key: 'serviceContent', label: '服务内容/提供产品名称', type: 'textarea' },
      { key: 'contractAmount', label: '合同金额', type: 'number' },
    ],
  },
  {
    label: '交付条款',
    fields: [
      { key: 'deliveryTime', label: '交货时间/服务期间', type: 'text' },
      { key: 'deliveryMethod', label: '交货方式/提供服务方式', type: 'text' },
      { key: 'settlementMethod', label: '结算方式', type: 'text' },
      { key: 'settlementTime', label: '结算时间', type: 'text' },
    ],
  },
  {
    label: '合同条款',
    fields: [
      { key: 'warrantyClause', label: '质量保证条款', type: 'textarea' },
      { key: 'returnClause', label: '销售退回条款', type: 'textarea' },
      { key: 'breachClause', label: '违约条款', type: 'textarea' },
      { key: 'specialTerms', label: '特殊约定（信用期、运输方式等与惯例/同行业不同之处）', type: 'textarea' },
    ],
  },
  {
    label: '签署确认',
    fields: [
      { key: 'isSigned', label: '订立双方是否签字', type: 'radio' },
      { key: 'isSealed', label: '订立双方是否盖章', type: 'radio' },
    ],
  },
  {
    label: '收入确认',
    fields: [
      { key: 'recognitionMethod', label: '时段法/时点法', type: 'method' },
      { key: 'acceptanceClause', label: '验收条款', type: 'textarea' },
      { key: 'recognitionTime', label: '收入确认时间', type: 'text' },
      { key: 'controlTransferDoc', label: '表明控制权转移的单据名称', type: 'text' },
      { key: 'specialTransaction', label: '是否涉及特定交易及相关说明', type: 'textarea' },
    ],
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4ContractInspection(options: UseD4ContractInspectionOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options

  const contracts = ref<ContractInspectionItem[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load ──────────────────────────────────────────────────────────────

  function loadContracts() {
    const resp = allResponses.value.get('D4-12-contracts-v2')
    if (resp?.remark) {
      try {
        const parsed = JSON.parse(resp.remark)
        if (Array.isArray(parsed) && parsed.length) {
          contracts.value = parsed
          return
        }
      } catch { /* ignore */ }
    }
    contracts.value = []
  }

  function loadNoteConclusion() {
    auditNote.value = allResponses.value.get('D4-12-note')?.remark || ''
    auditConclusion.value = allResponses.value.get('D4-12-conclusion')?.remark || ''
  }

  watch(() => allResponses.value.get('D4-12-contracts-v2')?.remark, () => loadContracts(), { immediate: true })
  watch(() => allResponses.value.get('D4-12-note')?.remark, () => loadNoteConclusion(), { immediate: true })

  // ─── CRUD ──────────────────────────────────────────────────────────────

  function addContract(label: string): ContractInspectionItem {
    const idx = contracts.value.length + 1
    const item: ContractInspectionItem = {
      id: `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      indexNo: `D4-12-${idx}`,
      label,
      contractNo: '',
      counterparty: '',
      signDate: '',
      serviceContent: '',
      contractAmount: 0,
      deliveryTime: '',
      deliveryMethod: '',
      settlementMethod: '',
      settlementTime: '',
      warrantyClause: '',
      returnClause: '',
      breachClause: '',
      specialTerms: '',
      isSigned: '',
      isSealed: '',
      recognitionMethod: '',
      acceptanceClause: '',
      recognitionTime: '',
      controlTransferDoc: '',
      specialTransaction: '',
      conclusion: '',
      ocrStatus: 'none',
    }
    contracts.value.push(item)
    persistContracts()
    return item
  }

  function removeContract(id: string) {
    if (isReadonly.value) return
    contracts.value = contracts.value.filter(c => c.id !== id)
    // 重新编号
    contracts.value.forEach((c, i) => { c.indexNo = `D4-12-${i + 1}` })
    persistContracts()
  }

  function updateField(id: string, field: keyof ContractInspectionItem, value: any) {
    if (isReadonly.value) return
    const item = contracts.value.find(c => c.id === id)
    if (item) {
      ;(item as any)[field] = value
      persistContracts()
    }
  }

  function mergeOcrFields(id: string, fields: OcrExtractedFields, overwriteExisting: boolean) {
    const item = contracts.value.find(c => c.id === id)
    if (!item) return
    for (const [key, val] of Object.entries(fields)) {
      if (val == null || val === '') continue
      const currentVal = (item as any)[key]
      if (overwriteExisting || !currentVal || currentVal === '' || currentVal === 0) {
        ;(item as any)[key] = val
      }
    }
    item.ocrStatus = 'done'
    persistContracts()
  }

  function setOcrStatus(id: string, status: ContractInspectionItem['ocrStatus']) {
    const item = contracts.value.find(c => c.id === id)
    if (item) {
      item.ocrStatus = status
      persistContracts()
    }
  }

  function setAttachment(id: string, attachmentId: string, attachmentName: string) {
    const item = contracts.value.find(c => c.id === id)
    if (item) {
      item.attachmentId = attachmentId
      item.attachmentName = attachmentName
      persistContracts()
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  const totalContractAmount = computed(() =>
    contracts.value.reduce((sum, c) => sum + parseNum(c.contractAmount), 0),
  )

  const coverageRate = computed(() => {
    // 从allResponses读D4-1审定表的总收入
    const totalRevenueResp = allResponses.value.get('D4-adj-revenue-total')
    const totalRevenue = parseNum(totalRevenueResp?.remark)
    if (totalRevenue <= 0) return 0
    return Math.min((totalContractAmount.value / totalRevenue) * 100, 100)
  })

  const completedCount = computed(() =>
    contracts.value.filter(c => c.conclusion && c.conclusion !== '').length,
  )

  const summaryConclusion = computed(() => {
    const total = contracts.value.length
    if (total === 0) return ''
    const compliant = contracts.value.filter(c => c.conclusion === 'Y').length
    const nonCompliant = contracts.value.filter(c => c.conclusion === 'N').length
    const amountStr = (totalContractAmount.value / 10000).toFixed(2)
    return `共检查${total}份合同，金额${amountStr}万元，覆盖率${coverageRate.value.toFixed(1)}%。` +
      `其中${compliant}份合规，${nonCompliant}份存在问题。`
  })

  // ─── Audit note/conclusion ─────────────────────────────────────────────

  function updateAuditNote(val: string) {
    if (isReadonly.value) return
    auditNote.value = val
    persistMeta()
  }

  function updateAuditConclusion(val: string) {
    if (isReadonly.value) return
    auditConclusion.value = val
    persistMeta()
  }

  // ─── Persist ───────────────────────────────────────────────────────────

  function persistContracts() {
    allResponses.value.set('D4-12-contracts-v2', {
      item_id: 'D4-12-contracts-v2',
      conclusion: null,
      remark: JSON.stringify(contracts.value),
    })
    debounceSave()
  }

  function persistMeta() {
    allResponses.value.set('D4-12-note', {
      item_id: 'D4-12-note', conclusion: null, remark: auditNote.value,
    })
    allResponses.value.set('D4-12-conclusion', {
      item_id: 'D4-12-conclusion', conclusion: null, remark: auditConclusion.value,
    })
    debounceSave()
  }

  function debounceSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave() {
    const keys = ['D4-12-contracts-v2', 'D4-12-note', 'D4-12-conclusion']
    const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
    window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    contracts,
    auditNote,
    auditConclusion,
    totalContractAmount,
    coverageRate,
    completedCount,
    summaryConclusion,
    addContract,
    removeContract,
    updateField,
    mergeOcrFields,
    setOcrStatus,
    setAttachment,
    updateAuditNote,
    updateAuditConclusion,
  }
}
