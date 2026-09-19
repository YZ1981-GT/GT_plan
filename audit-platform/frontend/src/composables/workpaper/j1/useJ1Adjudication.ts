/**
 * useJ1Adjudication — J1 应付职工薪酬 审定表 composable
 *
 * 科目：2211应付职工薪酬（贷方/负债类）
 * J1-1审定表：短期薪酬/离职后福利/辞退福利/一年内到期其他长期 四大分类
 *
 * 列结构：
 *   项目名称 | 期初数(未审/调整/审定) | 期末数(未审/调整/审定)
 *   | 本期未审数与上期审定数比较(额/率) | 本期审定数与上期审定数比较(额/率) | 原因分析
 *
 * 🔴 口径：审定表的「上期审定数」即本表「期初审定数」（上年年末=本年年初），
 *    故 unadjVsPrior = 期末未审 − 期初审定；auditedVsPrior = 期末审定 − 期初审定。
 *    历史实现只算 changeDiff/changeRate，而模板读 unadjVsPriorDiff/Rate 与
 *    auditedVsPriorDiff/Rate → 四个变动列恒 undefined、>30% 标红从不触发（2026-07-26 修）。
 *
 * 🔴 持久化：rows 存 `J1-1-rows`（JSON），并派生跨表键
 *    `J1-1-audited-total` / `J1-1-audited-begin-total`（供跨表勾稽消费）。
 *    历史实现无任何持久化 → 审定表编辑刷新即丢（2026-07-26 修）。
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 2.2-2.6, 3.2
 */
import { ref, computed, type Ref } from 'vue'
import {
  calcAuditedAmount,
  calcChangeDiff,
  calcChangeRate,
  calcSubtotal,
  parseNum,
} from './useJ1FormulaEngine'

export interface AdjudicationRow {
  id: string
  label: string
  category: 'short_term' | 'post_employment' | 'severance' | 'other_long_term'
  /** 缩进层级（1=子项，可编辑名称/可删除） */
  indent?: number
  // 期初
  beginUnadj: number
  beginAje: number
  beginAudited: number
  // 期末
  endUnadj: number
  endAje: number
  endAudited: number
  // 本期未审数 与 上期审定数（=期初审定数）比较
  unadjVsPriorDiff: number
  unadjVsPriorRate: number
  // 本期审定数 与 上期审定数 比较
  auditedVsPriorDiff: number
  auditedVsPriorRate: number
  /** @deprecated 同 auditedVsPriorDiff，保留兼容既有引用 */
  changeDiff: number
  /** @deprecated 同 auditedVsPriorRate，保留兼容既有引用 */
  changeRate: number
  // 原因分析
  analysis: string
}

export interface AdjudicationGroup {
  category: string
  label: string
  rows: AdjudicationRow[]
  subtotal: AdjudicationRow
}

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseJ1AdjudicationOptions {
  /** 共享 allResponses（主入口 persistence.responses），用于 hydrate + 写回内存 */
  allResponses?: Ref<Map<string, ChecklistItem>>
  /** 主入口 handleChildSave（逐 item debounce PUT） */
  saveImmediate?: (items: ChecklistItem[]) => Promise<void>
}

const CATEGORIES = [
  { key: 'short_term', label: '（1）短期薪酬' },
  { key: 'post_employment', label: '（2）离职后福利-设定提存计划' },
  { key: 'severance', label: '（3）辞退福利' },
  { key: 'other_long_term', label: '（4）一年内到期的其他长期职工福利' },
] as const

/** 行存储键（前端唯一真源；后端 render 优先读它，回退历史 J1-adjudication-data / tb_balance 预填） */
export const J1_ADJ_ROWS_KEY = 'J1-1-rows'
/** 跨表键：期末/期初审定合计（供 useJ1CrossSheet 等消费） */
export const J1_ADJ_END_TOTAL_KEY = 'J1-1-audited-total'
export const J1_ADJ_BEGIN_TOTAL_KEY = 'J1-1-audited-begin-total'

/** J1-2 明细表分区存储键（与 useJ1Detail 的 STORAGE_KEY_PREFIX 一致） */
export const J1_DETAIL_SECTION_KEYS = {
  shortTerm: 'J1-2-detail-shortTerm',
  postEmployment: 'J1-2-detail-postEmployment',
  severance: 'J1-2-detail-severance',
} as const

