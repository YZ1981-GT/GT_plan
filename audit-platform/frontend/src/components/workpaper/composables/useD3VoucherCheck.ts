/**
 * useD3VoucherCheck — D3-7 预收账款检查表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 13.1
 *
 * 职责：
 * - 定义 VoucherCheckRow/SamplingParams 类型
 * - samplingParams reactive
 * - currentChangeRows（本期增减17列）+ postPeriodRows（期后结转16列）
 * - totalChecked/anomalyCount/anomalyRate computed
 * - addSample/removeSample/updateCell
 * - autoMarkCrossPeriod（日期<收入确认日→标"跨期疑点"）
 *
 * Requirements: 11.1-11.9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { parseNum, calcAnomalyRate } from './useD3FormulaEngine'
import { partyNameForColumn } from './shared/samplingPartyTarget'
import type { ChecklistResponse } from './useD3FormData'
import type { FillMode } from './useSamplingAlgorithms'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface VoucherCheckRow {
  rowId: string
  customerName: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetailAccount: string
  debitAmount?: number       // 仅(1)本期增减有此列
  creditAmount: number
  supportingDoc: string
  checkItems: [boolean, boolean, boolean, boolean, boolean]
  indexRef: string
  isAbnormal: string         // 是否异常
  remark: string
  attachment?: string        // 已关联附件文件名（OCR/证据）
  source?: '手工' | '抽凭'    // 行来源：手工录入 / 抽凭引擎回填（Req 7.6 / 24.5）
  actualMisstatement?: number // 审计师录入的该行实际错报金额（Req 18）
}

/**
 * 抽样引擎回填样本（子集，仅回填映射所需字段；与 useSamplingAlgorithms.SampledVoucher 结构兼容）。
 */
export interface SampledVoucherLike {
  /** 往来单位名称（后端 tb_aux_ledger 补全）；未匹配/歧义时为 null，不得臆造 */
  partyName?: string | null
  voucherNo: string
  voucherDate?: string | null
  summary?: string | null
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  counterpartAccount?: string | null
  accountCode?: string | null
  actualMisstatement?: string | number | null
}

export interface SamplingParams {
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingMethod: string
  samplingProcess: string
  targetSampleSize: number
  currentSampleSize: number
}

export interface UseD3VoucherCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_PARAMS = 'D3-vc-params'
const ITEM_ID_CURRENT_ROWS = 'D3-vc-current-rows'
const ITEM_ID_POST_ROWS = 'D3-vc-post-rows'
const ITEM_ID_CONCLUSION = 'D3-vc-conclusion'

/**
 * D3-7 检查表 5 项核对内容标签（对齐源模板「测试内容说明」R13）。
 * checkItems[0..4] 与此一一对应。
 */
export const D3_VOUCHER_CHECK_ITEMS = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确',
  '是否记录于恰当的会计期间',
  '其他核对事项',
] as const

// ─── Pure Helpers (exported for PBT testability) ─────────────────────────────

/**
 * 计算异常率（纯函数，方便 PBT 测试）
 *
 * anomalyRate = 非空 isAbnormal 行数 / 总行数 × 100
 */
export function computeAnomalyRate(rows: { isAbnormal: string }[]): number {
  if (rows.length === 0) return 0
  const anomalyCount = rows.filter(r => r.isAbnormal !== '' && r.isAbnormal !== null && r.isAbnormal !== undefined).length
  return calcAnomalyRate(anomalyCount, rows.length)
}

/**
 * 判断是否应标记跨期疑点（纯函数，方便 PBT 测试）
 *
 * 当凭证日期早于收入确认日期时，返回 true。
 */
export function shouldMarkCrossPeriod(voucherDate: Date, revenueDate: Date): boolean {
  return voucherDate < revenueDate
}

/** 跨期疑点异常类型常量（跨底稿联动至 D4 收入截止测试的判定依据，Req 11.2） */
export const CROSS_PERIOD_ANOMALY = '跨期疑点'

/**
 * 异常汇总（纯函数，方便 PBT 测试）。
 *
 * 统计异常总笔数、跨期疑点笔数（→ D4 可追溯）、按异常类型分组计数（→ A13 可追溯）。
 * 空 isAbnormal（''/null/undefined）不计入异常。
 *
 * Requirements: 11.1, 11.2, 11.3, 11.4
 */
