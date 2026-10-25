/**
 * 差额分录面板的纯逻辑（spec consol-tree-three-code-autobuild 任务 10.5）：状态机按钮、表单校验、请求体。
 *
 * 与后端同一规则：
 * - 状态机（elimination_service.change_review_status）：草稿/已驳回可修改、删除、提交审批；
 *   草稿/待审批可审批、驳回；已审批不可改删；
 * - 归属：合并差额节点 ⇒ `branch_entity_code = null`；母分差额节点 ⇒ 该企业代码（需求 6.1）；
 * - 借贷必须平衡且至少一行有金额；有金额的行必须有科目（与 `_serialize_lines` 一致）。
 */
import Decimal from 'decimal.js'
import type {
  ConsolTreeNode,
  EliminationEntry,
  EliminationEntryPayload,
  EliminationReviewStatus,
  EliminationType,
  NodeAmountRow,
} from '@/services/consolidationApi'

export const TYPE_OPTIONS: ReadonlyArray<{ value: EliminationType; label: string }> = [
  { value: 'internal_ar_ap', label: '内部往来' },
  { value: 'internal_trade', label: '内部交易' },
  { value: 'unrealized_profit', label: '未实现利润' },
  { value: 'equity', label: '权益抵销' },
  { value: 'other', label: '其他调整' },
]

const STATUS: Record<EliminationReviewStatus, { label: string; type: 'info' | 'warning' | 'success' | 'danger' }> = {
  draft: { label: '草稿', type: 'info' },
  pending_review: { label: '待审批', type: 'warning' },
  approved: { label: '已审批', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
}

export function typeLabel(value: string | null | undefined): string {
  return TYPE_OPTIONS.find((o) => o.value === value)?.label || value || ''
}

export function statusLabel(value: string | null | undefined): string {
  return STATUS[value as EliminationReviewStatus]?.label || value || ''
}

export function statusTagType(value: string | null | undefined): 'info' | 'warning' | 'success' | 'danger' {
  return STATUS[value as EliminationReviewStatus]?.type || 'info'
}

type WithStatus = Pick<EliminationEntry, 'review_status'>

export function canEdit(entry: WithStatus): boolean {
  return entry.review_status === 'draft' || entry.review_status === 'rejected'
}

export function canSubmit(entry: WithStatus): boolean {
  return entry.review_status === 'draft' || entry.review_status === 'rejected'
}

export function canApprove(entry: WithStatus): boolean {
  return entry.review_status === 'draft' || entry.review_status === 'pending_review'
}

/** 撤销审批：已审批 → 草稿（合并锁定时后端 423 拒绝），撤销后合并数随推送回到审批前 */
export function canRevoke(entry: WithStatus): boolean {
  return entry.review_status === 'approved'
}

/** 已审批 ⇒ 计入合并数（只有已审批分录参与计算） */
export function isCounted(entry: WithStatus): boolean {
  return entry.review_status === 'approved'
}

/** 表单明细行（金额以字符串编辑，提交前按 Decimal 解析） */
export interface FormLine {
  account_code: string
  account_name: string
  debit_amount: string
  credit_amount: string
}

export function emptyLine(): FormLine {
  return { account_code: '', account_name: '', debit_amount: '', credit_amount: '' }
}

const AMOUNT_RE = /^-?\d+(\.\d{1,2})?$/

function parseAmount(raw: string | number | null | undefined): Decimal | null {
  const text = String(raw ?? '').replace(/[,，\s]/g, '')
  if (!text) return new Decimal(0)
  if (!AMOUNT_RE.test(text)) return null
  return new Decimal(text)
}

/**
 * 金额的规范文本（两位小数，元）：用于请求体、输入框回填与传给 GtAmountCell 的原值。
 * 不是展示格式 —— 展示由 GtAmountCell 按单位偏好处理；这里若套展示格式会把「万元」等写进请求体。
 */
function toCents(value: Decimal | string | number | null | undefined): string {
  const d = value instanceof Decimal ? value : new Decimal(value || 0)
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- 规范化金额文本（请求体/回填），非展示格式
  return d.toFixed(2)
}

export interface LineCheck {
  debit: Decimal
  credit: Decimal
  /** 空串 = 可保存；否则为中文原因 */
  error: string
}

/** 借贷合计与可保存判定（有金额无科目、金额格式错、没有金额、借贷不平衡都拦下） */
export function validateLines(lines: FormLine[]): LineCheck {
  let debit = new Decimal(0)
  let credit = new Decimal(0)
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const dr = parseAmount(line.debit_amount)
    const cr = parseAmount(line.credit_amount)
    if (dr === null || cr === null) return { debit, credit, error: `第 ${i + 1} 行金额格式不正确（最多两位小数）` }
    const hasAmount = !dr.isZero() || !cr.isZero()
    if (hasAmount && !line.account_code.trim()) return { debit, credit, error: `第 ${i + 1} 行有金额但没有科目` }
    debit = debit.plus(dr)
    credit = credit.plus(cr)
  }
  if (debit.isZero() && credit.isZero()) return { debit, credit, error: '请至少填写一行金额' }
  if (!debit.equals(credit)) return { debit, credit, error: '借贷不平衡' }
  return { debit, credit, error: '' }
}

