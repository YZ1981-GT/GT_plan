/**
 * K7 递延收益 — 科目码单一真源。
 *
 * 报表行：BS-066（两准则同号；2026-08-09 由 BS-069 / BS-095 改正）
 * 公式：TB('2401','期末余额') 四准则一致
 * 兜底码：2401
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
 *
 * ================  ==============  ================================================
 * 字段               改正前           改正前那个码在 `report_config` 里实际是什么
 * ================  ==============  ================================================
 * listed row_code   ``BS-069``      **非流动负债合计**（`ROW()` 派生行）
 * soe row_code      ``BS-095``      row_name 是「递延收益」但 **formula 为 NULL**
 * ================  ==============  ================================================
 *
 * 后果分级 **TRACE_ONLY**：派生行抽不出 `TB()`、NULL 公式也解析不出码 ⇒ 两侧都退兜底
 * `2401`，金额是对的，只有 `resolved_from` 谎报。但溯源面板会把「非流动负债合计」
 * 当成递延收益的来源行展示。
 *
 * 正确落点（`report_config` 四变体一致）::
 *
 *     BS-066 递延收益 = TB('2401','期末余额')
 *
 * 🔴 两准则**同号**。保留 LISTED/SOE 两个常量是为了与其余 K 循环形态一致。
 */
export const K7_REPORT_ROW_CODE_LISTED = 'BS-066'

/** 报表行编码 —— 国企准则（与上市同号，见上方改正说明） */
export const K7_REPORT_ROW_CODE_SOE = 'BS-066'

/** 兜底标准码 */
export const K7_FALLBACK_STANDARD = '2401'

/** 科目中文名（展示用） */
export const K7_ACCOUNT_NAME = '递延收益'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K7TbSourceCodes {
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
export function k7QueryCodes(src?: K7TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  return resolved.length ? resolved : [K7_FALLBACK_STANDARD]
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 * 取**标准码**（`trial_balance.standard_account_code` 口径）。
 */
export function k7AccountCode(src?: K7TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || K7_FALLBACK_STANDARD
}
