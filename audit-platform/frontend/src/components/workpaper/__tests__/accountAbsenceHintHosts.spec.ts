/**
 * H5 油气资产 / H7 生产性生物资产 / M8 一般风险准备宿主：不按「行业」拦截，按科目有无提示
 * （spec trim-followup-residual-findings-closure R1）。
 *
 * 原状（可打红）：H5 / H7 宿主 `inject('projectContext')` 比对行业白名单（平台没有这个上下文，恒放行，
 * 且原来同时挂着 el-empty 拦截）；M8 宿主读恒空的 project_info.industry ⇒ 所有项目整页拦截成
 * 「一般风险准备仅适用金融企业」。现：三处只在渲染返回 accounts_found=false 时顶部挂
 * WpAccountAbsenceHint，正文照常渲染。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { parse } from '@vue/compiler-sfc'
import ElementPlus from 'element-plus'

const hoisted = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: hoisted.get, put: hoisted.put, post: vi.fn() } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ params: {}, query: {} }) }))
vi.mock('../sync/workpaperSyncApi', () => ({ readStoreProjection: vi.fn() }))
vi.mock('../sync/workpaperSyncCapability', () => ({ capabilityForEntry: () => 'bidirectional' }))
vi.mock('../sync/useWorkpaperSyncBridge', async () => {
  const { ref } = await import('vue')
  return {
    WP_BRIDGE_IN_FLIGHT_STATES: [],
    useWorkpaperSyncBridge: () => ({
      mode: ref('html'), state: ref('html_idle'), descriptor: ref(null), dirty: ref(false), canForcesave: ref(false),
      persistMode: vi.fn(), switchToOnlyOffice: vi.fn(), leaveWithoutSaving: vi.fn(), reloadAfterApplied: vi.fn(),
    }),
  }
})
vi.mock('../composables/useWorkpaperReviewThreads', () => ({
  useWorkpaperReviewThreads: () => ({ getThreadDot: vi.fn(), getRowDot: vi.fn() }),
}))

import GtM8GeneralRiskReserve from '../GtM8GeneralRiskReserve.vue'
import WpAccountAbsenceHint from '../shared/WpAccountAbsenceHint.vue'

const WORKPAPER_DIR = resolve(__dirname, '..')

type TemplateNode = { type: number; tag?: string; props?: any[]; children?: TemplateNode[] }

function directive(node: TemplateNode, name: string) {
  return (node.props ?? []).find((p) => p.type === 7 && p.name === name)
}

function boundExpr(node: TemplateNode, arg: string): string | undefined {
  const prop = (node.props ?? []).find((p) => p.type === 7 && p.name === 'bind' && p.arg?.content === arg)
  return prop?.exp?.content
}

/** 宿主模板根容器下：加载占位（v-if）之后的 v-else 分支直接挂提示，提示本身不再被别的条件包住。 */
function hintPlacement(file: string) {
  const { descriptor } = parse(readFileSync(resolve(WORKPAPER_DIR, file), 'utf-8'), { filename: file })
  const rootChildren = (descriptor.template!.ast!.children as TemplateNode[]).filter((n) => n.type === 1)
  expect(rootChildren).toHaveLength(1)
  const branches = (rootChildren[0].children ?? []).filter((n) => n.type === 1)
  const loading = branches[0]
  const elseBranch = branches.find((n) => directive(n, 'else'))
  return {
    branches,
    loadingCondition: directive(loading, 'if')?.exp?.content,
    hint: (elseBranch?.children ?? []).find((n) => n.type === 1 && n.tag === 'WpAccountAbsenceHint'),
    script: descriptor.scriptSetup?.content ?? '',
    template: descriptor.template!.content,
  }
}

describe.each([
  ['GtH5OilGasAssets.vue', 'H', '油气资产'],
  ['GtH7BiologicalAssets.vue', 'H', '生产性生物资产'],
  ['GtM8GeneralRiskReserve.vue', 'M', '一般风险准备'],
])('%s：按科目提示、不按行业拦截', (file, cycle, accountName) => {
  it('加载占位之后只有一个正文分支，提示挂在正文最前', () => {
    const { branches, loadingCondition, hint } = hintPlacement(file)
    expect(loadingCondition).toBe('isLoading')
    expect(branches).toHaveLength(2) // 原 M8 / H5 / H7 中间夹着行业拦截分支（v-else-if）
    expect(hint, '正文分支里没有 WpAccountAbsenceHint').toBeTruthy()
    expect(directive(hint!, 'if')).toBeUndefined()
    expect(boundExpr(hint!, 'accounts-found')).toBe('accountsFound')
    const attrs = Object.fromEntries((hint!.props ?? []).filter((p) => p.type === 6).map((p) => [p.name, p.value?.content]))
    expect(attrs.cycle).toBe(cycle)
    expect(attrs['account-name']).toBe(accountName)
  })

  it('脚本不再读行业，accountsFound 来自渲染返回', () => {
    const { script, template } = hintPlacement(file)
    // 只看代码：注释里说明「原来按行业」不算
    const code = script.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
    for (const banned of ['projectContext', 'industry', 'APPLICABLE_INDUSTRIES', 'FINANCIAL_INDUSTRIES', 'isApplicable', 'isFinancialEntity', 'markNotApplicable']) {
      expect(code, banned).not.toContain(banned)
    }
    expect(template.replace(/<!--[\s\S]*?-->/g, '')).not.toMatch(/industry-guard|行业/)
    expect(code).toContain("typeof props.htmlData?.accounts_found === 'boolean'")
  })
})

describe('GtM8GeneralRiskReserve 挂载', () => {
  beforeEach(() => {
    hoisted.get.mockReset()
    hoisted.put.mockReset()
  })

  function mountM8(htmlData: unknown) {
    return shallowMount(GtM8GeneralRiskReserve, {
      props: { wpId: 'wp-m8', projectId: 'p-m8', sheetName: '底稿目录', htmlData },
      global: { plugins: [ElementPlus], renderStubDefaultSlot: true },
    })
  }

  it.each([
    [false, { accounts_found: false, project_info: { client_name: '某制造企业' } }],
    [true, { accounts_found: true, project_info: { client_name: '某银行股份有限公司' } }],
  ])('accounts_found=%s：提示随渲染返回，正文照常渲染（不再整页拦截）', async (found, htmlData) => {
    const wrapper = mountM8(htmlData)
    await flushPromises()
    expect(wrapper.findComponent(WpAccountAbsenceHint).props('accountsFound')).toBe(found)
    expect(wrapper.find('.industry-guard').exists()).toBe(false)
    expect(wrapper.html()).toContain('wp-id="wp-m8"') // 底稿目录 Tab 渲染了
    expect(hoisted.put).not.toHaveBeenCalled() // 不再有「标记为不适用」写入
  })

  it('没有 htmlData 时从 render-config 取 accounts_found', async () => {
    hoisted.get.mockResolvedValue({ data: { sheets: [{ html_data: { accounts_found: false } }] } })
    const wrapper = mountM8(null)
    await flushPromises()
    expect(hoisted.get).toHaveBeenCalledWith(
      '/api/workpapers/wp-m8/render-config?force_component_type=m8-general-risk-reserve', expect.anything())
    expect(wrapper.findComponent(WpAccountAbsenceHint).props('accountsFound')).toBe(false)
    expect(wrapper.html()).toContain('wp-id="wp-m8"')
  })
})
