/**
 * useAuditCheckReport — 前端运行时勾稽判定上报（S6）
 *
 * audit-check-review-gate-hardening Task 4.3
 *
 * 底稿现有 composable（useReportCrossCheck / tbReconcile / adjustmentReconcile 等）
 * 的**运行时勾稽判定结果**通过本 composable 上报到后端
 * `POST /api/projects/{pid}/workpapers/{wp_id}/audit-checks/report`（Task 4.2），
 * 写入统一 `parsed_data.audit_checks` 缓存，供「审计检查」面板一处读。
 *
 * 设计约束（design §3 / Req3.1/3.3/4.1）：
 * - **不新造判定**：items 全部来自底稿已有 composable 的 computed 结果映射，
 *   仅 map 成上报格式，不在此重新计算勾稽。
 * - **旁路增强**：上报失败静默（`_silent` + `console.warn`），绝不阻断底稿保存主流程。
 * - **同 source 覆盖不累积**：后端按 `source` 命名空间 upsert，重报覆盖旧项。
 * - **空 items 跳过**：无判定项时不发请求（避免无意义清空/请求）。
 *
 * source 必须 ∈ 前端可上报枚举：
 *   `tb_recon` | `adjustment_recon` | `report_cross_check` | `cross_sheet`
 * （其他 source 后端一律 400，本 composable 由调用方保证传对；失败静默不影响主流程）
 *
 * 注意：`@/utils/http` baseURL='/' 不自动加 /api，URL 必须自带 `/api` 前缀
 * （本仓库铁律，与同目录其它 composable 一致）。
 */
import http from '@/utils/http'

/** 单条上报检查项（与后端 ReportedCheckItem 字段对齐） */
export interface AuditCheckItemInput {
  /** 检查项稳定编码（如 'K11-1-vs-TB-6701'） */
  code: string
  /** 严重度：info | warning | error（前端勾稽通常 warning） */
  severity?: string
  /** 检查类型：balance | reconciliation | cross_ref 等 */
  check_type?: string
  /** 检查项描述 */
  description?: string
  /** 判定消息（一致 / 差异说明） */
  message?: string
  /** 三态：一致→true，不一致→false，数据缺失/未判定→null（不误判 true） */
  passed?: boolean | null
  /** 实际值（本表侧） */
  actual?: number | null
  /** 期望值（勾稽目标侧） */
  expected?: number | null
  /** 差额 */
  diff?: number | null
  /** 定位提示（sheet 编码，供面板跳转） */
  sheet_hint?: string | null
}

export function useAuditCheckReport() {
  /**
   * 上报某底稿某 source 命名空间的运行时勾稽判定。
   *
   * @param projectId 项目 ID
   * @param wpId 底稿 ID
   * @param source 上报来源枚举（tb_recon/adjustment_recon/report_cross_check/cross_sheet）
   * @param items 判定项（来自底稿现有 composable 映射，不新造判定）
   *
   * 行为：
   * - `items` 为空数组 → 跳过请求（不上报空）
   * - 缺 projectId/wpId/source → 跳过（无法定位）
   * - 请求失败 → `console.warn` 静默，不抛错、不阻断主流程
   */
  async function reportAuditChecks(
    projectId: string,
    wpId: string,
    source: string,
    items: AuditCheckItemInput[],
  ): Promise<void> {
    if (!projectId || !wpId || !source) return
    if (!Array.isArray(items) || items.length === 0) return

    try {
      await http.post(
        `/api/projects/${projectId}/workpapers/${wpId}/audit-checks/report`,
        { source, items },
        // 旁路增强：失败不弹全局 toast，由本 composable 静默处理
        { _silent: true } as Record<string, unknown>,
      )
    } catch (err) {
      // 上报失败不阻断底稿编制/保存主流程，仅告警
      console.warn('[useAuditCheckReport] 审计检查上报失败', { source, wpId }, err)
    }
  }

  return { reportAuditChecks }
}
