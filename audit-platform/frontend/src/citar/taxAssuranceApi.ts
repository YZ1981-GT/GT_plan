/**
 * 鉴证报告四个菜单的后端接口（spec citar-assurance-report-menus）。
 * 金额值格式与税审底稿一致：{n} 数字（字符串保精度）/ {s} 文字 / {e} 错误 / null 空。
 */
import { api } from '@/services/apiProxy'
import { taxAssurance as P_ta } from '@/services/apiPaths'
import http, { downloadFile } from '@/utils/http'
import type { TaxValue } from '@/views/tax-workpapers/taxWorkpaperApi'

export interface ReportBodyLine {
  /** 底稿 1-01报告正文的行号（17~41） */
  row: number
  no: string
  item: string
  amount: TaxValue
  amount_text: string
  /** 税率行：按百分数显示与输入 */
  is_rate: boolean
  /** 手工改过（本页或底稿 1-01） */
  manual: boolean
  /** 手工改过时：按公式取自申报表的值 */
  auto: TaxValue
}

export interface ReportBodyData {
  year: number
  /** 报告日期那一行的版本 */
  version: number
  /** 摘录表金额（底稿 1-01）那一行的版本 */
  amounts_version: number
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
  /** 段落键（规则表行号 r{n}；※ 标题补的「无。」为 r{n}-none），人工修改按它存 */
  key: string
  row: number
  /** 编号 + 正文 */
  text: string
  /** 自动编号（一、/（一）/1、…） */
  number: string
  /** 正文（人工改过即人工文字） */
  body: string
  /** 按规则自动生成的正文 */
  auto_body: string
  edited: boolean
  /** 改过之后自动文字又变了（数据变化） */
  auto_changed: boolean
  /** 2~9 标题层级 / 文本1 / 文本2 */
  style: string
  level: number | null
  bold: boolean
  indent: [number | null, number | null]
}

/** 段落人工修改：text = null 即删除本段；auto = 修改时的自动正文 */
export interface ReviewEdit {
  text: string | null
  auto: string | null
}

export interface ReviewNotesData {
  year: number
  version: number
  header: string[]
  footer: string[]
  paragraphs: ReviewParagraph[]
  edits: Record<string, ReviewEdit>
  /** 被删除、本该显示的段（可恢复） */
  deleted: { key: string; row: number; auto_text: string }[]
  /** 有人工修改、但数据变化后不再显示的段（可丢弃） */
  orphans: { key: string; text: string | null; auto: string | null }[]
  notices: string[]
}

export interface FsRow {
  r: number
  /** 企业会计准则格式（平台审定报表）的行次编码 */
  row_code?: string
  label: string
  indent: number
  heading: boolean
  total: boolean
  note: string | null
  current: TaxValue
  prior: TaxValue
  /** 手工改过的列：auto = 自动算出的金额 */
  manual: Partial<Record<'current' | 'prior', { auto: TaxValue }>> | null
}

export interface FsStatement {
  key: string
  title: string
  attachment: string | null
  columns: string[]
  /** fs = 企业会计制度格式（PUT financial-statements）；report = 平台审定报表（PUT /api/reports/…/manual） */
  source: 'fs' | 'report'
  rows: FsRow[]
}

/** 问题在报表上的位置：r 为 null = 整列（如上期金额整列为空）；column 为 null = 整张表（如报表未生成） */
export interface FsTarget {
  statement: string
  r: number | null
  column: 'current' | 'prior' | null
}

export interface FinancialStatementsData {
  year: number
  /** 企业会计制度格式手工值那一行的版本 */
  version: number
  entity_name: string
  format: 'enterprise_system' | 'cas' | null
  format_label: string
  standard_code: string
  format_source: 'tax_return' | 'chart'
  statements: FsStatement[]
  notices: string[]
  /** 提示文字 → 位置（只登记能在本页表格里定位的提示） */
  notice_targets?: Record<string, FsTarget[]>
  /** 提示文字 → 源头页（页级） */
  notice_sources?: Record<string, FsSource[]>
  checks: {
    label: string
    difference: TaxValue
    ok: boolean
    column?: 'current' | 'prior'
    targets?: FsTarget[]
    /** 不平时的差额来源（spec citar-fs-issue-source-locate） */
    sources?: FsSource[]
  }[]
}

/** 差额来源的源头页：路由在 fsIssueSources.ts 一处换算；null = 没有可去的页面 */
export type FsSourcePage =
  | 'balance' | 'journal' | 'mapping' | 'trial_balance' | 'adjustments' | 'ledger_import' | 'reports' | 'statement'

