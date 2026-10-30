/**
 * G6-15 其他债权投资凭证检查。
 *
 * 对齐源模板：样本选取标准 → 本期发生额 → 期后处置/新增 →
 * 六项三态核对 → 检查比例、例外事项与审计结论。
 * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：本期、期后各一张表，
 * 一个对方科目一行（后端配对），按分录指纹去重，行元数据 `_gt` 随行 JSON 落库
 * （spec voucher-identity-writeback-and-audit-phase 任务 11）。
 */
import { computed, ref, type MaybeRefOrGetter, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { calcSumColumn, parseNum } from '@/composables/useG6EclFormulaEngine'
import type {
  VoucherCheckPeriod,
  VoucherCheckResult,
  VoucherCheckRow,
  VoucherSampleCriteria,
  VoucherSelectionCategory,
} from '@/components/workpaper/composables/useG6EclFormData'
import {
  metaOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem,
} from '@/components/workpaper/composables/shared/voucherCheckFill'

export const G6_VOUCHER_SCHEMA_VERSION = 2
export const G6_VOUCHER_ROW_KEY = 'G6-15-rows'
export const G6_VOUCHER_CRITERIA_KEY = 'G6-15-criteria'
export const G6_VOUCHER_NOTE_KEY = 'G6-15-audit-note'
export const G6_VOUCHER_CONCLUSION_KEY = 'G6-15-audit-conclusion'
export {
  G6_12_DATA_KEY,
  G6_14_DATA_KEY,
} from '@/components/workpaper/composables/g6CrossHelpers'
// 与 g6StorageContract.G6_ITEM_IDS 保持同源

export const G6_VOUCHER_CHECKS: Array<{ key: keyof VoucherCheckRow; label: string }> = [
  { key: 'checkOriginal', label: '原始凭证内容完整' },
  { key: 'checkAuthorized', label: '有授权批准' },
  { key: 'checkAccounting', label: '账务处理正确' },
  { key: 'checkInitialCost', label: '初始成本计算正确' },
  { key: 'checkInterest', label: '利息计算正确' },
  { key: 'checkFairValue', label: '公允价值符合准则要求' },
]

export const G6_VOUCHER_BUSINESS_TYPES = [
  '新增/购买',
  '利息确认',
  '利息收取',
  '公允价值变动',
  '减值计提',
  '减值转回',
  '核销',
  '处置',
  'OCI重分类',
  '其他',
] as const

export const G6_VOUCHER_CONCLUSION_TEMPLATES: Record<string, string> = {
  A: '经检查，所抽查其他债权投资相关凭证支持性文件完整、授权批准适当，初始成本、利息、公允价值及账务处理未见异常。',
  B: '经检查，除上述重大不符事项应作为调整事项处理外，其余样本未见异常。',
  C: '由于存在重大未调整事项或审计范围受限，暂无法就相关交易形成审计结论。',
}

export function createEmptyVoucherCriteria(): VoucherSampleCriteria {
  return {
    populationDebitCount: 0,
    populationDebitAmount: 0,
    populationCreditCount: 0,
    populationCreditAmount: 0,
    specificSample: '大额、关联方/关联交易及异常项目全部测试',
    specificSampleCount: 0,
    specificSampleAmount: 0,
    samplingPopulationCount: 0,
    samplingPopulationAmount: 0,
    sampleSize: 0,
    samplingMethod: '随机选样',
    samplingProcess: '',
    bookDebitOccurrence: 0,
    bookCreditOccurrence: 0,
  }
}

/** 三态规范化。旧 boolean false 默认视为「未检查」，仅在明确异常时视为 N。 */
export function normalizeResult(
  value: unknown,
  opts: { treatFalseAsFail?: boolean } = {},
): VoucherCheckResult {
  if (value === true || value === 'Y' || value === '是' || value === '✓') return 'Y'
  if (value === 'N' || value === '否' || value === '✗') return 'N'
  if (value === false) return opts.treatFalseAsFail ? 'N' : ''
  if (value === 'NA' || value === 'N/A' || value === '不适用') return 'NA'
  if (value == null || value === '') return ''
  const s = String(value).trim().toUpperCase()
  if (s === 'Y' || s === 'N' || s === 'NA') return s as VoucherCheckResult
  return ''
}

function makeId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `g6vc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function buildSourceId(parts: {
  sourceId?: string
  date?: string
  voucherNo?: string
  debitAmount?: number | string
  creditAmount?: number | string
}): string {
  if (parts.sourceId?.trim()) return parts.sourceId.trim()
  return [
    String(parts.date || '').trim(),
    String(parts.voucherNo || '').trim().toLowerCase(),
    // eslint-disable-next-line gt-audit/no-amount-toFixed
    parseNum(parts.debitAmount).toFixed(2),
    // eslint-disable-next-line gt-audit/no-amount-toFixed
    parseNum(parts.creditAmount).toFixed(2),
  ].join('|')
}

export function createEmptyVoucherRow(
  period: VoucherCheckPeriod = 'occurrence',
  partial: Partial<VoucherCheckRow> = {},
): VoucherCheckRow {
  const base: VoucherCheckRow = {
    id: makeId(),
    seq: 0,
    period,
    date: '',
    voucherNo: '',
    businessContent: '',
    businessType: '',
    counterAccount: '',
    detailAccount: '',
    debitAmount: 0,
    creditAmount: 0,
    attachment: null,
    attachmentId: null,
    attachmentUrl: null,
    attachmentUploadedAt: null,
    supportingDoc: '',
    checkOriginal: '',
    checkAuthorized: '',
    checkAccounting: '',
    checkInitialCost: '',
    checkInterest: '',
    checkFairValue: '',
    indexRef: '',
    isAbnormal: false,
    manualAbnormal: false,
    abnormalNote: '',
    riskLevel: '',
    suggestion: '',
    remark: '',
    source: '手工',
    selectionReason: '',
    samplingMethod: '',
    selectionCategory: 'manual',
    sourceId: '',
  }
  const merged = { ...base, ...partial, period: partial.period ?? period }
  if (!merged.sourceId) {
    merged.sourceId = buildSourceId(merged)
  }
  return merged
}

function isLegacyBooleanChecks(raw: any): boolean {
  const keys = [
    'checkOriginal', 'checkAuthorized', 'checkAccounting',
    'checkAmount', 'checkInitialCost', 'checkInterest',
    'checkClassification', 'checkFairValue', 'checkImpairment',
  ]
  return keys.some(k => typeof raw?.[k] === 'boolean')
}

/** 兼容旧版七项 boolean、单表 rows 及导入数据。 */
export function migrateVoucherRow(raw: any, index = 0): VoucherCheckRow {
  const period: VoucherCheckPeriod =
    raw?.period === 'post' || raw?.section === 'post' ? 'post' : 'occurrence'
  const legacyBool = isLegacyBooleanChecks(raw)
  const explicitlyAbnormal =
    raw?.isAbnormal === true
    || raw?.isAbnormal === '是'
    || raw?.manualAbnormal === true
  // 旧版 false 同时表示「未检查」和「不通过」：仅当整行已标异常时才把 false 视作 N
  const treatFalseAsFail = legacyBool && explicitlyAbnormal

  const row = createEmptyVoucherRow(period, {
    ...raw,
    id: raw?.id || makeId(),
    seq: index + 1,
    period,
    businessType: raw?.businessType ?? '',
    counterAccount: raw?.counterAccount ?? raw?.offsetAccount ?? '',
    detailAccount: raw?.detailAccount ?? raw?.offsetSubAccount ?? '',
    debitAmount: parseNum(raw?.debitAmount),
    creditAmount: parseNum(raw?.creditAmount),
    checkOriginal: normalizeResult(raw?.checkOriginal, { treatFalseAsFail }),
    checkAuthorized: normalizeResult(raw?.checkAuthorized, { treatFalseAsFail }),
    checkAccounting: normalizeResult(raw?.checkAccounting, { treatFalseAsFail }),
    checkInitialCost: normalizeResult(raw?.checkInitialCost ?? raw?.checkAmount, { treatFalseAsFail }),
    checkInterest: normalizeResult(raw?.checkInterest, { treatFalseAsFail }),
    checkFairValue: normalizeResult(
      raw?.checkFairValue ?? raw?.checkClassification ?? raw?.checkImpairment,
      { treatFalseAsFail },
    ),
    attachmentId: raw?.attachmentId ?? null,
    attachmentUrl: raw?.attachmentUrl ?? null,
    attachmentUploadedAt: raw?.attachmentUploadedAt ?? null,
    manualAbnormal: !!raw?.manualAbnormal || (legacyBool && explicitlyAbnormal && !treatFalseAsFail),
    source: raw?.source ?? '迁移',
    selectionReason: raw?.selectionReason ?? '',
    samplingMethod: raw?.samplingMethod ?? '',
    selectionCategory: (raw?.selectionCategory as VoucherSelectionCategory) || (
      raw?.source === '抽凭引擎' ? 'representative' : (raw?.source ? 'manual' : '')
    ),
    sourceId: buildSourceId({
      sourceId: raw?.sourceId,
      date: raw?.date,
      voucherNo: raw?.voucherNo,
      debitAmount: raw?.debitAmount,
      creditAmount: raw?.creditAmount,
    }),
  })
  recalcVoucherAbnormal(row)
  return row
}

export function voucherCheckResults(row: VoucherCheckRow): VoucherCheckResult[] {
  return G6_VOUCHER_CHECKS.map(({ key }) => normalizeResult(row[key]))
}

export function isVoucherCheckComplete(row: VoucherCheckRow): boolean {
  return voucherCheckResults(row).every(Boolean)
}

export function recalcVoucherAbnormal(row: VoucherCheckRow): void {
  row.isAbnormal = !!row.manualAbnormal || voucherCheckResults(row).includes('N')
}

/** 行级质量校验 */
export function validateVoucherRow(
  row: VoucherCheckRow,
  opts: { bsDate?: string } = {},
): string[] {
  const errors: string[] = []
  if (!String(row.date || '').trim()) errors.push('日期为空')
  if (!String(row.voucherNo || '').trim()) errors.push('凭证号为空')
  if (parseNum(row.debitAmount) < 0 || parseNum(row.creditAmount) < 0) errors.push('金额为负')
  if (parseNum(row.debitAmount) === 0 && parseNum(row.creditAmount) === 0) errors.push('借贷金额均为零')
  if (parseNum(row.debitAmount) > 0 && parseNum(row.creditAmount) > 0) errors.push('借贷方同时有金额')
  if (row.period === 'post' && opts.bsDate && row.date && row.date <= opts.bsDate) {
    errors.push('期后日期未晚于资产负债表日')
  }
  if (row.isAbnormal) {
    if (!String(row.abnormalNote || '').trim()) errors.push('异常未填写说明')
    if (!row.riskLevel) errors.push('异常未定风险等级')
    if (!String(row.suggestion || '').trim()) errors.push('异常未填处理建议')
  }
  return errors
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function inferSelectionCategory(sample: any): VoucherSelectionCategory {
  if (sample?.selectionCategory === 'specific' || sample?.isHighValue) return 'specific'
  if (sample?.selectionCategory === 'manual') return 'manual'
  return 'representative'
}

function inferBusinessType(summary: string): string {
  const s = summary || ''
  if (/核销/.test(s)) return '核销'
  if (/转回|收回/.test(s)) return '减值转回'
  if (/减值|信用损失|ECL/.test(s)) return '减值计提'
  if (/利息/.test(s)) return /收/.test(s) ? '利息收取' : '利息确认'
  if (/公允|估值|市值/.test(s)) return '公允价值变动'
  if (/处置|出售|赎回/.test(s)) return '处置'
  if (/购|买入|申购|新增/.test(s)) return '新增/购买'
  if (/OCI|其他综合收益|重分类/.test(s)) return 'OCI重分类'
  return ''
}

/**
 * 共享回填函数的待写入项 → G6-15 检查行（期间由所进的表定）：金额在样本自己的借贷栏，对方科目 = 编码、
 * 对方明细科目 = 名称（配不上写「多科目」时沿用原来的本科目名称兜底）；同一分录按对方科目展开的几行
 * sourceId 各不相同（重复样本告警按它认）。
 */
export function mapPreparedToG6VoucherRow(item: PreparedItem, period: VoucherCheckPeriod): VoucherCheckRow {
  const s = item.sample as PreparedItem['sample'] & {
    summary?: string | null; businessType?: string | null; selectionReason?: string | null
    samplingMethod?: string | null; accountName?: string | null
  }
  const code = item.counterpartAccount
  const name = item.counterpartAccountName
  const summary = s.summary ?? ''
  return migrateVoucherRow({
    period,
    date: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    businessContent: summary,
    businessType: s.businessType || inferBusinessType(summary),
    counterAccount: code,
    detailAccount: name && name !== code ? name : (s.accountName ?? ''),
    debitAmount: item.debitAmount ?? 0,
    creditAmount: item.creditAmount ?? 0,
    source: item.meta.src.includes('attach') ? '挂凭' : '抽凭引擎',
    selectionReason: s.selectionReason ?? '',
    samplingMethod: s.samplingMethod ?? '',
    selectionCategory: inferSelectionCategory(s),
    sourceId: item.meta.lfp ? `${item.meta.lfp}#${item.meta.cp ?? ''}` : '',
  })
}

