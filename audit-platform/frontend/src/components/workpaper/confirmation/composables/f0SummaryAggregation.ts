/**
 * f0SummaryAggregation.ts — F0-1 品种矩阵纯函数（4 品种 × 7 指标）
 *
 * 源模板：`函证结果汇总表F0-1` R28:H37（下区「一、函证情况」）
 *
 * 🔴 公式逐格实证（2026-08-03 openpyxl `data_only=False` 直读，Task 28 返工依据）。
 * 上区列语义（R6 表头）：E=账户/交易 · F=金额（发函）· U=可确认金额 · Y=替代后可确认金额。
 *
 * | 行  | 源模板公式                          | 本模块实现                                    |
 * |-----|-------------------------------------|-----------------------------------------------|
 * | R30 | 手填（示例值 100）                  | F1/F3/F4 render-config tb_amount + 手工覆盖   |
 * | R31 | `SUMIF(E8:E27,E29,F8:F27)`          | `sumByCategory(rows, cat, 'amount')`          |
 * | R32 | `IF(ISERROR(E31/E30),0,E31/E30)`    | `safeRatio(R31, R30)`（缺失返 null 不返 0）   |
 * | R33 | `SUMIF(E8:E27,E29,U8:U27)`          | `sumByCategory(rows, cat, 'confirmed_amount')`|
 * | R34 | `IF(ISERROR(E33/E31),0,E33/E31)`    | `safeRatio(R33, R31)`                         |
 * | R35 | `IF(ISERROR(E33/E30),0,E33/E30)`    | `safeRatio(R33, R30)`                         |
 * | R36 | `SUMIF(E8:E27,E29,Y8:Y27)`          | `sumByCategory(rows, cat, 'alt_confirmed')`   |
 * | R37 | `(E36+E33)/E30`                     | `safeRatio(R33 + R36, R30)`                   |
 *
 * 该实证推翻 requirements.md 原 R1.2/R1.3 两处描述（已同步更正）：
 * - R1.2 原写「S 列中 N 列=『相符』的行求和」→ **源模板是 SUMIF(U) 无相符过滤**。
 *   平台 `useConfirmationData.computeConfirmedAmount` 已按相符/不符/未回函派生
 *   `confirmed_amount`，业务规则本就内含在 U 列里，再叠一层过滤是双重口径。
 *   （E0 的 `e0SummaryMatrix.ts` 同样直接 `sumByCategory(..., 'confirmed_amount')`。）
 * - R1.3 原写「F0-5 合计 + F0-6 合计按品种归属」→ **源模板是 SUMIF(Y)**，即替代确认
 *   金额本就逐行记在上区 Y 列「替代后可确认金额」。原 `distributeAltAmounts`
 *   （F0-5 全归预付 / F0-6 平分应付票据+应付账款）是无源模板依据的编造，已删。
 *   F0-5/F0-6 的四区块合计改作**勾稽信号**（见 `checkAltConsistency`），不参与矩阵取值。
 *
 * 设计约束（f0-confirmation-linkage-and-structural-enhancement, Property 1/6）：
 * - 分母 0 → 显示「-」（null），绝不产出 NaN/Infinity
 * - bookAmounts 缺该品种 → 比例返回 null 渲染「-」
 * - 手工覆盖（isManual=true）不被自动值覆盖
 * - 与 E0 `e0SummaryMatrix.ts` 同族设计，品种和指标数不同
 */

import type { ConfirmationRow } from '../confirmationTypes'

// ─── 品种常量 ─────────────────────────────────────────────────────────────────

export const F0_MATRIX_CATEGORIES = [
  '预付账款',
  '应付票据',
  '应付账款',
  '本期采购',
] as const

export type F0Category = typeof F0_MATRIX_CATEGORIES[number]

// ─── 指标常量（源模板 R30~R37 逐行对应） ──────────────────────────────────────

export const F0_MATRIX_LABELS = [
  '本期（期末）账面金额',
  '抽取样本的发函金额',
  '发函金额占账面金额的比例(%)',
  '回函确认金额',
  '回函可确认金额占发函金额的比例(%)',
  '回函可确认金额占账面金额的比例(%)',
  '替代测试确认金额',
  '回函和替代确认金额占账面金额的比例(%)',
] as const

