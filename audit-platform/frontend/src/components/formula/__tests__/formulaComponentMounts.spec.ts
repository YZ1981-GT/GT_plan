/**
 * 公式组件挂载守卫（spec formula-governance-coverage-closure R4.3）
 *
 * `components/formula/` 下每个 Vue 组件都必须被至少一处**生产代码**引用（import 路径，或模板里
 * PascalCase / kebab-case 标签）。测试、`components.d.ts`（开发服务器自动生成的登记表）、stories
 * 不算；注释里提到也不算 —— 否则「写了 262 行却从没挂过」的组件会一直躺着（R4 处置前有 6 个）。
 *
 * 新增组件忘了接线 / 接线被删 ⇒ 本守卫打红。确实该删的组件就删掉，不要加豁免。
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve, sep } from 'node:path'

const SRC = resolve(__dirname, '../../..')
const FORMULA_DIR = resolve(SRC, 'components', 'formula')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules') continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out
}

const rel = (p: string) => relative(SRC, p).split(sep).join('/')
const isTestOrGenerated = (r: string) =>
  r.includes('/__tests__/') || /\.(spec|test|stories)\.[jt]sx?$/.test(r) || r === 'components.d.ts'

/** 去掉注释（HTML / 块 / 行），注释里提到组件名不算引用；`://` 不当行注释（URL） */
function stripComments(code: string): string {
  return code
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:\\])\/\/.*$/gm, '$1')
}

const kebab = (name: string) => name.replace(/([a-z0-9])([A-Z])/g, '$1-$2').replace(/([A-Z])([A-Z][a-z])/g, '$1-$2').toLowerCase()

/** 生产代码里引用了该组件：import 路径以 `/Name` 或 `/Name.vue` 结尾，或模板标签 `<Name` / `<name-kebab` */
function isReferenced(name: string, code: string): boolean {
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`['"\`][^'"\`]*/${esc}(\\.vue)?['"\`]`).test(code)
    || new RegExp(`<${esc}[\\s/>]`).test(code)
    || new RegExp(`<${kebab(name)}[\\s/>]`).test(code)
}

/** files：{相对路径: 源码}；返回没有任何其他生产文件引用的组件（相对路径） */
function findUnmounted(components: string[], files: Record<string, string>): string[] {
  const prod = Object.entries(files)
    .filter(([r]) => !isTestOrGenerated(r))
    .map(([r, code]) => [r, stripComments(code)] as const)
  return components.filter((c) => {
    const name = c.split('/').pop()!.replace(/\.vue$/, '')
    return !prod.some(([r, code]) => r !== c && isReferenced(name, code))
  })
}

describe('公式组件都被生产代码挂载', () => {
  const all = walk(SRC).filter((p) => /\.(vue|ts|tsx|js)$/.test(p))
  const files = Object.fromEntries(all.map((p) => [rel(p), readFileSync(p, 'utf-8')]))
  const components = walk(FORMULA_DIR).map(rel).filter((r) => r.endsWith('.vue') && !isTestOrGenerated(r))

  it('扫描面非空（防「扫描目录写错 ⇒ 0 个组件 ⇒ 恒绿」）', () => {
    expect(components.length).toBeGreaterThan(30)
    expect(components).toContain('components/formula/FormulaManagerDialog.vue')
    expect(components).toContain('components/formula/settings/FormulaSettingsToolbar.vue')
    expect(Object.keys(files)).toContain('layouts/ThreeColumnLayout.vue')
  })

  it('🔴 components/formula 下没有未挂载的组件', () => {
    expect(findUnmounted(components, files)).toEqual([])
  })
})

describe('判据自检（双向）', () => {
  const C = 'components/formula/GtDemoPanel.vue'
  const host = (code: string) => ({ [C]: '<template><div /></template>', 'views/Host.vue': code })

  it('import 路径 / PascalCase 标签 / kebab 标签 / 异步 import 都算引用', () => {
    for (const code of [
      "import GtDemoPanel from '@/components/formula/GtDemoPanel.vue'",
      "import GtDemoPanel from './GtDemoPanel'",
      '<template><GtDemoPanel :a="1" /></template>',
      '<template><gt-demo-panel></gt-demo-panel></template>',
      "const X = defineAsyncComponent(() => import('@/components/formula/GtDemoPanel.vue'))",
    ]) {
      expect(findUnmounted([C], host(code)), code).toEqual([])
    }
  })

  it('只在注释 / 测试 / components.d.ts / 自身里出现：不算挂载', () => {
    const cases: Record<string, string>[] = [
      host('// 与 GtDemoPanel 同一模式\n<!-- <GtDemoPanel /> -->\n/* import x from "./GtDemoPanel.vue" */'),
      { [C]: '<GtDemoPanel />', 'components/formula/__tests__/x.spec.ts': "import X from '../GtDemoPanel.vue'" },
      { [C]: '', 'components.d.ts': "GtDemoPanel: typeof import('./components/formula/GtDemoPanel.vue')['default']" },
      { [C]: '', 'stories/x.stories.ts': "import X from '../components/formula/GtDemoPanel.vue'" },
      host('<template><GtDemoPanelExtra /></template>'),
    ]
    for (const files of cases) {
      expect(findUnmounted([C], files)).toEqual([C])
    }
  })

  it('kebab 转换', () => {
    expect(kebab('GtRowNameAlignmentTag')).toBe('gt-row-name-alignment-tag')
    expect(kebab('FormulaBar')).toBe('formula-bar')
  })
})
