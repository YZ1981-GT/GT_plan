/**
 * usePenetrate — 统一穿透导航 composable [R7-S3-09 Task 43]
 *
 * 封装所有跨模块穿透跳转逻辑，消除各视图散乱的 router.push 拼接。
 * 所有金额单元格双击/右键穿透统一走此 composable。
 * V3 Req 8.3.1: 每次穿透跳转前自动 push 当前路由到 useNavigationStack。
 *
 * @example
 * const { toLedger, toWorkpaper, toReportRow, toAdjustment, toMisstatement, toNote } = usePenetrate()
 * // 双击金额 → 穿透到序时账
 * toLedger('1001')
 */
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { openWorkpaperCell } from '@/services/openWorkpaperCell'
import { useNavigationStack, type NavigationEntry } from './useNavigationStack'
import { useProjectStore } from '@/stores/project'
import { parseAuditYear, yearQuery } from '@/utils/resolveAuditYear'

export function usePenetrate() {
  const router = useRouter()
  const route = useRoute()
  const { push: navPush } = useNavigationStack()

  function pid(): string {
    return (route.params.projectId as string) || ''
  }

  /** 当前年度：路由 → 项目 store；都没有为 null（跳转不带 year，目标页按项目审计年度取；原先兜底去年） */
  function year(): number | null {
    const routeYear = parseAuditYear(route.query.year)
    if (routeYear != null) return routeYear
    try {
      return useProjectStore().year
    } catch {
      return null // 无 pinia 上下文
    }
  }

  /**
   * V3 Req 8.3.1: 跳转前自动 push 当前路由到 navigation stack
   * @param label 面包屑显示文本（可选，默认从 route.meta.title 推断）
   * @param direction 穿透方向标记
   */
  function _pushCurrentRoute(label?: string, direction?: 'down' | 'up') {
    const entry: NavigationEntry = {
      source_view: route.fullPath,
      label: label || (route.meta?.title as string) || undefined,
      direction,
      scroll_position: window.scrollY,
    }
    navPush(entry)
  }

  return {
    /** 穿透到序时账（按科目编码） */
    toLedger(accountCode: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/ledger`,
        query: { code: accountCode, ...yearQuery(year()) },
      })
    },

    /** 穿透到试算表（按科目编码） — Sprint 2 Task 2.4 CellTrace 使用 */
    toTB(accountCode: string) {
      router.push({
        path: `/projects/${pid()}/trial-balance`,
        query: { code: accountCode, ...yearQuery(year()) },
      })
    },

    /** 穿透到底稿（按底稿编码） */
    toWorkpaper(wpCode: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/workpapers`,
        query: { code: wpCode },
      })
    },

    /** 穿透到报表行明细 */
    toReportRow(reportType: string, rowCode: string) {
      _pushCurrentRoute(undefined, 'up')
      router.push({
        path: `/projects/${pid()}/reports`,
        query: { tab: reportType, row: rowCode, ...yearQuery(year()) },
      })
    },

    /** 穿透到调整分录（按科目或分录组 ID） */
    toAdjustment(accountOrGroupId: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/adjustments`,
        query: { account: accountOrGroupId, ...yearQuery(year()) },
      })
    },

    /** 穿透到未更正错报 */
    toMisstatement(id: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/misstatements`,
        query: { id, ...yearQuery(year()) },
      })
    },

    /** 穿透到附注章节 */
    toNote(sectionId: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/disclosure-notes`,
        query: { section: sectionId, ...yearQuery(year()) },
      })
    },

    /** 穿透到底稿编辑器（可选带定位上下文） */
    toWorkpaperEditor(wpId: string, locate?: { sheet?: string; cell?: string }) {
      _pushCurrentRoute(undefined, 'down')
      const query: Record<string, string> = {}
      if (locate?.sheet) query.sheet = locate.sheet
      if (locate?.cell) query.cell = locate.cell
      router.push({
        path: `/projects/${pid()}/workpapers/${wpId}/edit`,
        query: Object.keys(query).length > 0 ? query : undefined,
      })
    },

    // ─── Sprint 11: 全链路穿透扩展 (Requirements: 28.1-28.6) ───

    /** 报表行次 → 附注章节（正向穿透） */
    toNoteFromReport(rowCode: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/disclosure-notes`,
        query: { fromReport: rowCode, ...yearQuery(year()) },
      })
    },

    /** 附注 → 报表行次（反向穿透） */
    toReportFromNote(sectionCode: string) {
      _pushCurrentRoute(undefined, 'up')
      router.push({
        path: `/projects/${pid()}/reports`,
        query: { fromNote: sectionCode, ...yearQuery(year()) },
      })
    },

    /** 报表行次 → 底稿审定表 → 调整分录 */
    toWorkpaperFromReport(rowCode: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/workpapers`,
        query: { fromReport: rowCode, ...yearQuery(year()) },
      })
    },

    /** 调整分录 → 影响范围分析 */
    toImpactAnalysis(adjustmentId: string) {
      _pushCurrentRoute(undefined, 'down')
      router.push({
        path: `/projects/${pid()}/adjustments`,
        query: { impact: adjustmentId, ...yearQuery(year()) },
      })
    },

    /** 附注 → 底稿 cell 直达（wp-traceability-panel Task 4.1）：按编码取本项目底稿后打开编辑器并带 ?sheet=&cell=
     *  （原先跳底稿列表页，列表页不读 code / sheet / cell，定位丢失；spec wp-deeplink-locate-coverage-closure） */
    async toWorkpaperFromNote(wpCode: string, locate?: { sheet?: string; cell?: string }) {
      _pushCurrentRoute(undefined, 'up')
      const reason = await openWorkpaperCell(router, { projectId: pid(), wpCode, sheet: locate?.sheet, cell: locate?.cell })
      if (reason) ElMessage.warning(reason)
    },
  }
}
