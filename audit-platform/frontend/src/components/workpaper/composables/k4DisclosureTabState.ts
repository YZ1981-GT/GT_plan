/**
 * K4 其他流动负债披露表：表单初值、读回、自动取数与同步快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `K4TabDisclosureListed` / `K4TabDisclosureSoe` 原先在组件里内联「默认表 → onMounted 读已保存的表（loadSavedData）+ 从 K4-1 自动取数
 * （applyAutoFill）→ 同步时拼载荷行与说明」；抽成本模块的纯函数后，Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。
 * 读回 / 取数就地改传入的行（Tab 传 reactive 数组，界面照常响应）；提示、AI、事件订阅、持久化留在 Tab。
 *
 * 🔴 国企读回原只读 `saved?.value`：宿主 checklist 回复只有 `remark` / `conclusion`（Tab 保存经 emit('save') 落 `remark`），`value` 恒
 *    undefined ⇒ 已存的四段从不读回（重开即默认空表；下次编辑把这一段的空表写回，覆盖已存数据）。现读 `remark`（兼容旧 `value`）。
 */
import type { K4BondContRow, K4BondRow, K4DisclosureRow, K4SyncPayloadExtras } from './k4NoteSectionMap'

/** 底稿回复（Tab 的 props.allResponses / 离屏框架读回的回复，两种来源同口径） */
export type K4DisclosureResponses = ReadonlyMap<string, any>

// ═══ 国企（八、48）═══

export interface K4SoeDisclosureRow {
  rowIdx: number
  item: string
  endBalance: number
  beginBalance: number
  remark: string
  isFormula?: boolean
  isAutoFilled?: boolean
}

export interface K4SoeDisclosureSection {
  id: string
  title: string
  rows: K4SoeDisclosureRow[]
  hasTextArea: boolean
  textContent: string
}

function makeRow(item: string, idx: number, opts?: Partial<K4SoeDisclosureRow>): K4SoeDisclosureRow {
  return {
    rowIdx: idx, item, endBalance: 0, beginBalance: 0, remark: '',
    ...opts,
  }
}

/** 国企四段初值：14 行分配到「一、按项目性质分类 / 二、增减变动说明」两张表，另两段只有文字 */
export function createK4SoeDisclosureSections(): K4SoeDisclosureSection[] {
  // 一、按项目性质分类（~9行）
  const natureItems = [
    '预提费用', '待转销项税额', '代扣代缴款项', '待认证进项税额',
    '应付短期利息', '其他', '合计',
  ]
  const natureRows = natureItems.map((item, i) => makeRow(item, i, { isFormula: item === '合计' }))

  // 二、增减变动说明（~3行）
  const changeItems = ['本期增加', '本期减少', '净变动']
  const changeRows = changeItems.map((item, i) => makeRow(item, i, { isFormula: item === '净变动' }))

  return [
    { id: 'nature', title: '一、按项目性质分类', rows: natureRows, hasTextArea: true, textContent: '' },
    { id: 'change', title: '二、增减变动说明', rows: changeRows, hasTextArea: true, textContent: '' },
    { id: 'k7-reconcile', title: '三、政府补助与K7递延收益勾稽', rows: [], hasTextArea: true, textContent: '' },
    { id: 'other', title: '四、其他披露事项', rows: [], hasTextArea: true, textContent: '' },
  ]
}

function soeResponseNumber(responses: K4DisclosureResponses, key: string): number {
  const item = responses.get(key)
  if (!item) return 0
  const val = item.value ?? item
  return typeof val === 'number' ? val : parseFloat(val) || 0
}

