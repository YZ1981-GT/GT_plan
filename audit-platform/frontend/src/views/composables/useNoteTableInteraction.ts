/**
 * useNoteTableInteraction — 附注表格的单元格交互（点击 / 右键菜单 / 选区动作）
 * 与三个只读面板句柄（数字信任度 / 状态机 / 时光机）。
 *
 * 从 `DisclosureEditor.vue` 抽出（该宿主 3398 行 / HARD_CAPS ceiling 1800）。
 *
 * 注：`trustScorePanelRef` / `smPanelRef` / `tmDrawerRef` 必须由本 composable 返回
 * 并在宿主模板上 `ref=` 绑定 —— 它们是**组件实例句柄**，只能由模板赋值。
 */
import { ref, toRaw, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

interface CtxLike {
  cellClassName: (p: { rowIndex: number; columnIndex: number }) => string
  closeContextMenu: () => void
  openContextMenu: (e: MouseEvent, name: string) => void
  selectCell: (r: number, c: number, v: unknown, additive?: boolean, range?: boolean) => void
  isCellSelected: (r: number, c: number) => boolean
  copySelectedValues: () => void
  sumSelectedValues: () => number
  contextMenu: { itemName: string; rowData?: unknown }
  selectedCells: Ref<Array<{ row: number; value: unknown }>> | ComputedRef<Array<{ row: number; value: unknown }>>
}

export interface UseNoteTableInteractionOptions {
  activeTableData: Ref<any> | ComputedRef<any>
  currentNote: Ref<any> | ComputedRef<any>
  editMode: Ref<boolean> | ComputedRef<boolean>
  showNoteFormulaManager: Ref<boolean>
  deCtx: CtxLike
  deComments: { commentCellClass: (sheetKey: string, r: number, c: number) => string }
  /** 激活单元格编辑（label 列用 -1 标识） */
  activateCell: (rowIndex: number, colIndex: number) => void
  fmtAmount: (n: number) => string
}

export function useNoteTableInteraction(options: UseNoteTableInteractionOptions) {
  const {
    activeTableData, currentNote, editMode, showNoteFormulaManager,
    deCtx, deComments, activateCell, fmtAmount,
  } = options

  // ─── 面板句柄（模板 ref= 绑定）───────────────────────────────────────────
  /** V3 Req 9.6: 数字信任度 */
  const trustScorePanelRef = ref<any>(null)
  /** V3 Req 10.4: 可解释状态机 */
  const smPanelRef = ref<any>(null)
  const disclosureInstanceId = ref('')
  /** V3 Req 11.6: 时光机 */
  const tmDrawerRef = ref<any>(null)

  function onTimeMachineRestored(_snap: unknown) {
    window.location.reload()
  }

  // ─── 单元格定位 ─────────────────────────────────────────────────────────

  /** 把 (row, column) 解析成表内下标；任一维解析失败返回 null */
  function locate(row: any, column: any): { rowIdx: number; colIdx: number; values: any[] } | null {
    const tableRows = activeTableData.value?.rows || []
    const rowIdx = tableRows.findIndex((candidate: any) => toRaw(candidate) === toRaw(row))
    const headers = activeTableData.value?.headers || []
    const colIdx = headers.indexOf(column?.label)
    if (rowIdx < 0 || colIdx < 0) return null
    return { rowIdx, colIdx, values: row?.values || row?.cells || [] }
  }

  function deCellClassName({ rowIndex, columnIndex }: any): string {
    const classes: string[] = []
    const selClass = deCtx.cellClassName({ rowIndex, columnIndex })
    if (selClass) classes.push(selClass)
    const sec = activeTableData.value
    const sheetKey = sec?.section_id || currentNote.value?.note_section || 'default'
    const ccClass = deComments.commentCellClass(sheetKey, rowIndex, columnIndex)
    if (ccClass) classes.push(ccClass)
    return classes.join(' ')
  }

  function cellValue(row: any, values: any[], colIdx: number): unknown {
    return colIdx === 0 ? (row?.label ?? '') : (values[colIdx - 1] ?? '')
  }

  function onDeCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
    deCtx.closeContextMenu()
    const hit = locate(row, column)
    if (!hit) return
    const { rowIdx, colIdx, values } = hit
    const value = cellValue(row, values, colIdx)
    deCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
    deCtx.contextMenu.itemName = row?.label || `行${rowIdx + 1}`
    // 单元格激活编辑：编辑模式下点击非合计行直接激活
    if (editMode.value && !row.is_total) {
      activateCell(rowIdx, colIdx === 0 ? -1 : colIdx - 1)
    }
  }

  function onDeCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
    const hit = locate(row, column)
    // 如果右键点击的单元格已在选区内，保持选区不变
    if (hit && !deCtx.isCellSelected(hit.rowIdx, hit.colIdx)) {
      const value = cellValue(row, hit.values, hit.colIdx)
      deCtx.selectCell(hit.rowIdx, hit.colIdx, value, false)
      deCtx.contextMenu.itemName = row?.label || `行${hit.rowIdx + 1}`
    }
    deCtx.openContextMenu(event, deCtx.contextMenu.itemName)
  }

  // ─── 右键菜单动作 ───────────────────────────────────────────────────────

  function onDeCtxCopy() {
    deCtx.closeContextMenu()
    deCtx.copySelectedValues()
    ElMessage.success('已复制')
  }

  function onDeCtxFormula() {
    deCtx.closeContextMenu()
    showNoteFormulaManager.value = true
  }

  function onDeCtxTrustScore() {
    deCtx.closeContextMenu()
    const section = currentNote.value?.note_section || ''
    const cell = deCtx.contextMenu.rowData ? `row${deCtx.selectedCells.value[0]?.row || 0}` : ''
    trustScorePanelRef.value?.open(`note:${section}|${cell}`)
  }

  function onDeCtxSum() {
    deCtx.closeContextMenu()
    const sum = deCtx.sumSelectedValues()
    ElMessage.info(`选中 ${deCtx.selectedCells.value.length} 格，合计：${fmtAmount(sum)}`)
  }

  function onDeCtxCompare() {
    deCtx.closeContextMenu()
    if (deCtx.selectedCells.value.length < 2) return
    const vals = deCtx.selectedCells.value.map((c) => Number(c.value) || 0)
    ElMessage.info(`差异：${fmtAmount(vals[0] - vals[1])}`)
  }

  return {
    trustScorePanelRef, smPanelRef, disclosureInstanceId, tmDrawerRef,
    onTimeMachineRestored,
    deCellClassName, onDeCellClick, onDeCellContextMenu,
    onDeCtxCopy, onDeCtxFormula, onDeCtxTrustScore, onDeCtxSum, onDeCtxCompare,
  }
}
