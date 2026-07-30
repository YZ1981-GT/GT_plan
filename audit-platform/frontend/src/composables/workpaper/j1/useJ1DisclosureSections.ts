/**
 * useJ1DisclosureSections — J1 附注披露表（上市/国企）分区数据 + 持久化
 *
 * 历史实现：两张披露表把 summary/短期薪酬/设定提存 全部行放在组件本地 ref，
 * onMounted 里只有 `// TODO: 从持久化数据恢复` → **录入刷新即丢**（2026-07-26 修）。
 *
 * 存储键（variant = listed | soe）：
 *   J1-disc-{variant}-summary          汇总表数据行（不含合计行，合计为 computed）
 *   J1-disc-{variant}-short-term       （1）短期薪酬明细行
 *   J1-disc-{variant}-post-employment  （2）设定提存计划明细行
 *   J1-disc-{variant}-notes            各段说明文本（{ key: text }）
 *
 * 口径：期末 = 期初 + 本期增加 − 本期减少（负债贷方）；
 *       小计/合计只累加非缩进行（缩进行是「其中：」明细，避免重复计入）。
 */
import { ref, computed, watch, type Ref } from 'vue'
import {
  buildDisclosureSubtotal,
  recalcDisclosureRow,
  type J1DisclosureRow,
  type J1DisclosureVariant,
} from './j1DisclosureRowModel'
import {
  applyDetailPullToDisclosureRows,
  J1_SOE_SHORT_TERM_ABSORB,
  type J1DetailPullResult,
  type J1DetailPullRow,
} from './j1DisclosureDetailPull'
import { J1_DETAIL_SECTION_KEYS } from './useJ1Adjudication'

// 行模型与合计口径已抽到零依赖的 leaf 模块（`j1DisclosureRowModel`），
// 供 `j1DisclosureDetailPull` / `j1NoteSectionMap` 共用而不产生循环依赖。
// 此处 re-export，既有 `from '.../useJ1DisclosureSections'` 的 import 保持可用。
export {
  buildDisclosureSubtotal,
  recalcDisclosureRow,
  type J1DisclosureRow,
  type J1DisclosureVariant,
}

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseJ1DisclosureSectionsOptions {
  variant: J1DisclosureVariant
  defaults: {
    summary: J1DisclosureRow[]
    shortTerm: J1DisclosureRow[]
    postEmployment: J1DisclosureRow[]
  }
  allResponses?: Ref<Map<string, ChecklistItem>>
  saveImmediate?: (items: ChecklistItem[]) => Promise<void>
  isReadonly?: Ref<boolean>
  /** 说明文本键（listed 有多段，soe 单段） */
  noteKeys: string[]
}

// ── 从 J1-1 审定表 / J1-2 明细表带入 ────────────────────────────────────────

export type J1Category = 'short_term' | 'post_employment' | 'severance' | 'other_long_term'

export interface J1CategoryAgg {
  begin: number
  increase: number
  decrease: number
  /** 来源侧是否出现过该分类（未出现则不覆盖手工录入） */
  has: boolean
}

function emptyAgg(): Record<J1Category, J1CategoryAgg> {
  return {
    short_term: { begin: 0, increase: 0, decrease: 0, has: false },
    post_employment: { begin: 0, increase: 0, decrease: 0, has: false },
    severance: { begin: 0, increase: 0, decrease: 0, has: false },
    other_long_term: { begin: 0, increase: 0, decrease: 0, has: false },
  }
}

function n(v: unknown): number {
  const x = Number(v)
  return Number.isFinite(x) ? x : 0
}

/** 汇总表行名 → 审定表分类（附注汇总 4 行对应 J1-1 四大分类） */
export function categoryForSummaryLabel(label: unknown): J1Category | null {
  const s = String(label ?? '').replace(/[\s\u3000]/g, '')
  if (!s) return null
  if (s.includes('辞退')) return 'severance'
  if (s.includes('一年内到期') || s.includes('其他长期') || s.includes('其他福利')) return 'other_long_term'
  if (s.includes('短期薪酬')) return 'short_term'
  if (s.includes('离职后福利') || s.includes('设定提存')) return 'post_employment'
  return null
}

