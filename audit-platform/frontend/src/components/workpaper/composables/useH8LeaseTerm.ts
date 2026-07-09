/**
 * useH8LeaseTerm — H8-5 租赁期确定 composable（段落型，52行8列）
 *
 * CAS21租赁期 = 不可撤销期 + 合理确定续租期 - 合理确定终止期
 *
 * 段落型交互：逐项判断续租/终止选择权是否合理确定行使
 * 每份合同一份租赁期确定记录
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 4.2, 4.4
 */
import { ref, computed, watch, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 租赁期确定记录 */
export interface H8LeaseTermRecord {
  recordId: string
  /** 关联合同号 */
  contractNo: string
  /** 不可撤销租赁期（月） */
  nonCancellableTerm: number
  /** 续租选择权期限（月） */
  renewalOptionTerm: number
  /** 是否合理确定行使续租选择权 */
  isRenewalReasonablyCertain: '是' | '否' | ''
  /** 终止选择权期限（月） */
  terminationOptionTerm: number
  /** 是否合理确定行使终止选择权 */
  isTerminationReasonablyCertain: '是' | '否' | ''
  /** 最终租赁期（月） */
  finalLeaseTerm: number
  /** 判断说明 */
  explanation: string
  /** 结论 */
  conclusion: '是' | '否' | '不适用' | ''
}

// ─── Constants ───────────────────────────────────────────────────────────────

const RECORDS_KEY = 'H8-5-records'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8LeaseTerm(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const records = ref<H8LeaseTermRecord[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _generateId(): string {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  }

  /** 计算最终租赁期 = 不可撤销期 + (合理确定续租?续租期:0) - (合理确定终止?终止期:0) */
  function _calcFinalTerm(record: H8LeaseTermRecord): number {
    let term = record.nonCancellableTerm
    if (record.isRenewalReasonablyCertain === '是') {
      term += record.renewalOptionTerm
    }
    if (record.isTerminationReasonablyCertain === '是') {
      term -= record.terminationOptionTerm
    }
    return Math.max(term, 0)
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(RECORDS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      records.value = data.map((r: any) => {
        const rec: H8LeaseTermRecord = {
          recordId: r.recordId ?? _generateId(),
          contractNo: r.contractNo ?? '',
          nonCancellableTerm: Number(r.nonCancellableTerm) || 0,
          renewalOptionTerm: Number(r.renewalOptionTerm) || 0,
          isRenewalReasonablyCertain: r.isRenewalReasonablyCertain ?? '',
          terminationOptionTerm: Number(r.terminationOptionTerm) || 0,
          isTerminationReasonablyCertain: r.isTerminationReasonablyCertain ?? '',
          finalLeaseTerm: 0,
          explanation: r.explanation ?? '',
          conclusion: r.conclusion ?? '',
        }
        rec.finalLeaseTerm = _calcFinalTerm(rec)
        return rec
      })
    } else {
      records.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 已完成记录数 */
  const completedCount = computed(() =>
    records.value.filter(r => r.conclusion !== '').length,
  )

  /** 平均租赁期（月） */
  const avgLeaseTerm = computed(() => {
    if (records.value.length === 0) return 0
    const total = records.value.reduce((s, r) => s + r.finalLeaseTerm, 0)
    return Math.round(total / records.value.length)
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRecord(contractNo: string): void {
    if (!contractNo?.trim()) return
    records.value.push({
      recordId: _generateId(),
      contractNo: contractNo.trim(),
      nonCancellableTerm: 0,
      renewalOptionTerm: 0,
      isRenewalReasonablyCertain: '',
      terminationOptionTerm: 0,
      isTerminationReasonablyCertain: '',
      finalLeaseTerm: 0,
      explanation: '',
      conclusion: '',
    })
    _persist()
  }

  function deleteRecord(recordId: string): void {
    const idx = records.value.findIndex(r => r.recordId === recordId)
    if (idx === -1) return
    records.value.splice(idx, 1)
    _persist()
  }

  function updateField(recordId: string, field: string, value: any): void {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return

    const numFields = ['nonCancellableTerm', 'renewalOptionTerm', 'terminationOptionTerm']
    if (numFields.includes(field)) {
      ;(record as any)[field] = Number(value) || 0
    } else {
      ;(record as any)[field] = String(value ?? '')
    }

    // 重算最终租赁期
    record.finalLeaseTerm = _calcFinalTerm(record)
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(RECORDS_KEY, records.value.map(r => ({
      recordId: r.recordId, contractNo: r.contractNo,
      nonCancellableTerm: r.nonCancellableTerm,
      renewalOptionTerm: r.renewalOptionTerm,
      isRenewalReasonablyCertain: r.isRenewalReasonablyCertain,
      terminationOptionTerm: r.terminationOptionTerm,
      isTerminationReasonablyCertain: r.isTerminationReasonablyCertain,
      explanation: r.explanation, conclusion: r.conclusion,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    records, completedCount, avgLeaseTerm,
    addRecord, deleteRecord, updateField, save, load,
  }
}

export default useH8LeaseTerm