export interface FsSourceRow {
  /** 客户科目（balance / journal / mapping）或标准科目（trial_balance）编码；本页手工修改为空 */
  code: string
  name: string
  /** 对差额的影响 */
  amount: TaxValue
  note: string
  /** 另给「序时账」按该科目筛选 */
  journal?: boolean
  /** page = statement：本页格子 */
  statement?: string
  r?: number
  column?: 'current' | 'prior'
}

export interface FsSource {
  kind: string
  title: string
  /** 对差额的影响（资产 − 负债和所有者权益口径）；提示类为 null */
  amount: TaxValue | null
  page: FsSourcePage | null
  rows: FsSourceRow[]
  /** 超出显示上限还有几行 */
  more: number
}

const params = (year: number) => ({ params: { year } })

export function fetchReportBody(projectId: string, year: number): Promise<ReportBodyData> {
  return api.get(P_ta.reportBody(projectId), params(year)) as Promise<ReportBodyData>
}

/** 网页预览：后端把导出的 Word 交给 OnlyOffice 转成 PDF（版式与 Word 一致）。 */
export interface ReportBodyPreview {
  pdf: ArrayBuffer
  /** OnlyOffice 服务器缺的字体（非空时字形、行距与 Word 有差异） */
  missingFonts: string[]
}

export async function fetchReportBodyPreview(projectId: string, year: number): Promise<ReportBodyPreview> {
  const response = await http.get<ArrayBuffer>(P_ta.reportBodyPreviewPdf(projectId), {
    // _silent：失败原因由页面显示（拦截器对 _silent 请求不弹提示、也不做 5xx 自动重试）
    params: { year }, responseType: 'arraybuffer', _silent: true, _dedupe: false,
  } as any)
  const header = String(response.headers?.['x-preview-missing-fonts'] ?? '')
  return {
    pdf: response.data,
    missingFonts: header.split(',').filter(Boolean).map(s => decodeURIComponent(s)),
  }
}

/** 预览失败原因：后端 503 的 message（arraybuffer 响应体按 JSON 解析）；解析不出返回空串 */
export function previewErrorReason(error: unknown): string {
  const data = (error as any)?.response?.data
  // 不用 instanceof ArrayBuffer：跨领域（iframe / jsdom）的 ArrayBuffer 构造函数不是同一个
  if (Object.prototype.toString.call(data) !== '[object ArrayBuffer]') return ''
  try {
    const body = JSON.parse(new TextDecoder().decode(data as ArrayBuffer))
    return typeof body?.message === 'string' ? body.message : ''
  } catch {
    return ''
  }
}

export function saveReportDate(projectId: string, year: number, version: number, reportDate: string | null): Promise<ReportBodyData> {
  return api.put(P_ta.reportBody(projectId), { version, report_date: reportDate }, { params: { year }, _silent: true } as any) as Promise<ReportBodyData>
}

/** 摘录表金额手工值整份替换：values = {行号: 数字 | null}；不在里面的行恢复为公式值 */
export function saveReportBodyAmounts(
  projectId: string, year: number, version: number, values: Record<string, number | null>,
): Promise<ReportBodyData> {
  return api.put(P_ta.reportBodyAmounts(projectId), { version, values }, { params: { year }, _silent: true } as any) as Promise<ReportBodyData>
}

export function fetchReviewNotes(projectId: string, year: number): Promise<ReviewNotesData> {
  return api.get(P_ta.reviewNotes(projectId), params(year)) as Promise<ReviewNotesData>
}

/** 审核说明段落人工修改整份替换；不在 edits 里的段恢复自动文字 */
export function saveReviewNotes(
  projectId: string, year: number, version: number, edits: Record<string, ReviewEdit>,
): Promise<ReviewNotesData> {
  return api.put(P_ta.reviewNotes(projectId), { version, edits }, { params: { year }, _silent: true } as any) as Promise<ReviewNotesData>
}

export function fetchFinancialStatements(projectId: string, year: number): Promise<FinancialStatementsData> {
  return api.get(P_ta.financialStatements(projectId), params(year)) as Promise<FinancialStatementsData>
}

/** 企业会计制度格式手工值整份替换：values = {表 key: {行号: {current|prior: 金额 | null}}} */
export function saveFinancialStatements(
  projectId: string, year: number, version: number,
  values: Record<string, Record<string, Partial<Record<'current' | 'prior', number | null>>>>,
): Promise<FinancialStatementsData> {
  return api.put(P_ta.financialStatements(projectId), { version, values }, { params: { year }, _silent: true } as any) as Promise<FinancialStatementsData>
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
