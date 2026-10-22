/**
 * functionSupportMatrix.ts — 函数支持矩阵（前端镜像）
 * spec formula-manager-closure · Task 4.2 / 需求 8（禁静默 0）
 *
 * 「函数 × 执行器 → 支持 / 不支持」矩阵的前端侧。**单一真源在后端**
 * （backend/app/services/formula_management/function_support_matrix.py），本文件据同一张
 * golden 对照（backend/tests/fixtures/function_support_matrix.json）镜像，两侧经
 * functionSupportMatrix.spec.ts 对拍 ⇒ 前端渲染 == 后端真相（与 sheetKeyNormalization 对拍同模式）。
 *
 * UI 用法（FormulaBar.vue）：按当前执行器查 isFunctionSupported(fn, executor)；
 * 不支持者禁用按钮 + tooltip 标注 unsupportedReason(fn, executor)「此处不支持」，
 * **禁止点击后静默返回 0**。
 *
 * 禁在本文件写死矩阵值以外的任何判据计数；矩阵值本身即与后端 golden 对拍的内容。
 */

export type Executor = 'wp_evaluator' | 'report_path' | 'note_executor' | 'central_batch'

/** UI 工具栏可提供的取数函数全集（顺序即展示建议顺序，与后端 FUNCTIONS 对齐）。 */
export const FUNCTIONS = [
  'TB',
  'SUM_TB',
  'ROW',
  'SUM_ROW',
  'REPORT',
  'NOTE',
  'WP',
  'PREV',
  'AUX',
  'ADJ',
] as const
export type FormulaFunction = (typeof FUNCTIONS)[number]

export const EXECUTORS: Executor[] = ['wp_evaluator', 'report_path', 'note_executor', 'central_batch']

interface Cell {
  supported: boolean
  reason: string | null
}

/**
 * 矩阵真值（镜像后端）。每一格依据见后端模块 docstring 的逐执行器实证：
 *  - wp_evaluator：工作底稿可编辑公式 10 个函数都支持（R6：PREV/AUX/ROW/SUM_ROW/REPORT/NOTE 严格按值代入，
 *    ADJ 走统一预载层；取不到数报错不代入 0）
 *  - report_path：PREV/AUX 硬置 0、ADJ 默认不注入 ⇒ False
 *  - note_executor：仅 TB/REPORT/NOTE/WP（用 PRIOR/AGING，非 PREV/AUX）
 *  - central_batch：ADJ 实时注入 ⇒ 全 True
 */
const MATRIX: Record<FormulaFunction, Record<Executor, Cell>> = {
  TB: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: true, reason: null },
    note_executor: { supported: true, reason: null },
    central_batch: { supported: true, reason: null },
  },
  SUM_TB: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: true, reason: null },
    note_executor: { supported: false, reason: '附注执行器不解析 SUM_TB（附注表内用 SUM 行区间）' },
    central_batch: { supported: true, reason: null },
  },
  ROW: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: true, reason: null },
    note_executor: { supported: false, reason: '附注执行器不解析 ROW（跨报表行引用用 REPORT）' },
    central_batch: { supported: true, reason: null },
  },
  SUM_ROW: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: true, reason: null },
    note_executor: { supported: false, reason: '附注执行器不解析 SUM_ROW' },
    central_batch: { supported: true, reason: null },
  },
  REPORT: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: true, reason: null },
    note_executor: { supported: true, reason: null },
    central_batch: { supported: true, reason: null },
  },
  NOTE: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: true, reason: null },
    note_executor: { supported: true, reason: null },
    central_batch: { supported: true, reason: null },
  },
  WP: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: true, reason: null },
    note_executor: { supported: true, reason: null },
    central_batch: { supported: true, reason: null },
  },
  PREV: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: false, reason: '报表路径对 PREV 恒置 0（上期值走报表 prior 列，非 PREV）' },
    note_executor: { supported: false, reason: '附注执行器用 PRIOR 取上年附注，不解析 PREV' },
    central_batch: { supported: true, reason: null },
  },
  AUX: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: false, reason: '报表路径对 AUX 恒置 0（辅助核算不进报表求值）' },
    note_executor: { supported: false, reason: '附注执行器用 AGING 取账龄分桶，不解析 AUX' },
    central_batch: { supported: true, reason: null },
  },
  ADJ: {
    wp_evaluator: { supported: true, reason: null },
    report_path: { supported: false, reason: '报表路径默认不注入实时调整额（走 central_batch 注入）' },
    note_executor: { supported: false, reason: '附注执行器不解析 ADJ' },
    central_batch: { supported: true, reason: null },
  },
}

/** 序列化载荷（供 golden 对拍；结构与后端 build_matrix_payload 完全一致）。 */
export function buildMatrixPayload(): {
  schema_version: number
  functions: string[]
  executors: string[]
  matrix: Record<string, Record<string, Cell>>
} {
  const matrix: Record<string, Record<string, Cell>> = {}
  for (const fn of FUNCTIONS) {
    matrix[fn] = {}
    for (const exe of EXECUTORS) {
      const cell = MATRIX[fn][exe]
      matrix[fn][exe] = { supported: cell.supported, reason: cell.supported ? null : cell.reason }
    }
  }
  return {
    schema_version: 1,
    functions: [...FUNCTIONS],
    executors: [...EXECUTORS],
    matrix,
  }
}

/** 函数在某执行器是否支持。未知函数/执行器 fail-closed 判不支持。 */
export function isFunctionSupported(fn: string, executor: Executor): boolean {
  const row = MATRIX[fn as FormulaFunction]
  if (!row) return false
  const cell = row[executor]
  return !!cell && cell.supported
}

/** 不支持时的原因文案（UI tooltip 用）；支持时返 null。 */
export function unsupportedReason(fn: string, executor: Executor): string | null {
  if (isFunctionSupported(fn, executor)) return null
  const cell = MATRIX[fn as FormulaFunction]?.[executor]
  return cell?.reason ?? '此执行器不支持该函数'
}
