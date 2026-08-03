/**
 * D4 营业收入 —— 科目口径**单一真源**（零 Vue 依赖纯函数 + 常量）。
 *
 * 🔴 运行态优先取 render 下发的 `tb_source_codes`（`html_data.project_context.tb_source_codes`），
 * 本文件的常量仅作**兜底 + 展示**。禁止在组件里再写字面量科目码。
 *
 * report_config 实证（四准则一致）：
 *   IS-001 一、营业收入   = SUM_TB('6001~6099','本期发生额')  ← 区间，非单码
 *   IS-002 减：营业成本   = SUM_TB('6401~6499','本期发生额')
 *
 * 🔴 D4 是损益类（发生额），不是余额类 —— 无期初/期末概念。
 * 🔴 均为**区间**而非单码；实际叶子由 `resolve_d4_accounts` 逐项目展开。
 *
 * spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/ Requirements 2.6
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

// ─────────────────────────────────────────────────────────────────────────────
// 报表行常量
// ─────────────────────────────────────────────────────────────────────────────

/** 报表行次编码 — 营业收入 */
export const D4_REVENUE_ROW_CODE = 'IS-001'

/** 报表行次编码 — 营业成本 */
export const D4_COST_ROW_CODE = 'IS-002'

// ─────────────────────────────────────────────────────────────────────────────
// 兜底 / 展示常量（仅在 render 未下发 tb_source_codes 时用于 UI 展示 / 兜底查询）
// ─────────────────────────────────────────────────────────────────────────────

/** 兜底标准码 — 收入（主营 + 其他）。仅展示/兜底用，运行态取 `revenue_standard_expanded` */
export const D4_REVENUE_FALLBACK_STANDARD: readonly string[] = ['6001', '6051']

/** 兜底标准码 — 成本。仅展示/兜底用，运行态取 `cost_standard_expanded` */
export const D4_COST_FALLBACK_STANDARD: readonly string[] = ['6401', '6402']

/** 主营业务收入标准码（审定表分段用：主营段） */
export const D4_MAIN_REVENUE_STANDARD = '6001'

/** 其他业务收入标准码（审定表分段用：其他段） */
export const D4_OTHER_REVENUE_STANDARD = '6051'

/** 主营业务成本标准码 */
export const D4_MAIN_COST_STANDARD = '6401'

/** 其他业务成本标准码 */
export const D4_OTHER_COST_STANDARD = '6402'

/** 科目中文名 — 收入（AI 上下文 / UI 文案统一取此常量） */
export const D4_REVENUE_ACCOUNT_NAME = '营业收入'

/** 科目中文名 — 成本 */
export const D4_COST_ACCOUNT_NAME = '营业成本'

// ─────────────────────────────────────────────────────────────────────────────
// D4 专属 tb_source_codes 接口
// ─────────────────────────────────────────────────────────────────────────────

/**
 * D4 tb_source_codes 视图模型（后端 `build_d4_source_codes` 输出，
 * 含 `D4AccountScope.as_dict()` 全部字段 + `revenue_row_code`/`cost_row_code`）。
 *
 * 消费方：`WpFourTableSourcePanel`、`D4TabAdjudication`。
 */
export interface D4TbSourceCodes extends TbSourceCodes {
  revenue_row_code?: string
  cost_row_code?: string
  /** 收入标准码规格集（可含区间如 `'6001~6099'`） */
  revenue_standard?: string[]
  /** 成本标准码规格集 */
  cost_standard?: string[]
  /** 收入客户原始码前缀集（`account_mapping` 反解，逐项目） */
  revenue_original?: string[]
  /** 成本客户原始码前缀集 */
  cost_original?: string[]
  /** 收入解析来源 */
  revenue_resolved_from?: string
  /** 成本解析来源 */
  cost_resolved_from?: string
  /** 收入是否精确反解 */
  revenue_exact?: boolean
  /** 成本是否精确反解 */
  cost_exact?: boolean
  /** 收入报表公式原文 */
  revenue_formula?: string | null
  /** 成本报表公式原文 */
  cost_formula?: string | null
  /** 标准码有、account_mapping 无映射记录 */
  unmapped_standard?: string[]
  /** 收入区间内该项目**实际存在**的标准码（逐项目展开结果） */
  revenue_standard_expanded?: string[]
  /** 成本区间内该项目实际存在的标准码 */
  cost_standard_expanded?: string[]
  /** 被语义收敛剔除的标准码 `[[码, 名], ...]` */
  excluded_standard?: Array<[string, string]>
}

// ─────────────────────────────────────────────────────────────────────────────
// 运行态查询函数
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 取收入查询用的科目码集合（标准码）。
 *
 * **运行态优先**：从 render 下发的 `revenue_standard_expanded` 取（逐项目动态展开结果）；
 * 回退到 `D4_REVENUE_FALLBACK_STANDARD`。
 */
export function d4RevenueQueryCodes(src?: D4TbSourceCodes | null): string[] {
  if (src?.revenue_standard_expanded?.length) return [...src.revenue_standard_expanded]
  return tbQueryCodes(src?.gross_standard, D4_MAIN_REVENUE_STANDARD)
}

/**
 * 取成本查询用的科目码集合（标准码）。
 *
 * **运行态优先**：从 render 下发的 `cost_standard_expanded` 取；
 * 回退到 `D4_COST_FALLBACK_STANDARD`。
 */
export function d4CostQueryCodes(src?: D4TbSourceCodes | null): string[] {
  if (src?.cost_standard_expanded?.length) return [...src.cost_standard_expanded]
  return tbQueryCodes(src?.cost_standard?.[0] ? src.cost_standard : undefined, D4_MAIN_COST_STANDARD)
}

/**
 * 主营业务收入科目码（用于 EventBus / writebackTB）。
 * 运行态取 `revenue_standard_expanded` 第一个以 `6001` 开头的码；回退兜底常量。
 */
export function d4MainRevenueCode(src?: D4TbSourceCodes | null): string {
  const codes = d4RevenueQueryCodes(src)
  return codes.find((c) => c.startsWith('6001')) || codes[0] || D4_MAIN_REVENUE_STANDARD
}

/**
 * 其他业务收入科目码。
 */
export function d4OtherRevenueCode(src?: D4TbSourceCodes | null): string {
  const codes = d4RevenueQueryCodes(src)
  return codes.find((c) => c.startsWith('6051')) || D4_OTHER_REVENUE_STANDARD
}

/**
 * 判断给定科目码属于主营还是其他业务收入。
 * 用于审定表分段（主营段 / 其他段）。
 */
export function isMainRevenueCode(code: string): boolean {
  return code.startsWith('6001')
}

/**
 * 判断给定科目码属于其他业务收入。
 */
export function isOtherRevenueCode(code: string): boolean {
  return code.startsWith('6051')
}
