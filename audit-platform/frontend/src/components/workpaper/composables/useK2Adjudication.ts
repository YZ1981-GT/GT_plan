/**
 * useK2Adjudication — K2-1 其他流动资产审定表 composable（**动态明细行**）
 *
 * 科目：其他流动资产（报表行 `BS-014` → `TB('1901','期末余额')`）。
 * 🔴 历史实现把科目写成 `1231`（那是应收款项坏账准备），且明细行**硬编码 8 行**
 * —— 详见 `k2AdjudicationRows.ts` 与后端 `_k2_other_current_assets.py` 的说明。
 *
 * 行模型：源模板「根据实际情况列示；不存在的项目请删除」→ 行清单持久化在
 * `K2-1-rows`，各列值仍在 `K2-1-{rowId}-{field}`。历史固定行按旧 rowKey 迁移，
 * 既有金额零丢失（`migrateLegacyFixedRows`）。
 *
 * 公式（`useK2FormulaEngine` 纯函数）：
 * - 资产类期末 = 期初 + 借方 − 贷方
 * - 审定数 = 未审 + AJE + RJE
 * - 合计 = Σ 全部动态行（不是 Σ 固定 8 行）
 * - 三角勾稽差额 = 期末 − (期初 + 借 − 贷)
 *
 * Spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 3.2
 * Requirements: 2.1, 2.2, 2.3, 2.6, 2.7, 2.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from './useK2FormulaEngine'
import { K2_ADJ_ROWS_SPEC } from './k2AdjudicationRows'
import {
  appendManualRow,
  collectRowItemIds,
  deserializeRows,
  dropRow,
  findDuplicateLabel,
  foreignRowWarning,
  normalizeLabel,
  readNum,
  readRaw,
  renameRowLabel,
  resolveInitialRows,
  rowFieldItemId,
  rowsItemId,
  seedRowsFromPrefill,
  serializeRows,
  type DynamicAdjRow,
  type DynamicRowPrefillItem,
} from './shared/dynamicAdjudicationRows'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K2AdjRow {
  /** 行标识（动态行的 `rowId`；合计行为 `subtotal`） */
  rowKey: string
  label: string
  begin: number
  debit: number
  credit: number
  end: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  changeRate: number | null
  remark: string
  /** 行来源（合计行为 `undefined`） */
  source?: DynamicAdjRow['source']
  /** 该行属于别的报表行时的警示文案（历史遗留行） */
  foreignWarning?: string | null
}

export interface K2ReconciliationResult {
  diff: number
  isBalanced: boolean
}

/** 增删改的结果（供 UI 提示） */
export interface K2RowMutationResult {
  ok: boolean
  message?: string
  rowId?: string
}

/** 「从 K2-2 明细带入」结果 */
export interface K2PullFromDetailResult {
  /** 已写入未审数的行数 */
  filled: number
  /** 因审定表原无该项目而新建的行数 */
  created: number
  /** 明细表有该项目但金额为 0 且审定表无对应行 → 不建空行（宁缺勿造） */
  unmatched: string[]
}

