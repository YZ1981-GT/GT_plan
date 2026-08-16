/**
 * K3 其他应付款 — 科目码单一真源。
 *
 * 报表行：**BS-050（两准则同号）**
 * 公式：standalone `TB('2241')+TB('2231')` / consolidated `TB('2241')`
 * 兜底码：2241；附加科目 2231 应付利息（单列，不并入原值）
 *
 * 🔴 **2026-08-09 改正**（`report_config` 连库按 row_name 反查四变体）：
 * 原值 listed=`BS-053` 实为**其他流动负债**（= K4 应指的行，跨循环撞码）、
 * soe=`BS-075` 在 soe 侧名对但 formula 为 NULL、在 listed 侧是**股本**。
 * 两个原值的 formula 均 NULL ⇒ 解析退兜底 `2241` ⇒ 金额碰巧对，
 * 但**漏了 `2231` 应付利息**（财会[2018]15 号要求并入其他应付款列报），
 * 且溯源面板谎报「报表规则映射」。后果分级 TRACE_ONLY。
 *
 * **使用铁律**：运行态一律取 render 下发的 `tb_source_codes.gross`（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。范式同 `k2AccountScope.ts`。
 *
 * 判据在 DB，不在本文件 —— 交叉锁死守卫见
 * `__tests__/kCycleAccountScopeCrossLock.spec.ts`（读后端 `k_cycle_specs.py` 源码比对）。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/ Task 7
 *       Requirements 1.3, 3.5 / Property 10
 */

/** 报表行编码 —— 上市准则（两准则同号，保留两个常量以兼容既有 import） */
export const K3_REPORT_ROW_CODE_LISTED = 'BS-050'

/** 报表行编码 —— 国企准则 */
export const K3_REPORT_ROW_CODE_SOE = 'BS-050'

/** 兜底标准码 */
export const K3_FALLBACK_STANDARD = '2241'

/**
 * 报表公式引用但**单列不并入**其他应付款原值的科目：`2231` 应付利息。
 *
 * 🔴 它属 L2 循环（应付利息）—— 并入 `gross` 会造成跨循环双算。
 * 后端 `KCycleSpec.extra_standard_codes=('2231',)` 让共享件把它放进 `extra`。
 */
export const K3_EXTRA_STANDARD_CODES: readonly string[] = ['2231']

/** 科目中文名（展示用） */
export const K3_ACCOUNT_NAME = '其他应付款'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K3TbSourceCodes {
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
export function k3QueryCodes(src?: K3TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  return resolved.length ? resolved : [K3_FALLBACK_STANDARD]
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 * 取**标准码**（`trial_balance.standard_account_code` 口径）。
 */
export function k3AccountCode(src?: K3TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || K3_FALLBACK_STANDARD
}
