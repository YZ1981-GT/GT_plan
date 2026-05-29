/**
 * Tests for useWpClassification composable
 *
 * Feature: workpaper-editor-slimdown
 * Task 3.2: 前端验证 useWpClassification 对所有 wp_code 返回有效 componentType（不再 fallback Univer）
 *
 * **Validates: Requirements US-7.8**
 *
 * 验证要点：
 * 1. composable 正确透传后端 componentType，不做本地覆盖
 * 2. A/B/C/D/E 类 wp_code 不会 fallback 到 'univer'
 * 3. 后端返回空/无归类时返回 'skip'（而非 'univer'）
 * 4. F/G 类正确返回 'univer'（设计保留）
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useWpClassification } from '../useWpClassification'

// Mock apiProxy
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/services/apiProxy'
const mockApiGet = vi.mocked(api.get)

// ─── Helper: 构造后端响应 ─────────────────────────────────────────────────────

function makeClassificationResponse(
  wpCode: string,
  componentType: string,
  classCode: string | null = null,
  scope: string = 'standalone',
) {
  return {
    wp_code: wpCode,
    project_id: 'test-project-id',
    classifications: [
      {
        sheet_name: 'Sheet1',
        class_code: classCode,
        componentType,
        scope,
        is_real_workpaper: true,
        delegated_module: null,
        has_override: false,
      },
    ],
  }
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useWpClassification — componentType 透传（无 Univer 兜底）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('A 类 wp_code 返回 a-program-console（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('A1-11', 'a-program-console', 'A-程序表'),
    )

    const wpCode = ref('A1-11')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('a-program-console')
    expect(componentType.value).not.toBe('univer')
  })

  it('B 类 wp_code 返回 b-index（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('B1', 'b-index', 'B-目录'),
    )

    const wpCode = ref('B1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('b-index')
    expect(componentType.value).not.toBe('univer')
  })

  it('C 类 wp_code 返回 c-note-table（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('C1', 'c-note-table', 'C-附注'),
    )

    const wpCode = ref('C1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('c-note-table')
    expect(componentType.value).not.toBe('univer')
  })

  it('D 类 wp_code 返回 d-form-table（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('D2-1', 'd-form-table', 'D-检查表'),
    )

    const wpCode = ref('D2-1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('d-form-table')
    expect(componentType.value).not.toBe('univer')
  })

  it('D 类子路由：函证 → d-form-confirmation', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('D2-3', 'd-form-confirmation', 'D-函证'),
    )

    const wpCode = ref('D2-3')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('d-form-confirmation')
  })

  it('E 类 wp_code 返回 e-control-test（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('E1', 'e-control-test', 'E-控制测试'),
    )

    const wpCode = ref('E1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('e-control-test')
    expect(componentType.value).not.toBe('univer')
  })

  it('F 类 wp_code 正确返回 univer（设计保留）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('F2-21', 'univer', 'F-数据表'),
    )

    const wpCode = ref('F2-21')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('univer')
  })

  it('G 类 wp_code 正确返回 univer（设计保留）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('G1', 'univer', 'G-测算'),
    )

    const wpCode = ref('G1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('univer')
  })

  it('H 类 wp_code 返回 h-static-doc', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('H1', 'h-static-doc', 'H-辅助说明'),
    )

    const wpCode = ref('H1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('h-static-doc')
  })

  it('后端返回空 classifications 时 componentType = skip（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce({
      wp_code: 'X1',
      project_id: 'test-project-id',
      classifications: [],
    })

    const wpCode = ref('X1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('skip')
    expect(componentType.value).not.toBe('univer')
  })

  it('后端请求失败时 componentType = skip（不是 univer）', async () => {
    mockApiGet.mockRejectedValueOnce(new Error('404 Not Found'))

    const wpCode = ref('A1-99')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    // classification is null after error → componentType defaults to 'skip'
    expect(componentType.value).toBe('skip')
    expect(componentType.value).not.toBe('univer')
  })

  it('scope=consolidated 时返回 delegate-consolidation（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('A1', 'a-program-console', 'A-程序表', 'consolidated'),
    )

    const wpCode = ref('A1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('delegate-consolidation')
    expect(componentType.value).not.toBe('univer')
  })

  it('scope=parent_only 时返回 delegate-parent-view（不是 univer）', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('B1', 'b-index', 'B-目录', 'parent_only'),
    )

    const wpCode = ref('B1')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(componentType.value).toBe('delegate-parent-view')
    expect(componentType.value).not.toBe('univer')
  })

  it('wpCode 为空时不发请求，componentType = skip', async () => {
    const wpCode = ref('')
    const projectId = ref('test-project-id')
    const { componentType, load } = useWpClassification(wpCode, projectId)

    await load()

    expect(mockApiGet).not.toHaveBeenCalled()
    expect(componentType.value).toBe('skip')
  })

  it('正确传递 wp_code 和 project_id 参数给后端', async () => {
    mockApiGet.mockResolvedValueOnce(
      makeClassificationResponse('D2A', 'd-form-table', 'D-检查表'),
    )

    const wpCode = ref('D2A')
    const projectId = ref('my-project-123')
    const { load } = useWpClassification(wpCode, projectId)

    await load()

    expect(mockApiGet).toHaveBeenCalledWith('/api/wp-classifications', {
      params: { wp_code: 'D2A', project_id: 'my-project-123' },
    })
  })
})
