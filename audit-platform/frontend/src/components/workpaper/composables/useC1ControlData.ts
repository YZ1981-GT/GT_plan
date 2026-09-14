/**
 * useC1ControlData — C1 企业层面控制测试 数据加载 / debounce保存 / 即时保存
 *
 * Spec: .kiro/specs/c1-entity-level-control/
 * Task: 3.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载所有 `C1-` 前缀数据
 * - 文本字段（测试结果说明 / 不适用理由 / 过程记录长文本）debounce 2s 保存
 * - 判断/枚举字段（是否适用 / 测试方法 / 结论 / 控制频率）变更立即保存
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses（http/axios 带 Authorization）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - readonly=true 时禁止任何保存
 * - 保存失败保留本地编辑内容并提示（Requirement 7.5）
 *
 * item_id 命名（前缀 C1-，详见 phase0-notes.md 第 6 节）：
 *   程序适用性  C1-{sec}-{step}-applicable  (conclusion=Y/N, remark=不适用理由)
 *   程序结果    C1-{sec}-{step}-result       (remark=说明文本)
 *   程序索引    C1-{sec}-{step}-index        (wp_ref=引用底稿编码)
 *   段结论      C1-{sec}-conclusion          (conclusion=有效/无效/部分有效)
 *   过程记录    C1-4-{k}-{field}
 *   样本单元    C1-4-4-sample-{row}-{col}
 *   整体结论    C1-overall-conclusion
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { canPersistApplicability } from './useC1SectionEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface C1Response {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

/** 可写字段子集（item_id 不可变） */
export type C1FieldPatch = Partial<Omit<C1Response, 'item_id'>>

export const C1_ITEM_PREFIX = 'C1-'

/** debounce 文本保存延迟（ms） */
const DEBOUNCE_MS = 2000

