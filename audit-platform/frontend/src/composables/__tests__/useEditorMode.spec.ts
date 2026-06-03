/**
 * useEditorMode unit tests - V3 Req 12.1.3
 *
 * Validates behaviour parity with the pre-extraction WorkpaperEditor.vue
 * component_type routing block:
 *  - HTML_COMPONENT_TYPES exact whitelist
 *  - fetchComponentType prefers detail.component_type, then template_metadata, then 'univer'
 *  - fetchComponentType falls back to 'univer' on http error
 *  - useHtmlRenderer = true only when classification loaded + ct in whitelist
 *  - useHtmlRenderer = false when classification empty / not loaded / not in whitelist
 *  - watch on (wp_code, projectId) triggers wpClassification.load() on first run
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref, nextTick, type Ref } from 'vue'

// Mock api proxy before importing the composable.
const apiGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => apiGet(...args),
  },
}))

// Mock useWpClassification so we drive classification state directly without a real network.
const classification = ref<any>(null)
const classificationComponentType = ref<string>('skip')
const classificationLoad = vi.fn(() => Promise.resolve())
vi.mock('@/composables/useWpClassification', () => ({
  useWpClassification: () => ({
    classification,
    componentType: classificationComponentType,
    loading: ref(false),
    error: ref(null),
    isRealWorkpaper: ref(true),
    excludeFromArchive: ref(false),
    load: classificationLoad,
  }),
}))

import { useEditorMode, HTML_COMPONENT_TYPES } from '../useEditorMode'

interface HarnessRefs {
  wpId: Ref<string>
  projectId: Ref<string>
  wpDetail: Ref<any>
}

function withSetup(refs: HarnessRefs) {
  let result!: ReturnType<typeof useEditorMode>
  const Comp = defineComponent({
    setup() {
      result = useEditorMode(refs)
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Comp)
  return { result, wrapper }
}

describe('useEditorMode - HTML_COMPONENT_TYPES allowlist', () => {
  it('contains exactly 12 entries (HTML registry + skip)', () => {
    expect(HTML_COMPONENT_TYPES.size).toBe(12)
  })

  it('includes the documented HTML class types', () => {
    const expected = [
      'a-program-console',
      'b-index',
      'c-note-table',
      'd-form-table',
      'd-form-paragraph',
      'd-form-qa',
      'd-form-confirmation',
      'd-form-review',
      'e-control-test',
      'h-static-doc',
      'custom',
      'skip',
    ]
    for (const ct of expected) {
      expect(HTML_COMPONENT_TYPES.has(ct)).toBe(true)
    }
  })

  it('rejects Univer / unknown types', () => {
    expect(HTML_COMPONENT_TYPES.has('univer')).toBe(false)
    expect(HTML_COMPONENT_TYPES.has('form')).toBe(false)
    expect(HTML_COMPONENT_TYPES.has('hybrid')).toBe(false)
    expect(HTML_COMPONENT_TYPES.has('')).toBe(false)
  })
})

describe('useEditorMode - fetchComponentType', () => {
  beforeEach(() => {
    apiGet.mockReset()
    classification.value = null
    classificationComponentType.value = 'skip'
    classificationLoad.mockClear()
  })

  afterEach(() => {
    apiGet.mockReset()
  })

  it('reads detail.component_type when present', async () => {
    apiGet.mockResolvedValueOnce({ component_type: 'form', wp_code: 'D2-1' })

    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref(null),
    }
    const { result } = withSetup(refs)
    expect(result.componentType.value).toBe('univer')

    await result.fetchComponentType()

    expect(result.componentType.value).toBe('form')
    expect(refs.wpDetail.value).toEqual({ component_type: 'form', wp_code: 'D2-1' })
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('falls back to template_metadata.component_type when detail.component_type missing', async () => {
    apiGet.mockResolvedValueOnce({
      template_metadata: { component_type: 'word' },
      wp_code: 'F2-47',
    })
    const refs: HarnessRefs = {
      wpId: ref('wp-2'),
      projectId: ref('proj-A'),
      wpDetail: ref(null),
    }
    const { result } = withSetup(refs)

    await result.fetchComponentType()

    expect(result.componentType.value).toBe('word')
    expect(refs.wpDetail.value?.template_metadata?.component_type).toBe('word')
  })

  it("falls back to 'univer' when neither field is present", async () => {
    apiGet.mockResolvedValueOnce({ wp_code: 'A1' })
    const refs: HarnessRefs = {
      wpId: ref('wp-3'),
      projectId: ref('proj-A'),
      wpDetail: ref(null),
    }
    const { result } = withSetup(refs)

    await result.fetchComponentType()

    expect(result.componentType.value).toBe('univer')
  })

  it("falls back to 'univer' on http error and does not throw", async () => {
    apiGet.mockRejectedValueOnce(new Error('boom'))
    const refs: HarnessRefs = {
      wpId: ref('wp-4'),
      projectId: ref('proj-A'),
      wpDetail: ref({ wp_code: 'A1', stale: true }),
    }
    const { result } = withSetup(refs)

    // pre-set component_type to something else to confirm reset on error
    result.componentType.value = 'form'

    await expect(result.fetchComponentType()).resolves.toBeUndefined()
    expect(result.componentType.value).toBe('univer')
    // wpDetail should NOT be overwritten on error
    expect(refs.wpDetail.value).toEqual({ wp_code: 'A1', stale: true })
  })
})

describe('useEditorMode - useHtmlRenderer', () => {
  beforeEach(() => {
    apiGet.mockReset()
    classification.value = null
    classificationComponentType.value = 'skip'
    classificationLoad.mockClear()
  })

  it('is false when classification has not loaded yet', async () => {
    classification.value = null
    classificationComponentType.value = 'skip'

    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref({ wp_code: 'D2-1' }),
    }
    const { result } = withSetup(refs)
    await nextTick()

    expect(result.useHtmlRenderer.value).toBe(false)
    expect(result.htmlComponentType.value).toBe('')
  })

  it('is false when classification.classifications array is empty', async () => {
    classification.value = { wp_code: 'D2-1', project_id: 'proj-A', classifications: [] }
    classificationComponentType.value = 'skip'

    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref({ wp_code: 'D2-1' }),
    }
    const { result } = withSetup(refs)
    await nextTick()

    expect(result.useHtmlRenderer.value).toBe(false)
  })

  it('is true when classification loaded and componentType is in HTML_COMPONENT_TYPES', async () => {
    classification.value = {
      wp_code: 'D2-1',
      project_id: 'proj-A',
      classifications: [
        {
          sheet_name: 's1',
          class_code: 'D',
          componentType: 'd-form-table',
          scope: 'standalone',
          is_real_workpaper: true,
          exclude_from_archive: false,
          delegated_module: null,
          has_override: false,
        },
      ],
    }
    classificationComponentType.value = 'd-form-table'

    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref({ wp_code: 'D2-1' }),
    }
    const { result } = withSetup(refs)
    await nextTick()

    expect(result.htmlComponentType.value).toBe('d-form-table')
    expect(result.useHtmlRenderer.value).toBe(true)
  })

  it('is false when classification componentType is NOT in HTML allowlist (e.g. univer / delegate)', async () => {
    classification.value = {
      wp_code: 'F2-47',
      project_id: 'proj-A',
      classifications: [
        {
          sheet_name: 's1',
          class_code: 'F',
          componentType: 'univer',
          scope: 'standalone',
          is_real_workpaper: true,
          exclude_from_archive: false,
          delegated_module: null,
          has_override: false,
        },
      ],
    }
    classificationComponentType.value = 'univer'

    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref({ wp_code: 'F2-47' }),
    }
    const { result } = withSetup(refs)
    await nextTick()

    expect(result.htmlComponentType.value).toBe('')
    expect(result.useHtmlRenderer.value).toBe(false)
  })

  it("recognises the 'skip' placeholder as HTML class", async () => {
    classification.value = {
      wp_code: 'X1',
      project_id: 'proj-A',
      classifications: [
        {
          sheet_name: 's1',
          class_code: null,
          componentType: 'skip',
          scope: 'standalone',
          is_real_workpaper: false,
          exclude_from_archive: true,
          delegated_module: null,
          has_override: false,
        },
      ],
    }
    classificationComponentType.value = 'skip'

    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref({ wp_code: 'X1' }),
    }
    const { result } = withSetup(refs)
    await nextTick()

    expect(result.useHtmlRenderer.value).toBe(true)
  })
})

describe('useEditorMode - classification load on (wp_code, projectId) ready', () => {
  beforeEach(() => {
    apiGet.mockReset()
    classification.value = null
    classificationComponentType.value = 'skip'
    classificationLoad.mockClear()
  })

  it('triggers wpClassification.load() on initial mount when both ready', async () => {
    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref({ wp_code: 'D2-1' }),
    }
    withSetup(refs)
    await nextTick()

    expect(classificationLoad).toHaveBeenCalled()
  })

  it('does NOT trigger load when wp_code is empty', async () => {
    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref(null),
    }
    withSetup(refs)
    await nextTick()

    expect(classificationLoad).not.toHaveBeenCalled()
  })

  it('triggers load when wpDetail later acquires a wp_code', async () => {
    const refs: HarnessRefs = {
      wpId: ref('wp-1'),
      projectId: ref('proj-A'),
      wpDetail: ref<any>(null),
    }
    withSetup(refs)
    await nextTick()
    expect(classificationLoad).not.toHaveBeenCalled()

    refs.wpDetail.value = { wp_code: 'D2-1' }
    await nextTick()

    expect(classificationLoad).toHaveBeenCalled()
  })
})
