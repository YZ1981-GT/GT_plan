/**
 * useK10Detail — K10-2 明细表逻辑（12列11公式，按补助项目逐项管理）
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 3.4
 * Requirements: 3.1-3.4
 *
 * 职责：
 * - 动态行管理（新增/删除/重排序），每行代表一笔其他收益明细
 * - 12列：项目/类型/判断依据/本期未审/本期AJE/重分类/审定/上年同期未审/上年AJE/上年审定/文件索引号/备注
 * - 行级审定 = 未审 + AJE + RJE
 * - 合计行联动审定表（存储 "K10-2-subtotal" 供CrossSheet交叉验证）
 * - 导入/导出集成钩子
 *
 * 科目：6117其他收益（**损益类/贷方科目**）
 * Item IDs: "K10-2-detail-rows", "K10-2-subtotal"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcYoYChange,
  calcSubtotal,
} from './useK10FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行存储结构 */
export interface K10DetailRow {
  rowKey: string
  /** 序号 */
  seq: number
  /** 补助项目名称 */
  projectName: string
  /** 补助类型（即征即退/财政贴息/研发补助/稳岗补贴/其他） */
  grantType: string
  /** 判断依据 */
  judgmentBasis: string
  /** 本期未审数 */
  unadjusted: number
  /** 本期AJE调整 */
  aje: number
  /** 本期RJE重分类 */
  rje: number
  /** 本期审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 上年同期未审数 */
  priorUnadj: number
  /** 上年同期AJE */
  priorAje: number
  /** 上年同期审定数（公式：上年未审+上年AJE） */
  priorAudited: number
  /** 文件索引号 */
  fileRef: string
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

export interface K10DetailSubtotal {
  unadjusted: number
  aje: number
  rje: number
  audited: number
  priorUnadj: number
  priorAje: number
  priorAudited: number
}

export interface UseK10DetailParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K10-2-detail-rows'
const ITEM_PREFIX = 'K10-2'

/** 补助类型选项 */
export const GRANT_TYPE_OPTIONS = [
  '即征即退',
  '财政贴息',
  '研发补助',
  '稳岗补贴',
  '其他',
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK10Detail(params: UseK10DetailParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K10DetailRow[]>([])
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map((r, idx) => _normalizeRow(r, idx))
    } else {
      rows.value = []
    }
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): K10DetailRow {
    const unadjusted = parseNum(raw.unadjusted)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorUnadj = parseNum(raw.priorUnadj)
    const priorAje = parseNum(raw.priorAje)
    const priorAudited = calcAuditedAmount(priorUnadj, priorAje, 0)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: idx + 1,
      projectName: raw.projectName ?? '',
      grantType: raw.grantType ?? '',
      judgmentBasis: raw.judgmentBasis ?? '',
      unadjusted,
      aje,
      rje,
      audited,
      priorUnadj,
      priorAje,
      priorAudited,
      fileRef: raw.fileRef ?? '',
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<K10DetailRow[]> = computed(() => {
    return rows.value.map((row, idx) => {
      const audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      const priorAudited = calcAuditedAmount(row.priorUnadj, row.priorAje, 0)
      return { ...row, seq: idx + 1, audited, priorAudited }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotal: ComputedRef<K10DetailSubtotal> = computed(() => {
    const detail = computedRows.value
    const unadjusted = calcSubtotal(detail.map(r => r.unadjusted))
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorUnadj = calcSubtotal(detail.map(r => r.priorUnadj))
    const priorAje = calcSubtotal(detail.map(r => r.priorAje))
    const priorAudited = calcAuditedAmount(priorUnadj, priorAje, 0)
    return { unadjusted, aje, rje, audited, priorUnadj, priorAje, priorAudited }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K10DetailRow): void {
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.priorAudited = calcAuditedAmount(row.priorUnadj, row.priorAje, 0)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(projectName: string, grantType: string = ''): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seq: rows.value.length + 1,
      projectName,
      grantType,
      judgmentBasis: '',
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      priorUnadj: 0,
      priorAje: 0,
      priorAudited: 0,
      fileRef: '',
      remark: '',
      isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = rows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      isChanged.value = true
      _persist()
    }
  }

  function reorderRow(fromIdx: number, toIdx: number): void {
    if (isReadonly?.value) return
    if (fromIdx < 0 || toIdx < 0 || fromIdx >= rows.value.length || toIdx >= rows.value.length) return
    const [moved] = rows.value.splice(fromIdx, 1)
    rows.value.splice(toIdx, 0, moved)
    isChanged.value = true
    _persist()
  }

  // ─── 批量导入（导入导出支持） ─────────────────────────────────────────────

  function importRows(data: Array<Partial<K10DetailRow>>): void {
    if (isReadonly?.value) return
    const imported = data.map((r, idx) => _normalizeRow(r, rows.value.length + idx))
    rows.value.push(...imported)
    isChanged.value = true
    _persist()
  }

  function exportRows(): K10DetailRow[] {
    return computedRows.value
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 同步审定合计供CrossSheet使用（K10-1↔K10-2交叉验证）
    onSave(`${ITEM_PREFIX}-subtotal`, subtotal.value.audited)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    subtotal,
    isChanged,
    updateCell,
    addRow,
    removeRow,
    reorderRow,
    importRows,
    exportRows,
    initFromResponses,
  }
}

export default useK10Detail
