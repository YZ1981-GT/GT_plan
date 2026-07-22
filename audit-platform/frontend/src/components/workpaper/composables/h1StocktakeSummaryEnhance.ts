/**
 * H1-11 监盘小结 — 增强逻辑（实时联动/闸门/起草/推送/导出）
 */
import {
  calcRecountRates,
  draftLocationsFromCheckRows,
  draftRecountFromCheckRows,
  isTimeRangeValid,
  type H1StocktakeSummaryForm,
} from './h1StocktakeSummaryModel'

export const AUTO_SYNC_FIELDS = [
  'recountTotalUnits',
  'recountSampleUnits',
  'recountCorrectUnits',
  'recountTotalAmount',
  'recountSampleAmount',
  'recountCorrectAmount',
  'locations',
  'actualDate',
  'samplingMethod',
] as const

export type AutoSyncField = (typeof AUTO_SYNC_FIELDS)[number]

export interface CompletenessItem {
  id: string
  label: string
  ok: boolean
  hint: string
}

export interface SamplePlanGap {
  plannedSamples: number
  actualChecked: number
  gap: number
  ok: boolean
  message: string
}

export interface DiffEvidenceRow {
  rowId: string
  name: string
  assetNo: string
  result: string
  diffAmount: number
  diffReason: string
  actualStatus: string
  photoUrl: string
  suggestion: string
}

export interface StocktakeConcernItem {
  source: 'H1-11'
  assetName: string
  assetNo: string
  reason: string
  bookNetValue: number
  suggest: 'idle' | 'impairment' | 'both'
  checkRowId: string
}

/** 可自动回填的复盘字段（尊重 manualOverrides） */
export function applyAutoSyncPatch(
  form: H1StocktakeSummaryForm,
  patch: Partial<H1StocktakeSummaryForm>,
  overrides: string[],
): string[] {
  const applied: string[] = []
  const ov = new Set(overrides)
  for (const [k, v] of Object.entries(patch)) {
    if (ov.has(k)) continue
    if (v === undefined) continue
    const cur = (form as any)[k]
    if (k === 'locations') {
      if (!Array.isArray(cur) || cur.length === 0) {
        ;(form as any)[k] = v
        applied.push(k)
      }
      continue
    }
    if (cur == null || cur === '' || cur === 0) {
      ;(form as any)[k] = v
      applied.push(k)
    }
  }
  return applied
}

export function buildAutoSyncPatch(ctx: {
  planDate: string
  planMethod: string
  planParticipants: string
  planLocation: string
  checkRows: { name: string; location: string; result: string; bookNetValue: number; bookCost: number }[]
}): Partial<H1StocktakeSummaryForm> {
  const recount = draftRecountFromCheckRows(ctx.checkRows)
  const locations = draftLocationsFromCheckRows(ctx.checkRows)
  const patch: Partial<H1StocktakeSummaryForm> = { ...recount, recountIndex: 'H1-10' }
  if (ctx.planDate) patch.actualDate = ctx.planDate
  if (ctx.planMethod) {
    patch.samplingMethod = `按监盘计划（H1-9）采用${ctx.planMethod}；从账面至实物、从实物至账面双向抽查。`
  }
  if (locations.length) patch.locations = locations
  return patch
}

export function fingerprintCheckRows(
  rows: { rowId: string; result: string; diffAmount: number; actualStatus: string; bookNetValue: number }[],
): string {
  return rows.map((r) => `${r.rowId}:${r.result}:${r.diffAmount}:${r.actualStatus}:${r.bookNetValue}`).join('|')
}

export function buildDiffEvidence(
  rows: {
    rowId: string
    name: string
    assetNo: string
    result: string
    diffAmount: number
    diffReason: string
    actualStatus: string
    photoUrl: string
    suggestion: string
  }[],
): DiffEvidenceRow[] {
  return rows
    .filter((r) => r.result === '盘盈' || r.result === '盘亏' || r.actualStatus === '闲置' || r.actualStatus === '报废')
    .map((r) => ({
      rowId: r.rowId,
      name: r.name,
      assetNo: r.assetNo,
      result: r.result || r.actualStatus,
      diffAmount: r.diffAmount,
      diffReason: r.diffReason,
      actualStatus: r.actualStatus,
      photoUrl: r.photoUrl,
      suggestion: r.suggestion,
    }))
}

