/**
 * importE0ListsToSummary — E0 发函记录表（E0-3~E0-6，d-form-table）→ E0-1 函证结果汇总带入
 *
 * 口径唯一裁决者 = 源模板 `函证结果汇总表E0-1` 的 F 列（发函金额（原币））嵌套公式：
 *
 *   =IF(OR(D="银行存款",D="其他货币资金"),
 *        SUMIF(E0-3!$G:$G, E0-1!$E, E0-3!$K:$K),                 // 银行账号 → 账户余额（原币）
 *     IF(OR(D="短期借款",D="长期借款"),
 *        SUMIFS(E0-4!$I:$I, E0-4!$A:$A, E0-1!$D, E0-4!$G:$G, E0-1!$E),  // (所属科目, 借款账号) → 余额
 *     IF(D="应付票据",
 *        SUMIF(E0-5!$A:$A, E0-1!$B, E0-5!$G:$G),                 // 索引号 → 票面金额（一函多票求和）
 *     IF(D="理财产品",
 *        SUMIFS(E0-6!$H:$H, E0-6!$A:$A, E0-1!$B, E0-6!$D:$D, E0-1!$E), // (索引号, 产品名称) → 产品净值
 *     0))))
 *
 * 由此得到四条互不相同的口径（`E0_LIST_SPECS` 是唯一真源）：
 *
 * | 清单 | 源 tab                      | 是否函证列 | 聚合键              | 金额列        | 品种          |
 * |------|-----------------------------|-----------|---------------------|---------------|---------------|
 * | E0-3 | 货币资金发函记录表E0-3      | 有(E 列)  | 银行账号            | 账户余额（原币） | 按所属科目细分 |
 * | E0-4 | 借款发函记录表E0-4          | 有(E 列)  | 所属科目 + 借款账号 | 余额          | 按所属科目细分 |
 * | E0-5 | 应付银行承兑汇票发函记录表E0-5 | **无**   | **索引号**（一函多票）| 票面金额      | 应付票据      |
 * | E0-6 | 理财产品发函记录表E0-6      | **无**    | 索引号 + 产品名称   | 产品净值      | 理财产品      |
 *
 * 🔴 E0-5 / E0-6 源模板**没有「是否函证」列**（10 / 11 列逐格实证）——
 * 它们整表就是发函记录，不能套 E0-3/E0-4 的「是否函证=是」门控，否则这两品种恒产出 0 行。
 * 🔴 E0-5 是四张里唯一**单条件按索引号汇总**的：一份询证函可覆盖多张银行承兑汇票，
 * 发函金额 = 该索引号下全部票面金额之和；按「银行+品种」去重会把多张票压成一张、金额少算。
 * 🔴 E0-4 的品种权威列是 **A 列「所属科目」**（E0-1 SUMIFS 就按它匹配），
 * O 列「借款类型」只是补充信息列，仅作兜底。
 */
import { fetchWorkpaperHtmlRows } from './importFromSummary'
import type { ConfirmationRow } from '../confirmationTypes'

/** 单张 E0 发函记录表的取数口径声明（源模板列名逐字） */
export interface E0ListSpec {
  /** 源 xlsx tab 名（逐字，供守卫与用户提示） */
  sheetName: string
  /**
   * 可接受的 `html_data._format`（按序尝试）。
   * 通用 `d-form-table` 用中文列名作键；专属组件（如 E0-6 `wealth-list-v1`）用英文字段名，
   * 故各 keys 数组同时登记两套别名。
   */
  formats: string[]
  /** 源模板是否有「是否函证」列（无 → 整表即发函记录，不做门控） */
  hasConfirmFlag: boolean
  /** 索引号列候选（顺序即优先级） */
  indexKeys: string[]
  /** 被询证单位（开户银行）列候选 */
  entityKeys: string[]
  /** 金额列候选：首项必须是源模板逐字列名 */
  amountKeys: string[]
  /** E0-1「账号/理财产品名称」对应列候选 */
  accountNoKeys: string[]
  /** 币种列候选 */
  currencyKeys: string[]
  /** 品种判定列候选（顺序即优先级；空数组 = 品种固定） */
  subtypeKeys: string[]
  /** 品种固定值 / 判定失败时的兜底值 */
  defaultAccountType: string
  /** E0-1 F 列的聚合口径 */
  groupBy: 'index' | 'accountNo' | 'index+accountNo'
}

