/**
 * 编辑器首屏底稿详情竞态（spec procedure-chain-hardening-and-java-contracts R1）
 *
 * 真实 utils/http（R11 起同一 GET 在飞时共享、不再取消先发）+ apiProxy（GET 在途共享）+ 假 adapter；
 * 不 mock useEditorMode / useEditorUniver / workpaperApi。复现 Shell（fetchComponentType）与
 * Univer 核心（initUniver）同时取同一底稿详情：修复前 2 发、先发被取消、核心判「底稿文件尚未生成」。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed, defineComponent, h, ref } from 'vue'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn(), setTokens: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn(), push: vi.fn() } }))
vi.mock('@univerjs/presets', () => ({
  createUniver: vi.fn(() => ({
    univerAPI: { createWorkbook: vi.fn(), onCommandExecuted: vi.fn() },
    univer: { dispose: vi.fn() },
  })),
  LocaleType: { ZH_CN: 'zh-CN' },
  mergeLocales: vi.fn((l: any) => l),
}))
vi.mock('@univerjs/preset-sheets-core', () => ({ UniverSheetsCorePreset: vi.fn(() => ({})) }))
vi.mock('@univerjs/preset-sheets-core/lib/locales/zh-CN', () => ({ default: {} }))
vi.mock('@/composables/useWpClassification', () => ({
  useWpClassification: () => ({
    classification: ref(null), componentType: ref('skip'), loading: ref(false), error: ref(null),
    isRealWorkpaper: ref(true), excludeFromArchive: ref(false), load: vi.fn(() => Promise.resolve()),
  }),
}))

const PID = 'p1'
const WID = '12345678-1234-1234-1234-123456789abc'
const DETAIL_URL = `/api/projects/${PID}/working-papers/${WID}`

type Call = { url: string; outcome: 'pending' | 'ok' | 'canceled' }

describe('编辑器首屏底稿详情竞态（真实 GET 去重）', () => {
  let http: any
  let originalAdapter: any
  let calls: Call[]
  let releaseDetail: () => void

  beforeEach(async () => {
    vi.resetModules()
    http = (await import('@/utils/http')).default
    const axiosMod = (await import('axios')).default
    calls = []
    let open!: () => void
    const gate = new Promise<void>((r) => { open = r })
    releaseDetail = open
    originalAdapter = http.defaults.adapter
    http.defaults.adapter = async (config: any) => {
      const url = String(config.url)
      const ok = (data: unknown) => ({ data, status: 200, statusText: 'OK', headers: {}, config })
      if (url === DETAIL_URL) {
        const call: Call = { url, outcome: 'pending' }
        calls.push(call)
        await new Promise<void>((resolve, reject) => {
          const onAbort = () => {
            call.outcome = 'canceled'
            reject(new axiosMod.CanceledError(undefined, undefined, config))
          }
          if (config.signal?.aborted) return onAbort()
          config.signal?.addEventListener?.('abort', onAbort, { once: true })
          gate.then(() => {
            config.signal?.removeEventListener?.('abort', onAbort)
            resolve()
          })
        })
        call.outcome = 'ok'
        return ok({ id: WID, wp_code: 'H1A', wp_name: '固定资产', file_version: 1 })
      }
      if (url.endsWith('/template-file/xlsx-to-json')) {
        return ok({ id: 'wb', sheetOrder: ['s0'], sheets: { s0: { id: 's0', name: 'H1A', rowCount: 5, columnCount: 5, cellData: {} } } })
      }
      return ok({})
    }
  })

  afterEach(() => {
    if (http) http.defaults.adapter = originalAdapter
  })

  async function setup() {
    const { useEditorMode } = await import('@/composables/useEditorMode')
    const { useEditorUniver } = await import('@/composables/useEditorUniver')
    const wpDetail = ref<any>(null)
    const mode = useEditorMode({ wpId: ref(WID), projectId: ref(PID), wpDetail })
    const univer = useEditorUniver({
      containerRef: ref(document.createElement('div')),
      projectId: computed(() => PID),
      wpId: computed(() => WID),
      wpDetail: computed(() => wpDetail.value), // UniverEditorCore 传给它的就是只读 computed
      onDetailLoaded: (d: any) => { wpDetail.value = d }, // Core 转成 update:wpDetail 交回 Shell
      sheetNavFacade: { refresh: vi.fn(), bindUniverApi: vi.fn() } as any,
    } as any)
    return { wpDetail, mode, univer }
  }

  /** 以组件宿主挂 useWpRenderer（它在 onMounted 里发请求）。 */
  async function mountRenderer() {
    const { useWpRenderer } = await import('@/composables/useWpRenderer')
    let state: any
    const Host = defineComponent({
      setup() {
        state = useWpRenderer(ref(WID))
        return () => h('div')
      },
    })
    const wrapper = mount(Host)
    return { wrapper, state }
  }

  it('Shell 与 Univer 核心同时取详情：只发 1 次、不取消、不误报无文件', async () => {
    const { wpDetail, mode, univer } = await setup()
    const shell = mode.fetchComponentType() // Shell onMounted 先发
    const core = univer.initUniver() // 项目元数据先回来、Core 挂载后再发
    await new Promise((r) => setTimeout(r, 0))
    releaseDetail()
    await Promise.all([shell, core])

    expect(calls).toEqual([{ url: DETAIL_URL, outcome: 'ok' }])
    expect(univer.loadErrorState.value).toBeNull()
    expect(wpDetail.value?.wp_code).toBe('H1A')
  })

  it('详情 404（无权 / 已删除 / 不存在）⇒ 请求静默不弹全局提示，编辑器给中性文案（R10）', async () => {
    const { ElMessage } = await import('element-plus')
    const axiosMod = (await import('axios')).default
    http.defaults.adapter = async (config: any) => {
      const response = { data: { code: 404, message: '资源不存在或不可访问' }, status: 404, statusText: 'Not Found', headers: {}, config }
      throw new axiosMod.AxiosError('Request failed with status code 404', 'ERR_BAD_REQUEST', config, null, response as any)
    }
    const { univer } = await setup()
    await univer.initUniver()
    expect(univer.loadErrorState.value).toBe('no_index')
    expect(vi.mocked(ElMessage.error)).not.toHaveBeenCalled()
    expect(vi.mocked(ElMessage.warning)).not.toHaveBeenCalled()
  })

  it('详情 404 时壳的辅助请求也静默：步骤映射（R10）；GtWpRenderer 主路径照旧提示（对照）', async () => {
    const { ElMessage } = await import('element-plus')
    const axiosMod = (await import('axios')).default
    http.defaults.adapter = async (config: any) => {
      const response = { data: { code: 404, message: '资源不存在或不可访问' }, status: 404, statusText: 'Not Found', headers: {}, config }
      throw new axiosMod.AxiosError('Request failed with status code 404', 'ERR_BAD_REQUEST', config, null, response as any)
    }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      const { useStepMapping } = await import('@/composables/useStepMapping')
      await useStepMapping(WID).loadMapping()
      expect(vi.mocked(ElMessage.warning)).not.toHaveBeenCalled()
      expect(vi.mocked(ElMessage.error)).not.toHaveBeenCalled()

      // 对照：GtWpRenderer 的主路径不静默，仍由全局拦截器提示 —— 证明上面的「没提示」不是空转。
      // （壳原先另有一份静默的 render-config 给侧栏 decision_trace，spec platform-perf-hotspots R4 起改读
      //  GtWpRenderer 的配置，壳不再自带实例 —— 由 WorkpaperEditor.chainWiring.spec.ts 钉住。）
      const renderer = await mountRenderer()
      await vi.waitFor(() => expect(renderer.state.loading.value).toBe(false))
      expect(renderer.state.error.value).toBeTruthy()
      expect(vi.mocked(ElMessage.warning)).toHaveBeenCalledTimes(1)
      renderer.wrapper.unmount()
    } finally {
      warn.mockRestore()
    }
  })

  it('同 URL 的另一处独立请求不再取消共享的那一发 ⇒ 三方都就绪（spec platform-performance-residual-findings-closure R11）', async () => {
    const { wpDetail, mode, univer } = await setup()
    const shell = mode.fetchComponentType()
    const core = univer.initUniver()
    await new Promise((r) => setTimeout(r, 0))
    // 页面上另一处直接用 utils/http 取同一详情（如保存后刷新）：原先 GET 去重取消先发的那一发、壳与核心靠重取兜底；
    // 现在同一 GET 在飞时共用、不取消任何一方
    const other = http.get(DETAIL_URL).catch((e: unknown) => e)
    await new Promise((r) => setTimeout(r, 0))
    releaseDetail()
    const [, , otherResult] = await Promise.all([shell, core, other])

    expect(calls.length).toBeGreaterThan(0)
    expect(calls.every((c) => c.outcome === 'ok')).toBe(true)
    expect((otherResult as any)?.data?.wp_code).toBe('H1A')
    expect(univer.loadErrorState.value).toBeNull()
    expect(mode.componentType.value).toBe('univer') // 详情里没有 component_type 时仍按 univer
    expect(wpDetail.value?.wp_code).toBe('H1A')
  })
})
