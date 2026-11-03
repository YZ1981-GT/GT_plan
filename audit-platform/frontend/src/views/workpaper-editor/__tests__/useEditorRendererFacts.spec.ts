/**
 * 编辑器外壳从渲染器拿的两项事实（spec platform-perf-hotspots R4）：侧栏 decision_trace 与编制说明闸门。
 */
import { describe, expect, it } from 'vitest'
import { ref, toRaw } from 'vue'
import type { WorkpaperSheetContext } from '@/composables/useWpRenderer'
import { useEditorRendererFacts, type UniverCatalogFacts } from '../useEditorRendererFacts'

const TRACE_HTML = [{ stage: 'html' }] as any
const TRACE_UNIVER = [{ stage: 'univer' }] as any

function emptyContext(over: Partial<WorkpaperSheetContext> = {}): WorkpaperSheetContext {
  return {
    sheetName: '', sheetCode: null, sheetUid: null, sheetUidNullReason: 'sheet_uid_unavailable',
    host: 'univer', wholeWorkbook: false, ownerEpoch: 1, contextRevision: 0, ...over,
  } as WorkpaperSheetContext
}

function setup() {
  const s = {
    useHtmlRenderer: ref(true),
    wpRendererRef: ref<{ renderConfig?: any; loading?: boolean } | null>(null),
    univerCatalog: ref<UniverCatalogFacts | null>(null),
    univerSheetIdentityReady: ref(false),
    activeSheetContext: ref<WorkpaperSheetContext>(emptyContext()),
  }
  return { s, facts: useEditorRendererFacts(s) }
}

describe('useEditorRendererFacts：侧栏 decision_trace', () => {
  it('HTML 模式读 GtWpRenderer 暴露的配置；渲染器未挂 / 未加载完为 null', () => {
    const { s, facts } = setup()
    expect(facts.sidePanelDecisionTrace.value).toBeNull()
    s.wpRendererRef.value = { renderConfig: null, loading: true }
    expect(facts.sidePanelDecisionTrace.value).toBeNull()
    s.wpRendererRef.value = { renderConfig: { decision_trace: TRACE_HTML }, loading: false }
    // 测试里的 ref 是深层的，读到的是响应式代理：按原始对象比同一性
    expect(toRaw(facts.sidePanelDecisionTrace.value)).toBe(TRACE_HTML)
    // Univer 目录里的值在 HTML 模式不用
    s.univerCatalog.value = { wpCode: 'D2', decisionTrace: TRACE_UNIVER }
    expect(toRaw(facts.sidePanelDecisionTrace.value)).toBe(TRACE_HTML)
  })

  it('Univer 模式读目录请求顺带取到的 decision_trace；目录不可用为 null', () => {
    const { s, facts } = setup()
    s.useHtmlRenderer.value = false
    s.wpRendererRef.value = { renderConfig: { decision_trace: TRACE_HTML }, loading: false }
    expect(facts.sidePanelDecisionTrace.value).toBeNull()
    s.univerCatalog.value = { wpCode: 'D2', decisionTrace: TRACE_UNIVER }
    expect(toRaw(facts.sidePanelDecisionTrace.value)).toBe(TRACE_UNIVER)
    s.univerCatalog.value = { wpCode: 'D2', decisionTrace: null }
    expect(facts.sidePanelDecisionTrace.value).toBeNull()
  })
})

describe('useEditorRendererFacts：编制说明闸门', () => {
  it.each([
    ['sheetName', { sheetName: '底稿目录' }],
    ['sheetCode', { sheetCode: 'D2-1' }],
    ['sheetUid', { sheetUid: 'uid-1' }],
    ['wholeWorkbook', { wholeWorkbook: true }],
  ] as const)('页签上下文有 %s 即放行（不等渲染器 / 目录）', (_name, over) => {
    for (const html of [true, false]) {
      const { s, facts } = setup()
      s.useHtmlRenderer.value = html
      s.wpRendererRef.value = { loading: true }
      s.activeSheetContext.value = emptyContext(over as Partial<WorkpaperSheetContext>)
      expect(facts.guidanceContextReady.value).toBe(true)
    }
  })

  it('HTML 模式没有上下文时等 GtWpRenderer 加载结束（loading 明确为 false）', () => {
    const { s, facts } = setup()
    expect(facts.guidanceContextReady.value).toBe(false) // 渲染器还没挂
    s.wpRendererRef.value = {}
    expect(facts.guidanceContextReady.value).toBe(false) // 未暴露 loading 不算加载完
    s.wpRendererRef.value = { loading: true }
    expect(facts.guidanceContextReady.value).toBe(false)
    s.wpRendererRef.value = { loading: false }
    expect(facts.guidanceContextReady.value).toBe(true) // 拿不到上下文：按整册请求一次
    s.univerSheetIdentityReady.value = false
    expect(facts.guidanceContextReady.value).toBe(true) // Univer 目录状态在 HTML 模式不参与
  })

  it('Univer 模式没有上下文时等目录就绪', () => {
    const { s, facts } = setup()
    s.useHtmlRenderer.value = false
    s.wpRendererRef.value = { loading: false }
    expect(facts.guidanceContextReady.value).toBe(false)
    s.univerSheetIdentityReady.value = true
    expect(facts.guidanceContextReady.value).toBe(true)
  })
})
