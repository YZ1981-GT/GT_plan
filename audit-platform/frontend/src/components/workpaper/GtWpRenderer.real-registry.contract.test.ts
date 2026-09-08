import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { flushPromises, mount } from '@vue/test-utils'
import { defineAsyncComponent, defineComponent, h, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WpComponentType } from '@/types/componentCapabilities.generated'
import type { RenderConfigWire } from '@/types/renderConfig'
import type { HtmlRendererEntry } from './registry/types'

const { scaffoldSpy } = vi.hoisted(() => ({
  scaffoldSpy: vi.fn(),
}))

vi.mock('@/components/workpaper/composables/useWorkpaperScaffold', () => ({
  useWorkpaperScaffold: scaffoldSpy,
}))
vi.mock('@/composables/useWpRenderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useWpRenderer')>()
  return { ...actual, useWpRenderer: vi.fn() }
})
vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: vi.fn() }),
}))
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    projectId: 'project-redacted',
    auditYear: 2026,
    year: 2026,
    loadProjectContext: vi.fn(),
  }),
}))

import { useWpRenderer } from '@/composables/useWpRenderer'
import {
  assertUniqueRegistryComponentTypes as assertUniqueLegacyRegistry,
  getRendererEntry,
  HTML_RENDERER_REGISTRY,
} from './htmlRendererRegistry'
import {
  assertUniqueRegistryComponentTypes as assertUniqueBarrelRegistry,
  REGISTRY_LIST as BARREL_REGISTRY_LIST,
} from './registry'
import GtWpRenderer from './GtWpRenderer.vue'

const GOLDEN_PATH = resolve(
  process.cwd(),
  '..',
  '..',
  'backend',
  'tests',
  'fixtures',
  'platform_architecture',
  'render_config_wire_golden.json',
)

const MANIFEST_PATH = resolve(
  process.cwd(),
  '..',
  '..',
  'backend',
  'app',
  'data',
  'component_capabilities.json',
)

interface GoldenSample {
  wp_code: string
  component_types: string[]
  sheet_fields: string[]
  categories?: string[]
}

function loadGolden(): { source: string; samples: GoldenSample[] } {
  const golden = JSON.parse(readFileSync(GOLDEN_PATH, 'utf-8')) as {
    source: string
    samples: GoldenSample[]
  }
  expect(golden.source).toBe('live_database_production_render_path')
  return golden
}

function loadLiveStaticDocComponentType(): WpComponentType {
  const golden = loadGolden()
  const sample = golden.samples.find((item) => item.wp_code === 'B50-1')
  expect(sample).toBeDefined()
  expect(sample?.component_types).toContain('h-static-doc')
  return 'h-static-doc'
}

function loadLiveConfirmationComponentType(): WpComponentType {
  const golden = loadGolden()
  const sample = golden.samples.find((item) => item.wp_code === 'D0')
  expect(sample).toBeDefined()
  expect(sample?.categories).toContain('confirmation')
  expect(sample?.component_types).toContain('confirmation-summary')
  return 'confirmation-summary'
}

function makeLiveShapePayload(
  componentType: string,
  overrides: Partial<RenderConfigWire> & {
    sheet_name?: string
    html_data?: Record<string, unknown>
    schema?: Record<string, unknown>
  } = {},
): RenderConfigWire {
  const sheetName = overrides.sheet_name ?? '相关资源'
  const { sheet_name: _sn, html_data: htmlData, schema: schemaOverride, ...top } = overrides
  return {
    wp_id: 'wp-redacted',
    wp_code: 'B50-1',
    project_id: 'project-redacted',
    scope: 'standalone',
    is_real_workpaper: true,
    template_version: null,
    audit_year: 2026,
    applicable_standards: [],
    fill_results: {},
    guidance: null,
    sheets: [
      {
        sheet_name: sheetName,
        sheet_code: null,
        sheet_code_reason: 'no_canonical_code',
        whole_workbook: false,
        componentType: componentType as WpComponentType,
        schema: schemaOverride ?? { title: sheetName },
        html_data: htmlData ?? { content: '# 相关资源\n\n真实库 shape 脱敏挂载样本。' },
        cross_refs: [],
        sheet_type: null,
        field_sources: null,
      },
    ],
    ...top,
  }
}