export function summarizeAnomalies(rows: { isAbnormal: string }[]): {
  total: number
  crossPeriod: number
  byType: Record<string, number>
} {
  const byType: Record<string, number> = {}
  let total = 0
  let crossPeriod = 0
  for (const r of rows) {
    const type = r.isAbnormal
    if (type == null || type === '') continue
    total += 1
    byType[type] = (byType[type] || 0) + 1
    if (type === CROSS_PERIOD_ANOMALY) crossPeriod += 1
  }
  return { total, crossPeriod, byType }
}

/** 覆盖率/代表性反馈结果（检查表汇总区展示，Req 8） */
export interface VoucherCoverageFeedback {
  /** 已检查笔数 */
  checkedCount: number
  /** 目标样本量（抽样参数 targetSampleSize） */
  targetSampleSize: number
  /** 笔数覆盖率 = 已检查 / 目标样本量 × 100（无目标时：有检查行→100，否则 0；上限 100） */
  countCoverageRate: number
  /** 已完成核对笔数（5 个核对项全部勾选） */
  completedCount: number
  /** 核对完成率 = 已完成 / 已检查 × 100 */
  completionRate: number
  /** 已检查金额合计（借方 + 贷方，单位：元） */
  checkedAmount: number
  /** 覆盖率偏低：设定了目标样本量但已检查笔数不足 */
  lowCoverage: boolean
}

/**
 * 计算覆盖率/代表性反馈（纯函数，方便 PBT 测试）。
 *
 * 以检查表已检查行相对目标样本量的笔数覆盖率、核对完成率与已检查金额合计，
 * 呈现抽样的充分性与代表性反馈（Req 8.1/8.2/8.3/8.5）。
 *
 * @param rows 已检查行（两区块合并）
 * @param targetSampleSize 抽样参数中的目标样本量
 */
export function computeCoverageFeedback(
  rows: VoucherCheckRow[],
  targetSampleSize: number,
): VoucherCoverageFeedback {
  const checkedCount = rows.length
  const target = targetSampleSize > 0 ? targetSampleSize : 0
  const completedCount = rows.filter(
    r => Array.isArray(r.checkItems) && r.checkItems.length > 0 && r.checkItems.every(Boolean),
  ).length
  const checkedAmount = rows.reduce(
    (sum, r) => sum + parseNum(r.debitAmount) + parseNum(r.creditAmount),
    0,
  )
  const countCoverageRate = target > 0
    ? Math.min(100, (checkedCount / target) * 100)
    : (checkedCount > 0 ? 100 : 0)
  const completionRate = checkedCount > 0 ? (completedCount / checkedCount) * 100 : 0
  const lowCoverage = target > 0 && checkedCount < target
  return {
    checkedCount,
    targetSampleSize: target,
    countCoverageRate,
    completedCount,
    completionRate,
    checkedAmount,
    lowCoverage,
  }
}

// ─── OCR 字段映射（复用 /d4/contract-ocr 范式，参照 G4/G6） ────────────────────

/** 低置信度阈值：识别结果置信度低于此值需人工复核（Confidence_Threshold） */
export const CONFIDENCE_THRESHOLD = 0.8

/** OCR 识别键 → VoucherCheckRow 字段（Req 2.2） */
export const OCR_FIELD_MAP: Record<string, keyof VoucherCheckRow> = {
  客户名称: 'customerName',
  对方单位: 'customerName',
  对方名称: 'customerName',
  counterparty: 'customerName',
  日期: 'date',
  凭证日期: 'date',
  signDate: 'date',
  凭证号: 'voucherNo',
  凭证编号: 'voucherNo',
  voucherNo: 'voucherNo',
  contractNo: 'voucherNo',
  摘要: 'businessContent',
  业务内容: 'businessContent',
  serviceContent: 'businessContent',
  businessContent: 'businessContent',
  对方科目: 'counterAccount',
  counterAccount: 'counterAccount',
  金额: 'creditAmount',
  贷方金额: 'creditAmount',
  贷方: 'creditAmount',
  contractAmount: 'creditAmount',
  借方金额: 'debitAmount',
  借方: 'debitAmount',
}

/** 字段中文标签（确认弹窗预览用） */
const OCR_FIELD_LABELS: Partial<Record<keyof VoucherCheckRow, string>> = {
  customerName: '客户名称',
  date: '日期',
  voucherNo: '凭证号',
  businessContent: '业务内容',
  counterAccount: '对方科目',
  debitAmount: '借方金额',
  creditAmount: '贷方金额',
}

