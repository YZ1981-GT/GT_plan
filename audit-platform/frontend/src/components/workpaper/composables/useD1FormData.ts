/**
 * useD1FormData — D1 应收票据数据加载/debounce保存/即时保存/辅助
 *
 * Spec: .kiro/specs/d1-notes-receivable/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 D1-* 数据
 * - debounce 2s 文本字段保存 / 结论/状态/选择类字段立即保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses
 * - trial_balance 回写：writebackTrialBalance
 * - 子底稿数据读取：loadSubWorkpaperData（D1-2/D1-3）
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { getWpIndex } from '@/services/workpaperApi'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export type ChecklistResponse = ChecklistItem

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1FormData(wpId: Ref<string>, projectId?: Ref<string>) {
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const loading = ref(false)
  const saving = ref(false)

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSave = false

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('D1-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
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
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: wpId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    } finally {
      saving.value = false
    }
  }

  /** 立即保存指定 items（结论/状态/选择类字段触发） */
  async function saveImmediate(items: ChecklistItem[]): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    await doSave(items)
  }

  /** debounce 2000ms 文本字段保存 */
  function saveDebouncedText(item: ChecklistItem): void {
    allResponses.value.set(item.item_id, { ...item })
    pendingSave = true

    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      pendingSave = false
      const items = Array.from(allResponses.value.values())
      doSave(items)
    }, 2000)
  }

  /** flush 未保存数据（组件卸载时调用） */
  function flushPendingSave(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingSave) {
      pendingSave = false
      const items = Array.from(allResponses.value.values())
      doSave(items)
    }
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
    saveImmediate([updated])
  }

  // ─── trial_balance 回写 ──────────────────────────────────────────────────

  /** 回写审定数到 trial_balance */
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

  /** 读取 D1-2/D1-3 audit-sheet 子底稿数据供跨 sheet 引用 */
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

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    flushPendingSave()
  })

  return {
    allResponses,
    loading,
    saving,
    loadAll,
    saveImmediate,
    saveDebouncedText,
    flushPendingSave,
    getField,
    setFieldImmediate,
    writebackTrialBalance,
    loadSubWorkpaperData,
  }
}

export default useD1FormData
