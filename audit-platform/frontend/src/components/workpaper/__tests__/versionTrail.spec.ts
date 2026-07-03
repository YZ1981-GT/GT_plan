/**
 * useVersionTrail — 单元测试
 *
 * Spec: .kiro/specs/workpaper-version-trail/
 * Task: 15.1
 *
 * 测试范围：
 * - loadVersions 正确请求 API + 填充 versions 数组
 * - createSnapshot 调用后刷新列表
 * - compareDiff 填充 diffResult
 * - rollback 调用确认弹窗 + emit
 * - canRollback 根据角色计算
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// ─── Mock http ───────────────────────────────────────────────────────────────
const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

// ─── Mock element-plus ───────────────────────────────────────────────────────
const mockElMessageBoxConfirm = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: (...args: any[]) => mockElMessageBoxConfirm(...args) },
}))

// ─── Mock stores ─────────────────────────────────────────────────────────────
let mockAuthRole = 'manager'
let mockEffectiveRole: string | null = 'manager'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { role: mockAuthRole },
  }),
}))

vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => ({
    effectiveRole: mockEffectiveRole,
  }),
}))

import { useVersionTrail } from '../composables/useVersionTrail'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createComposable() {
  return useVersionTrail({
    projectId: ref('proj-001'),
    workpaperId: ref('wp-001'),
  })
}

const MOCK_VERSIONS = [
  {
    id: 'v-001',
    snapshot_type: 'manual',
    description: '手动保存',
    change_summary: '新增2项',
    item_count: 10,
    data_size_bytes: 2048,
    user_id: 'u-001',
    user_name: '张三',
    created_at: '2025-06-01T10:00:00Z',
  },
  {
    id: 'v-002',
    snapshot_type: 'auto_sampling',
    description: null,
    change_summary: '抽凭快照',
    item_count: 8,
    data_size_bytes: 1500,
    user_id: 'u-002',
    user_name: '李四',
    created_at: '2025-06-01T09:00:00Z',
  },
]

// ═══════════════════════════════════════════════════════════════════════════════
// loadVersions
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVersionTrail - loadVersions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthRole = 'manager'
    mockEffectiveRole = 'manager'
  })

  it('正确请求 API 并填充 versions 数组', async () => {
    mockGet.mockResolvedValueOnce({
      data: { items: MOCK_VERSIONS, total: 2 },
    })

    const { loadVersions, versions, totalCount, currentPage } = createComposable()
    await loadVersions()

    // 验证 API 调用
    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/proj-001/workpapers/wp-001/versions',
      { params: { page: 1, page_size: 20 } },
    )

    // 验证数据映射
    expect(versions.value).toHaveLength(2)
    expect(versions.value[0].id).toBe('v-001')
    expect(versions.value[0].snapshotType).toBe('manual')
    expect(versions.value[0].description).toBe('手动保存')
    expect(versions.value[0].itemCount).toBe(10)
    expect(versions.value[0].userName).toBe('张三')
    expect(totalCount.value).toBe(2)
    expect(currentPage.value).toBe(1)
  })

  it('传入 page 参数请求指定页', async () => {
    mockGet.mockResolvedValueOnce({
      data: { items: [], total: 25 },
    })

    const { loadVersions, currentPage } = createComposable()
    await loadVersions(2)

    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/proj-001/workpapers/wp-001/versions',
      { params: { page: 2, page_size: 20 } },
    )
    expect(currentPage.value).toBe(2)
  })

  it('API 失败时不抛出异常', async () => {
    mockGet.mockRejectedValueOnce(new Error('网络错误'))

    const { loadVersions, versions } = createComposable()
    await loadVersions()

    expect(versions.value).toHaveLength(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// createSnapshot
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVersionTrail - createSnapshot', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthRole = 'manager'
    mockEffectiveRole = 'manager'
  })

  it('调用后刷新列表', async () => {
    // createSnapshot POST
    mockPost.mockResolvedValueOnce({ data: { id: 'v-new' } })
    // loadVersions(1) 刷新调用
    mockGet.mockResolvedValueOnce({
      data: { items: MOCK_VERSIONS, total: 2 },
    })

    const { createSnapshot, versions } = createComposable()
    await createSnapshot('测试快照')

    // 验证 POST 调用
    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-001/workpapers/wp-001/versions',
      { snapshot_type: 'manual', description: '测试快照' },
    )

    // 验证列表刷新（GET 被调用）
    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/proj-001/workpapers/wp-001/versions',
      { params: { page: 1, page_size: 20 } },
    )
    expect(versions.value).toHaveLength(2)
  })

  it('无描述时 description 为 null', async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 'v-new' } })
    mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } })

    const { createSnapshot } = createComposable()
    await createSnapshot()

    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-001/workpapers/wp-001/versions',
      { snapshot_type: 'manual', description: null },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// compareDiff
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVersionTrail - compareDiff', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthRole = 'manager'
    mockEffectiveRole = 'manager'
  })

  it('填充 diffResult', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        added: [{ item_id: 'item-3', change_type: 'added' }],
        deleted: [{ item_id: 'item-1', change_type: 'deleted' }],
        modified: [{ item_id: 'item-2', change_type: 'modified', field_name: 'conclusion', value_a: 'Y', value_b: 'N' }],
        unchanged_count: 5,
        summary: '新增1项，删除1项，修改1个字段',
      },
    })

    const { compareDiff, diffResult } = createComposable()
    await compareDiff('v-001', 'v-002')

    // 验证 POST 调用
    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-001/workpapers/wp-001/versions/compare',
      { version_a_id: 'v-001', version_b_id: 'v-002' },
    )

    // 验证 diffResult 填充
    expect(diffResult.value).not.toBeNull()
    expect(diffResult.value!.added).toHaveLength(1)
    expect(diffResult.value!.added[0].itemId).toBe('item-3')
    expect(diffResult.value!.deleted).toHaveLength(1)
    expect(diffResult.value!.deleted[0].itemId).toBe('item-1')
    expect(diffResult.value!.modified).toHaveLength(1)
    expect(diffResult.value!.modified[0].fieldName).toBe('conclusion')
    expect(diffResult.value!.modified[0].valueA).toBe('Y')
    expect(diffResult.value!.modified[0].valueB).toBe('N')
    expect(diffResult.value!.unchangedCount).toBe(5)
    expect(diffResult.value!.summary).toBe('新增1项，删除1项，修改1个字段')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// rollback
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVersionTrail - rollback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthRole = 'manager'
    mockEffectiveRole = 'manager'
  })

  it('调用确认弹窗 + 确认后 POST rollback', async () => {
    // 先加载一次使 versions 有数据（rollback 中查找 targetVersion）
    mockGet.mockResolvedValueOnce({ data: { items: MOCK_VERSIONS, total: 2 } })
    const { rollback, loadVersions } = createComposable()
    await loadVersions()
    vi.clearAllMocks()

    // 用户确认弹窗
    mockElMessageBoxConfirm.mockResolvedValueOnce('confirm')
    // rollback POST
    mockPost.mockResolvedValueOnce({ data: { id: 'v-rollback' } })
    // 刷新列表
    mockGet.mockResolvedValueOnce({ data: { items: MOCK_VERSIONS, total: 2 } })

    await rollback('v-001')

    // 验证弹窗被调用
    expect(mockElMessageBoxConfirm).toHaveBeenCalledTimes(1)
    expect(mockElMessageBoxConfirm.mock.calls[0][2]).toMatchObject({
      type: 'warning',
      confirmButtonText: '确定回滚',
    })

    // 验证 rollback POST
    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-001/workpapers/wp-001/versions/v-001/rollback',
    )
  })

  it('用户取消弹窗时不执行 rollback', async () => {
    // 用户取消 — ElMessageBox.confirm 抛出异常代表取消
    mockElMessageBoxConfirm.mockRejectedValueOnce(new Error('cancel'))

    const { rollback } = createComposable()
    await rollback('v-001')

    // 弹窗被调用
    expect(mockElMessageBoxConfirm).toHaveBeenCalledTimes(1)
    // POST 不应被调用（因为用户取消了）
    expect(mockPost).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// canRollback
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVersionTrail - canRollback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('effectiveRole=manager → canRollback=true', () => {
    mockEffectiveRole = 'manager'
    mockAuthRole = 'assistant'
    const { canRollback } = createComposable()
    expect(canRollback.value).toBe(true)
  })

  it('effectiveRole=admin → canRollback=true', () => {
    mockEffectiveRole = 'admin'
    mockAuthRole = 'assistant'
    const { canRollback } = createComposable()
    expect(canRollback.value).toBe(true)
  })

  it('effectiveRole=partner → canRollback=true', () => {
    mockEffectiveRole = 'partner'
    mockAuthRole = 'assistant'
    const { canRollback } = createComposable()
    expect(canRollback.value).toBe(true)
  })

  it('effectiveRole=qc → canRollback=true', () => {
    mockEffectiveRole = 'qc'
    mockAuthRole = 'assistant'
    const { canRollback } = createComposable()
    expect(canRollback.value).toBe(true)
  })

  it('effectiveRole=assistant → canRollback=false', () => {
    mockEffectiveRole = 'assistant'
    mockAuthRole = 'assistant'
    const { canRollback } = createComposable()
    expect(canRollback.value).toBe(false)
  })

  it('effectiveRole=null 时降级到 authStore.user.role', () => {
    mockEffectiveRole = null
    mockAuthRole = 'manager'
    const { canRollback } = createComposable()
    expect(canRollback.value).toBe(true)
  })

  it('effectiveRole=null + authStore.role=assistant → false', () => {
    mockEffectiveRole = null
    mockAuthRole = 'assistant'
    const { canRollback } = createComposable()
    expect(canRollback.value).toBe(false)
  })
})
