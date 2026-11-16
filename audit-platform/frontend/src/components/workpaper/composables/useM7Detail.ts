/**
 * useM7Detail — M7-2 专项储备明细表（**模板驱动**）
 *
 * spec: `m-cycle-key-naming-unification` §R12（M3/M5/M7 行模型重建）
 *
 * ═══ 为什么重写 ═══
 *
 * 原实现的行模型与权威模板是**两张不同的表**：
 * 模板是「项目 + 未审数(期初/增加/减少/期末) + 期初调整 + 账项调整 + 重分类调整 + 审定数 + 文件依据/索引号/备注」共 18 列、**固定 7 行**；
 * 而原前端只有 25 行键，与契约列交集 仅 remark。
 * 两张表的键名谈不上「对齐」，只能重建。
 *
 * ═══ 现在的形态 ═══
 *
 * * 列、两级表头、editable/formula、行标签 全部来自生成文件
 *   `m-cycle/mCycleDetailColumns.generated.ts`（真源 = provider 的 `DETAIL_FIELDS` / `DETAIL_SHEET`
 *   + 权威 xlsx 的行标签）；
 * * 行就是模板的固定行，`row_identity_kind = template_row_key`
 *   意味着模板没有多余行位 ⇒ **没有新增/删除行**；
 * * **公式列不在前端重算**：模板那些格子是公式，由 OO 侧重算后回流；
 *   前端重复实现一份就必然与模板漂移。
 */
import { computed, ref, type ComputedRef } from 'vue'
import type { useM7FormData } from './useM7FormData'
import { M_CYCLE_DETAIL_COLUMNS } from '../m-cycle/mCycleDetailColumns.generated'

// ─── Types ──────────────────────────────────────────────────────────

/** 明细表行：键 = provider 的 `jsonKey`，另有 `key` 作前端行身份。 */
export type M7DetailRow = Record<string, string | number | null>

/** 模板固定行标签（来自生成文件，不写死）。 */
const M7_ROW_LABELS: string[] = M_CYCLE_DETAIL_COLUMNS.M7?.rowLabels ?? []

/** 可录入的字段（`mode === 'editable'`）。 */
const M7_EDITABLE_FIELDS = (M_CYCLE_DETAIL_COLUMNS.M7?.fields ?? []).filter(
  (f) => f.mode === 'editable',
)

// ─── Composable ─────────────────────────────────────────────────────────

/** 按模板固定行标签建空行。 */
export function createM7EmptyRows(): M7DetailRow[] {
  return M7_ROW_LABELS.map((label, index) => {
    const row: M7DetailRow = { key: `m7-fixed-${index}` }
    for (const f of M7_EDITABLE_FIELDS) row[f.jsonKey] = f.valueType === 'amount' ? 0 : ''
    // 行标签就是模板 A 列，它是行身份：有标签就写死，留白行保持空
    if (label) row[M7_EDITABLE_FIELDS[0]?.jsonKey ?? 'projectName'] = label
    return row
  })
}

/**
 * M7-2 专项储备明细表 业务逻辑（模板驱动、固定行、无前端重算）
 */
export function useM7Detail(
  formData: ReturnType<typeof useM7FormData>,
  detailRows: { value: M7DetailRow[] },
) {
  const { debouncedSave } = formData

  /** 模板列定义（供宿主渲染两级表头） */
  const columns = computed(() => M_CYCLE_DETAIL_COLUMNS.M7?.fields ?? [])

  /** 模板固定行标签 */
  const rowLabels: ComputedRef<string[]> = computed(() => M7_ROW_LABELS)

  /** 当前行 */
  const rows: ComputedRef<M7DetailRow[]> = computed(() => detailRows.value)

  /** 按字段求和（仅供校验展示，不作为模板值） */
  function columnTotal(jsonKey: string): number {
    return detailRows.value.reduce((sum, r) => {
      const n = Number(r[jsonKey] ?? 0)
      return sum + (Number.isFinite(n) ? n : 0)
    }, 0)
  }

  /** 行数不足模板时补齐（多出的不删） */
  function ensureTemplateRows(): void {
    const empty = createM7EmptyRows()
    if (detailRows.value.length >= empty.length) return
    detailRows.value = [...detailRows.value, ...empty.slice(detailRows.value.length)]
  }

  /** 更新某行某字段 */
  function updateRow(index: number, jsonKey: string, value: string | number): void {
    const row = detailRows.value[index]
    if (!row) return
    row[jsonKey] = value
    _triggerSave(index)
  }

  // ─── 保存触发 ──────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    // 逐行 JSON（任务 4 后的唯一来源）：键名就是 provider 声明的 jsonKey
    debouncedSave(`M7-2-row-${rowIndex + 1}-data`, {
      remark: JSON.stringify(row),
    })
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < detailRows.value.length; i++) _triggerSave(i)
  }

  // ─── Return ────────────────────────────────────────────

  return {
    columns,
    rowLabels,
    rows,
    columnTotal,
    updateRow,
    ensureTemplateRows,
    saveAll: _triggerSaveAll,
  }
}

export default useM7Detail
