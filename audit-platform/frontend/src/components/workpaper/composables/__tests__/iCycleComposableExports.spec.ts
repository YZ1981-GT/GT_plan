/**
 * I 循环 composable **导出完整性**守卫 —— 组件解构的每个成员必须真在 return 清单里。
 *
 * ## 缺陷来源（浏览器实测，整页白屏）
 *
 * `I2TabDisclosureListed.vue` 从 `useI2Disclosure()` 解构了 `removeNatureRow`，
 * 而 `useI2Disclosure` 虽然**写了该函数的完整实现**，却漏在 return 清单里
 * ⇒ 解构得到 `undefined` ⇒ 点「删」触发
 * `TypeError: removeNatureRow is not a function` ⇒ ErrorBoundary 兜住后
 * **整页显示「页面渲染出错」**，且该次崩溃**打断了 debounce 保存**，
 * 刷新后用户刚新增的费用性质行整行消失（实测：加行后库里 1044 字节含新行，
 * 崩溃那次刷新后只剩源模板 6 行）。
 *
 * ## 四层守卫为何全绿
 *
 * | 层 | 为何漏 |
 * |---|---|
 * | grep | 搜 `removeNatureRow` 能搜到**函数定义**，看着像已接通 |
 * | model 层 vitest | 测的是 `removeI2NatureRow` 纯函数，与 composable 是否导出无关 |
 * | `tsc --noEmit` | **不解析 `.vue`**（本仓 805 个 TS2307 即此因），SFC 内解构错误要 `vue-tsc` |
 * | `get_diagnostics` | 无报（本轮已两次实证它对类型不匹配漏报） |
 *
 * ⇒ 判据只能落到「**运行时真调一次 composable，检查组件解构的键都在返回对象里**」。
 *
 * ## 本守卫的判据形态
 *
 * 从 SFC 源码里抽出 `= disc`／`= useXxx(...)` 的解构键集合（真实消费清单），
 * 再真实调用 composable 取其 return 键集合，两者做包含关系断言。
 * 这样**新增解构而忘了导出**会立刻打红，且不依赖手工维护键名列表。
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 24（补测 3/5）
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import useI2Disclosure from '../useI2Disclosure'
import { useI1ListedDisclosure, useI1SoeDisclosure } from '../useI1Disclosure'

// ─── REPO_ROOT：向上找具体哨兵文件，禁写死回退级数 ──────────────────────────
const HERE = dirname(fileURLToPath(import.meta.url))
function findUp(startDir: string, rel: string): string {
  let dir = startDir
  for (let i = 0; i < 12; i += 1) {
    try {
      readFileSync(join(dir, rel))
      return dir
    } catch {
      const parent = resolve(dir, '..')
      if (parent === dir) break
      dir = parent
    }
  }
  throw new Error(`找不到哨兵文件 ${rel}（从 ${startDir} 起向上 12 级）`)
}
const FRONTEND_ROOT = findUp(HERE, join('src', 'components', 'workpaper', 'composables', 'useI2Disclosure.ts'))
const WP_DIR = join(FRONTEND_ROOT, 'src', 'components', 'workpaper')

function readSfc(rel: string): string {
  return readFileSync(join(WP_DIR, rel), 'utf-8')
}

/** 去注释（防注释里的示例解构被当成真实消费） */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/**
 * 抽 SFC 里对某个源标识符的解构键集合。
 *
 * 匹配 `const { a, b, c } = <source>`（允许换行、别名 `a: b`、跳过 `...rest`）。
 * 🔴 括号配对扫描而非固定字符窗口（多行解构块常见，正则 `\{[^}]*\}` 会被
 *    嵌套的默认值对象骗过）。
 */
function destructuredKeys(src: string, source: string): Set<string> {
  const clean = stripComments(src)
  const out = new Set<string>()
  const re = new RegExp(`(?:const|let)\\s*\\{`, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(clean)) !== null) {
    const open = m.index + m[0].length - 1
    let depth = 0
    let end = -1
    for (let i = open; i < clean.length; i += 1) {
      const ch = clean[i]
      if (ch === '{') depth += 1
      else if (ch === '}') {
        depth -= 1
        if (depth === 0) { end = i; break }
      }
    }
    if (end < 0) continue
    const tail = clean.slice(end + 1, end + 1 + 120)
    // `} = disc` / `} = useI2Disclosure(` 才算命中目标来源
    if (!new RegExp(`^\\s*=\\s*${source}\\b`).test(tail)) continue
    for (const part of clean.slice(open + 1, end).split(',')) {
      const name = part.split(':')[0].trim()
      if (!name || name.startsWith('...')) continue
      if (/^[A-Za-z_$][\w$]*$/.test(name)) out.add(name)
    }
  }
  return out
}

function blankResponses() {
  return ref(new Map<string, any>())
}

