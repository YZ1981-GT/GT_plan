/**
 * H1 固定资产披露表内部勾稽校验（纯函数，上市 / 国企双变体）
 *
 * 源模板要求的联动点：
 * - 汇总表（R7–R10）「固定资产」行 = ①情况表账面价值（期末 / 期初）；
 *   「固定资产清理」行 = （2）清理表合计。
 * - R56 红字：政府补助冲减固定资产账面价值的金额应在①表原值「（2）其他减少」中列示
 *   → ⑤政府补助金额不得超过该行合计。
 * - ②闲置 / ③经营租出 / ④未办妥产权证书 都是①表期末账面价值的**子集**，不得超出。
 * - ⑥已提足折旧（平台增强）披露账面原值，不得超过①表原值期末合计。
 * - 国企：土地资产不计提折旧（源模板 R24 整行「—」）。
 *
 * 设计约定：只做**可判定**的勾稽，不猜业务意图；不等式类超出报 error，
 * 相等类差异按容差 0.01 元（分）判定，差异非零报 error，无数据一律 ok。
 */
import {
  H1_LISTED_MOVEMENT_ROWS,
  num,
  idleBookValue,
  sumClearing,
  sumFullyDep,
  sumIdle,
  sumLease,
  totalCellValue,
  type ClearingRow,
  type FullyDepRow,
  type H1ListedCategory,
  type IdleRow,
  type LeaseOutRow,
  type MovementCellMap,
  type SummaryRow,
  type TitleCertRow,
} from './h1ListedDisclosureModel'
import {
  H1_SOE_CATEGORIES,
  clearingSubtotal,
  fullyDepSubtotal,
  idleSubtotal,
  layerTotal,
  titleSubtotal,
  n as soeNum,
  type H1SoeDisclosureState,
  type H1SoeFullyDepRow,
  type H1SoeLayer,
} from './h1SoeDisclosureModel'

/** 金额容差：1 分 */
export const H1_AMOUNT_TOLERANCE = 0.01

export type H1CheckLevel = 'ok' | 'warn' | 'error'

export interface H1ConsistencyCheck {
  id: string
  /** 校验项名（UI 首列） */
  label: string
  /** 勾稽规则文字，供审计追溯 */
  rule: string
  level: H1CheckLevel
  /** 左值（本表金额） */
  left: number
  /** 右值（勾稽对象金额） */
  right: number
  /** left − right */
  diff: number
  /** 结论描述 */
  detail: string
  /** 相关索引（GtIndexChip / 附注章节），供跳转追溯 */
  refs: string[]
}

export interface H1ConsistencySummary {
  checks: H1ConsistencyCheck[]
  errorCount: number
  warnCount: number
  okCount: number
  /** 全部通过 */
  allPass: boolean
}

function round2(v: number): number {
  return Math.round(num(v) * 100) / 100
}

/** 相等类勾稽：|left − right| ≤ 容差 → ok */
function eqCheck(
  id: string,
  label: string,
  rule: string,
  left: number,
  right: number,
  refs: string[],
  opts?: { leftName?: string; rightName?: string },
): H1ConsistencyCheck {
  const l = round2(left)
  const r = round2(right)
  const diff = round2(l - r)
  const ln = opts?.leftName ?? '本表'
  const rn = opts?.rightName ?? '勾稽值'
  return {
    id,
    label,
    rule,
    left: l,
    right: r,
    diff,
    level: Math.abs(diff) <= H1_AMOUNT_TOLERANCE ? 'ok' : 'error',
    detail:
      Math.abs(diff) <= H1_AMOUNT_TOLERANCE
        ? '一致'
        : `${ln} ${l.toFixed(2)} 与${rn} ${r.toFixed(2)} 相差 ${diff.toFixed(2)}`,
    refs,
  }
}

/** 子集类勾稽：left ≤ right + 容差 → ok；right 为 0 且 left > 0 时视为缺上层数据（warn） */
function subsetCheck(
  id: string,
  label: string,
  rule: string,
  left: number,
  right: number,
  refs: string[],
): H1ConsistencyCheck {
  const l = round2(left)
  const r = round2(right)
  const diff = round2(l - r)
  let level: H1CheckLevel = 'ok'
  let detail = '未超出上限'
  if (l > 0 && r === 0) {
    level = 'warn'
    detail = `本表已填 ${l.toFixed(2)}，但①情况表对应上限为 0 —— 请先完成①表取数`
  } else if (diff > H1_AMOUNT_TOLERANCE) {
    level = 'error'
    detail = `本表 ${l.toFixed(2)} 超出上限 ${r.toFixed(2)}，超出 ${diff.toFixed(2)}`
  }
  return { id, label, rule, left: l, right: r, diff, level, detail, refs }
}

