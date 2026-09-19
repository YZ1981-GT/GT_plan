/**
 * useN2DisclosureTables — N2 应交税费披露表（上市 / 国企）编制模型
 *
 * 把源模板结构收敛到一处：行骨架、列定义、合计公式、国企期末余额行内公式、
 * 持久化键、勾稽入参、同步载荷组装。两个 Tab 只负责渲染。
 *
 * 源模板权威 = `backend/wp_templates/N/N2 应交税费.xlsx`
 * （`附注披露信息（上市公司）` A1:K27 / `附注披露信息（国企）` A1:K24）。
 *
 * 🔴 两版口径本质不同（上市双期余额 / 国企变动），行骨架与列都分别构造；
 * 现状缺陷即两个组件复制粘贴导致上市误用国企口径。
 * 🔴 源模板里没有的小节（税种变动说明 / 欠缴税款说明 / 应缴国有资本收益说明）不再提供 ——
 * 变动分析属审计过程，留在 N2-1 审定表与 N2-2 明细表。
 */
import { computed, ref, type Ref } from 'vue'
import {
  N2_TOTAL_LABEL,
  buildN2SyncPayload,
  computeN2SoeEnd,
  n2ColumnsFor,
  type N2DisclosureSnapshot,
  type N2DisclosureVariant,
  type N2ListedTaxRow,
  type N2SoeTaxRow,
} from './n2NoteSectionMap'
import { N2_FIXED_TAX_LABELS, normalizeTaxLabel } from './n2TaxLabelMap'
import {
  runN2ListedChecks,
  runN2SoeChecks,
  type WpCheckResult,
} from './nCycleTaxConsistency'
import { nz, sumNullable, type NullableAmount } from './shared/disclosureConsistency'
import type { WpSegColumn, WpSegment } from './shared/disclosureSegmentTypes'

// ─── 行骨架（源模板 R8~R20 逐字 13 行，两版完全一致）─────────────────────────

/**
 * 上市默认税种（附注模板 五、41 rows）。
 * 源模板权威 = N2_FIXED_TAX_LABELS（n2TaxLabelMap.ts 单一真源）。
 */
export const N2_LISTED_TAX_ITEMS: readonly string[] = N2_FIXED_TAX_LABELS

/**
 * 国企默认税种（附注模板 八、41 rows）。
 * 源模板两版行集完全一致（R8~R20 逐字相同），共用 N2_FIXED_TAX_LABELS。
 */
export const N2_SOE_TAX_ITEMS: readonly string[] = N2_FIXED_TAX_LABELS

// ─── 行模型 ──────────────────────────────────────────────────────────────────

export interface N2ListedRowModel extends N2ListedTaxRow {
  _editableLabel?: boolean
}

/** 国企行：`end` 不落库（行内公式），持久化时剔除 */
export interface N2SoeRowModel {
  item: string
  opening: NullableAmount
  payable: NullableAmount
  paid: NullableAmount
  _editableLabel?: boolean
}

// ─── 持久化键 ────────────────────────────────────────────────────────────────

export function n2DisclosureItemIds(variant: N2DisclosureVariant) {
  const p = `N2-disclosure-${variant}`
  return {
    taxes: `${p}-taxes`,
    offsetNote: `${p}-offset-note`,
    conclusion: `${p}-conclusion`,
    syncedTables: `${p}-synced-tables`,
  } as const
}

// ─── 列定义（供 WpDisclosureSegmentTable）────────────────────────────────────

const AMT = 'amount' as const

export function n2ListedSegColumns(): WpSegColumn[] {
  return [
    { key: 'end', label: '期末余额', format: AMT, minWidth: 170 },
    { key: 'prior', label: '上年年末余额', format: AMT, minWidth: 170 },
  ]
}

export function n2SoeSegColumns(): WpSegColumn[] {
  return [
    { key: 'opening', label: '期初余额', format: AMT, minWidth: 160 },
    { key: 'payable', label: '本期应交', format: AMT, minWidth: 160 },
    { key: 'paid', label: '本期已交', format: AMT, minWidth: 160 },
    // 源模板 E 列是行内公式 =B8+C8-D8 → 只读公式列
    { key: 'end', label: '期末余额', format: AMT, minWidth: 170, readonly: true },
  ]
}

