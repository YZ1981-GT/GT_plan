/**
 * transposeGrid — 客户端整表行列转置纯函数（高级查询模块 · 预览态）
 *
 * Task 18.4（advanced-query-module）：实现前端纯函数整表行列互换，作为**预览态**
 * （行列 ≤ 200×200）的即时交互能力，与后端 `pivot_engine.py::PivotEngine.transpose`
 * 语义对称，供 fast-check round-trip 属性测试（Task 18.5 / Property 10）复用。
 *
 * 设计对齐（design.md §Components 5 PivotEngine「服务端 vs 客户端决策」）：
 *  - 分组/透视后的结果集在**服务端**转置（保证与导出一致、addr_id 溯源精确）。
 *  - 纯明细结果集的整表行列互换在**客户端**（预览态、行列 ≤ 200×200）实现即时交互，
 *    不落导出——即本文件。
 *
 * 数据结构（镜像后端 `Grid` / `Cell`，采用前端 camelCase 契约）：
 *  - `Grid: { rowLabels: string[], colLabels: string[], cells: Cell[][] }`
 *  - `Cell: { value: unknown, addrId: string | null }`
 *  - `cells` 为 `R × C` 二维矩阵，`cells[r][c]` 对应 `rowLabels[r]` × `colLabels[c]`
 *    的交叉单元格。
 *
 * round-trip（R6.3 / Property 10）：`transposeGrid(transposeGrid(grid))` 在
 * **单元格值、行标签、列标签、行列顺序**四个维度上与原网格完全一致。为此
 * `transposeGrid` 实现为**对称纯函数**：
 *  - 不修改入参（`rowLabels` / `colLabels` 复制新数组，`Cell` 逐个浅拷贝，
 *    不与入参共享可变引用）；
 *  - 无 IO、无副作用、无 async；
 *  - 维度以标签长度为准（`R = rowLabels.length`、`C = colLabels.length`），
 *    从而对退化形态（空表、有标签无数据、单行/单列）亦保持严格 round-trip。
 *
 * Validates: Requirements 6.2, 6.3
 */

/**
 * 转置网格单元格。
 *
 * - `value`：单元格显示值（任意标量，含 `null` 表示空值）。
 * - `addrId`：当且仅当该值由**单一可解析源格**产生时携带其 ACNR `addr_id`
 *   以支持下钻；多源聚合或无源 → `null`（不可下钻）。
 */
export interface Cell {
  value: unknown
  addrId: string | null
}

/**
 * 行列交叉结果网格。
 *
 * - `rowLabels`：行标签（长度 `R`）。
 * - `colLabels`：列标签（长度 `C`）。
 * - `cells`：`R × C` 二维矩阵，`cells[r][c]` 为第 `r` 行第 `c` 列的 {@link Cell}。
 *
 * 不变式：`cells.length === rowLabels.length` 且每行 `cells[r].length === colLabels.length`。
 */
export interface Grid {
  rowLabels: string[]
  colLabels: string[]
  cells: Cell[][]
}

/** 预览态整表转置的行数上限（design.md：客户端转置 行列 ≤ 200×200）。 */
export const PREVIEW_MAX_ROWS = 200

/** 预览态整表转置的列数上限（design.md：客户端转置 行列 ≤ 200×200）。 */
export const PREVIEW_MAX_COLS = 200

/**
 * 判断网格是否超出预览态整表转置的规模上限（行 > 200 或列 > 200）。
 *
 * 视图层应在调用 {@link transposeGrid} 之前用本函数守卫：超限时不做客户端转置，
 * 转而走服务端透视/转置路径（design.md §Components 5「超阈值 → 服务端」）。
 *
 * @param grid 结果网格。
 * @returns 行数超过 {@link PREVIEW_MAX_ROWS} 或列数超过 {@link PREVIEW_MAX_COLS} 时为 `true`。
 */
export function exceedsPreviewLimit(grid: Grid): boolean {
  return (
    grid.rowLabels.length > PREVIEW_MAX_ROWS ||
    grid.colLabels.length > PREVIEW_MAX_COLS
  )
}

/**
 * 安全读取 `cells[r][c]` 并返回**忠实浅拷贝**；越界/缺失 → 空 `Cell`。
 *
 * 以浅拷贝（`{ value, addrId }`）确保转置结果不与入参共享可变 `Cell` 引用（纯函数）；
 * `Cell` 字段为不可变标量，浅拷贝已足够隔离。对良构网格（`cells` 与标签维度一致）
 * 恒返回原单元格的忠实拷贝，从而保证严格 round-trip；仅对畸形/越界网格以空
 * `{ value: null, addrId: null }` 兜底，使函数为全函数（不抛异常）。
 */
function cellAt(cells: Cell[][], r: number, c: number): Cell {
  const row = cells[r]
  if (row !== undefined) {
    const cell = row[c]
    if (cell !== undefined) {
      return { value: cell.value, addrId: cell.addrId }
    }
  }
  return { value: null, addrId: null }
}

/**
 * 整表行列互换（R6.2），对称纯函数保证 round-trip（R6.3）。
 *
 * 语义：
 *  - 新行标签 = 原列标签；新列标签 = 原行标签。
 *  - 新矩阵 `out[c][r] = grid.cells[r][c]`（矩阵转置）。
 *
 * 实现为对称纯函数：
 *  - 维度以标签长度为准（`R = rowLabels.length`、`C = colLabels.length`），
 *    对「空数据但有标签」等退化形态亦保持严格 round-trip
 *    （`transposeGrid(transposeGrid(g))` 在值 / 行标签 / 列标签 / 行列顺序上完全一致）。
 *  - 不修改入参（标签数组复制、`Cell` 逐个浅拷贝），无 IO、无 async。
 *  - 对越界/缺失单元格以空 `Cell` 兜底，函数为全函数（不抛异常）。
 *
 * 注意：本函数**不做规模上限校验**（保持纯粹以满足 round-trip 属性）；预览态调用方
 * 应先用 {@link exceedsPreviewLimit} 守卫 200×200 上限，超限走服务端路径。
 *
 * @param grid 满足 `R × C` 不变式的结果网格。
 * @returns 转置后的新 `Grid`（`C × R`），与入参无共享引用。
 */
export function transposeGrid(grid: Grid): Grid {
  const rCount = grid.rowLabels.length
  const cCount = grid.colLabels.length

  const transposed: Cell[][] = []
  for (let c = 0; c < cCount; c += 1) {
    const outRow: Cell[] = []
    for (let r = 0; r < rCount; r += 1) {
      outRow.push(cellAt(grid.cells, r, c))
    }
    transposed.push(outRow)
  }

  return {
    rowLabels: [...grid.colLabels],
    colLabels: [...grid.rowLabels],
    cells: transposed,
  }
}