/** 行上已填核对结果、附件、支持性文件、索引、例外说明 / 风险 / 建议或备注（替换与撤销抽凭时据此先确认） */
export function hasG6VoucherContent(r: VoucherCheckRow): boolean {
  return voucherCheckResults(r).some(Boolean) || !!r.manualAbnormal
    || [r.attachment, r.supportingDoc, r.indexRef, r.abnormalNote, r.riskLevel, r.suggestion, r.remark]
      .some(v => String(v ?? '').trim() !== '')
}

export function useG6EclVoucherCheck(
  wpId: Ref<string>,
  _projectId?: Ref<string>,
  htmlData?: Ref<Record<string, any> | null>,
  opts?: { readonly?: MaybeRefOrGetter<boolean> },
) {
  const criteria = ref<VoucherSampleCriteria>(createEmptyVoucherCriteria())
  const rows = ref<VoucherCheckRow[]>([])
  const activePeriod = ref<VoucherCheckPeriod>('occurrence')
  const activeTab = ref<'base' | 'checks' | 'result'>('base')
  const ocrLoadingRowId = ref<string | null>(null)
  /** 跨底稿覆盖缺口（由页面注入 G6-12/G6-14 摘要后计算） */
  const crossCoverageGaps = ref<string[]>([])

  const bsDate = computed(() => String(htmlData?.value?.bsDate || ''))

  const occurrenceRows = computed(() => rows.value.filter(r => r.period === 'occurrence'))
  const postPeriodRows = computed(() => rows.value.filter(r => r.period === 'post'))
  const currentRows = computed(() =>
    activePeriod.value === 'occurrence' ? occurrenceRows.value : postPeriodRows.value,
  )

  const occurrenceDebitChecked = computed(() =>
    calcSumColumn(occurrenceRows.value.map(row => parseNum(row.debitAmount))),
  )
  const occurrenceCreditChecked = computed(() =>
    calcSumColumn(occurrenceRows.value.map(row => parseNum(row.creditAmount))),
  )
  const postDebitChecked = computed(() =>
    calcSumColumn(postPeriodRows.value.map(row => parseNum(row.debitAmount))),
  )
  const postCreditChecked = computed(() =>
    calcSumColumn(postPeriodRows.value.map(row => parseNum(row.creditAmount))),
  )
  const debitRatio = computed<number | null>(() => {
    const denominator = criteria.value.bookDebitOccurrence || criteria.value.populationDebitAmount
    return denominator > 0 ? occurrenceDebitChecked.value / denominator : null
  })
  const creditRatio = computed<number | null>(() => {
    const denominator = criteria.value.bookCreditOccurrence || criteria.value.populationCreditAmount
    return denominator > 0 ? occurrenceCreditChecked.value / denominator : null
  })

  const specificRows = computed(() =>
    occurrenceRows.value.filter(r => r.selectionCategory === 'specific'),
  )
  const representativeRows = computed(() =>
    occurrenceRows.value.filter(r => r.selectionCategory === 'representative'),
  )

  const incompleteRows = computed(() => rows.value.filter(row => !isVoucherCheckComplete(row)))
  const abnormalRows = computed(() => rows.value.filter(row => row.isAbnormal))
  const unexplainedAbnormalRows = computed(() =>
    abnormalRows.value.filter(row => !row.abnormalNote.trim()),
  )
  const rowValidationErrors = computed(() => {
    const list: Array<{ id: string; voucherNo: string; errors: string[] }> = []
    for (const row of rows.value) {
      const errors = validateVoucherRow(row, { bsDate: bsDate.value })
      if (errors.length) list.push({ id: row.id, voucherNo: row.voucherNo, errors })
    }
    return list
  })
  const duplicateRows = computed(() => {
    const seen = new Set<string>()
    const duplicates: VoucherCheckRow[] = []
    for (const row of rows.value) {
      const key = row.sourceId || buildSourceId(row)
      if (!row.voucherNo.trim() && !row.sourceId) continue
      if (seen.has(key)) duplicates.push(row)
      seen.add(key)
    }
    return duplicates
  })

  const gateWarnings = computed(() => {
    const warnings: string[] = []
    if (!criteria.value.populationDebitCount && !criteria.value.populationCreditCount) {
      warnings.push('尚未填写借贷方测试总体笔数')
    }
    if (!criteria.value.sampleSize && !criteria.value.specificSampleCount) {
      warnings.push('尚未确定特定样本或代表性样本量')
    }
    if (!criteria.value.samplingProcess.trim()) warnings.push('尚未记录抽样过程')

    const plannedSpecific = criteria.value.specificSampleCount || 0
    const plannedRep = criteria.value.sampleSize || 0
    if (plannedSpecific > 0 && specificRows.value.length < plannedSpecific) {
      warnings.push(`特定样本实际 ${specificRows.value.length} 笔，少于计划 ${plannedSpecific} 笔`)
    }
    if (plannedRep > 0 && representativeRows.value.length < plannedRep) {
      warnings.push(`代表性样本实际 ${representativeRows.value.length} 笔，少于计划 ${plannedRep} 笔`)
    }
    // 兼容：未区分类别时，用本期总行数对照「特定+代表性」
    const plannedTotal = plannedSpecific + plannedRep
    if (
      plannedTotal > 0
      && !specificRows.value.length
      && !representativeRows.value.length
      && occurrenceRows.value.length < plannedTotal
    ) {
      warnings.push(`本期实际样本 ${occurrenceRows.value.length} 笔，少于计划 ${plannedTotal} 笔`)
    }

    if (debitRatio.value != null && debitRatio.value > 1.001) {
      warnings.push('借方检查比例超过100%，请核对总体分母或重复样本')
    }
    if (creditRatio.value != null && creditRatio.value > 1.001) {
      warnings.push('贷方检查比例超过100%，请核对总体分母或重复样本')
    }
    if (incompleteRows.value.length) warnings.push(`${incompleteRows.value.length} 笔样本核对未完成`)
    if (unexplainedAbnormalRows.value.length) {
      warnings.push(`${unexplainedAbnormalRows.value.length} 笔异常样本未填写异常说明`)
    }
    if (duplicateRows.value.length) warnings.push(`发现 ${duplicateRows.value.length} 笔重复样本`)
    if (rowValidationErrors.value.length) {
      warnings.push(`${rowValidationErrors.value.length} 笔样本存在字段质量问题`)
    }
    warnings.push(...crossCoverageGaps.value)
    return warnings
  })

  // ─── 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（本期、期后各一张表） ───

  /** 已在某个期间表的分录（按指纹）：再次回填 / 挂凭导入仍进那张表 */
  function periodHolding(lfp: string | null): VoucherCheckPeriod | null {
    if (!lfp) return null
    return rows.value.find(r => metaOf(r)?.lfp === lfp)?.period ?? null
  }
  const periodTable = (period: VoucherCheckPeriod) => computed<VoucherCheckRow[]>({
    get: () => rows.value.filter(r => r.period === period),
    set: (list) => {
      rows.value = period === 'occurrence'
        ? [...list, ...rows.value.filter(r => r.period === 'post')]
        : [...rows.value.filter(r => r.period === 'occurrence'), ...list]
    },
  })
  const periodTables = { occurrence: periodTable('occurrence'), post: periodTable('post') }
  const voucherFill = useVoucherCheckFill<VoucherCheckRow>({
    projectId: () => _projectId?.value,
    tables: periodTables,
    tableOf: item => periodHolding(item.meta.lfp),
    mapSampleToRow: (item, key) => mapPreparedToG6VoucherRow(item, key as VoucherCheckPeriod),
    // 宿主深度监听 rows 落库（rowsToPersist 已按读入版本写回预审行），这里不另存
    persist: () => undefined,
    hasUserContent: hasG6VoucherContent,
    afterChange: () => resequence(),
    readonly: opts?.readonly,
  })

  /** 保存用的行：年审阶段预审行按读入版本写回（宿主落库与 toJSON 都用它） */
  function rowsToPersist(): VoucherCheckRow[] {
    return [
      ...voucherFill.guardPersist(periodTables.occurrence.value, 'occurrence'),
      ...voucherFill.guardPersist(periodTables.post.value, 'post'),
    ]
  }

  /** 期后表只收资产负债表日之后的凭证：截止日前的剔除并提示 */
  function dropPreCutoff<S extends FillSample>(period: VoucherCheckPeriod, samples: S[]): S[] {
    const cutoff = bsDate.value
    if (period !== 'post' || !cutoff) return samples
    const kept = samples.filter(s => !(s.voucherDate && s.voucherDate <= cutoff))
    const rejected = samples.length - kept.length
    if (rejected) ElMessage.warning(`期后表只收资产负债表日（${cutoff}）之后的凭证，已剔除截止日前 ${rejected} 笔`)
    return kept
  }

  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedRow(row: VoucherCheckRow | undefined): boolean {
    return !!row && voucherFill.isRowLocked(row)
  }

  function resequence(): void {
    let occurrenceSeq = 0
    let postSeq = 0
    for (const row of rows.value) {
      row.seq = row.period === 'occurrence' ? ++occurrenceSeq : ++postSeq
    }
  }

  function loadRows(data: any[] | { rows?: any[]; occurrenceRows?: any[]; postPeriodRows?: any[] }): void {
    let rawRows: any[] = []
    if (Array.isArray(data)) rawRows = data
    else if (data && Array.isArray(data.rows)) rawRows = data.rows
    else if (data) {
      rawRows = [
        ...(data.occurrenceRows || []).map((r: any) => ({ ...r, period: 'occurrence' })),
        ...(data.postPeriodRows || []).map((r: any) => ({ ...r, period: 'post' })),
      ]
    }
    rows.value = rawRows.map((r, i) => withRowMeta(migrateVoucherRow(r, i), r))
    resequence()
    voucherFill.markLoaded()
  }

  function addRow(period: VoucherCheckPeriod = activePeriod.value): VoucherCheckRow {
    const row = createEmptyVoucherRow(period, { selectionCategory: 'manual', source: '手工' })
    rows.value.push(row)
    resequence()
    return row
  }

  function removeRow(id: string): void {
    if (lockedRow(rows.value.find(row => row.id === id))) return
    rows.value = rows.value.filter(row => row.id !== id)
    resequence()
  }

  function setCheck(row: VoucherCheckRow, key: keyof VoucherCheckRow, value: VoucherCheckResult): void {
    if (lockedRow(row)) return
    ;(row as any)[key] = value
    recalcVoucherAbnormal(row)
  }

  function setManualAbnormal(row: VoucherCheckRow, value: boolean): void {
    if (lockedRow(row)) return
    row.manualAbnormal = value
    recalcVoucherAbnormal(row)
  }

  /**
   * 抽凭引擎回填进所选的期间表（本期 / 期后，缺省当前期间）：一个对方科目一行，按分录指纹去重；
   * 「替换本阶段抽凭行」只动所选的表。期后表只收资产负债表日之后的凭证（截止日前的剔除并提示）。
   * 原实现按 sourceId 去重、替换时清空整个期间（含手工行），已删除。
   */
  async function onEngineFilled(
    payload: EngineFilledPayload & { method?: string },
    period: VoucherCheckPeriod = activePeriod.value,
  ) {
    const samples = dropPreCutoff(period, payload.samples ?? [])
      .map(s => ({ ...s, samplingMethod: (s as { samplingMethod?: string }).samplingMethod ?? payload.method ?? '' }))
    return voucherFill.onEngineFilled({ ...payload, samples }, { tables: [period] })
  }

  /** 从序时账挂入导入所选的期间表：幂等追加（已在另一期间表的分录留在原处） */
  async function onAttachImported(samples: FillSample[], period: VoucherCheckPeriod = activePeriod.value) {
    return voucherFill.onAttachImported(dropPreCutoff(period, samples), { tables: [period] })
  }

  /**
   * 根据 G6-12 / G6-14 重大事项检查抽凭覆盖。
   * materialityThreshold 默认取总体金额 1% 与 0 中较大者，调用方可覆盖。
   */
  function evaluateCrossCoverage(payload: {
    impairmentRows?: any[]
    reversals?: any[]
    writeOffs?: any[]
    materialityThreshold?: number
  }): string[] {
    const gaps: string[] = []
    const threshold = payload.materialityThreshold ?? Math.max(
      (criteria.value.populationDebitAmount + criteria.value.populationCreditAmount) * 0.01,
      0,
    )
    const hasVoucherMatch = (keywords: RegExp) =>
      rows.value.some(r => keywords.test(`${r.businessType} ${r.businessContent}`))

    const impairment = (payload.impairmentRows || []).filter(r =>
      Math.abs(parseNum(r.currentProvision ?? r.impairmentProvision)) >= threshold && threshold > 0
      || (threshold === 0 && Math.abs(parseNum(r.currentProvision ?? r.impairmentProvision)) > 0),
    )
    if (impairment.length && !hasVoucherMatch(/减值计提|减值|信用损失/)) {
      gaps.push(`G6-12 有 ${impairment.length} 笔重大减值计提，但凭证检查未见对应样本`)
    }

    const reversals = (payload.reversals || []).filter(r =>
      Math.abs(parseNum(r.reversalAmount ?? r.amount)) > 0,
    )
    if (reversals.length && !hasVoucherMatch(/减值转回|转回|收回/)) {
      gaps.push(`G6-14 有 ${reversals.length} 笔转回/收回，但凭证检查未见对应样本`)
    }

    const writeOffs = (payload.writeOffs || []).filter(r =>
      Math.abs(parseNum(r.writeOffAmount ?? r.amount)) > 0,
    )
    if (writeOffs.length && !hasVoucherMatch(/核销/)) {
      gaps.push(`G6-14 有 ${writeOffs.length} 笔核销，但凭证检查未见对应样本`)
    }

    crossCoverageGaps.value = gaps
    return gaps
  }

  const OCR_FIELD_MAP: Record<string, keyof VoucherCheckRow> = {
    date: 'date',
    voucher_date: 'date',
    凭证日期: 'date',
    voucherNo: 'voucherNo',
    voucher_no: 'voucherNo',
    凭证号: 'voucherNo',
    凭证编号: 'voucherNo',
    summary: 'businessContent',
    摘要: 'businessContent',
    业务内容: 'businessContent',
    counter_account: 'counterAccount',
    对方科目: 'counterAccount',
    detail_account: 'detailAccount',
    明细科目: 'detailAccount',
    debit_amount: 'debitAmount',
    借方金额: 'debitAmount',
    credit_amount: 'creditAmount',
    贷方金额: 'creditAmount',
  }

  function mapOcrToVoucherFields(fields: Record<string, any>): Partial<VoucherCheckRow> {
    const patch: Partial<VoucherCheckRow> = {}
    for (const [sourceKey, value] of Object.entries(fields)) {
      const target = OCR_FIELD_MAP[sourceKey]
      if (!target || value == null || String(value).trim() === '') continue
      ;(patch as any)[target] =
        target === 'debitAmount' || target === 'creditAmount'
          ? parseNum(value)
          : String(value).trim()
    }
    return patch
  }

  async function handleRowOcr(row: VoucherCheckRow, file: File): Promise<boolean> {
    if (!wpId.value || lockedRow(row)) return false
    ocrLoadingRowId.value = row.id
    try {
      const body = new FormData()
      body.append('file', file)
      const response = await http.post(`/api/workpapers/${wpId.value}/d4/contract-ocr`, body, {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any)
      const data = response.data?.data ?? response.data
      const fields = data?.extracted_fields || {}
      const patch = mapOcrToVoucherFields(fields)
      const attachmentId = data?.attachment_id || data?.attachmentId || null
      if (!Object.keys(patch).length && !attachmentId) {
        ElMessage.info('OCR完成，未识别到可填充字段')
        return false
      }
      const preview = Object.entries(patch)
        .map(([key, value]) => `<div><b>${escapeHtml(key)}：</b>${escapeHtml(value)}</div>`)
        .join('')
        // 显示文件名而不是附件编号（spec attachment-inline-preview 需求 3.3）
        + (attachmentId ? `<div><b>附件：</b>${escapeHtml(file.name)}</div>` : '')
      await ElMessageBox.confirm(preview || '确认保存附件？', 'OCR识别结果', {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
        dangerouslyUseHTMLString: true,
      })
      Object.assign(row, patch)
      row.attachment = file.name
      row.attachmentId = attachmentId
      row.attachmentUrl = attachmentId
        ? `/api/workpapers/${wpId.value}/attachments/${attachmentId}`
        : null
      row.attachmentUploadedAt = new Date().toISOString()
      ElMessage.success('已填入OCR识别结果并落库附件')
    } catch (error: any) {
      if (error !== 'cancel' && error?.toString?.() !== 'cancel') ElMessage.warning('OCR识别失败')
    } finally {
      ocrLoadingRowId.value = null
    }
    return false
  }

  function applyConclusionTemplate(option: string, current = ''): string {
    return current || G6_VOUCHER_CONCLUSION_TEMPLATES[option] || current
  }

  function abnormalSummaryForAi(limit = 8): string[] {
    return abnormalRows.value.slice(0, limit).map(r =>
      `${r.voucherNo || '无号'}｜${r.businessType || r.businessContent || ''}｜${r.abnormalNote || '原因待补'}｜风险${r.riskLevel || '未定'}`,
    )
  }

  function toJSON() {
    return {
      schemaVersion: G6_VOUCHER_SCHEMA_VERSION,
      criteria: { ...criteria.value },
      rows: rowsToPersist().map(row => ({ ...row })),
    }
  }

  return {
    criteria,
    rows,
    occurrenceRows,
    postPeriodRows,
    currentRows,
    specificRows,
    representativeRows,
    activePeriod,
    activeTab,
    ocrLoadingRowId,
    crossCoverageGaps,
    occurrenceDebitChecked,
    occurrenceCreditChecked,
    postDebitChecked,
    postCreditChecked,
    debitRatio,
    creditRatio,
    incompleteRows,
    abnormalRows,
    unexplainedAbnormalRows,
    duplicateRows,
    rowValidationErrors,
    gateWarnings,
    loadRows,
    addRow,
    removeRow,
    setCheck,
    setManualAbnormal,
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled,
    onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    rowsToPersist,
    evaluateCrossCoverage,
    mapOcrToVoucherFields,
    handleRowOcr,
    applyConclusionTemplate,
    abnormalSummaryForAi,
    recalcAbnormal: recalcVoucherAbnormal,
    isAllChecked: isVoucherCheckComplete,
    toJSON,
  }
}

export default useG6EclVoucherCheck
