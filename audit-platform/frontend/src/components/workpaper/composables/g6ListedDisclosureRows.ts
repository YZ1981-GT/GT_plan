/**
 * G6 其他债权投资 — 附注披露（上市公司）行模型（纯函数，可单测）
 *
 * 🔴 **重写背景**：旧 `G6TabDisclosureListed.vue` 是**自造**的 —— 7 个虚构小节
 * （一、其他债权投资成本 / 二、利息调整 / … / 七、其他披露事项）+ `generateRows()`
 * 批量生成 137 行 `成本项目N`，列头也是自拟的，与源模板对不上任何一张表。
 * 接附注同步会把这些假行推进附注，故必须先按源模板重写。
 *
 * **权威源**：`backend/wp_templates/G/G6 其他债权投资.xlsx` sheet「附注披露信息（上市公司）」
 * （运行时权威模板库；`基础数据/…` 那份参考副本已落后）逐格精读 + `附注模版/上市报表附注_单体.md`
 * §其他债权投资 交叉验证。
 *
 * 源模板 6 个小节 / 14 张表：
 *
 * | # | 表 | 列 |
 * |---|----|----|
 * | 1 | 其他债权投资（主表）| 项目 / 期末余额 / 上年年末余额（3 列单级）|
 * | 2 | （1）其他债权投资情况 | 8 列单级（期初余额…累计在其他综合收益中确认的减值准备）|
 * | 3 | （2）减值准备本期变动情况 | 5 列单级（期初/本期增加/本期减少/期末）|
 * | 4 | （3）期末重要的其他债权投资 | 项目 + 期末余额{面值/票面利率/实际利率/到期日/逾期本金} |
 * | 5 | 续：上年年末余额 | 同上，父表头换成上年年末余额 |
 * | 6~11 | （4）六张三阶段减值表 | 复用 `g4ListedStageDisclosure` 模型 |
 * | 12 | （5）本期计提、收回或转回 | 减值准备 + 第一/二/三阶段 + 合计（两级，12 行固定）|
 * | 13 | （6）本期实际核销 | 项目 / 核销金额 |
 * | 14 | 重要核销情况（逐项披露）| 6 列单级 |
 *
 * 源模板「项目N（可改名）」「（预留，可填或在本区内插入行）」是**占位提示**，
 * 落成初始空行（可改名 / 可增删），不作为披露数据行。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.3
 */
import {
  buildG6ListedStageBlocks,
  parseStageBlocks,
  serializeStageBlocks,
  stageTotals,
  type G4StageBlock,
} from './g4ListedStageDisclosure'

export const G6_LISTED_ACCOUNT = '其他债权投资'

// ─────────────────────────── 行类型 ───────────────────────────

/** 主表 / 减值变动表共用的「可改名 + 若干金额列」行 */
export interface G6NamedRow {
  id: string
  label: string
  /** 结构行（小计 / 减：一年内到期 / 合计 / 其他（如有））不可删、名不可改 */
  fixed?: boolean
  kind?: 'data' | 'subtotal' | 'deduction' | 'total'
}

export interface G6BalanceRow extends G6NamedRow {
  endBalance: number
  priorBalance: number
}

/** （1）其他债权投资情况：A~G 七个金额列 */
export interface G6FairValueRow extends G6NamedRow {
  openingFv: number
  accruedInterest: number
  fvChangeCurrent: number
  closingFv: number
  cost: number
  fvChangeCumulative: number
  ociImpairment: number
}

/** （2）减值准备本期变动情况 */
export interface G6ProvisionMovementRow extends G6NamedRow {
  opening: number
  increase: number
  decrease: number
}

/** （3）期末重要的其他债权投资（期末 / 上年年末各一张） */
export interface G6ImportantRow extends G6NamedRow {
  faceValue: number
  couponRate: string
  effectiveRate: string
  maturityDate: string
  overduePrincipal: number
}

