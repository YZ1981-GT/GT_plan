/**
 * k0SummaryMatrix.ts — K0-1 下区「一、函证情况」品种矩阵纯函数（2 品种 × 8 指标）
 *
 * spec: k0-confirmation-source-alignment · Task 8（Requirements 3.2 / 3.3 / 3.4 / 11.2 / 11.3）
 *
 * ─── 源模板事实（`k0MatrixSpec.ts` 已固化文字真源，后端
 *     `test_k0_source_template_facts.py` 以 openpyxl 直读裁决）────────────────
 * `函证结果汇总表K0-1` 下区 `C27 一、函证情况`：
 *   品种列头 `E28 其他应收款` / `F28 其他应付款` —— **固定 2 个，无 `……` 可扩位**
 *   指标行 `C29:C36` 与公式：
 *     R29 本期（期末）账面金额         —— **无公式 = 手填 / 从相邻循环带入**
 *     R30 抽取样本的发函金额           = SUMIF(E7:E26, 品种, F7:F26)
 *     R31 发函金额占账面金额的比例(%)   = IF(ISERROR(R30/R29), 0, R30/R29)
 *     R32 回函确认金额                 = SUMIF(E7:E26, 品种, U7:U26)
 *     R33 回函可确认金额占发函金额比例  = IF(ISERROR(R32/R30), 0, R32/R30)
 *     R34 回函可确认金额占账面金额比例  = IF(ISERROR(R32/R29), 0, R32/R29)
 *     R35 替代测试确认金额             = SUMIF(E7:E26, 品种, Y7:Y26)
 *     R36 回函和替代确认金额占账面比例  = (R35+R32)/R29   ← **无 ISERROR 兜底**
 *   上区列语义：E=账户/交易（品种维度）· F=金额 · U=可确认金额 · Y=替代后可确认金额
 *
 * 🔴 **三条 SUMIF 一律不叠「相符」过滤** —— 源模板 R32 直取 `U` 列（可确认金额），
 * 业务规则已在 `useConfirmationData.computeConfirmedAmount` 的派生里
 * （相符→amount / 不符→reply_amount / 消极式未回函→视同相符）。
 * 再叠一层 `match_status === '相符'` 是**双重口径**（F0 那轮已定论）。
 *
 * ─── 🔴 与 L0 的**有意差异**：分母缺失/为 0 返 `null` 不返 `0` ────────────────
 * 源模板中间三个比例是 `IF(ISERROR(...),0,...)`，`l0SummaryMatrix` 选择忠实返 `0`；
 * 而 K0 的 Requirement 3.4 / Property 6 明确要求「渲染「-」（null）… SHALL NOT 用 0
 * 冒充」——理由是 `0` 会把「账面金额未取到」伪装成「比例算出来是 0」，让
 * 「本项目无此科目」与「覆盖率为 0」不可区分（审计场景里后者是重大结论）。
 * 故 K0 沿用 **F0/G0/H0 的 `null` 口径**并直接复用 `f0SummaryAggregation.safeRatio`
 * ⇒ 同源守卫（Property 7）也因此能逐字节比对 F0 与 K0 的同名指标。
 * 末行本就无 ISERROR 兜底，`null` 更是唯一正确解。
 *
 * ─── 与 E0/F0/G0/H0/L0 五份既有矩阵的关系（裁决门 D = D-2）────────────────────
 * 用户裁决「各自实现后收敛」→ 本模块是**独立副本**，
 * `f0SummaryAggregation.ts` / `e0SummaryMatrix.ts` / `g0SummaryMatrix.ts` /
 * `h0SummaryMatrix.ts` / `l0SummaryMatrix.ts` **一行不改**（Property 7 用内容哈希钉死）。
 * 只**引用** `safeRatio` / `sumByCategory` 两个纯函数（Requirement 11.2 的既定范式）。
 *
 * | 维度        | F0                     | L0            | K0（本模块）                |
 * |-------------|------------------------|---------------|-----------------------------|
 * | 指标        | 8（label-as-key）      | 8（key+label）| 8（key+label，同 L0/G0 命名）|
 * | 品种        | 4（固定）              | 2（固定）     | **2（固定，源无可扩位）**    |
 * | 分母 0/缺失 | `null`                 | `0`           | **`null`**（同 F0）          |
 * | 账面取数    | F1/F3/F4 前端拉        | 后端注入      | **K1/K3 前端拉**（见 `k0MatrixDataSources`）|
 *
 * 🔴 收敛锚点：收敛 spec 靠 grep `CONVERGENCE_TARGET` 定位全部副本，勿删勿改名。
 */

