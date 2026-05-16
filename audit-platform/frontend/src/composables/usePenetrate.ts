/**
 * usePenetrate — 统一穿透导航 composable [R7-S3-09 Task 43]
 *
 * 封装所有跨模块穿透跳转逻辑，消除各视图散乱的 router.push 拼接。
 * 所有金额单元格双击/右键穿透统一走此 composable。
 *
 * @example
 * const { toLedger, toWorkpaper, toReportRow, toAdjustment, toMisstatement, toNote } = usePenetrate()
 * // 双击金额 → 穿透到序时账
 * toLedger('1001')
 */
import { useRouter, useRoute } from 'vue-router'

export function usePenetrate() {
  const router = useRouter()
  const route = useRoute()

  function pid(): string {
    return (route.params.projectId as string) || ''
  }

  function year(): number {
    return Number(route.query.year) || new Date().getFullYear() - 1
  }

  return {
    /** 穿透到序时账（按科目编码） */
    toLedger(accountCode: string) {
      router.push({
        path: `/projects/${pid()}/ledger`,
        query: { code: accountCode, year: String(year()) },
      })
    },

    /** 穿透到底稿（按底稿编码） */
    toWorkpaper(wpCode: string) {
      router.push({
        path: `/projects/${pid()}/workpapers`,
        query: { code: wpCode },
      })
    },

    /** 穿透到报表行明细 */
    toReportRow(reportType: string, rowCode: string) {
      router.push({
        path: `/projects/${pid()}/reports`,
        query: { tab: reportType, row: rowCode, year: String(year()) },
      })
    },

    /** 穿透到调整分录（按科目或分录组 ID） */
    toAdjustment(accountOrGroupId: string) {
      router.push({
        path: `/projects/${pid()}/adjustments`,
        query: { account: accountOrGroupId, year: String(year()) },
      })
    },

    /** 穿透到未更正错报 */
    toMisstatement(id: string) {
      router.push({
        path: `/projects/${pid()}/misstatements`,
        query: { id, year: String(year()) },
      })
    },

    /** 穿透到附注章节 */
    toNote(sectionId: string) {
      router.push({
        path: `/projects/${pid()}/disclosure-notes`,
        query: { section: sectionId, year: String(year()) },
      })
    },

    /** 穿透到底稿编辑器 */
    toWorkpaperEditor(wpId: string) {
      router.push({
        path: `/projects/${pid()}/workpapers/${wpId}/edit`,
      })
    },

    // ─── Sprint 11: 全链路穿透扩展 (Requirements: 28.1-28.6) ───

    /** 报表行次 → 附注章节（正向穿透） */
    toNoteFromReport(rowCode: string) {
      router.push({
        path: `/projects/${pid()}/disclosure-notes`,
        query: { fromReport: rowCode, year: String(year()) },
      })
    },

    /** 附注 → 报表行次（反向穿透） */
    toReportFromNote(sectionCode: string) {
      router.push({
        path: `/projects/${pid()}/reports`,
        query: { fromNote: sectionCode, year: String(year()) },
      })
    },

    /** 报表行次 → 底稿审定表 → 调整分录 */
    toWorkpaperFromReport(rowCode: string) {
      router.push({
        path: `/projects/${pid()}/workpapers`,
        query: { fromReport: rowCode, year: String(year()) },
      })
    },

    /** 调整分录 → 影响范围分析 */
    toImpactAnalysis(adjustmentId: string) {
      router.push({
        path: `/projects/${pid()}/adjustments`,
        query: { impact: adjustmentId, year: String(year()) },
      })
    },
  }
}
