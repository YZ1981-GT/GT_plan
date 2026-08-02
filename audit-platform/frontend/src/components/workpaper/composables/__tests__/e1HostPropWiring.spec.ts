/**
 * e1HostPropWiring.spec.ts — E1 宿主传参守卫
 *
 * 背景（N2 已实证的同款缺陷）：宿主漏传 `:html-data` 给子组件 → 子组件
 * `props.htmlData` 恒 undefined → 四表取数**静默失效**（不崩、不报错，
 * `get_diagnostics` 与 vitest 全绿，只有活体点开才发现取数是空的）。
 *
 * E1 披露 Tab 需要 `html_data.restricted_prefill` 才能做受限资金动态取数，
 * 故这里钉死宿主必须传 `:html-data`。
 *
 * 🔴 源码型断言先 blankComments()：本守卫与被守卫源码的注释里都写着 `:html-data`
 *    字样，不剥离会误判为已传。
 *
 * **Validates: Requirements 11.5, 11.6**
 *
 * spec: e1-four-table-extraction-and-disclosure-alignment (Task 8)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const WP_ROOT = resolve(__dirname, '../..')
const HOST = resolve(WP_ROOT, 'GtE1MonetaryFund.vue')
const DISCLOSURE = resolve(WP_ROOT, 'e1/E1TabDisclosure.vue')

function blankComments(src: string): string {
  const blank = (m: string) => m.replace(/[^\n]/g, ' ')
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[^:])(\/\/[^\n]*)/gm, (_m, pre: string, cmt: string) => pre + blank(cmt))
}

/** 抽取模板里所有 `<E1TabDisclosure ... />` 使用点（含跨行属性）。 */
function disclosureUsages(src: string): string[] {
  const out: string[] = []
  const re = /<E1TabDisclosure\b[\s\S]*?\/>/g
  let m: RegExpExecArray | null
  while ((m = re.exec(src)) !== null) out.push(m[0])
  return out
}

describe('E1 宿主传参', () => {
  const HOST_SRC = blankComments(readFileSync(HOST, 'utf-8'))
  const usages = disclosureUsages(HOST_SRC)

  it('反向自检：确实抓到两个披露 Tab 使用点（上市 + 国企）', () => {
    expect(usages.length).toBe(2)
    expect(usages.some((u) => /variant="listed"/.test(u))).toBe(true)
    expect(usages.some((u) => /variant="soe"/.test(u))).toBe(true)
  })

  it('🔴 每个使用点都必须传 :html-data（漏传 → 受限资金四表取数静默失效）', () => {
    for (const u of usages) {
      const variant = /variant="(\w+)"/.exec(u)?.[1] ?? '?'
      expect(
        /:html-data=/.test(u) || /v-bind="\$props"/.test(u),
        `variant=${variant} 的 E1TabDisclosure 未传 :html-data`,
      ).toBe(true)
    }
  })

  it('每个使用点都必须传 :project-id（否则同步按钮永久 disabled）', () => {
    for (const u of usages) {
      expect(/:project-id=/.test(u) || /v-bind="\$props"/.test(u)).toBe(true)
    }
  })

  it('🔴 每个使用点都必须传 :applicable-standards（漏传 → current_standard 退化成 *_standalone）', () => {
    for (const u of usages) {
      const variant = /variant="(\w+)"/.exec(u)?.[1] ?? '?'
      expect(
        /:applicable-standards=/.test(u) || /v-bind="\$props"/.test(u),
        `variant=${variant} 的 E1TabDisclosure 未传 :applicable-standards`,
      ).toBe(true)
    }
  })

  it('宿主经平台单一入口 useHostApplicableStandards 取准则（不自写取值链）', () => {
    expect(HOST_SRC).toContain('useHostApplicableStandards')
    // 死 fallback：`WorkpaperRuntimeContext` 无 applicableStandards 以外的形状
    expect(HOST_SRC).not.toMatch(/runtime(\s+as\s+any)?\)?\??\.applicableStandards/)
  })

  it('披露组件声明了 htmlData prop', () => {
    const src = blankComments(readFileSync(DISCLOSURE, 'utf-8'))
    expect(src).toMatch(/htmlData\?:/)
  })

  it('🔴 披露组件不得再给 buildE1SyncPayload 传 null 准则', () => {
    const src = blankComments(readFileSync(DISCLOSURE, 'utf-8'))
    expect(src).toContain('buildE1SyncPayload(')
    // 旧缺陷形态：buildE1SyncPayload(variant.value, wpId, null, snapshot)
    expect(src).not.toMatch(/buildE1SyncPayload\([\s\S]{0,120}?,\s*null\s*,/)
    expect(src).toMatch(/buildE1SyncPayload\([\s\S]{0,160}?applicableStandards\.value/)
    expect(src).toContain('useHostApplicableStandards')
  })

  it('披露组件读的是 snake_case 的 restricted_prefill', () => {
    const src = blankComments(readFileSync(DISCLOSURE, 'utf-8'))
    // 后端 render 返回 snake_case；读 camelCase 会静默 undefined（E1 曾踩过
    // props.htmlData.projectContext vs project_context 同款）
    expect(src).toContain('htmlData?.restricted_prefill')
    expect(src).not.toContain('htmlData?.restrictedPrefill')
  })
})