export function mergeDiffIntoAbnormal(existing: string, diffs: DiffEvidenceRow[]): string {
  if (!diffs.length) return existing
  const block = [
    '【自 H1-10 同步的差异/异常】',
    ...diffs.map((d) => {
      const photo = d.photoUrl ? ` 照片:${d.photoUrl}` : ''
      return `- ${d.name}(${d.assetNo || '无编号'}) ${d.result} 差额${d.diffAmount || 0} 原因:${d.diffReason || '未填'}${photo}`
    }),
  ].join('\n')
  if (!existing.trim()) return block
  const re = /【自 H1-10 同步的差异\/异常】[^\n]*(?:\n-[^\n]*)*/
  if (re.test(existing)) {
    return existing.replace(re, block).replace(/\n{3,}/g, '\n\n').trim()
  }
  return `${existing.trim()}\n\n${block}`
}

export function calcSamplePlanGap(
  sampleSelections: { sampleSize: number }[],
  actualChecked: number,
): SamplePlanGap {
  const plannedSamples = sampleSelections.reduce((s, r) => s + (Number(r.sampleSize) || 0), 0)
  const gap = plannedSamples - actualChecked
  const ok = plannedSamples <= 0 || actualChecked >= plannedSamples
  return {
    plannedSamples,
    actualChecked,
    gap,
    ok,
    message: plannedSamples <= 0
      ? 'H1-9 未填计划样本量'
      : ok
        ? `实盘 ${actualChecked} ≥ 计划 ${plannedSamples}`
        : `实盘 ${actualChecked} 低于计划样本量 ${plannedSamples}（差 ${gap}）`,
  }
}

export function evaluateCompleteness(ctx: {
  form: H1StocktakeSummaryForm
  matchRate: number
  deficitRows: { diffReason: string }[]
  checkTotal: number
}): CompletenessItem[] {
  const f = ctx.form
  const preOk = f.precheckItems.every((p) => !!p.obtained)
  const timeOk = !!(f.actualDate && f.startTime && f.endTime && isTimeRangeValid(f.startTime, f.endTime))
  const deficitOk = ctx.deficitRows.every((r) => !!(r.diffReason || '').trim())
  const recountOk = !!(f.recountIndex || '').trim()
  const conclusionOk = (f.conclusion || '').trim().length >= 20
  const signOk = !!(f.preparedBy && f.preparedDate)
  const matchOk = ctx.checkTotal === 0 || ctx.matchRate >= 95 || !!(f.abnormalNote || '').trim()
  const docsOk = f.diffExplanationObtained !== '' && f.sampleTableObtained !== ''

  return [
    { id: 'precheck', label: '盘前检查程序已勾选', ok: preOk, hint: '第五节四项均需选择是/否/不适用' },
    { id: 'time', label: '实际盘点时间完整合法', ok: timeOk, hint: '日期+起止时间，且结束晚于开始' },
    { id: 'deficit', label: '盘亏均有差异原因', ok: deficitOk, hint: '回 H1-10 补全盘亏原因' },
    { id: 'recount', label: '复盘索引已填', ok: recountOk, hint: '通常为 H1-10' },
    { id: 'match', label: '相符率达标或已披露异常', ok: matchOk, hint: '相符率<95%须在异常说明中披露' },
    { id: 'docs', label: '结束工作资料勾选', ok: docsOk, hint: '差异说明/复盘抽查表是否取得' },
    { id: 'conclusion', label: '结论不少于20字', ok: conclusionOk, hint: '可使用「起草结论」' },
    { id: 'sign', label: '监盘人签字与日期', ok: signOk, hint: '结论区签署' },
  ]
}

