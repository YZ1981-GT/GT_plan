/**
 * G13-2 分类骨架**落库** —— 受管表的真身（spec `g-cycle-single-region-detail-lanes` Task 12）
 *
 * ═══ 为什么要多一个 store item ═══
 *
 * 致同模板 `明细表G13-2` 的 R11-R20 是**固定 10 个损益表项目**（交易性金融资产 / 其中：指定… /
 * 衍生金融资产 / … / 以公允价值计量的投资性房地产 / 其他），带三层父子结构（`B11=B12+B13`）。
 * 而 `G13-detail-rows` 存的是平台增强出来的**金融工具级明细**（`instrumentName` 用户自填、
 * 动态增删）—— 两侧行模型**不同构**：前端第 N 行明细根本不对应模板第 N 个项目行。
 *
 * 原先 `buildG13CategorySkeleton()` 已经按 10 个固定项目汇总出骨架，但它是 `computed`、
 * **不落库** ⇒ 双向回写没有载体（出方向能算，回方向无处可落）。
 *
 * ⇒ 本模块把骨架**持久化**成独立 store item `G13-detail-skeleton`（10 行固定行集，
 * `rowKey` 为行身份），受管它；工具明细 `G13-detail-rows` 保持 HTML-only 平台增强。
 *
 * ═══ 🔴 手工覆盖优先（用户拍板）═══
 *
 * 骨架值默认来自工具明细汇总。OO 侧改动回流后若被汇总无条件重算，等于回流无效 ⇒
 * 落库行带 `manualOverride` 标记：**有标记的行用存库值，无标记的行用汇总值**。
 * `clearOverride()` 把某行退回汇总口径。
 *
 * ═══ 受管字段 ═══
 *
 * 模板 12 列里只有 6 个可填列进落库形态（其余是公式列或固定文本）：
 * `B 未审数` · `C 调整数` · `F 成本` · `G 本期公允价值变动` · `H 累计公允价值变动` · `L 索引号`。
 * `E 对应科目` 是模板预填的科目名（`TEMPLATE_BELONG_LABELS_G13`）⇒ 也落库，允许现场改写。
 * `A 项目` 由 `TEMPLATE_ROW_LABELS_G13` 三方锁死（模板 A 列 ↔ 本常量 ↔ provider），不可改。
 * `D 审定数`(=B+C) · `I 公允价值`(=F+H) · `J 计入损益`(=G) · `K 核对`(=J=D) 是模板公式列。
 */
import { G13_ADJUDICATION_ITEMS } from './g13Constants'
import type { G13CategorySkeletonRow } from './g13CategorySkeleton'

/** 落库行：只存可填列 + 覆盖标记。缺字段读作「未覆盖」。 */
export interface G13SkeletonStoredRow {
  rowKey: string
  /** B 未审数 */
  currentUnadjusted?: number
  /** C 调整数 */
  adjustment?: number
  /** E 对应科目（模板预填科目名，允许现场改写） */
  belongLabel?: string
  /** F 成本 */
  cost?: number
  /** G 本期公允价值变动 */
  periodFvChange?: number
  /** H 累计公允价值变动 */
  cumulativeFvChange?: number
  /** L 索引号 */
  sourceIndex?: string
  /** 🔴 手工覆盖：为真时本行用存库值，不被工具明细汇总重算冲掉 */
  manualOverride?: boolean
}

/** 可被手工覆盖的字段（= 模板可填列）。顺序即模板列序 B/C/E/F/G/H/L。 */
export const G13_SKELETON_OVERRIDABLE_FIELDS = [
  'currentUnadjusted',
  'adjustment',
  'belongLabel',
  'cost',
  'periodFvChange',
  'cumulativeFvChange',
  'sourceIndex',
] as const

export type G13SkeletonOverridableField = (typeof G13_SKELETON_OVERRIDABLE_FIELDS)[number]

/**
 * 🔴 模板 `明细表G13-2` A11-A20 **逐字**行名（含缩进空格）。
 *
 * 与 `G13_ADJUDICATION_ITEMS[i].label` 的差别只在缩进：模板用 5 个前导空格表达子行层级
 * （`     衍生金融资产`），前端用 `indent` 字段渲染 ⇒ 两者**不是**逐字相等。
 * provider 侧 `TEMPLATE_ROW_LABELS_G1302` 与本常量双向锁，判据再与模板 A 列比第三方。
 */
