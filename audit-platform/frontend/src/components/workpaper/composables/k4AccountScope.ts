/**
 * K4 其他流动负债 — 科目码单一真源。
 *
 * 报表行：**BS-053**（两准则同号）
 *
 * 🔴 **2026-08-09 改正**（后端 `k_cycle_specs.py` 已按 `report_config` 连库对账改正，
 * 本文件同步跟进；判据在 `kCycleAccountScopeCrossLock.spec.ts`）::
 *
 *     原值 listed=BS-058 / soe=BS-081
 *       BS-081 实为**实收资本（或股本）** `TB('4001','期末余额')`
 *       ⇒ 后果 SILENT_EMPTY —— 4001 在 client 侧 8 项目为 credit，
 *         而 K4 原未声明负债方向 ⇒ 原值被 split_gross_provision 判成**备抵**
 *         ⇒ gross 变空 ⇒ 表现为「恒空」而非错数，掩盖了错位本身
 *
 * ✅ **宁缺勿造成立（K 循环唯一一个）**：`BS-053` 四变体公式全 NULL，
 * 且 `account_chart` 按名（其他流动负债）按码（`2301`）**两侧都零命中**
 * ⇒ 本科目在实务中是报表行、由多个明细按性质归集，四表侧无法自动取数。
 *
 * ⚠️ 与「本项目没用这个科目」是**两层不同的事**：本条是标准科目表里就没有
 * （设计期结论）；后者是运行期降级（后端 `EMPTY_REASON_NOT_IN_PROJECT`）。
 *
 * **使用铁律**：运行态一律取 render 下发的 `tb_source_codes.gross`（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。范式同 `k2AccountScope.ts`。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/ (Task 7)
 *       Requirements 1.8, 3.5 / Property 2, 4, 10
 */

/** 报表行编码 —— 上市准则（两准则同号，保留两个常量以兼容既有 import） */
export const K4_REPORT_ROW_CODE_LISTED = 'BS-053'

/** 报表行编码 —— 国企准则（实测与 listed 同号） */
export const K4_REPORT_ROW_CODE_SOE = 'BS-053'

/**
 * 兜底标准码：**空串** —— 标准科目表里没有「其他流动负债」这个科目（宁缺勿造）。
 *
 * 🔴 不要「顺手」填一个看起来合理的码（历史曾写 `2301`，全库两侧零命中）：
 * 填了会让审定表把别的科目余额显示成其他流动负债，比留空更坏。
 */
export const K4_FALLBACK_STANDARD = ''

/** 科目中文名（展示用） */
export const K4_ACCOUNT_NAME = '其他流动负债'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K4TbSourceCodes {
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
export function k4QueryCodes(src?: K4TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  return resolved.length ? resolved : []
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 * 取**标准码**（`trial_balance.standard_account_code` 口径）。
 * 无科目时返回空数组，消费方据此禁用取数类按钮。
 */
export function k4AccountCode(src?: K4TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || ''
}
