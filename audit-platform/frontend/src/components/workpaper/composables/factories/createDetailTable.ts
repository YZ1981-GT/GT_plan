/**
 * createDetailTable — 参数化工厂：明细表 composable
 *
 * Feature: platform-global-hardening
 * Requirements: 6.5, 6.6
 *
 * 用于收敛 useD2Detail / useF1Detail / useG1Detail 等同构实现。
 * 每个循环底稿的明细表 composable 结构相同：
 *   - 行管理（增/删/设置）
 *   - 合计行自动计算（对指定数字字段求和）
 *   - 账龄字段自动合计（若配置）
 *   - 搜索/筛选
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ColumnDef {
  /** 字段 key */
  key: string
  /** 列标题 */
  label: string
  /** 是否为数字列（参与合计） */
  numeric?: boolean
  /** 是否为账龄列 */
  aging?: boolean
  /** 是否只读（计算列） */
  readonly?: boolean
  /** 最小宽度 */
  minWidth?: number
}

export interface DetailTableConfig<R extends Record<string, unknown> = Record<string, unknown>> {
  /** 列定义 */
  columns: ColumnDef[]
  /** 新行默认值工厂 */
  defaultRow: () => R
  /** 需要合计的字段名列表（若不指定则从 columns numeric=true 推导） */
  totalFields?: string[]
  /** 账龄字段名列表（若不指定则从 columns aging=true 推导） */
  agingFields?: string[]
}

export interface DetailTableReturn<R extends Record<string, unknown> = Record<string, unknown>> {
  /** 当前行数据 */
  rows: Ref<R[]>
  /** 合计行（按 totalFields 汇总） */
  totals: ComputedRef<Record<string, number>>
  /** 行数 */
  rowCount: ComputedRef<number>
  /** 添加一行（尾部） */
  addRow: (initial?: Partial<R>) => void
  /** 删除指定行 */
  removeRow: (index: number) => void
  /** 批量设置行数据（替换全部） */
  setRows: (data: R[]) => void
  /** 更新指定行的字段 */
  updateRow: (index: number, field: keyof R, value: unknown) => void
  /** 插入一行到指定位置 */
  insertRow: (index: number, initial?: Partial<R>) => void
  /** 清空所有行 */
  clearRows: () => void
  /** 列定义（透传给模板） */
  columnDefs: ColumnDef[]
}

// ─── Factory ─────────────────────────────────────────────────────────────────

export function createDetailTable<R extends Record<string, unknown> = Record<string, unknown>>(
  config: DetailTableConfig<R>,
): DetailTableReturn<R> {
  const { columns, defaultRow, totalFields, agingFields } = config

  // 推导合计字段
  const numericFields: string[] = totalFields
    ?? columns.filter(c => c.numeric).map(c => c.key)

  // 推导账龄字段
  const agingFieldNames: string[] = agingFields
    ?? columns.filter(c => c.aging).map(c => c.key)

  // 合并所有需要合计的字段
  const allSumFields = [...new Set([...numericFields, ...agingFieldNames])]

  const rows = ref<R[]>([]) as Ref<R[]>

  const rowCount = computed(() => rows.value.length)

  const totals = computed<Record<string, number>>(() => {
    const result: Record<string, number> = {}
    for (const field of allSumFields) {
      result[field] = 0
    }
    for (const row of rows.value) {
      for (const field of allSumFields) {
        const val = Number((row as any)[field])
        if (!isNaN(val)) {
          result[field] += val
        }
      }
    }
    return result
  })

  function addRow(initial?: Partial<R>): void {
    const newRow = { ...defaultRow(), ...initial } as R
    rows.value.push(newRow)
  }

  function removeRow(index: number): void {
    if (index >= 0 && index < rows.value.length) {
      rows.value.splice(index, 1)
    }
  }

  function insertRow(index: number, initial?: Partial<R>): void {
    const newRow = { ...defaultRow(), ...initial } as R
    if (index < 0) index = 0
    if (index > rows.value.length) index = rows.value.length
    rows.value.splice(index, 0, newRow)
  }

  function setRows(data: R[]): void {
    rows.value = [...data]
  }

  function updateRow(index: number, field: keyof R, value: unknown): void {
    if (index >= 0 && index < rows.value.length) {
      ;(rows.value[index] as any)[field] = value
    }
  }

  function clearRows(): void {
    rows.value = []
  }

  return {
    rows,
    totals,
    rowCount,
    addRow,
    removeRow,
    setRows,
    updateRow,
    insertRow,
    clearRows,
    columnDefs: columns,
  }
}
