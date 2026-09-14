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

/** 统一失败提示文案（各消费方复用，UI 口径一致） */
export const RESOLVE_FAIL_MSG = {
  wpNotFound: (code: string) => `底稿 ${code} 在当前项目不存在`,
  notRegistered: '该模板未在 registry，请先 migrate',
  noUri: '无法确定数据源 URI',
} as const
