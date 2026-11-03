/**
 * useH4DisposalCheck — H4-5 减少检查表 composable
 *
 * 对齐致同「工程物资减少检查表」：
 * 一、审计目标 → 二、样本选取 → 三、测试（原值/减值/净值/清理损益 + 核对1–5）
 * → 检查比例（勾稽 H4-2，防 #DIV/0!）→ 四、审计说明 → 五、审计结论
 *
 * 平台增强：领用出库 → H2 编号必填；关联方预埋 → H4-9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type H4DisposalCheckRow,
  type H4DisposalSamplingParams,
  type H4DisposalSummary,
  type LinkedDisposalTotal,
  normalizeDisposalRow,
  normalizeSamplingParams,
  createEmptySamplingParams,
  recalcDisposalRow,
  calcDisposalSummary,
  sumDetailDecrease,
  needsH2Ref,
  buildNoteDraft,
  buildConclusionDraft,
  normalizeDisposalMethod,
} from './h4DisposalCheckModel'
import { H45_AJE_MARKER, pushDraftPairsToH43 } from './h4AdjustmentDraftPush'
import {
  counterpartText, metaOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import { assetAmount, assetLegacyKey, fillIntoSelectedRow, sampleOf } from './assetVoucherFill'

export type {
  H4DisposalCheckRow,
  H4DisposalSamplingParams,
  H4DisposalSummary,
  LinkedDisposalTotal,
  DisposalMethod,
  DisposalReason,
} from './h4DisposalCheckModel'

export {
  DISPOSAL_METHOD_OPTS,
  DISPOSAL_REASON_OPTIONS,
  SAMPLING_METHOD_OPTS,
  H4_DISPOSAL_TEST_CONTENT_ITEMS,
  getEvidenceHint,
  calcNetValue,
  calcDisposalNetPl,
  calcCoverageRate,
  needsH2Ref,
} from './h4DisposalCheckModel'

const ROWS_KEY = 'H4-5-rows'
const DISPOSAL_TOTAL_KEY = 'H4-5-disposal-total'
const PARAMS_KEY = 'H4-5-sampling-params'
const NOTE_KEY = 'H4-5-note'
const CONCLUSION_KEY = 'H4-5-conclusion'
const DETAIL_ROWS_KEY = 'H4-2-rows'
const POP_MANUAL_KEY = 'H4-5-population-manual'

/**
 * 共享回填函数的待写入项 → H4-5 行（spec voucher-identity-writeback-and-audit-phase 任务 12）：凭证号、减少日期、
 * 对方科目（编码 名称，按后端配对，配不上「多科目」）、原值（样本自己那一栏的金额，减少在贷方，红字带符号照记），
 * 名称缺省取摘要。原实现名称取本科目名称（每行都是「工程物资」）、原值取绝对值、不写对方科目与日期，
 * 逐行抽凭还把摘要写进支持性文件。keepFilled：逐行抽凭写进已有行时，已填的名称 / 备注保留。
 */
export function applyDisposalSample(row: H4DisposalCheckRow, item: PreparedItem, keepFilled = false): void {
  const s = sampleOf(item)
  row.voucherNo = String(s.voucherNo ?? '')
  row.disposalDate = String(s.voucherDate ?? '')
  row.oppositeAccount = counterpartText(item)
  row.originalCost = assetAmount(item, 'credit')
  row.amount = row.originalCost
  row.voucherResult = '已抽凭'
  if (s.abnormal === true) row.isAbnormal = '是'
  const summary = String(s.summary ?? '').trim()
  if (!(keepFilled && row.name.trim())) row.name = (summary || '抽凭样本').slice(0, 40)
  const reason = String(s.selectionReason ?? s.remark ?? '').trim()
  if (reason && !(keepFilled && row.remark.trim())) row.remark = reason
  recalcDisposalRow(row)
}

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：减少方式、支持性文件、领料与 H2 编号、核对勾选、清理收支等 */
export function hasH4DisposalContent(r: H4DisposalCheckRow): boolean {
  return [r.category, r.disposalMethod, r.supportingDocs, r.pickingNo, r.department, r.projectName, r.approver,
    r.h2Ref, r.indexRef, r.conclusion, r.relatedPartyName, r.relationship].some(v => String(v ?? '').trim() !== '')
    || Object.values(r.checks ?? {}).some(Boolean)
    || [r.quantity, r.impairment, r.disposalCost, r.disposalIncome].some(v => Number(v) !== 0)
    || r.isRelatedParty === '是'
}