/** （5）本期计提、收回或转回的减值准备情况（12 行固定） */
export interface G6StageMoveRow {
  rowKey: string
  label: string
  stage1: number
  stage2: number
  stage3: number
  /** 阶段间转移行的符号约束提示（源模板用【负数】/【正数】标注） */
  signHint?: string
}

/** （6）重要核销情况（逐项披露） */
export interface G6WriteoffRow {
  id: string
  label: string
  nature: string
  amount: number
  reason: string
  procedure: string
  relatedParty: boolean
}

export interface G6ListedDisclosureState {
  version: 1
  balanceRows: G6BalanceRow[]
  fairValueRows: G6FairValueRow[]
  provisionRows: G6ProvisionMovementRow[]
  importantEndRows: G6ImportantRow[]
  importantPriorRows: G6ImportantRow[]
  stageBlocks: G4StageBlock[]
  stageMoveRows: G6StageMoveRow[]
  writeoffTotal: number
  writeoffRows: G6WriteoffRow[]
  /** 源模板 R20 C2 的说明行 */
  fvNote: string
  /** 源模板 R96：本期发生损失准备的账面余额显著变动情况 */
  significantChangeNote: string
  /** 源模板 R97：本期减值准备计提金额与信用风险显著增加的判断依据 */
  judgementBasisNote: string
}

// ─────────────────────────── 常量（源模板逐字） ───────────────────────────

export const G6_SUBTOTAL_LABEL = '小 计'
export const G6_TOTAL_LABEL = '合 计'
export const G6_DEDUCTION_LABEL = '减：一年内到期的其他债权投资'
export const G6_OTHER_IF_ANY_LABEL = '其他（如有）'
export const G6_WRITEOFF_ROW_LABEL = '实际核销的其他债权投资'

/** （5）表 12 行 —— 源模板 R152~R163 逐字 */
export const G6_STAGE_MOVE_ROWS: ReadonlyArray<{ rowKey: string; label: string; signHint?: string }> = [
  { rowKey: 'opening', label: '期初余额' },
  { rowKey: 'opening_in_period', label: '期初余额在本期' },
  { rowKey: 'to_stage2', label: '--转入第二阶段', signHint: '一阶段【负数】/二阶段【正数】' },
  { rowKey: 'to_stage3', label: '--转入第三阶段', signHint: '一、二阶段【负数】/三阶段【正数】' },
  { rowKey: 'back_stage2', label: '--转回第二阶段', signHint: '二阶段【正数】/三阶段【负数】' },
  { rowKey: 'back_stage1', label: '--转回第一阶段', signHint: '一阶段【正数】/二、三阶段【负数】' },
  { rowKey: 'provision', label: '本期计提' },
  { rowKey: 'reversal', label: '本期转回' },
  { rowKey: 'write_down', label: '本期转销' },
  { rowKey: 'write_off', label: '本期核销' },
  { rowKey: 'other', label: '其他变动' },
  { rowKey: 'closing', label: '期末余额' },
]

/** 源模板「编制说明」（R174~R180），作为编制提示展示，不进披露数据 */
export const G6_LISTED_PREP_NOTES: readonly string[] = [
  '本表服务于财务报表附注披露：公允价值取自审定表 G6-1 / 明细表 G6-2，减值准备取自坏账准备明细表 G6-3，并与三阶段划分 G6-11、减值测算 G6-12/G6-13 勾稽。',
  '主表按公允价值列示；扣减一年内到期部分后，应与资产负债表「其他债权投资」及审定表 G6-1 一致。损失准备在其他综合收益中确认，不冲减资产负债表列示的账面价值。',
  '第（4）部分按 CAS 22 三阶段披露：第一阶段采用未来 12 个月 ECL，第二、三阶段采用整个存续期 ECL；本区「账面价值」属于减值分析口径，不得与资产负债表公允价值列示口径混同。',
  '第（5）部分阶段转移：同一行三个阶段金额代数和应为 0；期末余额 ＝ 期初 ＋ 阶段转移 ＋ 计提 − 转回 − 转销 − 核销 ＋ 其他，并与坏账准备明细表 G6-3 期末审定数勾稽。',
  '重要核销信息应逐项披露投资性质、核销原因、履行程序、核销金额及是否由关联交易产生。',
  '三阶段「其中」为可扩展区：默认 1 行明细 ＋ 预留行；仅在对应「按单项 / 按组合」与下一父行之间填写或插入行，平台对应「+添加其中行」。',
]

