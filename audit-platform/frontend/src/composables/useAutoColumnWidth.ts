/**
 * useAutoColumnWidth — 根据实际数据内容动态计算列宽
 *
 * 同时适用于 el-table（:width 绑定）与 el-table-v2（VirtualColumn.width）。
 *
 * 为什么不用 element-plus 的 `table-layout="auto"`：
 *   上游 issue #19737（至今 OPEN）——`table-layout="auto"` 叠加带 `width` 的
 *   fixed 列会渲染错位；且 el-table-v2 根本不是 <table> 元素（div 绝对定位，
 *   虚拟滚动靠固定列宽算位置），压根不支持 table-layout。故走内容测量路线。
 *
 * 宽度来源取三者最大值：表头文字 / 该列所有数据的最长文本 / 列声明的 minWidth，
 * 再截到 maxWidth。超过 maxWidth 的文本由 CSS 负责折行（见 global.css 文本列折行段）。
 *
 * 用法（数值列，向后兼容的旧签名）：
 * ```ts
 * const { colWidth } = useAutoColumnWidth({
 *   rows: computed(() => flatRows),
 *   columns: [
 *     { field: 'amount', header: '未审数' },
 *     { field: 'adj',    header: '账项调整' },
 *   ],
 *   formatter: (val) => fmtAmount(val),
 * })
 * // 模板：<el-table-column :width="colWidth('amount')" ...>
 * ```
 *
 * 用法（混合文本/数值列 + 撑满容器）：
 * ```ts
 * const { colWidth, totalWidth } = useAutoColumnWidth({
 *   rows: filteredRows,
 *   columns: [
 *     { field: 'customerName', header: '客户名称', type: 'text', maxWidth: 240 },
 *     { field: 'amount',       header: '期末审定', type: 'number' },
 *   ],
 *   formatter: (v) => fmtAmount(v),      // 仅 number 列使用
 *   containerWidth: 1200,                // 总宽不足时按比例放大撑满
 * })
 * ```
 */
import { computed, unref, type Ref, type ComputedRef } from 'vue'

/** 可以是裸值，也可以是 ref/computed（不依赖 vue 的 MaybeRef 导出，避免版本差异） */
type Unwrappable<T> = T | Ref<T> | ComputedRef<T>

/** 列的内容类型：决定用哪套字符宽度，以及空值如何取文本 */
export type AutoColType = 'text' | 'number'

export interface AutoColDef {
  /** 行数据中的字段名 */
  field: string
  /** 列表头文字（用于计算表头最小宽度） */
  header: string
  /**
   * 列内容类型，默认 'number'（保持旧行为：空值走 formatter(0)）。
   * 'text' 时空值按空串处理，不会被 formatter 变成 "0.00"。
   */
  type?: AutoColType
  /** 该列专属格式化函数，优先于全局 formatter */
  formatter?: (value: any, row?: Record<string, any>) => string
  /** 覆盖该列最小宽度（默认 defaultMinWidth） */
  minWidth?: number
  /** 覆盖该列最大宽度（默认 defaultMaxWidth） */
  maxWidth?: number
  /** 该列不参与容器撑满的按比例放大（如序号/操作列宽度应固定） */
  noGrow?: boolean
}

export interface UseAutoColumnWidthOptions {
  /** 响应式数据行（所有行平铺，含合计行） */
  rows: Ref<Record<string, any>[]> | ComputedRef<Record<string, any>[]>
  /** 需要自适应的列定义（可传数组，或随配置动态变化的 ref/computed） */
  columns: Unwrappable<AutoColDef[]>
  /**
   * 值格式化函数（将原始值转为显示文本，用于估算宽度）。
   * 仅作用于 type==='number' 且未声明列级 formatter 的列。
   */
  formatter?: (value: any) => string
  /** 数据字符像素宽度，默认 6.2（Arial Narrow 12px） */
  charWidth?: number
  /** 表头字符像素宽度，默认 8（系统 UI 字体 13px，非 Arial Narrow） */
  headerCharWidth?: number
  /** cell 两侧 padding + border 余量，默认 16px */
  cellPadding?: number
  /** 全局最小列宽，默认 56px */
  defaultMinWidth?: number
  /** 全局最大列宽，默认 180px */
  defaultMaxWidth?: number
  /**
   * 容器可用宽度。给定时，若各列算出的总宽小于容器宽度，
   * 剩余空间按各列宽度比例分配给可放大的列（避免表格右侧留白）。
   */
  containerWidth?: Unwrappable<number>
  /**
   * 扫描行数上限，默认 500。超大数据集只测前 N 行，避免每次重算遍历十万行。
   */
  sampleLimit?: number
}

