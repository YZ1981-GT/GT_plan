/**
 * H1-11 监盘小结 — 数据结构与默认值
 * 对齐致同模板「固定资产监盘小结」编制逻辑：了解→计划→执行→分类复盘→统计→结论
 */

export interface SummaryLocationRow {
  rowId: string
  seq: number
  assetCategory: string
  assetName: string
  storageLocation: string
  certIndex: string
  attachmentId: string
  ocrResult: string
}

export interface SummaryPersonnelRow {
  rowId: string
  seq: number
  department: string
  headcount: number
  names: string
  responsibleArea: string
}

export interface SummaryAuditorRow {
  rowId: string
  seq: number
  names: string
  responsibleArea: string
}

export interface SummaryMgmtItem {
  id: string
  label: string
  answer: string
}

export interface SummaryPrecheckItem {
  id: string
  label: string
  obtained: '' | 'Y' | 'N' | 'NA'
  indexRef: string
  attachmentId: string
  remark: string
  ocrResult: string
}

export interface SummaryGroupRow {
  groupNo: number
  countTarget: string
  recorder: string
  headcount: number
}

export interface SummaryCategoryNote {
  category: string
  checks: Record<string, string>
  note: string
  indexRef: string
}

export interface H1StocktakeSummaryForm {
  bsDateNote: string
  locations: SummaryLocationRow[]
  mgmtItems: SummaryMgmtItem[]
  clientPersonnel: SummaryPersonnelRow[]
  auditorPersonnel: SummaryAuditorRow[]
  siteObservationNote: string
  precheckItems: SummaryPrecheckItem[]
  actualDate: string
  startTime: string
  endTime: string
  companyPersonnelNote: string
  groups: SummaryGroupRow[]
  companySpecialNote: string
  samplingMethod: string
  observationMethod: string
  movementStopped: '' | 'Y' | 'N'
  stayedOnSite: '' | 'Y' | 'N'
  categoryNotes: SummaryCategoryNote[]
  abnormalNote: string
  recountPersonnel: string
  recountIndex: string
  recountTotalUnits: number | null
  recountSampleUnits: number | null
  recountTotalAmount: number | null
  recountSampleAmount: number | null
  recountCorrectUnits: number | null
  recountCorrectAmount: number | null
  evalFamiliarity: string
  evalAttitude: string
  evalCooperation: string
  diffExplanationObtained: '' | 'Y' | 'N'
  diffExplanationIndex: string
  sampleTableObtained: '' | 'Y' | 'N'
  sampleTableIndex: string
  conclusion: string
  preparedBy: string
  preparedDate: string
  reviewedBy: string
  reviewedDate: string
  /** 人工覆盖过的自动字段名（不再被 H1-10 实时回填） */
  manualOverrides: string[]
  lastAutoSyncAt: string
  lastCheckFingerprint: string
}

export const MGMT_ITEM_DEFS: { id: string; label: string }[] = [
  { id: 'dept', label: '资产管理部门' },
  { id: 'staff', label: '资产管理人员' },
  { id: 'tagging', label: '资产标识/挂牌情况' },
  { id: 'maintain', label: '定期保养维修制度' },
  { id: 'repairCycle', label: '大修周期' },
  { id: 'ledgerComplete', label: '固定资产明细账/卡片完整性' },
  { id: 'recordComplete', label: '明细账/卡片单项记录完整性' },
]

export const PRECHECK_ITEM_DEFS: { id: string; label: string }[] = [
  { id: 'ledger', label: '已取得固定资产明细账/卡片' },
  { id: 'mgmtPolicy', label: '已取得固定资产管理制度' },
  { id: 'maintainPolicy', label: '已取得维修保养制度' },
  { id: 'locationMap', label: '已取得资产存放地点示意图' },
]

