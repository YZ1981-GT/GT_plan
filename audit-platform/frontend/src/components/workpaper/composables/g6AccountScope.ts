/**
 * G6 其他债权投资 — 科目定位（**薄壳**，委托 `gCycleAccountScope`）。
 *
 * 🔴 **2026-08-01 纠错 + 去双真源**
 *
 * 本文件原先写 `G6_GROSS_FALLBACK_STANDARD = '1505'`，依据是 `report_config` 的
 * `BS-022 = TB('1505','期末余额')`。但 `account_chart` + `trial_balance.account_name`
 * 双向实证 **`1505` 实为「债权投资减值准备」**（G4 的备抵），其他债权投资的真实科目是
 * **`1506`**。根因是 `report_config` 的 BS-022 / BS-025 / BS-026 **连续偏移一位**
 * （平台标准科目表在 `1504 债权投资` 与 `1506 其他债权投资` 之间插了
 * `1505 债权投资减值准备`，且其他非流动金融资产跳到 `1519`）。
 *
 * 同时本文件与 `gCycleAccountScope.ts` 构成双真源 → 改为薄壳委托，
 * 科目声明只在 `gCycleAccountScope.ts` 一处（与后端 `g_cycle_specs.py` 对称）。
 *
 * 无备抵槽（CAS22 FVOCI-Debt 减值在 OCI 确认，不冲减资产负债表账面价值）。
 */
import { gCycleScope } from './gCycleAccountScope'
import type { TbSourceCodes } from './shared/tbSourceCodes'

const SCOPE = gCycleScope('G6')!

/** G6 对应的报表行编码（仅展示 / 溯源用，不是定位依据） */
export const G6_REPORT_ROW_CODE = SCOPE.spec.reportRowCode as string

/** 原值兜底标准科目码（仅 render 未下发时用；实证真值 1506） */
export const G6_GROSS_FALLBACK_STANDARD = SCOPE.primaryFallback

/**
 * render 下发的科目溯源结构。
 *
 * 后端已改为语义解析（`slots` 结构 + 向后兼容的扁平投影），故直接复用平台共享类型。
 */
export type G6TbSourceCodes = TbSourceCodes

/** 运行态获取 G6 原值查询科目码列表（缺失时回退兜底码） */
export function g6GrossQueryCodes(
  tbSourceCodes?: G6TbSourceCodes | null,
): string[] {
  return SCOPE.queryCodes(tbSourceCodes)
}

/** 首个科目码（展示 / 请求参数用） */
export function g6AccountCode(tbSourceCodes?: G6TbSourceCodes | null): string {
  return SCOPE.accountCode(tbSourceCodes) || G6_GROSS_FALLBACK_STANDARD
}

/**
 * 本项目是否**确实没有**其他债权投资科目。
 *
 * `true` 时界面须提示「本项目无此科目」而不是显示 0 —— 后端解析不到时是
 * 宁缺勿造地返空，与「余额为 0」语义不同。
 */
export function isG6AccountAbsent(
  tbSourceCodes?: G6TbSourceCodes | null,
): boolean {
  return SCOPE.isAccountAbsent(tbSourceCodes)
}