function summarize(checks: H1ConsistencyCheck[]): H1ConsistencySummary {
  const errorCount = checks.filter((c) => c.level === 'error').length
  const warnCount = checks.filter((c) => c.level === 'warn').length
  return {
    checks,
    errorCount,
    warnCount,
    okCount: checks.length - errorCount - warnCount,
    allPass: errorCount === 0 && warnCount === 0,
  }
}

// ─── 上市 ────────────────────────────────────────────────────────────────────

export interface H1ListedConsistencyInput {
  summary: SummaryRow[]
  categories: readonly H1ListedCategory[]
  movement: MovementCellMap
  idle: IdleRow[]
  leaseOut: LeaseOutRow[]
  titleCert: TitleCertRow[]
  clearing: ClearingRow[]
  fullyDep: FullyDepRow[]
  govSubsidyAmount: number
}

/** ①情况表某行的「合计」列值 */
export function listedMovementTotal(
  movement: MovementCellMap,
  categories: readonly H1ListedCategory[],
  rowKey: string,
): number {
  const def = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === rowKey)
  if (!def) return 0
  return totalCellValue(movement, def, categories)
}

export function checkH1ListedConsistency(
  input: H1ListedConsistencyInput,
): H1ConsistencySummary {
  const { movement, categories } = input
  const total = (rowKey: string) => listedMovementTotal(movement, categories, rowKey)

  const bookEnd = total('book_end')
  const bookBegin = total('book_begin')
  const costEnd = total('cost_end')
  const costDecOther = total('cost_dec_other')

  const faRow = input.summary.find((r) => r.key === 'fixed_assets')
  const clearingRow = input.summary.find((r) => r.key === 'clearing')
  const clearingTot = sumClearing(input.clearing)
  const idleTot = sumIdle(input.idle)
  const titleTot = input.titleCert.reduce((s, r) => s + num(r.bookValue), 0)

  const checks: H1ConsistencyCheck[] = [
    eqCheck(
      'listed-summary-fa-end',
      '汇总表「固定资产」期末余额',
      '汇总表固定资产期末余额 = ①固定资产情况表「四、账面价值 / 1.期末账面价值」合计列',
      num(faRow?.endBalance),
      bookEnd,
      ['Note:五、22'],
      { leftName: '汇总表', rightName: '①表期末账面价值' },
    ),
    eqCheck(
      'listed-summary-fa-begin',
      '汇总表「固定资产」上年年末余额',
      '汇总表固定资产上年年末余额 = ①表「四、账面价值 / 2.期初账面价值」合计列',
      num(faRow?.priorBalance),
      bookBegin,
      ['Note:五、22'],
      { leftName: '汇总表', rightName: '①表期初账面价值' },
    ),
    eqCheck(
      'listed-summary-clearing-end',
      '汇总表「固定资产清理」期末余额',
      '汇总表固定资产清理期末余额 = （2）固定资产清理表期末余额合计',
      num(clearingRow?.endBalance),
      clearingTot.endBalance,
      ['wp:H6'],
      { leftName: '汇总表', rightName: '清理表合计' },
    ),
    eqCheck(
      'listed-summary-clearing-begin',
      '汇总表「固定资产清理」上年年末余额',
      '汇总表固定资产清理上年年末余额 = （2）清理表上年年末余额合计',
      num(clearingRow?.priorBalance),
      clearingTot.priorBalance,
      ['wp:H6'],
      { leftName: '汇总表', rightName: '清理表合计' },
    ),
    subsetCheck(
      'listed-gov-subsidy-in-other-dec',
      '⑤政府补助冲减金额',
      '源模板提示：政府补助冲减固定资产账面价值的金额应在①表账面原值「（2）其他减少」中列示，故不得超过该行合计',
      num(input.govSubsidyAmount),
      costDecOther,
      ['Note:五、22'],
    ),
    subsetCheck(
      'listed-idle-within-book',
      '②暂时闲置账面价值合计',
      '闲置固定资产是期末固定资产的子集：合计账面价值 ≤ ①表期末账面价值合计',
      idleTot.bookValue,
      bookEnd,
      ['wp:H1-4'],
    ),
    subsetCheck(
      'listed-lease-within-book',
      '③经营租出账面价值合计',
      '经营租出固定资产是期末固定资产的子集：合计账面价值 ≤ ①表期末账面价值合计',
      sumLease(input.leaseOut),
      bookEnd,
      ['wp:H1-19'],
    ),
    subsetCheck(
      'listed-title-within-book',
      '④未办妥产权证书账面价值合计',
      '未办证固定资产是期末固定资产的子集：合计账面价值 ≤ ①表期末账面价值合计',
      titleTot,
      bookEnd,
      ['wp:H1-16'],
    ),
    subsetCheck(
      'listed-fullydep-within-cost',
      '⑥已提足折旧账面原值合计',
      '已提足折旧仍在使用的资产是期末资产的子集：合计账面原值 ≤ ①表账面原值期末余额合计',
      sumFullyDep(input.fullyDep),
      costEnd,
      ['wp:H1-2'],
    ),
    eqCheck(
      'listed-idle-book-formula',
      '②闲置表账面价值公式',
      '账面价值 = 账面原值 − 累计折旧 − 减值准备（逐行成立，合计随之成立）',
      idleTot.bookValue,
      input.idle.reduce((s, r) => s + idleBookValue(r), 0),
      [],
      { leftName: '合计行', rightName: '逐行推导' },
    ),
  ]

  return summarize(checks)
}

