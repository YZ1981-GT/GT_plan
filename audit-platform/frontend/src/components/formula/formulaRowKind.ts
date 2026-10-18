/**
 * formulaRowKind.ts — 公式行 kind 分类 + 只读判定 + 保存端点分派的单一真源
 *   （Task 1.4 / ADR-FMC-02 / §5 步骤 1 改动点②）
 *
 * 背景（修复的缺陷 FM-P0-02）：
 *   1. 后端 surfaced/Tier B 投影逐条硬标 `readonly:true`（§1 #3 实测），前端却把它
 *      渲染成可编辑行并包装「自定义 / 健康度100%」等伪装标签 —— 把只读说明元数据当成
 *      可编辑的权威公式。
 *   2. `onFormulaEditSave` 的「已有行——更新到后端」分支为 `if (row.id) { PUT report-config }`，
 *      **无 kind 校验**：任何有 id 的非报表、非 tb_detail 行保存时都会发 report-config
 *      detail 端点（§1 #2 实测），把工作底稿公式误写进全局报表模板。
 *
 * 本模块把「行属于哪类权威源（kind）」「是否只读投影」「保存应发哪个端点」收敛为纯函数，
 * 由 `FormulaManagerDialog.vue` 的模板（隐藏只读行编辑按钮/伪装标签）与 `onFormulaEditSave`
 * （按 kind 分派）复用，并由单测钉死 + 变异反证守护。
 *
 * kind 边界（与 `loadWpFormulas` 组装的行形态对齐）：
 *   - wp         : 工作底稿正式公式（`wp_formula` 表）。`formula_source === '底稿公式(wp_formula)'`，
 *                  或可编辑的四表提取 Tier A（`formula_source` 以「四表提取」开头且非只读）。
 *                  保存走 `PUT /api/workpapers/{wp_id}/formulas`（wpFormula.upsert）。
 *   - surfaced   : 专属组件取数公式 surfacing（`*-surfaced-*` 伪 id，`readonly:true`）。只读，禁保存。
 *   - extraction : 四表提取只读溯源（Tier B，`readonly:true`，`tierB-*` id）。只读，禁保存。
 *   - report     : 报表模板公式（report_config），有真实 id，保存走 report-config detail。
 *   - tb_detail  : 试算表科目明细公式（持久化 wizard_state）。**在本模块之外**由
 *                  `persistTbDetailFormulas()` 分流（调用方在进入本模块前已拦截），此处不涉及。
 *
 * 只读判定（fail-closed 的反面：宁可多判只读也不把只读投影放成可编辑）：
 *   后端对所有只读投影硬标 `row.readonly === true`，这是唯一权威信号。另：surfaced 伪 id
 *   形如 `*-surfaced-*`、Tier B id 形如 `tierB-*`，作为次级防御（即便某行漏标 readonly，
 *   凭 id 形态也能识别为只读投影），避免只依赖单一布尔被上游误清。
 */

/** 公式行的权威源 kind。 */
export type FormulaRowKind = 'wp' | 'surfaced' | 'extraction' | 'report'

/** 保存分派目标。`reject` = 只读投影不可保存。 */
export type SaveDispatchTarget = 'wp' | 'report' | 'reject'

/** 公式行投影的最小结构（只取分类所需字段，容忍其余任意字段）。 */
export interface FormulaRowLike {
  id?: unknown
  readonly?: unknown
  formula_source?: unknown
  // 保存 wp 行时需要的回源字段（loadWpFormulas 组装时保留）。
  sheet_name?: unknown
  target_cell?: unknown
}

/** surfaced 伪 id：`E1-surfaced-tb-check` / `E1-surfaced-adj-0` / `{base}-surfaced-{sheet}-{i}` 等。 */
const SURFACED_ID_RE = /-surfaced-|^[A-Za-z0-9]+-surfaced$/
/** Tier B 只读溯源 id：`tierB-*`。 */
const TIER_B_ID_RE = /^tierB-/

function asStr(v: unknown): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v)
}

/**
 * 该行是否为**只读投影**（surfaced / Tier B 溯源）。
 *   权威信号 = 后端硬标的 `readonly === true`；次级信号 = surfaced/tierB 伪 id 形态。
 *   任一命中即判只读（禁把只读投影渲染成可编辑 / 禁保存）。
 */
export function isReadonlyProjectionRow(row: FormulaRowLike | null | undefined): boolean {
  if (!row) return false
  if (row.readonly === true) return true
  const id = asStr(row.id)
  if (id && (SURFACED_ID_RE.test(id) || TIER_B_ID_RE.test(id))) return true
  return false
}

/**
 * 分类公式行的权威源 kind。
 *   - 只读投影：按 id/source 细分为 surfaced 或 extraction（Tier B）。
 *   - 可编辑四表提取 Tier A（source 以「四表提取」开头且非只读）归 wp（保存走 wp 端点）。
 *   - `formula_source === '底稿公式(wp_formula)'` → wp。
 *   - 其余（含报表模板行）→ report。
 *
 * 注：tb_detail 行由调用方在进入保存链前经 `persistTbDetailFormulas()` 分流，不走本函数。
 */
export function classifyFormulaRowKind(row: FormulaRowLike | null | undefined): FormulaRowKind {
  if (!row) return 'report'
  const src = asStr(row.formula_source)
  const id = asStr(row.id)

  // 只读投影：surfaced vs extraction（Tier B 溯源）。
  if (isReadonlyProjectionRow(row)) {
    if (TIER_B_ID_RE.test(id) || src === 'Tier B 溯源' || src.startsWith('四表提取')) {
      return 'extraction'
    }
    // 伪 id 含 -surfaced- 或后端未标 source 的只读行默认归 surfaced。
    return 'surfaced'
  }

  // 可编辑行：wp_formula 正式公式 / 可编辑的四表提取 Tier A（保存都走 wp 端点）。
  if (src === '底稿公式(wp_formula)' || src.startsWith('四表提取')) {
    return 'wp'
  }

  // 其余为报表模板公式（report_config）。
  return 'report'
}

/**
 * 解析该行保存应发往哪个端点（保存链「先按 kind 分派」的裁决）。
 *   - wp         → 'wp'     （`PUT /api/workpapers/{wp_id}/formulas`，wpFormula.upsert）
 *   - surfaced   → 'reject' （只读投影，禁保存）
 *   - extraction → 'reject' （只读溯源，禁保存）
 *   - report     → 'report' （report-config detail）
 */
export function resolveSaveDispatch(row: FormulaRowLike | null | undefined): SaveDispatchTarget {
  const kind = classifyFormulaRowKind(row)
  if (kind === 'surfaced' || kind === 'extraction') return 'reject'
  if (kind === 'wp') return 'wp'
  return 'report'
}
