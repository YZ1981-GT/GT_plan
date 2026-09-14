/**
 * 平台级守卫：`DisplayPrefs_Key` 的引入来源必须是单一真源
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion (Task 30)
 *
 * ## 缺陷形态（2026-08-07 浏览器实测抓出，5 个文件中招）
 *
 * `DisplayPrefs_Key` 只在 `composables/displayPrefsKey.ts` 导出；
 * `stores/displayPrefs.ts` 的导出集是 TableDensity / TABLE_DENSITIES /
 * FixedColumnsConfig / useDisplayPrefsStore，**没有** 这个 key。
 *
 * 从 store 连带引入它，浏览器会抛
 * "does not provide an export named" + key 名，整个底稿页崩成
 * 「页面渲染出错」白屏 —— 而 Volar `get_diagnostics` / vitest / Vite transform
 * 三层全绿（Vite transform 只做单文件编译，不解析跨模块导出集合）。
 *
 * 实测中招清单（已全部修正）：
 *   d4/core/D4TabDisclosureSoe.vue · d4/core/D4TabDisclosureListed.vue
 *   f3-notes-payable/F3TabDisclosureListed.vue · F3TabDisclosureSOE.vue
 *   custom/GtCustomGridSheet.vue
 *
 * 与 memory 已登记的「`fmtAmount` 是 store 成员不是模块级导出」是同一族：
 * 只有浏览器能发现的运行时导出缺失。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

// ─── 仓库根定位（双哨兵具体文件，禁写死回退级数）────────────────────────────

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const a = join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = join(dir, 'backend', 'requirements.txt')
    try {
      statSync(a)
      statSync(b)
      return dir
    } catch {
      dir = join(dir, '..')
    }
  }
  throw new Error('repoRoot 未找到（双哨兵均未命中）')
}

const ROOT = repoRoot()
const SRC = join(ROOT, 'audit-platform', 'frontend', 'src')
const KEY_MODULE = join(SRC, 'components', 'workpaper', 'composables', 'displayPrefsKey.ts')
const STORE_MODULE = join(SRC, 'stores', 'displayPrefs.ts')

/** 本守卫自身（文档里必然写着反例，不能自我命中）*/
const SELF_REL = relative(SRC, __filename).split(sep).join('/')

const KEY_NAME = 'DisplayPrefs_Key'
/** 反例路径按段拼接，避免本文件出现完整字面量而被自己扫到 */
const STORE_SPEC = '@/stores/' + 'displayPrefs'

// ─── 扫描 ────────────────────────────────────────────────────────────────────

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist' || name === '.git') continue
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) walk(p, out)
    else if (/\.(ts|vue)$/.test(name)) out.push(p)
  }
  return out
}

/** 剥块注释 / 行注释；不处理字符串，故调用方须另行排除自身文档 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

interface Hit {
  rel: string
  names: string[]
}

/** 收集「从 store 引入 DisplayPrefs_Key」的位置 */
function collectWrongImports(): Hit[] {
  const hits: Hit[] = []
  const re = /import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g
  for (const abs of walk(SRC)) {
    const rel = relative(SRC, abs).split(sep).join('/')
    if (rel === SELF_REL) continue // 本守卫文档里写着反例
    const body = stripComments(readFileSync(abs, 'utf-8'))
    let m: RegExpExecArray | null
    while ((m = re.exec(body)) !== null) {
      const spec = m[2]
      if (!spec.endsWith('stores/displayPrefs')) continue
      const names = m[1]
        .split(',')
        .map((s) => s.trim().replace(/^type\s+/, '').split(/\s+as\s+/)[0].trim())
        .filter(Boolean)
      if (names.includes(KEY_NAME)) hits.push({ rel, names })
    }
  }
  return hits
}

/** 收集「正确从 composables/displayPrefsKey 引入」的位置（证明扫描面非空）*/
function collectCorrectImports(): string[] {
  const out: string[] = []
  const re = /import\s*\{[^}]*\}\s*from\s*['"]([^'"]*displayPrefsKey)['"]/g
  for (const abs of walk(SRC)) {
    const rel = relative(SRC, abs).split(sep).join('/')
    if (rel === SELF_REL) continue
    const body = stripComments(readFileSync(abs, 'utf-8'))
    if (re.test(body)) out.push(rel)
    re.lastIndex = 0
  }
  return out
}

// ─── Property：真源与 store 的导出集互斥 ─────────────────────────────────────

describe('平台级：DisplayPrefs_Key 引入来源单一真源', () => {
  it('真源模块 composables/displayPrefsKey.ts 确实导出该 key', () => {
    const src = readFileSync(KEY_MODULE, 'utf-8')
    expect(new RegExp(`export\\s+const\\s+${KEY_NAME}\\b`).test(src)).toBe(true)
  })

  it('stores/displayPrefs.ts 确实不导出该 key（这是崩溃的根因，不是笔误）', () => {
    const src = readFileSync(STORE_MODULE, 'utf-8')
    // 任何形态的导出都算：export const / export { X } / export type
    const hasNamedExport =
      new RegExp(`export\\s+(const|let|var|type|function)\\s+${KEY_NAME}\\b`).test(src) ||
      new RegExp(`export\\s*\\{[^}]*\\b${KEY_NAME}\\b[^}]*\\}`).test(src)
    expect(hasNamedExport).toBe(false)
  })

  it(`全前端不得从 ${STORE_SPEC} 引入 ${KEY_NAME}（运行时崩溃，四层查不出）`, () => {
    const hits = collectWrongImports()
    expect(
      hits.map((h) => `${h.rel}  names=${h.names.join('|')}`),
      `${KEY_NAME} 只在 composables/displayPrefsKey.ts 导出。从 store 引入会在浏览器抛` +
        ' "does not provide an export named" 并让整个底稿页白屏 ——' +
        ' 而 Volar / vitest / Vite transform 全绿。',
    ).toEqual([])
  })

  // ─── 反向自检：证明扫描面非空、判据真的会命中 ───────────────────────────

  it('反向自检：正确引入该 key 的文件数量可观（扫描面非空）', () => {
    const ok = collectCorrectImports()
    expect(ok.length).toBeGreaterThan(30)
  })

  it('反向自检：判据对替身源码必打红', () => {
    const fake = [
      'import { useDisplayPrefsStore, ' + KEY_NAME + " } from '" + STORE_SPEC + "'",
      'const p = inject(' + KEY_NAME + ', null)',
    ].join('\n')
    const re = /import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g
    const m = re.exec(stripComments(fake))
    expect(m).not.toBeNull()
    expect(m![2].endsWith('stores/displayPrefs')).toBe(true)
    expect(m![1]).toContain(KEY_NAME)
  })

  it('反向自检：正确来源的 import 不得被判据误伤', () => {
    const good = "import { " + KEY_NAME + " } from '../composables/displayPrefsKey'"
    const re = /import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g
    const m = re.exec(stripComments(good))
    expect(m).not.toBeNull()
    expect(m![2].endsWith('stores/displayPrefs')).toBe(false)
  })

  it('反向自检：stripComments 确实剥掉了注释里的反例', () => {
    const withComment = [
      '// import { ' + KEY_NAME + " } from '" + STORE_SPEC + "'",
      '/* import { ' + KEY_NAME + " } from '" + STORE_SPEC + "' */",
      'const x = 1',
    ].join('\n')
    const stripped = stripComments(withComment)
    expect(stripped).not.toContain('import {')
    expect(stripped).toContain('const x = 1')
  })
})
