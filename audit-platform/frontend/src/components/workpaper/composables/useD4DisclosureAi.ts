/**
 * useD4DisclosureAi — D4 营业收入 8 个披露文本域 AI 辅助生成
 *
 * 走平台标准 `wpAiText` 共享件（`POST /api/workpapers/{wpId}/ai/generate-text`）。
 * 🔴 `context` 必须是 `Record<string, string>`（踩坑铁律：传字符串→422 被 catch 静默吞）。
 *
 * 四处齐备：
 *   ① 后端 `_d4_ai_generate._SUPPORTED_SECTIONS`（8 条）
 *   ② 后端 `_d4_ai_generate._SECTION_PROMPTS`（每条 ≥20 字含「不得虚构」）
 *   ③ 前端联合类型 `D4DisclosureAiSection`（本文件）
 *   ④ 前端 `D4_AI_TARGETS`（Listed 8 / Soe 7，两版 Tab 引用）
 */
import { ref, type Ref } from 'vue'
import { generateWpText } from './shared/wpAiText'

// ── ③ 前端联合类型 ─────────────────────────────────────────────────────────────
export type D4DisclosureAiSection =
  | 'd4-disc-note-1'
  | 'd4-disc-note-2'
  | 'd4-disc-note-3'
  | 'd4-disc-note-4'
  | 'd4-disc-note-5'
  | 'd4-disc-note-6'
  | 'd4-disc-note-7'
  | 'd4-disc-note-8'

// ── ④ AI_TARGETS ────────────────────────────────────────────────────────────────
/** 上市版 8 个文本域（note-1 到 note-8） */
export const D4_LISTED_AI_TARGETS: readonly D4DisclosureAiSection[] = [
  'd4-disc-note-1',
  'd4-disc-note-2',
  'd4-disc-note-3',
  'd4-disc-note-4',
  'd4-disc-note-5',
  'd4-disc-note-6',
  'd4-disc-note-7',
  'd4-disc-note-8',
] as const

/** 国企版 7 个文本域（note-1 到 note-7，无试运行销售收入） */
export const D4_SOE_AI_TARGETS: readonly D4DisclosureAiSection[] = [
  'd4-disc-note-1',
  'd4-disc-note-2',
  'd4-disc-note-3',
  'd4-disc-note-4',
  'd4-disc-note-5',
  'd4-disc-note-6',
  'd4-disc-note-7',
] as const

/** noteKey (note-1..note-8) → section id 映射 */
export function noteKeyToSection(noteKey: string): D4DisclosureAiSection {
  return `d4-disc-${noteKey}` as D4DisclosureAiSection
}

export interface UseD4DisclosureAiOptions {
  wpId: Ref<string>
  variant: 'listed' | 'soe'
  /** 当前文本值获取 */
  getNoteText: (noteKey: string) => string
  /** 写回文本 */
  setNoteText: (noteKey: string, value: string) => void
}

/**
 * D4 披露文本域 AI 辅助 composable。
 *
 * 用法（在 Tab setup 顶层调用）：
 * ```ts
 * const { aiLoading, aiGenerate } = useD4DisclosureAi({
 *   wpId: computed(() => props.wpId),
 *   variant: 'listed',
 *   getNoteText: (k) => noteTexts.value[k] || '',
 *   setNoteText: (k, v) => updateNote(k, v),
 * })
 * ```
 */
export function useD4DisclosureAi(opts: UseD4DisclosureAiOptions) {
  const aiLoading = ref(false)

  async function aiGenerate(noteKey: string) {
    if (aiLoading.value) return
    aiLoading.value = true
    try {
      const section = noteKeyToSection(noteKey)
      // 🔴 context 必须是 dict[str,str]（值全字符串），否则 422
      const context: Record<string, string> = {
        variant: opts.variant,
        noteKey,
      }
      const text = await generateWpText({
        wpId: opts.wpId.value,
        section,
        prompt: '', // 后端按 section 兜底专属 prompt
        context,
        existingContent: opts.getNoteText(noteKey),
      })
      if (text) {
        opts.setNoteText(noteKey, text)
      }
    } finally {
      aiLoading.value = false
    }
  }

  return { aiLoading, aiGenerate }
}

export default useD4DisclosureAi
