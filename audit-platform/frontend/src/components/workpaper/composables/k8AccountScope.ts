/**
 * K8 销售费用 — 科目码单一真源。
 *
 * 报表行：IS-004（两准则同号；2026-08-09 由 IS-022 改正 soe 侧）
 * 公式：TB('6601','本期发生额') 四准则一致
 * 兜底码：6601
 * 损益类/借方科目 —— 取本期发生额非余额
 *
 * **使用铁律**：运行态一律取 render 下发的 `tb_source_codes.gross`（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。范式同 `k2AccountScope.ts`。
 *
 * spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
 *       Requirements 5.1~5.3 / Property 9
 */

/**
 * 报表行编码 —— 上市准则。
 *
 * 🔴 **2026-08-09 连库对账改正**（spec k-cycle-…-closure Task 4/7）：
 * soe 侧原写 ``IS-022``，而该码在 `report_config` 里实际是
 * **三、利润总额**（`ROW('IS-019')+ROW('IS-020')−ROW('IS-021')` 派生行）。
 *
 * 后果分级 **TRACE_ONLY（仅溯源失真）** —— 该码的公式是 `ROW()` 派生或为 NULL ⇒
 * `extract_signed_codes` 抽不出 `TB()` ⇒ 退兜底码 ⇒ **金额是对的**，
 * 只有 `resolved_from` 谎报 `report_config`、溯源面板展示错误的来源行。
 *
 * 正确落点（`report_config` 四变体一致）::
 *
 *     IS-004 销售费用 = TB('6601','本期发生额')
 *
 * 🔴 两准则**同号**（K 循环无一例外）。保留 LISTED/SOE 两个常量是为了与其余
 * K 循环形态一致，**不是**因为它们该不同。
 */
export const K8_REPORT_ROW_CODE_LISTED = 'IS-004'

/** 报表行编码 —— 国企准则（与上市同号，见上方改正说明） */
export const K8_REPORT_ROW_CODE_SOE = 'IS-004'

/** 兜底标准码 */
export const K8_FALLBACK_STANDARD = '6601'

/** 科目中文名（展示用） */
export const K8_ACCOUNT_NAME = '销售费用'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K8TbSourceCodes {
  gross?: string[] | null
  gross_standard?: string[] | null
  resolved_from?: string | null
  empty_reason?: string | null
  nature?: string | null
}

function normalize(codes: unknown): string[] {
  if (!Array.isArray(codes)) return []
  const out: string[] = []
  for (const c of codes) {
    const s = String(c ?? '').trim()
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}

/**
 * `tb_balance` / 明细查询用的**原始码**前缀集。
 * 运行态优先用 render 解析结果；缺失时退到兜底码。
 */
export function k8QueryCodes(src?: K8TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  return resolved.length ? resolved : [K8_FALLBACK_STANDARD]
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 * 取**标准码**（`trial_balance.standard_account_code` 口径）。
 */
export function k8AccountCode(src?: K8TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || K8_FALLBACK_STANDARD
}
