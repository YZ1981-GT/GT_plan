/**
 * useD2DisclosureImportExport — D2 附注披露页导入导出（多工作表工作簿）
 *
 * 后端：`backend/app/routers/wp_render_strategies/_d2_disclosure_import_export.py`
 *   POST /api/workpapers/{wpId}/d2/export-template?sheet=D2-disc-{listed|soe}
 *   POST /api/workpapers/{wpId}/d2/export-data?sheet=D2-disc-{listed|soe}
 *   POST /api/workpapers/{wpId}/d2/import-data?sheet=D2-disc-{listed|soe}（multipart）
 *
 * 🔴 必须走 axios（http）不能用原生 fetch：fetch 不带 Authorization → 401。
 * 🔴 `sheet` 是后端 Query 参数，不能塞进 FormData。
 *
 * 范围：只覆盖披露页**手工录入**的明细表与各子节说明文本；
 *      账龄披露/按计提方法分类/坏账准备变动等取数派生表与手工覆盖值不在范围。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import type { D2DisclosureVariant } from './d2NoteSectionMap'

export interface D2DisclosureImportResult {
  rowCount: number
  fieldCount: number
  tables?: Record<string, number>
  notes?: number
  warning?: string
  warnings?: string[]
}

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

export function d2DisclosureSheetParam(variant: D2DisclosureVariant): string {
  return `D2-disc-${variant}`
}

/** 解析 Content-Disposition（优先 RFC5987 filename*=UTF-8''，回退 filename=""） */
export function parseFilenameFromHeader(header: string | null | undefined, fallback: string): string {
  if (!header) return fallback
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim())
    } catch {
      return star[1].trim()
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain?.[1]?.trim() || fallback
}

function downloadBlob(data: BlobPart, filename: string): void {
  const blob = new Blob([data], { type: XLSX_MIME })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function useD2DisclosureImportExport(options: {
  wpId: Ref<string>
  variant: D2DisclosureVariant
}) {
  const { wpId, variant } = options
  const busy = ref(false)
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  const label = variant === 'soe' ? '国企' : '上市公司'
  const sheet = d2DisclosureSheetParam(variant)

  async function download(kind: 'export-template' | 'export-data'): Promise<void> {
    lastError.value = null
    busy.value = true
    try {
      const res: any = await http.post(
        `/api/workpapers/${wpId.value}/d2/${kind}`,
        null,
        { params: { sheet }, responseType: 'blob' } as any,
      )
      const fallback = `D2应收账款附注披露(${label})-${kind === 'export-template' ? '模板' : '数据'}.xlsx`
      const filename = parseFilenameFromHeader(res?.headers?.['content-disposition'], fallback)
      downloadBlob(res?.data ?? res, filename)
      ElMessage.success(kind === 'export-template' ? '模板已导出' : '数据已导出')
    } catch (err: any) {
      lastError.value = err?.message || '导出失败'
      ElMessage.error(lastError.value!)
    } finally {
      busy.value = false
    }
  }

  const exportTemplate = () => download('export-template')
  const exportData = () => download('export-data')

  async function importData(file: File): Promise<D2DisclosureImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      const form = new FormData()
      form.append('file', file)
      const res: any = await http.post(
        `/api/workpapers/${wpId.value}/d2/import-data`,
        form,
        { params: { sheet } } as any,
      )
      const payload = res?.data?.data ?? res?.data ?? res
      const result: D2DisclosureImportResult = payload?.data ?? payload
      const msgs = [
        `成功导入 ${result?.rowCount ?? 0} 行`,
        result?.notes ? `${result.notes} 段说明` : '',
      ].filter(Boolean)
      const extra = [result?.warning, ...(result?.warnings ?? [])].filter(Boolean)
      ElMessage.success({
        message: extra.length > 0 ? `${msgs.join('，')}（${extra.join('；')}）` : msgs.join('，'),
        duration: extra.length > 0 ? 6000 : 3000,
      })
      return result
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.message
      lastError.value = detail || err?.message || '导入失败'
      ElMessage.error(lastError.value!)
      return null
    } finally {
      importing.value = false
    }
  }

  return { busy, importing, lastError, exportTemplate, exportData, importData }
}

export default useD2DisclosureImportExport
