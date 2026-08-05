/**
 * samplingFillTarget — 抽凭回填的宿主侧共享件（sampling-compliance-closure R6）
 *
 * 背景（2026-08-04 实测）：81 个宿主引入 `GtVoucherSamplingEngine`，其中 **42 个丢弃
 * `filled` 载荷里的 `methodology`**，最极端者只做 `addRow(v.summary || v.voucherNo)`
 * —— 凭证号 / 日期 / 金额 / 科目全丢。留痕在 `workpaper_extraction_log` 里没丢，但
 * **底稿正文（打印件 / 归档件）不体现抽样方法学与样本关键字段**，而复核与归档看的是底稿。
 *
 * 本模块是零 Vue 依赖的纯函数集合，便于 PBT 与平台守卫交叉读取。
 *
 * Validates: Requirements 6.1, 6.5
 * Properties: Property 16, Property 17
 */

// ─── 方法学快照 ──────────────────────────────────────────────────────────────

/**
 * 抽样方法学快照（与 `GtVoucherSamplingEngine` 的 `SamplingFilledMethodology` 同构，
 * 额外容纳 `batchId` / `datasetId` 供归档追溯）。
 */
export interface SamplingMethodologySnapshot {
  samplingMethod: string
  samplingInterval: string | null
  sampleSize: number
  suggestedSampleSize: number | null
  tolerableMisstatement: number | string | null
  expectedMisstatement: number | string | null
  confidenceLevel: number | null
  accountCodes: string[]
  randomSeed: string | null
  /** 抽凭批次号（`workpaper_extraction_log.batch_id`） */
  batchId?: string | null
  /** 抽样框数据集版本（`ledger_datasets.id`）；序时账重导后据此判定不可复算 */
  datasetId?: string | null
}

/** 抽样方法中文名（与后端 `sampling_registry_service._METHOD_LABELS` 保持一致） */
export const SAMPLING_METHOD_LABELS: Readonly<Record<string, string>> = Object.freeze({
  random: '随机抽样',
  stratified: '金额分层抽样',
  specific_item: '特定项目选取',
  systematic: '系统（等距）抽样',
  mus: '货币单元抽样（MUS）',
})

/**
 * 方法学持久化键：一底稿一条，**最后一次抽样为准**。
 *
 * 不按 sheet 分键的理由：同一底稿的多个抽凭 sheet 共用一次抽样配置的场景占多数，
 * 而"这张底稿的样本是怎么抽的"是底稿级事实。需要多批次并存时读
 * `voucher-history`（后端按 batch 留全量）。
 */
export function samplingMethodologyItemKey(wpCode: string): string {
  const code = String(wpCode || '').trim()
  return code ? `${code}-sampling-methodology` : 'sampling-methodology'
}

/** 方法名 → 中文；未知方法原样返回（不吞掉未登记的新方法） */
export function samplingMethodLabel(method: string | null | undefined): string {
  const key = String(method || '')
  return SAMPLING_METHOD_LABELS[key] ?? (key || '未记录')
}

function hasValue(v: unknown): boolean {
  return v !== null && v !== undefined && v !== ''
}

/**
 * 方法学 → 一行中文摘要（供 bar 折叠态、导出、底稿备注复用）。
 *
 * 只渲染**有值**的项：缺省项直接不出现，而不是显示「间隔: -」——
 * 归档件上的「-」无法与「取不到」区分。
 */
export function buildMethodologySummary(
  m: SamplingMethodologySnapshot | null | undefined,
): string {
  if (!m) return ''
  const parts: string[] = [`方法=${samplingMethodLabel(m.samplingMethod)}`]
  if (m.accountCodes?.length) parts.push(`科目=${m.accountCodes.join('、')}`)
  parts.push(`样本量=${Number(m.sampleSize) || 0}`)
  if (hasValue(m.suggestedSampleSize)) parts.push(`系统建议=${m.suggestedSampleSize}`)
  if (hasValue(m.samplingInterval)) parts.push(`抽样间隔=${m.samplingInterval}`)
  if (hasValue(m.tolerableMisstatement)) parts.push(`可容忍错报=${m.tolerableMisstatement}`)
  if (hasValue(m.expectedMisstatement)) parts.push(`预期错报=${m.expectedMisstatement}`)
  if (hasValue(m.confidenceLevel)) parts.push(`置信度=${m.confidenceLevel}`)
  if (hasValue(m.randomSeed)) parts.push(`随机种子=${m.randomSeed}`)
  if (hasValue(m.batchId)) parts.push(`批次=${String(m.batchId).slice(0, 8)}`)
  if (hasValue(m.datasetId)) parts.push(`账套版本=${String(m.datasetId).slice(0, 8)}`)
  return parts.join('　')
}

