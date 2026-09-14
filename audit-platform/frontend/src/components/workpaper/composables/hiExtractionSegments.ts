/**
 * H/I 循环四表取数分段配置注册表（per-wpCode）。
 * 各主入口用 `getHiExtractionSegments(wpCode)` 获取分段配置，
 * 传给 HiFourTableSourcePanel 作参数化渲染。
 *
 * Spec: .kiro/specs/hi-cycle-four-table-extraction/ Task 4.2
 *       .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 18（H8/H9 双族）
 */
import { h8Scope, h9Scope } from './hCycleAccountScope'

export interface HiExtractionSegment {
  label: string
  accountCode: string
  expression: string
  anchorKey: string
}

/** `TB('a','期末余额')+TB('b','期末余额')` —— 单码时退化为单项，绝不产出空表达式 */
function tbSumExpr(codes: readonly string[], column = '期末余额'): string {
  if (!codes.length) throw new Error('tbSumExpr 需要至少一个科目码')
  return codes.map((c) => `TB('${c}','${column}')`).join('+')
}

// H8/H9 双族兜底码：真源 = 后端 `four_table/dual_family_codes.py`，
// 前端镜像在 `hCycleAccountScope.ts`（由 `hCycleAccountScope.spec.ts` 三向锁死）。
const H8_GROSS_CODES = h8Scope.def.slotFallbacks.gross
const H8_DEP_CODES = h8Scope.def.slotFallbacks.accum_dep
const H8_IMP_CODES = h8Scope.def.slotFallbacks.impairment
const H9_GROSS_CODES = h9Scope.def.slotFallbacks.gross
const H9_UNEARNED_CODES = h9Scope.def.slotFallbacks.unearned_finance