export const E0_LIST_SPECS: Record<string, E0ListSpec> = {
  'E0-3': {
    sheetName: '货币资金发函记录表E0-3',
    formats: ['d-form-table'],
    hasConfirmFlag: true,
    indexKeys: ['索引号', 'confirm_index'],
    entityKeys: ['开户银行', '账户名称'],
    amountKeys: ['账户余额（原币）', '账户余额(原币)', '账户余额'],
    accountNoKeys: ['银行账号'],
    currencyKeys: ['币种', 'currency'],
    subtypeKeys: ['所属科目', '账户类型'],
    defaultAccountType: '银行存款',
    groupBy: 'accountNo',
  },
  'E0-4': {
    sheetName: '借款发函记录表E0-4',
    formats: ['d-form-table'],
    hasConfirmFlag: true,
    indexKeys: ['索引号', 'confirm_index'],
    entityKeys: ['开户银行', '借款人名称'],
    amountKeys: ['余额'],
    accountNoKeys: ['借款账号'],
    currencyKeys: ['币种', 'currency'],
    // A 列「所属科目」是 E0-1 SUMIFS 的匹配列 → 权威；O 列「借款类型」仅兜底
    subtypeKeys: ['所属科目', '借款类型'],
    defaultAccountType: '短期借款',
    groupBy: 'accountNo',
  },
  'E0-5': {
    sheetName: '应付银行承兑汇票发函记录表E0-5',
    formats: ['d-form-table'],
    hasConfirmFlag: false,
    indexKeys: ['索引号', 'confirm_index'],
    entityKeys: ['开户银行'],
    amountKeys: ['票面金额'],
    accountNoKeys: ['结算账户账号'],
    currencyKeys: ['币种', 'currency'],
    subtypeKeys: [],
    defaultAccountType: '应付票据',
    groupBy: 'index',
  },
  'E0-6': {
    sheetName: '理财产品发函记录表E0-6',
    // 专属组件 `wealth-list-v1` 已上线（英文字段名），通用 d-form-table 保留兼容
    formats: ['wealth-list-v1', 'd-form-table'],
    hasConfirmFlag: false,
    indexKeys: ['索引号', 'confirm_index'],
    entityKeys: ['开户行名称及收件人', 'bank_and_recipient'],
    // 金额取「产品净值」总额口径；禁「持有份额 × 净值」
    amountKeys: ['产品净值', 'net_value'],
    accountNoKeys: ['产品名称', 'product_name'],
    currencyKeys: ['币种', 'currency'],
    subtypeKeys: [],
    defaultAccountType: '理财产品',
    groupBy: 'index+accountNo',
  },
}

/** E0 清单 sheet 编码 → 默认品种（account_type）；由 E0_LIST_SPECS 派生，勿另写一份 */
export const E0_LIST_ACCOUNT_TYPE: Record<string, string> = Object.fromEntries(
  Object.entries(E0_LIST_SPECS).map(([code, spec]) => [code, spec.defaultAccountType]),
)

/** 「是否函证」列的候选列名 */
const CONFIRM_FLAG_KEYS = ['是否函证', '是否发函', 'confirm_flag', 'is_confirm']

/** 带入候选行：ConfirmationRow 子集 + 诊断标记（`_` 前缀，不写入持久化字段） */
export type E0ListCandidate = Partial<ConfirmationRow> & {
  /** 来源清单编码 */
  _list_code?: string
  /** 品种由兜底值推出（源模板 所属科目/借款类型 两列都缺）→ UI 应提示复核 */
  _type_fallback?: boolean
}

function pick(raw: Record<string, any>, keys: string[]): any {
  for (const k of keys) {
    if (raw[k] != null && String(raw[k]).trim() !== '') return raw[k]
  }
  return undefined
}

function text(raw: Record<string, any>, keys: string[]): string {
  const v = pick(raw, keys)
  return v == null ? '' : String(v).trim()
}

function num(v: any): number {
  if (v == null || String(v).trim() === '') return 0
  const n = Number(String(v).replace(/,/g, ''))
  return Number.isFinite(n) ? n : 0
}

