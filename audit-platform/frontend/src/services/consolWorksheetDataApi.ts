/**
 * 合并工作底稿数据存储 API
 * 通用 JSON 存储，支持所有 16 张表的保存/加载
 */
import http from '@/utils/http'

export interface WorksheetDataResponse {
  project_id: string
  year: number
  sheet_key: string
  data: Record<string, any>
  updated_at?: string
}

/** 加载某张表的数据 */
export async function loadWorksheetData(
  projectId: string, year: number, sheetKey: string
): Promise<Record<string, any>> {
  try {
    const { data } = await http.get(
      `/api/consol-worksheet-data/${projectId}/${year}/${sheetKey}`,
      { validateStatus: (s: number) => s < 600 }
    )
    const result = data?.data ?? data
    return result?.data || {}
  } catch {
    return {}
  }
}

/** 保存某张表的数据 */
export async function saveWorksheetData(
  projectId: string, year: number, sheetKey: string, sheetData: Record<string, any>
): Promise<boolean> {
  try {
    await http.put(
      `/api/consol-worksheet-data/${projectId}/${year}/${sheetKey}`,
      { sheet_key: sheetKey, data: sheetData },
      { validateStatus: (s: number) => s < 600 }
    )
    return true
  } catch {
    return false
  }
}

/** 批量加载项目所有表的数据 */
export async function loadAllWorksheetData(
  projectId: string, year: number
): Promise<Record<string, Record<string, any>>> {
  try {
    const { data } = await http.get(
      `/api/consol-worksheet-data/${projectId}/${year}`,
      { validateStatus: (s: number) => s < 600 }
    )
    const items = data?.data ?? data ?? []
    const result: Record<string, Record<string, any>> = {}
    if (Array.isArray(items)) {
      for (const item of items) {
        if (item.sheet_key && item.data) {
          result[item.sheet_key] = item.data
        }
      }
    }
    return result
  } catch {
    return {}
  }
}