const _REGISTRY: Record<string, HiExtractionSegment[]> = {
  H5: [
    { label: '油气资产原值(1631)', accountCode: '1631', expression: "TB('1631','期末余额')", anchorKey: 'H5-1-tb-amount' },
    { label: '累计折耗(1632)', accountCode: '1632', expression: "TB('1632','期末余额')", anchorKey: 'H5-1-tb-depletion' },
  ],
  H6: [
    { label: '固定资产清理(1606)', accountCode: '1606', expression: "TB('1606','期末余额')", anchorKey: 'H6-1-tb-amount' },
  ],
  H7: [
    { label: '生产性生物资产(1621)', accountCode: '1621', expression: "TB('1621','期末余额')", anchorKey: 'H7-1-tb-amount' },
  ],
  // 🔴 2026-08-03 纠正（浏览器实测发现）：H8 原写 `1901`（待处理财产损溢）/
  //    `190101`（非真实科目），H9 原写 `2205`（合同负债，D7 域）/ `220501`。
  //    这两组是本 spec 的 P0 —— 底稿「四表取数（公式管理）」面板显示的就是这里的值，
  //    改后端 render 但漏改本文件时，面板照旧显示错科目、当前值恒为 0/—。
  //
  // 🔴 2026-08-09 双族并取（spec h-cycle-… 裁决 1）：使用权资产 / 租赁负债在真实库里
  //    **两套编码族并存且逐项目互斥** —— 9 个项目里 5 个用新族（`1651`/`1652`/`2651`）。
  //    只写 primary 时溯源面板的取数公式在这些项目上**只覆盖真实金额的 0.04%**
  //    （trial_balance：1641=160,078.75 vs 1651=386,272,594.21），比恒空更隐蔽。
  //    表达式由 `H8_SEG_*` / `H9_SEG_*` 常量拼出，与后端
  //    `four_table/dual_family_codes.py` 由守卫逐字锁死（禁在此写死字面量清单）。
  H8: [
    { label: `使用权资产原值(${H8_GROSS_CODES.join('/')})`, accountCode: H8_GROSS_CODES[0], expression: tbSumExpr(H8_GROSS_CODES), anchorKey: 'H8-1-tb-amount' },
    { label: `累计折旧(${H8_DEP_CODES.join('/')})`, accountCode: H8_DEP_CODES[0], expression: tbSumExpr(H8_DEP_CODES), anchorKey: 'H8-1-tb-dep' },
    // 减值准备新族无对应码（客户科目表未见 1653）⇒ 宁缺勿造，保持单码
    { label: `减值准备(${H8_IMP_CODES.join('/')})`, accountCode: H8_IMP_CODES[0], expression: tbSumExpr(H8_IMP_CODES), anchorKey: 'H8-1-tb-impair' },
  ],
  H9: [
    { label: `租赁负债(${H9_GROSS_CODES.join('/')})`, accountCode: H9_GROSS_CODES[0], expression: tbSumExpr(H9_GROSS_CODES), anchorKey: 'H9-1-tb-amount' },
    // 未确认融资费用：新族做成 2651.02 子科目、已含在 2651 父额内，再并取即双算
    { label: `未确认融资费用(${H9_UNEARNED_CODES.join('/')})`, accountCode: H9_UNEARNED_CODES[0], expression: tbSumExpr(H9_UNEARNED_CODES), anchorKey: 'H9-1-tb-unearned' },
  ],
  H10: [
    { label: '资产处置损益(6115)', accountCode: '6115', expression: "TB('6115','审定数')", anchorKey: 'H10-1-tb-amount' },
  ],
  I1: [
    { label: '无形资产原值(1701)', accountCode: '1701', expression: "TB('1701','期末余额')", anchorKey: 'I1-1-tb-cost' },
    { label: '累计摊销(1702)', accountCode: '1702', expression: "TB('1702','期末余额')", anchorKey: 'I1-1-tb-amort' },
    { label: '减值准备(1703)', accountCode: '1703', expression: "TB('1703','期末余额')", anchorKey: 'I1-1-tb-impair' },
  ],
  // 🔴 I1~I6 的科目码**单一真源 = `iCycleAccountScope.I_CYCLE_ACCOUNT_SPECS`**
  //    （后端真源 `four_table/i_cycle_accounts.I_CYCLE_SEGMENTS` 的前端镜像）。
  //    本表曾是独立硬编码副本，实测分叉三处（I2 写 1717、I6 写 6602、I5 写 1911），
  //    Task 16 收敛真源时没同步到这里 ⇒ 正是本文件顶部注释警告的「抄 N 份、改一处漏一处」。
  //    现由 `iCycleExtractionSegments.spec.ts` 双向锁死：本表 I 段的 accountCode/expression
  //    必须与真源 fallback 逐字一致，且真源有码的段本表必须有、真源空码的段本表必须无。
  I2: [
    // 1704（`report_config` BS-033 + account_chart 双证）；旧值 1717 全库两张科目表都无
    { label: '开发支出(1704)', accountCode: '1704', expression: "TB('1704','期末余额')", anchorKey: 'I2-1-tb-amount' },
  ],
  I3: [
    { label: '商誉(1711)', accountCode: '1711', expression: "TB('1711','期末余额')", anchorKey: 'I3-1-tb-amount' },
  ],
  I4: [
    { label: '长期待摊费用(1801)', accountCode: '1801', expression: "TB('1801','期末余额')", anchorKey: 'I4-1-tb-amount' },
  ],
  // 🔴 I5 **不产段**：真源 `I_CYCLE_ACCOUNT_SPECS.I5` 的 cost 段 `fallback: []`
  //    —— `1911` 全库 `account_chart` 两个 source 都零命中，给了兜底码只会产出一个
  //    查不到任何数据的假前缀，把「本项目无此科目」掩盖成 0（宁缺勿造，R1.4）。
  //    旧值 `TB('1911','期末余额')` 取数恒空。
  //    📌 遗留改进：段为空 ⇒ HI 溯源面板整块不渲染，审计师看不到「本项目无此科目」的
  //       显式提示（与 I5-1 审定表 `WpFourTableSourcePanel` 自我隐藏是同一问题）。
  //       应让面板在 `iCycleAccountAbsent()` 为真时渲染一行明确提示而非整块消失。
  I5: [],
  I6: [
    // 6604 研发费用；旧值 6602 是**管理费用**（全库借方 6.24 亿）⇒ 数字完全错
    { label: '研发费用(6604)', accountCode: '6604', expression: "TB('6604','审定数')", anchorKey: 'I6-1-tb-amount' },
  ],
}

export function getHiExtractionSegments(wpCode: string): HiExtractionSegment[] {
  return _REGISTRY[wpCode] ?? []
}