/**
 * 估算文本像素宽度。
 * CJK 汉字/全角标点按 1.7 倍 ASCII 宽度计（Arial Narrow 下的经验值）。
 */
function measureTextWidth(text: string, charW: number): number {
  let width = 0
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i)
    // CJK 统一汉字 / 全角标点 / 全角数字字母
    if (code > 0x2e7f) {
      width += charW * 1.7
    } else {
      width += charW
    }
  }
  return width
}

/** 把任意值转成用于测宽的显示文本 */
function toDisplayText(
  raw: any,
  col: AutoColDef,
  row: Record<string, any> | undefined,
  globalFormatter: ((value: any) => string) | undefined,
): string {
  if (col.formatter) return col.formatter(raw, row) ?? ''

  const type = col.type ?? 'number'
  if (type === 'text') {
    // 文本列：空值就是空串，不能交给数值 formatter 变成 "0.00"
    if (raw == null) return ''
    if (typeof raw === 'boolean') return raw ? '是' : '-'
    return String(raw)
  }

  // 数值列：保持旧行为 formatter(raw ?? 0)
  if (globalFormatter) return globalFormatter(raw ?? 0) ?? ''
  return raw == null ? '' : String(raw)
}

export function useAutoColumnWidth(options: UseAutoColumnWidthOptions) {
  const {
    rows,
    formatter,
    charWidth = 6.2,
    headerCharWidth = 8,
    cellPadding = 16,
    defaultMinWidth = 56,
    defaultMaxWidth = 180,
    sampleLimit = 500,
  } = options

  /** 列定义（支持传入 ref/computed，便于列集合随账龄配置等动态变化） */
  const cols = computed<AutoColDef[]>(() => unref(options.columns) ?? [])

  /** 内容测量得出的原始宽度（未做容器撑满） */
  const rawWidths: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}
    const data = rows.value ?? []
    const scanCount = Math.min(data.length, sampleLimit)

    for (const col of cols.value) {
      const minW = col.minWidth ?? defaultMinWidth
      const maxW = col.maxWidth ?? defaultMaxWidth

      // 表头文字宽度（系统 UI 字体，比 Arial Narrow 宽）
      const headerW = measureTextWidth(col.header, headerCharWidth) + cellPadding

      // 扫描数据行，取最长内容
      let maxDataW = 0
      for (let i = 0; i < scanCount; i++) {
        const row = data[i]
        const txt = toDisplayText(row?.[col.field], col, row, formatter)
        const w = measureTextWidth(txt, charWidth)
        if (w > maxDataW) maxDataW = w
      }

      const dataW = maxDataW + cellPadding
      const needed = Math.max(headerW, dataW)
      result[col.field] = Math.max(minW, Math.min(maxW, needed))
    }

    return result
  })

  /**
   * 最终宽度：总宽不足容器时按比例放大可增长列，铺满容器避免右侧留白。
   * 总宽超出容器时保持原值（表格横向滚动，由 CSS 折行兜住超长文本）。
   */
  const widths: ComputedRef<Record<string, number>> = computed(() => {
    const base = rawWidths.value
    const container = unref(options.containerWidth)
    if (!container || container <= 0) return base

    const list = cols.value
    const total = list.reduce((sum, c) => sum + (base[c.field] ?? 0), 0)
    const slack = container - total
    if (slack <= 0) return base

    // 只有未标 noGrow 的列参与放大
    const growable = list.filter((c) => !c.noGrow)
    const growBase = growable.reduce((sum, c) => sum + (base[c.field] ?? 0), 0)
    if (growBase <= 0) return base

    const result: Record<string, number> = { ...base }
    let distributed = 0
    growable.forEach((c, idx) => {
      const share = (base[c.field] ?? 0) / growBase
      // 最后一列吃掉取整误差，保证合计精确等于容器宽度
      const add = idx === growable.length - 1
        ? slack - distributed
        : Math.floor(slack * share)
      distributed += add
      result[c.field] = (base[c.field] ?? 0) + add
    })

    return result
  })

  /** 获取单列宽度（模板绑定用） */
  function colWidth(field: string): number {
    return widths.value[field] ?? defaultMinWidth
  }

  /** 所有列宽度合计，可直接喂给 el-table-v2 的 :width */
  const totalWidth = computed(() =>
    cols.value.reduce((sum, c) => sum + colWidth(c.field), 0),
  )

  return { widths, colWidth, totalWidth }
}
