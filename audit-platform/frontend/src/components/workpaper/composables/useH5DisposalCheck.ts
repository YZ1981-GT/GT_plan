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
import {
  useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import { assetAmount, assetLegacyKey, sampleOf, sampleRemark } from './assetVoucherFill'

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

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：油田 / 区块、处置原因、折耗与净值、处置收入、审批、联动 H10、结论等 */
export function hasH5DisposalContent(r: DisposalCheckRow): boolean {
  return [r.oilField, r.block, r.disposalReason, r.approvalDoc, r.approvalDate, r.h10RefIndex, r.conclusion]
    .some(v => String(v ?? '').trim() !== '')
    || [r.accDepletion, r.netValue, r.disposalIncome].some(v => Number(v) !== 0) || r.linkedH10
}

export function useH5DisposalCheck(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
  onNavigateSheet?: (sheetName: string) => void
  /** 整张底稿只读：抽凭回填 / 挂凭导入 / 撤销一律不改行 */
  isReadonly?: Ref<boolean>
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
        rows.value = Array.isArray(parsed) ? parsed.map((r: any) => withRowMeta(_normalize(r), r)) : []
      } catch { rows.value = [] }
    } else { rows.value = [] }
    voucherFill.markLoaded()
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
    rows.value.push(_emptyRow(assetName))
    _persist()
  }

  function _emptyRow(assetName: string): DisposalCheckRow {
    return {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1, assetName,
      oilField: '', block: '', disposalReason: '', disposalDate: '',
      originalCost: 0, accDepletion: 0, netValue: 0,
      disposalIncome: 0, disposalGainLoss: 0,
      approvalDoc: '', approvalDate: '', voucherNo: '', voucherResult: '',
      linkedH10: false, h10RefIndex: '', conclusion: '', remark: '',
    }
  }

  /**
   * 共享回填函数的待写入项 → 减少检查行（任务 12）：资产名称取摘要，凭证号、减少日期、原值（样本自己那一栏，
   * 减少在贷方，红字带符号照记）。原实现把凭证号、原值作为第二个参数传给只收名称的 addRow，被丢掉
   */
  function _rowFromPrepared(item: PreparedItem): DisposalCheckRow {
    const s = sampleOf(item)
    const row = _emptyRow(String(s.summary || '抽凭样本').slice(0, 80))
    row.voucherNo = String(s.voucherNo ?? '')
    row.disposalDate = String(s.voucherDate ?? '')
    row.originalCost = assetAmount(item, 'credit')
    row.voucherResult = '已抽凭'
    row.remark = sampleRemark(item, '高值必选')
    return row
  }

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（一个样本一行）
  const voucherFill = useVoucherCheckFill<DisposalCheckRow>({
    projectId: () => opts.projectId.value,
    tables: rows,
    policy: 'join',
    mapSampleToRow: item => _rowFromPrepared(item),
    persist: () => _persist(),
    hasUserContent: hasH5DisposalContent,
    afterChange: (_key, list) => { list.forEach((r, i) => { r.seq = i + 1 }) },
    // 旧行（没有 `_gt`）身份：凭证号 + 原值（原实现回填没写减少日期）
    legacy: r => assetLegacyKey(r.voucherNo, '', r.originalCost),
    readonly: () => opts.isReadonly?.value === true,
  })


  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0 && voucherFill.isRowLocked(rows.value[idx])) return
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof DisposalCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || voucherFill.isRowLocked(row)) return
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

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, voucherFill.guardPersist(rows.value)) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion,
    totalDisposalCost, totalDisposalNetValue, totalGainLoss,
    addRow, removeRow, updateCell, navigateToH10, saveNote, saveConclusion,
    onEngineFilled: (payload: EngineFilledPayload) => voucherFill.onEngineFilled(payload),
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: (payload: UndoRequestPayload) => voucherFill.onUndoRequest(payload),
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}
