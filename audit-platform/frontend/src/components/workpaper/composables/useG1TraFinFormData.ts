import { ref, onScopeDispose, type Ref } from 'vue'
import { registerPendingFlusher, trackPendingWrite } from '../sync/pendingWrites'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'
import { useWorkpaperAuditYear } from './workpaperAuditYear'

export function useG1TraFinFormData(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('G1-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('G1数据加载失败，可手动填写')
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([
        loadResponses(),
        (async () => {
          const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
            params: { force_component_type: 'g1-trading-financial-assets' },
            _silent: true,
          } as any)
          const data = res?.data ?? res
          const sheets = data?.sheets ?? data?.data?.sheets ?? []
          for (const s of sheets) {
            sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
          }
          // 合并 responses_snapshot（bundle内嵌场景防御性处理）
          const snapshot = data?.html_data?.responses_snapshot ?? data?.responses_snapshot
          if (snapshot && typeof snapshot === 'object' && !Array.isArray(snapshot)) {
            for (const [k, v] of Object.entries(snapshot)) {
              if (!k.startsWith('G1-')) continue
              if (!allResponses.value.has(k)) {
                const val = v as any
                allResponses.value.set(k, {
                  item_id: k,
                  conclusion: val?.conclusion ?? null,
                  remark: val?.remark ?? null,
                })
              }
            }
          }
        })(),
      ])
    } finally {
      isLoading.value = false
    }
  }

  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
      project_id: opts.projectId.value,
      items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
    })
    opts.onAfterSave?.()
  }

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(
      itemId,
      setTimeout(() => {
        _debounceTimers.delete(itemId)
        void trackPendingWrite(saveImmediate(itemId, updated)).catch((err: unknown) => {
        // 这家没有重试、没有本地草稿：静默就等于编辑丢了且用户不知道。
        // 屏障仍从 trackPendingWrite 得到失败，这里只负责让用户看见。
        ElMessage.error('保存失败，请检查网络后重试')
        console.error('[G1] 底稿保存未落库', err)
      })
      }, 2000),
    )
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  // spec: tb-writeback-explicit-publish-gate Task 12：原 writebackTrialBalance（旧端点
  // PUT trial-balance/writeback，经宿主 handleG1Writeback 触发）为零消费死代码——TB 回写
  // 已改由 G1-1 审定表「发布到试算表」显式确认门（G1TabAdjudication.handlePublishToTb →
  // POST publish-to-tb，科目1501余额口径）承载，故移除此重复定义及其 return export。

  /** 切表/卸载前刷出未到点的 debounce，避免 <2s 编辑丢失 */
  async function flushPending(): Promise<void> {
    const inFlight: Array<Promise<void>> = []
    for (const [itemId, timer] of _debounceTimers.entries()) {
      clearTimeout(timer)
      const resp = allResponses.value.get(itemId)
      if (resp) inFlight.push(saveImmediate(itemId, resp))
    }
    _debounceTimers.clear()
    // 必须 await：fire-and-forget 会让 flushHtml 读到未落库的旧投影
    await Promise.all(inFlight)
  }

  registerPendingFlusher(flushPending)

  onScopeDispose(() => {
    void flushPending().catch((err: unknown) => {
      // 卸载时没有 UI 可提示：至少留下可排查的痕迹，不能让失败的保存彻底无痕消失。
      console.error('[G1] 卸载时仍有未落库的底稿保存', err)
    })
  })

  return {
    isLoading,
    sheetCache,
    allResponses,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPending,
  }
}
