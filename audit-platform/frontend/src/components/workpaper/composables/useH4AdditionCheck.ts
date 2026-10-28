/**
 * useH4AdditionCheck — H4-4 增加检查表 composable
 *
 * 对齐致同「工程物资增加检查表」：
 * 一、审计目标 → 二、样本选取 → 三、测试（记账凭证 + 核对1–5）
 * → 检查比例（勾稽 H4-2，防 #DIV/0!）→ 四、审计说明 → 五、审计结论
 *
 * 平台增强：发票三方差异；关联方预埋 → H4-9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type H4AdditionCheckRow,
  type H4AdditionSamplingParams,
  type H4AdditionSummary,
  type LinkedAdditionTotal,
  normalizeAdditionRow,
  normalizeSamplingParams,
  createEmptySamplingParams,
  recalcAdditionRow,
  calcAdditionSummary,
  sumDetailIncrease,
  buildNoteDraft,
  buildConclusionDraft,
  isCheckIncomplete,
} from './h4AdditionCheckModel'
import { H44_AJE_MARKER, pushDraftPairsToH43 } from './h4AdjustmentDraftPush'
import {
  type H4AdditionSamplePatch,
  mapPreparedToAdditionPatch,
  applyAdditionSamplePatch,
  applyOcrPatchToAdditionRow,
  mapOcrToAdditionPatch,
  extractOcrFields,
} from './h4AdditionSampleFill'
import {
  metaOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import { assetLegacyKey, fillIntoSelectedRow } from './assetVoucherFill'

export type {
  H4AdditionCheckRow,
  H4AdditionSamplingParams,
  H4AdditionSummary,
  LinkedAdditionTotal,
} from './h4AdditionCheckModel'

export {
  SAMPLING_METHOD_OPTS,
  H4_ADDITION_TEST_CONTENT_ITEMS,
  calcInvoiceDiff,
  calcCoverageRate,
  isCheckIncomplete,
} from './h4AdditionCheckModel'

const ROWS_KEY = 'H4-4-rows'
const ADDITION_TOTAL_KEY = 'H4-4-addition-total'
const PARAMS_KEY = 'H4-4-sampling-params'
const NOTE_KEY = 'H4-4-note'
const CONCLUSION_KEY = 'H4-4-conclusion'
const DETAIL_ROWS_KEY = 'H4-2-rows'
const POP_MANUAL_KEY = 'H4-4-population-manual'

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：类别、支持性文件、供应商与单据、核对勾选、关联方、结论等 */
export function hasH4AdditionContent(r: H4AdditionCheckRow): boolean {
  return [r.category, r.supportingDocs, r.supplier, r.contractNo, r.inboundNo, r.invoiceNo, r.inspector,
    r.indexRef, r.conclusion, r.relatedPartyName, r.relationship].some(v => String(v ?? '').trim() !== '')
    || Object.values(r.checks ?? {}).some(Boolean)
    || Number(r.invoiceAmount) !== 0 || r.hasAttachment || r.isRelatedParty === '是'
}

/** 旧行（没有 `_gt`）身份：凭证号 + 凭证日期 + 借方金额（原实现取绝对值） */
const additionLegacy = (r: H4AdditionCheckRow) => assetLegacyKey(r.voucherNo, r.voucherDate, r.amount)