/**
 * 将 OCR 识别字段映射为 VoucherCheckRow 可 merge 的字段对象（纯函数，方便测试）。
 *
 * - 仅映射 OCR_FIELD_MAP 中已知的键；空值/空白跳过。
 * - 金额字段走 parseNum，解析为 0 则跳过（视为无有效值）。
 * - 支持值为 `{ value, confidence }` 形态或标量 + 整体置信度；
 *   当某字段的有效置信度低于 CONFIDENCE_THRESHOLD 时计入 lowConfidence（Req 2.8）。
 *
 * @param fields OCR 返回的 extracted_fields
 * @param confidence 整体置信度（可选，端点仅返回整体置信度时使用）
 */
export function mapOcrToVoucherFields(
  fields: Record<string, any>,
  confidence?: number,
): { patch: Partial<VoucherCheckRow>; lowConfidence: (keyof VoucherCheckRow)[] } {
  const patch: Partial<VoucherCheckRow> = {}
  const lowConfidence: (keyof VoucherCheckRow)[] = []
  if (!fields || typeof fields !== 'object') return { patch, lowConfidence }

  for (const [ocrKey, raw] of Object.entries(fields)) {
    const target = OCR_FIELD_MAP[ocrKey]
    if (!target) continue

    // 兼容 { value, confidence } 与标量
    let val: any = raw
    let conf: number | undefined = confidence
    if (raw && typeof raw === 'object' && 'value' in raw) {
      val = (raw as any).value
      conf = (raw as any).confidence ?? confidence
    }
    if (val == null || String(val).trim() === '') continue

    if (target === 'debitAmount' || target === 'creditAmount') {
      const num = parseNum(val)
      if (num === 0) continue
      ;(patch as any)[target] = num
    } else {
      ;(patch as any)[target] = String(val).trim()
    }

    if (conf != null && conf < CONFIDENCE_THRESHOLD && !lowConfidence.includes(target)) {
      lowConfidence.push(target)
    }
  }

  return { patch, lowConfidence }
}

/**
 * merge 语义：仅保留 patch 中「当前行为空」的字段，
 * 避免覆盖 Auditor 已手工录入的值（Req 2.4 保留已填值）。
 */
function computeMergePatch(row: VoucherCheckRow, patch: Partial<VoucherCheckRow>): Partial<VoucherCheckRow> {
  const merged: Partial<VoucherCheckRow> = {}
  for (const [key, val] of Object.entries(patch)) {
    const cur = (row as any)[key]
    const isEmpty = cur == null || cur === '' || (typeof cur === 'number' && cur === 0)
    if (isEmpty) (merged as any)[key] = val
  }
  return merged
}

/** 渲染 OCR 识别结果确认弹窗 HTML（低置信度字段标注需人工复核，Req 2.8） */
function renderOcrPreview(
  patch: Partial<VoucherCheckRow>,
  lowConfidence: (keyof VoucherCheckRow)[],
  confidence: number,
): string {
  const lines = Object.entries(patch).map(([key, val]) => {
    const label = OCR_FIELD_LABELS[key as keyof VoucherCheckRow] || key
    const low = lowConfidence.includes(key as keyof VoucherCheckRow)
    const tag = low ? '<span style="color:#e6a23c;margin-left:6px">⚠ 需人工复核</span>' : ''
    return `<div style="margin:4px 0"><strong>${label}：</strong>${val}${tag}</div>`
  })
  const confPct = (confidence * 100).toFixed(0)
  const confColor = confidence >= CONFIDENCE_THRESHOLD ? '#67c23a' : '#e6a23c'
  return `
    <div style="font-size:13px">
      <div style="margin-bottom:8px;color:${confColor}">
        整体置信度：${confPct}%${confidence < CONFIDENCE_THRESHOLD ? '（建议人工核对）' : ''}
      </div>
      ${lines.length ? lines.join('') : '<div style="color:#909399">未提取到有效字段</div>'}
    </div>
  `.trim()
}

/** 校验附件类型：仅接受图片与 PDF（Req 1.2 / 1.5） */
export function isAllowedAttachment(file: File): boolean {
  const type = file.type || ''
  if (type.startsWith('image/') || type === 'application/pdf') return true
  return /\.(jpe?g|png|gif|bmp|webp|pdf)$/i.test(file.name || '')
}

