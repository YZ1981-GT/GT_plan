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
 * 从结果行 + 本次结果的数据源推断模板溯源 URI（`GET /api/custom-query/address-resolve` 认的 module 前缀，ADR-AQL-17）。
 *
 * 优先行上的底稿编码（有 sheet / 单元格时带上）> 行上的报表 / 附注标记 > 按数据源：底稿选区源原样、报表叶子 →
 * `report:<类型>`、报表行次配置 → `report:<行上的报表类型>`、附注章节 → `note:<章节号>`、附注目录 → `note:`、
 * 调整分录 → `adj:<源>`、其余（试算 / 四表 / 合并）→
 * `tb:<源>`（后端回 `registered=false`：这类结果没有模板定义）。原先注册表源键原样发出（如 `tb_detail`），后端认不出 ⇒ 400。
 */
export function buildTraceUri(row: Record<string, any>, selectedSource: string): string {
  if (row.wp_code) {
    return buildWorkpaperUri(row.wp_code, row.sheet_name, row.cell_ref)
  }
  if (row.module === 'report' && row.report_type) {
    return `report:${row.report_type}`
  }
  if (row.module === 'note' && row.section_id) {
    return `note:${row.section_id}`
  }
  const source = selectedSource || ''
  if (!source) return ''
  if (source.startsWith('workpaper:')) return source
  const reportType = reportTypeOfSource(source)
  if (reportType) return `report:${reportType}`
  // 报表行次配置 / 通用报表源：行上带报表类型（报表配置即报表模板）
  if (source === 'report_lines' || source === 'report') return `report:${row.report_type ?? ''}`
  if (source.startsWith('disclosure_note:')) return `note:${source.slice('disclosure_note:'.length)}`
  if (source === 'disclosure') return 'note:'
  if (source === 'adjustment' || source.startsWith('adj_')) return `adj:${source}`
  return `tb:${source}`
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
  notRegistered: '该底稿编码未在模板目录中登记，无法打开模板',
  noTemplate: '该类结果没有模板定义',
  noUri: '无法确定该结果的数据源',
} as const
