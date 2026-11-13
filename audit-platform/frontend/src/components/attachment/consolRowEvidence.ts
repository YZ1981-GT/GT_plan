/**
 * 合并底稿行内证据：稳定 sheet/row/cell 身份（批 6 / ADR-CRW-006 / 任务 6.3）
 *
 * 合并薄壳（`A3-CONSOL` 底稿）复用通用 `EvidenceLink` 与证据端点：证据按壳的 `working_paper_id`
 * 挂，位置用稳定的 `node:<key>/row:<identity>/col:<identity>` 写进 `cell_ref`，`sheet_name` 放
 * 合并表键。**绝不只用行号**——插入 / 删除行不改变其它行的身份串，证据不会漂到相邻行，
 * 因此**不需要** `rowEvidence.ts` 里 `shiftIndexedRowEvidence` 那种删行后前移附件的补偿。
 *
 * 身份构造的权威真源是后端 `workpaper-shell/evidence-target` 端点（身份派生是纯函数，不写库）：
 * 它按合并权威源（consol_trial / consol_report / consol_note_data / consol_worksheet_data）规则
 * 从行业务键派生稳定身份，并给出壳的 `wp_id`（未建壳时为 null，首次上传前先调 `ensure`）。
 * 显式稳定行 id（科目码 / 行自带 id）时前端也能直接拼 `id:` 串，省一次往返。
 */
import http from '@/utils/http'
import { consolidation as P_consol } from '@/services/apiPaths'
import { attachments as P_att } from '@/services/apiPaths'
import { invalidateWpEvidenceLinks } from '@/composables/useWpEvidenceLinks'

export type ConsolSheetType = 'trial' | 'report' | 'note' | 'worksheet'

export interface ConsolEvidenceTarget {
  /** 薄壳底稿 id（证据挂这里）；壳未创建时为 null */
  wpId: string | null
  shellExists: boolean
  /** 合并表键：consol_trial / consol_report / sheet_key / section_id */
  sheetName: string
  /** 稳定身份串 node:<key>/row:<identity>/col:<identity>（插删行不漂移） */
  cellRef: string
  nodeKey: string
  rowIdentity: string | null
  col: string | null
}

function unwrap(body: any): any {
  if (body && typeof body === 'object' && 'code' in body && 'data' in body) return body.data
  return body
}

/** cell_ref 段转义：`%` `/` `:` 与后端一致，解析才能无歧义还原。 */
function sanitizeSegment(value: string): string {
  return value.replace(/%/g, '%25').replace(/\//g, '%2F').replace(/:/g, '%3A')
}

/**
 * 有稳定行 id（科目码 / 行自带 id）时，前端直接拼 `node:<key>/row:id:<值>[/col:<列>]`，无需后端往返。
 * 与后端 `build_cell_ref(node, row_identity="id:"+id, col)` 逐字节一致。
 */
export function consolCellRefWithRowId(
  nodeKey: string,
  rowId: string,
  col?: string | null,
): string {
  const parts = [`node:${sanitizeSegment(nodeKey)}`]
  if (rowId) parts.push(`row:${sanitizeSegment('id:' + rowId)}`)
  if (col) parts.push(`col:${sanitizeSegment(col)}`)
  return parts.join('/')
}

/** 合并试算表行身份 = 科目码（天然稳定）。 */
export function consolTrialCellRef(standardAccountCode: string, col?: string | null): string {
  return consolCellRefWithRowId('consol_trial', standardAccountCode, col)
}

/** 合并报表行身份 = 报表行键（稳定）。 */
export function consolReportCellRef(lineKey: string, col?: string | null): string {
  return consolCellRefWithRowId('consol_report', lineKey, col)
}

/**
 * 解析证据坐标：权威身份来自后端（无稳定行 id 时按行内容派生摘要，前端不自算 SHA）。
 * 返回 `wpId` + `sheetName` + `cellRef`，调用方把它们交给通用证据端点上传 / 链接 / 小眼睛。
 * 失败抛出，调用方 `handleApiError`。
 */
export async function resolveConsolEvidenceTarget(params: {
  projectId: string
  year: number
  sheetType: ConsolSheetType
  /** 合并表键：sheet_key / consol_trial / consol_report / section_id */
  nodeKey: string
  /** 行的业务标识字段（无稳定 id 时据此派生稳定身份；不含数组下标） */
  rowFields?: Record<string, unknown> | null
  /** 显式稳定行 id（科目码 / 行自带 id）；给定则优先 */
  rowIdentity?: string | null
  col?: string | null
}): Promise<ConsolEvidenceTarget> {
  const { projectId, year } = params
  if (!projectId || !(year >= 0)) throw new Error('缺少项目或年度，无法解析合并证据坐标')
  const res = await http.post(
    P_consol.evidenceTarget(projectId, year),
    {
      sheet_type: params.sheetType,
      node_key: params.nodeKey,
      row_fields: params.rowFields ?? null,
      row_identity: params.rowIdentity ?? null,
      col: params.col ?? null,
    },
    { _silent: true } as any,
  )
  const body = unwrap(res?.data) || {}
  return {
    wpId: body.wp_id ?? null,
    shellExists: Boolean(body.shell_exists),
    sheetName: body.sheet_name ?? params.nodeKey,
    cellRef: body.cell_ref ?? '',
    nodeKey: body.node_key ?? params.nodeKey,
    rowIdentity: body.row_identity ?? null,
    col: body.col ?? null,
  }
}

/**
 * 壳未创建时幂等建占位壳（edit 级），拿到 `wpId` 后才能上传证据。返回壳的 `working_paper_id`。
 * readonly 用户查看既有证据不需要调它。
 */
export async function ensureConsolShell(projectId: string, year: number): Promise<string> {
  const res = await http.post(P_consol.workpaperShellEnsure(projectId, year), {}, { _silent: true } as any)
  const body = unwrap(res?.data) || {}
  const wpId = body.working_paper_id
  if (!wpId) throw new Error('创建合并底稿壳失败')
  return wpId
}

/** 识别 / 上传 / 链接成功后：本壳证据仓失效重取，同页所有行内小眼睛立即看到新文件。 */
export function refreshConsolRowEvidence(wpId: string | null | undefined, projectId: string | null | undefined): void {
  if (!wpId || !projectId) return
  void invalidateWpEvidenceLinks(projectId, wpId).catch(() => [])
}

/**
 * 把证据表单带上合并行级位置（表页键 + 稳定 cell_ref）。
 * 与通用 `rowEvidence.appendRowEvidence` 不同：合并身份已是无漂移稳定串，直接带 `sheet_name` + `cell_ref`，
 * 不走 `evidence_sheet` / `evidence_cell`（那是底稿 OCR 端点的字段）。
 */
export function appendConsolEvidence(form: FormData, sheetName: string, cellRef: string): void {
  if (sheetName) form.append('sheet_name', sheetName)
  if (cellRef) form.append('cell_ref', cellRef)
}

/** 证据链接 API 路径（给合并壳建 / 删链接，复用通用证据端点）。 */
export const consolEvidenceApi = {
  links: (projectId: string, wpId: string) => P_att.evidenceLinks(projectId, wpId),
  linkCreate: (projectId: string, wpId: string) => P_att.evidenceLinkCreate(projectId, wpId),
  upload: (projectId: string, wpId: string) => P_att.evidenceUpload(projectId, wpId),
}