/**
 * Core/forms 代表集：真实 REGISTRY 声明可达，且适合 Vitest 经 GtWpRenderer 轻量挂载。
 * 过重叶移入 MOUNT_UNIT_EXEMPTIONS，勿与本列表重叠。
 */
const MOUNT_BATCH_SAMPLE_TYPES = Object.freeze([
  'h-static-doc',
  'b-index',
  'checklist-table',
  'a17-summary',
  'review-checklist',
  'analytical-review',
  'd-form-table',
  'd-form-paragraph',
  'd-form-qa',
  'd-form-confirmation',
  'd-form-review',
] as const)

/**
 * 单元测试免挂载：confirmation Teleport/重 SFC、OnlyOffice/Word 绑定叶等。
 * confirmation-summary 保留 stub 挂载证据，但仍须登记豁免（不在 batch 真挂载路径）。
 */
const MOUNT_UNIT_EXEMPTIONS: Record<string, { owner: string; reason: string }> = Object.freeze({
  'confirmation-summary': {
    owner: 'platform-architecture-convergence/T09',
    reason:
      'Heavy confirmation SFC with Teleport/portals; unit tests use ConfirmationLightStub only, not GtWpRenderer batch.',
  },
  'confirmation-entity-verify': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation leaf with Teleport and multi-step API surface; stub-only in unit Vitest.',
  },
  'confirmation-followup': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation followup SFC with Teleport/drawers; not mountable in lightweight Vitest.',
  },
  'confirmation-diff-reconcile': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation diff reconcile Teleport SFC; exempt from GtWpRenderer unit mount batch.',
  },
  'confirmation-alternative-d05': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative program SFC with Teleport; stub-only outside Playwright.',
  },
  'confirmation-alternative-d06': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative program SFC with Teleport; stub-only outside Playwright.',
  },
  'confirmation-diff-checklist': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation checklist Teleport SFC; not in lightweight GtWpRenderer mount batch.',
  },
  'confirmation-fraud-risk': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation fraud-risk Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-reliability': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation reliability Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-wealth-list': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation wealth-list Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-send-list-e03': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation send-list Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-send-list-e04': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation send-list Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-send-list-e05': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation send-list Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-alternative-f05': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-alternative-f06': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-alternative-g06': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-alternative-h05': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-alternative-k05': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-alternative-k06': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-alternative-l05': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation alternative Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-diff-securities': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation securities diff Teleport SFC; exempt from unit mount batch.',
  },
  'confirmation-diff-nonsecurities': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Heavy confirmation non-securities diff Teleport SFC; exempt from unit mount batch.',
  },
  'word-template': {
    owner: 'platform-architecture-convergence/T09',
    reason: 'OnlyOffice/Word-bound editor host; cannot mount document kernel in Vitest unit tests.',
  },
  custom: {
    owner: 'platform-architecture-convergence/T09',
    reason: 'Custom workpaper editor bound to OnlyOffice/Univer kernel; too heavy for Vitest unit mounts.',
  },
})

/** confirmation-* 真实叶过重（Teleport 等）；轻量 stub 映射同一 componentType 的宿主根。 */
const ConfirmationLightStub = defineComponent({
  name: 'ConfirmationLightStub',
  props: {
    sheetName: { type: String, default: '' },
  },
  template:
    '<div class="gt-confirmation-summary">' +
    '<div class="gt-confirmation-summary__sheet">{{ sheetName }}</div>' +
    '<div class="gt-confirmation-summary__content">confirmation-light-stub</div>' +
    '</div>',
})