import { safeRatio, sumByCategory } from '../composables/f0SummaryAggregation'
import type { ConfirmationRow } from '../confirmationTypes'
import {
  K0_CATEGORY_NAMES,
  K0_MATRIX_CATEGORIES,
  K0_MATRIX_EDITABLE_METRIC_INDEX,
  K0_MATRIX_METRIC_ANCHORS,
  K0_MATRIX_METRIC_LABELS,
  k0MatrixOverrideItemId,
} from './k0MatrixSpec'

/** 收敛锚点（裁决门 D = D-2）—— 矩阵类副本的统一标识 */
export const CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'

// ─── 指标 ────────────────────────────────────────────────────────────────────

/**
 * 指标稳定 key。
 *
 * 🔴 逐字沿用 `g0SummaryMatrix` / `l0SummaryMatrix` 的命名 —— 收敛时无需再改名，
 * 同源守卫也能直接按 key 对齐比对；**手工覆盖键的指标段用它而不是中文 label**
 * （改文案不会让既有录入值失联，F0 的 label-as-key 正是收敛时要改掉的那一侧）。
 */
export type K0MetricKey =
  | 'book_amount'
  | 'send_amount'
  | 'send_ratio'
  | 'reply_confirmed'
  | 'reply_over_send'
  | 'reply_over_book'
  | 'alt_confirmed'
  | 'reply_alt_over_book'

export interface K0MetricDef {
  key: K0MetricKey
  /** 源模板逐字标签 —— **取自 `k0MatrixSpec.K0_MATRIX_METRIC_LABELS`，此处不抄第二份** */
  label: string
  kind: 'amount' | 'ratio'
  /** true = 可手填（仅账面金额行；源 R29 无公式） */
  editable: boolean
  /** 金额类：聚合的 grid 字段（对应源模板 SUMIF 的 sum_range 列） */
  sum?: 'amount' | 'confirmed_amount' | 'alt_confirmed'
  /** 比例类：分子（可多项相加）/ 分母 */
  ratio?: { num: K0MetricKey[]; den: K0MetricKey }
  /** 源锚点（`C29`..`C36`，取自 `K0_MATRIX_METRIC_ANCHORS`） */
  anchor: string
  /** 完整源出处（`K0-1!C29` 形态） */
  sourceRef: string
}

/** 指标顺序（与源 `C29:C36` 逐行对应），只声明「除 label/anchor 外」的形态。 */
const METRIC_SHAPES: readonly Omit<K0MetricDef, 'label' | 'anchor' | 'sourceRef'>[] = [
  { key: 'book_amount', kind: 'amount', editable: true },
  { key: 'send_amount', kind: 'amount', editable: false, sum: 'amount' },
  { key: 'send_ratio', kind: 'ratio', editable: false, ratio: { num: ['send_amount'], den: 'book_amount' } },
  { key: 'reply_confirmed', kind: 'amount', editable: false, sum: 'confirmed_amount' },
  { key: 'reply_over_send', kind: 'ratio', editable: false, ratio: { num: ['reply_confirmed'], den: 'send_amount' } },
  { key: 'reply_over_book', kind: 'ratio', editable: false, ratio: { num: ['reply_confirmed'], den: 'book_amount' } },
  { key: 'alt_confirmed', kind: 'amount', editable: false, sum: 'alt_confirmed' },
  {
    key: 'reply_alt_over_book',
    kind: 'ratio',
    editable: false,
    // 源 R36 = (R35 + R32) / R29 —— 替代在前、回函在后（与源模板加数顺序一致）
    ratio: { num: ['alt_confirmed', 'reply_confirmed'], den: 'book_amount' },
  },
]

