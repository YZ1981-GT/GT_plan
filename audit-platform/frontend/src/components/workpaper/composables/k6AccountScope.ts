/**
 * K6 持有待售资产和负债 — 科目码单一真源。
 *
 * 🔴 **2026-08-09 连库对账改正**（spec k-cycle-…-closure Task 4/7）：
 *
 * ================  ==============  ================================================
 * 字段               改正前           改正前那个码在 `report_config` 里实际是什么
 * ================  ==============  ================================================
 * listed row_code   ``BS-015``      **流动资产合计**（`ROW()` 派生行，抽不出 `TB()`）
 * soe row_code      ``BS-024``      **长期股权投资** `TB('1511','期末余额')`（G7 的行）
 * 兜底标准码          ``''``          误判「三表零命中」而置空
 * ================  ==============  ================================================
 *
 * `BS-024` 是本循环最严重的一处（后果分级 **ACTIVE_WRONG**）：`1511` 在 8 个 client
 * 项目存在且 `direction=debit`（不会被备抵拆分挡住）⇒ 国企项目的持有待售资产审定表
 * **取到长期股权投资余额**，不是「取不到数」而是「取到别的科目的钱」。
 *
 * 正确落点（`report_config` 四变体一致，按 `row_name` 反查）::
 *
 *     BS-012 持有待售资产      = TB('1481','期末余额')
 *     BS-051 持有待售负债      = TB('2245','期末余额')
 *     IMP-007 持有待售资产减值准备 = TB('1482','期末余额')   （仅 soe_standalone 有公式）
 *
 * 🔴 **「宁缺勿造」在 K6 不成立**（推翻旧记载）：`1481`/`1482`/`2245` 在
 * `account_chart` **client 侧确实存在**（各 1 个项目），三条报表行公式也都在
 * ⇒ 后端 `has_account` 已由 `False` 改 `True`、兜底码由 `''` 改 `'1481'`。
 *
 * 但**多数项目仍没有这三个科目** ⇒ 走运行期降级（`empty_reason` 非空 ⇒ 前端显示
 * 「本项目无此科目」而非 `0.00`）。这与「标准科目表里就没这个科目」是**两层不同的事**。
 *
 * **使用铁律**：运行态一律取 render 下发的 `tb_source_codes.gross`（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。范式同 `k2AccountScope.ts`。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
 *       Requirements 1.5, 1.9, 2.3, 3.5, 4.6 / Property 2, 4, 10
 */

/**
 * 报表行编码 —— 上市准则（资产侧）。
 *
 * 🔴 两准则**同号**（`report_config` 实测 `BS-012` 四变体一致）。保留 LISTED/SOE
 * 两个常量是为了与其余 K 循环形态一致，不是因为它们该不同。
 */
export const K6_REPORT_ROW_CODE_LISTED = 'BS-012'

/** 报表行编码 —— 国企准则（资产侧，与上市同号） */
export const K6_REPORT_ROW_CODE_SOE = 'BS-012'

/**
 * 报表行编码 —— **负债侧**（持有待售负债）。
 *
 * K6 一个循环管资产与负债两侧且方向相反（`1481`/`1482` 是 debit、`2245` 是 credit）
 * ⇒ 后端分两个 `ReportLineAccountSpec`，负债侧声明负债方向。前端只表达资产侧会让
 * 溯源面板漏报负债侧口径。
 */
export const K6_LIABILITY_ROW_CODE = 'BS-051'

/** 报表行编码 —— **备抵侧**（持有待售资产减值准备，仅 soe_standalone 有公式） */
export const K6_PROVISION_ROW_CODE = 'IMP-007'

/**
 * 资产侧兜底标准码：`1481` 持有待售资产。
 *
 * 🔴 改正前是空串（误判「三表零命中」）。改动本常量前先查 `account_chart`
 * **按 source 分域**（client / standard 分母不同）。
 */
export const K6_FALLBACK_STANDARD = '1481'

/** 备抵侧兜底标准码：`1482` 持有待售资产减值准备 */
export const K6_PROVISION_FALLBACK_STANDARD = '1482'

/** 负债侧兜底标准码：`2245` 持有待售负债 */
export const K6_LIABILITY_FALLBACK_STANDARD = '2245'

/** 科目中文名（展示用） */
export const K6_ACCOUNT_NAME = '持有待售资产和负债'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K6TbSourceCodes {
  gross?: string[] | null
  gross_standard?: string[] | null
  provision?: string[] | null
  provision_standard?: string[] | null
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
 * 本项目是否确实没有该科目（运行期降级判据）。
 *
 * 🔴 与「余额为 0」必须可区分 —— 后端只在**科目表里查不到**时才写 `empty_reason`；
 * 余额为 0 时 `empty_reason` 为 null 且金额确为 0，此时应照显 `0.00`。
 */
export function k6AccountAbsent(src?: K6TbSourceCodes | null): boolean {
  return Boolean(String(src?.empty_reason ?? '').trim())
}

/**
 * `tb_balance` / 明细查询用的**原始码**前缀集。
 *
 * 运行态优先用 render 解析结果；缺失时退到兜底码。
 *
 * 🔴 `empty_reason` 非空时返回**空数组**而不是兜底码 —— 兜底码在本项目科目表里
 * 不存在，拿它去查只会得到空结果并把「本项目无此科目」伪装成「余额为 0」。
 */
export function k6QueryCodes(src?: K6TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  if (resolved.length) return resolved
  return k6AccountAbsent(src) ? [] : [K6_FALLBACK_STANDARD]
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 * 取**标准码**（`trial_balance.standard_account_code` 口径）。
 *
 * 本项目无该科目时返回空串，消费方据此禁用取数类按钮。
 */
export function k6AccountCode(src?: K6TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  if (resolved.length) return resolved[0]
  return k6AccountAbsent(src) ? '' : K6_FALLBACK_STANDARD
}

/** 备抵侧查询口径（标准码集）；缺省回退 `1482`，本项目无科目时返空 */
export function k6ProvisionQueryCodes(src?: K6TbSourceCodes | null): string[] {
  const resolved = normalize(src?.provision_standard)
  if (resolved.length) return resolved
  return k6AccountAbsent(src) ? [] : [K6_PROVISION_FALLBACK_STANDARD]
}
