/**
 * useCopyPaste — 表格复制粘贴 composable [R3.6]
 *
 * 功能：
 * - 复制选中区域到剪贴板（HTML 表格 + 制表符纯文本双格式，兼容 Excel/Word）
 * - 粘贴剪贴板内容到选中区域（解析制表符文本，按矩形区域写入）
 * - 设置 paste 事件监听器（绑定到容器元素）
 *
 * 增强了 useCellSelection 中已有的 copySelectedValues（纯文本），
 * 提供 HTML+纯文本双格式复制，以及粘贴写入能力。
 *
 * @module composables/useCopyPaste
 */

import { onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { SelectedCell } from '@/composables/useCellSelection'

/**
 * 复制选中单元格到剪贴板（HTML 表格 + 制表符纯文本双格式）
 *
 * @param selectedCells - 当前选中的单元格数组
 * @param tableData - 表格数据（行数组）
 * @param columns - 列定义，每项包含 { key, label }
 */
export async function copySelection(
  selectedCells: SelectedCell[],
  tableData: Record<string, any>[],
  columns: { key: string; label: string }[],
): Promise<void> {
  if (!selectedCells.length) {
    ElMessage.warning('请先选中要复制的单元格')
    return
  }

  // 计算选区边界
  const rows = selectedCells.map(c => c.row)
  const cols = selectedCells.map(c => c.col)
  const minRow = Math.min(...rows)
  const maxRow = Math.max(...rows)
  const minCol = Math.min(...cols)
  const maxCol = Math.max(...cols)

  // 按行列排列，构建矩形区域数据
  const lines: string[][] = []
  for (let r = minRow; r <= maxRow; r++) {
    const rowCells: string[] = []
    for (let c = minCol; c <= maxCol; c++) {
      const cell = selectedCells.find(cc => cc.row === r && cc.col === c)
      if (cell?.value != null) {
        rowCells.push(String(cell.value))
      } else {
        // 尝试从 tableData 取值
        const rowData = tableData[r]
        const colDef = columns[c]
        const val = rowData && colDef ? rowData[colDef.key] : ''
        rowCells.push(val != null ? String(val) : '')
      }
    }
    lines.push(rowCells)
  }

  // 纯文本格式：制表符分隔
  const text = lines.map(row => row.join('\t')).join('\n')

  // HTML 表格格式：兼容 Excel/Word 粘贴
  const htmlRows = lines.map(row =>
    `<tr>${row.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`,
  ).join('')
  const html = `<table border="1">${htmlRows}</table>`

  try {
    const htmlBlob = new Blob([html], { type: 'text/html' })
    const textBlob = new Blob([text], { type: 'text/plain' })
    await navigator.clipboard.write([
      new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob }),
    ])
    const cellCount = lines.reduce((sum, row) => sum + row.length, 0)
    ElMessage.success(`已复制 ${lines.length} 行 × ${lines[0]?.length || 0} 列（${cellCount} 格）`)
  } catch {
    // 降级：仅写入纯文本
    await navigator.clipboard?.writeText(text)
    ElMessage.success('已复制为文本格式')
  }
}

/**
 * 粘贴剪贴板内容到选中区域
 *
 * 从 paste 事件中解析制表符分隔文本，以选区左上角为起点，
 * 按行列顺序写入单元格。超出表格范围的数据会被忽略。
 *
 * @param event - 原生 paste 事件
 * @param selectedCells - 当前选中的单元格数组
 * @param tableData - 表格数据（行数组，必须是响应式数组 ref 的 .value，否则 UI 不更新）
 * @param columns - 列定义，每项包含 { key, label }
 * @param onCellChange - 单元格值变更回调，用于通知外部更新
 * @returns 写入的单元格数量
 */
export function pasteToSelection(
  event: ClipboardEvent,
  selectedCells: SelectedCell[],
  tableData: Record<string, any>[],
  columns: { key: string; label: string }[],
  onCellChange?: (rowIdx: number, colIdx: number, key: string, value: string) => void,
): number {
  const clipText = event.clipboardData?.getData('text/plain')
  if (!clipText?.trim()) return 0

  // 解析制表符分隔文本
  const pasteRows = clipText.split(/\r?\n/).filter(line => line.length > 0)
  const pasteData = pasteRows.map(row => row.split('\t'))

  if (!selectedCells.length) return 0

  // 以选区左上角为起点
  const startRow = Math.min(...selectedCells.map(c => c.row))
  const startCol = Math.min(...selectedCells.map(c => c.col))

  let written = 0

  for (let ri = 0; ri < pasteData.length; ri++) {
    const targetRow = startRow + ri
    if (targetRow >= tableData.length) break // 超出表格行数

    for (let ci = 0; ci < pasteData[ri].length; ci++) {
      const targetCol = startCol + ci
      if (targetCol >= columns.length) break // 超出列数

      const colDef = columns[targetCol]
      const value = pasteData[ri][ci]

      // 写入 tableData
      tableData[targetRow][colDef.key] = value

      // 通知外部
      if (onCellChange) {
        onCellChange(targetRow, targetCol, colDef.key, value)
      }

      written++
    }
  }

  if (written > 0) {
    ElMessage.success(`已粘贴 ${pasteData.length} 行 × ${pasteData[0]?.length || 0} 列（${written} 格）`)
  }

  return written
}

/**
 * 设置 paste 事件监听器
 *
 * 在容器元素上监听 paste 事件，当有选中单元格时拦截粘贴并写入表格。
 * 自动在 onMounted 时绑定，onUnmounted 时解绑。
 *
 * @param containerRef - 容器元素的 ref（el-table ref 或 DOM 元素 ref）
 * @param handler - paste 事件处理函数
 */
export function setupPasteListener(
  containerRef: Ref<HTMLElement | { $el: HTMLElement } | null>,
  handler: (event: ClipboardEvent) => void,
): void {
  function onPaste(e: ClipboardEvent) {
    // 忽略在 input/textarea 等可编辑元素中的粘贴
    const target = e.target as HTMLElement
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      return
    }
    e.preventDefault()
    handler(e)
  }

  onMounted(() => {
    const el = containerRef.value
    if (!el) return
    const dom = '$el' in el ? (el as any).$el : el
    if (dom) {
      dom.addEventListener('paste', onPaste)
    }
  })

  onUnmounted(() => {
    const el = containerRef.value
    if (!el) return
    const dom = '$el' in el ? (el as any).$el : el
    if (dom) {
      dom.removeEventListener('paste', onPaste)
    }
  })
}

/** HTML 转义 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
