/**
 * useL2Adjudication — L2-1 应付利息审定表核心逻辑 composable
 *
 * 对齐致同源模板「审定表L2-1」结构（2026-07 复盘重建）：
 * - 分类行（源模板 5 类 + 优先股/永续债子行 工具1/工具2 + 其他）
 * - 双期结构：期初数(未审/账项调整/重分类/审定) + 期末数(未审/账项调整/重分类/审定)
 * - 变动分析：本期未审 vs 期初审定(变动额/率) + 本期审定 vs 期初审定(变动额/率)
 * - 原因分析（每行文本）
 * - 审计说明（增减原因 + 欠付利息原因）+ 审计结论
 * - 与经审计财报核对区（应付利息/应付股利/其他应付款 → 报表数 → 差异）
 * - 从 L2-2 明细带入（SUMIF 等价按类别聚合）
 * - TB回写（科目 2231，期末审定合计）+ EventBus 'substantive:adjudicated'
 *
 * 科目：2231 应付利息（贷方/负债类）：审定 = 未审 + 账项调整 + 重分类调整
 *
 * ⚠️ 旧版为单期 roll-forward（期初/贷方/借方/期末），与源模板双期变动分析结构不符，
 *    本次重建为源模板结构；旧 item_id 数据不再兼容（结构性纠错）。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useL2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjudicationRow {
  /** 行唯一标识 */
  rowKey: string
  /** 分类标签 */
  label: string
  /** 是否为缩进子行（工具1/工具2） */
  isSub: boolean
  /** 是否可编辑（优先股永续债汇总行/合计行不可编辑） */
  isEditable: boolean
  // ── 期初数 ──
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number // = beginUnadjusted + beginAje + beginRje
  // ── 期末数 ──
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number // = endUnadjusted + endAje + endRje
  // ── 变动分析 ──
  unadjChange: number // = endUnadjusted - beginUnadjusted
  unadjRate: number
  auditedChange: number // = endAudited - beginAudited
  auditedRate: number
  // ── 原因分析 ──
  reason: string
}

export interface UseL2AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  writebackTB: (auditedAmount: number) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 分类行定义（对齐源模板 A7~A13） */
export const SOURCE_ROWS = [
  { rowKey: 'long-term-loan', label: '分期付息到期还本的长期借款利息', isSub: false },
  { rowKey: 'corporate-bond', label: '企业债券利息', isSub: false },
  { rowKey: 'short-term-loan', label: '短期借款应付利息', isSub: false },
  { rowKey: 'preferred-perpetual', label: '划分为金融负债的优先股/永续债利息', isSub: false },
  { rowKey: 'tool1', label: '其中：工具1', isSub: true },
  { rowKey: 'tool2', label: '工具2', isSub: true },
  { rowKey: 'other', label: '其他', isSub: false },
] as const

/** 参与合计的主行（源模板 =SUM(B7:B10,B13)：4主类 + 优先股汇总 + 其他，不含工具1/工具2子行） */
const TOTAL_ROW_KEYS = ['long-term-loan', 'corporate-bond', 'short-term-loan', 'preferred-perpetual', 'other']

/** 优先股/永续债汇总行 = 工具1 + 工具2 */
const PREFERRED_SUB_KEYS = ['tool1', 'tool2']

/** item_id 前缀 */
const PREFIX = 'L2-L2-1'

