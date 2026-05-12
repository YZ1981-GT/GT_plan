/**
 * 通用单元格选中 composable
 *
 * 支持：
 * - 单击选中
 * - Ctrl+单击 多选（离散）
 * - Shift+单击 范围选中（从锚点到目标的矩形区域）
 * - 鼠标拖拽框选（mousedown → mousemove → mouseup 连续区域）
 * - 右键菜单定位
 * - 复制选中值、求和、对比差异
 */
import { ref, reactive, onMounted, onUnmounted } from 'vue'

export interface SelectedCell {
  row: number
  col: number
  value: any
}

export interface CellContextMenuState {
  visible: boolean
  x: number
  y: number
  itemName: string
  rowData: any
}

// ── 全局引用计数（多实例共享 document 监听器）──
let _instanceCount = 0
let _docClickHandler: ((e: MouseEvent) => void) | null = null
let _docMouseUpHandler: (() => void) | null = null
const _docClickCallbacks: Set<(e: MouseEvent) => void> = new Set()
const _docMouseUpCallbacks: Set<() => void> = new Set()

function _ensureDocListeners() {
  if (_instanceCount === 0) {
    _docClickHandler = (e: MouseEvent) => _docClickCallbacks.forEach(cb => cb(e))
    _docMouseUpHandler = () => _docMouseUpCallbacks.forEach(cb => cb())
    document.addEventListener('click', _docClickHandler)
    document.addEventListener('mouseup', _docMouseUpHandler)
  }
  _instanceCount++
}

function _releaseDocListeners() {
  _instanceCount--
  if (_instanceCount === 0 && _docClickHandler && _docMouseUpHandler) {
    document.removeEventListener('click', _docClickHandler)
    document.removeEventListener('mouseup', _docMouseUpHandler)
    _docClickHandler = null
    _docMouseUpHandler = null
  }
}

