/**
 * importE0ListsToSummary — E0 发函前清单（E0-3~E0-6，d-form-table）→ E0-1 函证结果汇总带入
 *
 * 决策 4（E0 重建 B 方案）新增能力：筛「是否函证 = 是」的行 → 生成 Summary_Sheet 行，
 * account_type 按来源品种置值。复用 fetchWorkpaperHtmlRows 读 d-form-table 清单，
 * 不新造 confirmation-v1 写入实现（产出行由 Summary_Sheet 侧 importCompanies/addRow 消费）。
 *
 * E0 清单 → account_type 品种映射（design 决策 4）：
 *   E0-3 货币资金发函记录表 → 银行存款 / 其他货币资金（按账户类型细分）
 *   E0-4 借款发函记录表     → 短期借款
 *   E0-5 应付银行承兑汇票   → 应付票据
 *   E0-6 理财产品发函记录表 → 理财产品
 */
import { fetchWorkpaperHtmlRows } from './importFromSummary'
import type { ConfirmationRow } from '../confirmationTypes'

/** E0 清单 sheet 编码 → 默认品种（account_type） */
export const E0_LIST_ACCOUNT_TYPE: Record<string, string> = {
  'E0-3': '银行存款',
  'E0-4': '短期借款',
  'E0-5': '应付票据',
  'E0-6': '理财产品',
}

/** 「是否函证」列的候选列名 */
const CONFIRM_FLAG_KEYS = ['是否函证', '是否发函', 'confirm_flag', 'is_confirm']
/** 单位/账户名称候选列名 */
const ENTITY_KEYS = ['开户银行', '账户名称', '被询证单位', '借款人', '单位名称', '公司名称', '理财产品名称', '产品名称', 'entity_name']
/** 索引号候选列名 */
const INDEX_KEYS = ['索引号', '函证索引号', '编号', 'confirm_index']
/** 金额候选列名 */
const AMOUNT_KEYS = ['账户余额', '余额', '发函金额', '金额', '期末余额', 'amount']
/** 账户类型候选列名（E0-3 细分银行存款/其他货币资金） */
const ACCOUNT_SUBTYPE_KEYS = ['账户类型', '科目', '所属科目', 'account_type']

function pick(raw: Record<string, any>, keys: string[]): any {
  for (const k of keys) {
    if (raw[k] != null && String(raw[k]).trim() !== '') return raw[k]
  }
  return undefined
}

/** 「是否函证」判定为「是」（宽松：是/Y/true/√/1） */
export function isConfirmFlagYes(raw: Record<string, any>): boolean {
  const v = pick(raw, CONFIRM_FLAG_KEYS)
  if (v == null) return false
  const s = String(v).trim().toLowerCase()
  return ['是', 'y', 'yes', 'true', '√', '1', '✓'].includes(s)
}

/**
 * 从单张 E0 清单 rows 生成 Summary_Sheet 待带入行（纯函数，便于单测）。
 * - 仅取「是否函证 = 是」的行
 * - account_type 按品种置值（E0-3 按账户类型细分银行存款/其他货币资金）
 * - 无单位名称的行跳过
 */
export function buildSummaryRowsFromListRows(
  listRows: any[],
  listCode: string,
): Partial<ConfirmationRow>[] {
  const defaultType = E0_LIST_ACCOUNT_TYPE[listCode] || ''
  const out: Partial<ConfirmationRow>[] = []
  for (const raw of listRows || []) {
    if (!raw || typeof raw !== 'object') continue
    if (!isConfirmFlagYes(raw)) continue
    const entity = pick(raw, ENTITY_KEYS)
    if (!entity) continue
    // E0-3 按账户类型细分（其他货币资金 vs 银行存款）
    let accountType = defaultType
    if (listCode === 'E0-3') {
      const sub = String(pick(raw, ACCOUNT_SUBTYPE_KEYS) || '')
      if (/其他货币资金|保证金|信用证|备用金/.test(sub)) accountType = '其他货币资金'
    }
    const amount = pick(raw, AMOUNT_KEYS)
    out.push({
      entity_name: String(entity).trim(),
      confirm_index: pick(raw, INDEX_KEYS) ? String(pick(raw, INDEX_KEYS)).trim() : undefined,
      account_type: accountType,
      amount: amount != null ? Number(amount) || 0 : 0,
    })
  }
  return out
}

/** 去重：按 entity_name + account_type 合并（对齐已存在行不重复追加） */
export function dedupeSummaryRows(
  candidates: Partial<ConfirmationRow>[],
  existing: ConfirmationRow[],
): Partial<ConfirmationRow>[] {
  const seen = new Set<string>()
  const keyOf = (r: Partial<ConfirmationRow>) =>
    `${String(r.entity_name || '').trim()}||${String(r.account_type || '').trim()}`
  for (const r of existing) seen.add(keyOf(r))
  const result: Partial<ConfirmationRow>[] = []
  for (const c of candidates) {
    const k = keyOf(c)
    if (seen.has(k)) continue
    seen.add(k)
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
}

/**
 * 一键：从 E0-3~E0-6 清单拉取「是否函证 = 是」行并去重（相对已存在 Summary 行）。
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
    const all: Partial<ConfirmationRow>[] = []
    for (const code of listCodes) {
      const res = await fetchWorkpaperHtmlRows(projectId, code, 'd-form-table')
      if (!res || !res.rows?.length) continue
      all.push(...buildSummaryRowsFromListRows(res.rows, code))
    }
    if (all.length === 0) {
      return { ok: true, candidates: [], emptyReason: '发函清单（E0-3~E0-6）暂无「是否函证=是」的记录' }
    }
    const deduped = dedupeSummaryRows(all, existing)
    if (deduped.length === 0) {
      return { ok: true, candidates: [], emptyReason: '发函清单项目已全部带入，无新增' }
    }
    return { ok: true, candidates: deduped }
  } catch (e: any) {
    return { ok: false, candidates: [], reason: 'error', message: e?.message || '带入失败' }
  }
}
