/**
 * useSEstimateDisclosureEventBus — S 类计算型底稿 EventBus 联动 composable
 *
 * 共享逻辑，适用于 S3 / S15 / S20 / S21 四个计算型底稿。
 *
 * 职责：
 * 1. 保存后发布 WORKPAPER_SAVED 事件（Req 7.3）
 * 2. 披露文本区文本更新时发布 disclosure:note-text-updated（Req 8.2）
 * 3. 订阅 substantive:adjudicated 事件刷新披露引用数据（Req 8.3）
 * 4. AI 辅助生成披露文本（Req 8.1）
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 5.2
 * Requirements: 7.3, 8.1, 8.2, 8.3
 */
import { ref, onMounted, onBeforeUnmount, type Ref } from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 防抖去重间隔（毫秒） */
const DEDUP_MS = 2000

/** S 类底稿 wpCode → accountCode 映射（用于事件 payload） */
export const S_ESTIMATE_ACCOUNT_CODES: Record<string, string> = {
  S15: '6901', // 每股收益（非标准科目，仅标记用）
  S20: '6001', // 营业收入
  S3: '6801',  // 会计政策变更
  S21: '1701', // 无形资产（数据资产）
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SEstimateDisclosureOptions {
  /** 底稿 wpCode（S3 / S15 / S20 / S21） */
  wpCode: string
  /** 底稿 wp_id */
  wpId: string | Ref<string>
  /** 项目 ID */
  projectId: string | Ref<string>
  /** 刷新回调 — substantive:adjudicated 触发时调用 */
  onRefresh?: () => void | Promise<void>
  /** 是否只读 */
  isReadonly?: Ref<boolean>
}

export interface DisclosureTextState {
  /** 披露文本 */
  text: Ref<string>
  /** AI 生成中 */
  aiLoading: Ref<boolean>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useSEstimateDisclosureEventBus(options: SEstimateDisclosureOptions) {
  const { wpCode, wpId, projectId, onRefresh, isReadonly } = options

  // ── Disclosure text state ──────────────────────────────────────────────────

  const disclosureText = ref('')
  const aiLoading = ref(false)

  // ── Dedup state ────────────────────────────────────────────────────────────

  let lastSavedKey = ''
  let lastSavedAt = 0
  let lastDisclosureKey = ''
  let lastDisclosureAt = 0
  let disclosureTimer: ReturnType<typeof setTimeout> | null = null

  // ── Helpers ────────────────────────────────────────────────────────────────

  function getWpId(): string {
    return typeof wpId === 'string' ? wpId : wpId.value
  }

  function getProjectId(): string {
    return typeof projectId === 'string' ? projectId : projectId.value
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 1. WORKPAPER_SAVED — 保存后发布（Req 7.3）
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * 调用后端保存端点后，发布 WORKPAPER_SAVED 前端事件。
   * 后端 wp_html_save 统一发布后端 EventBus WORKPAPER_SAVED，
   * 前端此处发布 eventBus 用于组件间联动（如一致性检查 UI 刷新）。
   */
  async function publishWorkpaperSaved(extra?: Record<string, unknown>): Promise<void> {
    const key = JSON.stringify({ wpCode, ...extra })
    const now = Date.now()
    if (key === lastSavedKey && now - lastSavedAt < DEDUP_MS) return
    lastSavedKey = key
    lastSavedAt = now

    try {
      eventBus.emit('substantive:adjudicated', {
        wpCode,
        accountCode: S_ESTIMATE_ACCOUNT_CODES[wpCode] || '',
        auditedAmount: (extra?.auditedAmount as number) ?? 0,
        timestamp: now,
      })
    } catch { /* silent */ }
  }

  /**
   * 保存底稿数据到后端并发布事件。
   * 调用方通常是审定表保存按钮。
   */
  async function saveAndPublish(savePayload?: Record<string, unknown>): Promise<boolean> {
    const id = getWpId()
    try {
      await http.post(`/api/workpapers/${id}/save`, savePayload || {})
      await publishWorkpaperSaved(savePayload)
      return true
    } catch (err) {
      console.warn(`[useSEstimateDisclosureEventBus] save failed (${wpCode}):`, err)
      return false
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 2. disclosure:note-text-updated — 披露文本发布（Req 8.2）
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * 发布 disclosure:note-text-updated 事件。
   * 带防抖去重，避免频繁 emit。
   */
  function publishDisclosureNoteUpdated(section?: string, text?: string): void {
    if (disclosureTimer) clearTimeout(disclosureTimer)
    disclosureTimer = setTimeout(() => {
      disclosureTimer = null
      const detail = {
        wpCode,
        section: section || 'disclosure',
        text: text ?? disclosureText.value,
        timestamp: Date.now(),
      }
      const key = JSON.stringify(detail)
      const now = Date.now()
      if (key === lastDisclosureKey && now - lastDisclosureAt < DEDUP_MS) return
      lastDisclosureKey = key
      lastDisclosureAt = now

      try {
        window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', { detail }))
      } catch { /* silent */ }
    }, DEDUP_MS)
  }

  /**
   * 披露文本变更处理器 — 绑定到 textarea @input 或 watch。
   */
  function onDisclosureTextChange(newText: string, section?: string): void {
    disclosureText.value = newText
    publishDisclosureNoteUpdated(section, newText)
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 3. substantive:adjudicated — 订阅刷新（Req 8.3）
  // ══════════════════════════════════════════════════════════════════════════

  function onSubstantiveAdjudicated(payload: any): void {
    // 仅在本底稿相关科目变化时刷新
    const accountCode = S_ESTIMATE_ACCOUNT_CODES[wpCode]
    if (payload?.accountCode && payload.accountCode !== accountCode) {
      // 不同科目 → 跳过（但如果是全局刷新，无 accountCode 则也处理）
      return
    }
    onRefresh?.()
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 4. AI 辅助生成披露文本（Req 8.1）
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * 调用后端 AI 端点生成披露文本。
   * 使用现有 /api/workpapers/{wp_id}/ai/generate 端点模式。
   */
  async function generateDisclosureWithAi(section?: string, context?: Record<string, unknown>): Promise<string | null> {
    if (isReadonly?.value) return null
    const id = getWpId()
    aiLoading.value = true
    try {
      const resp = await http.post(`/api/workpapers/${id}/ai/generate`, {
        section: section || 'disclosure',
        wp_code: wpCode,
        context: context || {},
      })
      const generated = (resp as any)?.data?.text || (resp as any)?.text || ''
      if (generated) {
        disclosureText.value = generated
        publishDisclosureNoteUpdated(section, generated)
      }
      return generated
    } catch (err) {
      console.warn(`[useSEstimateDisclosureEventBus] AI generate failed (${wpCode}):`, err)
      return null
    } finally {
      aiLoading.value = false
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Lifecycle — 订阅/取消订阅
  // ══════════════════════════════════════════════════════════════════════════

  function subscribe(): void {
    eventBus.on('substantive:adjudicated', onSubstantiveAdjudicated)
  }

  function unsubscribe(): void {
    eventBus.off('substantive:adjudicated', onSubstantiveAdjudicated)
    if (disclosureTimer) {
      clearTimeout(disclosureTimer)
      disclosureTimer = null
    }
  }

  onMounted(() => {
    subscribe()
  })

  onBeforeUnmount(() => {
    unsubscribe()
  })

  // ── Return ─────────────────────────────────────────────────────────────────

  return {
    // State
    disclosureText,
    aiLoading,

    // Actions
    saveAndPublish,
    publishWorkpaperSaved,
    publishDisclosureNoteUpdated,
    onDisclosureTextChange,
    generateDisclosureWithAi,

    // Lifecycle (manual control, if needed outside setup)
    subscribe,
    unsubscribe,
  }
}