function makePacMountHost(componentType: string) {
  return defineComponent({
    name: `PacMountHost_${componentType}`,
    props: {
      wpId: { type: String, default: '' },
      sheetName: { type: String, default: '' },
      schema: { type: Object, default: () => ({}) },
      htmlData: { type: Object, default: () => ({}) },
      readonly: { type: Boolean, default: false },
      wpCode: { type: String, default: '' },
      formType: { type: String, default: '' },
      projectId: { type: String, default: '' },
      year: { type: [Number, String], default: null },
      wpGenerated: { type: Boolean, default: false },
    },
    setup() {
      return () =>
        h('div', {
          'data-testid': 'pac-mount-host',
          'data-component-type': componentType,
        })
    },
  })
}

/**
 * Keep real REGISTRY declaration; swap only the lazy leaf for unit stability.
 * Still exercises GtWpRenderer → getRendererEntry → async component resolve.
 */
async function withBatchedRegistryLeaf(
  componentType: string,
  run: (entry: HtmlRendererEntry) => Promise<void>,
): Promise<void> {
  const entry = getRendererEntry(componentType)
  expect(entry, `REGISTRY missing declaration for ${componentType}`).toBeDefined()
  const original = entry!.component
  entry!.component = defineAsyncComponent(async () => makePacMountHost(componentType))
  try {
    await run(entry!)
  } finally {
    entry!.component = original
  }
}

function isPlaceholderHost(wrapper: ReturnType<typeof mount>): boolean {
  return (
    wrapper.find('.gt-wp-renderer__unknown-placeholder').exists() ||
    wrapper.find('.gt-wp-renderer__error').exists() ||
    wrapper.find('.gt-skip-placeholder').exists()
  )
}

const ElResultStub = {
  name: 'ElResult',
  props: ['icon', 'title', 'subTitle'],
  template:
    '<div class="el-result-stub" :data-icon="icon">' +
    '<div class="el-result-stub__title">{{ title }}</div>' +
    '<div class="el-result-stub__sub">{{ subTitle }}<slot name="sub-title" /></div>' +
    '</div>',
}

function mountRenderer() {
  return mount(GtWpRenderer, {
    props: { wpId: 'wp-redacted' },
    global: {
      directives: { tabWheel: {}, loading: {} },
      stubs: {
        GtLoadingOverlay: true,
        GtWpPreparationHeader: true,
        GtWpToolbar: true,
        GtWorkpaperRuntimeHosts: true,
        WorkpaperAttachmentsDrawer: true,
        GtBArchitectureTree: true,
        GtOnlyOfficeSheet: true,
        GtGridSheet: true,
        ElAlert: true,
        ElResult: ElResultStub,
        ElButton: true,
        ElPopover: true,
        ElTabs: true,
        ElTabPane: true,
        ElIcon: true,
        ElOption: true,
        ElSelect: true,
        ElTag: true,
        ElSkeleton: true,
        ElEmpty: true,
        ElTooltip: true,
        ElDrawer: true,
        ElDialog: true,
        ElImage: true,
      },
    },
  })
}