const SPEC = K2_ADJ_ROWS_SPEC
const ROWS_ITEM_ID = rowsItemId(SPEC)

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK2Adjudication(
  allResponses: Ref<Map<string, any>>,
  options?: {
    prefill?: Ref<DynamicRowPrefillItem[] | undefined>
    onSave?: (itemId: string, value: any) => void
    /** 删除行时清理该行全部字段键（未提供则只从本地 Map 移除） */
    onRemove?: (itemIds: string[]) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  /** 动态行清单（唯一行集真源） */
  const rowDefs = ref<DynamicAdjRow[]>([])

  // ─── 行清单加载 / 持久化 ───────────────────────────────────────────────────

  function persistRowDefs(): void {
    const payload = serializeRows(rowDefs.value)
    allResponses.value.set(ROWS_ITEM_ID, {
      item_id: ROWS_ITEM_ID,
      conclusion: null,
      remark: payload,
    })
    options?.onSave?.(ROWS_ITEM_ID, payload)
  }

  /**
   * 加载行清单：持久化清单优先，其次迁移历史固定行（**只迁有数据的行**）。
   * 迁移结果立即落库，避免每次加载重算。
   */
  function loadRowDefs(): void {
    const stored = deserializeRows(readRaw(allResponses.value, ROWS_ITEM_ID))
    if (stored.length > 0) {
      rowDefs.value = stored
      return
    }
    const { rows, migrated } = resolveInitialRows(SPEC, allResponses.value)
    rowDefs.value = rows
    if (migrated) persistRowDefs()
  }

  // ─── 四表库预填（宁缺勿造：无科目 → 不建行、不塞「其他」兜底行） ───────────

  function seedFromPrefill(): boolean {
    const pf = options?.prefill?.value
    if (!pf || pf.length === 0) return false
    const { rows, values } = seedRowsFromPrefill(SPEC, pf, rowDefs.value, {
      opening: 'begin',
      closing: 'unadj',
    })
    let touched = false
    for (const [itemId, value] of Object.entries(values)) {
      // 手工优先：已有非零值不覆盖
      if (readNum(allResponses.value, itemId) !== 0) continue
      allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: value })
      options?.onSave?.(itemId, value)
      touched = true
    }
    if (rows.length !== rowDefs.value.length) {
      rowDefs.value = rows
      persistRowDefs()
      touched = true
    }
    return touched
  }

  // ─── Row Builder ───────────────────────────────────────────────────────────

  function buildRow(def: DynamicAdjRow): K2AdjRow {
    const at = (field: string) => readNum(allResponses.value, rowFieldItemId(SPEC, def.rowId, field))
    const begin = at('begin')
    const debit = at('debit')
    const credit = at('credit')
    const unadjusted = at('unadj')
    const aje = at('aje')
    const rje = at('rje')
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    return {
      rowKey: def.rowId,
      label: def.label,
      begin,
      debit,
      credit,
      end: calcAssetEndBalance(begin, debit, credit),
      unadjusted,
      aje,
      rje,
      audited,
      changeRate: calcChangeRate(audited, at('prior-audited')),
      remark: readRaw(allResponses.value, rowFieldItemId(SPEC, def.rowId, 'remark')),
      source: def.source,
      foreignWarning: foreignRowWarning(SPEC, def),
    }
  }

  // ─── Computed Rows ─────────────────────────────────────────────────────────

  const rows: ComputedRef<K2AdjRow[]> = computed(() => rowDefs.value.map(buildRow))

  /** 合计行 —— 覆盖**全部**动态行（Property 9） */
  const subtotalRow: ComputedRef<K2AdjRow> = computed(() => {
    const r = rows.value
    const audited = calcSubtotal(r.map((x) => x.audited))
    const priorSum = calcSubtotal(
      rowDefs.value.map((d) =>
        readNum(allResponses.value, rowFieldItemId(SPEC, d.rowId, 'prior-audited')),
      ),
    )
    return {
      rowKey: 'subtotal',
      label: '合计',
      begin: calcSubtotal(r.map((x) => x.begin)),
      debit: calcSubtotal(r.map((x) => x.debit)),
      credit: calcSubtotal(r.map((x) => x.credit)),
      end: calcSubtotal(r.map((x) => x.end)),
      unadjusted: calcSubtotal(r.map((x) => x.unadjusted)),
      aje: calcSubtotal(r.map((x) => x.aje)),
      rje: calcSubtotal(r.map((x) => x.rje)),
      audited,
      changeRate: calcChangeRate(audited, priorSum),
      remark: '',
    }
  })

  // ─── Triangle Reconciliation ───────────────────────────────────────────────

  const reconciliation: ComputedRef<K2ReconciliationResult> = computed(() => {
    const st = subtotalRow.value
    const diff = calcTriangleReconciliation(st.begin, st.debit, st.credit, st.end)
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── 单元格更新 ────────────────────────────────────────────────────────────

  function updateField(rowKey: string, field: string, value: number | string): void {
    const itemId = rowFieldItemId(SPEC, rowKey, field)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: String(value) })
    options?.onSave?.(itemId, String(value))
  }

  // ─── 动态行增 / 改名 / 删 ──────────────────────────────────────────────────

  /** 新增项目行（调用方负责先取到行名，如 `ElMessageBox.prompt`） */
  function addRow(label: string): K2RowMutationResult {
    const name = normalizeLabel(label)
    if (!name) return { ok: false, message: '项目名称不能为空' }
    const dup = findDuplicateLabel(rowDefs.value, name)
    if (dup) return { ok: false, message: `已存在同名项目行「${dup.label}」` }
    const { rows: next, row } = appendManualRow(rowDefs.value, name)
    rowDefs.value = next
    persistRowDefs()
    return { ok: true, rowId: row.rowId }
  }

  /** 行名改写（撞名拒绝；行名是附注/明细带入的匹配键，必须唯一） */
  function renameRow(rowId: string, label: string): K2RowMutationResult {
    const name = normalizeLabel(label)
    if (!name) return { ok: false, message: '项目名称不能为空' }
    const dup = findDuplicateLabel(rowDefs.value, name, rowId)
    if (dup) return { ok: false, message: `已存在同名项目行「${dup.label}」` }
    const before = rowDefs.value.find((r) => r.rowId === rowId)?.label
    if (before === name) return { ok: true, rowId }
    rowDefs.value = renameRowLabel(rowDefs.value, rowId, name)
    persistRowDefs()
    return { ok: true, rowId }
  }

  /** 删除行 + 清理该行全部字段键（其它行不受影响） */
  function removeRow(rowId: string): K2RowMutationResult {
    const { rows: next, removedItemIds } = dropRow(
      SPEC,
      rowDefs.value,
      allResponses.value,
      rowId,
    )
    if (next.length === rowDefs.value.length) return { ok: false, message: '该行不存在' }
    rowDefs.value = next
    for (const id of removedItemIds) allResponses.value.delete(id)
    options?.onRemove?.(removedItemIds)
    persistRowDefs()
    return { ok: true, rowId }
  }

  /** 该行在 `allResponses` 中的全部字段键（供 UI 展示删除影响面） */
  function rowItemIds(rowId: string): string[] {
    return collectRowItemIds(SPEC, allResponses.value, rowId)
  }

  // ─── 从 K2-2 明细表带入（按**行名**聚合，不做模糊包含匹配） ─────────────────

  /**
   * 从 K2-2 明细表按项目名称聚合期末余额 → 写入审定表未审数。
   *
   * 与旧实现的差别：旧实现按「性质」模糊包含匹配固定行、匹配不上就丢弃；
   * 现在按**行名精确匹配**（规范化后），审定表没有该项目时**自动建行**
   * —— 明细表本就是动态行，审定表跟着它长才是「按实际情况列示」。
   */
  function pullFromDetail(): K2PullFromDetailResult {
    const raw = readRaw(allResponses.value, 'K2-2-rows')
    const out: K2PullFromDetailResult = { filled: 0, created: 0, unmatched: [] }
    if (!raw) return out
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      return out
    }
    if (!Array.isArray(parsed) || parsed.length === 0) return out

    // 按项目名归集期末余额（同名合并）
    const byName = new Map<string, number>()
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue
      const rec = item as Record<string, unknown>
      const name = normalizeLabel(rec.name as string)
      if (!name) continue
      const end = Number(rec.endBalance ?? 0)
      byName.set(name, (byName.get(name) ?? 0) + (Number.isFinite(end) ? end : 0))
    }

    for (const [name, amount] of byName) {
      let row = findDuplicateLabel(rowDefs.value, name)
      if (!row) {
        if (amount === 0) { out.unmatched.push(name); continue }
        const { rows: next, row: created } = appendManualRow(rowDefs.value, name)
        rowDefs.value = next
        row = created
        out.created++
      }
      updateField(row.rowId, 'unadj', amount)
      out.filled++
    }
    if (out.created > 0) persistRowDefs()
    return out
  }

  // ─── Audit Note / Conclusion ───────────────────────────────────────────────

  watch(
    () => allResponses.value.get(`${SPEC.prefix}-audit-note`)?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(`${SPEC.prefix}-audit-conclusion`)?.remark,
    (v) => { auditConclusion.value = v || '' },
    { immediate: true },
  )

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => loadRowDefs(), { immediate: true, deep: false })
  watch(() => options?.prefill?.value, () => seedFromPrefill(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    rowDefs,
    subtotalRow,
    reconciliation,
    auditNote,
    auditConclusion,
    updateField,
    addRow,
    renameRow,
    removeRow,
    rowItemIds,
    pullFromDetail,
    seedFromPrefill,
    loadRowDefs,
  }
}
