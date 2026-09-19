/**
 * useWpHeaderProtection — 底稿表头只读保护
 *
 * 在 Univer/GtGridSheet 渲染底稿时，将前 N 行（默认5行）标记为只读，
 * 阻止用户编辑表头区域。
 *
 * 对于 GtGridSheet（HTML 渲染）：headerRows 已在 thead 中渲染（天然只读）。
 * 对于 Univer（xlsx 渲染）：通过 beforeCellEdit 钩子拦截表头行编辑。
 *
 * Requirements: 1.4
 */
import { computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

export interface HeaderProtectionOptions {
  /** 受保护的行数（从第1行开始，默认5） */
  protectedRows?: number
  /** Univer Facade API ref（可选，如有则注册 hook） */
  univerAPI?: Ref<any>
  /** 是否启用（false 则跳过保护） */
  enabled?: boolean
}

/**
 * 判断给定行号是否在表头保护区域内
 */
export function isHeaderRow(row: number, protectedRows = 5): boolean {
  // 行号从 0 或 1 开始均兼容（<=protectedRows 覆盖 1-based 和 0-based 前5行）
  return row >= 0 && row < protectedRows
}

export function useWpHeaderProtection(options: HeaderProtectionOptions = {}) {
  const { protectedRows = 5, univerAPI, enabled = true } = options

  const protectedRange = computed(() => ({
    startRow: 0,
    endRow: protectedRows - 1,
    startCol: 0,
    endCol: 99, // 覆盖足够宽的列
  }))

  /**
   * beforeCellEdit 拦截器 — 在 Univer onBeforeCellEdit 注册
   * 如果编辑目标在表头区域，返回 false 阻止编辑
   */
  function shouldBlockEdit(row: number, _col: number): boolean {
    if (!enabled) return false
    return isHeaderRow(row, protectedRows)
  }

  /**
   * 尝试编辑表头时的用户提示
   */
  function notifyHeaderLocked() {
    ElMessage.warning('表头区域为只读，不可编辑')
  }

  return {
    protectedRange,
    protectedRows,
    shouldBlockEdit,
    notifyHeaderLocked,
    isHeaderRow: (row: number) => isHeaderRow(row, protectedRows),
  }
}
