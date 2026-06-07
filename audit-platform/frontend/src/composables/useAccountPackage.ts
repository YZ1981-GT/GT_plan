/**
 * useAccountPackage — 科目工作包数据获取 composable
 *
 * spec workpaper-account-package-d1-d2-pilot Task 4/5
 *
 * 职责：
 * - 获取工作包列表（按 cycle 筛选）
 * - 获取工作包详情（sheets、external_cards、downstream）
 * - 获取工作包摘要（program_status_summary、missing_sources、stale_summary）
 * - 更新程序状态
 *
 * Validates: Requirements 1.2, 1.3, 2.1, 2.2, 2.3, 3.1
 */
import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'
import api from '@/utils/http'
import { eventBus } from '@/utils/eventBus'

// ─── Types ─────────────────────────────────────────────────────────────────

export interface PackageListItem {
  account_package_id: string
  cycle: string
  account_code: string
  account_name: string
  mapping_status: string
  primary_wp_code: string
  sheet_count: number
}

export interface SheetDef {
  sheet_name: string
  sheet_type: string
  source_wp_code?: string
  schema_ref?: string
}

export interface PackageDetail {
  account_package_id: string
  cycle: string
  account_code: string
  account_name: string
  mapping_status: string
  primary_wp_code: string
  control_panel_sheet: string | null
  source_wp_codes: string[]
  sheets: SheetDef[]
  external_cards: string[]
  downstream: string[]
}

export interface MissingSource {
  sheet_name: string
  source_wp_code: string
  reason: string
}

export interface PackageSummary {
  registry_status: string
  mapping_status: string
  program_status_summary: Record<string, any>
  external_cards: Array<Record<string, any>>
  stale_summary: Record<string, any>
  missing_sources: MissingSource[]
}

export interface ProgramStatus {
  id: string
  project_id: string
  account_package_id: string
  program_code: string
  applicable: boolean
  status: string
  evidence: string | null
  review_result: string | null
  conclusion: string | null
  not_applicable_reason: string | null
  reviewer: string | null
  reviewed_at: string | null
  updated_by: string | null
  updated_at: string | null
  created_at: string | null
}

export interface ProgramStatusUpdate {
  applicable?: boolean
  status?: string
  evidence?: string
  review_result?: string
  conclusion?: string
  not_applicable_reason?: string
}

// ─── Sheet type 分组定义 ─────────────────────────────────────────────────

export interface SheetTypeGroup {
  type: string
  label: string
  icon: string
  sheets: SheetDef[]
}

/** sheet_type → 中文标签映射 */
export const SHEET_TYPE_LABELS: Record<string, string> = {
  control_panel: '程序控制台',
  audit_sheet: '审定表',
  detail_table: '明细表',
  analysis: '分析',
  procedure: '检查程序',
  adjustment: '调整分录',
  disclosure: '附注披露',
  conclusion: '科目结论',
}

/** sheet_type → 图标映射 */
export const SHEET_TYPE_ICONS: Record<string, string> = {
  control_panel: '🎯',
  audit_sheet: '✅',
  detail_table: '📑',
  analysis: '📈',
  procedure: '🔍',
  adjustment: '✏️',
  disclosure: '📝',
  conclusion: '🏁',
}

/** 按 sheet_type 分组并排序 */
const SHEET_TYPE_ORDER = [
  'control_panel',
  'audit_sheet',
  'detail_table',
  'analysis',
  'procedure',
  'adjustment',
  'disclosure',
  'conclusion',
]

export function groupSheetsByType(sheets: SheetDef[]): SheetTypeGroup[] {
  const map = new Map<string, SheetDef[]>()
  for (const sheet of sheets) {
    const type = sheet.sheet_type || 'unknown'
    if (!map.has(type)) map.set(type, [])
    map.get(type)!.push(sheet)
  }

  const groups: SheetTypeGroup[] = []
  for (const type of SHEET_TYPE_ORDER) {
    const items = map.get(type)
    if (items && items.length > 0) {
      groups.push({
        type,
        label: SHEET_TYPE_LABELS[type] || type,
        icon: SHEET_TYPE_ICONS[type] || '📄',
        sheets: items,
      })
    }
  }
  // 添加未知类型
  for (const [type, items] of map) {
    if (!SHEET_TYPE_ORDER.includes(type) && items.length > 0) {
      groups.push({
        type,
        label: type,
        icon: '📄',
        sheets: items,
      })
    }
  }
  return groups
}

// ─── D2 坏账与 ECL 特殊分组 ──────────────────────────────────────────────

const BAD_DEBT_ECL_SHEETS = ['D2-3', 'D2-8', 'D2-9', 'D2-10', 'C-D2-disclosure']

export function isBadDebtEclSheet(sheetName: string): boolean {
  return BAD_DEBT_ECL_SHEETS.some((code) => sheetName.includes(code))
}

