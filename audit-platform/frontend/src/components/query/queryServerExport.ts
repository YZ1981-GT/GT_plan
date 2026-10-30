/**
 * queryServerExport.ts — 业务视图「导出全部」（advanced-query-linkage-closure 任务 28 / 29，R8.1~R8.3，AQ-20 前端）
 *
 * 弹窗与页面版共用：按当前查询（条件、列、排序）调 `POST /api/custom-query/export`，服务端流式导出全量结果（数据行数 =
 * total，另附「查询说明」sheet），表头用界面所见的中文列名（`headers`，键为列键），文件名取响应头（RFC 5987）。
 * 「导出当前页」仍是前端 `exportQueryResultToXlsx`（次选项）。失败时错误体是 Blob：调用方先 `readBlobErrorBody` 再
 * `describeQueryError`（超限 400、并发 429 `EXPORT_BUSY` 都显示后端中文原因）。
 */
import { downloadFile } from '@/utils/http'
import { customQuery as P_cq } from '@/services/apiPaths'
import { sanitizeExportName } from './queryExport'

/** 导出请求体：业务视图请求体（`buildBusinessPayload`，不含翻页）+ 中文表头 + 文件名 */
export function buildExportBody(
  payload: Record<string, unknown>, headers: Record<string, string>, fileName: string,
): Record<string, unknown> {
  const body: Record<string, unknown> = { ...payload, file_name: sanitizeExportName(fileName) || '高级查询' }
  delete body.limit // 导出不分页：limit / offset 不参与（后端同样忽略）
  delete body.offset
  if (Object.keys(headers).length) body.headers = { ...headers }
  return body
}

/** 发起「导出全部」并保存文件（文件名以响应头为准，取不到时用 `{fileName}.xlsx`） */
export async function exportAllQueryRows(body: Record<string, unknown>): Promise<void> {
  const name = typeof body.file_name === 'string' && body.file_name ? body.file_name : '高级查询'
  await downloadFile(P_cq.export, { method: 'post', data: body, fileName: `${name}.xlsx`, silent: true })
}