/** 数值字段列表（可编辑） */
export const ADJ_NUM_FIELDS = [
  'beginUnadjusted', 'beginAje', 'beginRje',
  'endUnadjusted', 'endAje', 'endRje',
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(rowKey: string, field: string): string {
  return `${PREFIX}-${rowKey}-${field}`
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function getResponseNum(responses: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(responses.get(itemId)?.remark)
}

function getResponseStr(responses: Map<string, ChecklistResponse>, itemId: string): string {
  return responses.get(itemId)?.remark ?? ''
}

/** 变动率：期初为 0 时特殊处理（对齐源模板 IF(AND(base=0,change=0),0,IF(AND(base=0,change>0),1,change/base)) ） */
function calcRate(base: number, change: number): number {
  if (base === 0) {
    if (change === 0) return 0
    return change > 0 ? 1 : -1
  }
  return change / base
}

/** 构建一个原始（可编辑基础字段）行 —— 派生列后填 */
function buildBaseRow(
  def: { rowKey: string; label: string; isSub: boolean },
  responses: Map<string, ChecklistResponse>,
): AdjudicationRow {
  const beginUnadjusted = getResponseNum(responses, makeItemId(def.rowKey, 'beginUnadjusted'))
  const beginAje = getResponseNum(responses, makeItemId(def.rowKey, 'beginAje'))
  const beginRje = getResponseNum(responses, makeItemId(def.rowKey, 'beginRje'))
  const endUnadjusted = getResponseNum(responses, makeItemId(def.rowKey, 'endUnadjusted'))
  const endAje = getResponseNum(responses, makeItemId(def.rowKey, 'endAje'))
  const endRje = getResponseNum(responses, makeItemId(def.rowKey, 'endRje'))
  const reason = getResponseStr(responses, makeItemId(def.rowKey, 'reason'))

  return {
    rowKey: def.rowKey,
    label: def.label,
    isSub: def.isSub,
    isEditable: true,
    beginUnadjusted, beginAje, beginRje, beginAudited: 0,
    endUnadjusted, endAje, endRje, endAudited: 0,
    unadjChange: 0, unadjRate: 0, auditedChange: 0, auditedRate: 0,
    reason,
  }
}

/** 派生列填充（审定/变动/率） */
function deriveRow(row: AdjudicationRow): AdjudicationRow {
  const beginAudited = row.beginUnadjusted + row.beginAje + row.beginRje
  const endAudited = row.endUnadjusted + row.endAje + row.endRje
  const unadjChange = row.endUnadjusted - row.beginUnadjusted
  const auditedChange = endAudited - beginAudited
  return {
    ...row,
    beginAudited,
    endAudited,
    unadjChange,
    unadjRate: calcRate(row.beginUnadjusted, unadjChange),
    auditedChange,
    auditedRate: calcRate(beginAudited, auditedChange),
  }
}

/** 聚合多行的基础数值（用于优先股汇总行/合计行） */
function aggregateRows(
  rowKey: string,
  label: string,
  sources: AdjudicationRow[],
): AdjudicationRow {
  const sum = (f: (r: AdjudicationRow) => number) => sources.reduce((s, r) => s + f(r), 0)
  const base: AdjudicationRow = {
    rowKey,
    label,
    isSub: false,
    isEditable: false,
    beginUnadjusted: sum(r => r.beginUnadjusted),
    beginAje: sum(r => r.beginAje),
    beginRje: sum(r => r.beginRje),
    beginAudited: 0,
    endUnadjusted: sum(r => r.endUnadjusted),
    endAje: sum(r => r.endAje),
    endRje: sum(r => r.endRje),
    endAudited: 0,
    unadjChange: 0, unadjRate: 0, auditedChange: 0, auditedRate: 0,
    reason: '',
  }
  return deriveRow(base)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL2Adjudication(options: UseL2AdjudicationOptions) {
  const { allResponses, saveField, debouncedSave, writebackTB } = options

  // ─── Rows computed（含优先股汇总行的派生） ─────────────────────────────

  const rows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const responses = allResponses.value

    // 先构建所有可编辑行
    const baseMap = new Map<string, AdjudicationRow>()
    for (const def of SOURCE_ROWS) {
      baseMap.set(def.rowKey, buildBaseRow(def, responses))
    }

    // 优先股/永续债汇总行 = 工具1 + 工具2（不可编辑，自动聚合）
    const subRows = PREFERRED_SUB_KEYS.map(k => baseMap.get(k)!).filter(Boolean)
    const preferredAgg = aggregateRows('preferred-perpetual', '划分为金融负债的优先股/永续债利息', subRows)
    preferredAgg.isEditable = false
    baseMap.set('preferred-perpetual', preferredAgg)

    // 派生其余可编辑行
    return SOURCE_ROWS.map(def => {
      const r = baseMap.get(def.rowKey)!
      return def.rowKey === 'preferred-perpetual' ? r : deriveRow(r)
    })
  })

  /** 合计行（源模板 =SUM(主类, 优先股汇总, 其他)，不含工具1/工具2） */
  const totalRow: ComputedRef<AdjudicationRow> = computed(() => {
    const totalSources = rows.value.filter(r => TOTAL_ROW_KEYS.includes(r.rowKey))
    return aggregateRows('__total__', '合计', totalSources)
  })

  // ─── 合计审定数（期末/期初） ────────────────────────────────────────────

  /** 期末审定合计（用于 TB 回写 + 跨sheet消费） */
  const totalAuditedAmount: ComputedRef<number> = computed(() => totalRow.value.endAudited)
  /** 期初审定合计 */
  const totalBeginAuditedAmount: ComputedRef<number> = computed(() => totalRow.value.beginAudited)

  // ─── 同步合计到 allResponses 供跨sheet消费 ────────────────────────────

  watch([totalAuditedAmount, totalBeginAuditedAmount], ([endVal, beginVal]) => {
    allResponses.value.set('L2-L2-1-adjudication-total', {
      item_id: 'L2-L2-1-adjudication-total',
      conclusion: null,
      remark: String(endVal),
    })
    allResponses.value.set('L2-L2-1-adjudication-begin-total', {
      item_id: 'L2-L2-1-adjudication-begin-total',
      conclusion: null,
      remark: String(beginVal),
    })
  }, { immediate: true })

  // ─── 审计说明 / 结论 ────────────────────────────────────────────────────

  const noteChange = computed(() => getResponseStr(allResponses.value, `${PREFIX}-note-change`))
  const noteOverdue = computed(() => getResponseStr(allResponses.value, `${PREFIX}-note-overdue`))
  const conclusion = computed(() => getResponseStr(allResponses.value, `${PREFIX}-conclusion`))

  function updateNote(field: 'note-change' | 'note-overdue' | 'conclusion', value: string): void {
    debouncedSave(`${PREFIX}-${field}`, { remark: value })
  }

  // ─── 与经审计财报核对区 ─────────────────────────────────────────────────

  interface ReconRow {
    key: string
    label: string
    /** 期末值 */
    end: number
    /** 期初值 */
    begin: number
    /** 是否可编辑（应付利息审定数=自动，其余手填） */
    editable: boolean
    /** 是否为合计/差异行 */
    computed: boolean
  }

  const reconRows: ComputedRef<ReconRow[]> = computed(() => {
    const responses = allResponses.value
    const interestEnd = totalAuditedAmount.value
    const interestBegin = totalBeginAuditedAmount.value
    const dividendEnd = getResponseNum(responses, `${PREFIX}-recon-dividend-end`)
    const dividendBegin = getResponseNum(responses, `${PREFIX}-recon-dividend-begin`)
    const otherEnd = getResponseNum(responses, `${PREFIX}-recon-other-end`)
    const otherBegin = getResponseNum(responses, `${PREFIX}-recon-other-begin`)
    const reportEnd = getResponseNum(responses, `${PREFIX}-recon-report-end`)
    const reportBegin = getResponseNum(responses, `${PREFIX}-recon-report-begin`)
    const sumEnd = interestEnd + dividendEnd + otherEnd
    const sumBegin = interestBegin + dividendBegin + otherBegin

    return [
      { key: 'interest', label: '应付利息审定数', end: interestEnd, begin: interestBegin, editable: false, computed: false },
      { key: 'dividend', label: '应付股利审定数', end: dividendEnd, begin: dividendBegin, editable: true, computed: false },
      { key: 'other', label: '其他应付款审定数', end: otherEnd, begin: otherBegin, editable: true, computed: false },
      { key: 'sum', label: '其他应付款合计数', end: sumEnd, begin: sumBegin, editable: false, computed: true },
      { key: 'report', label: '报表数', end: reportEnd, begin: reportBegin, editable: true, computed: false },
      { key: 'diff', label: '差异', end: sumEnd - reportEnd, begin: sumBegin - reportBegin, editable: false, computed: true },
    ]
  })

  function updateRecon(key: string, period: 'end' | 'begin', value: number): void {
    debouncedSave(`${PREFIX}-recon-${key}-${period}`, { remark: String(value) })
  }

  // ─── updateCell（分类行基础字段） ──────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number | string): void {
    const itemId = makeItemId(rowKey, field)
    const strValue = typeof value === 'number' ? String(value) : value
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── 从 L2-2 明细带入（SUMIF 等价按类别聚合） ──────────────────────────

  /** 明细类别 → 审定表 rowKey 关键词映射 */
  function detailSourceToRowKey(source: string): string {
    const s = source || ''
    if (s.includes('长期借款') || s.includes('分期付息')) return 'long-term-loan'
    if (s.includes('债券')) return 'corporate-bond'
    if (s.includes('短期借款')) return 'short-term-loan'
    if (s.includes('优先股') || s.includes('永续债') || s.includes('工具')) return 'other'
    return 'other'
  }

  /**
   * 从 L2-2 明细行按类别聚合带入审定表。
   * 期初未审 = Σ 明细 beginBalance；期末未审 = Σ 明细 endBalance（期末余额）
   * 期末账项调整 = Σ 明细 aje；期末重分类调整 = Σ 明细 rje
   * @returns 带入的行数
   */
  function importFromDetail(): number {
    const detailResp = allResponses.value.get('L2-L2-2-rows')
    if (!detailResp?.remark) return 0
    let detailRows: any[] = []
    try {
      const parsed = JSON.parse(detailResp.remark)
      detailRows = Array.isArray(parsed) ? parsed : []
    } catch {
      return 0
    }
    if (detailRows.length === 0) return 0

    // 按 rowKey 聚合（期末未审取明细 endUnadjusted[=期末应付+重分类]，使审定表期末审定=Σ明细审定）
    const agg: Record<string, { beginUnadj: number; endUnadj: number; endAje: number; endRje: number }> = {}
    for (const r of detailRows) {
      const key = detailSourceToRowKey(r.source)
      if (!agg[key]) agg[key] = { beginUnadj: 0, endUnadj: 0, endAje: 0, endRje: 0 }
      agg[key].beginUnadj += parseNum(r.beginBalance)
      agg[key].endUnadj += (r.endUnadjusted != null ? parseNum(r.endUnadjusted) : parseNum(r.endBalance))
      agg[key].endAje += parseNum(r.aje)
      agg[key].endRje += parseNum(r.rje)
    }

    let count = 0
    for (const [rowKey, v] of Object.entries(agg)) {
      updateCell(rowKey, 'beginUnadjusted', v.beginUnadj)
      updateCell(rowKey, 'endUnadjusted', v.endUnadj)
      updateCell(rowKey, 'endAje', v.endAje)
      updateCell(rowKey, 'endRje', v.endRje)
      count++
    }
    return count
  }

  // ─── publishAdjudicated + writebackTB ──────────────────────────────────

  async function submitAdjudication(): Promise<void> {
    const amount = totalAuditedAmount.value
    await writebackTB(amount)
    await saveField('L2-L2-1-adjudication-total', { remark: String(amount) })
  }

  // ─── onAdjustmentCreated（EventBus监听，明细已写入 allResponses 自动响应） ──

  function onAdjustmentCreated(): void {
    // adjustment:created 触发时，rows computed 会自动响应 allResponses 变化
  }

  eventBus.on('adjustment:created', onAdjustmentCreated)
  onBeforeUnmount(() => {
    eventBus.off('adjustment:created', onAdjustmentCreated)
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 数据行
    rows,
    totalRow,
    totalAuditedAmount,
    totalBeginAuditedAmount,
    // 审计说明/结论
    noteChange,
    noteOverdue,
    conclusion,
    updateNote,
    // 财报核对
    reconRows,
    updateRecon,
    // 操作
    updateCell,
    importFromDetail,
    submitAdjudication,
    // EventBus
    onAdjustmentCreated,
    // 常量
    SOURCE_ROWS,
  }
}

export default useL2Adjudication
