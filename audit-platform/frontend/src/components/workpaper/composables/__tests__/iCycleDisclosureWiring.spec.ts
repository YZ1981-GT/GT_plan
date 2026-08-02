/**
 * I 循环披露 Tab 接线正确性守卫
 *
 * spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/ Task 7.1
 *
 * 背景：I 循环 6 个底稿（I1 无形资产 / I2 开发支出 / I3 商誉 / I4 长期待摊费用
 * / I5 其他非流动资产 / I6 研发费用）共有 12 个披露 Tab + 6 个审定表 Tab。
 *
 * 本守卫验证 4 项 wiring 属性：
 * - Property 9: syncToNotes/syncToDisclosureNotes 函数体内不得出现 scheduleAutoSync
 *   （自调度 = 800ms 周期重复 POST + 骗过覆盖率守卫，见踩坑铁律）
 * - Property 12: `el-input-number` 计数归零（金额用 WpAmountInput），
 *   唯一例外 = I1 Listed 的 `remainingAmortMonths`（摊销月份是整数非金额）
 * - AI `context` 必须是对象而非字符串（后端 `dict[str,str]`，字符串必 422）
 * - 披露子组件必须收到 `:project-id` 或 `v-bind="$props"`
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve, basename } from 'node:path'

// ─── Helpers ───────────────────────────────────────────────────────────────

const WP_ROOT = resolve(__dirname, '../..')
const CORE_DIRS = ['i1', 'i2', 'i3', 'i4', 'i5', 'i6'].map(
  (p) => resolve(WP_ROOT, p, 'core')
)

/** 去掉 `//` 行注释与 `/* *\/` 块注释，避免注释里的反例被当代码统计 */
export function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
}

/** 从 .vue 文件提取 <script> + <template> 全文（去注释） */
function readVueFile(path: string): string {
  const raw = readFileSync(path, 'utf-8')
  return stripComments(raw)
}

/** 从 .vue 文件提取仅 <script> 部分（去注释） */
function readVueScript(path: string): string {
  const raw = readFileSync(path, 'utf-8')
  const match = raw.match(/<script[^>]*>([\s\S]*?)<\/script>/)
  return match ? stripComments(match[1]) : ''
}

// ─── Target file collection ────────────────────────────────────────────────

interface TargetFile {
  name: string
  path: string
  cycle: string
  isDisclosure: boolean
  isAdjudication: boolean
}

const TARGET_FILES: TargetFile[] = []
for (const dir of CORE_DIRS) {
  let files: string[] = []
  try {
    files = readdirSync(dir).filter((f) => f.endsWith('.vue'))
  } catch {
    // core dir might not exist for some cycles
    continue
  }
  const cycle = basename(resolve(dir, '..'))
  for (const f of files) {
    const isDisclosure = /TabDisclosure/i.test(f)
    const isAdjudication = /TabAdjudication/i.test(f)
    if (isDisclosure || isAdjudication) {
      TARGET_FILES.push({
        name: f,
        path: resolve(dir, f),
        cycle,
        isDisclosure,
        isAdjudication,
      })
    }
  }
}

const DISCLOSURE_FILES = TARGET_FILES.filter((t) => t.isDisclosure)
const ALL_FILES = TARGET_FILES

// ─── Regexes ───────────────────────────────────────────────────────────────