export const CATEGORY_CHECK_DEFS: Record<string, { key: string; label: string }[]> = {
  房屋及土地使用权: [
    { key: 'qtyMatch', label: '产权证数量与账面是否一致' },
    { key: 'areaMatch', label: '产权证面积与账面是否一致' },
    { key: 'certWithoutHouse', label: '是否存在有证无房' },
    { key: 'houseWithoutCert', label: '是否存在有房无证' },
  ],
  机器设备: [
    { key: 'hasTag', label: '是否有管理标识' },
    { key: 'tagRule', label: '标识编号规则说明' },
    { key: 'qtyMatch', label: '各型号数量与账面是否一致' },
    { key: 'idle', label: '是否存在闲置/不需用设备' },
    { key: 'scrappedOnBook', label: '实物已报废毁损但仍挂账' },
    { key: 'inUseOffBook', label: '在用但未入账设备' },
    { key: 'diagrams', label: '是否具备位置图/管线图' },
    { key: 'ownership', label: '大型电气设备权属是否清晰' },
  ],
  运输设备: [
    { key: 'certCheck', label: '现场核对行驶证/产权与实物' },
    { key: 'existence', label: '资产是否真实存在' },
    { key: 'inTransit', label: '在途设备确认方法' },
    { key: 'idle', label: '是否存在闲置设备' },
    { key: 'scrappedOnBook', label: '实物已报废毁损但仍挂账' },
    { key: 'inUseOffBook', label: '在用但未入账设备' },
  ],
  办公设备及其他: [
    { key: 'hasTag', label: '是否有管理标识' },
    { key: 'qtyMatch', label: '数量与账面是否一致' },
    { key: 'sameModelLoc', label: '同型号是否登记存放地点' },
    { key: 'idle', label: '是否存在闲置设备' },
    { key: 'scrappedOnBook', label: '实物已报废毁损但仍挂账' },
    { key: 'inUseOffBook', label: '在用但未入账设备' },
  ],
}

