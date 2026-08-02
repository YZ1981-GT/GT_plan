/**
 * e1SetupOrder.spec.ts — `<script setup>` 声明顺序守卫（防 TDZ 崩溃复发）
 *
 * 背景（2026-08-01 E1 实证的第四种「只有浏览器挂载才暴露」缺陷）：
 * `E1TabDisclosure.vue` 原先把 `watch([disclosureRows, restrictedRows, noteText, variant], …)`
 * 写在 setup 顶部（L62），而这四个 `const` 分别声明在 L83/167/452/493。
 * `<script setup>` 编译成的 setup 函数里 `const` 有 TDZ，**watch 的依赖数组在 setup 期即求值**
 * → 抛 ReferenceError → 整个披露 Tab 挂载失败、手动同步与自动同步一起废掉。
 *
 * 而 `get_diagnostics`(Volar) 零诊断、Vite transform 200、vitest 不覆盖该分支 —— 只有
 * 浏览器挂载才暴露。故用源码级守卫钉死「被监听标识符声明行号 < watch 行号」。
 *
 * 🔴 必须先 blankComments()：本守卫与被守卫源码的注释里都写着反例（含 `watch(` 字样与
 *    标识符名），不剥离会误报。**且必须保留行数**（本守卫按行号裁决），所以是
 *    「注释字符换成空格」而非「整段删掉」。
 * 🔴 每条规则都有反向自检：内联 fixture 构造违规源码，断言检测器确实能抓出来，
 *    证明断言不是空转。
 *
 * **Validates: Requirements 1.1, 1.2, 1.4**
 *
 * spec: e1-four-table-extraction-and-disclosure-alignment (Task 1)
 * Property: 7
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import { resolve } from 'path'

// ─── 路径常量 ─────────────────────────────────────────────────────────────────

const WP_ROOT = resolve(__dirname, '../..')
const E1_ROOT = resolve(WP_ROOT, 'e1')
const DISCLOSURE_PATH = resolve(E1_ROOT, 'E1TabDisclosure.vue')

// ─── 注释剥离（保留行数）──────────────────────────────────────────────────────

/**
 * 把注释内容换成等长空白，**保留换行**，使行号不偏移。
 * 覆盖 JS 块注释 / JS 行注释 / HTML 注释；`//` 前有 `:` 的跳过（避免误伤 URL）。
 */
export function blankComments(src: string): string {
  const blank = (m: string) => m.replace(/[^\n]/g, ' ')
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[^:])(\/\/[^\n]*)/gm, (_m, pre: string, cmt: string) => pre + blank(cmt))
}

// ─── 声明顺序检测器 ───────────────────────────────────────────────────────────

/** 提取 `<script setup>` 块内容与其在原文件中的起始行偏移。 */
function extractScriptSetup(src: string): { body: string; lineOffset: number } {
  const m = /<script\b[^>]*\bsetup\b[^>]*>/.exec(src)
  if (!m) return { body: '', lineOffset: 0 }
  const start = m.index + m[0].length
  const end = src.indexOf('</script>', start)
  const body = src.slice(start, end < 0 ? undefined : end)
  const lineOffset = src.slice(0, start).split('\n').length - 1
  return { body, lineOffset }
}

