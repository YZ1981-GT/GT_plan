/**
 * useNoteCellActions — 附注单元格右键菜单动作处理
 *
 * 从 DisclosureEditor.vue 抽取，处理：
 * - 查看相关底稿
 * - 穿透到序时账
 * - 查看数据来源
 * - 查看合并明细
 * - 单元格溯源
 * - 数字信任度
 * - 来源追溯 (Phase 3 F1)
 */
import { ref, reactive, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { usePenetrate } from '@/composables/usePenetrate'
import { useNavigationStack } from '@/composables/useNavigationStack'
import { handleApiError } from '@/utils/errorHandler'
import type { TraceSourceData } from '@/components/common/TraceSourcePopover.vue'

export interface UseNoteCellActionsOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
  currentNote: Ref<any>
  activeTableData: ComputedRef<any>
  deCtx: any
  router: any
  route: any
}

export function useNoteCellActions(options: UseNoteCellActionsOptions) {
  const { projectId, year, currentNote, activeTableData, deCtx, router, route } = options

  const penetrate = usePenetrate()
  const { push: navPush } = useNavigationStack()

  // Sprint 5.7: 查看数据来源
  const showCellFormulaDetail = ref(false)
  const cellDetailWpCode = ref('')
  const cellDetailSheet = ref('')
  const cellDetailLabel = ref('')

  // 合并穿透
  const consolBreakdownVisible = ref(false)
  const consolBreakdownSectionId = ref('')

  // CellTrace 溯源
  const showCellTrace = ref(false)
  const cellTraceCtx = reactive<{ noteId: string; rowIdx: number; colIdx: number }>({
    noteId: '', rowIdx: 0, colIdx: 0,
  })

  // Phase 3 F1: 来源追溯
  const tracePopoverVisible = ref(false)
  const traceLoading = ref(false)
  const traceData = ref<TraceSourceData | null>(null)
  const tracePopoverPos = ref({ x: 0, y: 0 })

  async function onDeCtxRelatedWp() {
    deCtx.closeContextMenu()
    const note = currentNote.value
    if (!note?.note_section) { ElMessage.warning('请先选择附注章节'); return }
    const sel = deCtx.selectedCells.value[0]
    if (!sel) return
    const rowCode = `row_${sel.row}`
    try {
      const data: any = await api.get(
        P.disclosureNotes.relatedWorkpapers(projectId.value, year.value, note.note_section, rowCode),
        { validateStatus: (s: number) => s < 600 },
      )
      const wps = data?.workpapers || []
      if (!wps.length) { ElMessage.info('该附注行暂无关联底稿'); return }
      if (wps.length === 1) {
        router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: wps[0].id } })
        return
      }
      const list = wps.map((w: any) => `${w.wp_code} ${w.wp_name}`).join('\n')
      ElMessage.info(`该行关联 ${wps.length} 张底稿：\n${list}`)
    } catch (e: any) { handleApiError(e, '查看相关底稿') }
  }

  function onDeCtxPenetrateToLedger() {
    deCtx.closeContextMenu()
    const note = currentNote.value
    if (!note?.note_section) { ElMessage.warning('请先选择附注章节'); return }
    const sel = deCtx.selectedCells.value[0]
    if (!sel) return
    const tableRows = activeTableData.value?.rows || []
    const row = tableRows[sel.row]
    const accountCode = row?.account_code || row?.values?.[0] || row?.cells?.[0] || ''
    if (accountCode) { penetrate.toLedger(String(accountCode)) }
    else { ElMessage.warning('无法识别当前行的科目编码') }
  }

  function onDeCtxViewDataSource() {
    deCtx.closeContextMenu()
    const note = currentNote.value
    if (!note?.note_section) { ElMessage.warning('请先选择附注章节'); return }
    cellDetailWpCode.value = note.note_section
    cellDetailSheet.value = ''
    cellDetailLabel.value = ''
    showCellFormulaDetail.value = true
  }

  function onDeCtxViewConsolBreakdown() {
    deCtx.closeContextMenu()
    const note = currentNote.value
    if (!note?.note_section) { ElMessage.warning('请先选择附注章节'); return }
    consolBreakdownSectionId.value = note.note_section
    consolBreakdownVisible.value = true
  }

  function onDeCtxOpenCellTrace() {
    deCtx.closeContextMenu()
    const note = currentNote.value
    if (!note?.id) { ElMessage.warning('请先选择附注章节'); return }
    const sel = deCtx.selectedCells.value[0]
    if (!sel) { ElMessage.warning('请先选中一个单元格'); return }
    cellTraceCtx.noteId = String(note.id)
    cellTraceCtx.rowIdx = sel.row
    cellTraceCtx.colIdx = sel.col
    showCellTrace.value = true
  }

  function onCellTracePenetrateTb(payload: { account_code: string }) {
    if (!payload?.account_code) return
    showCellTrace.value = false
    penetrate.toTB(payload.account_code)
  }

  function onCellDetailNavigate(uri: string) {
    showCellFormulaDetail.value = false
    const parts = uri.split(':')
    const mod = parts[0]?.toUpperCase()
    if (mod === 'WP' && parts[1]) {
      router.push({ name: 'WorkpaperEditor', params: { id: projectId.value }, query: { wp: parts[1] } })
    } else if (mod === 'REPORT') {
      router.push({ name: 'ReportView', params: { id: projectId.value } })
    } else if (mod === 'TB') {
      router.push({ path: `/projects/${projectId.value}/trial-balance` })
    }
  }

  async function onAutoCellTraceClick(rowIndex: number, colIndex: number, event: MouseEvent) {
    const note = currentNote.value
    if (!note?.note_section) return
    const cellId = `${note.note_section}:${rowIndex}:${colIndex}`
    tracePopoverPos.value = { x: event.clientX, y: event.clientY + 8 }
    tracePopoverVisible.value = true
    traceLoading.value = true
    traceData.value = null
    try {
      const resp: any = await api.get(P.disclosureNotes.traceSource(projectId.value, cellId))
      traceData.value = resp as TraceSourceData
    } catch (e) {
      handleApiError(e, '追溯来源')
      tracePopoverVisible.value = false
    } finally { traceLoading.value = false }
  }

  function onTraceJumpToTB(accountCode?: string) {
    tracePopoverVisible.value = false
    navPush({ source_view: route.fullPath, label: `附注 ${currentNote.value?.section_title || ''}`, direction: 'up' })
    const query: Record<string, string> = {}
    if (accountCode) query.account_code = accountCode
    router.push({ name: 'TrialBalance', params: { projectId: projectId.value }, query })
  }

  return {
    penetrate,
    showCellFormulaDetail, cellDetailWpCode, cellDetailSheet, cellDetailLabel,
    consolBreakdownVisible, consolBreakdownSectionId,
    showCellTrace, cellTraceCtx,
    tracePopoverVisible, traceLoading, traceData, tracePopoverPos,
    onDeCtxRelatedWp, onDeCtxPenetrateToLedger, onDeCtxViewDataSource,
    onDeCtxViewConsolBreakdown, onDeCtxOpenCellTrace, onCellTracePenetrateTb,
    onCellDetailNavigate, onAutoCellTraceClick, onTraceJumpToTB,
  }
}
