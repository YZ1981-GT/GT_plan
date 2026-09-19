/**
 * useN1AiText — N1 递延所得税资产 AI 文本生成（真回填）
 *
 * 实现已提升为平台共用 `shared/wpAiText.ts`（`n-cycle-tax-disclosure-alignment`
 * Task 2：N2 / N4 / N5 复用同一端点契约）。本模块保留为 N1 侧的具名入口，
 * 避免既有引用 churn。
 *
 * 端点契约（写错就静默空转，见 shared/wpAiText.ts 注释）：
 * `POST /api/workpapers/{wpId}/ai/generate-text`，
 * body `{section, prompt, context: dict[str,str], existingContent}`，
 * 响应 `data.data.content`。
 */
import { generateWpText, type GenerateWpTextOptions } from './shared/wpAiText'

export type GenerateN1TextOptions = GenerateWpTextOptions

/**
 * 调用 AI 生成文本并返回内容字符串。
 * @returns 生成的文本；失败或无返回时为空串。
 */
export async function generateN1Text(opts: GenerateN1TextOptions): Promise<string> {
  return generateWpText(opts)
}

export default generateN1Text