// ─── 抽凭回填（Req 4/7/24：抽样样本 → 检查表行） ─────────────────────────────

/**
 * 将抽样引擎样本映射为 VoucherCheckRow（凭证号/日期/金额/摘要/对方科目），
 * 并标注来源为「抽凭」（Req 7.2 / 7.6 / 24.5）。纯函数，方便 PBT/单测。
 */
export function mapSampledToVoucherRow(s: SampledVoucherLike): VoucherCheckRow {
  const debit = s.debitAmount != null ? parseNum(s.debitAmount) : undefined
  return {
    rowId: generateRowId(),
    // 客户名称 = 辅助明细账（tb_aux_ledger）精确匹配出的往来单位，**经语义门控**。
    // D3 预收款项这一列语义是「客户」（付款方），故只接受来自「客户/往来单位」
    // 维度的名称；来自「职员」等维度一律不填（备用金往来不是客户）。
    // 匹配不到 / 一键多名 / 维度不符 → 留空由审计师填，**绝不猜**。
    customerName: partyNameForColumn(s, 'customer'),
    date: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    counterAccount: s.counterpartAccount || '',
    counterDetailAccount: '',
    debitAmount: debit,
    creditAmount: parseNum(s.creditAmount ?? 0),
    supportingDoc: '',
    checkItems: [false, false, false, false, false],
    indexRef: '',
    isAbnormal: '',
    remark: '',
    attachment: undefined,
    source: '抽凭',
    actualMisstatement: s.actualMisstatement != null ? parseNum(s.actualMisstatement) : undefined,
  }
}

/**
 * 抽样回填三模式（复用 applyFillMode 语义，keyed by voucherNo）。纯函数，方便 PBT/单测。
 *
 * - append: 将 incoming 追加到 existing 末尾（Req 7.5）
 * - replace: 以 incoming 替换目标区块现有行（Req 7.3）
 * - merge: 按 voucherNo 去重后追加 incoming 中的新增项（Req 7.4）
 *
 * 空 voucherNo 的行不参与去重，一律保留（merge 时始终追加）。
 */
export function applyVoucherFillMode(
  existing: VoucherCheckRow[],
  incoming: VoucherCheckRow[],
  mode: FillMode,
): VoucherCheckRow[] {
  switch (mode) {
    case 'replace':
      return [...incoming]
    case 'merge': {
      // 去重集合含既有行 voucherNo，并随处理逐步纳入 incoming 已接受的 voucherNo，
      // 保证 merge 后同区块内非空 voucherNo 唯一（design Property 8）。
      const seenNos = new Set(existing.map(r => r.voucherNo).filter(Boolean))
      const newItems: VoucherCheckRow[] = []
      for (const r of incoming) {
        if (!r.voucherNo) { newItems.push(r); continue }  // 空号不去重
        if (seenNos.has(r.voucherNo)) continue
        seenNos.add(r.voucherNo)
        newItems.push(r)
      }
      return [...existing, ...newItems]
    }
    case 'append':
    default:
      return [...existing, ...incoming]
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseRows(jsonStr: string | null | undefined): VoucherCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): VoucherCheckRow {
  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterDetailAccount: raw.counterDetailAccount || '',
    debitAmount: raw.debitAmount !== undefined ? parseNum(raw.debitAmount) : undefined,
    creditAmount: parseNum(raw.creditAmount),
    supportingDoc: raw.supportingDoc || '',
    checkItems: Array.isArray(raw.checkItems) && raw.checkItems.length === 5
      ? raw.checkItems as [boolean, boolean, boolean, boolean, boolean]
      : [false, false, false, false, false],
    indexRef: raw.indexRef || '',
    isAbnormal: raw.isAbnormal || '',
    remark: raw.remark || '',
    attachment: raw.attachment || undefined,
    source: raw.source === '抽凭' ? '抽凭' : (raw.source === '手工' ? '手工' : undefined),
    actualMisstatement: raw.actualMisstatement !== undefined && raw.actualMisstatement !== null
      ? parseNum(raw.actualMisstatement)
      : undefined,
  }
}