export function useCellSelection() {
  const selectedCells = ref<SelectedCell[]>([])
  const contextMenu = reactive<CellContextMenuState>({
    visible: false, x: 0, y: 0, itemName: '', rowData: null,
  })

  // ── 锚点（用于 Shift 范围选和拖拽起点） ──
  let anchorRow = -1
  let anchorCol = -1

  // ── 拖拽状态 ──
  let isDragging = false
  /** 防止 setupTableDrag 的 mousedown 和 el-table 的 cell-click 重复处理 */
  let _skipNextCellClick = false
  /** 外部提供的取值函数（拖拽框选时需要获取单元格值） */
  let _getCellValue: ((row: number, col: number) => any) | null = null

  /**
   * 注册取值函数（在组件 setup 中调用一次）
   * 用于拖拽框选时自动获取矩形区域内每个单元格的值
   */
  function registerCellValueGetter(fn: (row: number, col: number) => any) {
    _getCellValue = fn
  }

  function cellClassName({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }): string {
    const isSelected = selectedCells.value.some(c => c.row === rowIndex && c.col === columnIndex)
    if (!isSelected) return ''
    // 单选时加额外样式（Excel 风格的填充柄）
    if (selectedCells.value.length === 1) return 'gt-ucell--selected gt-ucell--single-selected'
    return 'gt-ucell--selected'
  }

  /** 判断某单元格是否已在选区内 */
  function isCellSelected(rowIdx: number, colIdx: number): boolean {
    return selectedCells.value.some(c => c.row === rowIdx && c.col === colIdx)
  }

  /**
   * 选中单元格
   * @param rowIdx 行索引
   * @param colIdx 列索引
   * @param value 单元格值
   * @param multi Ctrl 键按下（离散多选）
   * @param range Shift 键按下（范围选中）
   */
  function selectCell(rowIdx: number, colIdx: number, value: any, multi: boolean, range = false) {
    // 如果 setupTableDrag 已经处理了这次点击（Shift/拖拽），跳过
    if (_skipNextCellClick) {
      _skipNextCellClick = false
      return
    }

    if (range && anchorRow >= 0 && anchorCol >= 0) {
      // Shift+点击：选中锚点到目标的矩形区域
      selectRange(anchorRow, anchorCol, rowIdx, colIdx)
      return
    }

    if (multi) {
      // Ctrl+点击：切换单个单元格
      const idx = selectedCells.value.findIndex(c => c.row === rowIdx && c.col === colIdx)
      if (idx >= 0) {
        selectedCells.value.splice(idx, 1)
      } else {
        selectedCells.value.push({ row: rowIdx, col: colIdx, value })
      }
    } else {
      // 普通点击：单选
      selectedCells.value = [{ row: rowIdx, col: colIdx, value }]
    }

    // 更新锚点
    anchorRow = rowIdx
    anchorCol = colIdx
  }

  /**
   * 选中矩形区域（从 r1,c1 到 r2,c2）
   */
  function selectRange(r1: number, c1: number, r2: number, c2: number) {
    const minR = Math.min(r1, r2)
    const maxR = Math.max(r1, r2)
    const minC = Math.min(c1, c2)
    const maxC = Math.max(c1, c2)

    const cells: SelectedCell[] = []
    for (let r = minR; r <= maxR; r++) {
      for (let c = minC; c <= maxC; c++) {
        const value = _getCellValue ? _getCellValue(r, c) : null
        cells.push({ row: r, col: c, value })
      }
    }
    selectedCells.value = cells
  }

  /**
   * 开始拖拽（mousedown 时调用）
   */
  function startDrag(rowIdx: number, colIdx: number, value: any) {
    isDragging = true
    anchorRow = rowIdx
    anchorCol = colIdx
    selectedCells.value = [{ row: rowIdx, col: colIdx, value }]
    document.body.classList.add('gt-dragging')
  }

  /**
   * 拖拽中（mousemove 时调用）
   */
  function updateDrag(rowIdx: number, colIdx: number) {
    if (!isDragging || anchorRow < 0) return
    selectRange(anchorRow, anchorCol, rowIdx, colIdx)
  }

  /**
   * 结束拖拽（mouseup 时调用）
   */
  function endDrag() {
    isDragging = false
    document.body.classList.remove('gt-dragging')
  }

  /** 清空选中 */
  function clearSelection() {
    selectedCells.value = []
    anchorRow = -1
    anchorCol = -1
  }

  /** 获取选中区域的边界 */
  function getSelectionBounds(): { minRow: number; maxRow: number; minCol: number; maxCol: number } | null {
    if (!selectedCells.value.length) return null
    const rows = selectedCells.value.map(c => c.row)
    const cols = selectedCells.value.map(c => c.col)
    return {
      minRow: Math.min(...rows),
      maxRow: Math.max(...rows),
      minCol: Math.min(...cols),
      maxCol: Math.max(...cols),
    }
  }

  function openContextMenu(e: MouseEvent, itemName: string, rowData?: any) {
    e.preventDefault()
    e.stopPropagation()
    setTimeout(() => {
      contextMenu.x = e.clientX
      contextMenu.y = e.clientY
      contextMenu.itemName = itemName
      contextMenu.rowData = rowData || null
      contextMenu.visible = true
    }, 0)
  }

  function closeContextMenu() {
    contextMenu.visible = false
  }

  /**
   * 复制选中值（HTML 表格 + 制表符纯文本双格式）
   * - 单行：制表符分隔
   * - 多行矩形：按行列排列，行间换行，列间制表符
   * - HTML 格式兼容 Excel/Word 粘贴
   */
  function copySelectedValues() {
    const cells = selectedCells.value
    if (!cells.length) return

    const bounds = getSelectionBounds()
    if (!bounds) return

    // 按行列排列
    const lines: string[][] = []
    for (let r = bounds.minRow; r <= bounds.maxRow; r++) {
      const rowCells: string[] = []
      for (let c = bounds.minCol; c <= bounds.maxCol; c++) {
        const cell = cells.find(cc => cc.row === r && cc.col === c)
        rowCells.push(cell?.value != null ? String(cell.value) : '')
      }
      lines.push(rowCells)
    }

    const text = lines.map(row => row.join('\t')).join('\n')
    const htmlRows = lines.map(row =>
      `<tr>${row.map(c => `<td>${c.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</td>`).join('')}</tr>`,
    ).join('')
    const html = `<table border="1">${htmlRows}</table>`

    try {
      navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([text], { type: 'text/plain' }),
        }),
      ])
    } catch {
      navigator.clipboard?.writeText(text)
    }
  }

  function sumSelectedValues(): number {
    return selectedCells.value.reduce((s, c) => s + (Number(c.value) || 0), 0)
  }

  /** 选中单元格数量 */
  function selectionCount(): number {
    return selectedCells.value.length
  }

  /**
   * 选中区域统计（求和/平均/最大/最小/计数）
   * 用于底部状态栏显示
   */
  function selectionStats(): { count: number; numCount: number; sum: number; avg: number; max: number; min: number } | null {
    const cells = selectedCells.value
    if (!cells.length) return null

    const nums = cells.map(c => Number(c.value)).filter(n => !isNaN(n) && n !== 0)
    if (!nums.length) return { count: cells.length, numCount: 0, sum: 0, avg: 0, max: 0, min: 0 }

    const sum = nums.reduce((s, n) => s + n, 0)
    return {
      count: cells.length,
      numCount: nums.length,
      sum,
      avg: sum / nums.length,
      max: Math.max(...nums),
      min: Math.min(...nums),
    }
  }

  // 点击其他地方关闭菜单
  function onDocClick(e: MouseEvent) {
    if (!(e.target as HTMLElement)?.closest('.gt-ucell-context-menu')) {
      closeContextMenu()
    }
  }

  // 全局 mouseup 结束拖拽
  function onDocMouseUp() {
    if (isDragging) endDrag()
  }

  /**
   * 为 el-table 设置鼠标拖拽框选（DOM 事件委托）
   *
   * el-table 原生不支持 cell-mousedown/cell-mouseenter，
   * 通过在 table 容器上监听原生 mousedown/mouseover 事件，
   * 从 DOM 中解析出行列索引来实现拖拽框选。
   *
   * @param tableRef el-table 的 ref 或包含表格的 DOM 元素 ref
   * @param getRowData 根据行索引获取行数据的函数
   * @param getColIndex 根据列 DOM 元素获取列索引的函数
   * @param getCellVal 根据行索引和列索引获取单元格值的函数
   */
  function setupTableDrag(
    tableRef: { value: HTMLElement | { $el: HTMLElement } | null },
    getCellVal: (rowIdx: number, colIdx: number) => any,
  ) {
    // 从 td 元素解析行列索引
    function parseCellPosition(target: HTMLElement): { row: number; col: number } | null {
      const td = target.closest('td.el-table__cell') as HTMLElement | null
      if (!td) return null
      const tr = td.closest('tr') as HTMLElement | null
      if (!tr) return null
      // 行索引：tr 在 tbody 中的位置
      const tbody = tr.closest('tbody')
      if (!tbody) return null
      const rowIdx = Array.from(tbody.children).indexOf(tr)
      // 列索引：td 在 tr 中的位置（跳过 selection 列等）
      const colIdx = Array.from(tr.children).indexOf(td)
      if (rowIdx < 0 || colIdx < 0) return null
      return { row: rowIdx, col: colIdx }
    }

    function onTableMouseDown(e: MouseEvent) {
      // 只响应左键，忽略右键和中键
      if (e.button !== 0) return
      // 忽略在 input/button 等交互元素上的点击
      const tag = (e.target as HTMLElement).tagName
      if (['INPUT', 'BUTTON', 'TEXTAREA', 'SELECT', 'A'].includes(tag)) return

      const pos = parseCellPosition(e.target as HTMLElement)
      if (!pos) return

      const value = getCellVal(pos.row, pos.col)

      if (e.shiftKey) {
        // Shift+点击：范围选
        e.preventDefault()
        selectCell(pos.row, pos.col, value, false, true)
        _skipNextCellClick = true  // 阻止后续 cell-click 重复处理
      } else if (e.ctrlKey || e.metaKey) {
        // Ctrl+点击：多选（由 cell-click 处理）
        return
      } else {
        // 普通左键按下：开始拖拽
        e.preventDefault()
        startDrag(pos.row, pos.col, value)
        _skipNextCellClick = true  // 阻止后续 cell-click 重复处理
      }
    }

    function onTableMouseOver(e: MouseEvent) {
      if (!isDragging) return
      const pos = parseCellPosition(e.target as HTMLElement)
      if (!pos) return
      updateDrag(pos.row, pos.col)
    }

    // 注册取值函数
    registerCellValueGetter(getCellVal)

    // 绑定事件
    onMounted(() => {
      const el = tableRef.value
      if (!el) return
      const dom = '$el' in el ? (el as any).$el : el
      if (dom) {
        dom.addEventListener('mousedown', onTableMouseDown)
        dom.addEventListener('mouseover', onTableMouseOver)
      }
    })

    onUnmounted(() => {
      const el = tableRef.value
      if (!el) return
      const dom = '$el' in el ? (el as any).$el : el
      if (dom) {
        dom.removeEventListener('mousedown', onTableMouseDown)
        dom.removeEventListener('mouseover', onTableMouseOver)
      }
    })
  }

  onMounted(() => {
    _ensureDocListeners()
    _docClickCallbacks.add(onDocClick)
    _docMouseUpCallbacks.add(onDocMouseUp)
  })
  onUnmounted(() => {
    _docClickCallbacks.delete(onDocClick)
    _docMouseUpCallbacks.delete(onDocMouseUp)
    _releaseDocListeners()
  })

  // ── R7-S3-08：行选/列选/全选 ──

  /**
   * 选中整行（点击行号时调用）
   * @param rowIdx 行索引
   * @param totalCols 总列数
   */
  function selectRow(rowIdx: number, totalCols: number) {
    const cells: SelectedCell[] = []
    for (let c = 0; c < totalCols; c++) {
      const val = _getCellValue ? _getCellValue(rowIdx, c) : null
      cells.push({ row: rowIdx, col: c, value: val })
    }
    selectedCells.value = cells
    anchorRow = rowIdx
    anchorCol = 0
  }

  /**
   * 选中整列（点击列头时调用）
   * @param colIdx 列索引
   * @param totalRows 总行数
   */
  function selectColumn(colIdx: number, totalRows: number) {
    const cells: SelectedCell[] = []
    for (let r = 0; r < totalRows; r++) {
      const val = _getCellValue ? _getCellValue(r, colIdx) : null
      cells.push({ row: r, col: colIdx, value: val })
    }
    selectedCells.value = cells
    anchorRow = 0
    anchorCol = colIdx
  }

  /**
   * 全选（Ctrl+A，表格 focus 时）
   * @param totalRows 总行数
   * @param totalCols 总列数
   */
  function selectAll(totalRows: number, totalCols: number) {
    const cells: SelectedCell[] = []
    for (let r = 0; r < totalRows; r++) {
      for (let c = 0; c < totalCols; c++) {
        const val = _getCellValue ? _getCellValue(r, c) : null
        cells.push({ row: r, col: c, value: val })
      }
    }
    selectedCells.value = cells
    anchorRow = 0
    anchorCol = 0
  }

  return {
    selectedCells,
    contextMenu,
    cellClassName,
    isCellSelected,
    selectCell,
    selectRange,
    selectRow,
    selectColumn,
    selectAll,
    startDrag,
    updateDrag,
    endDrag,
    clearSelection,
    getSelectionBounds,
    registerCellValueGetter,
    setupTableDrag,
    openContextMenu,
    closeContextMenu,
    copySelectedValues,
    sumSelectedValues,
    selectionCount,
    selectionStats,
  }
}