/** 国企：按性质合计行从 K4-1 自动取数（Tab onMounted 与审定 / 调整事件；就地改行，不进载荷 —— 合计由 builder 重算） */
export function applyK4SoeAutoFill(responses: K4DisclosureResponses, sections: K4SoeDisclosureSection[]): void {
  const endBal = soeResponseNumber(responses, 'K4-1-liability-end')
  const beginBal = soeResponseNumber(responses, 'K4-1-liability-begin')

  // 按性质合计行自动填充
  const natureSection = sections.find(s => s.id === 'nature')
  if (natureSection) {
    const totalRow = natureSection.rows.find(r => r.item === '合计')
    if (totalRow) {
      totalRow.endBalance = endBal
      totalRow.beginBalance = beginBal
      totalRow.isAutoFilled = true
    }
  }
}

/** 国企：读已保存的四段（Tab onMounted 的 loadSavedData；就地改段）；缺失 / 损坏的段保持初值 */
export function loadK4SoeDisclosureState(responses: K4DisclosureResponses, sections: K4SoeDisclosureSection[]): void {
  for (let i = 0; i < sections.length; i++) {
    const section = sections[i]
    const saved = responses.get(`K4-disc-soe-${section.id}`)
    const raw = saved?.remark ?? saved?.value ?? null
    if (raw) {
      try {
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
        if (parsed.rows?.length) section.rows = parsed.rows
        if (parsed.textContent) section.textContent = parsed.textContent
      } catch { /* ignore */ }
    }
  }
}

/** 国企同步快照 → `buildK4SyncPayload('soe', wpId, rows, narrative)` */
export function buildK4SoeDisclosureSnapshot(
  sections: readonly K4SoeDisclosureSection[],
): { rows: K4DisclosureRow[]; narrative: string } {
  // 只推「一、按项目性质分类」段：`二、增减变动说明` 的本期增加/减少/净变动不是科目行，
  // 混进同一张附注表会变成假科目（原 `sections.flatMap` 把两段压进一张表）。
  // 增减变动说明随 `_note_texts` 走文字。
  const natureSection = sections.find(s => s.id === 'nature')
  const rows = (natureSection?.rows ?? [])
    .filter(r => !r.isFormula)
    .map(r => ({ project: r.item, endAmount: r.endBalance ?? 0, priorAmount: r.beginBalance ?? 0 }))
  const narrative = sections.filter(s => s.textContent).map(s => s.textContent).join('\n\n')
  return { rows, narrative }
}

// ═══ 上市（五、44）═══

export interface K4ListedSummaryRow { item: string; endBalance: number; beginBalance: number; remark: string; isTotal?: boolean }
export interface K4ListedBondRow { name: string; faceValue: number; couponRate: number; issueDate: string; term: string; issueAmount: number }
export interface K4ListedBondContRow { name: string; beginBalance: number; issued: number; interestAccrued: number; premiumAmort: number; repaid: number; defaulted: string }
export interface K4ListedGrantRow { item: string; beginBalance: number; increase: number; decrease: number; reason: string }

const SUMMARY_TYPES = ['短期应付债券', '政府补助', '待转销项税额', '应付退货款']

/** 上市汇总表初值（4 类型 + 合计行） */
export function createK4ListedSummaryRows(): K4ListedSummaryRow[] {
  return [
    ...SUMMARY_TYPES.map(item => ({ item, endBalance: 0, beginBalance: 0, remark: '' })),
    { item: '合计', endBalance: 0, beginBalance: 0, remark: '', isTotal: true },
  ]
}

export function recalcK4ListedSummaryTotal(summaryRows: K4ListedSummaryRow[]): void {
  const total = summaryRows.find(r => r.isTotal)
  if (!total) return
  total.endBalance = summaryRows.filter(r => !r.isTotal).reduce((s, r) => s + (r.endBalance || 0), 0)
  total.beginBalance = summaryRows.filter(r => !r.isTotal).reduce((s, r) => s + (r.beginBalance || 0), 0)
}

/** 上市读回复数值（remark → conclusion → 旧 value） */
export function k4ListedResponseNumber(responses: K4DisclosureResponses, key: string): number {
  const item = responses.get(key)
  if (!item) return 0
  const val = item.remark ?? item.conclusion ?? item.value ?? item
  const n = typeof val === 'number' ? val : parseFloat(val)
  return Number.isFinite(n) ? n : 0
}