export type F0Metric = typeof F0_MATRIX_LABELS[number]

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface F0MatrixCell {
  category: F0Category
  metric: F0Metric
  /** null = 无法计算（分母缺失）→ 渲染「-」 */
  value: number | null
  /** 'ratio' 时渲染百分比，'amount' 时渲染金额 */
  kind: 'amount' | 'ratio'
  /** true = 可手填（仅「本期（期末）账面金额」行） */
  editable: boolean
  /** 溯源 tooltip */
  sourceHint?: string
}

export interface F0MatrixInput {
  /** F0-1 上区 grid 明细行 */
  rows: readonly ConfirmationRow[]
  /** 四品种账面金额（从 F1/F3/F4 的 tb_amount 取，缺省 undefined ≠ 0） */
  bookAmounts?: Partial<Record<F0Category, number>>
  /** 手工覆盖值（key = `${category}::${metric}`） */
  manualOverrides?: Record<string, number>
}
/**
 * 🔴 `altF05Totals`/`altF06Totals` **不在** `F0MatrixInput` 里 ——
 * 源模板 R36 取的是上区 Y 列（`SUMIF(E,品种,Y)`），替代程序底稿合计只作勾稽用，
 * 见 `checkAltConsistency`。放进矩阵入参就会重新滑向「按底稿合计反推品种归属」的编造。
 */