function _id(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function createEmptySummaryForm(): H1StocktakeSummaryForm {
  return {
    bsDateNote: '',
    locations: [],
    mgmtItems: MGMT_ITEM_DEFS.map((d) => ({ ...d, answer: '' })),
    clientPersonnel: [],
    auditorPersonnel: [],
    siteObservationNote: '',
    precheckItems: PRECHECK_ITEM_DEFS.map((d) => ({
      ...d,
      obtained: '',
      indexRef: '',
      attachmentId: '',
      remark: '',
      ocrResult: '',
    })),
    actualDate: '',
    startTime: '',
    endTime: '',
    companyPersonnelNote: '',
    groups: [
      { groupNo: 1, countTarget: '', recorder: '', headcount: 0 },
      { groupNo: 2, countTarget: '', recorder: '', headcount: 0 },
      { groupNo: 3, countTarget: '', recorder: '', headcount: 0 },
    ],
    companySpecialNote: '',
    samplingMethod: '',
    observationMethod: '',
    movementStopped: '',
    stayedOnSite: '',
    categoryNotes: Object.keys(CATEGORY_CHECK_DEFS).map((category) => ({
      category,
      checks: Object.fromEntries(CATEGORY_CHECK_DEFS[category].map((c) => [c.key, ''])),
      note: '',
      indexRef: '',
    })),
    abnormalNote: '',
    recountPersonnel: '',
    recountIndex: 'H1-10',
    recountTotalUnits: null,
    recountSampleUnits: null,
    recountTotalAmount: null,
    recountSampleAmount: null,
    recountCorrectUnits: null,
    recountCorrectAmount: null,
    evalFamiliarity: '',
    evalAttitude: '',
    evalCooperation: '',
    diffExplanationObtained: '',
    diffExplanationIndex: '',
    sampleTableObtained: '',
    sampleTableIndex: '',
    conclusion: '',
    preparedBy: '',
    preparedDate: '',
    reviewedBy: '',
    reviewedDate: '',
    manualOverrides: [],
    lastAutoSyncAt: '',
    lastCheckFingerprint: '',
  }
}

/** 合并已存 JSON，补齐缺省字段（兼容旧版仅 note/conclusion） */
export function normalizeSummaryForm(raw: any, legacyConclusion = ''): H1StocktakeSummaryForm {
  const base = createEmptySummaryForm()
  if (!raw || typeof raw !== 'object') {
    if (legacyConclusion) base.conclusion = legacyConclusion
    return base
  }
  const out: H1StocktakeSummaryForm = { ...base, ...raw }

  out.mgmtItems = MGMT_ITEM_DEFS.map((d) => {
    const found = (Array.isArray(raw.mgmtItems) ? raw.mgmtItems : []).find((x: any) => x?.id === d.id)
    return { ...d, answer: found?.answer ?? '' }
  })

  out.precheckItems = PRECHECK_ITEM_DEFS.map((d) => {
    const found = (Array.isArray(raw.precheckItems) ? raw.precheckItems : []).find((x: any) => x?.id === d.id)
    return {
      ...d,
      obtained: found?.obtained ?? '',
      indexRef: found?.indexRef ?? '',
      attachmentId: found?.attachmentId ?? '',
      remark: found?.remark ?? '',
      ocrResult: found?.ocrResult ?? '',
    }
  })

  out.locations = Array.isArray(raw.locations)
    ? raw.locations.map((r: any, i: number) => ({
        rowId: r.rowId ?? `loc-${_id()}`,
        seq: r.seq ?? i + 1,
        assetCategory: r.assetCategory ?? '',
        assetName: r.assetName ?? '',
        storageLocation: r.storageLocation ?? '',
        certIndex: r.certIndex ?? '',
        attachmentId: r.attachmentId ?? '',
        ocrResult: r.ocrResult ?? '',
      }))
    : []

  out.clientPersonnel = Array.isArray(raw.clientPersonnel)
    ? raw.clientPersonnel.map((r: any, i: number) => ({
        rowId: r.rowId ?? `cp-${_id()}`,
        seq: r.seq ?? i + 1,
        department: r.department ?? '',
        headcount: Number(r.headcount) || 0,
        names: r.names ?? '',
        responsibleArea: r.responsibleArea ?? '',
      }))
    : []

  out.auditorPersonnel = Array.isArray(raw.auditorPersonnel)
    ? raw.auditorPersonnel.map((r: any, i: number) => ({
        rowId: r.rowId ?? `ap-${_id()}`,
        seq: r.seq ?? i + 1,
        names: r.names ?? '',
        responsibleArea: r.responsibleArea ?? '',
      }))
    : []

  out.groups = Array.isArray(raw.groups) && raw.groups.length
    ? raw.groups.map((g: any, i: number) => ({
        groupNo: g.groupNo ?? i + 1,
        countTarget: g.countTarget ?? '',
        recorder: g.recorder ?? '',
        headcount: Number(g.headcount) || 0,
      }))
    : base.groups

  out.categoryNotes = Object.keys(CATEGORY_CHECK_DEFS).map((category) => {
    const found = (Array.isArray(raw.categoryNotes) ? raw.categoryNotes : []).find(
      (c: any) => c?.category === category,
    )
    const defs = CATEGORY_CHECK_DEFS[category]
    return {
      category,
      checks: Object.fromEntries(
        defs.map((c) => [c.key, found?.checks?.[c.key] ?? '']),
      ),
      note: found?.note ?? '',
      indexRef: found?.indexRef ?? '',
    }
  })

  if (!out.conclusion && legacyConclusion) out.conclusion = legacyConclusion
  if (!Array.isArray(out.manualOverrides)) out.manualOverrides = []
  if (!out.lastAutoSyncAt) out.lastAutoSyncAt = ''
  if (!out.lastCheckFingerprint) out.lastCheckFingerprint = ''
  return out
}

export function newLocationRow(partial?: Partial<SummaryLocationRow>): SummaryLocationRow {
  return {
    rowId: `loc-${_id()}`,
    seq: 1,
    assetCategory: '',
    assetName: '',
    storageLocation: '',
    certIndex: '',
    attachmentId: '',
    ocrResult: '',
    ...partial,
  }
}

export function newClientPersonnelRow(partial?: Partial<SummaryPersonnelRow>): SummaryPersonnelRow {
  return {
    rowId: `cp-${_id()}`,
    seq: 1,
    department: '',
    headcount: 1,
    names: '',
    responsibleArea: '',
    ...partial,
  }
}

export function newAuditorRow(partial?: Partial<SummaryAuditorRow>): SummaryAuditorRow {
  return {
    rowId: `ap-${_id()}`,
    seq: 1,
    names: '',
    responsibleArea: '',
    ...partial,
  }
}

/** 复盘覆盖率 / 正确率（空值安全） */
export function calcRecountRates(form: H1StocktakeSummaryForm): {
  unitCoverage: number | null
  amountCoverage: number | null
  unitAccuracy: number | null
  amountAccuracy: number | null
} {
  const pct = (num: number | null, den: number | null) => {
    if (num == null || den == null || den <= 0) return null
    return Math.round((num / den) * 1000) / 10
  }
  return {
    unitCoverage: pct(form.recountSampleUnits, form.recountTotalUnits),
    amountCoverage: pct(form.recountSampleAmount, form.recountTotalAmount),
    unitAccuracy: pct(form.recountCorrectUnits, form.recountSampleUnits),
    amountAccuracy: pct(form.recountCorrectAmount, form.recountSampleAmount),
  }
}

/** 结束时间须晚于开始时间（HH:mm） */
export function isTimeRangeValid(start: string, end: string): boolean {
  if (!start || !end) return true
  const toMin = (t: string) => {
    const m = t.match(/^(\d{1,2}):(\d{2})$/)
    if (!m) return null
    return Number(m[1]) * 60 + Number(m[2])
  }
  const a = toMin(start)
  const b = toMin(end)
  if (a == null || b == null) return true
  return b > a
}

/** 从 H1-10 检查行汇总复盘统计草稿（仅填空） */
export function draftRecountFromCheckRows(
  rows: { result: string; bookNetValue?: number; bookCost?: number; bookAmount?: number }[],
): Partial<H1StocktakeSummaryForm> {
  const amtOf = (r: { bookNetValue?: number; bookCost?: number; bookAmount?: number }) =>
    Number(r.bookNetValue) || Number(r.bookAmount) || Number(r.bookCost) || 0
  const total = rows.length
  const match = rows.filter((r) => r.result === '账实相符').length
  const amount = rows.reduce((s, r) => s + amtOf(r), 0)
  const matchAmt = rows
    .filter((r) => r.result === '账实相符')
    .reduce((s, r) => s + amtOf(r), 0)
  return {
    recountTotalUnits: total || null,
    recountSampleUnits: total || null,
    recountCorrectUnits: match || null,
    recountTotalAmount: amount || null,
    recountSampleAmount: amount || null,
    recountCorrectAmount: matchAmt || null,
  }
}

/** 从 H1-10 推导主要存放地点（按地点去重） */
export function draftLocationsFromCheckRows(
  rows: { name: string; location: string; assetNo?: string }[],
): SummaryLocationRow[] {
  const map = new Map<string, SummaryLocationRow>()
  for (const r of rows) {
    const loc = (r.location || '').trim() || '（未填地点）'
    if (map.has(loc)) continue
    map.set(loc, newLocationRow({
      assetCategory: '',
      assetName: r.name || '',
      storageLocation: loc === '（未填地点）' ? '' : loc,
    }))
  }
  return [...map.values()].map((r, i) => ({ ...r, seq: i + 1 }))
}

export const H1_SUMMARY_OCR_LABELS: Record<string, string> = {
  assetCategory: '资产类别',
  assetName: '资产名称',
  storageLocation: '存放地点',
  certIndex: '权证/检查索引',
  titleCertNo: '权证号',
  address: '坐落地址',
  buildingArea: '建筑面积',
  owner: '权利人',
  full_text: '识别全文',
  documentType: '资料类型',
  indexSuggestion: '建议索引',
  content: '摘要内容',
}
