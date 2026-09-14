/**
 * customWpCellEdit — 自定义底稿单元格编辑的纯函数层（零 Vue 依赖，便于 PBT）
 *
 * ## 为什么前端也要一份单元格引用解析
 *
 * 后端 `app/services/custom_workpaper_projection.py` 已有
 * `parse_cell_ref` / `normalize_cell_ref` / `col_letter_to_index`。前端再实现一份
 * 是**有意的** —— 用户每敲一格都要即时校验/归一，不能每格往后端跑一趟。
 *
 * 🔴 两份实现必须语义一致，由守卫 `customGridEditing.spec.ts` 的 Property 23
 * **读后端源码做交叉锁死**（对同一组样本两侧结论相同）。改任一侧都要跑那条守卫。
 *
 * ## 坐标恒等
 *
 * 自定义底稿的投影坐标 ≡ xlsx 坐标（不剥表头、不重编行号、不裁空列），
 * 故本层产出的 `B6` 可直接作为 `PUT /custom-cells` 的 body 键写回 xlsx。
 * 🔴 这是为什么不能复用 `wp_grid_extract.extract_grid` 的投影 ——
 * 它 `row_offset = data_start_row - 1` 重编行号（实测 xlsx `B6` → 投影 `B2`），
 * 按投影坐标写回会写进表头区覆盖别的格。
 *
 * spec: .kiro/specs/custom-workpaper-dual-mode-formula-and-batch/ Wave 2 Task 7
 */

/** 单次提交上限，与后端 `MAX_CELL_UPDATES` 一致（守卫交叉锁死）。 */
export const MAX_CELL_UPDATES = 500

/** 列字母 → 1-based 列号（"A"→1, "Z"→26, "AA"→27）。非法返回 0。 */
export function colLetterToIndex(letters: string): number {
  if (!letters) return 0
  let n = 0
  for (const ch of letters.toUpperCase()) {
    if (ch < 'A' || ch > 'Z') return 0
    n = n * 26 + (ch.charCodeAt(0) - 64)
  }
  return n
}

/** 1-based 列号 → 列字母（1→"A", 27→"AA"）。非正数返回空串。 */
export function colIndexToLetter(c: number): string {
  if (!Number.isInteger(c) || c <= 0) return ''
  let s = ''
  let n = c
  while (n > 0) {
    const m = (n - 1) % 26
    s = String.fromCharCode(65 + m) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}

/**
 * 单元格引用 → `{row, col}`（均 1-based，与 openpyxl / 后端 `parse_cell_ref` 一致）。
 *
 * 🔴 非法引用返回 **`null`** 而不是 `{row: 0, col: 0}` —— 返回 0 会让调用方的
 * `if (ref.row)` 判空成功但语义是「第 0 行」，写回时把补丁投到不存在的格上。
 * 支持 `$B$5` 绝对引用与小写。
 */
export function parseCellRef(ref: string): { row: number; col: number } | null {
  if (typeof ref !== 'string') return null
  const raw = ref.trim().toUpperCase().replace(/\$/g, '')
  if (!raw) return null
  let letters = ''
  let digits = ''
  for (const ch of raw) {
    if (ch >= 'A' && ch <= 'Z') {
      // 字母出现在数字之后 → 非法（如 "B5C"）
      if (digits) return null
      letters += ch
    } else if (ch >= '0' && ch <= '9') {
      digits += ch
    } else {
      return null
    }
  }
  if (!letters || !digits) return null
  const col = colLetterToIndex(letters)
  const row = Number.parseInt(digits, 10)
  if (!col || !Number.isFinite(row) || row <= 0) return null
  return { row, col }
}

/** 归一化单元格引用（`b5` / `$B$5` → `B5`）。非法返回 `null`。 */
export function normalizeCellRef(ref: string): string | null {
  const rc = parseCellRef(ref)
  if (!rc) return null
  return `${colIndexToLetter(rc.col)}${rc.row}`
}

export interface CellPatchResult {
  /** 归一化后的补丁（键为标准引用），可直接作为 `PUT /custom-cells` 的 `updates` */
  updates: Record<string, unknown>
  /** 超过上限（未截断，调用方须提示用户分批） */
  overflow: boolean
  /** 键非法而被丢弃的原始键（调用方可提示具体是哪个格） */
  invalid: string[]
}

/**
 * 脏格收集 → 提交补丁。
 *
 * - 键归一化（`b5` 与 `$B$5` 归到同一个 `B5`）
 * - 同一格多次修改**保留最后一次**（Map 迭代序即写入序）
 * - 🔴 超过 `maxCells` 时置 `overflow` 而**不静默截断** ——
 *   截断会让用户以为都存上了（平台既有铁律：保存失败/部分失败必须可见）
 */
export function buildCellPatch(
  dirty: Map<string, unknown> | Record<string, unknown>,
  opts?: { maxCells?: number },
): CellPatchResult {
  const maxCells = opts?.maxCells ?? MAX_CELL_UPDATES
  const entries: Array<[string, unknown]> =
    dirty instanceof Map ? Array.from(dirty.entries()) : Object.entries(dirty ?? {})

  const updates: Record<string, unknown> = {}
  const invalid: string[] = []
  for (const [rawRef, value] of entries) {
    const ref = normalizeCellRef(String(rawRef))
    if (ref === null) {
      invalid.push(String(rawRef))
      continue
    }
    updates[ref] = value // 后写覆盖先写
  }
  return {
    updates,
    overflow: Object.keys(updates).length > maxCells,
    invalid,
  }
}

/**
 * 网格是否有可渲染内容 —— 与后端 `grid_has_content` / `GtGridSheet.hasData` 同口径。
 *
 * 🔴 三侧必须一致：后端判「有内容」而前端判「无内容」会让存量补齐白跑
 * （补齐了但界面仍显示空态）。
 */
export function gridHasContent(grid: unknown): boolean {
  if (!grid || typeof grid !== 'object') return false
  const g = grid as { cells?: unknown; max_row?: unknown }
  if (!g.cells || typeof g.cells !== 'object') return false
  if (Object.keys(g.cells as Record<string, unknown>).length === 0) return false
  const n = Number(g.max_row)
  return Number.isFinite(n) && n > 0
}

/**
 * 空网格的成因（R1.4）：必须能区分「底稿文件异常」与「确实是空底稿」。
 *
 * 🔴 两者都显示「暂无内容」会让文件损坏被当成正常空表 —— 用户以为自己还没录，
 * 实际是 xlsx 丢了，录进去也存不住。
 */
export type EmptyGridReason = 'has-content' | 'source-unavailable' | 'empty-workpaper'

export function classifyEmptyGrid(grid: unknown): EmptyGridReason {
  if (gridHasContent(grid)) return 'has-content'
  const g = (grid ?? {}) as { source_unavailable?: unknown }
  return g.source_unavailable === true ? 'source-unavailable' : 'empty-workpaper'
}

// ─── 公式选址列表（Task 12）───────────────────────────────────────────────────

export interface FormulaCellOption {
  /** 单元格引用（归一化后，如 `B5`） */
  cell: string
  /** 供审计师识别的语义标签 */
  label: string
}

/** 公式清单条目（后端 `list_formulas` 的 `items` 元素，只声明本组件消费的字段） */
export interface FormulaListItem {
  id: string
  target_cell: string
  expression: string
  formula_type: string
  sheet_name?: string | null
  computed_value?: string | null
  last_computed_at?: string | null
}

function cellTextOf(cells: Record<string, unknown>, ref: string): string {
  const raw = cells[ref]
  if (raw == null) return ''
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>
    // 公式格不拿它自己的值当标签（那是求值结果，不是项目名）
    const v = o.v ?? o.value
    return v == null ? '' : String(v).trim()
  }
  return String(raw).trim()
}

