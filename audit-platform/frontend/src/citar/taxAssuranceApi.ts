/**
 * 鉴证报告四个菜单的后端接口（spec citar-assurance-report-menus）。
 * 金额值格式与税审底稿一致：{n} 数字（字符串保精度）/ {s} 文字 / {e} 错误 / null 空。
 */
import { api } from '@/services/apiProxy'
import { taxAssurance as P_ta } from '@/services/apiPaths'
import http, { downloadFile } from '@/utils/http'
import type { TaxValue } from '@/views/tax-workpapers/taxWorkpaperApi'

export interface ReportBodyLine {
  no: string
  item: string
  amount: TaxValue
  amount_text: string
}

export interface ReportBodyData {
  year: number
  version: number
  cover: { client: string; title: string; period: string; firm: string }
  title: string
  report_no: string
  addressee: string
  intro: string[]
  lines: ReportBodyLine[]
  closing: string[]
  signatures: string[]
  firm: string[]
  report_date: string | null
  report_date_text: string
  attachments_title: string
  attachments: string[]
  notices: string[]
}

export interface ReviewParagraph {
  row: number
  text: string
  /** 2~9 标题层级 / 文本1 / 文本2 */
  style: string
  level: number | null
  bold: boolean
  indent: [number | null, number | null]
}

export interface ReviewNotesData {
  year: number
  header: string[]
  footer: string[]
  paragraphs: ReviewParagraph[]
  notices: string[]
}

export interface FsRow {
  r: number
  label: string
  indent: number
  heading: boolean
  total: boolean
  note: string | null
  current: TaxValue
  prior: TaxValue
}

export interface FsStatement {
  key: string
  title: string
  attachment: string | null
  columns: string[]
  rows: FsRow[]
}

export interface FinancialStatementsData {
  year: number
  entity_name: string
  format: 'enterprise_system' | 'cas' | null
  format_label: string
  standard_code: string
  format_source: 'tax_return' | 'chart'
  statements: FsStatement[]
  notices: string[]
  checks: { label: string; difference: TaxValue; ok: boolean }[]
}

const params = (year: number) => ({ params: { year } })

export function fetchReportBody(projectId: string, year: number): Promise<ReportBodyData> {
  return api.get(P_ta.reportBody(projectId), params(year)) as Promise<ReportBodyData>
}

/** 预览与导出读取同一份 Word，保留模板的页眉、图片与排版。 */
export async function fetchReportBodyDocument(projectId: string, year: number): Promise<ArrayBuffer> {
  const response = await http.get<ArrayBuffer>(P_ta.reportBodyExport(projectId), {
    params: { year }, responseType: 'arraybuffer', _silent: true, _dedupe: false,
  } as any)
  return response.data
}

export function saveReportDate(projectId: string, year: number, version: number, reportDate: string | null): Promise<ReportBodyData> {
  return api.put(P_ta.reportBody(projectId), { version, report_date: reportDate }, { params: { year }, _silent: true } as any) as Promise<ReportBodyData>
}

export function fetchReviewNotes(projectId: string, year: number): Promise<ReviewNotesData> {
  return api.get(P_ta.reviewNotes(projectId), params(year)) as Promise<ReviewNotesData>
}

export function fetchFinancialStatements(projectId: string, year: number): Promise<FinancialStatementsData> {
  return api.get(P_ta.financialStatements(projectId), params(year)) as Promise<FinancialStatementsData>
}

export type TaxAssuranceExport = 'reportBodyExport' | 'reviewNotesExport' | 'taxReturnExport' | 'financialStatementsExport'

export function downloadTaxAssurance(kind: TaxAssuranceExport, projectId: string, year: number, fileName: string) {
  return downloadFile(P_ta[kind](projectId), { params: { year }, fileName })
}

/** 值 → 数字（非数字 null） */
export function numberOf(v: TaxValue | undefined): number | null {
  if (!v || !('n' in v)) return null
  const n = Number(v.n)
  return Number.isFinite(n) ? n : null
}
