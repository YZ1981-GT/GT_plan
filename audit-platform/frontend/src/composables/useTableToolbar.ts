/**
 * useTableToolbar — 通用表格工具栏逻辑 composable [R3.3]
 *
 * 封装表格增删行、多选、导入导出、复制整表等通用操作，
 * 消除 worksheet 组件中重复的 selectedRows / addRow / batchDelete / export / import / copy 代码。
 *
 * 用法：
 *   const rows = ref<MyRow[]>([])
 *   const { selectedRows, selectedCount, addRow, deleteSelectedRows, onSelectionChange, exportExcel, importExcel, copyTable } = useTableToolbar(rows)
 *
 * @module composables/useTableToolbar
 */

import { ref, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmBatch } from '@/utils/confirm'
import { exportData, parseFile, type ExcelColumn, type ParseFileOptions } from '@/composables/useExcelIO'

/**
 * 通用表格工具栏 composable
 *
 * @param tableData - 表格数据的 Ref（Ref<T[]> 或 reactive 数组均可）
 * @returns 工具栏操作函数和状态
 */
export function useTableToolbar<T extends Record<string, any>>(tableData: Ref<T[]>) {
  /** 当前选中的行 */
  const selectedRows = ref<T[]>([]) as Ref<T[]>

  /** 选中行数量 */
  const selectedCount = computed(() => selectedRows.value.length)

  /**
   * el-table @selection-change 回调
   */
  function onSelectionChange(selection: T[]) {
    selectedRows.value = selection
  }

  /**
   * 新增一行到表格末尾（或选中行之后）
   *
   * @param defaultRow - 新行的默认值（工厂函数或对象）
   * @param insertAfterSelection - 是否插入到选中行之后（默认 false，追加到末尾）
   */
  function addRow(defaultRow: T | (() => T), insertAfterSelection = false): T {
    const newRow = typeof defaultRow === 'function' ? (defaultRow as () => T)() : { ...defaultRow }
    if (insertAfterSelection && selectedRows.value.length > 0) {
      const lastSelected = selectedRows.value[selectedRows.value.length - 1]
      const idx = tableData.value.indexOf(lastSelected)
      if (idx >= 0) {
        tableData.value.splice(idx + 1, 0, newRow)
        return newRow
      }
    }
    tableData.value.push(newRow)
    return newRow
  }

  /**
   * 删除所有选中行（带确认弹窗）
   *
   * 注意：使用对象引用比较（`Set.has(r)`）来过滤行。
   * 如果在选中行后刷新了 tableData（重新赋值数组），旧引用会失效，
   * 导致删除无效。应确保在用户选中后、删除前不重新加载数据。
   *
   * @returns 是否执行了删除（用户取消返回 false）
   */
  async function deleteSelectedRows(): Promise<boolean> {
    if (!selectedRows.value.length) {
      ElMessage.warning('请先选择要删除的行')
      return false
    }
    try {
      await confirmBatch('删除', selectedRows.value.length)
      const toDelete = new Set(selectedRows.value)
      tableData.value = tableData.value.filter(r => !toDelete.has(r))
      selectedRows.value = []
      return true
    } catch {
      // 用户取消
      return false
    }
  }

  /**
   * 导出表格数据到 Excel
   *
   * @param columns - 列定义（ExcelColumn[]）
   * @param fileName - 导出文件名（含 .xlsx）
   * @param sheetName - 工作表名称，默认 '数据'
   */
  async function exportExcel(
    columns: ExcelColumn[],
    fileName: string,
    sheetName = '数据',
  ): Promise<void> {
    const data = tableData.value.filter(r => {
      // 过滤空行：至少有一个非空字段
      return Object.values(r).some(v => v != null && v !== '')
    })
    if (!data.length) {
      ElMessage.warning('暂无数据可导出')
      return
    }
    await exportData({ data, columns, sheetName, fileName })
  }

  /**
   * 导入 Excel 文件数据到表格（追加模式）
   *
   * @param file - 上传的文件对象
   * @param columns - 列定义，用于将表头名映射回字段名
   * @param options - 解析选项（传给 parseFile）
   * @returns 导入的行数
   */
  async function importExcel(
    file: File,
    columns: ExcelColumn[],
    options?: ParseFileOptions,
  ): Promise<number> {
    const result = await parseFile(file, options)
    if (!result.rows.length) {
      ElMessage.warning('未解析到有效数据')
      return 0
    }
    // 将 header 名映射回 key
    const headerToKey = new Map(columns.map(c => [c.header, c.key]))
    const imported: T[] = result.rows.map(row => {
      const mapped: Record<string, any> = {}
      for (const [header, value] of Object.entries(row)) {
        const key = headerToKey.get(header) || header
        mapped[key] = value
      }
      return mapped as T
    })
    tableData.value.push(...imported)
    ElMessage.success(`已导入 ${imported.length} 行`)
    return imported.length
  }

  /**
   * 复制整个表格到剪贴板（制表符分隔文本 + HTML 表格双格式）
   *
   * @param columns - 列定义，用于确定表头和字段顺序
   */
  async function copyTable(columns: ExcelColumn[]): Promise<void> {
    const data = tableData.value.filter(r =>
      Object.values(r).some(v => v != null && v !== ''),
    )
    if (!data.length) {
      ElMessage.warning('暂无数据可复制')
      return
    }
    const headers = columns.map(c => c.header)
    const rows = data.map(r => columns.map(c => String(r[c.key] ?? '')))

    const text = [headers.join('\t'), ...rows.map(r => r.join('\t'))].join('\n')
    const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`

    try {
      const htmlBlob = new Blob([html], { type: 'text/html' })
      const textBlob = new Blob([text], { type: 'text/plain' })
      await navigator.clipboard.write([
        new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob }),
      ])
      ElMessage.success(`已复制 ${data.length} 行 × ${columns.length} 列，可粘贴到 Word/Excel`)
    } catch {
      await navigator.clipboard?.writeText(text)
      ElMessage.success('已复制为文本格式')
    }
  }

  return {
    selectedRows,
    selectedCount,
    onSelectionChange,
    addRow,
    deleteSelectedRows,
    exportExcel,
    importExcel,
    copyTable,
  }
}