/**
 * 派生公式选址列表：`{cell, label}`，label 带语义而非纯 `A1`/`B2`。
 *
 * 派生优先级（🔴 与后端无关，纯前端展示层）：
 *   ① 本格自带 `label` / `name`
 *   ② **同行首个有文本的列**（表格通常首列是项目名）→ `项目名 (B5)`
 *   ③ **同列首个有文本的行**（表头行）→ `表头 (B5)`
 *   ④ 都没有 → 纯引用 `B5`
 *
 * 🔴 不把「本格自身的数值」当标签：数值格的值是金额，拿它当标签会让选址列表
 *    出现一堆金额，反而更难定位。
 */
export function buildFormulaCellOptions(
  cellsInput: unknown,
): FormulaCellOption[] {
  if (!cellsInput || typeof cellsInput !== 'object') return []
  const cells = cellsInput as Record<string, unknown>

  // 预扫：每行/每列的首个文本格
  const rowFirstText = new Map<number, string>()
  const colFirstText = new Map<number, string>()
  const parsed: Array<{ ref: string; row: number; col: number }> = []

  for (const key of Object.keys(cells)) {
    const rc = parseCellRef(key)
    if (!rc) continue
    parsed.push({ ref: key, row: rc.row, col: rc.col })
  }
  // 按行、列升序，保证「首个」稳定（对象键序不可依赖）
  const byCol = [...parsed].sort((a, b) => a.col - b.col || a.row - b.row)
  const byRow = [...parsed].sort((a, b) => a.row - b.row || a.col - b.col)

  for (const p of byCol) {
    if (rowFirstText.has(p.row)) continue
    const t = cellTextOf(cells, p.ref)
    if (t && !isNumericText(t)) rowFirstText.set(p.row, t)
  }
  for (const p of byRow) {
    if (colFirstText.has(p.col)) continue
    const t = cellTextOf(cells, p.ref)
    if (t && !isNumericText(t)) colFirstText.set(p.col, t)
  }

  const out: FormulaCellOption[] = []
  for (const p of byRow) {
    const ref = normalizeCellRef(p.ref) ?? p.ref
    const raw = cells[p.ref]
    let label = ''
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      const o = raw as Record<string, unknown>
      const own = o.label ?? o.name
      if (own != null && String(own).trim()) label = String(own).trim()
    }
    if (!label) {
      const rowLabel = rowFirstText.get(p.row)
      const colLabel = colFirstText.get(p.col)
      // 行标签优先（首列项目名比表头更能定位具体行）
      const semantic = rowLabel || colLabel
      label = semantic ? `${semantic} (${ref})` : ref
    }
    out.push({ cell: ref, label })
  }
  return out
}

/** 是否纯数字文本（金额/数量不适合当语义标签） */
function isNumericText(s: string): boolean {
  const t = s.replace(/[,\s%]/g, '')
  if (!t) return false
  return Number.isFinite(Number(t))
}