export interface F0AltTotals {
  /** 四区块的合计金额总和 */
  total: number
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

/** 安全除法：分母 0 或缺失 → null；结果非有限 → null */
export function safeRatio(numerator: number | undefined | null, denominator: number | undefined | null): number | null {
  if (numerator == null || denominator == null) return null
  if (denominator === 0) return null
  const r = numerator / denominator
  if (!Number.isFinite(r)) return null
  return r
}

/**
 * 按品种列（account_type / E 列）求和指定金额字段。
 *
 * F0-1 源模板品种对应 grid E 列「账户/交易」，可能的值：
 * - 预付账款 / 应付票据 / 应付账款 / 本期采购
 */
export function sumByCategory(
  rows: readonly ConfirmationRow[],
  category: string,
  field: keyof ConfirmationRow,
): number {
  let total = 0
  for (const row of rows) {
    if (row.account_type === category) {
      const v = (row as Record<string, unknown>)[field]
      if (typeof v === 'number' && Number.isFinite(v)) {
        total += v
      }
    }
  }
  return total
}

/**
 * 替代确认金额与替代程序底稿的勾稽结果。
 *
 * 源模板把「替代测试确认金额」（R36）落在上区 Y 列逐行手填，而 F0-5/F0-6 才是
 * 替代程序的实际证据（四区块凭证金额）。两者应当相符 —— 不相符即说明
 * 「上区 Y 列漏填 / 替代程序底稿漏编 / 口径不一致」，是真实的审计线索。
 *
 * 🔴 只报差异不改数字：矩阵取值一律按源模板 SUMIF(Y)，不用 F0-5/F0-6 反推。
 */
export interface F0AltConsistency {
  /** 上区 Y 列合计（矩阵 R36 四品种之和） */
  gridAltTotal: number
  /** F0-5 + F0-6 四区块凭证金额合计 */
  procedureTotal: number
  /** gridAltTotal − procedureTotal */
  diff: number
  /** 'ok' = 相符（容差 0.01）；'mismatch' = 不符；'no-data' = 两侧都无数据 */
  level: 'ok' | 'mismatch' | 'no-data'
  /** 面板文案 */
  message: string
}

/**
 * 勾稽：上区「替代后可确认金额」合计 ?= F0-5 + F0-6 凭证金额合计。
 */
export function checkAltConsistency(input: {
  rows: readonly ConfirmationRow[]
  altF05Totals?: F0AltTotals
  altF06Totals?: F0AltTotals
}): F0AltConsistency {
  const gridAltTotal = round2(
    F0_MATRIX_CATEGORIES.reduce(
      (sum, cat) => sum + sumByCategory(input.rows, cat, 'alt_confirmed'),
      0,
    ),
  )
  const procedureTotal = round2((input.altF05Totals?.total ?? 0) + (input.altF06Totals?.total ?? 0))
  const diff = round2(gridAltTotal - procedureTotal)

  if (gridAltTotal === 0 && procedureTotal === 0) {
    return {
      gridAltTotal,
      procedureTotal,
      diff,
      level: 'no-data',
      message: '尚无替代程序数据（上区「替代后可确认金额」与 F0-5/F0-6 均为空）',
    }
  }
  if (Math.abs(diff) <= 0.01) {
    return {
      gridAltTotal,
      procedureTotal,
      diff: 0,
      level: 'ok',
      message: '上区「替代后可确认金额」合计与 F0-5/F0-6 凭证金额合计相符',
    }
  }
  return {
    gridAltTotal,
    procedureTotal,
    diff,
    level: 'mismatch',
    message:
      `上区「替代后可确认金额」合计 ${gridAltTotal} 与 F0-5/F0-6 凭证金额合计 ${procedureTotal} ` +
      `不符（差异 ${diff}）：请核对上区 Y 列是否漏填、替代程序底稿是否漏编`,
  }
}

/**
 * 上区 U 列与 Y 列重复计入的行（R37 双算风险提示）。
 *
 * 源模板 R37 = (R36+R33)/R30 —— 人工编表时未回函行的 U 列通常留空，故不双算。
 * 但平台 `computeConfirmedAmount` 对「积极式 + 未回函」返回的正是 `alt_confirmed`
 * → 这类行的 U 与 Y 相等，R37 会把同一笔钱算两次。
 *
 * 🔴 不擅自改公式（改了就不是源模板口径），只把风险行如实暴露给审计师。
 */
export function detectAltOverlapRows(
  rows: readonly ConfirmationRow[],
): ConfirmationRow[] {
  return rows.filter((row) => {
    const confirmed = Number(row.confirmed_amount)
    const alt = Number(row.alt_confirmed)
    if (!Number.isFinite(confirmed) || !Number.isFinite(alt)) return false
    if (confirmed === 0 || alt === 0) return false
    return Math.abs(confirmed - alt) <= 0.01
  })
}

/** 两位小数归一（避免浮点漂移进矩阵与勾稽） */
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── 主函数 ───────────────────────────────────────────────────────────────────

/**
 * 构建 F0-1「一、函证情况」矩阵（4 品种 × 8 指标）。
 *
 * 返回按品种分组的二维数组：`result[catIdx][metricIdx]`
 */
export function buildF0SummaryMatrix(input: F0MatrixInput): F0MatrixCell[][] {
  const { rows, bookAmounts, manualOverrides } = input
  const result: F0MatrixCell[][] = []

  for (const category of F0_MATRIX_CATEGORIES) {
    const book = bookAmounts?.[category] ?? undefined
    const manualKey = (metric: F0Metric) => `${category}::${metric}`
    const getManual = (metric: F0Metric): number | undefined => manualOverrides?.[manualKey(metric)]

    // R31 发函金额 = SUMIF(E, 品种, F) → grid「金额」列
    const sendAmount = sumByCategory(rows, category, 'amount')
    // R33 回函确认 = SUMIF(E, 品种, U) → grid「可确认金额」列（无相符过滤，见文件头实证表）
    const confirmAmount = sumByCategory(rows, category, 'confirmed_amount')
    // R36 替代确认 = SUMIF(E, 品种, Y) → grid「替代后可确认金额」列
    const altAmount = sumByCategory(rows, category, 'alt_confirmed')

    const cells: F0MatrixCell[] = [
      // R30 账面金额
      {
        category,
        metric: F0_MATRIX_LABELS[0],
        value: getManual(F0_MATRIX_LABELS[0]) ?? book ?? null,
        kind: 'amount',
        editable: true,
        sourceHint: book != null ? '从审定表取数' : '请手工填写',
      },
      // R31 发函金额
      {
        category,
        metric: F0_MATRIX_LABELS[1],
        value: getManual(F0_MATRIX_LABELS[1]) ?? sendAmount,
        kind: 'amount',
        editable: false,
        sourceHint: `Σ grid[品种=${category}].发函金额`,
      },
      // R32 发函占账面比例
      {
        category,
        metric: F0_MATRIX_LABELS[2],
        value: safeRatio(sendAmount, book),
        kind: 'ratio',
        editable: false,
      },
      // R33 回函确认金额
      {
        category,
        metric: F0_MATRIX_LABELS[3],
        value: getManual(F0_MATRIX_LABELS[3]) ?? confirmAmount,
        kind: 'amount',
        editable: false,
        sourceHint: `源模板 SUMIF(E,${category},U) — Σ grid[品种=${category}].可确认金额`,
      },
      // R34 回函占发函比例
      {
        category,
        metric: F0_MATRIX_LABELS[4],
        value: safeRatio(confirmAmount, sendAmount),
        kind: 'ratio',
        editable: false,
      },
      // R35 回函占账面比例
      {
        category,
        metric: F0_MATRIX_LABELS[5],
        value: safeRatio(confirmAmount, book),
        kind: 'ratio',
        editable: false,
      },
      // R36 替代确认金额
      {
        category,
        metric: F0_MATRIX_LABELS[6],
        value: getManual(F0_MATRIX_LABELS[6]) ?? altAmount,
        kind: 'amount',
        editable: false,
        sourceHint: `源模板 SUMIF(E,${category},Y) — Σ grid[品种=${category}].替代后可确认金额`,
      },
      // R37 回函+替代占账面比例
      {
        category,
        metric: F0_MATRIX_LABELS[7],
        value: safeRatio((confirmAmount + altAmount), book),
        kind: 'ratio',
        editable: false,
      },
    ]
    result.push(cells)
  }

  return result
}

/**
 * 从矩阵中提取指定指标行（按品种列顺序）。
 * 便于模板按行渲染。
 */
export function getMatrixRow(
  matrix: F0MatrixCell[][],
  metric: F0Metric,
): F0MatrixCell[] {
  return matrix.map(catCells => {
    const cell = catCells.find(c => c.metric === metric)
    return cell!
  })
}

/**
 * 判断某格是否被手工覆盖。
 */
export function isManualOverride(
  manualOverrides: Record<string, number> | undefined,
  category: F0Category,
  metric: F0Metric,
): boolean {
  if (!manualOverrides) return false
  const key = `${category}::${metric}`
  return key in manualOverrides
}


// ─── 账面金额取数 ─────────────────────────────────────────────────────────────

/** 账面金额在对方 render-config 里的取值路径声明 */
export interface F0BookAmountSource {
  /** 对方底稿 wp_code */
  wpCode: string
  /** 溯源 tooltip（报表行公式，与 `report_config` 逐字一致） */
  hint: string
  /**
   * 从某个 sheet 的 `html_data` 里取金额。
   *
   * 🔴 **三个循环的键名各不相同，不能统一假设 `project_context.tb_amount`**
   * （2026-08-03 浏览器实测 + 后端源码实证）：
   * - F1 = `project_context.prepaid_tb_amount`（另有 `prepaid_tb_leaf_amount` 并列口径）
   * - F3 = `tb_values['2201']`（**顶层不在 project_context**，且是「code → 值」的字典）
   * - F4 = `project_context.tb_amount`
   * 上一版对三者一律读 `project_context.tb_amount` → **只有 F4 取到**，F1/F3 静默落空。
   */
  pick: (htmlData: any) => unknown
}

/**
 * F0 四品种账面金额取数口径。
 *
 * 与 E0 的 `E0_BOOK_AMOUNT_SOURCES` 同族设计：
 * - 预付账款 → F1（报表行 BS-008 = TB('1123')）
 * - 应付票据 → F3（报表行 BS-044 = TB('2201')）
 * - 应付账款 → F4（报表行 BS-045 = TB('2202')）
 * - 本期采购 → 无固定科目（营业成本=SUM_TB('6401~6499')，需 D4 取数），缺失返 null
 *
 * 🔴 三者下发的都是**叶子聚合口径**（带 `parent_check.diff == 0` 自证），
 * 与 `trial_balance` 可能不等 —— 后者在部分项目是旧版 recalc 的父子双算陈旧数据
 * （实证 `2aa00f57`：F4 叶子 267,308,976.77 vs trial_balance 534,617,953.54 = 正好 2 倍）。
 * 各循环的后端 docstring 已明确「取叶子口径」是有意为之，此处照用不做换算。
 */
export const F0_BOOK_AMOUNT_SOURCES: Record<F0Category, F0BookAmountSource | null> = {
  '预付账款': {
    wpCode: 'F1',
    hint: "TB('1123','期末余额') — F1 审定表（project_context.prepaid_tb_amount）",
    pick: (hd) => hd?.project_context?.prepaid_tb_amount ?? hd?.project_context?.prepaid_tb_leaf_amount,
  },
  '应付票据': {
    wpCode: 'F3',
    hint: "TB('2201','期末余额') — F3 审定表（tb_values['2201']）",
    pick: (hd) => hd?.tb_values?.['2201'],
  },
  '应付账款': {
    wpCode: 'F4',
    hint: "TB('2202','期末余额') — F4 审定表（project_context.tb_amount）",
    pick: (hd) => hd?.project_context?.tb_amount,
  },
  '本期采购': null, // 需走 D4 营业成本取数，暂不自动预填
}

/**
 * 从相邻循环（F1/F3/F4）的 render-config html_data 中提取 tb_amount。
 *
 * 调用方需先通过 render-config API 获取对应底稿的 html_data，
 * 传入 `{wpCode: htmlData}` 映射。
 *
 * 设计约束：
 * - 缺失返回 undefined（非 0）——「本项目无此科目」与「余额为 0」是两种状态
 * - 取值路径**逐品种**走 `F0_BOOK_AMOUNT_SOURCES[cat].pick`，
 *   **不是**统一读 `project_context.tb_amount`（三个循环键名各不相同，见上方 `pick` 的实证注释）
 * - 只读对方 render 已下发的字段，不臆造、不做口径换算
 */
export function fetchTbAmountsForF0(
  htmlDataByWpCode: Partial<Record<string, any>>,
): Partial<Record<F0Category, number>> {
  const result: Partial<Record<F0Category, number>> = {}

  for (const category of F0_MATRIX_CATEGORIES) {
    const source = F0_BOOK_AMOUNT_SOURCES[category]
    if (!source) continue

    const amount = Number(source.pick(htmlDataByWpCode[source.wpCode]))
    if (Number.isFinite(amount)) {
      result[category] = amount
    }
  }

  return result
}

// ─── 替代程序合计（从 companies[] 实证结构计算） ──────────────────────────────

/**
 * F0-5/F0-6 替代程序「凭证金额」列字段名。
 *
 * 🔴 实证依据（2026-08-03 复盘返工时 grep 确认）：
 * - 数据形态 = `html_data[sheet]._format='alternative-f05-v1'` + `companies[]`
 *   （**不是** `checklist_responses` 的独立键 —— 上一版 `extractAltTotalsFromResponses`
 *   猜的 `{sheetCode}-block{n}-total` 键名全错，已删）
 * - 每个 company 有 `block1_rows` ~ `block4_rows`，行内金额列见
 *   `blockColumnConfigsF05.ts` 的 `sumField: true` 标记
 * - 四区块的凭证金额列统一为 `voucher_amount`（对齐 `_f0_import_export.py`
 *   的 `_VOUCHER_COLS` 里 `("金额", "voucher_amount", True)`）
 */
export const F0_ALT_VOUCHER_FIELD = 'voucher_amount'

/** 替代程序 company 的最小结构（只取本模块需要的字段） */
export interface F0AltCompanyLike {
  block1_rows?: Array<Record<string, unknown>>
  block2_rows?: Array<Record<string, unknown>>
  block3_rows?: Array<Record<string, unknown>>
  block4_rows?: Array<Record<string, unknown>>
}

/**
 * 从替代程序的 `companies[]` 计算该表的替代确认金额合计。
 *
 * 口径：四区块所有行的 `voucher_amount` 之和（凭证金额 = 已执行替代程序核查的金额）。
 * 空 companies / 空行 / 非数值 → 0（不产出 NaN）。
 */
export function computeAltTotalsFromCompanies(
  companies: readonly F0AltCompanyLike[] | null | undefined,
): F0AltTotals {
  if (!companies?.length) return { total: 0 }

  let total = 0
  for (const company of companies) {
    for (const blockKey of ['block1_rows', 'block2_rows', 'block3_rows', 'block4_rows'] as const) {
      const rows = company[blockKey]
      if (!Array.isArray(rows)) continue
      for (const row of rows) {
        const v = Number(row?.[F0_ALT_VOUCHER_FIELD])
        if (Number.isFinite(v)) total += v
      }
    }
  }

  // 精度归一（避免浮点漂移进矩阵）
  return { total: Math.round(total * 100) / 100 }
}
