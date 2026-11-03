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
 * - 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：一笔样本一个案件行，
 *   按分录指纹去重，行元数据 `_gt` 随行落库（spec voucher-identity-writeback-and-audit-phase 任务 13）
 *
 * 科目：2801 预计负债-未决诉讼（**贷方/负债类**）
 */
import { ref, computed, toValue, watch, type MaybeRefOrGetter, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  determineRecognition,
  type LikelihoodLevel,
  type Recognition,
} from './useK5ContingencyEngine'
import { calcSubtotal } from './useK5FormulaEngine'
import { useVoucherCheckFill, withRowMeta, type EngineFilledPayload, type FillSample, type PreparedItem } from './shared/voucherCheckFill'
import { assetAmount, assetLegacyKey, carryRowMeta, sampleOf } from './assetVoucherFill'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K5LitigationRow {
  rowId: string
  seqNo: number
  caseName: string             // 案件名称
  amount: number               // 涉案金额
  stage: string                // 诉讼阶段（一审/二审/执行/仲裁）
  lawyerOpinion: string        // 律师意见
  lossLikelihood: LikelihoodLevel | ''  // 败诉可能性级别
  estimatedLoss: number        // 应承担的赔偿支出金额（预计损失）
  bookProvision: number        // 已计提预计负债（账面）
  variance: number             // 差异金额（应承担赔偿 − 已计提，自动派生）
  varianceReason: string       // 差异原因
  recognition: Recognition | ''  // 是否确认（自动派生）
  shouldDisclose: boolean      // 是否需披露（possible→附注）
  lawyerLetterRef: string      // 律师函编号/附件路径（律师函联动）
  ocrAttachment: string        // OCR附件（行级OCR）
  voucherRef: string           // 抽凭凭证号（纯号，与平台其余底稿 voucherRef 口径一致）
  // 🔴 凭证号在真实数据中跨日重复（实测单号最多对应 83 个不同日期），只存号无法回溯
  //    是哪一张。与 voucherRef 组合才唯一定位一张凭证（同 useI5Detail 的字段模式）。
  voucherDate: string          // 抽凭凭证日期 YYYY-MM-DD
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
  /** 项目 id（抽凭回填按项目当前审计阶段标行阶段，年审阶段预审行只读） */
  projectId?: MaybeRefOrGetter<string | null | undefined>
  readonly?: MaybeRefOrGetter<boolean | undefined>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K5-6-rows'
const STAGE_OPTIONS = ['一审', '二审', '再审', '执行', '仲裁', '调解', '已结案']

function emptyLitigationRow(caseName: string): K5LitigationRow {
  return {
    rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seqNo: 1, caseName, amount: 0, stage: '', lawyerOpinion: '', lossLikelihood: '', estimatedLoss: 0,
    bookProvision: 0, variance: 0, varianceReason: '', recognition: '', shouldDisclose: false,
    lawyerLetterRef: '', ocrAttachment: '', voucherRef: '', voucherDate: '', remark: '',
  }
}

/**
 * 共享回填函数的待写入项 → 诉讼检查行：案件名称取摘要（诉讼类凭证摘要通常含案由；缺失时用凭证号占位，由审计师改写），
 * 凭证号、日期、涉案金额（样本自己那一栏的金额，红字带符号照记；原实现取借贷绝对值较大者）。
 * 败诉可能性 / 预计损失属专业判断（CAS13 三级），不由抽凭代填，备注里写明待办。
 */
export function mapPreparedToK5LitigationRow(item: PreparedItem): K5LitigationRow {
  const s = sampleOf(item) as ReturnType<typeof sampleOf> & { accountName?: string | null }
  const voucherNo = String(s.voucherNo ?? '').trim()
  const notes = [item.meta.src.includes('attach') ? '挂凭导入，待结合律师意见判断败诉可能性' : '抽凭引擎回填，待结合律师意见判断败诉可能性']
  if (s.accountName) notes.push(`科目：${s.accountName}`)
  if (s.abnormal) notes.push('引擎标记异常，待核查')
  return {
    ...emptyLitigationRow(String(s.summary ?? '').trim() || (voucherNo ? `抽凭 ${voucherNo}` : '抽凭样本')),
    amount: assetAmount(item, 'credit'),
    voucherRef: voucherNo,
    voucherDate: String(s.voucherDate ?? '').trim().slice(0, 10),
    remark: notes.join('；'),
  }
}

/** 行上已填专业判断或证据（替换与撤销抽凭时据此先确认） */
export function hasK5LitigationContent(r: K5LitigationRow): boolean {
  return [r.stage, r.lawyerOpinion, r.lossLikelihood, r.varianceReason, r.lawyerLetterRef, r.ocrAttachment]
    .some(v => String(v ?? '').trim() !== '')
    || !!Number(r.estimatedLoss) || !!Number(r.bookProvision)
}

/** 旧行（没有 `_gt`）身份：凭证号 + 凭证日期 + 涉案金额（原实现取绝对值） */
const litigationLegacy = (r: K5LitigationRow) => assetLegacyKey(r.voucherRef, r.voucherDate, r.amount)

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Litigation(params: UseK5LitigationParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const litigationRows = ref<K5LitigationRow[]>([])

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（一笔样本一个案件行）
  const voucherFill = useVoucherCheckFill<K5LitigationRow>({
    projectId: params.projectId ?? null,
    tables: litigationRows,
    mapSampleToRow: (item) => mapPreparedToK5LitigationRow(item),
    persist: () => _persist(),
    hasUserContent: hasK5LitigationContent,
    policy: 'join',
    afterChange: (_key, rows) => rows.forEach((r, i) => { r.seqNo = i + 1 }),
    legacy: litigationLegacy,
    readonly: () => Boolean(toValue(params.readonly)),
  })

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    try {
      _readRows()
    } finally {
      // 记下预审行的读入版本（年审阶段保存时据此写回）
      voucherFill.markLoaded()
    }
  }

  function _readRows(): void {
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
    return withRowMeta({
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      caseName: raw.caseName ?? '',
      amount: Number(raw.amount) || 0,
      stage: raw.stage ?? '',
      lawyerOpinion: raw.lawyerOpinion ?? '',
      lossLikelihood: likelihood,
      estimatedLoss: Number(raw.estimatedLoss) || 0,
      bookProvision: Number(raw.bookProvision) || 0,
      variance: (Number(raw.estimatedLoss) || 0) - (Number(raw.bookProvision) || 0),
      varianceReason: raw.varianceReason ?? '',
      recognition,
      shouldDisclose: recognition === 'disclose',
      lawyerLetterRef: raw.lawyerLetterRef ?? '',
      ocrAttachment: raw.ocrAttachment ?? '',
      voucherRef: raw.voucherRef ?? '',
      // 向后兼容：V166 前存的行没有该字段 → 默认空串，退化为「只有凭证号」
      voucherDate: raw.voucherDate ?? '',
      remark: raw.remark ?? '',
    }, raw)
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
    // 差异金额 = 应承担赔偿（预计损失）− 已计提预计负债
    row.variance = (row.estimatedLoss || 0) - (row.bookProvision || 0)
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
    if (!row || voucherFill.isRowLocked(row)) return
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

  /**
   * 新增诉讼行。传 ``caseName`` 时不弹 prompt（供抽凭回填等批量场景使用）。
   *
   * @returns 新建的行引用；用户取消 prompt 或名称为空时返回 ``null``
   *          —— 调用方据此判断是否继续填充该行，不要假设一定成功。
   */
  async function addRow(caseName?: string): Promise<K5LitigationRow | null> {
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
        return null
      }
    }
    if (!name) return null

    const newRow: K5LitigationRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: litigationRows.value.length + 1,
      caseName: name,
      amount: 0,
      stage: '',
      lawyerOpinion: '',
      lossLikelihood: '',
      estimatedLoss: 0,
      bookProvision: 0,
      variance: 0,
      varianceReason: '',
      recognition: '',
      shouldDisclose: false,
      lawyerLetterRef: '',
      ocrAttachment: '',
      voucherRef: '',
      voucherDate: '',
      remark: '',
    }
    litigationRows.value.push(newRow)
    _persist()
    return newRow
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= litigationRows.value.length) return
    // 年审阶段的预审行不删
    if (voucherFill.isRowLocked(litigationRows.value[idx])) return
    litigationRows.value.splice(idx, 1)
    litigationRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    // 整表替换：导入的同一笔分录带回原行的 `_gt`（导出表里没有这一列）；年审阶段预审行保存时按读入版本写回
    litigationRows.value = carryRowMeta(data.map((raw, i) => _normalizeRow(raw, i)), litigationRows.value, litigationLegacy)
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    saveResponse('6-rows', { remark: JSON.stringify(voucherFill.guardPersist(litigationRows.value)) })
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
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled: (payload: EngineFilledPayload) => voucherFill.onEngineFilled(payload),
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}