/** `context:` 后紧跟反引号/引号 = 传了字符串（后端要 dict[str,str] → 422） */
const STRING_CONTEXT_RE = /context:\s*[`'"]/

// ─── Tests ─────────────────────────────────────────────────────────────────

describe('I 循环披露 Tab 接线正确性', () => {
  // ===== Reverse self-checks =====

  describe('反向自检', () => {
    it('stripComments 去除行注释', () => {
      const input = `const x = 1 // scheduleAutoSync 是坏味道`
      const result = stripComments(input)
      expect(result).not.toContain('scheduleAutoSync')
      expect(result).toContain('const x = 1')
    })

    it('stripComments 去除块注释', () => {
      const input = `/* scheduleAutoSync(syncToNotes) */ const y = 2`
      const result = stripComments(input)
      expect(result).not.toContain('scheduleAutoSync')
      expect(result).toContain('const y = 2')
    })

    it('stripComments 不误删字符串内的双斜杠', () => {
      const input = `const url = "https://example.com/ai/generate-text"`
      const result = stripComments(input)
      expect(result).toContain('/ai/generate-text')
    })

    it('目标文件列表非空（> 10 个文件）', () => {
      // 6 cycles × (2 disclosure + 1 adjudication) = 18 target files
      expect(TARGET_FILES.length).toBeGreaterThan(10)
    })

    it('披露文件列表 = 12（I1~I6 × listed/soe）', () => {
      expect(DISCLOSURE_FILES.length).toBe(12)
    })
  })

  // ===== Property 9: No self-scheduling =====

  describe('Property 9 — syncToNotes 函数体内不得 scheduleAutoSync', () => {
    it.each(DISCLOSURE_FILES.map((f) => [f.name, f.path]))(
      '%s',
      (_name, filePath) => {
        const script = readVueScript(filePath)

        // Find syncToNotes / syncToDisclosureNotes function bodies
        // Match: function syncToNotes|async function syncToNotes|const syncToNotes = ...
        const syncFnRe =
          /(?:(?:async\s+)?function\s+(?:syncToNotes|syncToDisclosureNotes)\s*\([^)]*\)\s*\{|(?:const|let)\s+(?:syncToNotes|syncToDisclosureNotes)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*\w+\s*)?=>\s*\{|(?:const|let)\s+(?:syncToNotes|syncToDisclosureNotes)\s*=\s*(?:async\s+)?function\s*\([^)]*\)\s*\{)/g

        let match: RegExpExecArray | null
        while ((match = syncFnRe.exec(script)) !== null) {
          // Extract function body by counting braces
          const start = match.index + match[0].length
          let depth = 1
          let i = start
          while (i < script.length && depth > 0) {
            if (script[i] === '{') depth++
            else if (script[i] === '}') depth--
            i++
          }
          const body = script.slice(start, i - 1)
          expect(
            body.includes('scheduleAutoSync'),
            `${_name}: scheduleAutoSync found INSIDE syncToNotes/syncToDisclosureNotes body = self-scheduling`
          ).toBe(false)
        }
      }
    )
  })

  // ===== Property 12: el-input-number count = 0 (except I1 Listed remainingAmortMonths) =====

  describe('Property 12 — el-input-number 归零', () => {
    it.each(ALL_FILES.map((f) => [f.name, f.path, f.cycle]))(
      '%s',
      (name, filePath, cycle) => {
        const src = readVueFile(filePath)
        const count = (src.match(/<el-input-number/g) ?? []).length

        if (name === 'I1TabDisclosureListed.vue') {
          // I1 Listed allows exactly 1 for remainingAmortMonths (integer months, not monetary)
          expect(
            count,
            'I1TabDisclosureListed.vue should have at most 1 el-input-number (remainingAmortMonths)'
          ).toBeLessThanOrEqual(1)
        } else {
          expect(
            count,
            `${name}: found ${count} el-input-number — monetary fields must use WpAmountInput`
          ).toBe(0)
        }
      }
    )
  })

  // ===== AI context type: must not be a bare string =====

  describe('AI context 必须是对象（非字符串）', () => {
    it.each(DISCLOSURE_FILES.map((f) => [f.name, f.path]))(
      '%s',
      (_name, filePath) => {
        const script = readVueScript(filePath)

        // Only check files that actually call the AI endpoint
        if (/\/ai\/generate-text/.test(script) || /ai-generate/.test(script)) {
          expect(
            STRING_CONTEXT_RE.test(script),
            `${_name}: AI context 传了字符串 → 后端要 dict[str,str]，必然 422`
          ).toBe(false)
        }
      }
    )
  })

  // ===== :project-id passed to disclosure sub-components =====

  describe(':project-id 或 v-bind="$props" 传给披露子组件', () => {
    it.each(DISCLOSURE_FILES.map((f) => [f.name, f.path]))(
      '%s',
      (_name, filePath) => {
        const raw = readFileSync(filePath, 'utf-8')
        const template = raw.match(/<template>([\s\S]*?)<\/template>/)
        if (!template) return

        const tmpl = template[1]

        // Only match PascalCase Vue components (start with uppercase, at least 2 uppercase)
        // that have "Disclosure" or "Sync" or "Note" in the tag name itself.
        // This excludes <div>, <el-button>, <el-input> etc.
        const subComponentRe =
          /<([A-Z][a-zA-Z]*(?:Disclosure|Sync|Note|DisclosureNote)[a-zA-Z]*)[^>]*>/g
        let match: RegExpExecArray | null
        while ((match = subComponentRe.exec(tmpl)) !== null) {
          const fullTag = match[0]
          const tagName = match[1]
          // Check that it has :project-id or v-bind="$props"
          const hasProjectId =
            /:project-id/.test(fullTag) || /v-bind="\$props"/.test(fullTag)
          expect(
            hasProjectId,
            `${_name}: <${tagName}> missing :project-id or v-bind="$props"`
          ).toBe(true)
        }
      }
    )
  })
})
