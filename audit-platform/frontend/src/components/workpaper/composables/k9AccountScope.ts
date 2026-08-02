/**
 * K9 管理费用 — 科目码单一真源。
 *
 * 报表行：IS-005（上市）/ IS-023（国企）
 * 公式：TB('6602','本期发生额') 四准则一致
 * 兜底码：6602
 * 损益类/借方科目 —— 取本期发生额非余额
 *
 * **使用铁律**：运行态一律取 render 下发的 `tb_source_codes.gross`（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。范式同 `k2AccountScope.ts`。
 *
 * spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
 *       Requirements 5.1~5.3 / Property 9
 */

/** 报表行编码 —— 上市准则 */
export const K9_REPORT_ROW_CODE_LISTED = 'IS-005'

/** 报表行编码 —— 国企准则 */
export const K9_REPORT_ROW_CODE_SOE = 'IS-023'

/** 兜底标准码 */
export const K9_FALLBACK_STANDARD = '6602'

/** 科目中文名（展示用） */
export const K9_ACCOUNT_NAME = '管理费用'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K9TbSourceCodes {
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
export function k9QueryCodes(src?: K9TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  return resolved.length ? resolved : ['6602']
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 * 取**标准码**（`trial_balance.standard_account_code` 口径）。
 */
export function k9AccountCode(src?: K9TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || '6602'
}