export function n2SegColumns(variant: N2DisclosureVariant): WpSegColumn[] {
  return variant === 'listed' ? n2ListedSegColumns() : n2SoeSegColumns()
}

/** 标签列表头（源模板：上市 `税  项` / 国企 `项  目`） */
export const N2_LABEL_HEADER = {
  listed: '税  项',
  soe: '项  目',
} as const satisfies Record<N2DisclosureVariant, string>

// ─── 工具 ────────────────────────────────────────────────────────────────────

function parseJsonArray<T>(raw: unknown): T[] | null {
  if (typeof raw !== 'string' || !raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : null
  } catch {
    return null
  }
}

// ─── 审定表→披露表预填纯函数（模块级导出，可独立单测）─────────────────────────

/**
 * 从审定表/明细表行数据为披露表预填值（纯函数）。
 *
 * - 归一：normalizeTaxLabel(row.taxType) → 匹配 13 固定行
 * - 同一规范名多行累加（如多种增值税子科目合并到「增值税」行）
 * - 仅填 null 格子（手工优先：非 null 的格子不覆盖）
 * - 上市版：end = Σ adjRow.endAudited, prior = Σ adjRow.beginAudited
 * - 国企版：从 detailRows 取 opening = Σ audBegin, payable = Σ audPayable,
 *           paid = Σ audPaid; end = computeN2SoeEnd({opening, payable, paid})
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
 */
export function prefillFromAdjudication(params: {
  variant: N2DisclosureVariant
  /** N2-1 审定表行数组（已落库的用户编辑结果） */
  adjRows: Array<{ taxType: string; beginAudited: number; endAudited: number }>
  /** N2-2 明细表行数组（国企版需要） */
  detailRows?: Array<{ taxType: string; audBegin: number; audPayable: number; audPaid: number }>
  /**
   * 后端 render `htmlData.adjudication_prefill`（四表 tb_balance 归集的**未审**数）。
   *
   * 🔴 **为什么需要它**：审定表 UI 显示的种子值来自本数组，而用户未点保存前
   * `checklist_responses` 里**没有** `N2-1-adjudication-rows` —— 若披露表只读 checklist，
   * 「四表入库 → 披露表有数据」这一段就是断的（2026-08-01 实测复现）。
   *
   * 口径：无 AJE/RJE 调整时「审定数 == 未审数」，故 `end_unadj → end`、
   * `begin_unadj → prior`（上市）/ `begin_unadj → opening`（国企）。
   * 优先级低于 `adjRows` / `detailRows`（后者是用户编辑过的结果）。
   */
  renderPrefill?: Array<{ tax_type?: string; taxType?: string; begin_unadj?: number; end_unadj?: number }>
  /** 现有行（已有值的格子不覆盖） */
  existingListedRows?: N2ListedRowModel[]
  existingSoeRows?: N2SoeRowModel[]
}): { listedRows?: N2ListedRowModel[]; soeRows?: N2SoeRowModel[] } {
  const { variant, adjRows, detailRows, renderPrefill, existingListedRows, existingSoeRows } = params

  // render prefill 归一为 adj 行形态（审定数 == 未审数，无调整时成立）
  const seededAdj = (renderPrefill ?? []).map((p) => ({
    taxType: String(p.tax_type ?? p.taxType ?? ''),
    beginAudited: Number(p.begin_unadj ?? 0) || 0,
    endAudited: Number(p.end_unadj ?? 0) || 0,
  }))

  if (variant === 'listed') {
    // 已落库的审定行优先；无则用四表种子
    const source = adjRows.length > 0 ? adjRows : seededAdj
    return { listedRows: _prefillListed(source, existingListedRows) }
  }

  // 国企版本期应交/已交只存在于 N2-2（源模板 N/O 列），审定表无此口径。
  // N2-2 未填时，至少用四表种子带出「期初余额」，本期应交/已交留空待录。
  const soeSource =
    (detailRows ?? []).length > 0
      ? detailRows!
      : seededAdj.map((r) => ({
          taxType: r.taxType,
          audBegin: r.beginAudited,
          audPayable: 0,
          audPaid: 0,
        }))
  return { soeRows: _prefillSoe(soeSource, existingSoeRows) }
}

