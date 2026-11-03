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
import {
  useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import { assetAmount, assetLegacyKey, sampleOf, sampleRemark } from './assetVoucherFill'

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

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：油田 / 区块、阶段、审批与合同、资本化判断、结论等 */
export function hasH5AdditionContent(r: AdditionCheckRow): boolean {
  return [r.oilField, r.block, r.capitalizationBasis, r.explorationStage, r.developmentStage, r.approvalDoc,
    r.approvalDate, r.contractNo, r.supplier, r.paymentDate, r.voucherAttachment, r.capitalizeReason, r.conclusion]
    .some(v => String(v ?? '').trim() !== '') || r.isCapitalized
}

export function useH5AdditionCheck(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
  /** 整张底稿只读：抽凭回填 / 挂凭导入 / 撤销一律不改行 */
  isReadonly?: Ref<boolean>
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
    rows.value.push(_emptyRow(assetName))
    _persist()
  }

  function _emptyRow(assetName: string): AdditionCheckRow {
    return {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1, assetName,
      oilField: '', block: '', amount: 0,
      capitalizationBasis: '', explorationStage: '', developmentStage: '',
      approvalDoc: '', approvalDate: '', contractNo: '', supplier: '',
      paymentDate: '', voucherNo: '', voucherResult: '', voucherAttachment: '',
      isCapitalized: false, capitalizeReason: '', conclusion: '', remark: '',
    }
  }

  /**
   * 共享回填函数的待写入项 → 增加检查行（spec voucher-identity-writeback-and-audit-phase 任务 12）：资产名称取摘要，
   * 凭证号、金额（样本自己那一栏，增加在借方，红字带符号照记）。原实现把凭证号、金额作为第二个参数传给
   * 只收名称的 addRow，被丢掉，抽到的行只有摘要
   */
  function _rowFromPrepared(item: PreparedItem): AdditionCheckRow {
    const s = sampleOf(item)
    const row = _emptyRow(String(s.summary || '抽凭样本').slice(0, 80))
    row.voucherNo = String(s.voucherNo ?? '')
    row.amount = assetAmount(item, 'debit')
    row.voucherResult = '已抽凭'
    row.remark = sampleRemark(item, '高值必选')
    return row
  }

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（一个样本一行）
  const voucherFill = useVoucherCheckFill<AdditionCheckRow>({
    projectId: () => opts.projectId.value,
    tables: rows,
    policy: 'join',
    mapSampleToRow: item => _rowFromPrepared(item),
    persist: () => _persist(),
    hasUserContent: hasH5AdditionContent,
    afterChange: (_key, list) => { list.forEach((r, i) => { r.seq = i + 1 }) },
    // 旧行（没有 `_gt`）身份：凭证号 + 金额（表里没有凭证日期）
    legacy: r => assetLegacyKey(r.voucherNo, '', r.amount),
    readonly: () => opts.isReadonly?.value === true,
  })


  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0 && voucherFill.isRowLocked(rows.value[idx])) return
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof AdditionCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || voucherFill.isRowLocked(row)) return
    ;(row as any)[field] = value
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, voucherFill.guardPersist(rows.value)) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion,
    totalAmount, capitalizedCount, capitalizedAmount,
    addRow, removeRow, updateCell, saveNote, saveConclusion,
    onEngineFilled: (payload: EngineFilledPayload) => voucherFill.onEngineFilled(payload),
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: (payload: UndoRequestPayload) => voucherFill.onUndoRequest(payload),
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}