/**
 * 8 个指标定义。
 *
 * 🔴 `label` 与 `anchor` **从 `k0MatrixSpec` 取**（该模块是文字真源，已由后端源模板
 * 守卫逐格锁死）—— 本文件不抄第二份中文，否则两处漂移时无法裁决谁对。
 * 数量一致性由下方 import 期断言保证。
 */
export const K0_MATRIX_METRICS: readonly K0MetricDef[] = Object.freeze(
  METRIC_SHAPES.map((shape, i) =>
    Object.freeze({
      ...shape,
      label: K0_MATRIX_METRIC_LABELS[i] as string,
      anchor: K0_MATRIX_METRIC_ANCHORS[i] as string,
      sourceRef: `K0-1!${K0_MATRIX_METRIC_ANCHORS[i]}`,
    }),
  ),
) as readonly K0MetricDef[]

// import 期交叉锁死：形态表与文字真源的长度必须一致，否则上面的 `[i]` 会静默产出 undefined
if (
  METRIC_SHAPES.length !== K0_MATRIX_METRIC_LABELS.length ||
  METRIC_SHAPES.length !== K0_MATRIX_METRIC_ANCHORS.length
) {
  throw new Error(
    '[k0SummaryMatrix] 指标形态表与 k0MatrixSpec 的 label/anchor 长度不一致：' +
      `${METRIC_SHAPES.length} / ${K0_MATRIX_METRIC_LABELS.length} / ${K0_MATRIX_METRIC_ANCHORS.length}`,
  )
}
if (!K0_MATRIX_METRICS[K0_MATRIX_EDITABLE_METRIC_INDEX]?.editable) {
  throw new Error('[k0SummaryMatrix] K0_MATRIX_EDITABLE_METRIC_INDEX 指向的指标不可编辑')
}

/** 指标 label 序列（供同源守卫与渲染表头） */
export const K0_MATRIX_LABELS: readonly string[] = Object.freeze(
  K0_MATRIX_METRICS.map((m) => m.label),
)

/** 标签列表头 —— 源模板 `C28` 为空（品种列头在 E28/F28），故自拟中文表头 */
export const K0_MATRIX_LABEL_HEADER = '项目'

/** 品种名（渲染顺序 = 源 E28 → F28），转发 `k0MatrixSpec` 的真源 */
export const K0_MATRIX_CATEGORY_NAMES: readonly string[] = K0_CATEGORY_NAMES

// ─── 矩阵单元格 ─────────────────────────────────────────────────────────────

export interface K0MatrixCell {
  category: string
  /** 稳定 key（**非**中文 label；手工覆盖键的指标段用它） */
  metric: K0MetricKey
  /** 源模板逐字标签 */
  label: string
  kind: 'amount' | 'ratio'
  editable: boolean
  /**
   * `null` = 不可得：
   * - 账面金额行 = 未取数 / 本项目无此科目（两态由 `k0MatrixDataSources` 的三态视图区分）
   * - 比例行     = 分母缺失或为 0（**绝不用 0 冒充**，Requirement 3.4）
   */
  value: number | null
  /** 溯源提示（仅账面金额行；取自 `k0MatrixSpec.amountHint`） */
  sourceHint?: string
}

export interface BuildK0MatrixInput {
  /** 上区 grid 行 */
  rows: readonly ConfirmationRow[]
  /**
   * 账面金额（来自 `k0MatrixDataSources.buildK0BookAmountMap`）。
   *
   * 🔴 三态语义**必须原样传入，不得 `?? {}` 兜底**：
   * - 整个参数 `undefined` = 取数链路未跑 → 「未取数（可手填）」
   * - 键存在值为 `null`    = 本项目科目表无该科目 → 「本项目无此科目」
   * - 键存在值为 `0`       = 科目存在且余额为 0
   */
  bookAmounts?: Record<string, number | null> | undefined
  /** 审计师手工覆盖（键 = `k0MatrixOverrideItemId(品种, 指标key)`） */
  manualOverrides?: Record<string, number | string> | undefined
}