interface UseC1ControlDataOptions {
  /** 项目 id（用于 PUT body.project_id；不传则由后端从 wp_id 自动解析） */
  projectId?: Ref<string>
  /** 只读模式：为 true 时禁止所有保存 */
  readonly?: Ref<boolean>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useC1ControlData(wpId: Ref<string>, options: UseC1ControlDataOptions = {}) {
  const { projectId, readonly } = options

  /** 所有 C1- 响应，key = item_id */
  const responses = ref<Map<string, C1Response>>(new Map())
  const loading = ref(false)
  const saving = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const error = ref<string | null>(null)

  /** 待保存的 item_id 集合（增量批量，避免整表回写） */
  const pendingItemIds = new Set<string>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load ──────────────────────────────────────────────────────────────────

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    error.value = null
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, C1Response>()
      for (const r of list) {
        if (typeof r?.item_id === 'string' && r.item_id.startsWith(C1_ITEM_PREFIX)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
            wp_ref: r.wp_ref ?? null,
          })
        }
      }
      responses.value = map
    } catch (e: any) {
      error.value = e?.message || '数据加载失败'
      ElMessage.warning('C1 数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  // ─── 内部：写入本地 map（合并补丁） ────────────────────────────────────────

  function applyPatch(itemId: string, patch: C1FieldPatch): C1Response {
    const existing = responses.value.get(itemId) ?? {
      item_id: itemId,
      conclusion: null,
      remark: null,
      wp_ref: null,
    }
    const updated: C1Response = {
      item_id: itemId,
      conclusion: patch.conclusion !== undefined ? patch.conclusion : existing.conclusion,
      remark: patch.remark !== undefined ? patch.remark : existing.remark,
      wp_ref: patch.wp_ref !== undefined ? patch.wp_ref : existing.wp_ref,
    }
    responses.value.set(itemId, updated)
    return updated
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  function resolveProjectId(): string | undefined {
    // 优先 options.projectId；为空则从 URL /projects/:id 兜底；再空则交后端解析
    const pid = projectId?.value?.trim()
    if (pid) return pid
    try {
      const match = window.location.pathname.match(/\/projects\/([^/]+)/)
      return match?.[1] || undefined
    } catch {
      return undefined
    }
  }

  /** 保存当前 pending 集合中的所有 item（快照 + 失败回滚 pending） */
  async function flushToServer(): Promise<void> {
    if (readonly?.value) return
    if (!wpId.value) return
    if (pendingItemIds.size === 0) return

    const idsToSave = [...pendingItemIds]
    pendingItemIds.clear()

    const items = idsToSave.map((id) => {
      const r = responses.value.get(id)
      return {
        item_id: id,
        conclusion: r?.conclusion ?? null,
        remark: r?.remark ?? null,
        wp_ref: r?.wp_ref ?? null,
      }
    })

    saving.value = true
    try {
      const body: Record<string, any> = { items }
      const pid = resolveProjectId()
      if (pid) body.project_id = pid
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, body)
      lastSavedAt.value = new Date()
      error.value = null
    } catch (err: any) {
      const msg = err?.message || ''
      // axios 取消（重复请求）不算错误
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        error.value = msg || '保存失败'
        ElMessage.error('C1 保存失败，本地编辑已保留')
      }
      // 保留本地编辑：把 ids 放回 pending，下次编辑/flush 时再尝试（Requirement 7.5）
      for (const id of idsToSave) pendingItemIds.add(id)
    } finally {
      saving.value = false
    }
  }

  /** 立即保存：判断/枚举字段（是否适用 / 测试方法 / 结论 / 控制频率）变更触发 */
  function setFieldImmediate(itemId: string, patch: C1FieldPatch): void {
    if (readonly?.value) return
    applyPatch(itemId, patch)
    pendingItemIds.add(itemId)
    // 清除待触发的 debounce，立即连同 pending 文本一起 flush（避免文本编辑丢失）
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    void flushToServer()
  }

  /** debounce 2s 保存：文本字段（测试结果说明 / 不适用理由 / 过程记录长文本）触发 */
  function setFieldDebounced(itemId: string, patch: C1FieldPatch): void {
    if (readonly?.value) return
    applyPatch(itemId, patch)
    pendingItemIds.add(itemId)
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      void flushToServer()
    }, DEBOUNCE_MS)
  }

  // ─── 语义化便捷方法 ──────────────────────────────────────────────────────

  /**
   * 设置步骤/整段适用性（即时保存）。
   *
   * 铁律：标记「不适用」时必须填写理由，否则拒绝保存（Requirement 3.2）。
   * @param reason 不适用（applicable=false）时的理由，写入 remark
   * @returns 是否已发起保存（不适用但无理由时返回 false，未保存）
   */
  function setApplicable(itemId: string, applicable: boolean, reason?: string): boolean {
    if (readonly?.value) return false
    if (!canPersistApplicability(applicable, reason)) {
      // 不适用无理由 → 拒绝保存（调用方应先收集理由，如 ElMessageBox.prompt）
      return false
    }
    setFieldImmediate(itemId, {
      conclusion: applicable ? 'Y' : 'N',
      remark: applicable ? null : (reason as string).trim(),
    })
    return true
  }

  /** 设置结论类枚举（段结论 / 整体结论，即时保存） */
  function setConclusion(itemId: string, value: string | null): void {
    setFieldImmediate(itemId, { conclusion: value })
  }

  /** 设置长文本说明（debounce 2s，写入 remark） */
  function setText(itemId: string, text: string): void {
    setFieldDebounced(itemId, { remark: text })
  }

  /** 设置引用底稿编码（即时保存，写入 wp_ref，供 GtIndexChip 使用） */
  function setWpRef(itemId: string, wpRef: string | null): void {
    setFieldImmediate(itemId, { wp_ref: wpRef })
  }

  // ─── 读取 ────────────────────────────────────────────────────────────────

  function getField(itemId: string): C1Response {
    return (
      responses.value.get(itemId) ?? {
        item_id: itemId,
        conclusion: null,
        remark: null,
        wp_ref: null,
      }
    )
  }

  function getConclusion(itemId: string): string | null {
    return responses.value.get(itemId)?.conclusion ?? null
  }

  function getRemark(itemId: string): string | null {
    return responses.value.get(itemId)?.remark ?? null
  }

  function getWpRef(itemId: string): string | null {
    return responses.value.get(itemId)?.wp_ref ?? null
  }

  /** 是否适用（applicable item_id）：默认视为适用（true） */
  function isApplicable(itemId: string): boolean {
    return getConclusion(itemId) !== 'N'
  }

  // ─── flush（卸载 / 手动） ──────────────────────────────────────────────────

  function flushPendingSave(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingItemIds.size > 0) {
      void flushToServer()
    }
  }

  onScopeDispose(() => {
    flushPendingSave()
  })

  return {
    // State
    responses,
    loading,
    saving,
    lastSavedAt,
    error,

    // Load
    loadAll,

    // Save (generic)
    setFieldImmediate,
    setFieldDebounced,
    flushPendingSave,

    // Save (semantic)
    setApplicable,
    setConclusion,
    setText,
    setWpRef,

    // Read
    getField,
    getConclusion,
    getRemark,
    getWpRef,
    isApplicable,
  }
}

export default useC1ControlData