export function draftConclusionRule(ctx: {
  total: number
  matchCount: number
  matchRate: number
  surplusCount: number
  deficitCount: number
  surplusAmount: number
  deficitAmount: number
  form: H1StocktakeSummaryForm
  sampleGap: SamplePlanGap
}): string {
  const rates = calcRecountRates(ctx.form)
  const lines = [
    `本次固定资产监盘于 ${ctx.form.actualDate || '____'} 实施，共检查 ${ctx.total} 项。`,
    `账实相符 ${ctx.matchCount} 项，相符率 ${ctx.matchRate.toFixed(1)}%；盘盈 ${ctx.surplusCount} 项（金额约 ${ctx.surplusAmount.toFixed(2)} 元），盘亏 ${ctx.deficitCount} 项（金额约 ${ctx.deficitAmount.toFixed(2)} 元）。`,
  ]
  if (ctx.sampleGap.plannedSamples > 0) {
    lines.push(`与监盘计划（H1-9）对照：${ctx.sampleGap.message}。`)
  }
  if (rates.unitCoverage != null) {
    lines.push(`复盘数量覆盖率 ${rates.unitCoverage}%，数量正确率 ${rates.unitAccuracy ?? '—'}%；金额覆盖率 ${rates.amountCoverage ?? '—'}%，金额正确率 ${rates.amountAccuracy ?? '—'}%。`)
  }
  if (ctx.form.abnormalNote?.trim()) {
    lines.push(`异常情况已记录：${ctx.form.abnormalNote.trim().slice(0, 120)}${ctx.form.abnormalNote.length > 120 ? '…' : ''}`)
  }
  if (ctx.matchRate < 95 || ctx.deficitCount > 0) {
    lines.push('账实差异或盘亏事项需进一步追查并评估对固定资产余额真实性的影响；必要时建议调整或披露。')
  } else {
    lines.push('未发现重大账实不符；监盘程序执行充分，固定资产存在性认定可获合理保证。')
  }
  lines.push('详见 H1-9 监盘计划、H1-10 盘点检查表及本小结各节。')
  return lines.join('\n')
}

export function collectConcernsFromCheck(
  rows: {
    rowId: string
    name: string
    assetNo: string
    actualStatus: string
    qualityStatus?: string
    result: string
    bookNetValue: number
    bookCost: number
    bookAmount?: number
    diffReason: string
    suggestion: string
  }[],
): StocktakeConcernItem[] {
  const out: StocktakeConcernItem[] = []
  for (const r of rows) {
    const status = r.qualityStatus || r.actualStatus || ''
    const idle = status === '闲置'
    const scrap = status === '报废' || status === '待报废' || status === '毁损'
    const deficit = r.result === '盘亏'
    if (!idle && !scrap && !deficit) continue
    let suggest: StocktakeConcernItem['suggest'] = 'impairment'
    if (idle && !scrap && !deficit) suggest = 'idle'
    if (idle && (scrap || deficit)) suggest = 'both'
    out.push({
      source: 'H1-11',
      assetName: r.name,
      assetNo: r.assetNo,
      reason: [status, r.result, r.diffReason, r.suggestion].filter(Boolean).join(' / '),
      bookNetValue: Number(r.bookNetValue) || Number(r.bookAmount) || Number(r.bookCost) || 0,
      suggest,
      checkRowId: r.rowId,
    })
  }
  return out
}

/** 合并推送到 H1-4 闲置行（按名称+编号去重） */
export function mergeIdleRowsFromConcerns(
  existing: any[],
  concerns: StocktakeConcernItem[],
  checkRows: { rowId: string; name: string; assetNo: string; bookCost: number; bookNetValue: number }[],
): { rows: any[]; added: number } {
  const list = Array.isArray(existing) ? [...existing] : []
  let added = 0
  const targets = concerns.filter((c) => c.suggest === 'idle' || c.suggest === 'both')
  for (const c of targets) {
    const hit = list.find(
      (r) => (c.assetNo && r.assetNo === c.assetNo) || (r.name === c.assetName && c.assetName),
    )
    if (hit) {
      if (!hit.idleReason) hit.idleReason = c.reason
      if (!hit.remark) hit.remark = `来源:H1-11/${c.checkRowId}`
      continue
    }
    const src = checkRows.find((r) => r.rowId === c.checkRowId)
    list.push({
      rowId: `idle-from-h111-${c.checkRowId}`,
      seq: list.length + 1,
      idleType: 'unused',
      category: '',
      name: c.assetName,
      assetNo: c.assetNo,
      originalCost: src?.bookCost || 0,
      accDep: Math.max(0, (src?.bookCost || 0) - (src?.bookNetValue || 0)),
      impairmentProvision: 0,
      netValue: c.bookNetValue,
      idleReason: c.reason || '监盘发现闲置/报废',
      idleStartDate: '',
      idleEndDate: '',
      condition: /报废|毁损/.test(c.reason || '') ? '待报废' : '',
      depContinued: '',
      hasImpairment: c.suggest === 'both' || c.suggest === 'impairment' ? 'Y' : 'N',
      impairmentAmount: 0,
      periodDepProvision: 0,
      disposalSuggestion: c.suggest === 'impairment' || c.suggest === 'both' ? 'dispose' : 'idle',
      remark: `来源:H1-11/${c.checkRowId}`,
    })
    added += 1
  }
  return { rows: list.map((r, i) => ({ ...r, seq: i + 1 })), added }
}

