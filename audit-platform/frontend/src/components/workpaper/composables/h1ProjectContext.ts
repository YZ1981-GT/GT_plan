/** H1 宿主与离屏 provider 共用的项目附注口径读取。 */
export interface H1ProjectContext {
  templateType: string
  reportScope: string
}

function object(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

export function resolveH1ProjectContext(source: unknown): H1ProjectContext {
  const root = object(object(source).data ?? source)
  const html = object(root.html_data ?? root.htmlData ?? root)
  const context = object(
    html.project_context
    ?? html.projectContext
    ?? root.project_context
    ?? root.projectContext,
  )
  return {
    templateType: String(context.template_type ?? context.templateType ?? root.template_type ?? ''),
    reportScope: String(context.report_scope ?? context.reportScope ?? root.report_scope ?? ''),
  }
}
