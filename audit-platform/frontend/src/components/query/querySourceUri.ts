/**
 * 高级查询源 URI 解析纯函数（advanced-query-consolidation Req3）
 *
 * 从 CustomQueryDialog 的 jumpToCell / onTraceToTemplate 内联逻辑迁出，
 * 共享 URI 构造规则与失败提示文案常量。
 */

/**
 * 拼接 workpaper 类 URI：`workpaper:{wpCode}|{sheetName}|{cellRef}`
 * sheet/cell 缺省时省略对应分隔段。
 */
export function buildWorkpaperUri(wpCode: string, sheetName?: string, cellRef?: string): string {
  let uri = `workpaper:${wpCode}`
  if (sheetName) {
    uri += `|${sheetName}`
    if (cellRef) uri += `|${cellRef}`
  }
  return uri
}

/**
 * 从结果行 + 当前选定数据源推断溯源 URI。
 * 优先 workpaper > report > note > selectedSource 兜底。
 */
export function buildTraceUri(row: Record<string, any>, selectedSource: string): string {
  if (row.wp_code && row.sheet_name) {
    return buildWorkpaperUri(row.wp_code, row.sheet_name, row.cell_ref)
  }
  if (row.module === 'report' && row.report_type) {
    return `report:${row.report_type}`
  }
  if (row.module === 'note' && row.section_id) {
    return `note:${row.section_id}`
  }
  if (selectedSource) {
    return selectedSource
  }
  return ''
}

/**
 * 以 `report_` 开头、却不是报表叶子的数据源键：报表行次配置（advanced-query-linkage-closure 任务 17）。
 * 它们不得派生 `report_type` 筛选——否则请求带 `report_type: 'lines'`，后端按这个不存在的报表类型过滤得 0 行。
 */
const NON_REPORT_SOURCES: ReadonlySet<string> = new Set(['report_lines'])

/**
 * 报表叶子（`report_{类型}`）的报表类型；其余数据源（含 `report_lines` 与通用 `report`）返回 null。
 * 弹窗与页面版据此决定请求要不要带 `filters.report_type`（单一判定，两处不再各写 `startsWith('report_')`）。
 */
export function reportTypeOfSource(source: string): string | null {
  if (!source || !source.startsWith('report_') || NON_REPORT_SOURCES.has(source)) return null
  return source.slice('report_'.length) || null
}

/** 统一失败提示文案（各消费方复用，UI 口径一致） */
export const RESOLVE_FAIL_MSG = {
  wpNotFound: (code: string) => `底稿 ${code} 在当前项目不存在`,
  notRegistered: '该模板未在 registry，请先 migrate',
  noUri: '无法确定数据源 URI',
} as const