/** J1-2 明细行（只取带入所需字段） */
export interface J1DetailPullRow {
  label?: unknown
  indent?: unknown
  unadjBegin?: unknown
  unadjIncrease?: unknown
  unadjDecrease?: unknown
}

export interface J1DetailPullSections {
  shortTerm: J1DetailPullRow[]
  postEmployment: J1DetailPullRow[]
  severance: J1DetailPullRow[]
}

/**
 * 项目名称归一化（用于审定表↔明细表↔披露表按名匹配）
 * 去空白 / 去「其中：」前缀 / 去「1.」「2、」序号前缀 / 去「（不适用的删除）」尾注
 */
export function normalizeJ1Label(raw: unknown): string {
  let s = String(raw ?? '').replace(/[\s\u3000]/g, '')
  s = s.replace(/^其中[:：]/, '')
  s = s.replace(/^\d+[.．、]/, '')
  s = s.replace(/（不适用的删除）$/, '')
  return s
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 J1-2 明细表重建审定表行（未审数按明细带入，已录的调整/原因分析按同名保留）
 *
 * 分类映射：shortTerm→short_term；severance→severance；
 * postEmployment 分区自「其他长期职工福利」行起归入 other_long_term（源模板该分区含两段）。
 * 空名且全零的行（如辞退福利默认空行）跳过。
 */
export function buildAdjudicationRowsFromDetail(
  sections: J1DetailPullSections,
  existing: AdjudicationRow[],
): { rows: AdjudicationRow[]; matched: number } {
  const byLabel = new Map<string, AdjudicationRow>()
  for (const r of existing) {
    const k = normalizeJ1Label(r.label)
    if (k && !byLabel.has(k)) byLabel.set(k, r)
  }

  const out: AdjudicationRow[] = []
  let matched = 0
  let seq = 0

  const push = (
    src: J1DetailPullRow,
    category: AdjudicationRow['category'],
  ) => {
    const label = String(src.label ?? '').trim()
    const begin = num(src.unadjBegin)
    const inc = num(src.unadjIncrease)
    const dec = num(src.unadjDecrease)
    if (!label && begin === 0 && inc === 0 && dec === 0) return
    const prev = byLabel.get(normalizeJ1Label(label))
    if (prev) matched += 1
    seq += 1
    const row: AdjudicationRow = {
      id: prev?.id || `j1adj-pull-${category}-${seq}`,
      label,
      category,
      indent: Number(src.indent || 0) || undefined,
      beginUnadj: begin,
      beginAje: prev?.beginAje ?? 0,
      beginAudited: 0,
      endUnadj: begin + inc - dec,
      endAje: prev?.endAje ?? 0,
      endAudited: 0,
      unadjVsPriorDiff: 0,
      unadjVsPriorRate: 0,
      auditedVsPriorDiff: 0,
      auditedVsPriorRate: 0,
      changeDiff: 0,
      changeRate: 0,
      analysis: prev?.analysis ?? '',
    }
    out.push(recalcAdjudicationRow(row))
  }

  for (const r of sections.shortTerm || []) push(r, 'short_term')

  let inOtherLongTerm = false
  for (const r of sections.postEmployment || []) {
    if (normalizeJ1Label(r.label).includes('其他长期')) inOtherLongTerm = true
    push(r, inOtherLongTerm ? 'other_long_term' : 'post_employment')
  }

  for (const r of sections.severance || []) push(r, 'severance')

  return { rows: out, matched }
}

/** 由基础字段派生全部计算列（纯函数，便于单测） */
export function recalcAdjudicationRow(row: AdjudicationRow): AdjudicationRow {
  row.beginAudited = calcAuditedAmount(row.beginUnadj, row.beginAje, 0)
  row.endAudited = calcAuditedAmount(row.endUnadj, row.endAje, 0)
  // 上期审定数 = 期初审定数
  row.unadjVsPriorDiff = calcChangeDiff(row.endUnadj, row.beginAudited)
  row.unadjVsPriorRate = calcChangeRate(row.endUnadj, row.beginAudited)
  row.auditedVsPriorDiff = calcChangeDiff(row.endAudited, row.beginAudited)
  row.auditedVsPriorRate = calcChangeRate(row.endAudited, row.beginAudited)
  row.changeDiff = row.auditedVsPriorDiff
  row.changeRate = row.auditedVsPriorRate
  return row
}

export function useJ1Adjudication(
  htmlData: Ref<Record<string, unknown>>,
  options: UseJ1AdjudicationOptions = {},
) {
  const rows: Ref<AdjudicationRow[]> = ref([])
  const isInitialized = ref(false)

  // ── 初始化 ────────────────────────────────────────────────────────────────

  function normalizeRow(r: Record<string, unknown>): AdjudicationRow {
    const row: AdjudicationRow = {
      id: String(r.id || `row-${Math.random().toString(36).slice(2, 8)}`),
      label: String(r.label ?? ''),
      category: (r.category || 'short_term') as AdjudicationRow['category'],
      indent: Number(r.indent || 0) || undefined,
      // snake_case（后端 prefill）与 camelCase（前端持久化）双兼容
      beginUnadj: parseNum((r.beginUnadj ?? r.begin_unadj) as number),
      beginAje: parseNum((r.beginAje ?? r.begin_aje) as number),
      beginAudited: 0,
      endUnadj: parseNum((r.endUnadj ?? r.end_unadj) as number),
      endAje: parseNum((r.endAje ?? r.end_aje) as number),
      endAudited: 0,
      unadjVsPriorDiff: 0,
      unadjVsPriorRate: 0,
      auditedVsPriorDiff: 0,
      auditedVsPriorRate: 0,
      changeDiff: 0,
      changeRate: 0,
      analysis: String(r.analysis ?? ''),
    }
    return recalcAdjudicationRow(row)
  }

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.adjudication_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(normalizeRow)
    isInitialized.value = true
  }

  /** 从共享 allResponses 的持久化行 hydrate；无持久化时回退 htmlData（含后端 tb_balance 预填）。 */
  function init(data?: Record<string, unknown>) {
    const stored = options.allResponses?.value?.get(J1_ADJ_ROWS_KEY)?.remark
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed) && parsed.length > 0) {
          rows.value = parsed.map(normalizeRow)
          isInitialized.value = true
          return
        }
      } catch {
        /* 损坏数据 → 回退 htmlData */
      }
    }
    initFromHtmlData(data ?? htmlData.value ?? {})
  }

  // ── 按分类分组 ────────────────────────────────────────────────────────────

  function buildSubtotal(catKey: string, label: string, catRows: AdjudicationRow[]): AdjudicationRow {
    const subtotal: AdjudicationRow = {
      id: `subtotal-${catKey}`,
      label: `${label}小计`,
      category: catKey as AdjudicationRow['category'],
      beginUnadj: calcSubtotal(catRows.map(r => r.beginUnadj)),
      beginAje: calcSubtotal(catRows.map(r => r.beginAje)),
      beginAudited: calcSubtotal(catRows.map(r => r.beginAudited)),
      endUnadj: calcSubtotal(catRows.map(r => r.endUnadj)),
      endAje: calcSubtotal(catRows.map(r => r.endAje)),
      endAudited: calcSubtotal(catRows.map(r => r.endAudited)),
      unadjVsPriorDiff: 0,
      unadjVsPriorRate: 0,
      auditedVsPriorDiff: 0,
      auditedVsPriorRate: 0,
      changeDiff: 0,
      changeRate: 0,
      analysis: '',
    }
    // 小计行的变动按小计口径重算（不是逐行变动求和）
    subtotal.unadjVsPriorDiff = calcChangeDiff(subtotal.endUnadj, subtotal.beginAudited)
    subtotal.unadjVsPriorRate = calcChangeRate(subtotal.endUnadj, subtotal.beginAudited)
    subtotal.auditedVsPriorDiff = calcChangeDiff(subtotal.endAudited, subtotal.beginAudited)
    subtotal.auditedVsPriorRate = calcChangeRate(subtotal.endAudited, subtotal.beginAudited)
    subtotal.changeDiff = subtotal.auditedVsPriorDiff
    subtotal.changeRate = subtotal.auditedVsPriorRate
    return subtotal
  }

  const groups: Ref<AdjudicationGroup[]> = computed(() =>
    CATEGORIES.map(cat => {
      const catRows = rows.value.filter(r => r.category === cat.key)
      return {
        category: cat.key,
        label: cat.label,
        rows: catRows,
        subtotal: buildSubtotal(cat.key, cat.label, catRows),
      }
    }),
  ) as unknown as Ref<AdjudicationGroup[]>

  // ── 合计行 ────────────────────────────────────────────────────────────────

  const grandTotal = computed(() => {
    const allRows = rows.value
    const endAudited = calcSubtotal(allRows.map(r => r.endAudited))
    const beginAudited = calcSubtotal(allRows.map(r => r.beginAudited))
    const endUnadj = calcSubtotal(allRows.map(r => r.endUnadj))
    return {
      beginAudited,
      endAudited,
      endUnadj,
      unadjVsPriorDiff: calcChangeDiff(endUnadj, beginAudited),
      unadjVsPriorRate: calcChangeRate(endUnadj, beginAudited),
      auditedVsPriorDiff: calcChangeDiff(endAudited, beginAudited),
      auditedVsPriorRate: calcChangeRate(endAudited, beginAudited),
      changeDiff: calcChangeDiff(endAudited, beginAudited),
      changeRate: calcChangeRate(endAudited, beginAudited),
    }
  })

  // ── 持久化 ────────────────────────────────────────────────────────────────

  /** 序列化行（只存基础字段，计算列 hydrate 时重算，避免陈旧派生值） */
  function serializeRows(): string {
    return JSON.stringify(
      rows.value.map(r => ({
        id: r.id,
        label: r.label,
        category: r.category,
        indent: r.indent || 0,
        beginUnadj: r.beginUnadj,
        beginAje: r.beginAje,
        endUnadj: r.endUnadj,
        endAje: r.endAje,
        analysis: r.analysis,
      })),
    )
  }

  function buildPersistItems(): ChecklistItem[] {
    return [
      { item_id: J1_ADJ_ROWS_KEY, conclusion: null, remark: serializeRows() },
      { item_id: J1_ADJ_END_TOTAL_KEY, conclusion: null, remark: String(grandTotal.value.endAudited) },
      { item_id: J1_ADJ_BEGIN_TOTAL_KEY, conclusion: null, remark: String(grandTotal.value.beginAudited) },
    ]
  }

  /** 写内存 Map + 交主入口 debounce PUT */
  function persist(): void {
    const items = buildPersistItems()
    const map = options.allResponses?.value
    if (map) items.forEach(it => map.set(it.item_id, it))
    options.saveImmediate?.(items).catch(() => { /* 主入口已统一提示 */ })
  }

  // ── 更新单行 ──────────────────────────────────────────────────────────────

  function updateRow(id: string, field: keyof AdjudicationRow, value: unknown) {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as Record<string, unknown>)[field] = value
    recalcAdjudicationRow(row)
    persist()
  }

  /** 增删行后调用（组件直接 splice rows 时用） */
  function commitRows() {
    rows.value.forEach(recalcAdjudicationRow)
    persist()
  }

  // ── 从 J1-2 明细表带入未审数 ──────────────────────────────────────────────

  function readDetailSection(key: string): J1DetailPullRow[] {
    const raw = options.allResponses?.value?.get(key)?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? (parsed as J1DetailPullRow[]) : []
    } catch {
      return []
    }
  }

  /**
   * 从 J1-2 明细表带入：按明细项目清单重建审定表行，未审期初/期末取明细未审数
   * （期末未审=期初+本期增加−本期减少），同名行的账项调整/原因分析保留。
   * @returns 带入行数与其中沿用既有调整的行数；rowCount=0 表示明细表尚未编制
   */
  function pullFromDetail(): { rowCount: number; matched: number } {
    const sections: J1DetailPullSections = {
      shortTerm: readDetailSection(J1_DETAIL_SECTION_KEYS.shortTerm),
      postEmployment: readDetailSection(J1_DETAIL_SECTION_KEYS.postEmployment),
      severance: readDetailSection(J1_DETAIL_SECTION_KEYS.severance),
    }
    const { rows: pulled, matched } = buildAdjudicationRowsFromDetail(sections, rows.value)
    if (pulled.length === 0) return { rowCount: 0, matched: 0 }
    rows.value = pulled
    persist()
    return { rowCount: pulled.length, matched }
  }

  return {
    pullFromDetail,
    rows,
    groups,
    grandTotal,
    isInitialized,
    init,
    initFromHtmlData,
    updateRow,
    commitRows,
    persist,
    buildPersistItems,
  }
}
