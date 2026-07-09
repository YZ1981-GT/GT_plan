/**
 * useH8LeaseIdentification — H8-4 租赁识别 composable（段落型，90行10列）
 *
 * CAS21租赁识别判断：
 * - 是否存在已识别资产
 * - 是否取得控制权（使用+获益）
 * - 供应商是否有实质性替换权
 * - 结论：是/否/不适用
 *
 * 段落型交互：逐项判断+说明文本
 * 每份租赁合同一次租赁识别判断（与H8-2明细行联动）
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 4.1, 4.4, 4.5
 */
import { ref, computed, watch, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 单项识别判断 */
export interface H8IdentificationItem {
  itemId: string
  /** 判断项名称 */
  label: string
  /** 判断项分类 */
  category: 'identifiedAsset' | 'controlRight' | 'substitutionRight'
  /** 结论：是/否/不适用 */
  conclusion: '是' | '否' | '不适用' | ''
  /** 说明文本 */
  explanation: string
}

/** 租赁识别记录（每份合同一份） */
export interface H8IdentificationRecord {
  recordId: string
  /** 关联合同号 */
  contractNo: string
  /** 各判断项 */
  items: H8IdentificationItem[]
  /** 最终结论 */
  finalConclusion: '是' | '否' | '不适用' | ''
  /** 审计说明 */
  auditNote: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const RECORDS_KEY = 'H8-4-records'

/** CAS21租赁识别标准判断项 */
const DEFAULT_ITEMS: Omit<H8IdentificationItem, 'itemId'>[] = [
  { label: '合同是否依赖已识别资产', category: 'identifiedAsset', conclusion: '', explanation: '' },
  { label: '资产是否明确指定（显性/隐性）', category: 'identifiedAsset', conclusion: '', explanation: '' },
  { label: '供应商是否有实质性替换权', category: 'substitutionRight', conclusion: '', explanation: '' },
  { label: '替换是否对供应商经济可行', category: 'substitutionRight', conclusion: '', explanation: '' },
  { label: '客户是否有权主导资产使用', category: 'controlRight', conclusion: '', explanation: '' },
  { label: '客户是否获得几乎全部经济利益', category: 'controlRight', conclusion: '', explanation: '' },
  { label: '使用方式在使用期前预先确定', category: 'controlRight', conclusion: '', explanation: '' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8LeaseIdentification(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const records = ref<H8IdentificationRecord[]>([])

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

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(RECORDS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      records.value = data.map((r: any) => ({
        recordId: r.recordId ?? _generateId(),
        contractNo: r.contractNo ?? '',
        items: Array.isArray(r.items) ? r.items : [],
        finalConclusion: r.finalConclusion ?? '',
        auditNote: r.auditNote ?? '',
      }))
    } else {
      records.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 已完成判断的合同数 */
  const completedCount = computed(() =>
    records.value.filter(r => r.finalConclusion !== '').length,
  )

  /** 识别为租赁的合同数 */
  const leaseCount = computed(() =>
    records.value.filter(r => r.finalConclusion === '是').length,
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  /** 新增一份合同的租赁识别判断 */
  function addRecord(contractNo: string): void {
    if (!contractNo?.trim()) return
    const items: H8IdentificationItem[] = DEFAULT_ITEMS.map(item => ({
      ...item,
      itemId: _generateId(),
    }))
    records.value.push({
      recordId: _generateId(),
      contractNo: contractNo.trim(),
      items,
      finalConclusion: '',
      auditNote: '',
    })
    _persist()
  }

  function deleteRecord(recordId: string): void {
    const idx = records.value.findIndex(r => r.recordId === recordId)
    if (idx === -1) return
    records.value.splice(idx, 1)
    _persist()
  }

  /** 更新某判断项的结论或说明 */
  function updateItem(recordId: string, itemId: string, field: 'conclusion' | 'explanation', value: string): void {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return
    const item = record.items.find(i => i.itemId === itemId)
    if (!item) return
    if (field === 'conclusion') {
      item.conclusion = value as any
    } else {
      item.explanation = value
    }
    _persist()
  }

  /** 更新最终结论 */
  function updateConclusion(recordId: string, conclusion: '是' | '否' | '不适用'): void {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return
    record.finalConclusion = conclusion
    _persist()
  }

  /** 更新审计说明 */
  function updateNote(recordId: string, note: string): void {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return
    record.auditNote = note
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(RECORDS_KEY, records.value.map(r => ({
      recordId: r.recordId, contractNo: r.contractNo,
      items: r.items.map(i => ({
        itemId: i.itemId, label: i.label, category: i.category,
        conclusion: i.conclusion, explanation: i.explanation,
      })),
      finalConclusion: r.finalConclusion, auditNote: r.auditNote,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    records, completedCount, leaseCount,
    addRecord, deleteRecord, updateItem, updateConclusion, updateNote,
    save, load,
  }
}

export default useH8LeaseIdentification