describe('GtWpRenderer 真实 registry 挂载契约', () => {
  beforeEach(() => {
    scaffoldSpy.mockReset()
    scaffoldSpy.mockReturnValue({
      version: { openVersionHistory: vi.fn() },
    })
  })

  it('真实库 golden h-static-doc 经真实 registry 挂载真实宿主 DOM', async () => {
    const componentType = loadLiveStaticDocComponentType()
    const renderConfig = ref(makeLiveShapePayload(componentType))
    vi.mocked(useWpRenderer).mockReturnValue({
      renderConfig,
      loading: ref(false),
      error: ref(null),
      reload: vi.fn(),
    } as any)

    expect(getRendererEntry(componentType)).toBeDefined()
    const wrapper = mountRenderer()
    await flushPromises()
    await nextTick()

    await vi.waitFor(() => {
      expect(wrapper.find('.gt-h-static-doc').exists()).toBe(true)
    })
    expect(wrapper.get('.gt-h-static-doc__sheet').text()).toBe('相关资源')
    expect(wrapper.get('.gt-h-static-doc__content').text()).toContain('真实库 shape 脱敏挂载样本')
    wrapper.unmount()
  })

  it('golden confirmation-summary 在真实 registry，并经轻量 stub 挂载宿主根/sheet identity', async () => {
    const componentType = loadLiveConfirmationComponentType()
    const entry = getRendererEntry(componentType)
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('confirmation-summary')
    expect(HTML_RENDERER_REGISTRY.has(componentType)).toBe(true)
    expect(MOUNT_UNIT_EXEMPTIONS[componentType]).toBeDefined()
    expect(MOUNT_UNIT_EXEMPTIONS[componentType]?.reason).toMatch(/Teleport|heavy/i)

    const sheetName = '函证结果汇总表D0-1'
    const wrapper = mount(ConfirmationLightStub, {
      props: { sheetName },
    })
    expect(wrapper.find('.gt-confirmation-summary').exists()).toBe(true)
    expect(wrapper.get('.gt-confirmation-summary__sheet').text()).toBe(sheetName)
    wrapper.unmount()
  })

  it('MOUNT_UNIT_EXEMPTIONS 均在 REGISTRY，含 owner/reason，且与 batch sample 不重叠', () => {
    const sampleSet = new Set<string>(MOUNT_BATCH_SAMPLE_TYPES)
    for (const [componentType, meta] of Object.entries(MOUNT_UNIT_EXEMPTIONS)) {
      expect(
        HTML_RENDERER_REGISTRY.has(componentType as WpComponentType),
        `exemption ${componentType} missing from REGISTRY`,
      ).toBe(true)
      expect(meta.owner.length, `${componentType} owner too short`).toBeGreaterThan(10)
      expect(meta.reason.length, `${componentType} reason too short`).toBeGreaterThan(10)
      expect(sampleSet.has(componentType), `${componentType} listed in both sample and exemptions`).toBe(
        false,
      )
    }
    expect(Object.keys(MOUNT_UNIT_EXEMPTIONS).length).toBeGreaterThan(0)
    expect(MOUNT_UNIT_EXEMPTIONS['confirmation-summary']?.reason).toMatch(/Teleport|heavy/i)
  })

  it('core/forms MOUNT_BATCH_SAMPLE_TYPES 经真实 REGISTRY + GtWpRenderer 轻量挂载', async () => {
    expect(MOUNT_BATCH_SAMPLE_TYPES.length).toBeGreaterThanOrEqual(8)
    expect(MOUNT_BATCH_SAMPLE_TYPES.length).toBeLessThanOrEqual(12)

    for (const componentType of MOUNT_BATCH_SAMPLE_TYPES) {
      expect(
        MOUNT_UNIT_EXEMPTIONS[componentType],
        `${componentType} must not be exempted`,
      ).toBeUndefined()

      await withBatchedRegistryLeaf(componentType, async () => {
        const formType = componentType.startsWith('d-form-')
          ? componentType.slice('d-form-'.length)
          : undefined
        const renderConfig = ref(
          makeLiveShapePayload(componentType, {
            wp_code: `PAC-BATCH-${componentType}`,
            sheet_name: `batch-${componentType}`,
            schema: formType
              ? { title: `batch-${componentType}`, form_type: formType }
              : { title: `batch-${componentType}` },
            html_data: { content: `pac-batch:${componentType}` },
          }),
        )
        vi.mocked(useWpRenderer).mockReturnValue({
          renderConfig,
          loading: ref(false),
          error: ref(null),
          reload: vi.fn(),
        } as any)

        const wrapper = mountRenderer()
        try {
          await flushPromises()
          await nextTick()
          await vi.waitFor(
            () => {
              if (isPlaceholderHost(wrapper)) {
                throw new Error(
                  `${componentType} resolved to unknown/error/skip placeholder instead of host`,
                )
              }
              const host = wrapper.find(
                `[data-testid="pac-mount-host"][data-component-type="${componentType}"]`,
              )
              expect(
                host.exists(),
                `${componentType} async host did not resolve via real REGISTRY entry`,
              ).toBe(true)
            },
            { timeout: 10_000, interval: 50 },
          )
        } finally {
          wrapper.unmount()
        }
      })
    }
  })

  it('Map 构造前的声明序列重复 key 会 fail-closed', () => {
    expect(typeof assertUniqueLegacyRegistry).toBe('function')
    expect(typeof assertUniqueBarrelRegistry).toBe('function')
    // barrel 已在 Map 前对 REGISTRY_LIST 跑过；此处再喂重复序列必须 RED。
    expect(BARREL_REGISTRY_LIST.length).toBeGreaterThan(0)
    expect(() =>
      assertUniqueLegacyRegistry([
        { componentType: 'h-static-doc' },
        { componentType: 'h-static-doc' },
      ] as any),
    ).toThrowError(/htmlRendererRegistry componentType 重复声明: h-static-doc/)
    expect(() =>
      assertUniqueBarrelRegistry([
        { componentType: 'confirmation-summary' },
        { componentType: 'h-static-doc' },
        { componentType: 'confirmation-summary' },
      ] as any),
    ).toThrowError(/confirmation-summary/)
  })

  it('unknown / unsupported(skip) / error 三态有不同可见结果，异常不吞为空数据', async () => {
    const markers: string[] = []

    vi.mocked(useWpRenderer).mockReturnValue({
      renderConfig: ref(null),
      loading: ref(false),
      error: ref({ message: 'render-config boom' }),
      reload: vi.fn(),
    } as any)
    const errorWrapper = mountRenderer()
    await flushPromises()
    expect(errorWrapper.find('.gt-wp-renderer__error').exists()).toBe(true)
    expect(errorWrapper.find('.gt-wp-renderer__unknown-placeholder').exists()).toBe(false)
    expect(errorWrapper.find('.gt-skip-placeholder').exists()).toBe(false)
    expect(errorWrapper.text()).toContain('加载渲染配置失败')
    expect(errorWrapper.text()).toContain('render-config boom')
    markers.push('error')
    errorWrapper.unmount()

    vi.mocked(useWpRenderer).mockReturnValue({
      renderConfig: ref(makeLiveShapePayload('skip', { sheet_name: '占位Sheet' })),
      loading: ref(false),
      error: ref(null),
      reload: vi.fn(),
    } as any)
    const skipWrapper = mountRenderer()
    await flushPromises()
    await nextTick()
    expect(skipWrapper.find('.gt-skip-placeholder').exists()).toBe(true)
    expect(skipWrapper.find('.gt-wp-renderer__error').exists()).toBe(false)
    expect(skipWrapper.find('.gt-wp-renderer__unknown-placeholder').exists()).toBe(false)
    expect(skipWrapper.text()).toContain('占位Sheet')
    markers.push('unsupported')
    skipWrapper.unmount()

    vi.mocked(useWpRenderer).mockReturnValue({
      renderConfig: ref(
        makeLiveShapePayload('not-a-real-component', {
          sheet_name: '未知类型Sheet',
          html_data: { note: 'must-not-look-empty' },
        }),
      ),
      loading: ref(false),
      error: ref(null),
      reload: vi.fn(),
    } as any)
    const unknownWrapper = mountRenderer()
    await flushPromises()
    await nextTick()
    expect(unknownWrapper.find('.gt-wp-renderer__unknown-placeholder').exists()).toBe(true)
    expect(unknownWrapper.find('.gt-wp-renderer__error').exists()).toBe(false)
    expect(unknownWrapper.find('.gt-skip-placeholder').exists()).toBe(false)
    expect(unknownWrapper.text()).toContain('not-a-real-component')
    markers.push('unknown')
    unknownWrapper.unmount()

    expect(new Set(markers).size).toBe(3)
  })

  it('manifest has_frontend_component=true 全部出现在真实 REGISTRY keys（声明↔registry）', () => {
    const manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf-8')) as {
      components: Record<string, { has_frontend_component?: boolean; status?: string }>
    }
    const declared = Object.entries(manifest.components)
      .filter(([, meta]) => meta.has_frontend_component === true)
      .map(([componentType]) => componentType)
      .sort()
    const registryKeys = [...HTML_RENDERER_REGISTRY.keys()].map(String).sort()

    const missingInRegistry = declared.filter((ct) => !registryKeys.includes(ct))
    expect(missingInRegistry, `manifest 声明可挂载但 registry 缺失: ${missingInRegistry.join(', ')}`).toEqual(
      [],
    )
    expect(declared.length).toBeGreaterThan(100)
    expect(registryKeys.length).toBe(declared.length)
  })
})

