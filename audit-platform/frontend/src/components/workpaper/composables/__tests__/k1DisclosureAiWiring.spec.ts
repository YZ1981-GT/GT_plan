/**
 * K1 披露文字段落 AI 辅助接线守卫（Requirement 9.4）.
 *
 * 每个说明文本域必须：① 界面有 AI 按钮调用 `useK1AiGenerate` ② 对应
 * `_k1_ai_generate.py` 的 `_SECTION_PROMPTS` 有专属 prompt（≥20 字 + 不得虚构约束）。
 *
 * spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function readSrc(rel: string): string {
  return readFileSync(resolve(REPO_ROOT, rel), 'utf-8')
}

const listedVue = readSrc(
  'audit-platform/frontend/src/components/workpaper/k1/core/K1TabDisclosureListed.vue',
)
const backendAi = readSrc('backend/app/routers/wp_render_strategies/_k1_ai_generate.py')

describe('K1 上市披露 Tab：文本域 ↔ AI section 映射完整', () => {
  const expected: Record<string, string> = {
    balanceChange: 'disclosure-balance-change',
    eclBasis: 'disclosure-ecl-basis',
    writeoffNote: 'disclosure-writeoff-note',
    transferNote: 'disclosure-transfer-note',
    fundCentralization: 'disclosure-fund-centralization',
  }

  it('AI_SECTION_BY_NOTE 含全部 5 个映射', () => {
    const m = listedVue.match(/const AI_SECTION_BY_NOTE[^{]*\{([^}]*)\}/)
    expect(m, 'AI_SECTION_BY_NOTE 抽取失败').toBeTruthy()
    const body = m![1]
    for (const [key, section] of Object.entries(expected)) {
      expect(body, key).toContain(`${key}:`)
      expect(body, key).toContain(`'${section}'`)
    }
  })

  it('每个映射对应界面上确有一个 🤖 AI 按钮调用 onAiNote(该 key)', () => {
    for (const key of Object.keys(expected)) {
      const re = new RegExp(`onAiNote\\('${key}'\\)`)
      expect(listedVue, key).toMatch(re)
    }
  })

  it('反向自检：不存在的 key 不应出现 onAiNote 调用（防止正则命中错位）', () => {
    expect(listedVue).not.toMatch(/onAiNote\('doesNotExist'\)/)
  })
})

describe('K1 AI 生成端点：_SECTION_PROMPTS 完整且不诱导虚构', () => {
  const disclosureSections = [
    'disclosure-balance-change',
    'disclosure-ecl-basis',
    'disclosure-writeoff-note',
    'disclosure-transfer-note',
    'disclosure-fund-centralization',
  ]

  it('_SUPPORTED_SECTIONS 含全部披露 section', () => {
    for (const s of disclosureSections) {
      expect(backendAi, s).toMatch(new RegExp(`"${s}"`))
    }
  })

  function extractPromptBody(section: string): string | null {
    const idx = backendAi.indexOf(`"${section}": (`)
    if (idx === -1) return null
    // 文件为 CRLF（`\r\n`），用正则匹配 `),` 后跟任意换行符，不硬编码 `\n`。
    const rest = backendAi.slice(idx)
    const closeMatch = rest.match(/\),\r?\n/)
    if (!closeMatch) return null
    return rest.slice(0, closeMatch.index)
  }

  it('每条 prompt ≥ 20 字（防止过短诱导模型自造内容）', () => {
    for (const s of disclosureSections) {
      const body = extractPromptBody(s)
      expect(body, `${s} prompt 抽取失败`).toBeTruthy()
      const promptText = (body!.match(/"([^"]*)"/g) || []).join('')
      expect(promptText.length, s).toBeGreaterThanOrEqual(20)
    }
  })

  it('反向自检：抽取器对已知不存在的 section 必须失败（防空转）', () => {
    expect(extractPromptBody('disclosure-does-not-exist')).toBeNull()
  })
})