/** 汇总 J1-1 审定表按分类的期初/期末审定数（与 J1-1 小计口径一致：累加该分类全部行） */
export function aggregateAdjudicationByCategory(
  rows: Array<Record<string, unknown>>,
): Record<J1Category, { begin: number; end: number; has: boolean }> {
  const out: Record<J1Category, { begin: number; end: number; has: boolean }> = {
    short_term: { begin: 0, end: 0, has: false },
    post_employment: { begin: 0, end: 0, has: false },
    severance: { begin: 0, end: 0, has: false },
    other_long_term: { begin: 0, end: 0, has: false },
  }
  for (const r of rows || []) {
    const cat = String(r.category ?? '') as J1Category
    if (!(cat in out)) continue
    const beginAudited = n(r.beginUnadj) + n(r.beginAje)
    const endAudited = n(r.endUnadj) + n(r.endAje)
    out[cat].begin += beginAudited
    out[cat].end += endAudited
    out[cat].has = true
  }
  return out
}

/**
 * 汇总 J1-2 明细表按分类的审定期初/本期增加/本期减少
 * （审定 = 未审 + 期初调整 / 账项调整；只累加非「其中」子项行避免重复计入）
 */
export function aggregateDetailAuditedByCategory(sections: {
  shortTerm?: Array<Record<string, unknown>>
  postEmployment?: Array<Record<string, unknown>>
  severance?: Array<Record<string, unknown>>
}): Record<J1Category, J1CategoryAgg> {
  const out = emptyAgg()
  const add = (cat: J1Category, r: Record<string, unknown>) => {
    if (r.isSubItem) return
    out[cat].begin += n(r.unadjBegin) + n(r.openingAdj)
    out[cat].increase += n(r.unadjIncrease) + n(r.ajeIncrease)
    out[cat].decrease += n(r.unadjDecrease) + n(r.ajeDecrease)
    out[cat].has = true
  }
  for (const r of sections.shortTerm || []) add('short_term', r)
  let inOther = false
  for (const r of sections.postEmployment || []) {
    if (String(r.label ?? '').replace(/[\s\u3000]/g, '').includes('其他长期')) inOther = true
    add(inOther ? 'other_long_term' : 'post_employment', r)
  }
  for (const r of sections.severance || []) add('severance', r)
  return out
}

/**
 * 把审定表/明细表聚合值写入汇总表行（期初优先取 J1-1 审定，增减取 J1-2 审定）
 * @returns 实际覆盖的行数（来源侧未出现的分类不动，避免清零手工录入）
 */
export function applySummaryPull(
  summaryRows: J1DisclosureRow[],
  adjAgg: Record<J1Category, { begin: number; end: number; has: boolean }>,
  detailAgg: Record<J1Category, J1CategoryAgg>,
): number {
  let matched = 0
  for (const row of summaryRows) {
    const cat = categoryForSummaryLabel(row.label)
    if (!cat) continue
    const a = adjAgg[cat]
    const d = detailAgg[cat]
    if (!a?.has && !d?.has) continue
    row.beginBalance = a?.has ? a.begin : d.begin
    if (d?.has) {
      row.increase = d.increase
      row.decrease = d.decrease
    } else if (a?.has) {
      // 无明细增减数据时，用审定期末−期初的净变动作为增加/减少之一（净增计入增加，净减计入减少）
      const net = a.end - a.begin
      row.increase = net > 0 ? net : 0
      row.decrease = net < 0 ? -net : 0
    }
    recalcDisclosureRow(row)
    matched += 1
  }
  return matched
}