/** 「是否函证」判定为「是」（宽松：是/Y/true/√/1） */
export function isConfirmFlagYes(raw: Record<string, any>): boolean {
  const v = pick(raw, CONFIRM_FLAG_KEYS)
  if (v == null) return false
  const s = String(v).trim().toLowerCase()
  return ['是', 'y', 'yes', 'true', '√', '1', '✓'].includes(s)
}

/**
 * 品种判定：按 spec.subtypeKeys 顺序读源模板列，命中关键字则用之，否则兜底。
 * 返回 `fallback=true` 表示两列都缺 → 调用方应提示人工复核（静默归类会让长期借款品种恒空）。
 */
export function resolveE0AccountType(
  raw: Record<string, any>,
  spec: E0ListSpec,
): { accountType: string; fallback: boolean } {
  if (!spec.subtypeKeys.length) return { accountType: spec.defaultAccountType, fallback: false }
  const sub = text(raw, spec.subtypeKeys)
  if (!sub) return { accountType: spec.defaultAccountType, fallback: true }
  if (/长期借款/.test(sub)) return { accountType: '长期借款', fallback: false }
  if (/短期借款/.test(sub)) return { accountType: '短期借款', fallback: false }
  if (/其他货币资金|保证金|信用证|备用金/.test(sub)) {
    return { accountType: '其他货币资金', fallback: false }
  }
  if (/银行存款/.test(sub)) return { accountType: '银行存款', fallback: false }
  return { accountType: spec.defaultAccountType, fallback: true }
}

/** 组内取值一致才填，不一致宁缺勿造（避免把两个账号糊成一个） */
function uniformOrEmpty(values: string[]): string {
  const set = new Set(values.filter(Boolean))
  return set.size === 1 ? [...set][0] : ''
}

/**
 * 从单张 E0 发函记录表 rows 生成 E0-1 待带入行（纯函数，便于单测）。
 *
 * 与源模板 E0-1 F 列同口径：按 spec.groupBy 聚合并**求和**金额
 * （E0-5 一份询证函多张承兑汇票 → 汇总为一行，金额 = 票面金额之和）。
 * - spec.hasConfirmFlag 为 true 时才按「是否函证=是」筛行
 * - 无单位名称的行跳过
 */
export function buildSummaryRowsFromListRows(
  listRows: any[],
  listCode: string,
): E0ListCandidate[] {
  const spec = E0_LIST_SPECS[listCode]
  if (!spec) return []

  interface Bucket {
    entity: string[]
    index: string[]
    accountNo: string[]
    currency: string[]
    accountType: string
    fallback: boolean
    amount: number
  }
  const buckets = new Map<string, Bucket>()
  const order: string[] = []

  ;(listRows || []).forEach((raw, i) => {
    if (!raw || typeof raw !== 'object') return
    if (spec.hasConfirmFlag && !isConfirmFlagYes(raw)) return
    const entity = text(raw, spec.entityKeys)
    if (!entity) return

    const index = text(raw, spec.indexKeys)
    const accountNo = text(raw, spec.accountNoKeys)
    const { accountType, fallback } = resolveE0AccountType(raw, spec)

    // 聚合键严格对齐 E0-1 F 列的 SUMIF/SUMIFS 条件；键缺失时不与他行合并（`#i` 兜底）
    let keyParts: string[]
    if (spec.groupBy === 'index') keyParts = [index || `#${i}`]
    else if (spec.groupBy === 'accountNo') keyParts = [accountNo || `#${i}`]
    else keyParts = [index || `#${i}`, accountNo || `#${i}`]
    const key = [accountType, ...keyParts].join('\u0001')

    let b = buckets.get(key)
    if (!b) {
      b = { entity: [], index: [], accountNo: [], currency: [], accountType, fallback, amount: 0 }
      buckets.set(key, b)
      order.push(key)
    }
    b.entity.push(entity)
    b.index.push(index)
    b.accountNo.push(accountNo)
    b.currency.push(text(raw, spec.currencyKeys))
    b.amount += num(pick(raw, spec.amountKeys))
    b.fallback = b.fallback || fallback
  })

  return order.map((key) => {
    const b = buckets.get(key)!
    const out: E0ListCandidate = {
      entity_name: b.entity.find(Boolean) || '',
      account_type: b.accountType,
      amount: Math.round(b.amount * 100) / 100,
      _list_code: listCode,
    }
    const idx = uniformOrEmpty(b.index)
    if (idx) out.confirm_index = idx
    const no = uniformOrEmpty(b.accountNo)
    if (no) out.account_no = no
    const cur = uniformOrEmpty(b.currency)
    if (cur) out.currency = cur
    if (b.fallback) out._type_fallback = true
    return out
  })
}