// ─── 国企 ────────────────────────────────────────────────────────────────────

export interface H1SoeConsistencyInput {
  state: H1SoeDisclosureState
  fullyDep: H1SoeFullyDepRow[]
}

function soeLayerTotal(state: H1SoeDisclosureState, layer: H1SoeLayer) {
  const block = state.layers.find((l) => l.layer === layer)
  return block ? layerTotal(block) : { begin: 0, increase: 0, decrease: 0, end: 0 }
}

/** 指定层的土地资产金额绝对量之和（源模板整行「—」时应为 0） */
function soeLandAmount(state: H1SoeDisclosureState, layer: H1SoeLayer): number {
  const block = state.layers.find((l) => l.layer === layer)
  const land = block?.categories.find((c) => c.key === 'land')
  if (!land) return 0
  return soeNum(land.begin) + soeNum(land.increase) + soeNum(land.decrease) + soeNum(land.end)
}

/** 土地资产累计折旧（源模板 R24：整行「—」，应为 0） */
export function soeLandDepreciation(state: H1SoeDisclosureState): number {
  return soeLandAmount(state, 'dep')
}

/** 土地资产减值准备（源模板 R42：整行「--」，应为 0） */
export function soeLandImpairment(state: H1SoeDisclosureState): number {
  return soeLandAmount(state, 'impair')
}

