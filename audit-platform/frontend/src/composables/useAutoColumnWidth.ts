/**
 * useAutoColumnWidth — 根据实际数据内容动态计算 el-table 列宽
 *
 * 使用 Arial Narrow 12px 字体的字符宽度估算（约 6.2px/字符），
 * 比固定 min-width 更节省空间：有数据的列给足宽度，空列（只显示 "-"）自动收窄。
 *
 * 用法：
 * ```ts
 * const { colWidth } = useAutoColumnWidth({
 *   rows: computed(() => flatRows),
 *   columns: [
 *     { field: 'amount', header: '未审数' },
 *     { field: 'adj',    header: '账项调整' },
 *   ],
 *   formatter: (val) => fmtAmount(val),
 * })
 * // 模板中：<el-table-column :width="colWidth('amount')" ...>
 * ```
 */
import { computed, type Ref, type ComputedRef } from 'vue'

export interface AutoColDef {
  /** 行数据中的字段名 */
  field: string
  /** 列表头文字（用于计算表头最小宽度） */
  header: string
  /** 覆盖该列最小宽度（默认 COL_MIN） */
  minWidth?: number
  /** 覆盖该列最大宽度（默认 COL_MAX） */
  maxWidth?: number
}

export interface UseAutoColumnWidthOptions {
  /** 响应式数据行（所有行平铺，含合计行） */
  rows: Ref<Record<string, any>[]> | ComputedRef<Record<string, any>[]>
  /** 需要自适应的列定义 */
  columns: AutoColDef[]
  /** 值格式化函数（将原始值转为显示文本，用于估算宽度） */
  formatter: (value: any) => string
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
}

/**
 * 估算中文字符宽度倍率：一个中文字 ≈ 1.6 个 ASCII 字符宽度（Arial Narrow 下）
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

export function useAutoColumnWidth(options: UseAutoColumnWidthOptions) {
  const {
    rows,
    columns,
    formatter,
    charWidth = 6.2,
    headerCharWidth = 8,
    cellPadding = 16,
    defaultMinWidth = 56,
    defaultMaxWidth = 180,
  } = options

  /** 每列的计算宽度 */
  const widths: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}

    for (const col of columns) {
      const minW = col.minWidth ?? defaultMinWidth
      const maxW = col.maxWidth ?? defaultMaxWidth

      // 表头文字宽度（用系统 UI 字体宽度，非 Arial Narrow）
      const headerW = measureTextWidth(col.header, headerCharWidth) + cellPadding

      // 扫描所有行，找最大数据宽度（用 Arial Narrow 字体宽度）
      let maxDataW = 0
      const data = rows.value
      for (let i = 0; i < data.length; i++) {
        const raw = data[i]?.[col.field]
        const txt = formatter(raw ?? 0)
        const w = measureTextWidth(txt, charWidth)
        if (w > maxDataW) maxDataW = w
      }

      const dataW = maxDataW + cellPadding
      const needed = Math.max(headerW, dataW)
      result[col.field] = Math.max(minW, Math.min(maxW, needed))
    }

    return result
  })

  /** 获取单列宽度（模板绑定用） */
  function colWidth(field: string): number {
    return widths.value[field] ?? defaultMinWidth
  }

  return { widths, colWidth }
}
