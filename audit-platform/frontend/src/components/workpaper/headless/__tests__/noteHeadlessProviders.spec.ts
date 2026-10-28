/**
 * 离屏 provider 登记与副作用守卫（spec note-pull-followup-closure R1.2）。
 *
 * - 按组登记：每组只登记本组编码，同一编码只在一组；
 * - 每个登记项 = `() => import('<模块>').then((m) => m.<导出>)`，导出由 `defineHeadlessProvider(` 声明；
 * - provider 模块离屏没有界面：不 import element-plus / `.vue` 组件、不调 Tab 的 `syncTo…` 同步函数（里面有提示 / 确认框）、
 *   不接受限资产段同步。
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { HEADLESS_PROVIDER_GROUPS, HEADLESS_PROVIDERS } from '../registry'

const SRC = resolve(__dirname, '../../../..')
const GROUP_RULES: Record<string, RegExp> = {
  de: /^[DE]\d+$/, fjn: /^[FJN]\d+$/, g1: /^G[1-7]$/, g2: /^G(?:[89]|1[0-4])$/, h: /^H\d+$/, i: /^I\d+$/,
  k1: /^K[1-6]$/, k2: /^K(?:[7-9]|1[0-3])$/, l: /^L\d+$/, m: /^M\d+$/,
}
const ENTRY_RE = /^\s*(\w+):\s*\(\)\s*=>\s*import\(\s*'([^']+)'\s*\)\.then\(\(m\)\s*=>\s*m\.(\w+)\),?\s*$/gm
const FORBIDDEN: Array<[RegExp, string]> = [
  [/from\s+'element-plus'/, 'import element-plus'],
  [/\bEl(?:Message|MessageBox|Notification)\b/, '界面提示'],
  [/from\s+'[^']+\.vue'/, 'import .vue 组件'],
  [/\bsyncTo[A-Z]\w*\s*\(/, '调 Tab 的同步函数'],
  [/\buseRestrictedAssetsSync\b/, '受限资产段同步'],
]

function entries(group: string): Array<{ code: string; path: string; name: string }> {
  const text = readFileSync(resolve(__dirname, `../providers/${group}.ts`), 'utf-8')
  return [...text.matchAll(ENTRY_RE)].map((m) => ({ code: m[1], path: m[2], name: m[3] }))
}

function moduleSource(spec: string): string {
  const base = spec.startsWith('@/') ? resolve(SRC, spec.slice(2)) : resolve(__dirname, '../providers', spec)
  const file = [`${base}.ts`, `${base}/index.ts`].find((p) => existsSync(p))
  if (!file) throw new Error(`找不到 provider 模块：${spec}`)
  return readFileSync(file, 'utf-8')
}

describe('离屏 provider 登记', () => {
  it('每组只登记本组编码，同一编码只在一组', () => {
    const seen = new Map<string, string>()
    for (const [group, record] of Object.entries(HEADLESS_PROVIDER_GROUPS)) {
      expect(GROUP_RULES[group], `未知分组 ${group}`).toBeDefined()
      for (const code of Object.keys(record)) {
        expect(code, `${group} 组登记了 ${code}`).toMatch(GROUP_RULES[group])
        expect(seen.get(code), `${code} 在 ${seen.get(code)} 与 ${group} 两组都登记了`).toBeUndefined()
        seen.set(code, group)
      }
    }
    expect([...seen.keys()].sort()).toEqual(Object.keys(HEADLESS_PROVIDERS).sort())
  })

  it('登记项都是「懒加载 + defineHeadlessProvider 声明的导出」，模块没有界面副作用', () => {
    for (const [group, record] of Object.entries(HEADLESS_PROVIDER_GROUPS)) {
      const found = entries(group)
      expect(found.map((e) => e.code).sort(), `${group} 组登记写法`).toEqual(Object.keys(record).sort())
      for (const { code, path, name } of found) {
        const src = moduleSource(path)
        expect(src, `${code}：${path} 应导出 ${name} = defineHeadlessProvider(...)`)
          .toMatch(new RegExp(`export const ${name}\\b[^=]*=\\s*defineHeadlessProvider[<(]`))
        for (const [re, what] of FORBIDDEN) expect(re.test(src), `${code}：${path} 不得${what}`).toBe(false)
      }
    }
  })

  it('登记项都能加载出 provider 函数', async () => {
    for (const [code, load] of Object.entries(HEADLESS_PROVIDERS)) {
      expect(typeof (await load()), code).toBe('function')
    }
  })

  it('守卫自检：违规写法能被认出来', () => {
    const bad = "import { ElMessage } from 'element-plus'\nimport X from './X.vue'\nsyncToNotes()\nuseRestrictedAssetsSync()"
    expect(FORBIDDEN.filter(([re]) => re.test(bad)).length).toBe(FORBIDDEN.length)
    expect([..."  D9: () => import('@/a/b').then((m) => m.p),\n".matchAll(ENTRY_RE)].length).toBe(1)
  })
})