/** 数值归一：`null`/`undefined`/空串/非有限值 → `null`（不塌陷成 0）。 */
function toFiniteOrNull(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * 解析某品种的账面金额（手工覆盖 > 取数结果 > `null`）。
 *
 * 手工优先是 Requirement 3.5 的明文要求（源 R29 本就是手填行）。
 */
export function resolveK0BookAmount(
  category: string,
  input: Pick<BuildK0MatrixInput, 'bookAmounts' | 'manualOverrides'>,
): number | null {
  const manual = input.manualOverrides?.[k0MatrixOverrideItemId(category, 'book_amount')]
  const manualNum = toFiniteOrNull(manual)
  if (manualNum !== null) return manualNum

  if (!input.bookAmounts || !(category in input.bookAmounts)) return null
  return toFiniteOrNull(input.bookAmounts[category])
}

/**
 * 构建 2 品种 × 8 指标矩阵。
 *
 * 外层按**品种**（`K0_MATRIX_CATEGORY_NAMES` 顺序）、内层按**指标**
 * （`K0_MATRIX_METRICS` 顺序）。
 */
export function buildK0SummaryMatrix(input: BuildK0MatrixInput): K0MatrixCell[][] {
  const rows = input.rows ?? []

  return K0_MATRIX_CATEGORIES.map((cat) => {
    const values = new Map<K0MetricKey, number | null>()

    // ① 账面金额（手填/带入，可为 null）
    values.set('book_amount', resolveK0BookAmount(cat.category, input))

    // ② 金额类三项 —— 源模板 SUMIF(E列=品种, F/U/Y 列)，不叠相符过滤
    for (const m of K0_MATRIX_METRICS) {
      if (m.kind === 'amount' && m.sum) {
        values.set(m.key, sumByCategory(rows, cat.category, m.sum as keyof ConfirmationRow))
      }
    }

    // ③ 比例类四项 —— 分母缺失/为 0 → null（safeRatio 的既有语义）
    for (const m of K0_MATRIX_METRICS) {
      if (m.kind !== 'ratio' || !m.ratio) continue
      const den = values.get(m.ratio.den) ?? null
      // 分子任一项不可得视为不可得（不用 0 冒充）
      let numerator: number | null = 0
      for (const k of m.ratio.num) {
        const v = values.get(k) ?? null
        if (v === null) {
          numerator = null
          break
        }
        numerator += v
      }
      values.set(m.key, safeRatio(numerator, den))
    }

    return K0_MATRIX_METRICS.map<K0MatrixCell>((m) => ({
      category: cat.category,
      metric: m.key,
      label: m.label,
      kind: m.kind,
      editable: m.editable,
      value: values.has(m.key) ? (values.get(m.key) as number | null) : null,
      ...(m.key === 'book_amount' ? { sourceHint: cat.amountHint } : {}),
    }))
  })
}

/** 便捷取值：按品种 + 指标 key 取单格。 */
export function pickK0MatrixCell(
  matrix: readonly K0MatrixCell[][],
  category: string,
  metric: K0MetricKey,
): K0MatrixCell | undefined {
  const idx = K0_MATRIX_CATEGORY_NAMES.indexOf(category)
  if (idx < 0) return undefined
  return matrix[idx]?.find((c) => c.metric === metric)
}

/**
 * 「账户/交易」不在两品种内的行数（源模板矩阵只按 E28/F28 两个 criteria 聚合）。
 *
 * 🔴 与 F0 的「待归类」提示同款：**不猜归属**，只如实告知有多少行不计入函证情况
 * （空值行不计入 —— 那是尚未填写而不是归类错误）。
 */
export function countK0UnclassifiedRows(rows: readonly ConfirmationRow[]): number {
  const known = new Set<string>(K0_MATRIX_CATEGORY_NAMES)
  let n = 0
  for (const r of rows ?? []) {
    const t = String((r as Record<string, unknown>).account_type ?? '').trim()
    if (!t) continue
    if (!known.has(t)) n += 1
  }
  return n
}
