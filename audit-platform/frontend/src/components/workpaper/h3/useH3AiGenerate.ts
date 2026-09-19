/**
 * useH3AiGenerate — H3 投资性房地产共享 AI 生成 helper
 *
 * 统一替代各子组件的 `window.dispatchEvent('ai:generate')` 死事件。
 * 调用通用 `/ai/generate-text` 端点（接受任意 section，不限白名单）。
 * 命中 H3_SECTION_MAP 的 section 走专属 H3 AI 端点以获取更精准结果。
 *
 * 返回 { generateH3AI, h3AiLoading }，子组件 import 后 @click="generateH3AI('H3-8')" 即可。
 */
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

const h3AiLoading = ref(false)

/**
 * H3 专属 section → 端点映射。
 * 命中映射时走 /api/workpapers/{wpId}/h3/ai-generate 获取更精准内容。
 * adj-note-cost/adj-note-fair/adj-conclusion 需 measurement_model 判断，暂不映射走通用。
 */
const H3_SECTION_MAP: Record<string, string> = {
  'H3-14': 'rental-analysis',
  'H3-6': 'transfer-analysis',
  'H3-8': 'fair-value-summary',
  'H3-10': 'impairment-conclusion',
  'H3-4-policy-evaluation': 'policy-evaluation',
}

/**
 * @param wpId 底稿 ID
 * @param section 自由 section 标识（如 H3-8、H3-14-contract、H3-4-policy-evaluation）
 * @param opts.existingContent 已有文本（可选）
 * @param opts.onFill 若提供，AI 生成文本回填该回调；否则弹 alert 展示
 */
export async function generateH3AI(
  wpId: string,
  section: string,
  opts?: { existingContent?: string; onFill?: (text: string) => void },
): Promise<void> {
  if (h3AiLoading.value) return
  h3AiLoading.value = true
  try {
    const mapped = H3_SECTION_MAP[section]
    let text = ''
    if (mapped) {
      // 走专属端点
      const res = await http.post(`/api/workpapers/${wpId}/h3/ai-generate`, {
        section: mapped,
        existingContent: opts?.existingContent || '',
        relatedContext: {},
        measurement_model: 'cost',
      })
      text = res.data?.data?.content ?? res.data?.content ?? ''
    } else {
      // 走通用 /ai/generate-text 路径
      const res = await http.post(`/api/workpapers/${wpId}/ai/generate-text`, {
        section,
        context: { wpCode: 'H3', sheet: `H3 投资性房地产`, section },
        existingContent: opts?.existingContent || '',
      })
      text = res.data?.data?.text ?? res.data?.text ?? ''
    }
    if (!text) {
      ElMessage.warning('AI 暂无建议')
      return
    }
    if (opts?.onFill) {
      opts.onFill(text)
      ElMessage.success('AI 已生成内容')
    } else {
      ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '关闭' }).catch(() => {})
    }
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    h3AiLoading.value = false
  }
}

export { h3AiLoading }