/** 顶层 `const`/`let`/`function` 声明 → 1-based 行号（同名取最早一次）。 */
function collectTopLevelDeclLines(body: string): Map<string, number> {
  const out = new Map<string, number>()
  body.split('\n').forEach((line, i) => {
    // 只认顶层（行首无缩进）声明，避免把函数体内的局部变量当顶层
    const m = /^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*[=:]/.exec(line)
      || /^(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/.exec(line)
    if (m && !out.has(m[1])) out.set(m[1], i + 1)
  })
  return out
}

export interface SetupOrderViolation {
  identifier: string
  watchLine: number
  declLine: number
}

/**
 * 找出所有「`watch(` 依赖里引用了后面才声明的顶层 const」的违规点。
 *
 * 依赖表达式 = `watch(` 之后到**深度 0 的第一个逗号**（或右括号）为止的片段，
 * 即 watch 的第一个实参（source）。回调体内引用后面声明的符号是合法的
 * （回调延迟执行），只有 source 会在 setup 期立即求值。
 */
export function findSetupOrderViolations(src: string): SetupOrderViolation[] {
  const { body, lineOffset } = extractScriptSetup(src)
  if (!body) return []
  const clean = blankComments(body)
  const decls = collectTopLevelDeclLines(clean)
  const violations: SetupOrderViolation[] = []

  const re = /\bwatch(?:Effect)?\s*\(/g
  let m: RegExpExecArray | null
  while ((m = re.exec(clean)) !== null) {
    const openIdx = m.index + m[0].length - 1
    // 扫到深度 0 的逗号 / 匹配的右括号为止 = 第一个实参
    let depth = 0
    let i = openIdx
    for (; i < clean.length; i += 1) {
      const ch = clean[i]
      if (ch === '(' || ch === '[' || ch === '{') depth += 1
      else if (ch === ')' || ch === ']' || ch === '}') {
        depth -= 1
        if (depth === 0) break
      } else if (ch === ',' && depth === 1) break
    }
    const sourceExpr = clean.slice(openIdx + 1, i)
    const watchLine = clean.slice(0, m.index).split('\n').length

    // source 表达式里出现的标识符（跳过属性访问的右侧：`props.foo` 的 foo）
    const idRe = /(?:^|[^.\w$])([A-Za-z_$][\w$]*)/g
    let idm: RegExpExecArray | null
    const seen = new Set<string>()
    while ((idm = idRe.exec(sourceExpr)) !== null) {
      const id = idm[1]
      if (seen.has(id)) continue
      seen.add(id)
      const declLine = decls.get(id)
      if (declLine !== undefined && declLine > watchLine) {
        violations.push({
          identifier: id,
          watchLine: watchLine + lineOffset,
          declLine: declLine + lineOffset,
        })
      }
    }
  }
  return violations
}

// ─── 被守卫文件清单（E1 全部 .vue）───────────────────────────────────────────

const E1_VUE_FILES = [
  'E1TabDisclosure.vue',
  'E1TabAdjudication.vue',
  'E1TabCashDetail.vue',
  'E1TabBankDetail.vue',
  'E1TabCashCount.vue',
  'E1TabCreditReport.vue',
  'E1TabDigitalCurrency.vue',
  'E1TabAnalysis.vue',
  'E1TabReconciliation.vue',
  'E1TabAccountList.vue',
].filter((f) => existsSync(resolve(E1_ROOT, f)))

// ─── Property 7: setup 声明顺序 ───────────────────────────────────────────────

describe('Property 7: <script setup> 声明顺序（防 TDZ）', () => {
  it('被守卫文件清单非空（反向自检：路径没写错）', () => {
    expect(E1_VUE_FILES.length).toBeGreaterThan(0)
    expect(E1_VUE_FILES).toContain('E1TabDisclosure.vue')
  })

  it.each(E1_VUE_FILES)('%s 的 watch source 不得引用后面才声明的顶层 const', (file) => {
    const src = readFileSync(resolve(E1_ROOT, file), 'utf-8')
    const violations = findSetupOrderViolations(src)
    expect(
      violations,
      violations.length
        ? `TDZ 风险：${file} 中 ${violations
            .map((v) => `watch@L${v.watchLine} 引用了 L${v.declLine} 才声明的 \`${v.identifier}\``)
            .join('；')}。`
          + '修法：把 watch 移到全部被监听 const 声明之后（通常放文件末尾 Cleanup 之前）。'
        : '',
    ).toEqual([])
  })

  it('E1TabDisclosure.vue 的自动同步 watch 确实注册在 syncToDisclosureNotes 之后', () => {
    const src = readFileSync(DISCLOSURE_PATH, 'utf-8')
    const { body } = extractScriptSetup(src)
    const clean = blankComments(body)

    const syncDeclIdx = clean.indexOf('async function syncToDisclosureNotes')
    const watchIdx = clean.search(/\bwatch\(\s*\n?\s*\[disclosureRows/)

    // 反向自检：两个锚点都必须真实存在，否则断言是空转
    expect(syncDeclIdx, 'syncToDisclosureNotes 声明未找到（锚点漂移）').toBeGreaterThan(-1)
    expect(watchIdx, '自动同步 watch 未找到（锚点漂移）').toBeGreaterThan(-1)
    expect(watchIdx).toBeGreaterThan(syncDeclIdx)
  })

  it('E1TabDisclosure.vue 不再本地重复声明 DisclosureVariant（与 import 双真源）', () => {
    const src = readFileSync(DISCLOSURE_PATH, 'utf-8')
    const clean = blankComments(src)
    // import 侧必须存在（反向自检）
    expect(clean).toMatch(/import\s*\{[^}]*type\s+DisclosureVariant[^}]*\}\s*from/)
    // 本地 type alias 必须不存在
    expect(clean).not.toMatch(/^\s*type\s+DisclosureVariant\s*=/m)
  })
})

// ─── 反向自检：检测器本身有效 ─────────────────────────────────────────────────

describe('检测器反向自检', () => {
  const BAD = `<script setup lang="ts">
import { ref, watch, computed } from 'vue'
watch(
  [rowsX, textY],
  () => { doSomething() },
  { deep: true },
)
const rowsX = computed(() => [])
const textY = ref('')
</script>`

  const GOOD = `<script setup lang="ts">
import { ref, watch, computed } from 'vue'
const rowsX = computed(() => [])
const textY = ref('')
watch(
  [rowsX, textY],
  () => { doSomething() },
  { deep: true },
)
</script>`

  it('能抓出 watch 早于声明的违规（否则守卫是空转）', () => {
    const v = findSetupOrderViolations(BAD)
    expect(v.map((x) => x.identifier).sort()).toEqual(['rowsX', 'textY'])
  })

  it('声明顺序正确时不误报', () => {
    expect(findSetupOrderViolations(GOOD)).toEqual([])
  })

  it('回调体内引用后声明的符号不算违规（回调延迟执行，合法）', () => {
    const src = `<script setup lang="ts">
import { ref, watch } from 'vue'
const a = ref(0)
watch(a, () => { laterFn() })
const laterFn = () => {}
</script>`
    expect(findSetupOrderViolations(src)).toEqual([])
  })

  it('blankComments 保留行数且能屏蔽注释里的反例', () => {
    const src = 'const a = 1\n// watch([zzz], …) 这是注释里的反例\nconst zzz = 2\n'
    const out = blankComments(src)
    expect(out.split('\n').length).toBe(src.split('\n').length)
    expect(out).not.toContain('watch([zzz]')
  })
})
