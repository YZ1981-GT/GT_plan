/**
 * render-config 共享载荷展开（spec platform-perf-hotspots R1）。
 *
 * 后端 `share_html_data=1` 时，内容相同（只差 sheet_name）的页签 html_data 只在顶层
 * `shared_html_data[ref]` 放一份，页签只留差异键并带 `html_data_ref`（D2 一份 render-config
 * 由 14.7MB 降到约 1MB）。这里还原成不带参数时的形状：引用页签
 * `html_data = { ...structuredClone(shared[ref]), ...差异键 }`，再删掉引用与顶层字段。
 *
 * - 逐页深拷贝：原先每个页签是独立对象，下游有原地修改，共用引用会串页。
 * - 不改入参：apiProxy 在途共享会把同一个响应对象交给多个调用方。
 * - 引用缺失是契约错误，直接抛出（调用方进错误态），不静默给空数据。
 */
import { toRaw } from 'vue'
import type { RenderConfig, SheetRenderConfig } from '@/types/renderConfig'

export function expandSharedHtmlData(config: RenderConfig): RenderConfig {
  const sheets = config.sheets ?? []
  const shared = config.shared_html_data
  if (shared == null && !sheets.some((sheet) => sheet.html_data_ref != null)) return config
  const { shared_html_data: _shared, ...root } = config
  const expanded = sheets.map((sheet): SheetRenderConfig => {
    const ref = sheet.html_data_ref
    if (ref == null) return sheet
    const base = shared?.[ref]
    if (base == null) throw new Error(`render-config 共享载荷缺失：${ref}`)
    const { html_data_ref: _ref, ...rest } = sheet
    return { ...rest, html_data: { ...structuredClone(toRaw(base)), ...(sheet.html_data ?? {}) } }
  })
  return { ...root, sheets: expanded }
}
