/**
 * usePasteImport — 表格粘贴入库 composable [R7-S3-08 Task 40]
 *
 * 监听表格容器的 paste 事件，解析剪贴板制表符文本，
 * 弹窗确认后追加到表格数据。
 *
 * @example
 * const tableRef = ref<HTMLElement | null>(null)
 * usePasteImport({
 *   containerRef: tableRef,
 *   columns: [{ key: 'code', label: '编码' }, { key: 'name', label: '名称' }],
 *   onInsert: async (rows) => { tableData.value.push(...rows) },
 * })
 */
import { onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'

export interface PasteImportColumn {
  key: string
  label: string
}

export interface PasteImportOptions {
  /** 表格容器 ref（监听 paste 事件） */
  containerRef: Ref<HTMLElement | null>
  /** 列定义（key + label），用于映射粘贴列 */
  columns: PasteImportColumn[]
  /** 粘贴后回调：接收解析后的行数据 */
  onInsert: (rows: Record<string, any>[]) => Promise<void>
  /** 最大允许粘贴行数（默认 500） */
  maxRows?: number
}

export function usePasteImport(options: PasteImportOptions) {
  const maxRows = options.maxRows ?? 500

  function onPaste(e: ClipboardEvent) {
    const text = e.clipboardData?.getData('text/plain')
    if (!text || !text.includes('\t')) return // 只处理制表符分隔（来自 Excel/表格）

    // 解析制表符分隔文本
    const lines = text.split('\n').filter(l => l.trim())
    if (lines.length === 0) return
    if (lines.length > maxRows) {
      ElMessage.warning(`粘贴数据超过 ${maxRows} 行限制，请分批操作`)
      e.preventDefault()
      return
    }

    const rows = lines.map(line => {
      const cells = line.split('\t')
      const row: Record<string, any> = {}
      options.columns.forEach((col, i) => {
        if (cells[i] !== undefined) row[col.key] = cells[i].trim()
      })
      return row
    })

    // 确认弹窗
    ElMessageBox.confirm(
      `检测到粘贴 ${rows.length} 行数据（${options.columns.length} 列），是否追加到表格末尾？`,
      '粘贴导入',
      { confirmButtonText: '追加', cancelButtonText: '取消', type: 'info' },
    ).then(async () => {
      try {
        await options.onInsert(rows)
        ElMessage.success(`已追加 ${rows.length} 行`)
      } catch (err: any) {
        ElMessage.error(`追加失败：${err?.message || '未知错误'}`)
      }
    }).catch(() => { /* 用户取消 */ })

    e.preventDefault()
  }

  function _getEl(): HTMLElement | null {
    const v = options.containerRef.value
    if (!v) return null
    // 支持 Vue 组件 ref（取 $el）和原生 DOM ref
    if (v instanceof HTMLElement) return v
    if (v.$el instanceof HTMLElement) return v.$el
    return null
  }

  onMounted(() => {
    _getEl()?.addEventListener('paste', onPaste as any)
  })

  onUnmounted(() => {
    _getEl()?.removeEventListener('paste', onPaste as any)
  })
}
