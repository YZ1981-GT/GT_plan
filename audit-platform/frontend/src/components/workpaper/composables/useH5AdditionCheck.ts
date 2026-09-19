/**
 * useH5AdditionCheck — H5-7 增加检查 composable
 *
 * 24列, 勘探资本化, 抽凭
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 5.1-5.2, 5.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcSubtotal } from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdditionCheckRow {
  rowId: string
  seq: number
  assetName: string
  oilField: string
  block: string
  amount: number
  capitalizationBasis: string   // 资本化依据
  explorationStage: string      // 勘探阶段(勘探/评价/开发)
  developmentStage: string      // 开发阶段
  approvalDoc: string           // 审批文件
  approvalDate: string          // 审批日期
  contractNo: string            // 合同编号
  supplier: string              // 供应商
  paymentDate: string           // 付款日期
  voucherNo: string             // 凭证号
  voucherResult: string         // 抽凭结果
  voucherAttachment: string     // 附件
  isCapitalized: boolean        // 是否资本化
  capitalizeReason: string      // 资本化原因
  conclusion: string            // 检查结论
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-7'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5AdditionCheck(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const rows = ref<AdditionCheckRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const raw = allResponses.value.get(`${ITEM_PREFIX}-rows`)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalize) : []
      } catch { rows.value = [] }
    } else { rows.value = [] }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalize(raw: any): AdditionCheckRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: Number(raw.seq) || 0,
      assetName: raw.assetName ?? '',
      oilField: raw.oilField ?? '',
      block: raw.block ?? '',
      amount: Number(raw.amount) || 0,
      capitalizationBasis: raw.capitalizationBasis ?? '',
      explorationStage: raw.explorationStage ?? '',
      developmentStage: raw.developmentStage ?? '',
      approvalDoc: raw.approvalDoc ?? '',
      approvalDate: raw.approvalDate ?? '',
      contractNo: raw.contractNo ?? '',
      supplier: raw.supplier ?? '',
      paymentDate: raw.paymentDate ?? '',
      voucherNo: raw.voucherNo ?? '',
      voucherResult: raw.voucherResult ?? '',
      voucherAttachment: raw.voucherAttachment ?? '',
      isCapitalized: raw.isCapitalized === true,
      capitalizeReason: raw.capitalizeReason ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalAmount = computed(() => calcSubtotal(rows.value.map((r) => r.amount)))
  const capitalizedCount = computed(() => rows.value.filter((r) => r.isCapitalized).length)
  const capitalizedAmount = computed(() => calcSubtotal(rows.value.filter((r) => r.isCapitalized).map((r) => r.amount)))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(assetName: string): void {
    rows.value.push({
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1, assetName,
      oilField: '', block: '', amount: 0,
      capitalizationBasis: '', explorationStage: '', developmentStage: '',
      approvalDoc: '', approvalDate: '', contractNo: '', supplier: '',
      paymentDate: '', voucherNo: '', voucherResult: '', voucherAttachment: '',
      isCapitalized: false, capitalizeReason: '', conclusion: '', remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof AdditionCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, rows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion,
    totalAmount, capitalizedCount, capitalizedAmount,
    addRow, removeRow, updateCell, saveNote, saveConclusion,
  }
}