/** 完整去重键：询证函索引号 + 品种 + 账号/产品名 + 单位（同银行多账户不会互相压掉） */
function fullKey(r: Partial<ConfirmationRow>): string {
  return [r.confirm_index, r.account_type, r.account_no, r.entity_name]
    .map((v) => String(v ?? '').trim())
    .join('\u0001')
}

/** 历史去重键（旧版本按此建行，无 account_no）：仅用于与 existing 比对，保守不重复带入 */
function legacyKey(r: Partial<ConfirmationRow>): string {
  return `${String(r.entity_name || '').trim()}\u0001${String(r.account_type || '').trim()}`
}

/**
 * 去重。
 * - 与 `existing` 比对：完整键或历史键任一命中即跳过（保守，手工优先）
 * - 候选内部：只按**完整键**去重，保留同一银行下的多个账号/多个理财产品
 */
export function dedupeSummaryRows(
  candidates: Partial<ConfirmationRow>[],
  existing: ConfirmationRow[],
): Partial<ConfirmationRow>[] {
  const existFull = new Set<string>()
  const existLegacy = new Set<string>()
  for (const r of existing) {
    existFull.add(fullKey(r))
    existLegacy.add(legacyKey(r))
  }
  const seen = new Set<string>()
  const result: Partial<ConfirmationRow>[] = []
  for (const c of candidates) {
    const fk = fullKey(c)
    if (existFull.has(fk) || existLegacy.has(legacyKey(c)) || seen.has(fk)) continue
    seen.add(fk)
    result.push(c)
  }
  return result
}

export interface ImportE0ListsResult {
  ok: boolean
  candidates: Partial<ConfirmationRow>[]
  reason?: 'missing-project' | 'error'
  message?: string
  emptyReason?: string
  /** 品种靠兜底值推出的清单编码（源模板 所属科目/借款类型 都缺）→ UI 提示复核 */
  typeFallbackLists?: string[]
}

/**
 * 一键：从 E0-3~E0-6 发函记录表拉取并按源模板 E0-1 F 列口径聚合、去重。
 * @param existing 当前 Summary_Sheet 已有行（去重基准）
 */
export async function importE0ListsToSummary(
  projectId: string,
  existing: ConfirmationRow[],
  listCodes: string[] = ['E0-3', 'E0-4', 'E0-5', 'E0-6'],
): Promise<ImportE0ListsResult> {
  if (!projectId?.trim()) {
    return { ok: false, candidates: [], reason: 'missing-project', message: '缺少项目上下文' }
  }
  try {
    const all: E0ListCandidate[] = []
    for (const code of listCodes) {
      const spec = E0_LIST_SPECS[code]
      if (!spec) continue
      // 按 spec.formats 顺序尝试：专属组件格式优先，通用 d-form-table 兜底
      for (const format of spec.formats) {
        const res = await fetchWorkpaperHtmlRows(projectId, code, format, spec.sheetName)
        if (!res || !res.rows?.length) continue
        all.push(...buildSummaryRowsFromListRows(res.rows, code))
        break
      }
    }
    if (all.length === 0) {
      return { ok: true, candidates: [], emptyReason: '发函记录表（E0-3~E0-6）暂无可带入记录' }
    }
    const fallbackLists = [...new Set(all.filter(c => c._type_fallback).map(c => c._list_code!))]
    const deduped = dedupeSummaryRows(all, existing)
    if (deduped.length === 0) {
      return { ok: true, candidates: [], emptyReason: '发函记录表项目已全部带入，无新增' }
    }
    return {
      ok: true,
      candidates: deduped,
      ...(fallbackLists.length ? { typeFallbackLists: fallbackLists } : {}),
    }
  } catch (e: any) {
    return { ok: false, candidates: [], reason: 'error', message: e?.message || '带入失败' }
  }
}
