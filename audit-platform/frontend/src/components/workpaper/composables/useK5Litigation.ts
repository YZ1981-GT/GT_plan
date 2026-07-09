/**
 * useK5Litigation — K5-6 未决诉讼检查表逻辑
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.4
 * Requirements: 8.1-8.4
 *
 * 职责：
 * - 管理未决诉讼检查行（案件/涉案金额/诉讼阶段/律师意见/败诉可能性/预计损失/是否确认/披露）
 * - 律师函联动（律师意见字段）
 * - 败诉概率→三级可能性映射（>50%=very_likely/≤50%非极小=possible/极小=remote）
 * - 与K5-1未决诉讼行交叉验证
 * - 行级抽凭+行级OCR（律师函）
 * - Save with prefix "K5-6-"
 *
 * 科目：2701 预计负债-未决诉讼（**贷方/负债类**）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  determineRecognition,
  type LikelihoodLevel,
  type Recognition,
} from './useK5ContingencyEngine'
import { calcSubtotal } from './useK5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K5LitigationRow {
  rowId: string
  seqNo: number
  caseName: string             // 案件名称
  amount: number               // 涉案金额
  stage: string                // 诉讼阶段（一审/二审/执行/仲裁）
  lawyerOpinion: string        // 律师意见
  lossLikelihood: LikelihoodLevel | ''  // 败诉可能性级别
  estimatedLoss: number        // 预计损失金额
  recognition: Recognition | ''  // 是否确认（自动派生）
  shouldDisclose: boolean      // 是否需披露（possible→附注）
  lawyerLetterRef: string      // 律师函编号/附件路径（律师函联动）
  ocrAttachment: string        // OCR附件（行级OCR）
  voucherRef: string           // 抽凭凭证号
  remark: string
}

export interface K5LitigationSubtotals {
  totalAmount: number
  totalEstimatedLoss: number
  recognizedLoss: number
  disclosedLoss: number
  count: number
}

export interface K5LitigationCrossCheck {
  /** K5-6 已确认预计损失合计 */
  litigationTotal: number
  /** K5-1 未决诉讼行审定数 */
  adjudicationLitigation: number
  /** 差异 */
  diff: number
  /** 是否一致 */
  isMatch: boolean
}

export interface UseK5LitigationParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K5-6-rows'
const STAGE_OPTIONS = ['一审', '二审', '再审', '执行', '仲裁', '调解', '已结案']

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Litigation(params: UseK5LitigationParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const litigationRows = ref<K5LitigationRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { litigationRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        litigationRows.value = parsed.map(_normalizeRow)
      } else {
        litigationRows.value = []
      }
    } catch {
      litigationRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K5LitigationRow {
    const likelihood = raw.lossLikelihood || ''
    const recognition = likelihood ? determineRecognition(likelihood as LikelihoodLevel) : ''
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      caseName: raw.caseName ?? '',
      amount: Number(raw.amount) || 0,
      stage: raw.stage ?? '',
      lawyerOpinion: raw.lawyerOpinion ?? '',
      lossLikelihood: likelihood,
      estimatedLoss: Number(raw.estimatedLoss) || 0,
      recognition,
      shouldDisclose: recognition === 'disclose',
      lawyerLetterRef: raw.lawyerLetterRef ?? '',
      ocrAttachment: raw.ocrAttachment ?? '',
      voucherRef: raw.voucherRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K5LitigationRow): void {
    // 三级可能性→确认决策
    if (row.lossLikelihood) {
      row.recognition = determineRecognition(row.lossLikelihood as LikelihoodLevel)
      row.shouldDisclose = row.recognition === 'disclose'
    } else {
      row.recognition = ''
      row.shouldDisclose = false
    }
  }

  function recalcAll(): void {
    for (const row of litigationRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K5LitigationSubtotals> = computed(() => {
    const r = litigationRows.value
    const recognized = r.filter(x => x.recognition === 'recognize')
    const disclosed = r.filter(x => x.recognition === 'disclose')
    return {
      totalAmount: calcSubtotal(r.map(x => x.amount)),
      totalEstimatedLoss: calcSubtotal(r.map(x => x.estimatedLoss)),
      recognizedLoss: calcSubtotal(recognized.map(x => x.estimatedLoss)),
      disclosedLoss: calcSubtotal(disclosed.map(x => x.estimatedLoss)),
      count: r.length,
    }
  })

  // ─── 与K5-1交叉验证 (Req 8.2) ─────────────────────────────────────────────

  const crossCheck: ComputedRef<K5LitigationCrossCheck> = computed(() => {
    const litigationTotal = subtotals.value.recognizedLoss
    // 从 allResponses 获取K5-1未决诉讼行审定数（row index=1）
    const adjItem = allResponses.value.get('K5-1-r1-audited') ?? allResponses.value.get('K5-1-litigation-audited')
    const adjVal = Number(adjItem?.remark ?? adjItem?.conclusion ?? 0) || 0
    const diff = litigationTotal - adjVal
    return {
      litigationTotal,
      adjudicationLitigation: adjVal,
      diff,
      isMatch: Math.abs(diff) < 0.01,
    }
  })

  // ─── 需披露的或有负债列表（possible → 附注） ───────────────────────────────

  const disclosureItems = computed(() => {
    return litigationRows.value.filter(r => r.shouldDisclose)
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = litigationRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── 律师函联动（设置律师函引用） ──────────────────────────────────────────

  function setLawyerLetterRef(rowId: string, ref: string): void {
    const row = litigationRows.value.find(r => r.rowId === rowId)
    if (row) {
      row.lawyerLetterRef = ref
      _persist()
    }
  }

  /** 行级OCR：设置OCR附件路径 */
  function setOcrAttachment(rowId: string, path: string): void {
    const row = litigationRows.value.find(r => r.rowId === rowId)
    if (row) {
      row.ocrAttachment = path
      _persist()
    }
  }

  /** 行级抽凭：设置凭证号 */
  function setVoucherRef(rowId: string, voucherRef: string): void {
    const row = litigationRows.value.find(r => r.rowId === rowId)
    if (row) {
      row.voucherRef = voucherRef
      _persist()
    }
  }

  // ─── Dynamic Row Add ───────────────────────────────────────────────────────

  async function addRow(caseName?: string): Promise<void> {
    let name = caseName
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入诉讼案件名称',
          '新增未决诉讼',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX公司诉XX合同纠纷案',
            inputValidator: (val) => (!val?.trim() ? '案件名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return
      }
    }
    if (!name) return

    const newRow: K5LitigationRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: litigationRows.value.length + 1,
      caseName: name,
      amount: 0,
      stage: '',
      lawyerOpinion: '',
      lossLikelihood: '',
      estimatedLoss: 0,
      recognition: '',
      shouldDisclose: false,
      lawyerLetterRef: '',
      ocrAttachment: '',
      voucherRef: '',
      remark: '',
    }
    litigationRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= litigationRows.value.length) return
    litigationRows.value.splice(idx, 1)
    litigationRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    litigationRows.value = data.map((raw, i) => _normalizeRow(raw, i))
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    saveResponse('6-rows', { remark: JSON.stringify(litigationRows.value) })
    saveResponse('6-litigation-total', { remark: String(subtotals.value.recognizedLoss) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    litigationRows,
    subtotals,
    crossCheck,
    disclosureItems,
    stageOptions: STAGE_OPTIONS,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    setLawyerLetterRef,
    setOcrAttachment,
    setVoucherRef,
  }
}
