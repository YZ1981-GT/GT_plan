/**
 * useD2FormData — D2 应收账款数据加载/debounce保存/即时保存/辅助
 *
 * Spec: .kiro/specs/d2-accounts-receivable/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 D2-* 数据
 * - debounce 2s 文本字段保存 / 结论/状态/选择类字段立即保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses
 * - trial_balance 回写：writebackTrialBalance
 * - 子底稿数据读取：loadSubWorkpaperData（D2-2）
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { getWpIndex } from '@/services/workpaperApi'
import {
  useChecklistPersistence,
  type ChecklistResponse as PersistenceChecklistResponse,
} from '@/composables/workpaper/useChecklistPersistence'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ChecklistItem = PersistenceChecklistResponse
export type ChecklistResponse = ChecklistItem

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2FormData(wpId: Ref<string>, projectId?: Ref<string>, htmlData?: Ref<any>) {
  const persistence = useChecklistPersistence({ wpId, projectId, debounceMs: 2000 })
  const allResponses = persistence.responses
  const loading = ref(false)
  const saving = ref(false)

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      await persistence.load()
      // D2 主入口只暴露本循环 item，避免其他历史响应污染业务 composable。
      const d2Responses = new Map<string, ChecklistResponse>()
      for (const [itemId, response] of allResponses.value) {
        if (itemId.startsWith('D2-')) d2Responses.set(itemId, response)
      }
      persistence.hydrate(d2Responses)

      // 自动取试算平衡表 1122 科目余额 → D2-adj-tb-amount 锚点（seed 回退）
      // 🔴 主路径是 Tier A 公式（灰度开时由 render `seed_tier_a_reconciliation` 写入），
      //    此处只是前端自行 seed 的**回退**（灰度关/公式被停用时兜底）。
      //    **优先读 render 下发的 `project_context.tb_amount`（净额口径）**，
      //    只在无下发时才自行查 TB API（灰度关时 render 不下发，保持原值回退行为不变）。
      //    口径说明：审定表 D2-1 比的是「三、应收账款净值」合计 A27（原值 − 坏账准备），
      //    取原值会产生恰好等于坏账准备的假差异（D1 同款缺陷已实测）。
      if (projectId?.value) {
        try {
          const renderTbAmount = (htmlData?.value as any)?.project_context?.tb_amount
          if (renderTbAmount !== undefined && renderTbAmount !== null) {
            // render 已下发净额（灰度开时），直接用
            allResponses.value.set('D2-adj-tb-amount', {
              item_id: 'D2-adj-tb-amount',
              conclusion: null,
              remark: String(Number(renderTbAmount)),
            })
          } else {
            // 灰度关 / render 未下发：自行查 TB 回退（原值口径，与改动前行为一致）
            let year = new Date().getFullYear() - 1
            try {
              const projRes = await api.get(`/api/projects/${projectId.value}`)
              const proj = projRes?.data ?? projRes
              if (proj?.audit_year) year = Number(proj.audit_year)
            } catch { /* fallback */ }

            const tbRes = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
              params: { year },
            })
            const tbData = Array.isArray(tbRes?.data) ? tbRes.data : (Array.isArray(tbRes) ? tbRes : [])
            const tbRow = tbData.find((r: any) => r.standard_account_code === '1122')
            if (tbRow) {
              const tbAmount = Number(tbRow.audited_amount ?? tbRow.unadjusted_amount ?? 0)
              allResponses.value.set('D2-adj-tb-amount', {
                item_id: 'D2-adj-tb-amount',
                conclusion: null,
                remark: String(tbAmount),
              })
            }
          }
        } catch {
          // trial_balance 取数失败不阻断加载
        }
      }
    } catch {
      ElMessage.warning('数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  async function doSave(items: ChecklistItem[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    saving.value = true
    try {
      await Promise.all(items.map((item) => persistence.save(item.item_id, item)))
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
      throw err
    } finally {
      saving.value = false
    }
  }

  /** 立即保存指定 items（结论/状态/选择类字段触发） */
  async function saveImmediate(items: ChecklistItem[]): Promise<void> {
    await doSave(items)
  }

  /** debounce 2000ms 文本字段保存；Adapter 按 item 独立调度。 */
  function saveDebouncedText(item: ChecklistItem): void {
    persistence.saveDebounced(item.item_id, item)
  }

  /** flush 未保存数据（组件卸载或切换 sheet 时调用） */
  async function flushPendingSave(): Promise<void> {
    await persistence.flush()
  }

  /** 子 composable 通过 D2 注入批量保存。 */
  async function saveItemsFromEvent(items: ChecklistResponse[]): Promise<void> {
    const validItems = items.filter((item) => item?.item_id)
    if (!validItems.length) return
    await doSave(validItems)
  }

  /** 用 render-config snapshot 初始化 Adapter，保持历史响应格式兼容。 */
  function hydrate(source: unknown): void {
    persistence.hydrate(source)
  }

  // ─── Helper 方法 ─────────────────────────────────────────────────────────

  /** 获取单个字段 */
  function getField(itemId: string): ChecklistResponse | undefined {
    return allResponses.value.get(itemId)
  }

  /** 设置字段 + 立即保存（选择变更、签字操作） */
  function setFieldImmediate(itemId: string, data: Partial<Omit<ChecklistResponse, 'item_id'>>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    void saveImmediate([updated]).catch(() => undefined)
  }

  // ─── trial_balance 回写 ──────────────────────────────────────────────────

  /** 回写审定数到 trial_balance（科目 1122 应收账款） */
  async function writebackTrialBalance(accountCode: string, auditedAmount: number): Promise<void> {
    if (!projectId?.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: accountCode,
        audited_amount: auditedAmount,
      })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── 子底稿数据读取 ──────────────────────────────────────────────────────

  /** 读取 D2-2 audit-sheet 子底稿数据供 SUMIF 跨 sheet 引用 */
  async function loadSubWorkpaperData(subWpCode: string): Promise<Record<string, string | number>> {
    if (!projectId?.value) return {}
    try {
      const wpIndex = await getWpIndex(projectId.value)
      const subWp = wpIndex.find((w: any) => w.wp_code === subWpCode)
      if (!subWp) return {}

      const res = await api.get(`/api/workpapers/${subWp.id}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const result: Record<string, string | number> = {}
      for (const r of responses) {
        if (r.remark != null) result[r.item_id] = r.remark
        if (r.conclusion != null) result[r.item_id] = r.conclusion
      }
      return result
    } catch {
      ElMessage.warning(`子底稿 ${subWpCode} 数据加载失败`)
      return {}
    }
  }

  return {
    allResponses,
    loading,
    saving,
    loadAll,
    hydrate,
    saveImmediate,
    saveDebouncedText,
    saveItemsFromEvent,
    flushPendingSave,
    getField,
    setFieldImmediate,
    writebackTrialBalance,
    loadSubWorkpaperData,
    stateOf: persistence.stateOf,
    cancelPendingSave: persistence.cancel,
  }
}

export default useD2FormData
