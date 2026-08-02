/**
 * K6 持有待售资产和负债 — 科目码单一真源。
 *
 * 报表行：BS-015（上市）/ BS-024（国企）
 * 公式：四行 formula 全为 None，三表零命中
 * 兜底码：
 * 🔴 三表零命中（列报重分类科目），四表侧无法自动取数
 *
 * **使用铁律**：运行态一律取 render 下发的 `tb_source_codes.gross`（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。范式同 `k2AccountScope.ts`。
 *
 * spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
 *       Requirements 5.1~5.3 / Property 9
 */

/** 报表行编码 —— 上市准则 */
export const K6_REPORT_ROW_CODE_LISTED = 'BS-015'

/** 报表行编码 —— 国企准则 */
export const K6_REPORT_ROW_CODE_SOE = 'BS-024'

/** 兜底标准码（无实体科目 → 空串，宁缺勿造） */
export const K6_FALLBACK_STANDARD = ''

/** 科目中文名（展示用） */
export const K6_ACCOUNT_NAME = '持有待售资产和负债'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K6TbSourceCodes {
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
 * 无科目时返回空数组，消费方据此禁用取数类按钮。
 */
export function k6QueryCodes(src?: K6TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  return resolved.length ? resolved : []
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 * 取**标准码**（`trial_balance.standard_account_code` 口径）。
 * 无科目时返回空数组，消费方据此禁用取数类按钮。
 */
export function k6AccountCode(src?: K6TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || ''
}