export function useH4AdditionCheck(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  /** 整张底稿只读：抽凭回填 / 挂凭导入 / 撤销一律不改行 */
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, onSave } = params

  const rows = ref<H4AdditionCheckRow[]>([])
  const samplingParams = ref<H4AdditionSamplingParams>(createEmptySamplingParams())
  const populationManual = ref(false)
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    if (!item) return ''
    const raw = item.remark ?? item.conclusion
    if (raw == null) return ''
    if (typeof raw === 'string') {
      try {
        const p = JSON.parse(raw)
        return typeof p === 'string' ? p : raw
      } catch {
        return raw
      }
    }
    return String(raw)
  }

  function load(): void {
    const data = _getJson(ROWS_KEY)
    rows.value = Array.isArray(data) && data.length > 0
      ? data.map((r, i) => withRowMeta(normalizeAdditionRow(r, i), r))
      : []
    voucherFill.markLoaded()

    const sp = _getJson(PARAMS_KEY)
    samplingParams.value = normalizeSamplingParams(sp)

    const manual = _getJson(POP_MANUAL_KEY)
    populationManual.value = manual === true || manual === 'true'

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（一个样本一行，对方科目按配对拼接）
  const voucherFill = useVoucherCheckFill<H4AdditionCheckRow>({
    projectId: () => params.projectId.value,
    tables: rows,
    policy: 'join',
    mapSampleToRow: (item) => {
      const row = normalizeAdditionRow({ seq: 0 }, 0)
      applyAdditionSamplePatch(row, mapPreparedToAdditionPatch(item), { skipNameIfFilled: false })
      if (!row.name) row.name = '抽凭样本'
      recalcAdditionRow(row)
      return row
    },
    persist: () => _persistRows(),
    hasUserContent: hasH4AdditionContent,
    afterChange: (_key, list) => { list.forEach((r, i) => { r.seq = i + 1 }) },
    legacy: additionLegacy,
    readonly: () => params.isReadonly?.value === true,
  })

  watch(allResponses, () => load(), { immediate: true })

  const linkedIncrease: ComputedRef<LinkedAdditionTotal> = computed(() => {
    const data = _getJson(DETAIL_ROWS_KEY)
    return sumDetailIncrease(Array.isArray(data) ? data : [])
  })

  const summary: ComputedRef<H4AdditionSummary> = computed(() =>
    calcAdditionSummary(rows.value, samplingParams.value.populationAmount),
  )

  /** 增加合计金额（供 CrossSheet / 旧接口） */
  const additionTotal: ComputedRef<number> = computed(() => summary.value.checkedAmount)

  /** @deprecated 兼容旧 stats 接口 */
  const stats = computed(() => ({
    checkedCount: summary.value.checkedCount,
    totalAmount: summary.value.checkedAmount,
    diffCount: summary.value.diffCount,
  }))

  const populationDrift: ComputedRef<boolean> = computed(() => {
    const linked = linkedIncrease.value
    const pop = samplingParams.value.populationAmount
    return linked.source !== '' && linked.amount > 0 && Math.abs(pop - linked.amount) > 1
  })

  function _persistRows(): void {
    if (!onSave) return
    const toPersist = voucherFill.guardPersist(rows.value).map(r => {
      recalcAdditionRow(r)
      return withRowMeta({
        rowId: r.rowId,
        seq: r.seq,
        category: r.category,
        name: r.name,
        spec: r.spec || r.category,
        voucherDate: r.voucherDate,
        voucherNo: r.voucherNo,
        businessContent: r.businessContent,
        oppositeAccount: r.oppositeAccount,
        oppositeDetail: r.oppositeDetail,
        amount: r.amount,
        supportingDocs: r.supportingDocs,
        supplier: r.supplier,
        contractNo: r.contractNo,
        inboundDate: r.inboundDate || r.voucherDate,
        inboundNo: r.inboundNo,
        invoiceNo: r.invoiceNo,
        invoiceAmount: r.invoiceAmount,
        inspector: r.inspector,
        checks: { ...r.checks },
        check1: r.checks.check1,
        check2: r.checks.check2,
        check3: r.checks.check3,
        check4: r.checks.check4,
        check5: r.checks.check5,
        indexRef: r.indexRef,
        refIndex: r.indexRef,
        isAbnormal: r.isAbnormal,
        conclusion: r.conclusion,
        remark: r.remark,
        isRelatedParty: r.isRelatedParty,
        relatedPartyName: r.relatedPartyName,
        relationship: r.relationship,
        voucherResult: r.voucherResult,
        hasAttachment: r.hasAttachment,
      }, r)
    })
    onSave(ROWS_KEY, toPersist)
    onSave(ADDITION_TOTAL_KEY, additionTotal.value)
  }

  function _persistParams(): void {
    onSave?.(PARAMS_KEY, { ...samplingParams.value })
    onSave?.(POP_MANUAL_KEY, populationManual.value)
  }

  function addRow(name = ''): void {
    const seq = rows.value.length + 1
    rows.value.push(normalizeAdditionRow({ name: name.trim(), seq }, seq - 1))
    _persistRows()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1 || voucherFill.isRowLocked(rows.value[idx])) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || voucherFill.isRowLocked(row)) return

    if (field.startsWith('checks.')) {
      const key = field.split('.')[1] as keyof typeof row.checks
      row.checks[key] = Boolean(value)
      _persistRows()
      return
    }

    if (field === 'isRelatedParty') {
      row.isRelatedParty = String(value ?? '')
      if (value !== '是') {
        row.relatedPartyName = ''
        row.relationship = ''
      }
      _persistRows()
      return
    }

    if (field === 'hasAttachment') {
      row.hasAttachment = !!value
      _persistRows()
      return
    }

    const textFields = [
      'category', 'name', 'spec', 'voucherDate', 'voucherNo', 'businessContent',
      'oppositeAccount', 'oppositeDetail', 'supportingDocs', 'supplier', 'contractNo',
      'inboundDate', 'inboundNo', 'invoiceNo', 'inspector', 'indexRef', 'isAbnormal',
      'conclusion', 'remark', 'relatedPartyName', 'relationship', 'voucherResult',
    ]
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      if (field === 'indexRef') row.refIndex = row.indexRef
      if (field === 'voucherDate' && !row.inboundDate) row.inboundDate = row.voucherDate
      if (field === 'category' && !row.spec) row.spec = row.category
      _persistRows()
      return
    }

    const numFields = ['amount', 'invoiceAmount', 'quantity', 'unitPrice']
    if (numFields.includes(field)) {
      if (field === 'quantity' || field === 'unitPrice') {
        // 旧字段兼容：忽略或仅落库不展示
        ;(row as any)[field] = Number(value) || 0
        _persistRows()
        return
      }
      ;(row as any)[field] = Number(value) || 0
      recalcAdditionRow(row)
      _persistRows()
      return
    }
  }

  function updateSamplingParams(patch: Partial<H4AdditionSamplingParams>): void {
    samplingParams.value = { ...samplingParams.value, ...patch }
    if (patch.populationAmount != null) populationManual.value = true
    _persistParams()
  }

  function syncPopulationFromH42(): boolean {
    const linked = linkedIncrease.value
    if (!(linked.amount > 0)) return false
    samplingParams.value = {
      ...samplingParams.value,
      populationAmount: linked.amount,
    }
    populationManual.value = false
    _persistParams()
    return true
  }

  function saveNote(val: string): void {
    auditNote.value = val
    onSave?.(NOTE_KEY, val)
  }

  function saveConclusion(val: string): void {
    auditConclusion.value = val
    onSave?.(CONCLUSION_KEY, val)
  }

  function draftNote(): void {
    saveNote(buildNoteDraft(summary.value, samplingParams.value.populationAmount))
  }

  function draftConclusion(): void {
    saveConclusion(buildConclusionDraft(summary.value))
  }

  /**
   * 将异常/三方差异样本推送借贷成对草稿至 H4-3（幂等替换 H4-4-aje-auto）
   * 差异>0（入账>发票）：贷工程物资 / 借应付；差异<0：借工程物资 / 贷应付
   */
  function pushAjeDraftToH43(): { ok: boolean; added: number; amount: number; message: string } {
    const targets = rows.value.filter((r) => {
      const abn = r.isAbnormal === '是' || r.isAbnormal === 'Y'
      const hasDiff = Math.abs(r.diff) > 0.01 && r.invoiceAmount > 0
      return abn || hasDiff
    })
    if (!targets.length) {
      return { ok: false, added: 0, amount: 0, message: '无异常或发票差异行可推送' }
    }
    const pairs = targets.map((r) => {
      const amt = Math.abs(r.diff) > 0.01 ? Math.abs(r.diff) : Math.abs(r.amount)
      const overstated = r.diff > 0.01 || (Math.abs(r.diff) < 0.01 && (r.isAbnormal === '是' || r.isAbnormal === 'Y'))
      const name = (r.name || '工程物资').trim()
      const desc = `增加检查拟调整-${name}${r.diff ? `（差异${r.diff}）` : ''}`
      if (overstated) {
        return {
          description: desc,
          amount: amt,
          debitCode: '2202',
          debitName: '应付账款',
          creditCode: '1605',
          creditName: '工程物资',
          reportItemDebit: '应付账款',
          reportItemCredit: '工程物资',
          indexRef: 'H4-4',
          marker: H44_AJE_MARKER,
        }
      }
      return {
        description: desc,
        amount: amt,
        debitCode: '1605',
        debitName: '工程物资',
        creditCode: '2202',
        creditName: '应付账款',
        reportItemDebit: '工程物资',
        reportItemCredit: '应付账款',
        indexRef: 'H4-4',
        marker: H44_AJE_MARKER,
      }
    })
    return pushDraftPairsToH43({
      allResponses: allResponses.value,
      marker: H44_AJE_MARKER,
      pairs,
      onSave,
    })
  }

  /** 抽凭引擎回填（整表）：一个样本一行，按分录指纹去重；「替换本阶段抽凭行」只删本阶段抽凭填入的行 */
  function onEngineFilled(payload: EngineFilledPayload) {
    return voucherFill.onEngineFilled(payload)
  }

  /** 逐行抽凭（「抽凭」列）：第一笔写进所选行（已填的物资名称保留），其余样本并入（assetVoucherFill） */
  function onEngineFilledIntoRow(payload: EngineFilledPayload, rowId: string) {
    return fillIntoSelectedRow({
      fill: voucherFill,
      rows,
      rowId,
      idOf: r => r.rowId,
      payload,
      apply: (row, item) => {
        applyAdditionSamplePatch(row, mapPreparedToAdditionPatch(item), { skipNameIfFilled: true })
        recalcAdditionRow(row)
      },
      persist: () => _persistRows(),
      legacy: additionLegacy,
      readonly: () => params.isReadonly?.value === true,
    })
  }

  /** OCR 字段填入：支持性文件合并；供应商/发票等仅填空 */
  function mergeOcrResult(rowId: string, fields: Record<string, unknown>): H4AdditionSamplePatch {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || voucherFill.isRowLocked(row)) return {}
    const { patch } = mapOcrToAdditionPatch(fields)
    applyOcrPatchToAdditionRow(row, patch)
    recalcAdditionRow(row)
    _persistRows()
    return patch
  }

  /** 行样式：异常 / 发票差异 / 核对未完 + 年审阶段预审行只读 */
  function rowClassName({ row }: { row: H4AdditionCheckRow }): string {
    return [flagClassName(row), voucherFill.rowClass({ row })].filter(Boolean).join(' ')
  }

  function flagClassName(row: H4AdditionCheckRow): string {
    if (row.isAbnormal === '是' || row.isAbnormal === 'Y') return 'row-anomaly'
    if (Math.abs(row.diff) > 0.01 && row.invoiceAmount > 0) return 'row-anomaly'
    if (isCheckIncomplete(row)) return 'row-warn'
    return ''
  }

  function save(): void {
    _persistRows()
    _persistParams()
  }

  return {
    rows,
    samplingParams,
    populationManual,
    auditNote,
    auditConclusion,
    linkedIncrease,
    summary,
    stats,
    additionTotal,
    populationDrift,
    addRow,
    deleteRow,
    updateCell,
    updateSamplingParams,
    syncPopulationFromH42,
    saveNote,
    saveConclusion,
    draftNote,
    draftConclusion,
    pushAjeDraftToH43,
    onEngineFilled,
    onEngineFilledIntoRow,
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: (payload: UndoRequestPayload) => voucherFill.onUndoRequest(payload),
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    /** 行已关联凭证（有 `_gt`）：逐行抽凭只写未关联凭证的行 */
    rowHasVoucher: (row: H4AdditionCheckRow) => !!metaOf(row),
    mergeOcrResult,
    rowClassName,
    save,
    load,
  }
}

export {
  mapPreparedToAdditionPatch,
  mapOcrToAdditionPatch,
  extractOcrFields,
  mergeSupportingDocs,
} from './h4AdditionSampleFill'

export type { H4AdditionSamplePatch } from './h4AdditionSampleFill'

export default useH4AdditionCheck