/** 权证 OCR → H1-16 行（匹配或新增） */
export function mergeBuildingFromOcr(existing: any[], ocr: Record<string, any>): { rows: any[]; mode: 'update' | 'add' } {
  const list = Array.isArray(existing) ? [...existing] : []
  const cert = String(ocr.titleCertNo || '').trim()
  const addr = String(ocr.address || ocr.storageLocation || '').trim()
  const name = String(ocr.assetName || addr || cert || '监盘OCR房屋').trim()
  let row = list.find((r) => (cert && r.titleCertNo === cert) || (addr && r.address === addr))
  const mode: 'update' | 'add' = row ? 'update' : 'add'
  if (!row) {
    row = {
      rowId: `bld-h111-${Date.now().toString(36)}`,
      seq: list.length + 1,
      assetCode: '',
      name,
      bookValue: 0, accumDep: 0, impairment: 0, netValue: 0,
      titleCertNo: '', owner: '', coOwnership: '', address: '',
      issueDate: '', propertyNature: '', usage: '',
      buildingArea: 0, landArea: 0, usefulLife: '',
      issuingAuthority: '', otherRights: '', certCopyIndex: '',
      isOwnerEntity: 'Y',
      isMortgaged: 'N', mortgageArea: 0, mortgageAmount: 0,
      mortgageNature: '', mortgagee: '', mortgageExpiry: '',
      isRestricted: 'N',
      fromCip: 'N', completionDate: '', expectedCertDate: '', cipNote: '',
      certValue: 0, difference: 0, diffReason: '',
      checkConclusion: '', conclusion: '', remark: '来源:H1-11监盘OCR', ocrResult: '',
    }
    list.push(row)
  }
  const fill = (k: string, v: any) => {
    if (v == null || v === '' || v === 0) return
    if (row[k] == null || row[k] === '' || row[k] === 0) row[k] = v
  }
  fill('titleCertNo', cert)
  fill('owner', ocr.owner)
  fill('address', addr)
  fill('buildingArea', Number(ocr.buildingArea) || 0)
  fill('landArea', Number(ocr.landArea) || 0)
  if (ocr.attachment_id || ocr.attachmentId) {
    fill('certCopyIndex', `OCR:${String(ocr.attachment_id || ocr.attachmentId).slice(0, 8)}`)
  }
  row.ocrResult = JSON.stringify(ocr)
  if (!row.remark) row.remark = '来源:H1-11监盘OCR'
  return { rows: list.map((r, i) => ({ ...r, seq: i + 1 })), mode }
}

/** 导出归档用扁平行（对齐小结结构） */
export function buildExportRows(form: H1StocktakeSummaryForm, stats: Record<string, number | string>): Record<string, string | number>[] {
  const rates = calcRecountRates(form)
  return [
    { section: '仪表板', field: '盘点总数', value: stats.totalCount ?? '' },
    { section: '仪表板', field: '账实相符', value: stats.matchCount ?? '' },
    { section: '仪表板', field: '盘盈', value: stats.surplusCount ?? '' },
    { section: '仪表板', field: '盘亏', value: stats.shortageCount ?? '' },
    { section: '仪表板', field: '相符率%', value: stats.matchRate ?? '' },
    { section: '时间', field: '实际盘点日期', value: form.actualDate },
    { section: '时间', field: '开始', value: form.startTime },
    { section: '时间', field: '结束', value: form.endTime },
    { section: '复盘', field: '数量覆盖率%', value: rates.unitCoverage ?? '' },
    { section: '复盘', field: '数量正确率%', value: rates.unitAccuracy ?? '' },
    { section: '复盘', field: '金额覆盖率%', value: rates.amountCoverage ?? '' },
    { section: '复盘', field: '金额正确率%', value: rates.amountAccuracy ?? '' },
    { section: '异常', field: '异常说明', value: form.abnormalNote },
    { section: '结论', field: '监盘结论', value: form.conclusion },
    { section: '签署', field: '监盘人', value: form.preparedBy },
    { section: '签署', field: '监盘日期', value: form.preparedDate },
    { section: '签署', field: '复核人', value: form.reviewedBy },
    { section: '签署', field: '复核日期', value: form.reviewedDate },
  ]
}
