/**
 * useFormulaSource — 公式三来源（preset / custom / reference）数据源 composable
 *
 * Task 21.2（formula-management-library，Req 25.1-25.6）：
 * 支撑 GtFormulaEditDialog 的「来源选择」最小增量：
 *  - `preset`：从预设库一键套用（预设条目由 useFormulaImportExport.getPresetPage 供给，
 *    本 composable 只做候选归一化，不重复实现预设库）。
 *  - `custom`：自定义覆盖；复用 `wp_user_formulas` 的 restore/delete 端点
 *    `DELETE /api/workpapers/{wpId}/user-formulas/{cell_key}` 恢复预设（Req 25.4，**不重写该端点**）。
 *  - `reference`：参照已保存公式；候选取 `GET /api/workpapers/{wpId}/formulas`
 *    返回的公式列表，选中后复用其 expression（reference 解析已由 Task 21.1 后端落地，
 *    本前端仅携带 reference_formula_id 至保存请求，Req 25.5）。
 *
 * 全部使用 http (axios)，自动携带 Authorization header（不用原生 fetch，避免 401）。
 *
 * Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6
 */
import { ref, type Ref } from 'vue'
import http from '@/utils/http'
// spec: formula-management-runtime-closure Task 14 — 端点收敛进 apiPaths（纯搬迁）
import { wpFormula, wpUserFormula } from '@/services/apiPaths/formula'

// ─── Types ──────────────────────────────────────────────────────────────────

/** 公式三来源标识（与后端 _VALID_FORMULA_SOURCES 对齐）。 */
export type FormulaSource = 'preset' | 'custom' | 'reference'

/** reference 参照来源候选（取自 GET /formulas 已保存公式列表）。 */
export interface ReferenceCandidate {
  /** 源公式 id（保存 reference 公式时作为 reference_formula_id 落库） */
  id: string
  sheet_name: string
  target_cell: string
  expression: string
  formula_type: string
}

export interface UseFormulaSourceReturn {
  /** reference 候选源公式列表 */
  candidates: Ref<ReferenceCandidate[]>
  candidatesLoading: Ref<boolean>
  restoring: Ref<boolean>
  /** 拉取某底稿已保存公式作为 reference 候选源 */
  loadReferenceCandidates: (wpId: string) => Promise<void>
  /**
   * 恢复预设：删除该 cell 的用户自定义覆盖，使其回退到预设公式（Req 25.4）。
   * 复用既有 restore/delete 端点，不重写。返回是否成功。
   */
  restorePreset: (wpId: string, cellKey: string) => Promise<boolean>
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useFormulaSource(): UseFormulaSourceReturn {
  const candidates = ref<ReferenceCandidate[]>([])
  const candidatesLoading = ref(false)
  const restoring = ref(false)

  async function loadReferenceCandidates(wpId: string): Promise<void> {
    if (!wpId) return
    if (candidatesLoading.value) return
    candidatesLoading.value = true
    try {
      const resp = await http.get(wpFormula.list(wpId))
      // http 拦截器已解包 {code,data} 信封 → resp.data 即 {items:[...]}
      const payload: any = resp?.data ?? {}
      const items: any[] = Array.isArray(payload.items)
        ? payload.items
        : Array.isArray(payload.data?.items)
          ? payload.data.items
          : []
      candidates.value = items.map((it) => ({
        id: String(it.id),
        sheet_name: it.sheet_name ?? '',
        target_cell: it.target_cell ?? '',
        expression: it.expression ?? '',
        formula_type: it.formula_type ?? 'auto_calc',
      }))
    } catch (e) {
      console.warn('[useFormulaSource] loadReferenceCandidates 失败', e)
      candidates.value = []
    } finally {
      candidatesLoading.value = false
    }
  }

  async function restorePreset(wpId: string, cellKey: string): Promise<boolean> {
    if (!wpId || !cellKey) return false
    if (restoring.value) return false
    restoring.value = true
    try {
      await http.delete(
        wpUserFormula.restorePreset(wpId, encodeURIComponent(cellKey)),
      )
      return true
    } catch (e) {
      console.warn('[useFormulaSource] restorePreset 失败', e)
      return false
    } finally {
      restoring.value = false
    }
  }

  return {
    candidates,
    candidatesLoading,
    restoring,
    loadReferenceCandidates,
    restorePreset,
  }
}

export default useFormulaSource
