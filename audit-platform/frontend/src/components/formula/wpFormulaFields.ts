/**
 * wpFormulaFields.ts — 工作底稿（wp）公式行字段契约映射的单一真源
 *   （Task 1.5 / ADR-FMC-02「后果」独立改动点 / §5 步骤 1 改动点③ / §1 #2b / 需求 2.4）
 *
 * 背景（修复的缺陷 FM-P0-02 的独立子项 §1 #2b）：
 *   后端 `backend/app/routers/wp_formula.py : _formula_to_dict` 返回的工作底稿公式字段是
 *   **契约字段 `category` / `description`**（已实测：`"category": f.category` / `"description": f.description`，
 *   `FormulaSaveRequest` 同样是 `category` / `description`）。而 `FormulaManagerDialog.vue` 的
 *   `loadWpFormulas` 组装 wp 行时**误读** `it.formula_category` / `it.formula_description`（这两个键
 *   在 wp items 上恒为 `undefined`），导致分类/说明落到兜底值（`'取数'` / `''`），右栏显示与保存
 *   错位。此点**独立于 kind 分派**：即便分派正确，字段名读错仍致 category/description 显示与保存错位。
 *
 * ⚠ 口径纪律（必须区分 wp 行 vs report 行，禁误改 report）：
 *   - **wp 行**（本模块处理）：后端契约字段 = `category` / `description`。
 *   - **report 行**（report-config detail，`report_config.py` 的 `ReportConfigRow`）：后端契约字段
 *     **本就是** `formula_category` / `formula_description`（report_config 表字段，`formula_category`
 *     默认 `'auto_calc'`）。report 行读写这两个字段是**合法的**，本模块**不碰** report 行。
 *   - 组件内部行模型（表格列 `prop`、分组、过滤、tag/label）沿用归一化内部键
 *     `formula_category` / `formula_description`，由 wp/report 两侧共用；wp 行只需在**摄入边界**
 *     把契约字段 `category` / `description` 正确映射进内部键，保存 wp 行时再从内部值回写契约字段。
 *
 * 本模块把「wp items 契约字段 → 组件内部行键」的映射收敛为纯函数，由 `loadWpFormulas` 复用，
 * 并由单测钉死 + 变异反证守护（把读的字段改回 `formula_category`/`formula_description` 应打红）。
 */

/** 后端 wp_formula item 的最小结构（只取映射所需契约字段，容忍其余任意字段）。 */
export interface WpFormulaItemLike {
  /** 契约字段：公式分类（auto_calc / logic_check / reasonability / 取数 ...）。 */
  category?: unknown
  /** 契约字段：公式说明。 */
  description?: unknown
}

function asStrOr(v: unknown, fallback: string): string {
  if (typeof v === 'string') return v
  if (v == null) return fallback
  return String(v)
}

/**
 * 从 wp item 的**契约字段** `category` 读分类，缺失时回退默认值。
 *   —— 必须读 `category`（§1 #2b）；读 `formula_category` 会恒 undefined 落兜底（坐实的 bug）。
 */
export function readWpCategory(item: WpFormulaItemLike | null | undefined, fallback = '取数'): string {
  if (!item) return fallback
  const v = item.category
  // 空串视为「未提供」，回退兜底（与旧 `it.formula_category || '取数'` 的真值语义一致）。
  if (v === '' || v == null) return fallback
  return asStrOr(v, fallback)
}

/**
 * 从 wp item 的**契约字段** `description` 读说明，缺失时回退空串。
 *   —— 必须读 `description`（§1 #2b）；读 `formula_description` 会恒 undefined 落空。
 */
export function readWpDescription(item: WpFormulaItemLike | null | undefined, fallback = ''): string {
  if (!item) return fallback
  const v = item.description
  if (v == null) return fallback
  return asStrOr(v, fallback)
}

/**
 * 把 wp item 的契约字段映射进组件内部行键（`formula_category` / `formula_description`）。
 *   内部键名沿用（与 report 行共用的归一化键），但**取值来自契约字段** `category` / `description`。
 */
export function mapWpItemToRowFields(item: WpFormulaItemLike | null | undefined): {
  formula_category: string
  formula_description: string
} {
  return {
    formula_category: readWpCategory(item),
    formula_description: readWpDescription(item),
  }
}
