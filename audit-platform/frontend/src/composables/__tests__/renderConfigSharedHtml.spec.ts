/**
 * render-config 共享载荷展开（spec platform-perf-hotspots R1）。
 * 展开结果与不带参数的响应逐页深度相等、页签之间互不共享对象、不改入参；useWpRenderer 带参数并展开。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, reactive, ref } from 'vue'
import { mount } from '@vue/test-utils'
import type { RenderConfig } from '@/types/renderConfig'
import { expandSharedHtmlData } from '../renderConfigSharedHtml'
import { useWpRenderer } from '../useWpRenderer'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api: { get: apiGet } }))

function baseConfig(): RenderConfig {
  const payload = (name: string) => ({
    sheet_name: name,
    project_context: { year: 2025, applicable_standards: ['soe'] },
    responses_snapshot: { 'D2-1-adj-0': { remark: 'x', rows: [{ a: 1 }] } },
  })
  return {
    wp_id: 'wp', wp_code: 'D2', project_id: 'p', scope: 'standalone', is_real_workpaper: true,
    template_version: null, audit_year: 2025,
    sheets: [
      { sheet_name: '底稿目录', componentType: 'b-index' as any, schema: null, html_data: { cells: [] }, cross_refs: [] },
      ...['审定表D2-1', '明细表D2-2', '坏账准备D2-3'].map((name) => ({
        sheet_name: name, componentType: 'd2-accounts-receivable' as any, schema: null,
        html_data: payload(name), cross_refs: [],
      })),
    ],
  }
}

/** 后端 share_duplicated_html_data 的线上形状（同一份共享块 + 页签只留 sheet_name）。 */
function sharedWire(): RenderConfig {
  const base = baseConfig()
  const first = base.sheets[1].html_data as Record<string, any>
  const { sheet_name: _n, ...shared } = first
  return {
    ...base,
    shared_html_data: { h1: shared },
    sheets: base.sheets.map((sheet, index) => index === 0 ? sheet : {
      ...sheet, html_data: { sheet_name: sheet.sheet_name }, html_data_ref: 'h1',
    }),
  }
}

describe('expandSharedHtmlData', () => {
  it('没有共享载荷时原样返回（同一对象）', () => {
    const config = baseConfig()
    expect(expandSharedHtmlData(config)).toBe(config)
  })

  it('展开后与不带参数的响应逐页深度相等，且删掉引用与顶层字段', () => {
    const got = expandSharedHtmlData(sharedWire())
    expect(got).toEqual(baseConfig())
    expect('shared_html_data' in got).toBe(false)
    expect(got.sheets.every((sheet) => !('html_data_ref' in sheet))).toBe(true)
  })

  it('页签之间、页签与共享块之间互不共享对象（原地修改不串页）', () => {
    const wire = sharedWire()
    const got = expandSharedHtmlData(wire)
    const [, a, b] = got.sheets
    ;(a.html_data as any).responses_snapshot['D2-1-adj-0'].rows[0].a = 99
    ;(a.html_data as any).project_context.year = 1999
    expect((b.html_data as any).responses_snapshot['D2-1-adj-0'].rows[0].a).toBe(1)
    expect((b.html_data as any).project_context.year).toBe(2025)
    expect((wire.shared_html_data as any).h1.project_context.year).toBe(2025)
  })

  it('不改入参（apiProxy 在途共享会把同一响应交给多个调用方）', () => {
    const wire = sharedWire()
    const snapshot = structuredClone(wire)
    expandSharedHtmlData(wire)
    expect(wire).toEqual(snapshot)
    expect(expandSharedHtmlData(wire)).toEqual(baseConfig())
  })

  it('页签差异键覆盖共享块同名键', () => {
    const wire = sharedWire()
    ;(wire.shared_html_data as any).h1.sheet_name = '不该出现'
    expect(expandSharedHtmlData(wire).sheets[2].html_data?.sheet_name).toBe('明细表D2-2')
  })

  it('引用缺失是契约错误，直接抛出', () => {
    const wire = sharedWire()
    wire.shared_html_data = {}
    expect(() => expandSharedHtmlData(wire)).toThrow('render-config 共享载荷缺失：h1')
  })

  it('响应式入参也能展开（structuredClone 不接受 Proxy）', () => {
    expect(expandSharedHtmlData(reactive(sharedWire()) as RenderConfig)).toEqual(baseConfig())
  })
})

describe('useWpRenderer 接入共享载荷', () => {
  beforeEach(() => {
    apiGet.mockReset()
  })

  it('请求带 share_html_data=1（写在 URL 里，不加 config）并把展开结果交给下游', async () => {
    apiGet.mockResolvedValueOnce(sharedWire())
    let exposed: ReturnType<typeof useWpRenderer> | null = null
    mount(defineComponent({
      setup() {
        exposed = useWpRenderer(ref('wp-1'))
        return () => h('div')
      },
    }))
    await nextTick()
    await Promise.resolve()
    expect(apiGet).toHaveBeenCalledWith('/api/workpapers/wp-1/render-config?share_html_data=1')
    expect(apiGet.mock.calls[0]).toHaveLength(1) // 不加 config：保留 apiProxy 在途共享
    expect(exposed!.loading.value).toBe(false)
    expect(exposed!.renderConfig.value).toEqual(baseConfig())
  })
})
