import { sChecklistItemIds, type SChecklistComponentType } from './sChecklistItemIds'
import http from '@/utils/http'

export interface SChecklistRenderSheet {
  componentType?: string | null
  component_type?: string | null
  item_id?: string | null
  sheet_name?: string | null
  html_data?: Record<string, any> | null
  [key: string]: any
}

/**
 * 从 http 响应中取 render-config 的 sheets，兼容 axios、业务信封和测试夹具。
 * 组件不应自行猜测 response.data 的层级。
 */
export function getRenderConfigSheets(response: any): SChecklistRenderSheet[] {
  const candidates = [
    response?.data?.data?.sheets,
    response?.data?.sheets,
    response?.sheets,
  ]
  const sheets = candidates.find(Array.isArray)
  return Array.isArray(sheets) ? sheets : []
}

function identityValues(sheet: SChecklistRenderSheet): string[] {
  const payload = sheet.html_data
  return [
    sheet.componentType,
    sheet.component_type,
    payload?.component_type,
    payload?.componentType,
  ].filter((value): value is string => typeof value === 'string' && value.length > 0)
}

function itemIdentityValues(sheet: SChecklistRenderSheet): string[] {
  const payload = sheet.html_data
  return [sheet.item_id, payload?.item_id].filter(
    (value): value is string => typeof value === 'string' && value.length > 0,
  )
}

function payloadMatches(
  payload: Record<string, any> | null | undefined,
  componentType: SChecklistComponentType,
  sheetName?: string,
): payload is Record<string, any> {
  if (!payload || typeof payload !== 'object') return false
  const identities = [payload.component_type, payload.componentType]
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
  if (identities.length === 0 || identities.some((value) => value !== componentType)) return false

  const expectedSheet = sheetName || ''
  if (expectedSheet && payload.sheet_name !== expectedSheet) return false

  const expectedItemId = sChecklistItemIds[componentType]
  if (expectedItemId && payload.item_id !== expectedItemId) return false
  return true
}

/**
 * 按后端身份字段选择 S-checklist sheet。
 *
 * 这里故意不使用 sheet 名 substring：同一工作簿可能同时存在相似中文标题，
 * componentType 是路由身份，item_id 是 D3.2 保存身份，sheetName 仅用于同一
 * componentType（S17-1/2/3）内的精确页签选择。
 */
export function resolveSChecklistSheet(
  sheets: readonly SChecklistRenderSheet[],
  componentType: SChecklistComponentType,
  sheetName?: string,
): SChecklistRenderSheet | null {
  const expectedItemId = sChecklistItemIds[componentType]
  const expectedSheet = sheetName || ''

  return sheets.find((sheet) => {
    const identities = identityValues(sheet)
    if (identities.length === 0 || identities.some((value) => value !== componentType)) return false

    const itemIds = itemIdentityValues(sheet)
    if (expectedItemId) {
      if (itemIds.length === 0 || itemIds.some((value) => value !== expectedItemId)) {
        return false
      }
    }

    if (expectedSheet && sheet.sheet_name !== expectedSheet) return false
    return true
  }) ?? null
}

/**
 * 优先消费 GtWpRenderer 已经按当前 active sheet 投影的 htmlData；
 * 独立挂载时再从 render-config 按 componentType/item identity 解析。
 */
export function resolveSChecklistHtmlData(options: {
  response?: any
  htmlData?: Record<string, any> | null
  componentType: SChecklistComponentType
  sheetName?: string
}): Record<string, any> | null {
  const { response, htmlData, componentType, sheetName } = options
  if (payloadMatches(htmlData, componentType, sheetName)) return htmlData

  const sheet = resolveSChecklistSheet(
    getRenderConfigSheets(response),
    componentType,
    sheetName,
  )
  return sheet?.html_data && typeof sheet.html_data === 'object'
    ? sheet.html_data
    : null
}

export async function loadSChecklistHtmlData(options: {
  wpId: string
  htmlData?: Record<string, any> | null
  componentType: SChecklistComponentType
  sheetName?: string
}): Promise<Record<string, any> | null> {
  const fromProps = resolveSChecklistHtmlData(options)
  if (fromProps) return fromProps

  const response = await http.get(
    `/api/workpapers/${options.wpId}/render-config`,
    { _silent: true } as any,
  )
  return resolveSChecklistHtmlData({ ...options, response })
}