export const TEMPLATE_ROW_LABELS_G13 = [
  '交易性金融资产',
  '其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
  '     衍生金融资产',
  '交易性金融负债',
  '其中：指定为以公允价值计量且其变动计入当期损益的金融负债',
  '     衍生金融负债',
  '其他非流动金融资产',
  '其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
  '以公允价值计量的投资性房地产',
  '其他',
] as const

/** 🔴 模板 E11-E20 逐字预填的「对应科目」（E20 模板为空 ⇒ 空串）。 */
export const TEMPLATE_BELONG_LABELS_G13 = [
  '交易性金融资产',
  '交易性金融资产',
  // 🔴 两个衍生子行的分隔符是 `/` 不是 `-`（与 provider 的 TEMPLATE_BELONG_LABELS_G1302 双向锁）
  '交易性金融资产/衍生金融资产',
  '交易性金融负债',
  '交易性金融负债',
  '交易性金融负债/衍生金融负债',
  '其他非流动金融资产',
  '其他非流动金融资产',
  '投资性房地产',
  '',
] as const

/** 骨架行序（= 模板 R11-R20 行序），单一真源取自 `G13_ADJUDICATION_ITEMS`。 */
export const G13_SKELETON_ROW_KEYS: readonly string[] = G13_ADJUDICATION_ITEMS.map(
  (d) => d.rowKey,
)

/** rowKey → 模板 E 列预填科目名 */
export function templateBelongLabelOf(rowKey: string): string {
  const i = G13_SKELETON_ROW_KEYS.indexOf(rowKey)
  return i >= 0 ? TEMPLATE_BELONG_LABELS_G13[i] : ''
}

function num(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

/** store JSON → `rowKey → 落库行`（非数组 / 坏 JSON 一律读作空，不抛） */
export function parseStoredSkeleton(
  json: string | null | undefined,
): Map<string, G13SkeletonStoredRow> {
  const out = new Map<string, G13SkeletonStoredRow>()
  if (!json) return out
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return out
    for (const raw of parsed) {
      const rowKey = String(raw?.rowKey ?? '')
      if (!rowKey || !G13_SKELETON_ROW_KEYS.includes(rowKey)) continue
      out.set(rowKey, {
        rowKey,
        currentUnadjusted: raw?.currentUnadjusted,
        adjustment: raw?.adjustment,
        belongLabel: raw?.belongLabel,
        cost: raw?.cost,
        periodFvChange: raw?.periodFvChange,
        cumulativeFvChange: raw?.cumulativeFvChange,
        sourceIndex: raw?.sourceIndex,
        manualOverride: !!raw?.manualOverride,
      })
    }
  } catch {
    return new Map()
  }
  return out
}

/** 骨架展示行 = 汇总行 + 落库覆盖（多两个字段：E 列科目名 + 覆盖标记） */
export interface G13SkeletonDisplayRow extends G13CategorySkeletonRow {
  /** E 对应科目 */
  belongLabel: string
  /** 🔴 本行是否走手工覆盖（UI 打标 + 判据取证） */
  manualOverride: boolean
}

/**
 * 🔴 手工覆盖优先：有 `manualOverride` 的行用**存库值**，无标记的行用**汇总值**。
 *
 * `currentAudited`/`fairValue`/`amountInPl` 三列是模板公式列（`=B+C` / `=F+H` / `=G`），
 * 覆盖后必须按同口径**重算**，否则 UI 会显示「未审+调整 ≠ 审定」这种自相矛盾的数。
 */
