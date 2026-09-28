/**
 * F2 合同履约成本 — 科目码单一真源（**宁缺勿造**）。
 *
 * spec: voucher-sampling-account-scope-and-attach-closure（design 实证更正节 2，阶段 4）
 *
 * ## 为什么兜底是空串
 *
 * `F2TabContractCostCheck` 原硬编码 `account-code="1410"`。排查时一度判它是"错码"，
 * 但逐项实证后推翻了该判断：
 *
 * | 证据 | 现算结果（2026-09-28） |
 * |---|---|
 * | `F2_INVENTORY_ACCOUNT_CODES`（`f2NoteSectionMap.ts`） | `['1401'..'1412']` ⇒ **1410 在存货区间内**，非"区间外错码" |
 * | 同名常量（`useF2InspectionCheckFormulas.ts`） | 字符串 `'1401,...,1411'`，**亦含 1410** |
 * | `account_chart` / `tb_balance` 的 `1410` | **零命中** |
 * | `1341`（准则的合同履约成本标准码） | **零命中** |
 * | 任何 `account_name LIKE '%合同履约成本%'` / `'%合同资产%'` | **零命中**（8 个项目全无） |
 *
 * ⇒ 这些真实项目（医药流通 / 租车）**确实没有合同履约成本业务**，不是码写错了。
 * 把 `1410` 改成 `1341` 毫无意义（两者都查不到），且属于替审计师做专业判断。
 *
 * 🔴 因此本模块**不设兜底码**（`FALLBACK = ''`），与
 * `i5AccountScope` / `k4AccountScope` / `l7AccountScope` 同一取向：
 * 运行态解析不出科目时，由 `useSamplingAccountGate` 降级禁用抽凭并提示，
 * 而不是拿一个查不到的码去抽空。
 *
 * 🔴 **不要**把 `F2_INVENTORY_ACCOUNT_CODES`（整个存货族 1401~1412）当作本表的科目：
 * 那会让"合同履约成本检查"抽出原材料/库存商品的凭证。存货主表用那个常量是对的，
 * 本表不是。
 */

/**
 * 兜底标准码：**空串**（宁缺勿造）。
 *
 * 🔴 改动本常量前先查 `account_chart` 是否真有「合同履约成本」科目；
 * 若客户科目表确有（如 `1341` 或自定义码），正确做法是让 render 下发
 * `tb_source_codes`，而不是在此写死一个码。
 */
export const F2_CONTRACT_COST_FALLBACK_STANDARD = ''

/** 科目/底稿中文名（展示与提示文案用） */
export const F2_CONTRACT_COST_ACCOUNT_NAME = '合同履约成本'

/** 曾被误用的码 —— 守卫与代码评审用，防止再次填回 */
export const F2_CONTRACT_COST_WRONG_LEGACY_ACCOUNTS = [
  '1410', // 存货区间内的空码：account_chart/tb_balance 全库零命中
  '1341', // 准则标准码，但这些项目的科目表里同样不存在
] as const

/** render 下发的溯源结构（与其他循环 `*TbSourceCodes` 同构） */
export interface F2ContractCostTbSourceCodes {
  gross_raw?: string[] | null
  gross_standard?: string[] | null
  resolved_from?: string | null
}

function normalize(list?: string[] | null): string[] {
  const out: string[] = []
  for (const x of list ?? []) {
    const s = String(x ?? '').trim()
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}

/**
 * 查询口径科目码集。
 *
 * 只认 render 解析结果；解析不出时返回 **空数组**（不回退存货族、不臆造码）
 * —— 空数组会让 `useSamplingAccountGate` 判为 `absent` 并禁用抽凭。
 */
export function f2ContractCostQueryCodes(
  src?: F2ContractCostTbSourceCodes | null,
): string[] {
  const raw = normalize(src?.gross_raw)
  if (raw.length) return raw
  const std = normalize(src?.gross_standard)
  if (std.length) return std
  return F2_CONTRACT_COST_FALLBACK_STANDARD
    ? [F2_CONTRACT_COST_FALLBACK_STANDARD]
    : []
}
