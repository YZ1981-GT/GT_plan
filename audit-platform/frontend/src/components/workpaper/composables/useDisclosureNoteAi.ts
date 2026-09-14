/**
 * 披露说明文本域的 AI 辅助 + 复核入口（各循环共用）
 *
 * 抽自 D1 已验证实现（`d1/D1TabDisclosure.vue`），消除四份复制。
 *
 * 🔴 端点契约（曾长期写错导致 7 个按钮空转）：
 * `POST /api/workpapers/{wpId}/review-dialog/ai-generate`
 * 请求体 `{ section_id, related_data, existing_content }`、响应 `generated_text`。
 * 写成 `{ section, context }` / 读 `.text` 会 422 并被 catch 吞成「AI生成失败」。
 *
 * 🔴 `section_id` 必须同时在后端 `review_dialog._SECTION_PROMPTS` 登记，
 * 否则回退通用 prompt（过短 → 诱导模型自造披露内容）。
 * 守卫 `backend/tests/test_review_dialog_section_prompts.py` 从前端源码抽 section_id 校验。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export interface DisclosureNoteAiOptions {
  /** working_paper.id（route wpId） */
  wpId: Ref<string | undefined> | (() => string | undefined)
  /** 只读态判定（只读时 AI 不写入） */
  isReadonly: () => boolean
  /** 文本域当前值 */
  getText: (key: string) => string
  /** AI 生成后回写（走各循环自己的持久化路径） */
  setText: (key: string, text: string) => void
  /** `section_id` 构造（务必与后端 `_SECTION_PROMPTS` 的键一致） */
  buildSectionId: (key: string) => string
  /** 复核弹窗 sectionId（缺省复用 `buildSectionId`） */
  buildReviewId?: (key: string) => string
  /** 交给 AI 的业务上下文（表格数据摘要），缺省不传 */
  buildContext?: (key: string) => unknown
  /** 子节中文名（复核弹窗标题用） */
  labelOf?: (key: string) => string
  /** 复核弹窗注入函数（`inject('openReviewDialog', null)` 的结果） */
  openReviewDialog?: ((payload: Record<string, unknown>) => void) | null
}

export function useDisclosureNoteAi(opts: DisclosureNoteAiOptions) {
  /** 正在生成的子节键（''=空闲），供按钮 `:loading` 绑定 */
  const aiLoadingSection = ref('')

  const resolveWpId = (): string =>
    String((typeof opts.wpId === 'function' ? opts.wpId() : opts.wpId?.value) ?? '')

  async function runAi(key: string): Promise<void> {
    if (opts.isReadonly()) return
    const wpId = resolveWpId()
    if (!wpId) {
      ElMessage.warning('底稿未就绪，请稍后重试')
      return
    }
    aiLoadingSection.value = key
    try {
      const res: any = await http.post(`/api/workpapers/${wpId}/review-dialog/ai-generate`, {
        section_id: opts.buildSectionId(key),
        // 字段名用 `section_key` 而非 `section`：请求体顶层的 `section` 是历史错误字段
        // （会让后端 422），守卫按「源码中不得出现 `section:`」严格拦，避免再写错
        related_data: {
          section_key: key,
          ...(opts.buildContext ? { context: opts.buildContext(key) } : {}),
        },
        existing_content: opts.getText(key) || '',
      })
      const payload = res?.data ?? res
      const text = payload?.generated_text ?? payload?.data?.generated_text ?? ''
      if (!text) {
        ElMessage.warning('AI未返回内容，请重试')
        return
      }
      opts.setText(key, String(text))
      ElMessage.success('AI已生成说明')
    } catch {
      ElMessage.warning('AI生成失败，请重试')
    } finally {
      aiLoadingSection.value = ''
    }
  }

  function openReview(key: string): void {
    const open = opts.openReviewDialog
    if (!open) return
    open({
      sectionId: (opts.buildReviewId ?? opts.buildSectionId)(key),
      sectionLabel: opts.labelOf?.(key) ?? key,
      relatedData: { note: opts.getText(key) || '' },
    })
  }

  return { aiLoadingSection, runAi, openReview }
}

export default useDisclosureNoteAi