export function checkH1SoeConsistency(input: H1SoeConsistencyInput): H1ConsistencySummary {
  const { state } = input
  const cost = soeLayerTotal(state, 'cost')
  const dep = soeLayerTotal(state, 'dep')
  const net = soeLayerTotal(state, 'net')
  const impair = soeLayerTotal(state, 'impair')
  const carrying = soeLayerTotal(state, 'carrying')

  const clearingTot = clearingSubtotal(state.clearingRows)
  const idleTot = idleSubtotal(state.idleRows)
  const landDep = soeLandDepreciation(state)

  const checks: H1ConsistencyCheck[] = [
    eqCheck(
      'soe-net-formula-end',
      '三、账面净值合计（期末）',
      '固定资产账面净值 = 账面原值 − 累计折旧（源模板三、层为推导层）',
      net.end,
      cost.end - dep.end,
      ['Note:八、22'],
      { leftName: '净值层', rightName: '原值−折旧' },
    ),
    eqCheck(
      'soe-carrying-formula-end',
      '五、账面价值合计（期末）',
      '固定资产账面价值 = 账面净值 − 减值准备',
      carrying.end,
      net.end - impair.end,
      ['Note:八、22'],
      { leftName: '账面价值层', rightName: '净值−减值' },
    ),
    eqCheck(
      'soe-carrying-formula-begin',
      '五、账面价值合计（期初）',
      '期初账面价值 = 期初账面原值 − 期初累计折旧 − 期初减值准备',
      carrying.begin,
      cost.begin - dep.begin - impair.begin,
      ['Note:八、22'],
      { leftName: '账面价值层', rightName: '原值−折旧−减值' },
    ),
    eqCheck(
      'soe-cost-rollforward',
      '一、账面原值合计 期末结转',
      '期末余额 = 期初余额 + 本期增加 − 本期减少',
      cost.end,
      cost.begin + cost.increase - cost.decrease,
      ['wp:H1-2'],
      { leftName: '期末余额', rightName: '期初+增−减' },
    ),
    eqCheck(
      'soe-dep-rollforward',
      '二、累计折旧合计 期末结转',
      '期末余额 = 期初余额 + 本期增加 − 本期减少',
      dep.end,
      dep.begin + dep.increase - dep.decrease,
      ['wp:H1-12'],
      { leftName: '期末余额', rightName: '期初+增−减' },
    ),
    eqCheck(
      'soe-impair-rollforward',
      '四、减值准备合计 期末结转',
      '期末余额 = 期初余额 + 本期增加 − 本期减少',
      impair.end,
      impair.begin + impair.increase - impair.decrease,
      ['wp:H1-14'],
      { leftName: '期末余额', rightName: '期初+增−减' },
    ),
    eqCheck(
      'soe-summary-clearing-end',
      '汇总表「固定资产清理」期末账面价值',
      '汇总表清理行 = （2）固定资产清理表期末账面价值合计',
      soeNum(state.summary.clearingEnd),
      clearingTot.end,
      ['wp:H6'],
      { leftName: '汇总表', rightName: '清理表合计' },
    ),
    eqCheck(
      'soe-summary-clearing-begin',
      '汇总表「固定资产清理」期初账面价值',
      '汇总表清理行 = （2）清理表期初账面价值合计',
      soeNum(state.summary.clearingBegin),
      clearingTot.begin,
      ['wp:H6'],
      { leftName: '汇总表', rightName: '清理表合计' },
    ),
    eqCheck(
      'soe-land-no-depreciation',
      '土地资产累计折旧',
      '源模板约定：土地资产不计提折旧，累计折旧层该行整行填「—」（金额应为 0）',
      landDep,
      0,
      ['Note:八、22'],
      { leftName: '土地资产折旧', rightName: '模板约定' },
    ),
    eqCheck(
      'soe-land-no-impairment',
      '土地资产减值准备',
      '源模板约定：土地资产不单独计提减值准备，减值准备层该行整行填「--」（金额应为 0）',
      soeLandImpairment(state),
      0,
      ['Note:八、22'],
      { leftName: '土地资产减值', rightName: '模板约定' },
    ),
    subsetCheck(
      'soe-idle-within-carrying',
      '②暂时闲置账面价值合计',
      '闲置固定资产是期末固定资产的子集：合计账面价值 ≤ 五、账面价值合计期末余额',
      idleTot.carrying,
      carrying.end,
      ['wp:H1-4'],
    ),
    subsetCheck(
      'soe-title-within-carrying',
      '③未办妥产权证书账面价值合计',
      '未办证固定资产是期末固定资产的子集：合计账面价值 ≤ 五、账面价值合计期末余额',
      titleSubtotal(state.titleRows),
      carrying.end,
      ['wp:H1-16'],
    ),
    subsetCheck(
      'soe-fullydep-within-cost',
      '⑥已提足折旧账面原值合计',
      '已提足折旧仍在使用的资产是期末资产的子集：合计账面原值 ≤ 一、账面原值合计期末余额',
      fullyDepSubtotal(input.fullyDep),
      cost.end,
      ['wp:H1-2'],
    ),
  ]

  return summarize(checks)
}

/** 国企各层「其中：」类别之和是否等于该层合计（源模板每层合计 = Σ 分类） */
export function checkSoeLayerCategorySum(
  state: H1SoeDisclosureState,
): H1ConsistencyCheck[] {
  const known = new Set(H1_SOE_CATEGORIES.map((c) => c.key))
  return state.layers.map((block) => {
    const tot = layerTotal(block)
    const sum = block.categories
      .filter((c) => known.has(c.key))
      .reduce((s, c) => s + soeNum(c.end), 0)
    return eqCheck(
      `soe-layer-sum-${block.layer}`,
      `${block.layer} 层「其中：」分类求和`,
      '每层合计行 = 该层「其中：」各类别期末余额之和',
      tot.end,
      sum,
      ['Note:八、22'],
      { leftName: '合计行', rightName: '分类求和' },
    )
  })
}