function createEmptyRow(section: 'current' | 'postPeriod'): VoucherCheckRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetailAccount: '',
    debitAmount: section === 'current' ? 0 : undefined,
    creditAmount: 0,
    supportingDoc: '',
    checkItems: [false, false, false, false, false],
    indexRef: '',
    isAbnormal: '',
    remark: '',
    attachment: undefined,
    source: '手工',
    actualMisstatement: undefined,
  }
}

function safeParseParams(jsonStr: string | null | undefined): SamplingParams {
  const defaults: SamplingParams = {
    testPopulation: '',
    specificSamples: '',
    samplingPopulation: '',
    samplingMethod: '',
    samplingProcess: '',
    targetSampleSize: 0,
    currentSampleSize: 0,
  }
  if (!jsonStr) return defaults
  try {
    const parsed = JSON.parse(jsonStr)
    return { ...defaults, ...parsed }
  } catch {
    return defaults
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3VoucherCheck(options: UseD3VoucherCheckOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  // ─── Sampling Params ─────────────────────────────────────────────────

  const samplingParams = ref<SamplingParams>(safeParseParams(null))

  watch(
    () => allResponses.value.get(ITEM_ID_PARAMS)?.remark,
    (jsonStr) => { samplingParams.value = safeParseParams(jsonStr) },
    { immediate: true },
  )

  function updateSamplingParams(field: string, value: any): void {
    if (isReadonly.value) return
    ;(samplingParams.value as any)[field] = value
    debouncedSave(ITEM_ID_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  // ─── 检查结论（AI 辅助文本，持久化至 checklist_responses.remark） ──────────

  const conclusion = ref<string>('')

  watch(
    () => allResponses.value.get(ITEM_ID_CONCLUSION)?.remark,
    (jsonStr) => { conclusion.value = jsonStr || '' },
    { immediate: true },
  )

  /** 更新检查结论文本（Req 3.4：AI 建议确认后写入 / 手工编辑） */
  function updateConclusion(text: string): void {
    if (isReadonly.value) return
    conclusion.value = text
    debouncedSave(ITEM_ID_CONCLUSION, { remark: text })
  }

  // ─── Current Change Rows (1)本期增减 ─────────────────────────────────

  const currentChangeRows = ref<VoucherCheckRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_CURRENT_ROWS)?.remark,
    (jsonStr) => { currentChangeRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Post Period Rows (2)期后结转 ────────────────────────────────────

  const postPeriodRows = ref<VoucherCheckRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_POST_ROWS)?.remark,
    (jsonStr) => { postPeriodRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistCurrentRows(): void {
    debouncedSave(ITEM_ID_CURRENT_ROWS, { remark: JSON.stringify(currentChangeRows.value) })
  }

  function persistPostRows(): void {
    debouncedSave(ITEM_ID_POST_ROWS, { remark: JSON.stringify(postPeriodRows.value) })
  }

  // ─── Computed: totals ────────────────────────────────────────────────

  const totalChecked: ComputedRef<number> = computed(() => {
    return currentChangeRows.value.length + postPeriodRows.value.length
  })

  const anomalyCount: ComputedRef<number> = computed(() => {
    const allRows = [...currentChangeRows.value, ...postPeriodRows.value]
    return allRows.filter(r => r.isAbnormal !== '').length
  })

  const anomalyRate: ComputedRef<number> = computed(() => {
    return computeAnomalyRate([...currentChangeRows.value, ...postPeriodRows.value])
  })

  // ─── 异常汇总与跨底稿联动（Req 11.2/11.4）+ 覆盖率反馈（Req 8） ──────────

  /** 异常汇总：总笔数 / 跨期疑点笔数（→D4）/ 按类型分组（→A13） */
  const anomalySummary = computed(() =>
    summarizeAnomalies([...currentChangeRows.value, ...postPeriodRows.value]),
  )

  /** 跨期疑点笔数（保留与 D4 收入截止测试的可追溯关联标识，Req 11.2） */
  const crossPeriodCount: ComputedRef<number> = computed(() => anomalySummary.value.crossPeriod)

  /** 覆盖率/代表性反馈（Req 8.1/8.2/8.3/8.5） */
  const coverageFeedback = computed(() =>
    computeCoverageFeedback(
      [...currentChangeRows.value, ...postPeriodRows.value],
      samplingParams.value.targetSampleSize,
    ),
  )

  // ─── addSample / removeSample / updateCell ───────────────────────────

  function addSample(section: 'current' | 'postPeriod'): void {
    if (isReadonly.value) return
    const newRow = createEmptyRow(section)
    if (section === 'current') {
      currentChangeRows.value = [...currentChangeRows.value, newRow]
      persistCurrentRows()
    } else {
      postPeriodRows.value = [...postPeriodRows.value, newRow]
      persistPostRows()
    }
  }

  function removeSample(section: 'current' | 'postPeriod', rowId: string): void {
    if (isReadonly.value) return
    if (section === 'current') {
      currentChangeRows.value = currentChangeRows.value.filter(r => r.rowId !== rowId)
      persistCurrentRows()
    } else {
      postPeriodRows.value = postPeriodRows.value.filter(r => r.rowId !== rowId)
      persistPostRows()
    }
  }

  function updateCell(section: 'current' | 'postPeriod', rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const rows = section === 'current' ? currentChangeRows.value : postPeriodRows.value
    const idx = rows.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = parseNum(value)
    } else if (field.startsWith('checkItems.')) {
      const checkIdx = parseInt(field.replace('checkItems.', ''), 10)
      if (checkIdx >= 0 && checkIdx < 5) {
        row.checkItems = [...row.checkItems] as [boolean, boolean, boolean, boolean, boolean]
        row.checkItems[checkIdx] = Boolean(value)
      }
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...rows]
    newRows[idx] = row

    if (section === 'current') {
      currentChangeRows.value = newRows
      persistCurrentRows()
    } else {
      postPeriodRows.value = newRows
      persistPostRows()
    }
  }

  // ─── updateRow：批量合并一行的多个字段并单次持久化（引导式弹窗保存用） ──────

  /**
   * 将 patch 合并到指定区块的某行并单次持久化（用于逐笔核对引导弹窗保存）。
   * 避免逐字段 updateCell 触发多次防抖保存。
   */
  function updateRow(
    section: 'current' | 'postPeriod',
    rowId: string,
    patch: Partial<VoucherCheckRow>,
  ): void {
    if (isReadonly.value) return
    const list = section === 'current' ? currentChangeRows.value : postPeriodRows.value
    const idx = list.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const merged = [...list]
    merged[idx] = { ...merged[idx], ...patch, rowId }
    if (section === 'current') {
      currentChangeRows.value = merged
      persistCurrentRows()
    } else {
      postPeriodRows.value = merged
      persistPostRows()
    }
  }

  // ─── 抽凭回填（Req 4/7/24：抽样弹窗结果 → 检查表行，来源=抽凭） ──────────

  /**
   * 将抽样引擎回传的样本按填充模式回写到指定区块，行来源标注为「抽凭」。
   *
   * - 复用 applyFillMode 的 append/replace/merge 语义（keyed by voucherNo）。
   * - 只读状态禁用回填（Req 12.3）。
   *
   * @param samples  抽样引擎 @filled 回调的样本集合
   * @param fillMode 填充模式（append/replace/merge）
   * @param section  目标区块（本期增减 / 期后结转）
   * @returns 实际回填的样本数量
   */
  function fillFromSampling(
    samples: SampledVoucherLike[],
    fillMode: FillMode,
    section: 'current' | 'postPeriod',
  ): number {
    if (isReadonly.value) return 0
    if (!Array.isArray(samples) || samples.length === 0) return 0

    const incoming = samples.map(mapSampledToVoucherRow)

    if (section === 'current') {
      currentChangeRows.value = applyVoucherFillMode(currentChangeRows.value, incoming, fillMode)
      persistCurrentRows()
    } else {
      postPeriodRows.value = applyVoucherFillMode(postPeriodRows.value, incoming, fillMode)
      persistPostRows()
    }
    return incoming.length
  }

  // ─── 行级 OCR（复用 /d4/contract-ocr 范式，参照 G4/G6） ────────────────

  /** 正在执行 OCR 的行 rowId（用于 loading 态） */
  const ocrLoadingRowId = ref<string | null>(null)

  /**
   * 行级 OCR：上传 → POST /d4/contract-ocr → 映射 → ElMessageBox 确认（低置信度标注）
   * → merge 写入行（保留已填值）。始终返回 false 以阻止 el-upload 默认上传行为。
   *
   * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 1.5
   */
  async function handleRowOcr(section: 'current' | 'postPeriod', rowId: string, file: File): Promise<boolean> {
    if (isReadonly.value) return false
    if (!options.wpId.value) return false

    // 文件类型校验（Req 1.5）
    if (!isAllowedAttachment(file)) {
      ElMessage.error('仅支持图片或 PDF 格式的附件')
      return false
    }

    const rows = section === 'current' ? currentChangeRows.value : postPeriodRows.value
    const idx = rows.findIndex(r => r.rowId === rowId)
    if (idx === -1) return false

    ocrLoadingRowId.value = rowId
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${options.wpId.value}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields: Record<string, any> = data?.extracted_fields || {}
      const confidence: number = data?.confidence ?? 0

      if (!Object.keys(fields).length) {
        ElMessage.info('OCR 完成，未识别到可填充字段')  // Req 2.6
        return false
      }

      const { patch, lowConfidence } = mapOcrToVoucherFields(fields, confidence)
      if (Object.keys(patch).length === 0) {
        ElMessage.info('OCR 完成，识别字段无法匹配当前行')  // Req 2.6
        return false
      }

      // merge：仅填充当前行为空的字段，保留已手工录入值（Req 2.4）
      const targetRow = (section === 'current' ? currentChangeRows.value : postPeriodRows.value)
        .find(r => r.rowId === rowId)
      if (!targetRow) return false
      const mergePatch = computeMergePatch(targetRow, patch)

      // 确认弹窗（展示映射结果 + 低置信度标注，Req 2.3 / 2.8）
      await ElMessageBox.confirm(
        renderOcrPreview(mergePatch, lowConfidence, confidence),
        'OCR 识别结果',
        {
          confirmButtonText: '填入',
          cancelButtonText: '取消',
          dangerouslyUseHTMLString: true,
          type: confidence < CONFIDENCE_THRESHOLD ? 'warning' : 'info',
        },
      )

      // 确认后 merge 写入 + 记录附件名（Req 2.4 / 1.3）
      const list = section === 'current' ? [...currentChangeRows.value] : [...postPeriodRows.value]
      const i = list.findIndex(r => r.rowId === rowId)
      if (i === -1) return false
      list[i] = { ...list[i], ...mergePatch, attachment: file.name }
      if (section === 'current') {
        currentChangeRows.value = list
        persistCurrentRows()
      } else {
        postPeriodRows.value = list
        persistPostRows()
      }
      ElMessage.success('已填入 OCR 识别结果')
    } catch (e: any) {
      // ElMessageBox 取消抛 'cancel'：保持行字段不变（Req 2.5），不提示失败
      if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
        ElMessage.warning('OCR 识别失败，请稍后重试')  // Req 2.7
      }
    } finally {
      ocrLoadingRowId.value = null
    }
    return false  // 阻止 el-upload 默认上传
  }

  // ─── autoMarkCrossPeriod ─────────────────────────────────────────────

  /**
   * 自动标记跨期疑点：当凭证日期早于收入确认日期时，
   * 标记 isAbnormal 为"跨期疑点"。
   *
   * @param revenueRecognitionDate 收入确认日期字符串（如"2025-12-31"）
   */
  function autoMarkCrossPeriod(revenueRecognitionDate: string): void {
    if (isReadonly.value) return
    if (!revenueRecognitionDate) return

    const revenueDate = new Date(revenueRecognitionDate)
    if (isNaN(revenueDate.getTime())) return

    let changed = false
    const newRows = postPeriodRows.value.map(row => {
      if (!row.date) return row
      const voucherDate = new Date(row.date)
      if (isNaN(voucherDate.getTime())) return row

      if (shouldMarkCrossPeriod(voucherDate, revenueDate) && row.isAbnormal !== '跨期疑点') {
        changed = true
        return { ...row, isAbnormal: '跨期疑点' }
      }
      return row
    })

    if (changed) {
      postPeriodRows.value = newRows
      persistPostRows()
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    samplingParams,
    currentChangeRows,
    postPeriodRows,
    totalChecked,
    anomalyCount,
    anomalyRate,
    anomalySummary,
    crossPeriodCount,
    coverageFeedback,
    addSample,
    removeSample,
    updateCell,
    updateRow,
    updateSamplingParams,
    autoMarkCrossPeriod,
    // 检查结论（AI 辅助）
    conclusion,
    updateConclusion,
    // 抽凭回填
    fillFromSampling,
    // OCR
    ocrLoadingRowId,
    handleRowOcr,
    mapOcrToVoucherFields,
  }
}

export default useD3VoucherCheck