/**
 * 核销区披露要求（与「编制说明」第 5 条同源，仅重述、不新增口径）。
 * 展示在（6）重要核销明细表下方，避免用户漏填其中任一要素。
 */
export const G6_WRITEOFF_REG_NOTE =
  '重要的其他债权投资核销应逐项披露：被核销单位（项目）、其他债权投资性质、核销金额、核销原因、履行的核销程序，以及是否由关联交易产生。'

/** 源模板 R21 / R22 的两条红字提示 */
export const G6_LISTED_FORMULA_HINT =
  '【提示：期末公允价值D=期初公允价值A+当期应计利息B（即实际利息收入-实收利息）+当期公允价值变动C=初始成本E+累计应计利息∑B+累计公允价值变动F（即期末公允价值D-期末摊余成本）】'
export const G6_LISTED_OCI_HINT =
  '【G：对于以公允价值计量且其变动计入其他综合收益的金融资产，企业应当在其他综合收益中确认其损失准备，并将减值损失或利得计入当期损益，且不应减少该金融资产在资产负债表中列示的账面价值】'

// ─────────────────────────── 构造 ───────────────────────────

let _seq = 0
function uid(prefix: string): string {
  _seq += 1
  return `${prefix}-${Date.now().toString(36)}-${_seq.toString(36)}`
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function txt(v: unknown): string {
  return String(v ?? '')
}

export function emptyBalanceRow(label = ''): G6BalanceRow {
  return { id: uid('bal'), label, endBalance: 0, priorBalance: 0, kind: 'data' }
}

export function emptyFairValueRow(label = ''): G6FairValueRow {
  return {
    id: uid('fv'), label, kind: 'data',
    openingFv: 0, accruedInterest: 0, fvChangeCurrent: 0, closingFv: 0,
    cost: 0, fvChangeCumulative: 0, ociImpairment: 0,
  }
}

export function emptyProvisionRow(label = ''): G6ProvisionMovementRow {
  return { id: uid('prov'), label, opening: 0, increase: 0, decrease: 0, kind: 'data' }
}

export function emptyImportantRow(label = ''): G6ImportantRow {
  return {
    id: uid('imp'), label, kind: 'data',
    faceValue: 0, couponRate: '', effectiveRate: '', maturityDate: '', overduePrincipal: 0,
  }
}

export function emptyWriteoffRow(): G6WriteoffRow {
  return {
    id: uid('wo'), label: '', nature: '', amount: 0,
    reason: '', procedure: '', relatedParty: false,
  }
}

export function buildDefaultG6ListedState(): G6ListedDisclosureState {
  return {
    version: 1,
    // 源模板 R8~R13：3 个可改名空行 + 小计 + 减：一年内到期 + 合计
    balanceRows: [
      emptyBalanceRow(), emptyBalanceRow(), emptyBalanceRow(),
      { ...emptyBalanceRow(G6_SUBTOTAL_LABEL), fixed: true, kind: 'subtotal' },
      { ...emptyBalanceRow(G6_DEDUCTION_LABEL), fixed: true, kind: 'deduction' },
      { ...emptyBalanceRow(G6_TOTAL_LABEL), fixed: true, kind: 'total' },
    ],
    // 源模板 R16~R19：3 个空行 + 合计
    fairValueRows: [
      emptyFairValueRow(), emptyFairValueRow(), emptyFairValueRow(),
      { ...emptyFairValueRow(G6_TOTAL_LABEL), fixed: true, kind: 'total' },
    ],
    // 源模板 R25~R28：2 个空行 + 其他（如有）+ 合计
    provisionRows: [
      emptyProvisionRow(), emptyProvisionRow(),
      { ...emptyProvisionRow(G6_OTHER_IF_ANY_LABEL), fixed: true, kind: 'data' },
      { ...emptyProvisionRow(G6_TOTAL_LABEL), fixed: true, kind: 'total' },
    ],
    // 源模板 R32~R35 / R39~R42：3 个可改名空行 + 合计
    importantEndRows: [
      emptyImportantRow(), emptyImportantRow(), emptyImportantRow(),
      { ...emptyImportantRow(G6_TOTAL_LABEL), fixed: true, kind: 'total' },
    ],
    importantPriorRows: [
      emptyImportantRow(), emptyImportantRow(), emptyImportantRow(),
      { ...emptyImportantRow(G6_TOTAL_LABEL), fixed: true, kind: 'total' },
    ],
    stageBlocks: buildG6ListedStageBlocks(),
    stageMoveRows: G6_STAGE_MOVE_ROWS.map((r) => ({ ...r, stage1: 0, stage2: 0, stage3: 0 })),
    writeoffTotal: 0,
    // 源模板 R169~R172：3 个空行 + 合计（合计行由派生计算，不落成行）
    writeoffRows: [emptyWriteoffRow(), emptyWriteoffRow(), emptyWriteoffRow()],
    fvNote: '',
    significantChangeNote: '',
    judgementBasisNote: '',
  }
}

// ─────────────────────────── 派生（公式列） ───────────────────────────

/** 主表：小计 = 明细之和；合计 = 小计 − 减：一年内到期 */
export function recomputeBalanceRows(rows: readonly G6BalanceRow[]): G6BalanceRow[] {
  const detail = rows.filter((r) => r.kind === 'data')
  const sumEnd = detail.reduce((s, r) => s + num(r.endBalance), 0)
  const sumPrior = detail.reduce((s, r) => s + num(r.priorBalance), 0)
  const ded = rows.find((r) => r.kind === 'deduction')
  return rows.map((r) => {
    if (r.kind === 'subtotal') return { ...r, endBalance: sumEnd, priorBalance: sumPrior }
    if (r.kind === 'total') {
      return {
        ...r,
        endBalance: sumEnd - num(ded?.endBalance),
        priorBalance: sumPrior - num(ded?.priorBalance),
      }
    }
    return r
  })
}

/** （1）表：期末公允价值 D = 期初 A + 应计利息 B + 本期公允价值变动 C；合计行按列求和 */
export function recomputeFairValueRows(rows: readonly G6FairValueRow[]): G6FairValueRow[] {
  const withClosing = rows.map((r) =>
    r.kind === 'total'
      ? r
      : { ...r, closingFv: num(r.openingFv) + num(r.accruedInterest) + num(r.fvChangeCurrent) },
  )
  const detail = withClosing.filter((r) => r.kind === 'data')
  const sum = (pick: (r: G6FairValueRow) => number) => detail.reduce((s, r) => s + num(pick(r)), 0)
  return withClosing.map((r) =>
    r.kind === 'total'
      ? {
          ...r,
          openingFv: sum((x) => x.openingFv),
          accruedInterest: sum((x) => x.accruedInterest),
          fvChangeCurrent: sum((x) => x.fvChangeCurrent),
          closingFv: sum((x) => x.closingFv),
          cost: sum((x) => x.cost),
          fvChangeCumulative: sum((x) => x.fvChangeCumulative),
          ociImpairment: sum((x) => x.ociImpairment),
        }
      : r,
  )
}

/** （2）表：期末 = 期初 + 本期增加 − 本期减少；合计行按列求和（含「其他（如有）」） */
export function recomputeProvisionRows(
  rows: readonly G6ProvisionMovementRow[],
): G6ProvisionMovementRow[] {
  const detail = rows.filter((r) => r.kind !== 'total')
  const sum = (pick: (r: G6ProvisionMovementRow) => number) =>
    detail.reduce((s, r) => s + num(pick(r)), 0)
  return rows.map((r) =>
    r.kind === 'total'
      ? {
          ...r,
          opening: sum((x) => x.opening),
          increase: sum((x) => x.increase),
          decrease: sum((x) => x.decrease),
        }
      : r,
  )
}

export function provisionClosing(row: G6ProvisionMovementRow): number {
  return num(row.opening) + num(row.increase) - num(row.decrease)
}

/** 重要投资表：合计行只加总面值与逾期本金；利率 / 到期日源模板列示为「--」 */
export function recomputeImportantRows(rows: readonly G6ImportantRow[]): G6ImportantRow[] {
  const detail = rows.filter((r) => r.kind === 'data')
  const face = detail.reduce((s, r) => s + num(r.faceValue), 0)
  const overdue = detail.reduce((s, r) => s + num(r.overduePrincipal), 0)
  return rows.map((r) =>
    r.kind === 'total' ? { ...r, faceValue: face, overduePrincipal: overdue } : r,
  )
}

/** （5）表：合计列 = 三阶段之和 */
export function stageMoveTotal(row: G6StageMoveRow): number {
  return num(row.stage1) + num(row.stage2) + num(row.stage3)
}

/**
 * 阶段间转移行的符号校验：同一行三阶段代数和应为 0（权威模板编制说明第 4 条）。
 * @returns 违规行的 rowKey 列表（容差 0.01 元）
 */
export function stageTransferImbalances(rows: readonly G6StageMoveRow[]): string[] {
  const transferKeys = new Set(['to_stage2', 'to_stage3', 'back_stage2', 'back_stage1'])
  return rows
    .filter((r) => transferKeys.has(r.rowKey) && Math.abs(stageMoveTotal(r)) > 0.01)
    .map((r) => r.rowKey)
}

/** 期末三阶段减值准备合计（与（2）表期末余额、（1）表 OCI 减值准备勾稽） */
export function endingStageImpairment(blocks: readonly G4StageBlock[]): number {
  return blocks
    .filter((b) => b.period === 'ending')
    .reduce((s, b) => s + stageTotals(b).impairment, 0)
}

export function writeoffDetailTotal(rows: readonly G6WriteoffRow[]): number {
  return rows.reduce((s, r) => s + num(r.amount), 0)
}

// ─────────────────────────── 持久化 ───────────────────────────

export function serializeG6ListedState(state: G6ListedDisclosureState): string {
  return JSON.stringify({ ...state, stageBlocks: undefined })
}

export function serializeG6ListedStages(state: G6ListedDisclosureState): string {
  return serializeStageBlocks(state.stageBlocks)
}

function mergeNamed<T extends G6NamedRow>(
  defaults: readonly T[],
  saved: unknown,
  empty: () => T,
  coerce: (raw: any, base: T) => T,
): T[] {
  if (!Array.isArray(saved)) return defaults.map((d) => ({ ...d }))
  const structural = defaults.filter((d) => d.fixed)
  const out: T[] = []
  for (const raw of saved) {
    if (!raw || typeof raw !== 'object') continue
    const base = structural.find((s) => s.label === txt(raw.label)) ?? empty()
    out.push(coerce(raw, { ...base, id: txt(raw.id) || base.id }))
  }
  // 结构行必须齐备且顺序在末尾（源模板固定行序）
  for (const s of structural) {
    if (!out.some((r) => r.label === s.label)) out.push({ ...s })
  }
  const structuralLabels = structural.map((s) => s.label)
  const detail = out.filter((r) => !structuralLabels.includes(r.label))
  const fixedOrdered = structuralLabels.map(
    (label) => out.find((r) => r.label === label) ?? ({ ...structural.find((s) => s.label === label)! }),
  )
  return [...detail, ...fixedOrdered]
}

export function parseG6ListedState(
  rowsRaw: string | null | undefined,
  stagesRaw: string | null | undefined,
): G6ListedDisclosureState {
  const def = buildDefaultG6ListedState()
  const stageBlocks = parseStageBlocks(stagesRaw, buildG6ListedStageBlocks()) ?? def.stageBlocks
  if (!rowsRaw?.trim()) return { ...def, stageBlocks }
  let parsed: any
  try {
    parsed = JSON.parse(rowsRaw)
  } catch {
    return { ...def, stageBlocks }
  }
  if (!parsed || typeof parsed !== 'object') return { ...def, stageBlocks }

  return {
    version: 1,
    balanceRows: recomputeBalanceRows(
      mergeNamed(def.balanceRows, parsed.balanceRows, () => emptyBalanceRow(), (raw, base) => ({
        ...base,
        label: base.fixed ? base.label : txt(raw.label),
        endBalance: num(raw.endBalance),
        priorBalance: num(raw.priorBalance),
      })),
    ),
    fairValueRows: recomputeFairValueRows(
      mergeNamed(def.fairValueRows, parsed.fairValueRows, () => emptyFairValueRow(), (raw, base) => ({
        ...base,
        label: base.fixed ? base.label : txt(raw.label),
        openingFv: num(raw.openingFv),
        accruedInterest: num(raw.accruedInterest),
        fvChangeCurrent: num(raw.fvChangeCurrent),
        closingFv: num(raw.closingFv),
        cost: num(raw.cost),
        fvChangeCumulative: num(raw.fvChangeCumulative),
        ociImpairment: num(raw.ociImpairment),
      })),
    ),
    provisionRows: recomputeProvisionRows(
      mergeNamed(def.provisionRows, parsed.provisionRows, () => emptyProvisionRow(), (raw, base) => ({
        ...base,
        label: base.fixed ? base.label : txt(raw.label),
        opening: num(raw.opening),
        increase: num(raw.increase),
        decrease: num(raw.decrease),
      })),
    ),
    importantEndRows: recomputeImportantRows(
      mergeNamed(def.importantEndRows, parsed.importantEndRows, () => emptyImportantRow(), importantCoerce),
    ),
    importantPriorRows: recomputeImportantRows(
      mergeNamed(def.importantPriorRows, parsed.importantPriorRows, () => emptyImportantRow(), importantCoerce),
    ),
    stageBlocks,
    stageMoveRows: G6_STAGE_MOVE_ROWS.map((d) => {
      const found = Array.isArray(parsed.stageMoveRows)
        ? parsed.stageMoveRows.find((r: any) => r?.rowKey === d.rowKey)
        : null
      return {
        ...d,
        stage1: num(found?.stage1),
        stage2: num(found?.stage2),
        stage3: num(found?.stage3),
      }
    }),
    writeoffTotal: num(parsed.writeoffTotal),
    writeoffRows: Array.isArray(parsed.writeoffRows)
      ? parsed.writeoffRows.filter((r: any) => r && typeof r === 'object').map((raw: any) => ({
          id: txt(raw.id) || uid('wo'),
          label: txt(raw.label),
          nature: txt(raw.nature),
          amount: num(raw.amount),
          reason: txt(raw.reason),
          procedure: txt(raw.procedure),
          relatedParty: !!raw.relatedParty,
        }))
      : def.writeoffRows,
    fvNote: txt(parsed.fvNote),
    significantChangeNote: txt(parsed.significantChangeNote),
    judgementBasisNote: txt(parsed.judgementBasisNote),
  }
}

function importantCoerce(raw: any, base: G6ImportantRow): G6ImportantRow {
  return {
    ...base,
    label: base.fixed ? base.label : txt(raw.label),
    faceValue: num(raw.faceValue),
    couponRate: txt(raw.couponRate),
    effectiveRate: txt(raw.effectiveRate),
    maturityDate: txt(raw.maturityDate),
    overduePrincipal: num(raw.overduePrincipal),
  }
}