/** 上市：汇总表自动取数（K4-1 审定合计只作合计行备注参考；重算合计行。就地改行，合计行不进载荷） */
export function applyK4ListedAutoFill(responses: K4DisclosureResponses, summaryRows: K4ListedSummaryRow[]): void {
  const auditedTotal = k4ListedResponseNumber(responses, 'K4-1-audited-total')
  const bondRow = summaryRows.find(r => r.item === '短期应付债券')
  // 仅在用户未手工填写时用审定合计作为参考（填到合计的备注提示）
  if (auditedTotal && bondRow && !bondRow.endBalance && summaryRows.filter(r => !r.isTotal).every(r => !r.endBalance)) {
    const total = summaryRows.find(r => r.isTotal)
    if (total) total.remark = `K4-1审定合计参考：${auditedTotal.toLocaleString('zh-CN')}`
  }
  recalcK4ListedSummaryTotal(summaryRows)
}

function parseListed(responses: K4DisclosureResponses, key: string): any {
  const saved = responses.get(key)
  const raw = saved?.remark ?? saved?.conclusion ?? saved?.value ?? null
  if (!raw) return null
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw } catch { return null }
}

/** 已存的三张明细表（null = 没有已存 / 不是数组，调用方保持原值）与说明 */
export interface K4ListedSavedTables {
  bondRows: K4ListedBondRow[] | null
  bondContRows: K4ListedBondContRow[] | null
  grantRows: K4ListedGrantRow[] | null
  noteText: string
}

/** 上市：读已保存的表（Tab onMounted 的 loadSavedData）：汇总表按项目名就地回填并重算合计，三张明细表与说明由调用方赋值 */
export function loadK4ListedDisclosureState(
  responses: K4DisclosureResponses,
  summaryRows: K4ListedSummaryRow[],
): K4ListedSavedTables {
  const s = parseListed(responses, 'K4-disc-listed-summary')
  if (Array.isArray(s) && s.length) {
    for (const saved of s) {
      const target = summaryRows.find(r => r.item === saved.item)
      if (target) { target.endBalance = saved.endBalance || 0; target.beginBalance = saved.beginBalance || 0; target.remark = saved.remark || '' }
    }
  }
  const b = parseListed(responses, 'K4-disc-listed-bonds')
  const bc = parseListed(responses, 'K4-disc-listed-bond-cont')
  const g = parseListed(responses, 'K4-disc-listed-grants')
  const note = responses.get('K4-disc-listed-note')
  recalcK4ListedSummaryTotal(summaryRows)
  return {
    bondRows: Array.isArray(b) ? b : null,
    bondContRows: Array.isArray(bc) ? bc : null,
    grantRows: Array.isArray(g) ? g : null,
    noteText: (note?.remark ?? note?.conclusion ?? note?.value ?? '') || '',
  }
}

/** 上市同步快照 → `buildK4SyncPayload('listed', wpId, rows, narrative, extras)`（合计行不推，builder 重算） */
export function buildK4ListedDisclosureSnapshot(src: {
  summaryRows: readonly K4ListedSummaryRow[]
  noteText: string
  bondRows: readonly K4BondRow[]
  bondContRows: readonly K4BondContRow[]
}): { rows: K4DisclosureRow[]; narrative: string; extras: K4SyncPayloadExtras } {
  const rows = src.summaryRows.filter(r => !r.isTotal).map(r => ({ project: r.item, endAmount: r.endBalance ?? 0, priorAmount: r.beginBalance ?? 0 }))
  // 债券明细/续表为条件表：有行才进 sub_table_data（columns 由 builder 走同一判据配对）
  return { rows, narrative: src.noteText, extras: { bondRows: src.bondRows, bondContRows: src.bondContRows } }
}
