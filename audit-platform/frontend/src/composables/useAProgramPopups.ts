/**
 * useAProgramPopups — A 类程序表弹窗完成状态 + A16 推荐版本 + 程序行加载 + 导出
 *
 * 从 GtAProgramConsole.vue 抽出（spec workpaper-frontend-large-component-split, Req 1 复盘修正②）：
 * - 程序行数据加载：programs state + initData/fetchProcedureTableData（htmlData 优先，空则拉 procedure-tables API）
 * - 弹窗完成状态回显：popupCompletionStatus/reviewSignStatus state + checkCompletion + loadPopupCompletionStatus
 *   （A21~25 复核签字 / A16 询证 / A1-11/12/17/18 完成规则）
 * - A16 seq2 推荐版本：a16RecommendedCode/a16OtherExpanded + isA16Seq2Row/a16OtherVersions + fetchA16RecommendedVersion
 * - 导出程序表为 Excel：exportProgramTable
 *
 * 铁律：行为零变更、保响应式（ref/computed）；不在 composable 内 emit（数据/回调由主组件 wire）；
 *       依赖单向（主组件 → composable → util/api）；composable 之间不互相 import（共享依赖由主组件传入）。
 *
 * @example
 * const popups = useAProgramPopups({
 *   wpId: () => props.wpId,
 *   sheetName: () => props.sheetName,
 *   projectId,
 *   htmlData: () => props.htmlData,
 *   applicableWhen,
 *   parseLinkedWorkpapers,
 *   statusLabel,
 *   getYear: () => parseInt(route.query.year as string) || new Date().getFullYear(),
 * })
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { INLINE_POPUP_WP_CODES } from '@/components/workpaper/wpPopupDocxConfigs'

// ─── Types（与 GtAProgramConsole.vue 结构一致，composable 独立持有避免互相 import）───
interface ProgramAssertions {
  existence?: boolean
  completeness?: boolean
  rights?: boolean
  accuracy?: boolean
  presentation?: boolean
}

interface ProgramHistoryItem {
  timestamp: string
  user: string
  action: string
  reason?: string
}

interface ProgramRow {
  id: string
  program_no: number
  program_desc: string
  program_category: string
  assertions?: ProgramAssertions
  linked_workpapers?: string
  execution_summary?: string
  status: string
  trim_reason?: string
  history?: ProgramHistoryItem[]
  attachment_count?: number
  phase?: string
}

interface TrimDecision {
  programId: string
  reason: string
  timestamp?: string
  user?: string
}

interface AProgramHtmlData {
  programs: ProgramRow[]
  trim_decisions: TrimDecision[]
  signatures?: Array<{ role: string; name: string; date: string }>
}

export function useAProgramPopups(options: {
  /** 当前底稿 wpId 取值（getter，保持响应式） */
  wpId: () => string
  /** 当前底稿 sheetName 取值（getter，保持响应式） */
  sheetName: () => string
  /** 项目 ID */
  projectId: Ref<string>
  /** htmlData 取值（getter，保持响应式） */
  htmlData: () => AProgramHtmlData
  /** B30 等仅限合并审计底稿的 applicable_when 标记（主组件持有，fetchProcedureTableData 写回） */
  applicableWhen: Ref<string | null>
  /** 解析 linked_workpapers 字符串为数组（主组件持有，传入复用） */
  parseLinkedWorkpapers: (value: string) => string[]
  /** 状态码 → 中文标签（主组件持有，导出复用） */
  statusLabel: (status: string) => string
  /** 当前审计年度取值（getter，与主组件 route.query.year 口径一致） */
  getYear: () => number
}) {
  const { projectId, applicableWhen, parseLinkedWorkpapers, statusLabel, getYear } = options

  // ─── State ───
  const programs = ref<ProgramRow[]>([])

  /** 从 sheetName 提取 table_code (如 "审计程序A8" → "A8") */
  function extractTableCode(sheetName: string): string {
    // 匹配 A1~A17 格式（防御：a11-bundle 等嵌套渲染场景 sheetName 可能为 undefined）
    const m = sheetName?.match(/[A-S]\d+/)
    return m ? m[0] : ''
  }

  // ─── A16 seq2 推荐版本 + 折叠状态 ───
  const a16RecommendedCode = ref('')
  const a16OtherExpanded = ref(false)

  /** 判断当前程序表是否为 A16（从 sheetName 提取） */
  const isA16Table = computed(() => {
    const code = extractTableCode(options.sheetName())
    return code === 'A16'
  })

  /** 判断某行是否是 A16 seq2（含 A16-1~6 多版本 ref_index 的行） */
  function isA16Seq2Row(row: ProgramRow): boolean {
    if (!isA16Table.value) return false
    if (!row.linked_workpapers) return false
    const refs = parseLinkedWorkpapers(row.linked_workpapers)
    // A16 seq2 特征：ref_index 包含多个 A16-x 格式的子码
    const a16Refs = refs.filter(r => /^A16-[1-6]$/.test(r))
    return a16Refs.length >= 3 // 至少 3 个 A16-x 子码才认为是 seq2
  }

  /** 计算其他版本列表（排除推荐版本） */
  const a16OtherVersions = computed(() => {
    if (!a16RecommendedCode.value) return []
    // 从第一个匹配的 seq2 行中提取所有 A16-x refs
    const seq2Row = programs.value.find(r => isA16Seq2Row(r))
    if (!seq2Row) return []
    const allRefs = parseLinkedWorkpapers(seq2Row.linked_workpapers || '')
      .filter(r => /^A16-[1-6]$/.test(r))
    return allRefs.filter(r => r !== a16RecommendedCode.value)
  })

  /** 从 API 获取 A16 推荐版本 */
  async function fetchA16RecommendedVersion() {
    if (!isA16Table.value || !projectId.value) return
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/a16/recommended-version`,
      )
      const data = res?.data || res
      if (data?.main?.code) {
        a16RecommendedCode.value = data.main.code
      }
    } catch {
      // 降级：不显示推荐标记，正常渲染全部 chip
    }
  }

  // ─── 弹窗完成状态回显 ───
  const popupCompletionStatus = ref<Record<string, 'completed' | 'in_progress' | 'none'>>({})
  const reviewSignStatus = ref<Record<string, string | null>>({})

  /** 完成规则：根据 checklist_responses 判定子底稿完成状态 */
  function checkCompletion(wpCode: string, responses: Record<string, any>): 'completed' | 'in_progress' | 'none' {
    if (/^A2[1-5]-/.test(wpCode)) {
      const st = reviewSignStatus.value[wpCode] ?? responses[`${wpCode}-sign`]?.conclusion
      if (st === 'pass') return 'completed'
      if (st === 'reject') return 'in_progress'
      const chkPrefix = `${wpCode}-chk-`
      const chkIds = Object.keys(responses).filter(k => k.startsWith(chkPrefix))
      if (chkIds.some(id => responses[id]?.conclusion)) return 'in_progress'
      return 'none'
    }
    if (/^A16-\d/.test(wpCode)) {
      const st = responses[`${wpCode}-sign-status`]?.conclusion
      if (st === 'signed') return 'completed'
      if (st === 'sent') return 'in_progress'
      return 'none'
    }
    switch (wpCode) {
      case 'A1-17': {
        const ids = ['A1-17-001', 'A1-17-002', 'A1-17-003']
        const done = ids.filter(id => responses[id]?.conclusion).length
        if (done === ids.length) return 'completed'
        if (done > 0) return 'in_progress'
        return 'none'
      }
      case 'A1-12': {
        const ids = Array.from({ length: 14 }, (_, i) => `A1-12-${String(i + 1).padStart(3, '0')}`)
        const done = ids.filter(id => responses[id]?.conclusion).length
        if (done === ids.length) return 'completed'
        if (done > 0) return 'in_progress'
        return 'none'
      }
      case 'A1-11': {
        // 必填：项目经理+合伙人；A类额外：独立复核合伙人+EQCR
        const requiredIds = ['A1-11-sign-pm', 'A1-11-sign-partner']
        const allIds = [...requiredIds, 'A1-11-sign-irp', 'A1-11-sign-eqcr']
        const allDone = allIds.filter(id => responses[id]?.conclusion).length
        const requiredDone = requiredIds.filter(id => responses[id]?.conclusion).length
        if (requiredDone === requiredIds.length) return 'completed'
        if (allDone > 0) return 'in_progress'
        return 'none'
      }
      case 'A1-18': {
        return responses['A1-18-conclusion']?.conclusion ? 'completed' : 'none'
      }
      default: return 'none'
    }
  }

  /** 批量查询子底稿 checklist_responses，计算各弹窗底稿完成状态 */
  async function loadPopupCompletionStatus() {
    if (!options.wpId()) return
    try {
      if (projectId.value) {
        try {
          const signRes = await api.get(
            `/api/projects/${projectId.value}/a21/review-sign-status`,
          )
          reviewSignStatus.value = signRes?.data ?? signRes ?? {}
        } catch { reviewSignStatus.value = {} }
      }
      const res = await api.get(`/api/workpapers/${options.wpId()}/checklist-responses`)
      const list = Array.isArray(res) ? res : (res?.data ?? [])
      const byId: Record<string, any> = {}
      for (const r of list) {
        byId[r.item_id] = r
      }
      for (const code of INLINE_POPUP_WP_CODES) {
        popupCompletionStatus.value[code] = checkCompletion(code, byId)
      }
    } catch { /* ignore */ }
  }

  // ─── 程序行数据加载 ───
  /** 从 htmlData 初始化程序行（空则从 procedure-tables API 拉取兜底） */
  function initData() {
    const htmlData = options.htmlData()
    if (htmlData?.programs && htmlData.programs.length > 0) {
      programs.value = JSON.parse(JSON.stringify(htmlData.programs))
    } else {
      programs.value = []
      // htmlData 为空时自动从 procedure-tables API 拉取
      fetchProcedureTableData()
    }
  }

  /** 从 procedure-tables API 拉取程序行数据（htmlData 为空的兜底） */
  async function fetchProcedureTableData() {
    if (!projectId.value) return
    // 从 sheetName 推导 table_code：如 "审计程序A8" → "A8"
    const tableCode = extractTableCode(options.sheetName())
    if (!tableCode) return
    const year = getYear()
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/procedure-tables/${tableCode}`,
        { params: { year } },
      )
      const data = res?.data || res
      if (data?.items && Array.isArray(data.items)) {
        programs.value = data.items.map((item: any, idx: number) => ({
          id: item._key || `proc-${idx}`,
          program_no: item.seq,
          program_desc: item.content,
          program_category: '',
          linked_workpapers: item.ref_index || '',
          execution_summary: item.summary || '',
          status: item.step_status || ((item.applicable === 'na' || item.applicable === 'no') ? 'not_applicable' : 'pending'),
          phase: item.phase || undefined,
        }))
      }
      // 存储 applicable_when（B30 等仅限合并审计的底稿）
      if (data?.applicable_when) {
        applicableWhen.value = data.applicable_when
      }
    } catch {
      // 静默——api 可能未实现或无数据
    }
  }

  /** 导出程序表为 Excel */
  async function exportProgramTable() {
    const { useExcelIO } = await import('@/composables/useExcelIO')
    const { exportData } = useExcelIO()
    const data = programs.value.map(p => ({
      '序号': p.program_no,
      '程序描述': p.program_desc,
      '关联底稿': p.linked_workpapers || '',
      '执行说明': p.execution_summary || '',
      '状态': statusLabel(p.status),
    }))
    await exportData({
      data,
      columns: [
        { key: '序号', header: '序号' },
        { key: '程序描述', header: '审计程序' },
        { key: '关联底稿', header: '索引号' },
        { key: '执行说明', header: '执行情况说明' },
        { key: '状态', header: '状态' },
      ],
      sheetName: options.sheetName() || '程序表',
      fileName: `${options.sheetName() || 'A1'} 程序表.xlsx`,
    })
  }

  return {
    // state
    programs,
    popupCompletionStatus,
    a16RecommendedCode,
    a16OtherExpanded,
    // computed
    a16OtherVersions,
    // A16 seq2
    isA16Seq2Row,
    // 数据加载
    initData,
    fetchProcedureTableData,
    // 弹窗完成状态
    loadPopupCompletionStatus,
    // A16 推荐版本
    fetchA16RecommendedVersion,
    // 导出
    exportProgramTable,
  }
}