/**
 * Forms lane literal real mount (T09 follow-on, closes T23 §3 batch item 1).
 *
 * The generic batch above swaps the lazy leaf for a stub host to exercise the
 * async-resolve path. Here we mount the **real** ``GtDForm`` shell (the actual
 * component the 5 ``d-form-*`` registry entries point at), stubbing only its 5
 * heavy sub-components, and assert a real ``.gt-d-form`` root plus correct
 * ``form_type`` branch dispatch — a visible host, not a string stub.
 */
describe('forms lane: 真实 GtDForm 挂载（非 stub host）', () => {
  const FORM_SUB_STUBS = {
    GtDFormTable: { name: 'GtDFormTable', template: '<div class="stub-table" />' },
    GtDFormParagraph: { name: 'GtDFormParagraph', template: '<div class="stub-paragraph" />' },
    GtDFormQA: { name: 'GtDFormQA', template: '<div class="stub-qa" />' },
    GtDFormConfirmation: { name: 'GtDFormConfirmation', template: '<div class="stub-confirmation" />' },
    GtDFormReview: { name: 'GtDFormReview', template: '<div class="stub-review" />' },
  } as const

  const FORM_TYPE_TO_STUB: Record<string, string> = {
    'd-form-table': '.stub-table',
    'd-form-paragraph': '.stub-paragraph',
    'd-form-qa': '.stub-qa',
    'd-form-confirmation': '.stub-confirmation',
    'd-form-review': '.stub-review',
  }

  it('5 个 d-form-* 都指向同一真实 GtDForm 组件引用', () => {
    const references = Object.keys(FORM_TYPE_TO_STUB).map((ct) => getRendererEntry(ct)?.component)
    for (const ref of references) {
      expect(ref, 'd-form-* registry entry missing component').toBeDefined()
    }
    // 5 个子模式共享同一 async 组件引用（forms.ts 的 GtDForm 常量）。
    expect(new Set(references).size).toBe(1)
  })

  it.each(Object.entries(FORM_TYPE_TO_STUB))(
    '%s → 真实 .gt-d-form 根渲染，且分发到对应子模式分支',
    async (componentType, expectedStub) => {
      const formType = componentType.slice('d-form-'.length)
      const { default: GtDForm } = await import('./GtDForm/GtDForm.vue')
      const wrapper = mount(GtDForm as any, {
        props: {
          wpId: 'wp-redacted',
          sheetName: `forms-${componentType}`,
          schema: { form_type: formType, title: `forms-${componentType}` },
          htmlData: { content: `pac-forms:${componentType}` },
          formType: componentType,
        },
        global: {
          directives: { loading: {} },
          stubs: { ...FORM_SUB_STUBS, ElResult: ElResultStub, ElIcon: true, ElButton: true },
        },
      })
      await flushPromises()
      await nextTick()

      // 真实宿主根，不是占位/未知兜底。
      expect(wrapper.find('.gt-d-form').exists(), `${componentType} 未挂载真实 GtDForm 根`).toBe(true)
      expect(wrapper.find('.gt-d-form__unknown').exists(), `${componentType} 落到未识别兜底`).toBe(false)
      // 命中对应子模式分支（其余分支不渲染）。
      expect(wrapper.find(expectedStub).exists(), `${componentType} 未分发到 ${expectedStub}`).toBe(true)
      for (const [ct, stub] of Object.entries(FORM_TYPE_TO_STUB)) {
        if (ct !== componentType) {
          expect(wrapper.find(stub).exists(), `${componentType} 误渲染 ${stub}`).toBe(false)
        }
      }
      wrapper.unmount()
    },
  )
})