export function mergeSkeletonOverrides(
  aggregated: readonly G13CategorySkeletonRow[],
  stored: Map<string, G13SkeletonStoredRow>,
): G13SkeletonDisplayRow[] {
  return aggregated.map((agg) => {
    const hit = stored.get(agg.rowKey)
    const fallbackBelong = templateBelongLabelOf(agg.rowKey)
    if (!hit?.manualOverride) {
      return {
        ...agg,
        belongLabel: hit?.belongLabel ?? fallbackBelong,
        manualOverride: false,
      }
    }
    const currentUnadjusted = hit.currentUnadjusted === undefined
      ? agg.currentUnadjusted
      : num(hit.currentUnadjusted)
    const adjustment = hit.adjustment === undefined ? agg.adjustment : num(hit.adjustment)
    const cost = hit.cost === undefined ? agg.cost : num(hit.cost)
    const periodFvChange = hit.periodFvChange === undefined
      ? agg.periodFvChange
      : num(hit.periodFvChange)
    const cumulativeFvChange = hit.cumulativeFvChange === undefined
      ? agg.cumulativeFvChange
      : num(hit.cumulativeFvChange)
    // 模板公式列按模板口径重算（D=B+C · I=F+H · J=G）
    const currentAudited = currentUnadjusted + adjustment
    const fairValue = cost + cumulativeFvChange
    const amountInPl = periodFvChange
    return {
      ...agg,
      currentUnadjusted,
      adjustment,
      currentAudited,
      cost,
      periodFvChange,
      cumulativeFvChange,
      fairValue,
      amountInPl,
      // K 核对 = J=D；BS 侧 I=F+H 在覆盖后恒成立
      bsReconciled: true,
      plReconciled: Math.abs(amountInPl - currentAudited) <= 0.01,
      belongLabel: hit.belongLabel ?? fallbackBelong,
      sourceIndex: hit.sourceIndex ?? agg.sourceIndex,
      manualOverride: true,
    }
  })
}

/**
 * 落库 payload：**恒 10 行**（受管区 R11-R20 逐行对应，缺行会让行表引擎错位）。
 *
 * 未覆盖的行也写汇总值 —— 受管区必须有数据，否则 materialize 出来是空表。
 */
export function buildSkeletonPersistPayload(
  display: readonly G13SkeletonDisplayRow[],
): G13SkeletonStoredRow[] {
  const byKey = new Map(display.map((r) => [r.rowKey, r]))
  return G13_SKELETON_ROW_KEYS.map((rowKey) => {
    const r = byKey.get(rowKey)
    return {
      rowKey,
      currentUnadjusted: r?.currentUnadjusted ?? 0,
      adjustment: r?.adjustment ?? 0,
      belongLabel: r?.belongLabel ?? templateBelongLabelOf(rowKey),
      cost: r?.cost ?? 0,
      periodFvChange: r?.periodFvChange ?? 0,
      cumulativeFvChange: r?.cumulativeFvChange ?? 0,
      sourceIndex: r?.sourceIndex ?? '',
      manualOverride: !!r?.manualOverride,
    }
  })
}

/** 设一格手工覆盖（自动置 `manualOverride`）。返回新 Map，不改入参。 */
export function setSkeletonOverride(
  stored: Map<string, G13SkeletonStoredRow>,
  rowKey: string,
  field: G13SkeletonOverridableField,
  value: unknown,
  seed?: Partial<G13SkeletonStoredRow>,
): Map<string, G13SkeletonStoredRow> {
  if (!G13_SKELETON_ROW_KEYS.includes(rowKey)) return stored
  const next = new Map(stored)
  const base = next.get(rowKey) ?? { rowKey, ...seed }
  const parsed = field === 'belongLabel' || field === 'sourceIndex'
    ? String(value ?? '')
    : num(value)
  next.set(rowKey, { ...base, rowKey, [field]: parsed, manualOverride: true })
  return next
}

/** 清掉某行的手工覆盖 ⇒ 该行退回工具明细汇总口径。 */
export function clearSkeletonOverride(
  stored: Map<string, G13SkeletonStoredRow>,
  rowKey: string,
): Map<string, G13SkeletonStoredRow> {
  const next = new Map(stored)
  const hit = next.get(rowKey)
  if (!hit) return next
  next.set(rowKey, { rowKey, belongLabel: hit.belongLabel, manualOverride: false })
  return next
}

/** 当前有几行走手工覆盖（UI 提示 + 判据取证） */
export function countSkeletonOverrides(
  stored: Map<string, G13SkeletonStoredRow>,
): number {
  let n = 0
  for (const r of stored.values()) if (r.manualOverride) n += 1
  return n
}