describe('抽取器自检（判据本身不能失效）', () => {
  it('能抽出多行解构、别名与嵌套默认值不干扰', () => {
    const fake = `
      const {
        alpha, beta,
        gamma: renamed,
        ...rest
      } = disc
      const { unrelated } = somethingElse
      // const { commentedOut } = disc
      /* const { blockCommented } = disc */
    `
    const keys = destructuredKeys(fake, 'disc')
    expect(keys.has('alpha')).toBe(true)
    expect(keys.has('beta')).toBe(true)
    expect(keys.has('gamma')).toBe(true)      // 别名取左侧真实成员名
    expect(keys.has('renamed')).toBe(false)
    expect(keys.has('rest')).toBe(false)
    expect(keys.has('unrelated')).toBe(false)
    expect(keys.has('commentedOut'), '行注释里的解构被误当消费').toBe(false)
    expect(keys.has('blockCommented'), '块注释里的解构被误当消费').toBe(false)
  })

  it('抽取器在真实 SFC 上必须有产出（零产出=判据空转）', () => {
    const keys = destructuredKeys(readSfc(join('i2', 'core', 'I2TabDisclosureListed.vue')), 'disc')
    expect(keys.size, '抽不到任何解构键 ⇒ 本守卫恒绿，是判据缺陷不是代码没问题')
      .toBeGreaterThan(5)
  })
})

describe('I2 披露：组件解构的键必须都在 composable return 里', () => {
  const CASES: Array<[string, string]> = [
    ['上市版', join('i2', 'core', 'I2TabDisclosureListed.vue')],
    ['国企版', join('i2', 'core', 'I2TabDisclosureSoe.vue')],
  ]

  it.each(CASES)('%s', async (_label, rel) => {
    let src: string
    try {
      src = readSfc(rel)
    } catch {
      return // 该变体不存在则跳过（不制造假红）
    }
    const consumed = destructuredKeys(src, 'disc')
    if (!consumed.size) return

    const disc = useI2Disclosure(blankResponses(), {
      variant: rel.includes('Soe') ? 'soe' : 'listed',
    })
    await nextTick()
    const exported = new Set(Object.keys(disc as Record<string, unknown>))

    const missing = [...consumed].filter((k) => !exported.has(k))
    expect(
      missing,
      `组件解构了 composable 未导出的成员 ⇒ 运行时 undefined，点击即整页崩：${missing.join(', ')}`,
    ).toEqual([])
  })

  it('removeNatureRow 必须可调用（本轮崩溃点的定向回归）', async () => {
    const disc: any = useI2Disclosure(blankResponses(), { variant: 'listed' })
    await nextTick()
    expect(typeof disc.removeNatureRow, 'removeNatureRow 未导出 ⇒ 点「删」整页白屏').toBe('function')
    expect(typeof disc.addNatureRow).toBe('function')

    // 行为回归：加一行 → 可删；源模板固定 6 类不可删
    expect(disc.addNatureRow('委外研发费')).toBe(true)
    const custom = disc.natureRows.value.find((r: any) => r.name === '委外研发费')
    expect(custom).toBeTruthy()
    expect(disc.removeNatureRow(custom.rowId)).toBe(true)
    expect(disc.natureRows.value.some((r: any) => r.name === '委外研发费')).toBe(false)

    const fixed = disc.natureRows.value[0]
    expect(disc.removeNatureRow(fixed.rowId), '源模板固定类别竟可删').toBe(false)
    expect(disc.removeNatureRow('不存在的-rowId')).toBe(false)
  })
})

describe('I1 披露：两版 composable 的关键成员均可调用', () => {
  it('国企版导出 addCategory / removeCategory', async () => {
    const soe: any = useI1SoeDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()
    expect(typeof soe.addCategory).toBe('function')
    expect(typeof soe.removeCategory).toBe('function')
    expect(typeof soe.updateCategory).toBe('function')
  })

  it('上市版导出 addCategory / removeCategory / setCategoryPreset', async () => {
    const listed: any = useI1ListedDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()
    expect(typeof listed.addCategory).toBe('function')
    expect(typeof listed.removeCategory).toBe('function')
    expect(typeof listed.setCategoryPreset).toBe('function')
  })

  it.each([
    ['国企版', join('i1', 'core', 'I1TabDisclosureSoe.vue')],
    ['上市版', join('i1', 'core', 'I1TabDisclosureListed.vue')],
  ])('%s 组件解构的键都在 return 里', async (_label, rel) => {
    const src = readSfc(rel)
    const isSoe = rel.includes('Soe')
    const inst: any = isSoe
      ? useI1SoeDisclosure({ allResponses: blankResponses(), onSave: () => {} })
      : useI1ListedDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()
    const exported = new Set(Object.keys(inst))

    // I1 两版直接从 `useI1XxxDisclosure({...})` 解构
    const fnName = isSoe ? 'useI1SoeDisclosure' : 'useI1ListedDisclosure'
    const consumed = destructuredKeys(src, fnName)
    if (!consumed.size) return
    const missing = [...consumed].filter((k) => !exported.has(k))
    expect(
      missing,
      `组件解构了未导出的成员 ⇒ 运行时 undefined：${missing.join(', ')}`,
    ).toEqual([])
  })
})
