import { ref, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { reports as P_reports } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import {
  getReportDrilldown,
  type ReportRow, type ReportDrilldownData,
} from '@/services/auditPlatformApi'
import { useNavigationStack } from '@/composables/useNavigationStack'
import type { useCellSelection } from '@/composables/useCellSelection'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface LineCompositionAccount {
  code: string
  name: string
  closing_balance: number
  pct: number
}

export interface LineCompositionData {
  line_code: string
  item_name: string
  total_amount: number
  accounts: LineCompositionAccount[]
}

export interface UseReportDrilldownOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number>
  activeTab: Ref<string>
  reportMode: Ref<string>
  activeTabLabel: ComputedRef<string>
  getRowType: (row: ReportRow) => string
  rvCtx: ReturnType<typeof useCellSelection>
}

export interface UseReportDrilldownReturn {
  drilldownVisible: Ref<boolean>
  drilldownLoading: Ref<boolean>
  drilldownData: Ref<ReportDrilldownData | null>
  onDrilldown: (row: ReportRow) => Promise<void>

  lineCompVisible: Ref<boolean>
  lineCompLoading: Ref<boolean>
  lineCompData: Ref<LineCompositionData | null>
  onLineComposition: (row: ReportRow) => Promise<void>
  onLineCompJumpToTB: (accountCode: string) => void

  noteRefsVisible: Ref<boolean>
  noteRefsLoading: Ref<boolean>
  noteRefsList: Ref<any[]>
  noteRefsRowCode: Ref<string>
  noteRefsRowName: Ref<string>
  onRvCtxShowNoteRefs: () => Promise<void>
  onJumpToNoteSection: (ref: { note_section: string; table_index: number }) => void
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useReportDrilldown(options: UseReportDrilldownOptions): UseReportDrilldownReturn {
  const {
    projectId, year, activeTab, reportMode,
    activeTabLabel, getRowType, rvCtx,
  } = options

  const router = useRouter()
  const { push: navPush } = useNavigationStack()

  // ─── Drilldown ──────────────────────────────────────────────────────────────
  const drilldownVisible = ref(false)
  const drilldownLoading = ref(false)
  const drilldownData = ref<ReportDrilldownData | null>(null)

  async function onDrilldown(row: ReportRow) {
    if (!row.row_code || row.is_total_row) return
    drilldownVisible.value = true
    drilldownLoading.value = true
    drilldownData.value = null
    try {
      const result = await getReportDrilldown(projectId.value, year.value, activeTab.value, row.row_code)
      drilldownData.value = {
        ...result,
        accounts: result.accounts.map((item: any) => ({
          ...item,
          amount: reportMode.value === 'unadjusted'
            ? (item.unadjusted_amount ?? item.amount ?? '0')
            : (item.audited_amount ?? item.amount ?? '0'),
        })),
      }
    } catch (e) {
      handleApiError(e, '穿透查询')
    } finally {
      drilldownLoading.value = false
    }
  }

  // ─── Line Composition ───────────────────────────────────────────────────────
  const lineCompVisible = ref(false)
  const lineCompLoading = ref(false)
  const lineCompData = ref<LineCompositionData | null>(null)

  async function onLineComposition(row: ReportRow) {
    if (!row.row_code || row.is_total_row || getRowType(row) === 'header') return
    lineCompVisible.value = true
    lineCompLoading.value = true
    lineCompData.value = null
    try {
      const resp: any = await api.get(P_reports.lineComposition(projectId.value, row.row_code))
      lineCompData.value = resp as LineCompositionData
    } catch (e) {
      handleApiError(e, '构成科目查询')
      lineCompVisible.value = false
    } finally {
      lineCompLoading.value = false
    }
  }

  function onLineCompJumpToTB(accountCode: string) {
    lineCompVisible.value = false
    navPush({
      source_view: router.currentRoute.value.fullPath,
      label: `报表 ${activeTabLabel.value}`,
      direction: 'down',
    })
    router.push({
      name: 'TrialBalance',
      params: { projectId: projectId.value },
      query: { account_code: accountCode },
    })
  }

  // ─── Note References ────────────────────────────────────────────────────────
  const noteRefsVisible = ref(false)
  const noteRefsLoading = ref(false)
  const noteRefsRowCode = ref('')
  const noteRefsRowName = ref('')
  const noteRefsList = ref<Array<{ note_section: string; section_title: string; table_index: number }>>([])

  async function onRvCtxShowNoteRefs() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) {
      ElMessage.info('该行无 row_code，无法反查附注引用')
      return
    }
    noteRefsRowCode.value = row.row_code
    noteRefsRowName.value = row.row_name || ''
    noteRefsList.value = []
    noteRefsVisible.value = true
    noteRefsLoading.value = true
    try {
      const resp: any = await api.get(P_reports.noteReferences(projectId.value, year.value, row.row_code))
      noteRefsList.value = (resp?.notes || []) as any[]
    } catch (e) {
      handleApiError(e, '反查附注引用')
    } finally {
      noteRefsLoading.value = false
    }
  }

  function onJumpToNoteSection(ref: { note_section: string; table_index: number }) {
    noteRefsVisible.value = false
    router.push({
      path: `/projects/${projectId.value}/disclosure-notes`,
      query: {
        section: ref.note_section,
        table_index: String(ref.table_index ?? 0),
        year: String(year.value),
      },
    })
  }

  return {
    drilldownVisible,
    drilldownLoading,
    drilldownData,
    onDrilldown,

    lineCompVisible,
    lineCompLoading,
    lineCompData,
    onLineComposition,
    onLineCompJumpToTB,

    noteRefsVisible,
    noteRefsLoading,
    noteRefsList,
    noteRefsRowCode,
    noteRefsRowName,
    onRvCtxShowNoteRefs,
    onJumpToNoteSection,
  }
}
