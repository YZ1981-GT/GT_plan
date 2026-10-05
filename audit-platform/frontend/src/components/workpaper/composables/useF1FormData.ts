/**
 * useF1FormData — F1 预付账款数据加载/debounce保存/即时保存/批量保存
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Task: 3.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 F1-* 数据
 * - debounce 2s 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 切换前严格等待保存；组件卸载时非阻塞 flush（onScopeDispose）
 * - TB 回写由审定表显式发布门承载，本数据层不写 trial_balance
 * - selfLoad逻辑（render-config?force_component_type=f1-prepayment）
 * - 关联方清单加载：loadRelatedParties
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseF1FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1FormData(options: UseF1FormDataOptions) {
  const { wpId, projectId } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  // 只有当前版本真正落库后才清 pending；旧请求完成不得确认较新的编辑。
  const _pendingItems = new Set<string>()
  const _itemVersions = new Map<string, number>()
  const _queuedVersions = new Map<string, number>()
  const _saveFailures = new Map<string, unknown>()
  // 即时、批量、debounce 共用串行队列，防止旧请求后到覆盖新值。
  let _saveTail: Promise<void> = Promise.resolve()

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('F1-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('F1数据加载失败，可手动填写')
    }
  }

  /** selfLoad: 当组件在bundle内嵌时无htmlData，自行加载render-config */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      await api.get(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=f1-prepayment`,
        { _silent: true } as any,
      )
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  /** 统一加载入口 */
  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), selfLoad()])
    } finally {
      isLoading.value = false
    }
  }

  /** 从项目关联方清单加载关联方名单 */
  async function loadRelatedParties(): Promise<string[]> {
    if (!projectId.value) return []
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/related-parties`,
        { _silent: true } as any,
      )
      const parties: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      return parties.map((p: any) => (typeof p === 'string' ? p : p.name || p.party_name || '')).filter(Boolean)
    } catch {
      return []
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  async function _doSave(items: ChecklistResponse[], targetWpId: string, targetProjectId: string): Promise<void> {
    try {
      if (!targetWpId) throw new Error('底稿编号缺失，F1 数据尚未保存')
      await api.put(`/api/workpapers/${targetWpId}/checklist-responses`, {
        project_id: targetProjectId,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，编辑已保留，请重试')
      }
      throw err
    }
  }

  /** 调用时冻结值和版本；所有写入方共用队列，失败不清 pending。 */
  function _queuePending(itemIds: Iterable<string>): Promise<void> {
    const entries = [...new Set(itemIds)].flatMap((itemId) => {
      const version = _itemVersions.get(itemId)
      const response = allResponses.value.get(itemId)
      if (!response || version === undefined || _queuedVersions.get(itemId) === version) return []
      _queuedVersions.set(itemId, version)
      return [{ itemId, version, response: { ...response } }]
    })
    if (entries.length === 0) return _saveTail
    const targetWpId = wpId.value
    const targetProjectId = projectId.value
    const request = _saveTail.then(async () => {
      try {
        await _doSave(entries.map((entry) => entry.response), targetWpId, targetProjectId)
        for (const { itemId, version } of entries) {
          if (_itemVersions.get(itemId) === version) {
            _pendingItems.delete(itemId)
            _saveFailures.delete(itemId)
          }
        }
      } catch (error) {
        for (const { itemId, version } of entries) {
          if (_itemVersions.get(itemId) === version) _saveFailures.set(itemId, error)
        }
        throw error
      } finally {
        for (const { itemId, version } of entries) {
          if (_queuedVersions.get(itemId) === version) _queuedVersions.delete(itemId)
        }
      }
    })
    // 队列自身始终可继续；strict flush 从失败清册拒绝，不把后台拒绝留作 unhandled。
    _saveTail = request.catch(() => undefined)
    return request
  }

  function _stageItem(itemId: string, data: Partial<ChecklistResponse>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    allResponses.value.set(itemId, {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    })
    _itemVersions.set(itemId, (_itemVersions.get(itemId) ?? 0) + 1)
    _pendingItems.add(itemId)
    _saveFailures.delete(itemId)
  }

  function _cancelDebounce(itemId: string): void {
    const timer = _debounceTimers.get(itemId)
    if (timer !== undefined) clearTimeout(timer)
    _debounceTimers.delete(itemId)
  }

  /** 保留既有 Promise<void> 非抛错契约（有 void 调用方）；严格失败交由 flush 报告。 */
  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>): Promise<void> {
    _cancelDebounce(itemId)
    _stageItem(itemId, data)
    await _queuePending([itemId]).catch(() => undefined)
  }

  /** 批量保存多个 items */
  async function saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>): Promise<void> {
    // 🔴 同一批次不得重复提交相同 item_id：后端会**整批拒绝** → 该批全部数据丢失
    //    （联动回写常见：先写整表 JSON、再写其中某个汇总字段）。
    //    同 itemId 多次传入时后写覆盖先写，与「用户最后一次输入」语义一致。
    const deduped = [...new Map(items.map((it) => [it.itemId, it])).values()]
    for (const { itemId, data } of deduped) {
      _cancelDebounce(itemId)
      _stageItem(itemId, data)
    }
    await _queuePending(deduped.map((item) => item.itemId)).catch(() => undefined)
  }

  /** debounce 2s 文本字段保存（per item_id 独立计时器） */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    _cancelDebounce(itemId)
    _stageItem(itemId, data)
    const timer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      void _queuePending([itemId]).catch(() => undefined)
    }, 2000)
    _debounceTimers.set(itemId, timer)
  }

  // ─── trial_balance 回写：已移除 writebackTrialBalance（spec tb-writeback-explicit-publish-gate Task 3） ──
  // 原 writebackTrialBalance(1123) 直调旧端点 PUT /projects/{pid}/trial-balance/writeback，
  // 绕过显式确认门。改造后 TB 回写走显式发布门（F1TabAdjudication.publishToTb → publish-to-tb）。
  // 唯一消费方 GtF1Prepayment.handleF1Writeback 已随监听器移除 ⇒ 此函数为零消费死代码。

  // ─── Flush（组件卸载） ───────────────────────────────────────────────────

  /** 等待全部在途写入及等待期间的新编辑；任一当前版本失败则拒绝切到 OO。 */
  async function _flushPending(): Promise<void> {
    do {
      for (const timer of _debounceTimers.values()) clearTimeout(timer)
      _debounceTimers.clear()
      // flush 开始前的失败可重试；本次新失败不无限重试、不谎报成功。
      await _queuePending(_pendingItems).catch(() => undefined)
      let tail: Promise<void>
      do {
        tail = _saveTail
        await tail
      } while (tail !== _saveTail)
      for (const itemId of _pendingItems) {
        if (_saveFailures.has(itemId)) throw _saveFailures.get(itemId)
      }
    } while (_pendingItems.size > 0)
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    // 卸载钩子不能 await；失败已留痕并保留编辑，不能制造后台 unhandled rejection。
    void _flushPending().catch(() => undefined)
  })

  return {
    allResponses,
    isLoading,
    loadAll,
    loadRelatedParties,
    saveImmediate,
    saveBatch,
    debouncedSave,
    // syncBridge 须 await：等所有保存落库才允许读投影；失败保留 pending 并拒绝切 OO。
    flushPendingSave: _flushPending,
  }
}

export default useF1FormData
