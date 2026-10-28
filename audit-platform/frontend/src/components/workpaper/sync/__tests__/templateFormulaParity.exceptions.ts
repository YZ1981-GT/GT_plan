/**
 * 前端 ↔ 模板公式对拍的例外登记（spec oo-writeback-template-parity-closure R2.4，design §3.3）。
 *
 * 两张表都**只许减少**：守卫断言条数等于基线（减少了同步改小基线；增加需要在评审里说明为什么不改前端），
 * 并断言每一条都还在生效（未覆盖的 store item 仍有可对拍的公式、例外仍能挡住至少一处不一致）——
 * 前端修好了、例外却没删，守卫同样报红。
 *
 * 现有条目除 F3-4 计息口径（待用户裁决，裁决后改模板或前端再删）外全部是 R3（契约字段与前端字段没接通 /
 * 接错列），由任务 9 改契约或补前端后逐条删除。
 */
import type { ParityRow } from './templateFormulaParity.adapters'

const R3_FIELD_NAMES = 'R3 任务 9：契约字段名与前端行模型不同，前端算的是另一组字段，接通前对拍不了'

/** 没有适配器的 store item（有可对拍的模板公式，但前端行计算还接不上）→ 理由 */
export const UNCOVERED_ITEMS: Readonly<Record<string, string>> = {
  'B60-1-hour-budget-rows': '前端不算预算成本（模板 F 列独有，面板只录工时与费率）；R3 任务 9 决定前端补列或契约移出',
  'D2-ecl-discount-rows': 'R3 任务 9：前端是嵌套 scenarios[]、单一现值，模板是平铺情景行、两年现值（design §3.1 D2-10）',
  'F2-47-rows': 'R3 任务 9：契约列名仍与模板表头错位，且前端行模型与模板不同构（双价 pricePreContract / priceContract 对模板单价 P；销售费用 / 税费前端可手改，模板 T = N × Q、U = O × Q；应补提前端截 0，模板 Z = W − Y 可为负），回写未接通，先不改契约',
  'F3-1-adj-seed-rows': 'R3 任务 9：字段名已对齐（9.4c），但契约 store item 前端不存在（前端两区共存 F3-1-adj-rows，要区判据 + 多区门面）；且前端可录期初未审 / 期末调整，模板首区全是 F3-2 的 SUMPRODUCT（行模型待 R2 裁决）',
  'F3-1-adj-slot-rows': 'R3 任务 9：字段名已对齐（9.4c），但契约 store item 前端不存在（前端两区共存 F3-1-adj-rows，要区判据 + 多区门面）',
  'F4-1-adj-aging-seed-rows': 'R3 任务 9：字段名已对齐（9.4c），但契约 store item 前端不存在（前端账龄段行 + 残差行共存 F4-1-adj-aging-rows，要区判据 + 多区门面）',
  'F4-1-adj-aging-slot-rows': 'R3 任务 9：字段名已对齐（9.4c），但契约 store item 前端不存在（前端账龄段行 + 残差行共存 F4-1-adj-aging-rows，要区判据 + 多区门面）',
  'G5-2-rows': 'R3 任务 9：前端行模型与模板列不同构（前端 合同金额 − 已收回，模板 期初 + 借 − 贷 与审定三列，期初 / 调整列前端都没有）',
  'H3-2-cost-rows': 'R3 任务 9：前端期末多算转入 / 转出两列，审定三列按「未审 + AJE + RJE」而模板是审定滚动；模板 I~N / V~AA / AI~AN 前端无字段（design §3.2）',
  'N2-2-detail-rows': 'R3 批 C：字段名已改前端名，但前端无 H 列 beginRje（模板重分类调整列），行模型 R2 待裁',
  'N3-2-rows': 'R3 批 C：字段名已改前端名，但前端 useN3Detail 行模型与模板不同构（无两期暂时性差异 / 调整列）',
  'N4-2-detail-rows': 'R3 批 C：前端 N4 存 taxBasis×taxRate，不是模板的 未审+调整=审定',
}

export const UNCOVERED_BASELINE = 12

export interface ParityException {
  storeItem: string
  field: string
  /** formula = 前端算出的值与模板公式不一致；input = 前端改写了录入值（模板直接用录入值） */
  kind: 'formula' | 'input'
  reason: string
  /** 只在满足条件的样本上豁免；不写 = 整列豁免 */
  when?: (raw: ParityRow, row: ParityRow) => boolean
}

export const PARITY_EXCEPTIONS: readonly ParityException[] = [
  {
    // 字段名接通后（9.4c）新暴露、待用户裁决的口径差异，不是接错列：H 是公式列、不回写，两侧各按自己的口径显示
    storeItem: 'F3-4-rows', field: 'payableInterest', kind: 'formula',
    reason: '计息口径待用户确认：模板 H = ROUND(F*G,2)（不含天数），前端有出票日 / 到期日时按 票面金额 × 利率% × 期限 / 360；没有日期时两侧一致',
    when: (_raw, row) => Number(row.termDays) > 0,
  },
]

export const PARITY_EXCEPTION_BASELINE = 1
