/**
 * useH5DisposalCheck — H5-8 减少检查 composable
 *
 * 24列, 联动H10, GtIndexChip
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 5.3-5.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcSubtotal } from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisposalCheckRow {
  rowId: string
  seq: number
  assetName: string
  oilField: string
  block: string
  disposalReason: string        // 处置原因(报废/出售/转让)
  disposalDate: string
  originalCost: number          // 原值
  accDepletion: number          // 累计折耗
  netValue: number              // 净值
  disposalIncome: number        // 处置收入
  disposalGainLoss: number      // 处置损益 = 收入 - 净值
  approvalDoc: string           // 审批文件
  approvalDate: string
  voucherNo: string
  voucherResult: string
  linkedH10: boolean            // 是否联动H10
  h10RefIndex: string           // H10交叉索引
  conclusion: string
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-8'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5DisposalCheck(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
  onNavigateSheet?: (sheetName: string) => void
}) {
  const { allResponses, onSave } = opts

  const rows = ref<DisposalCheckRow[]>([])
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

  function _normalize(raw: any): DisposalCheckRow {
    const netValue = Number(raw.netValue) || 0
    const income = Number(raw.disposalIncome) || 0
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: Number(raw.seq) || 0,
      assetName: raw.assetName ?? '',
      oilField: raw.oilField ?? '',
      block: raw.block ?? '',
      disposalReason: raw.disposalReason ?? '',
      disposalDate: raw.disposalDate ?? '',
      originalCost: Number(raw.originalCost) || 0,
      accDepletion: Number(raw.accDepletion) || 0,
      netValue,
      disposalIncome: income,
      disposalGainLoss: income - netValue,
      approvalDoc: raw.approvalDoc ?? '',
      approvalDate: raw.approvalDate ?? '',
      voucherNo: raw.voucherNo ?? '',
      voucherResult: raw.voucherResult ?? '',
      linkedH10: raw.linkedH10 === true,
      h10RefIndex: raw.h10RefIndex ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalDisposalCost = computed(() => calcSubtotal(rows.value.map((r) => r.originalCost)))
  const totalDisposalNetValue = computed(() => calcSubtotal(rows.value.map((r) => r.netValue)))
  const totalGainLoss = computed(() => calcSubtotal(rows.value.map((r) => r.disposalGainLoss)))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(assetName: string): void {
    rows.value.push({
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1, assetName,
      oilField: '', block: '', disposalReason: '', disposalDate: '',
      originalCost: 0, accDepletion: 0, netValue: 0,
      disposalIncome: 0, disposalGainLoss: 0,
      approvalDoc: '', approvalDate: '', voucherNo: '', voucherResult: '',
      linkedH10: false, h10RefIndex: '', conclusion: '', remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof DisposalCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 重算处置损益
    if (field === 'disposalIncome' || field === 'netValue') {
      row.disposalGainLoss = row.disposalIncome - row.netValue
    }
    _persist()
  }

  /** 跳转到H10资产处置损益 */
  function navigateToH10(rowId: string): void {
    opts.onNavigateSheet?.('H10')
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, rows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion,
    totalDisposalCost, totalDisposalNetValue, totalGainLoss,
    addRow, removeRow, updateCell, navigateToH10, saveNote, saveConclusion,
  }
}
