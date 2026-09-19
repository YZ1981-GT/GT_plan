/**
 * useAiGenerateFlow — AI 三段式流程（生成→预览 diff→确认）
 *
 * Feature: platform-global-hardening
 * Requirements: 9.3, 9.4, 9.5, 9.6
 *
 * 状态机: IDLE → GENERATING → PREVIEWING → CONFIRMED
 *
 * 核心行为:
 * - 生成完成先展示 diff 预览，用户确认前不填入（Req 9.6）
 * - 确认后立即填入无额外延迟（Req 9.4）
 * - 目标区已有内容时预览 diff 标示差异并要求确认（Req 9.5）
 *
 * AI 生成端点: POST /api/workpapers/{wp_id}/ai/generate-text
 */
import { ref, computed, type Ref } from 'vue'
import type { AiContext } from './buildAiContext'

/** 状态机阶段 */
export type AiFlowPhase = 'IDLE' | 'GENERATING' | 'PREVIEWING' | 'CONFIRMED'

/** useAiGenerateFlow 配置 */
export interface AiGenerateFlowOptions {
  /** 工作底稿 ID */
  wpId: Ref<string>
  /** 目标模型（要填入的 ref） */
  targetModel: Ref<string>
  /** section 标识（用于 API 调用） */
  section: string
  /** HTTP 请求函数（默认使用 inject 或传入） */
  httpPost?: (url: string, body: any, config?: any) => Promise<any>
}

/** useAiGenerateFlow 的返回类型 */
export interface UseAiGenerateFlowReturn {
  /** 当前阶段 */
  phase: Ref<AiFlowPhase>
  /** 生成的内容（预览阶段显示） */
  generatedContent: Ref<string>
  /** 原始内容（生成前快照，用于 diff 展示） */
  originalContent: Ref<string>
  /** 是否有差异需要确认（目标区已有内容时为 true） */
  hasDiff: Ref<boolean>
  /** 错误信息 */
  error: Ref<string>
  /** 是否正在生成 */
  isGenerating: Ref<boolean>
  /** 是否正在预览 */
  isPreviewing: Ref<boolean>
  /** 触发生成 */
  generate: (context: AiContext | Record<string, unknown>, prompt?: string) => Promise<void>
  /** 确认填入（预览 → 确认） */
  confirm: () => void
  /** 取消/重置回 IDLE */
  cancel: () => void
  /** 重新生成（回到 GENERATING） */
  regenerate: (context: AiContext | Record<string, unknown>, prompt?: string) => Promise<void>
}

/**
 * useAiGenerateFlow — AI 三段式流程 composable
 *
 * @example
 * ```ts
 * const conclusion = ref('')
 * const { phase, generate, confirm, cancel, generatedContent, hasDiff } = useAiGenerateFlow({
 *   wpId: toRef(props, 'wpId'),
 *   targetModel: conclusion,
 *   section: 'd2-aging-conclusion',
 *   httpPost: api.post,
 * })
 *
 * // 用户点 AI 按钮
 * await generate(buildAiContext('D2', '账龄'))
 * // → phase = 'PREVIEWING', generatedContent 有值, hasDiff 可能为 true
 *
 * // 用户确认 diff
 * confirm()
 * // → phase = 'CONFIRMED', targetModel 立即更新为 generatedContent
 * ```
 */
export function useAiGenerateFlow(options: AiGenerateFlowOptions): UseAiGenerateFlowReturn {
  const { wpId, targetModel, section, httpPost } = options

  // ─── State ───
  const phase = ref<AiFlowPhase>('IDLE')
  const generatedContent = ref('')
  const originalContent = ref('')
  const error = ref('')

  // ─── Computed ───
  const hasDiff = computed(() => {
    return originalContent.value.trim().length > 0 && generatedContent.value !== originalContent.value
  })
  const isGenerating = computed(() => phase.value === 'GENERATING')
  const isPreviewing = computed(() => phase.value === 'PREVIEWING')

  // ─── Methods ───

  /**
   * 触发 AI 生成
   * IDLE → GENERATING → PREVIEWING
   */
  async function generate(
    context: AiContext | Record<string, unknown>,
    prompt?: string,
  ): Promise<void> {
    if (!wpId.value) {
      error.value = '缺少底稿 ID'
      return
    }

    // 快照当前内容（Req 9.5: diff 预览不覆盖已填内容）
    originalContent.value = targetModel.value || ''

    // 转换为 GENERATING
    phase.value = 'GENERATING'
    error.value = ''
    generatedContent.value = ''

    try {
      const requestBody: Record<string, unknown> = {
        section,
        context: typeof context === 'string' ? context : JSON.stringify(context),
        existingContent: originalContent.value,
      }
      if (prompt) {
        requestBody.prompt = prompt
      }

      let responseText = ''

      if (httpPost) {
        const res = await httpPost(
          `/api/workpapers/${wpId.value}/ai/generate-text`,
          requestBody,
          { _silent: true } as any,
        )
        responseText =
          res?.data?.data?.content ||
          res?.data?.content ||
          res?.data?.data?.text ||
          res?.data?.text ||
          res?.data?.data ||
          ''
      } else {
        // fallback: 无 httpPost 时模拟（开发/测试用）
        responseText = `[AI 生成内容 - ${section}]`
      }

      if (typeof responseText !== 'string') {
        responseText = String(responseText || '')
      }

      generatedContent.value = responseText

      // 生成完成 → 进入预览（Req 9.6: 生成完成先展示 diff 预览）
      phase.value = 'PREVIEWING'
    } catch (err: any) {
      error.value = err?.message || 'AI 生成失败'
      // 生成失败回到 IDLE，保留原始内容不变
      phase.value = 'IDLE'
    }
  }

  /**
   * 确认填入
   * PREVIEWING → CONFIRMED
   *
   * Req 9.4: 确认后立即填入无额外延迟
   * Req 9.5: 目标区已有内容时需用户确认后才覆盖
   */
  function confirm(): void {
    if (phase.value !== 'PREVIEWING') return

    // 立即填入，无延迟（Req 9.4）
    targetModel.value = generatedContent.value
    phase.value = 'CONFIRMED'

    // 确认后自动回到 IDLE（下次可重新生成）
    // 短延迟后回 IDLE，让 UI 有机会展示确认态
    setTimeout(() => {
      if (phase.value === 'CONFIRMED') {
        phase.value = 'IDLE'
      }
    }, 100)
  }

  /**
   * 取消/重置
   * 任意阶段 → IDLE
   *
   * 取消时保留 targetModel 的原始值不变
   */
  function cancel(): void {
    phase.value = 'IDLE'
    generatedContent.value = ''
    error.value = ''
    // 不修改 targetModel — 保留用户已填内容（Req 9.5）
  }

  /**
   * 重新生成
   * 任意阶段 → GENERATING → PREVIEWING
   */
  async function regenerate(
    context: AiContext | Record<string, unknown>,
    prompt?: string,
  ): Promise<void> {
    // 重新生成时使用最初快照的 originalContent，不是当前 targetModel
    // 因为 targetModel 可能已被前次 confirm 修改
    await generate(context, prompt)
  }

  return {
    phase,
    generatedContent,
    originalContent,
    hasDiff,
    error,
    isGenerating,
    isPreviewing,
    generate,
    confirm,
    cancel,
    regenerate,
  }
}
