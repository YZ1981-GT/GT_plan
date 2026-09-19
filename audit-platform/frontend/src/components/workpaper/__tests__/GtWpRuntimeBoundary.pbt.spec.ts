/**
 * Runtime Boundary component properties P7/P8.
 *
 * **Validates: Requirements 2.1, 2.4, 2.5**
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as fc from 'fast-check'
import { flushPromises, mount, type MountingOptions } from '@vue/test-utils'
import { computed, defineComponent, h, ref, type Component } from 'vue'
import { createPinia } from 'pinia'

const runtimeSpies = vi.hoisted(() => ({
  componentType: 'audit-sheet',
  nestedShell: false,
  versionInit: vi.fn(),
  reviewInit: vi.fn(),
  reload: vi.fn(async () => undefined),
  loadProjectContext: vi.fn(async () => undefined),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}))

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    projectId: 'project-runtime',
    auditYear: 2025,
    year: 2025,
    loadProjectContext: runtimeSpies.loadProjectContext,
  }),
}))
vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: vi.fn(() => true) }),
}))

vi.mock('@/composables/useAgingConfig', async () => {
  const { ref: vueRef } = await import('vue')
  return {
    useAgingConfig: () => ({
      segments: vueRef([]),
      bands: vueRef([]),
      preset: vueRef('FIVE_YEAR'),
      loading: vueRef(false),
      refresh: vi.fn(async () => undefined),
    }),
  }
})

vi.mock('@/components/workpaper/composables/useWorkpaperVersionToolbar', async () => {
  const { ref: vueRef } = await import('vue')
  return {
    useWorkpaperVersionToolbar: (options: unknown) => {
      runtimeSpies.versionInit(options)
      return {
        versionTrailRef: vueRef(null),
        openVersionHistory: vi.fn(),
        scheduleAutoSnapshot: vi.fn(),
        wrapSaveImmediate: <T extends (...args: any[]) => Promise<void>>(fn: T): T => fn,
      }
    },
  }
})

vi.mock('@/components/workpaper/composables/useWorkpaperReviewProvide', () => ({
  useWorkpaperReviewProvide: (options: unknown) => {
    runtimeSpies.reviewInit(options)
    return {
      isOpen: ref(false),
      activationParams: ref(null),
      openReviewDialog: vi.fn(),
      closeReviewDialog: vi.fn(),
    }
  },
}))

vi.mock('@/composables/useWpRenderer', async () => {
  const { computed: vueComputed, ref: vueRef } = await import('vue')
  return {
    useWpRenderer: () => {
      const renderConfig = vueRef({
        wp_id: 'wp-runtime',
        wp_code: 'D2',
        project_id: 'project-runtime',
        scope: 'standalone',
        is_real_workpaper: true,
        template_version: 'test',
        audit_year: 2025,
        sheets: [{
          sheet_name: '测试底稿 D2-1',
          componentType: runtimeSpies.componentType,
          schema: {},
          html_data: {},
          cross_refs: [],
        }],
      })
      return {
        renderConfig,
        loading: vueRef(false),
        error: vueRef(null),
        reload: runtimeSpies.reload,
        componentType: vueComputed(() => runtimeSpies.componentType),
        wpCode: vueComputed(() => 'D2'),
        fillResults: vueComputed(() => null),
        schemaFallbackBanner: vueComputed(() => null),
      }
    },
  }
})

vi.mock('@/components/workpaper/htmlRendererRegistry', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../htmlRendererRegistry')>()
  const { defineComponent: defineVueComponent, h: vueH } = await import('vue')
  const { default: GtWorkpaperShell } = await import('../GtWorkpaperShell.vue')
  const RegistryStandardProbe = defineVueComponent({
    name: 'RegistryStandardProbe',
    props: {
      wpId: { type: String, default: '' },
      projectId: { type: String, default: '' },
      wpCode: { type: String, default: '' },
      year: { type: Number, default: undefined },
    },
    setup(props) {
      return () => vueH('div', { 'data-testid': 'registry-standard-probe' }, [
        runtimeSpies.nestedShell
          ? vueH(GtWorkpaperShell, {
              wpId: props.wpId,
              projectId: props.projectId,
              wpCode: props.wpCode,
              year: props.year,
            }, { default: () => vueH('span', { 'data-testid': 'nested-shell-content' }, '可见') })
          : vueH('span', 'registry content'),
      ])
    },
  })
  return {
    ...actual,
    getRendererEntry: (componentType: string) => {
      const entry = actual.getRendererEntry(componentType)
      return entry ? { ...entry, component: RegistryStandardProbe } : undefined
    },
  }
})

import GtWpRenderer from '../GtWpRenderer.vue'
import GtWorkpaperShell from '../GtWorkpaperShell.vue'
import GtWorkpaperRuntimeHosts from '../GtWorkpaperRuntimeHosts.vue'
import {
  HTML_RENDERER_REGISTRY,
  type HtmlComponentType,
} from '../htmlRendererRegistry'
import { useWorkpaperScaffold } from '../composables/useWorkpaperScaffold'
const VersionHostStub = defineComponent({
  name: 'GtWpVersionTrail',
  template: '<div data-testid="version-host" />',
})
const ReviewHostStub = defineComponent({
  name: 'GtWpReviewDialogHost',
  template: '<div data-testid="review-host" />',
})

const commonStubs: Record<string, Component | boolean> = {
  GtLoadingOverlay: true,
  GtWpPreparationHeader: true,
  GtWpToolbar: true,
  GtBArchitectureTree: true,
  GtGridSheet: true,
  GtOnlyOfficeSheet: true,
  SkippedSheetPlaceholder: true,
  GtWpVersionTrail: VersionHostStub,
  GtWpReviewDialogHost: ReviewHostStub,
  ElAlert: true,
  ElButton: true,
  ElIcon: true,
  ElPopover: true,
  ElResult: true,
  ElTabPane: true,
  ElTabs: true,
}

function mountingOptions(): MountingOptions<any> {
  return {
    global: {
      plugins: [createPinia()],
      stubs: commonStubs,
      directives: { tabWheel: {} },
    },
  }
}

function mountRenderer(componentType: HtmlComponentType, nestedShell = false) {
  runtimeSpies.componentType = componentType
  runtimeSpies.nestedShell = nestedShell
  return mount(GtWpRenderer, {
    props: { wpId: 'wp-runtime' },
    ...mountingOptions(),
  })
}

const standardComponentTypes = [...HTML_RENDERER_REGISTRY.values()]
  .filter((entry) => entry.contextProps === 'standard')
  .map((entry) => entry.componentType)

interface RuntimeHarnessContext {
  wpId: string
  projectId: string
  wpCode: string
  year?: number
}

const NestedShell = defineComponent({
  name: 'NestedShell',
  props: {
    depth: { type: Number, required: true },
    context: { type: Object as () => RuntimeHarnessContext, required: true },
  },
  setup(props) {
    return () => h(GtWorkpaperShell, {
      wpId: props.context.wpId,
      projectId: props.context.projectId,
      wpCode: props.context.wpCode,
      year: props.context.year,
    }, {
      default: () => props.depth > 1
        ? h(NestedShell, { depth: props.depth - 1, context: props.context })
        : h('div', { 'data-testid': 'runtime-business-content' }, '底稿内容'),
    })
  },
})

const RuntimeBoundaryHarness = defineComponent({
  name: 'RuntimeBoundaryHarness',
  props: {
    depth: { type: Number, required: true },
    context: { type: Object as () => RuntimeHarnessContext, required: true },
  },
  setup(props) {
    useWorkpaperScaffold({
      wpId: computed(() => props.context.wpId),
      projectId: computed(() => props.context.projectId),
      wpCode: computed(() => props.context.wpCode),
      year: computed(() => props.context.year),
    })
    return () => h('section', [
      h(GtWorkpaperRuntimeHosts, {
        wpId: props.context.wpId,
        projectId: props.context.projectId,
      }),
      h(NestedShell, { depth: props.depth, context: props.context }),
    ])
  },
})

function mountHarness(context: RuntimeHarnessContext, depth: number) {
  return mount(RuntimeBoundaryHarness, {
    props: { context, depth },
    ...mountingOptions(),
  })
}

beforeEach(() => {
  runtimeSpies.componentType = 'audit-sheet'
  runtimeSpies.nestedShell = false
  runtimeSpies.versionInit.mockClear()
  runtimeSpies.reviewInit.mockClear()
  runtimeSpies.reload.mockClear()
  runtimeSpies.loadProjectContext.mockClear()
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})
describe('Runtime Boundary component properties', () => {
  it('P7: every registry standard componentType initializes exactly one runtime', async () => {
    expect(standardComponentTypes.length).toBeGreaterThan(0)

    fc.assert(
      fc.property(
        fc.shuffledSubarray(standardComponentTypes, {
          minLength: standardComponentTypes.length,
          maxLength: standardComponentTypes.length,
        }),
        (componentTypes) => {
          for (const componentType of componentTypes) {
            const versionBefore = runtimeSpies.versionInit.mock.calls.length
            const reviewBefore = runtimeSpies.reviewInit.mock.calls.length
            const wrapper = mountRenderer(componentType)

            expect(wrapper.find('[data-testid="registry-standard-probe"]').exists()).toBe(true)
            expect(runtimeSpies.versionInit.mock.calls.length - versionBefore).toBe(1)
            expect(runtimeSpies.reviewInit.mock.calls.length - reviewBefore).toBe(1)
            expect(wrapper.findAll('[data-testid="version-host"]')).toHaveLength(1)
            expect(wrapper.findAll('[data-testid="review-host"]')).toHaveLength(1)
            wrapper.unmount()
          }
        },
      ),
      { numRuns: 1 },
    )
  })

  it('P8: missing runtime context degrades without blanking business content', () => {
    const missingContextArb = fc.record({
      wpIdPresent: fc.boolean(),
      projectIdPresent: fc.boolean(),
      wpCodePresent: fc.boolean(),
      yearPresent: fc.boolean(),
      depth: fc.integer({ min: 1, max: 4 }),
    }).filter(({ wpIdPresent, projectIdPresent, wpCodePresent, yearPresent }) =>
      !wpIdPresent || !projectIdPresent || !wpCodePresent || !yearPresent)

    fc.assert(
      fc.property(missingContextArb, (sample) => {
        const versionBefore = runtimeSpies.versionInit.mock.calls.length
        const reviewBefore = runtimeSpies.reviewInit.mock.calls.length
        const wrapper = mountHarness({
          wpId: sample.wpIdPresent ? 'wp-runtime' : '',
          projectId: sample.projectIdPresent ? 'project-runtime' : '',
          wpCode: sample.wpCodePresent ? 'D2' : '',
          year: sample.yearPresent ? 2025 : undefined,
        }, sample.depth)

        expect(wrapper.find('[data-testid="runtime-business-content"]').text()).toBe('底稿内容')
        expect(runtimeSpies.versionInit.mock.calls.length - versionBefore).toBe(1)
        expect(runtimeSpies.reviewInit.mock.calls.length - reviewBefore).toBe(1)
        expect(console.error).toHaveBeenCalledWith(expect.stringContaining('[WorkpaperRuntime]'))
        wrapper.unmount()
      }),
      { numRuns: 5 },
    )
  })

  it('P8: nested Shells reuse the boundary and never add version/review hosts', () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 5 }), (depth) => {
        const versionBefore = runtimeSpies.versionInit.mock.calls.length
        const reviewBefore = runtimeSpies.reviewInit.mock.calls.length
        const wrapper = mountHarness({
          wpId: 'wp-runtime',
          projectId: 'project-runtime',
          wpCode: 'D2',
          year: 2025,
        }, depth)

        expect(wrapper.find('[data-testid="runtime-business-content"]').exists()).toBe(true)
        expect(runtimeSpies.versionInit.mock.calls.length - versionBefore).toBe(1)
        expect(runtimeSpies.reviewInit.mock.calls.length - reviewBefore).toBe(1)
        expect(wrapper.findAll('[data-testid="version-host"]')).toHaveLength(1)
        expect(wrapper.findAll('[data-testid="review-host"]')).toHaveLength(1)
        wrapper.unmount()
      }),
      { numRuns: 5 },
    )
  })

  it('nested Shell rendered by a registry component reuses the Renderer boundary', async () => {
    const wrapper = mountRenderer(standardComponentTypes[0], true)
    await flushPromises()

    expect(wrapper.find('[data-testid="nested-shell-content"]').text()).toBe('可见')
    expect(runtimeSpies.versionInit).toHaveBeenCalledTimes(1)
    expect(runtimeSpies.reviewInit).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('[data-testid="version-host"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="review-host"]')).toHaveLength(1)
    wrapper.unmount()
  })
})