/** 旧行（没有 `_gt`）身份：凭证号 + 原值（原实现回填不写减少日期、原值取绝对值） */
const disposalLegacy = (r: H4DisposalCheckRow) => assetLegacyKey(r.voucherNo, '', r.originalCost)

export function useH4DisposalCheck(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  /** 整张底稿只读：抽凭回填 / 挂凭导入 / 撤销一律不改行 */
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, onSave } = params

  const rows = ref<H4DisposalCheckRow[]>([])
  const samplingParams = ref<H4DisposalSamplingParams>(createEmptySamplingParams())
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
      ? data.map((r, i) => withRowMeta(normalizeDisposalRow(r, i), r))
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
  const voucherFill = useVoucherCheckFill<H4DisposalCheckRow>({
    projectId: () => params.projectId.value,
    tables: rows,
    policy: 'join',
    mapSampleToRow: (item) => {
      const row = normalizeDisposalRow({ seq: 0 }, 0)
      applyDisposalSample(row, item)
      return row
    },
    persist: () => _persistRows(),
    hasUserContent: hasH4DisposalContent,
    afterChange: (_key, list) => { list.forEach((r, i) => { r.seq = i + 1 }) },
    legacy: disposalLegacy,
    readonly: () => params.isReadonly?.value === true,
  })

  watch(allResponses, () => load(), { immediate: true })

  const linkedDecrease: ComputedRef<LinkedDisposalTotal> = computed(() => {
    const data = _getJson(DETAIL_ROWS_KEY)
    return sumDetailDecrease(Array.isArray(data) ? data : [])
  })

  const summary: ComputedRef<H4DisposalSummary> = computed(() =>
    calcDisposalSummary(rows.value, samplingParams.value.populationAmount),
  )

  /** 减少合计金额（供 CrossSheet / 旧接口） */
  const disposalTotal: ComputedRef<number> = computed(() => summary.value.checkedAmount)

  const missingH2Refs: ComputedRef<H4DisposalCheckRow[]> = computed(() =>
    rows.value.filter(needsH2Ref),
  )

  const populationDrift: ComputedRef<boolean> = computed(() => {
    const linked = linkedDecrease.value
    const pop = samplingParams.value.populationAmount
    return linked.source !== '' && linked.amount > 0 && Math.abs(pop - linked.amount) > 1
  })

  function _persistRows(): void {
    if (!onSave) return
    const toPersist = voucherFill.guardPersist(rows.value).map(r => {
      recalcDisposalRow(r)
      return withRowMeta({
        rowId: r.rowId,
        seq: r.seq,
        category: r.category,
        name: r.name,
        spec: r.spec || r.category,
        voucherNo: r.voucherNo,
        disposalMethod: r.disposalMethod,
        reason: r.disposalMethod,
        oppositeAccount: r.oppositeAccount,
        quantity: r.quantity,
        originalCost: r.originalCost,
        amount: r.originalCost,
        impairment: r.impairment,
        netValue: r.netValue,
        disposalCost: r.disposalCost,
        disposalIncome: r.disposalIncome,
        disposalNetPl: r.disposalNetPl,
        disposalDate: r.disposalDate,
        supportingDocs: r.supportingDocs,
        pickingNo: r.pickingNo,
        department: r.department,
        projectName: r.projectName,
        approver: r.approver,
        h2Ref: r.h2Ref,
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
      }, r)
    })
    onSave(ROWS_KEY, toPersist)
    onSave(DISPOSAL_TOTAL_KEY, disposalTotal.value)
  }

  function _persistParams(): void {
    onSave?.(PARAMS_KEY, { ...samplingParams.value })
    onSave?.(POP_MANUAL_KEY, populationManual.value)
  }

  function addRow(name = ''): void {
    const seq = rows.value.length + 1
    rows.value.push(normalizeDisposalRow({ name: name.trim(), seq }, seq - 1))
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

    if (field === 'disposalMethod' || field === 'reason') {
      row.disposalMethod = normalizeDisposalMethod(String(value ?? ''))
      row.reason = row.disposalMethod
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

    const textFields = [
      'category', 'name', 'spec', 'voucherNo', 'oppositeAccount', 'disposalDate',
      'supportingDocs', 'pickingNo', 'department', 'projectName', 'approver',
      'h2Ref', 'indexRef', 'isAbnormal', 'conclusion', 'remark',
      'relatedPartyName', 'relationship', 'voucherResult',
    ]
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persistRows()
      return
    }

    const numFields = ['quantity', 'originalCost', 'amount', 'impairment', 'disposalCost', 'disposalIncome']
    if (numFields.includes(field)) {
      const numVal = Number(value) || 0
      if (field === 'amount') {
        row.originalCost = numVal
        row.amount = numVal
      } else {
        ;(row as any)[field] = numVal
        if (field === 'originalCost') row.amount = numVal
      }
      recalcDisposalRow(row)
      _persistRows()
      return
    }
  }

  function updateSamplingParams(patch: Partial<H4DisposalSamplingParams>): void {
    samplingParams.value = { ...samplingParams.value, ...patch }
    if (patch.populationAmount != null) populationManual.value = true
    _persistParams()
  }

  function syncPopulationFromH42(): boolean {
    const linked = linkedDecrease.value
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
   * 异常减少样本 → H4-3：借营业外支出 / 贷工程物资（按净值，无净值则用原值）
   */
  function pushAjeDraftToH43(): { ok: boolean; added: number; amount: number; message: string } {
    const targets = rows.value.filter(
      (r) => r.isAbnormal === '是' || r.isAbnormal === 'Y',
    )
    if (!targets.length) {
      return { ok: false, added: 0, amount: 0, message: '无标记异常的减少行可推送' }
    }
    const pairs = targets.map((r) => {
      const amt = Math.abs(r.netValue) > 0.01 ? Math.abs(r.netValue) : Math.abs(r.originalCost)
      const name = (r.name || '工程物资').trim()
      const method = r.disposalMethod || r.reason || '减少'
      return {
        description: `减少检查拟调整-${name}（${method}）`,
        amount: amt,
        debitCode: '5301',
        debitName: '营业外支出',
        creditCode: '1605',
        creditName: '工程物资',
        reportItemDebit: '营业外支出',
        reportItemCredit: '工程物资',
        indexRef: 'H4-5',
        marker: H45_AJE_MARKER,
      }
    }).filter((p) => p.amount >= 0.005)
    return pushDraftPairsToH43({
      allResponses: allResponses.value,
      marker: H45_AJE_MARKER,
      pairs,
      onSave,
    })
  }

  /** 行样式：缺 H2 编号 / 异常 / 核对未完 + 年审阶段预审行只读 */
  function rowClassName({ row }: { row: H4DisposalCheckRow }): string {
    const flag = needsH2Ref(row) || row.isAbnormal === '是' || row.isAbnormal === 'Y'
      ? 'row-anomaly' : (isCheckIncompleteSafe(row) ? 'row-warn' : '')
    return [flag, voucherFill.rowClass({ row })].filter(Boolean).join(' ')
  }

  /** 抽凭引擎回填（整表）：一个样本一行，按分录指纹去重；「替换本阶段抽凭行」只删本阶段抽凭填入的行 */
  function onEngineFilled(payload: EngineFilledPayload) {
    return voucherFill.onEngineFilled(payload)
  }

  /** 逐行抽凭（「抽凭」列）：第一笔写进所选行（已填的名称 / 备注保留），其余样本并入（assetVoucherFill） */
  function onEngineFilledIntoRow(payload: EngineFilledPayload, rowId: string) {
    return fillIntoSelectedRow({
      fill: voucherFill,
      rows,
      rowId,
      idOf: r => r.rowId,
      payload,
      apply: (row, item) => applyDisposalSample(row, item, true),
      persist: () => _persistRows(),
      legacy: disposalLegacy,
      readonly: () => params.isReadonly?.value === true,
    })
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
    linkedDecrease,
    summary,
    disposalTotal,
    missingH2Refs,
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
    rowClassName,
    save,
    load,
    onEngineFilled,
    onEngineFilledIntoRow,
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: (payload: UndoRequestPayload) => voucherFill.onUndoRequest(payload),
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    /** 行已关联凭证（有 `_gt`）：逐行抽凭只写未关联凭证的行 */
    rowHasVoucher: (row: H4DisposalCheckRow) => !!metaOf(row),
  }
}

function isCheckIncompleteSafe(row: H4DisposalCheckRow): boolean {
  const c = row.checks
  return !c.check1 || !c.check2 || !c.check3 || !c.check4
}

export default useH4DisposalCheck