/**
 * 分录的归属差额节点（表单「归属节点」的一个选项）：与明细表接口的 `hosted_nodes` 同形。
 * `branch_entity_code`：null = 合并差额；企业代码 = 该企业的母分差额（需求 6.1 / ADR-CTREE-003）。
 */
export interface ElimTarget {
  node_key: string
  label: string
  branch_entity_code: string | null
}

/** 企业树差额节点 → 归属选项 */
export function elimTargetOf(
  node: Pick<ConsolTreeNode, 'node_key' | 'role' | 'company_code'>
    & Partial<Pick<ConsolTreeNode, 'display_name' | 'company_name'>>,
): ElimTarget {
  return {
    node_key: node.node_key,
    label: node.display_name || node.company_name || node.company_code || node.node_key,
    branch_entity_code: node.role === 'branch_elim' ? node.company_code : null,
  }
}

/** 已有分录对应的归属选项（按 branch_entity_code 匹配；空串与 null 同为合并差额）；不在选项里 ⇒ null */
export function findTarget(
  targets: ReadonlyArray<ElimTarget>, branchEntityCode: string | null | undefined,
): ElimTarget | null {
  const want = (branchEntityCode || '').trim() || null
  return targets.find((t) => ((t.branch_entity_code || '').trim() || null) === want) || null
}

/**
 * 分录请求体：只提交有科目的行；归属由所选节点决定（合并差额 ⇒ null，母分差额 ⇒ 该企业代码）。
 * 修改时 `forUpdate` 为真：不带 project_id / year（后端不接受改这两项）。
 */
export function buildEntryPayload(
  target: Pick<ElimTarget, 'branch_entity_code'>,
  form: { entry_type: EliminationType; description: string; lines: FormLine[] },
  ctx: { projectId: string; year: number | null; forUpdate?: boolean },
): EliminationEntryPayload {
  const lines = form.lines
    .filter((l) => l.account_code.trim())
    .map((l) => ({
      account_code: l.account_code.trim(),
      account_name: l.account_name.trim() || null,
      debit_amount: toCents(parseAmount(l.debit_amount)),
      credit_amount: toCents(parseAmount(l.credit_amount)),
    }))
  const payload: EliminationEntryPayload = {
    entry_type: form.entry_type,
    description: form.description.trim() || null,
    branch_entity_code: (target.branch_entity_code || '').trim() || null,
    lines,
  }
  if (!ctx.forUpdate) {
    payload.project_id = ctx.projectId
    payload.year = ctx.year ?? undefined
  }
  return payload
}

/** 已保存分录 → 表单行（修改时回填） */
export function linesToForm(entry: Pick<EliminationEntry, 'lines'>): FormLine[] {
  const lines = (entry.lines || []).map((l) => ({
    account_code: l.account_code || '',
    account_name: l.account_name || '',
    debit_amount: Number(l.debit_amount) ? toCents(l.debit_amount) : '',
    credit_amount: Number(l.credit_amount) ? toCents(l.credit_amount) : '',
  }))
  while (lines.length < 2) lines.push(emptyLine())
  return lines
}

/** 节点金额行：按自然方向归一后的调整 / 抵销净额（贷方性质科目取贷减借） */
export function signedNet(row: NodeAmountRow, column: 'adjustment' | 'elimination'): string {
  const dr = new Decimal(row[`${column}_debit`] || 0)
  const cr = new Decimal(row[`${column}_credit`] || 0)
  return toCents(row.direction === 'credit' ? cr.minus(dr) : dr.minus(cr))
}

/** 穿透接口的分录行（下级合并项目承载的差额节点只读查看用）→ 列表行 */
export function normalizeDrillRow(row: Record<string, any>): EliminationEntry {
  return {
    id: String(row.entry_id),
    project_id: String(row.host_project_id || ''),
    entry_no: row.entry_no || '',
    year: row.year ?? 0,
    entry_type: row.entry_type,
    description: row.description ?? null,
    related_company_codes: Array.isArray(row.related_company_codes) ? row.related_company_codes : null,
    branch_entity_code: row.branch_entity_code ?? null,
    review_status: row.review_status,
    debit_amount: row.debit_amount,
    credit_amount: row.credit_amount,
    lines: Array.isArray(row.lines) ? row.lines : [],
  }
}