function _prefillListed(
  adjRows: Array<{ taxType: string; beginAudited: number; endAudited: number }>,
  existing?: N2ListedRowModel[],
): N2ListedRowModel[] {
  // Start from existing rows or build default skeleton
  const rows: N2ListedRowModel[] = existing?.length
    ? existing.map((r) => ({ ...r }))
    : N2_LISTED_TAX_ITEMS.map((item) => ({ item, end: null, prior: null }))

  // Build accumulator: normalized label → { end, prior }
  const accum = new Map<string, { end: number; prior: number }>()
  for (const row of adjRows) {
    const label = normalizeTaxLabel(row.taxType)
    if (!label) continue
    const prev = accum.get(label) ?? { end: 0, prior: 0 }
    prev.end += (row.endAudited ?? 0)
    prev.prior += (row.beginAudited ?? 0)
    accum.set(label, prev)
  }

  // Apply to fixed rows (only null cells)
  const fixedLabels = new Set(N2_FIXED_TAX_LABELS)
  const usedLabels = new Set<string>()

  for (const row of rows) {
    const vals = accum.get(row.item)
    if (!vals) continue
    usedLabels.add(row.item)
    if (row.end === null || row.end === undefined) {
      row.end = Math.round(vals.end * 100) / 100
    }
    if (row.prior === null || row.prior === undefined) {
      row.prior = Math.round(vals.prior * 100) / 100
    }
  }

  // Dynamic rows: labels that didn't match any existing row (not in fixed labels either)
  for (const [label, vals] of accum) {
    if (usedLabels.has(label)) continue
    if (fixedLabels.has(label)) continue // already handled via skeleton
    // Check if row already exists with this label
    if (rows.some((r) => r.item === label)) continue
    rows.push({
      item: label,
      end: Math.round(vals.end * 100) / 100,
      prior: Math.round(vals.prior * 100) / 100,
      _editableLabel: true,
    })
  }

  return rows
}

function _prefillSoe(
  detailRows: Array<{ taxType: string; audBegin: number; audPayable: number; audPaid: number }>,
  existing?: N2SoeRowModel[],
): N2SoeRowModel[] {
  // Start from existing rows or build default skeleton
  const rows: N2SoeRowModel[] = existing?.length
    ? existing.map((r) => ({ ...r }))
    : N2_SOE_TAX_ITEMS.map((item) => ({ item, opening: null, payable: null, paid: null }))

  // Build accumulator: normalized label → { opening, payable, paid }
  const accum = new Map<string, { opening: number; payable: number; paid: number }>()
  for (const row of detailRows) {
    const label = normalizeTaxLabel(row.taxType)
    if (!label) continue
    const prev = accum.get(label) ?? { opening: 0, payable: 0, paid: 0 }
    prev.opening += (row.audBegin ?? 0)
    prev.payable += (row.audPayable ?? 0)
    prev.paid += (row.audPaid ?? 0)
    accum.set(label, prev)
  }

  // Apply to fixed rows (only null cells)
  const fixedLabels = new Set(N2_FIXED_TAX_LABELS)
  const usedLabels = new Set<string>()

  for (const row of rows) {
    const vals = accum.get(row.item)
    if (!vals) continue
    usedLabels.add(row.item)
    if (row.opening === null || row.opening === undefined) {
      row.opening = Math.round(vals.opening * 100) / 100
    }
    if (row.payable === null || row.payable === undefined) {
      row.payable = Math.round(vals.payable * 100) / 100
    }
    if (row.paid === null || row.paid === undefined) {
      row.paid = Math.round(vals.paid * 100) / 100
    }
    // end is NOT persisted — it's derived by computeN2SoeEnd at read time
  }

  // Dynamic rows: labels that didn't match any existing row
  for (const [label, vals] of accum) {
    if (usedLabels.has(label)) continue
    if (fixedLabels.has(label)) continue
    if (rows.some((r) => r.item === label)) continue
    rows.push({
      item: label,
      opening: Math.round(vals.opening * 100) / 100,
      payable: Math.round(vals.payable * 100) / 100,
      paid: Math.round(vals.paid * 100) / 100,
      _editableLabel: true,
    })
  }

  return rows
}

// ─── 主 composable ───────────────────────────────────────────────────────────