export function useJ1DisclosureSections(options: UseJ1DisclosureSectionsOptions) {
  const { variant, defaults, allResponses, saveImmediate, noteKeys } = options
  const prefix = `J1-disc-${variant}`
  const KEY_SUMMARY = `${prefix}-summary`
  const KEY_SHORT_TERM = `${prefix}-short-term`
  const KEY_POST = `${prefix}-post-employment`
  const KEY_NOTES = `${prefix}-notes`

  const summaryData = ref<J1DisclosureRow[]>(cloneRows(defaults.summary))
  const shortTermData = ref<J1DisclosureRow[]>(cloneRows(defaults.shortTerm))
  const postEmploymentData = ref<J1DisclosureRow[]>(cloneRows(defaults.postEmployment))
  const notes = ref<Record<string, string>>(Object.fromEntries(noteKeys.map(k => [k, ''])))

  function cloneRows(rows: J1DisclosureRow[]): J1DisclosureRow[] {
    return rows.map(r => recalcDisclosureRow({ ...r }))
  }

  function readRows(key: string): J1DisclosureRow[] | null {
    const raw = allResponses?.value?.get(key)?.remark
    if (!raw) return null
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) return null
      return parsed.map((r: Record<string, unknown>) =>
        recalcDisclosureRow({
          id: String(r.id || `row-${Math.random().toString(36).slice(2, 8)}`),
          label: String(r.label ?? ''),
          category: String(r.category ?? ''),
          indent: Number(r.indent || 0) || undefined,
          beginBalance: Number(r.beginBalance) || 0,
          increase: Number(r.increase) || 0,
          decrease: Number(r.decrease) || 0,
          endBalance: 0,
        }),
      )
    } catch {
      return null
    }
  }

  /** 从共享 allResponses hydrate（无持久化则保留默认骨架行） */
  function hydrate(): void {
    const s = readRows(KEY_SUMMARY)
    if (s) summaryData.value = s
    const st = readRows(KEY_SHORT_TERM)
    if (st) shortTermData.value = st
    const pe = readRows(KEY_POST)
    if (pe) postEmploymentData.value = pe
    const rawNotes = allResponses?.value?.get(KEY_NOTES)?.remark
    if (rawNotes) {
      try {
        const parsed = JSON.parse(rawNotes)
        if (parsed && typeof parsed === 'object') {
          for (const k of noteKeys) notes.value[k] = String(parsed[k] ?? '')
        }
      } catch {
        /* 忽略损坏数据 */
      }
    }
  }

  // ── 合计 / 小计（历史实现汇总表「合计」行恒为 0，无聚合） ────────────────
  const summaryTotal = computed(() =>
    buildDisclosureSubtotal('s-total', '合 计', 'summary', summaryData.value),
  )
  const summaryRows = computed(() => [...summaryData.value, summaryTotal.value])
  const shortTermSubtotal = computed(() =>
    buildDisclosureSubtotal('st-total', '合 计', 'short_term', shortTermData.value),
  )
  const postEmploymentSubtotal = computed(() =>
    buildDisclosureSubtotal('pe-total', '合 计', 'post_employment', postEmploymentData.value),
  )

  // ── 持久化 ─────────────────────────────────────────────────────────────
  function serialize(rows: J1DisclosureRow[]): string {
    return JSON.stringify(
      rows.map(r => ({
        id: r.id,
        label: r.label,
        category: r.category,
        indent: r.indent || 0,
        beginBalance: r.beginBalance,
        increase: r.increase,
        decrease: r.decrease,
      })),
    )
  }

  function buildItems(): ChecklistItem[] {
    return [
      { item_id: KEY_SUMMARY, conclusion: null, remark: serialize(summaryData.value) },
      { item_id: KEY_SHORT_TERM, conclusion: null, remark: serialize(shortTermData.value) },
      { item_id: KEY_POST, conclusion: null, remark: serialize(postEmploymentData.value) },
      { item_id: KEY_NOTES, conclusion: null, remark: JSON.stringify(notes.value) },
    ]
  }

  let timer: ReturnType<typeof setTimeout> | null = null

  function persist(): void {
    if (options.isReadonly?.value) return
    const items = buildItems()
    const map = allResponses?.value
    if (map) items.forEach(it => map.set(it.item_id, it))
    saveImmediate?.(items).catch(() => { /* 主入口统一提示 */ })
  }

  /** 输入类变更用防抖，避免逐字符 PUT */
  function persistDebounced(delay = 800): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(persist, delay)
  }

  /** 单元格变更：重算期末 + 落库 */
  function onRowChange(row: J1DisclosureRow): void {
    recalcDisclosureRow(row)
    persistDebounced()
  }

  // ── 从 J1-1 审定表 / J1-2 明细表带入 + 差异告警 ─────────────────────────

  function readJson<T>(key: string): T | null {
    const raw = allResponses?.value?.get(key)?.remark
    if (!raw) return null
    try {
      return JSON.parse(raw) as T
    } catch {
      return null
    }
  }

  /** J1-1 期末审定合计（跨表键，供披露↔审定勾稽） */
  const adjudicationEndTotal = computed(() => {
    const raw = allResponses?.value?.get('J1-1-audited-total')?.remark
    const v = Number(raw)
    return Number.isFinite(v) ? v : 0
  })

  /** 披露汇总期末合计 − J1-1 期末审定合计 */
  const summaryVsAdjudicationDiff = computed(
    () => summaryTotal.value.endBalance - adjudicationEndTotal.value,
  )

  /**
   * 「从审定表/明细表带入」：汇总表期初取 J1-1 审定期初，本期增减取 J1-2 审定增减
   * @returns 覆盖行数（0 = 审定表与明细表均未编制）
   */
  function pullFromSources(): number {
    const adjRows = readJson<Array<Record<string, unknown>>>('J1-1-rows') || []
    const detail = {
      shortTerm: readJson<Array<Record<string, unknown>>>('J1-2-detail-shortTerm') || [],
      postEmployment: readJson<Array<Record<string, unknown>>>('J1-2-detail-postEmployment') || [],
      severance: readJson<Array<Record<string, unknown>>>('J1-2-detail-severance') || [],
    }
    const matched = applySummaryPull(
      summaryData.value,
      aggregateAdjudicationByCategory(adjRows),
      aggregateDetailAuditedByCategory(detail),
    )
    if (matched > 0) persist()
    return matched
  }

  /**
   * 明细两表「从 J1-2 明细表带入」（审定口径）。
   *
   * 源模板里披露明细表**每一行**都引用 J1-2（`A18='明细表J1-2 '!J13` …），
   * 历史实现只带入了汇总表 4~5 行，短期薪酬 12 行 + 设定提存 8 行全靠手打。
   *
   * 只覆盖匹配到的行（未匹配的披露行保持原值，不清零手工录入）。
   */
  function pullDetailSections(): {
    shortTerm: J1DetailPullResult
    postEmployment: J1DetailPullResult
  } {
    const shortTerm = applyDetailPullToDisclosureRows(
      shortTermData.value,
      readJson<J1DetailPullRow[]>(J1_DETAIL_SECTION_KEYS.shortTerm) || [],
      // 🔴 仅国企：源模板 `B28='明细表J1-2 '!J30+J31` 把「非货币性福利」并入
      //    「其他短期薪酬」；上市披露表有独立该行，不得套用
      variant === 'soe' ? { absorb: J1_SOE_SHORT_TERM_ABSORB } : {},
    )
    const postEmployment = applyDetailPullToDisclosureRows(
      postEmploymentData.value,
      readJson<J1DetailPullRow[]>(J1_DETAIL_SECTION_KEYS.postEmployment) || [],
    )
    const touched =
      shortTerm.matched + shortTerm.appended + postEmployment.matched + postEmployment.appended
    if (touched > 0) persist()
    return { shortTerm, postEmployment }
  }

  // 深度监听兜底：项目名称等非金额字段的修改（模板未挂 @change）也会落库。
  // hydrate 期间抑制，避免刚加载就回写一次。
  let hydrating = false
  watch(
    [summaryData, shortTermData, postEmploymentData, notes],
    () => {
      if (hydrating) return
      persistDebounced()
    },
    { deep: true },
  )

  const hydrateSafe = () => {
    hydrating = true
    try {
      hydrate()
    } finally {
      // 让本轮 watch 回调（同步 flush 前）看到 hydrating=true
      setTimeout(() => { hydrating = false }, 0)
    }
  }

  return {
    summaryData,
    summaryRows,
    summaryTotal,
    shortTermData,
    shortTermSubtotal,
    postEmploymentData,
    postEmploymentSubtotal,
    notes,
    adjudicationEndTotal,
    summaryVsAdjudicationDiff,
    pullFromSources,
    pullDetailSections,
    /** hydrate（内部抑制 deep-watch 回写，避免加载即 PUT） */
    hydrate: hydrateSafe,
    persist,
    persistDebounced,
    onRowChange,
    buildItems,
    keys: { KEY_SUMMARY, KEY_SHORT_TERM, KEY_POST, KEY_NOTES },
  }
}
