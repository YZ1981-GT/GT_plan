/**
 * useK8AiGenerate — K8 销售费用 AI 辅助生成（统一端点 /ai/generate-text）
 *
 * 修复 K8 复盘发现的「AI 按钮大面积死」问题：
 * - K8-4/K8-5/附注上市国企 原本只是 `ElMessage.info(...)` 占位；
 * - K8-1/K8-2/K8-8 emit `K8-x-ai-trigger` 但入口只存 checklist、无 AI 调用。
 *
 * 本 composable 调平台统一端点 `POST /api/workpapers/{wpId}/ai/generate-text`
 * （wp_guidance_chat.py，接收 {prompt, context:dict[str,str], existingContent, section}）。
 *
 * 🔴 铁律：`context` 后端类型是 dict[str,str]，所有值必须转字符串，否则 422。
 */
import { ref, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export interface UseK8AiGenerateOptions {
  wpId: Ref<string>
}

/** 把任意 context 值安全转成字符串（避免 dict[str,str] 422） */
function stringifyContext(ctx: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(ctx)) {
    if (v == null) continue
    out[k] = typeof v === 'string' ? v : String(v)
  }
  return out
}

export function useK8AiGenerate(options: UseK8AiGenerateOptions) {
  const { wpId } = options
  const aiAvailable = ref(false)
  const loading = ref(false)

  async function checkAiHealth(): Promise<void> {
    try {
      const r = await http.get('/api/ai/health', { _silent: true } as any)
      const status = r.data?.data?.status ?? r.data?.status
      aiAvailable.value = status === 'healthy' || status === 'degraded'
    } catch {
      aiAvailable.value = false
    }
  }

  async function generate(
    section: string,
    existingContent: string,
    context: Record<string, unknown>,
    prompt = '',
  ): Promise<string> {
    const res = await http.post(
      `/api/workpapers/${wpId.value}/ai/generate-text`,
      {
        prompt,
        section,
        existingContent: existingContent ?? '',
        context: stringifyContext(context),
      },
      { _silent: true } as any,
    )
    return res.data?.data?.content ?? res.data?.content ?? ''
  }

  /** 生成 → ElMessageBox 预览确认 → 返回文本（取消/失败返回 null） */
  async function generateAndConfirm(
    section: string,
    existingContent: string,
    context: Record<string, unknown>,
    title: string,
    prompt = '',
  ): Promise<string | null> {
    if (!aiAvailable.value) {
      ElMessage.warning('AI 服务暂不可用')
      return null
    }
    loading.value = true
    try {
      const text = await generate(section, existingContent, context, prompt)
      if (!text) {
        ElMessage.warning('AI 未生成内容')
        return null
      }
      const preview = text.length > 500 ? `${text.slice(0, 500)}…` : text
      await ElMessageBox.confirm(preview, title, {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
        type: 'info',
        customStyle: { maxWidth: '620px' },
      })
      return text
    } catch (err: any) {
      if (err !== 'cancel' && err?.message !== 'cancel') {
        ElMessage.warning('AI 生成失败')
      }
      return null
    } finally {
      loading.value = false
    }
  }

  onMounted(() => { void checkAiHealth() })

  return { aiAvailable, loading, generate, generateAndConfirm, checkAiHealth }
}

export default useK8AiGenerate