export interface UseN2DisclosureTablesOptions {
  variant: N2DisclosureVariant
  allResponses: Ref<Map<string, { conclusion?: string | null; remark?: string | null }>>
  /**
   * 后端 render `htmlData.adjudication_prefill`（四表归集的未审数，数组形态）。
   *
   * 🔴 缺它则「四表入库 → 披露表有数据」链路断裂：审定表的种子值在用户保存前
   * 不在 `checklist_responses` 里，披露表只读 checklist 会全空（2026-08-01 实测）。
   * 宿主须把 `props.htmlData?.adjudication_prefill` 传进来。
   */
  renderPrefill?: Ref<
    Array<{ tax_type?: string; taxType?: string; begin_unadj?: number; end_unadj?: number }> | null | undefined
  >
}

export function useN2DisclosureTables(opts: UseN2DisclosureTablesOptions) {
  const { variant, allResponses, renderPrefill } = opts
  const ID = n2DisclosureItemIds(variant)

  const listedRows = ref<N2ListedRowModel[]>([])
  const soeRows = ref<N2SoeRowModel[]>([])
  const offsetNote = ref('')
  const conclusionNote = ref('')
  const syncedTables = ref<string[]>([])

  function restore(): void {
    const saved = allResponses.value.get(ID.taxes)?.conclusion
    if (variant === 'listed') {
      const rows = parseJsonArray<N2ListedRowModel>(saved)
      if (rows?.length) {
        // 有持久化数据 → 直接用
        listedRows.value = rows
      } else {
        // 无持久化数据 → 构造默认骨架后从审定表带入；审定表未落库时用四表种子兜底
        const skeleton = N2_LISTED_TAX_ITEMS.map((item) => ({ item, end: null, prior: null } as N2ListedRowModel))
        const adjRaw = allResponses.value.get('N2-1-adjudication-rows')?.conclusion
        const adjRows = parseJsonArray<{ taxType: string; beginAudited: number; endAudited: number }>(adjRaw)
        const seeds = renderPrefill?.value ?? []
        if (adjRows?.length || seeds.length) {
          const result = prefillFromAdjudication({
            variant: 'listed',
            adjRows: adjRows ?? [],
            renderPrefill: seeds,
            existingListedRows: skeleton,
          })
          listedRows.value = result.listedRows ?? skeleton
        } else {
          listedRows.value = skeleton
        }
      }
    } else {
      const rows = parseJsonArray<N2SoeRowModel>(saved)
      if (rows?.length) {
        // 有持久化数据 → 直接用
        soeRows.value = rows
      } else {
        // 无持久化数据 → 构造默认骨架后从 N2-2 明细带入；未填时用四表种子带出期初
        const skeleton = N2_SOE_TAX_ITEMS.map((item) => ({ item, opening: null, payable: null, paid: null } as N2SoeRowModel))
        const detRaw = allResponses.value.get('N2-2-detail-rows')?.conclusion
        const detailRows = parseJsonArray<{ taxType: string; audBegin: number; audPayable: number; audPaid: number }>(detRaw)
        const seeds = renderPrefill?.value ?? []
        if (detailRows?.length || seeds.length) {
          const result = prefillFromAdjudication({
            variant: 'soe',
            adjRows: [],
            detailRows: detailRows ?? [],
            renderPrefill: seeds,
            existingSoeRows: skeleton,
          })
          soeRows.value = result.soeRows ?? skeleton
        } else {
          soeRows.value = skeleton
        }
      }
    }
    offsetNote.value = allResponses.value.get(ID.offsetNote)?.remark || ''
    conclusionNote.value = allResponses.value.get(ID.conclusion)?.remark || ''
    syncedTables.value = parseJsonArray<string>(allResponses.value.get(ID.syncedTables)?.conclusion) ?? []
  }

  /** 国企：带行内公式结果的展示行（`end` 由 `computeN2SoeEnd` 算出） */
  const soeRowsWithEnd = computed<N2SoeTaxRow[]>(() =>
    soeRows.value.map((r) => ({
      item: r.item,
      opening: nz(r.opening),
      payable: nz(r.payable),
      paid: nz(r.paid),
      end: computeN2SoeEnd(r),
    })),
  )

  // ── 合计（源模板 =SUM(B8:B22) 等）──────────────────────────────────────────

  const listedTotals = computed(() => ({
    end: sumNullable(listedRows.value.map((r) => nz(r.end))),
    prior: sumNullable(listedRows.value.map((r) => nz(r.prior))),
  }))

  const soeTotals = computed(() => ({
    opening: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.opening))),
    payable: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.payable))),
    paid: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.paid))),
    end: sumNullable(soeRowsWithEnd.value.map((r) => nz(r.end))),
  }))

  // ── 渲染段（单段平表：label 为空串 → 不渲染分组标题行）────────────────────

  const asSegRows = (rows: readonly object[]): WpSegment['rows'] =>
    rows as unknown as WpSegment['rows']

  const segments = computed<WpSegment[]>(() => [
    {
      key: 'main',
      label: '',
      rows: asSegRows(variant === 'listed' ? listedRows.value : soeRowsWithEnd.value),
      subtotal:
        variant === 'listed'
          ? { end: listedTotals.value.end, prior: listedTotals.value.prior }
          : {
              opening: soeTotals.value.opening,
              payable: soeTotals.value.payable,
              paid: soeTotals.value.paid,
              end: soeTotals.value.end,
            },
      subtotalLabel: N2_TOTAL_LABEL,
    },
  ])

  const columns = computed(() => n2SegColumns(variant))
  const labelHeader = computed(() => N2_LABEL_HEADER[variant])

  // ── 勾稽 ──────────────────────────────────────────────────────────────────

  const checks = computed<WpCheckResult[]>(() =>
    variant === 'listed'
      ? runN2ListedChecks(listedRows.value, listedTotals.value)
      : runN2SoeChecks(soeRowsWithEnd.value, soeTotals.value),
  )

  // ── 行增删 ────────────────────────────────────────────────────────────────

  function addRow(): void {
    if (variant === 'listed') {
      listedRows.value = [
        ...listedRows.value,
        { item: '', end: null, prior: null, _editableLabel: true },
      ]
    } else {
      soeRows.value = [
        ...soeRows.value,
        { item: '', opening: null, payable: null, paid: null, _editableLabel: true },
      ]
    }
  }

  function removeRow(index: number): void {
    if (variant === 'listed') {
      listedRows.value = listedRows.value.filter((_, i) => i !== index)
    } else {
      soeRows.value = soeRows.value.filter((_, i) => i !== index)
    }
  }

  function setCell(index: number, key: string, value: number | string): void {
    const target = variant === 'listed' ? listedRows : soeRows
    const row = (target.value as Array<Record<string, unknown>>)[index]
    if (!row) return
    row[key] = value
  }

  function setLabel(index: number, value: string): void {
    const target = variant === 'listed' ? listedRows : soeRows
    const row = (target.value as Array<{ item: string }>)[index]
    if (!row) return
    row.item = value
  }

  /** 持久化载荷（国企不存 `end` —— 它是行内公式派生值，存了会变双真源） */
  function serializeRows(): string {
    return JSON.stringify(variant === 'listed' ? listedRows.value : soeRows.value)
  }

  // ── 同步载荷 ──────────────────────────────────────────────────────────────

  function buildSnapshot(): N2DisclosureSnapshot {
    const strip = <T extends { _editableLabel?: boolean }>(r: T) => {
      const { _editableLabel, ...rest } = r
      return rest
    }
    return {
      taxRows:
        variant === 'listed'
          ? listedRows.value.map(strip) as N2ListedTaxRow[]
          : soeRowsWithEnd.value,
      notes: {
        ...(offsetNote.value.trim() ? { offset: offsetNote.value } : {}),
        ...(conclusionNote.value.trim() ? { conclusion: conclusionNote.value } : {}),
      },
      previouslySyncedTables: syncedTables.value,
    }
  }

  function buildPayload(ctx: { wpId: string; year: number }) {
    return buildN2SyncPayload(variant, buildSnapshot(), ctx)
  }

  return {
    listedRows,
    soeRows,
    soeRowsWithEnd,
    offsetNote,
    conclusionNote,
    syncedTables,
    listedTotals,
    soeTotals,
    segments,
    columns,
    labelHeader,
    checks,
    addRow,
    removeRow,
    setCell,
    setLabel,
    serializeRows,
    restore,
    buildSnapshot,
    buildPayload,
    itemIds: ID,
    noteColumns: computed(() => n2ColumnsFor(variant)),
  }
}