/** 判定方法学是否有可展示内容（bar 的渲染门控，Property 17） */
export function hasMethodologyContent(
  m: SamplingMethodologySnapshot | null | undefined,
): boolean {
  if (!m || typeof m !== 'object') return false
  return Boolean(
    m.samplingMethod ||
      (Number(m.sampleSize) || 0) > 0 ||
      m.accountCodes?.length ||
      hasValue(m.samplingInterval) ||
      hasValue(m.randomSeed),
  )
}

/** 方法学序列化（写进 checklist remark 的 JSON 字符串；空内容返回空串不落库） */
export function serializeMethodology(
  m: SamplingMethodologySnapshot | null | undefined,
): string {
  if (!hasMethodologyContent(m)) return ''
  return JSON.stringify(m)
}

/** 方法学反序列化（宿主 seed 时用；解析失败返回 null 而非半个对象） */
export function parseMethodology(
  raw: string | null | undefined,
): SamplingMethodologySnapshot | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return hasMethodologyContent(parsed as SamplingMethodologySnapshot)
      ? (parsed as SamplingMethodologySnapshot)
      : null
  } catch {
    return null
  }
}

// ─── 样本 → 通用行的最小字段映射 ─────────────────────────────────────────────

/**
 * 抽凭样本的**最小字段集**（R6.5）。
 *
 * 宿主回填时至少要映射这 6 个字段 —— 只保留 `summary`/`voucherNo` 之一（当前 42 个
 * 宿主里最差的做法）会让底稿上的样本无法回溯到具体凭证。
 */
export interface GenericSampledRow {
  voucherNo: string
  voucherDate: string
  debitAmount: number
  creditAmount: number
  accountCode: string
  summary: string
  /**
   * 往来单位名称（客户/供应商/往来单位/职员），由后端
   * `enrich_items_with_aux_party` 按「凭证号+日期+科目+借贷金额」从
   * `tb_aux_ledger` 精确匹配补全。
   *
   * 空串有两种含义且**不可区分**（都如实留空，不猜）：
   * ①本项目该科目无辅助维度明细 ②同一键对应多个往来单位（歧义）。
   * 后者由 `partyAmbiguous` 标出，供 UI 提示"请人工选择"。
   */
  partyName: string
  /** 名称取自哪个辅助维度类型（如「客户」），供溯源展示 */
  partyAuxType: string
  /** 该行匹配到多个往来单位 ⇒ 后端刻意不填，需人工确认 */
  partyAmbiguous: boolean
}

/** 最小字段集的字段名（平台守卫据此断言宿主映射覆盖度） */
export const SAMPLING_MIN_FIELDS = [
  'voucherNo',
  'voucherDate',
  'debitAmount',
  'creditAmount',
  'accountCode',
  'summary',
] as const

function toNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function pick(src: Record<string, any>, ...keys: string[]): string {
  for (const k of keys) {
    const v = src[k]
    if (v !== null && v !== undefined && String(v).trim() !== '') return String(v).trim()
  }
  return ''
}

/**
 * `SampledVoucher`（或其 snake_case 变体）→ 通用最小行。
 *
 * 同时兼容 camelCase 与 snake_case：抽凭引擎发的是 camelCase，
 * 而部分宿主直接消费后端 items（snake_case），两者都要能映射。
 * 纯函数，不修改入参；非对象输入返回全空行（不抛错，避免一条脏样本打掉整批回填）。
 */
export function mapSampledToGenericRow(v: unknown): GenericSampledRow {
  const src = (v && typeof v === 'object' ? v : {}) as Record<string, any>
  return {
    voucherNo: pick(src, 'voucherNo', 'voucher_no'),
    voucherDate: pick(src, 'voucherDate', 'voucher_date'),
    debitAmount: toNum(src.debitAmount ?? src.debit_amount),
    creditAmount: toNum(src.creditAmount ?? src.credit_amount),
    accountCode: pick(src, 'accountCode', 'account_code'),
    summary: pick(src, 'summary', 'businessContent', 'business_content', 'remark'),
    partyName: pick(src, 'partyName', 'party_name'),
    partyAuxType: pick(src, 'partyAuxType', 'party_aux_type'),
    partyAmbiguous:
      src.partyAmbiguous === true || src.party_ambiguous === true,
  }
}

/** 批量映射 + 过滤掉「凭证号与摘要都为空」的空行（这类行进底稿没有意义） */
export function mapSampledRows(list: unknown): GenericSampledRow[] {
  if (!Array.isArray(list)) return []
  return list
    .map(mapSampledToGenericRow)
    .filter((r) => r.voucherNo !== '' || r.summary !== '')
}