export function getBadDebtEclGroup(sheets: SheetDef[]): SheetDef[] {
  return sheets.filter(
    (s) =>
      isBadDebtEclSheet(s.sheet_name) ||
      s.sheet_name.includes('坏账') ||
      s.sheet_name.includes('ECL') ||
      s.sheet_name.includes('预期信用损失')
  )
}

// ─── D1 附注来源链路 ──────────────────────────────────────────────────────

export interface DisclosureSource {
  sheet_name: string
  source_type: string
  description: string
}

/** D1 附注来源链路：D1-1, D1-4, D1-8, D1-12 → C-D1-disclosure */
export const D1_DISCLOSURE_SOURCES: DisclosureSource[] = [
  { sheet_name: '审定表D1-1', source_type: 'audit_sheet', description: '审定表余额数据' },
  { sheet_name: '坏账准备明细表D1-4', source_type: 'detail_table', description: '坏账准备数据' },
  { sheet_name: '应收票据贴现背书明细表D1-8', source_type: 'detail_table', description: '贴现/背书数据' },
  { sheet_name: '应收票据质押检查表D1-12', source_type: 'procedure', description: '质押数据' },
]

// ─── Composable ──────────────────────────────────────────────────────────

export function useAccountPackage(projectId: Ref<string>) {
  const packages = ref<PackageListItem[]>([])
  const detail = ref<PackageDetail | null>(null)
  const summary = ref<PackageSummary | null>(null)
  const confirmationSummary = ref<Record<string, any> | null>(null)
  const programStatuses = ref<ProgramStatus[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const sheetGroups = computed<SheetTypeGroup[]>(() => {
    if (!detail.value) return []
    return groupSheetsByType(detail.value.sheets)
  })

  const missingSourceCards = computed<MissingSource[]>(() => {
    return summary.value?.missing_sources ?? []
  })

  const hasMissingSources = computed(() => missingSourceCards.value.length > 0)

  async function fetchPackages(cycle?: string) {
    loading.value = true
    error.value = null
    try {
      const params = cycle ? { cycle } : {}
      const res = await api.get(
        `/api/projects/${projectId.value}/account-packages`,
        { params }
      )
      packages.value = res.data ?? res
    } catch (e: any) {
      error.value = e.message ?? '获取工作包列表失败'
    } finally {
      loading.value = false
    }
  }

  async function fetchDetail(packageId: string) {
    loading.value = true
    error.value = null
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/account-packages/${packageId}`
      )
      detail.value = res.data ?? res
    } catch (e: any) {
      error.value = e.message ?? '获取工作包详情失败'
    } finally {
      loading.value = false
    }
  }

  async function fetchSummary(packageId: string) {
    loading.value = true
    error.value = null
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/account-packages/${packageId}/summary`
      )
      summary.value = res.data ?? res
    } catch (e: any) {
      error.value = e.message ?? '获取工作包摘要失败'
    } finally {
      loading.value = false
    }
  }

  async function fetchProgramStatuses(packageId: string) {
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/account-packages/${packageId}/program-status`
      )
      programStatuses.value = res.data ?? res
    } catch (e: any) {
      console.warn('[useAccountPackage] fetchProgramStatuses failed:', e)
    }
  }

  async function updateProgramStatus(
    packageId: string,
    programCode: string,
    update: ProgramStatusUpdate
  ) {
    try {
      const res = await api.patch(
        `/api/projects/${projectId.value}/account-packages/${packageId}/program-status/${programCode}`,
        update
      )
      // 刷新列表
      await fetchProgramStatuses(packageId)
      return res.data ?? res
    } catch (e: any) {
      error.value = e.message ?? '更新程序状态失败'
      throw e
    }
  }

  async function fetchConfirmationSummary(packageId: string) {
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/account-packages/${packageId}/confirmation-summary`
      )
      confirmationSummary.value = res.data ?? res
    } catch (e: any) {
      console.warn('[useAccountPackage] fetchConfirmationSummary failed:', e)
    }
  }

  // Task 6.3: confirmation:received 事件后刷新 D2 函证摘要卡片
  let _activePackageId: string | null = null
  function setActivePackageId(packageId: string) {
    _activePackageId = packageId
  }

  function _onConfirmationReceived(payload: any) {
    if (payload?.projectId && payload.projectId !== projectId.value) return
    if (_activePackageId) {
      void fetchConfirmationSummary(_activePackageId)
      void fetchSummary(_activePackageId)
    }
  }

  onMounted(() => {
    eventBus.on('confirmation:received', _onConfirmationReceived)
  })

  onUnmounted(() => {
    eventBus.off('confirmation:received', _onConfirmationReceived)
  })

  return {
    packages,
    detail,
    summary,
    confirmationSummary,
    programStatuses,
    loading,
    error,
    sheetGroups,
    missingSourceCards,
    hasMissingSources,
    fetchPackages,
    fetchDetail,
    fetchSummary,
    fetchConfirmationSummary,
    fetchProgramStatuses,
    updateProgramStatus,
    setActivePackageId,
  }
}
