/**
 * useWpDetailGuard 单元测试
 *
 * 锚定 spec workpaper-editor-refactor Req 1, Task 1.3
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useWpDetailGuard } from '@/composables/useWpDetailGuard'

// Mock http
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
  },
}))

import http from '@/utils/http'
const mockGet = http.get as ReturnType<typeof vi.fn>

describe('useWpDetailGuard', () => {
  const projectId = ref('11111111-1111-1111-1111-111111111111')
  const wpId = ref('22222222-2222-2222-2222-222222222222')

  beforeEach(() => {
    mockGet.mockReset()
  })

  it('① 无效 wpId（非 UUID 格式）→ state=invalid_id', async () => {
    const badWpId = ref('not-a-uuid')
    const guard = useWpDetailGuard(projectId, badWpId)
    await nextTick()
    await new Promise(r => setTimeout(r, 50))
    expect(guard.state.value).toBe('invalid_id')
    expect(guard.errorMessage.value).toContain('格式不合法')
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('② 200 + 完整 file_path → state=ready', async () => {
    mockGet.mockResolvedValueOnce({
      status: 200,
      data: {
        id: wpId.value,
        wp_code: 'D2',
        wp_name: '应收账款审定表',
        file_path: '/storage/projects/xxx/D2.xlsx',
        status: 'draft',
      },
    })
    const guard = useWpDetailGuard(projectId, wpId)
    await new Promise(r => setTimeout(r, 50))
    expect(guard.state.value).toBe('ready')
    expect(guard.wpDetail.value?.wp_code).toBe('D2')
  })

  it('③ 200 但 file_path 为空 → state=no_file', async () => {
    mockGet.mockResolvedValueOnce({
      status: 200,
      data: {
        id: wpId.value,
        wp_code: 'D2',
        wp_name: '应收账款',
        file_path: null,
        status: 'not_started',
      },
    })
    const guard = useWpDetailGuard(projectId, wpId)
    await new Promise(r => setTimeout(r, 50))
    expect(guard.state.value).toBe('no_file')
    expect(guard.errorMessage.value).toContain('生命周期')
  })

  it('④ 404 + wpId 是 wp_index.id → state=no_file（带索引信息）', async () => {
    mockGet
      .mockResolvedValueOnce({ status: 404, data: { detail: '底稿不存在' } })
      .mockResolvedValueOnce({
        status: 200,
        data: [
          { id: wpId.value, wp_code: 'D2', wp_name: '应收账款', audit_cycle: 'D' },
        ],
      })
    const guard = useWpDetailGuard(projectId, wpId)
    await new Promise(r => setTimeout(r, 100))
    expect(guard.state.value).toBe('no_file')
    expect(guard.wpIndex.value?.wp_code).toBe('D2')
    expect(guard.errorMessage.value).toContain('D2')
  })

  it('⑤ 404 + wpId 不在 wp_index → state=no_index', async () => {
    mockGet
      .mockResolvedValueOnce({ status: 404, data: { detail: '底稿不存在' } })
      .mockResolvedValueOnce({ status: 200, data: [] })
    const guard = useWpDetailGuard(projectId, wpId)
    await new Promise(r => setTimeout(r, 100))
    expect(guard.state.value).toBe('no_index')
    expect(guard.errorMessage.value).toContain('不在当前项目')
  })

  it('⑥ 网络错误 → state=error', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network Error'))
    const guard = useWpDetailGuard(projectId, wpId)
    await new Promise(r => setTimeout(r, 50))
    expect(guard.state.value).toBe('error')
    expect(guard.errorMessage.value).toContain('Network Error')
  })

  it('⑦ wpId 变化自动 refresh', async () => {
    // 第一次：返回 D2
    mockGet.mockResolvedValueOnce({
      status: 200,
      data: { id: wpId.value, wp_code: 'D2', file_path: '/x.xlsx', status: 'draft' },
    })
    const localWpId = ref('22222222-2222-2222-2222-222222222222')
    const guard = useWpDetailGuard(projectId, localWpId)
    await new Promise(r => setTimeout(r, 50))
    expect(guard.state.value).toBe('ready')
    expect(guard.wpDetail.value?.wp_code).toBe('D2')

    // 切换 wpId，下一次调用返回 E1
    mockGet.mockResolvedValueOnce({
      status: 200,
      data: { id: '33333333-3333-3333-3333-333333333333', wp_code: 'E1', file_path: '/y.xlsx', status: 'draft' },
    })
    localWpId.value = '33333333-3333-3333-3333-333333333333'
    await nextTick()
    await new Promise(r => setTimeout(r, 100))
    expect(guard.wpDetail.value?.wp_code).toBe('E1')
  })

  it('⑧ loading computed 正确反映 state', async () => {
    mockGet.mockImplementation(() => new Promise(r => setTimeout(() => r({ status: 200, data: { file_path: '/x' } }), 100)))
    const guard = useWpDetailGuard(projectId, wpId)
    expect(guard.loading.value).toBe(true)
    await new Promise(r => setTimeout(r, 150))
    expect(guard.loading.value).toBe(false)
    expect(guard.state.value).toBe('ready')
  })

  // ⑨ CanceledError 短路：请求去重层 abort 旧请求时，不得弹「加载底稿失败/canceled」假失败屏。
  //   快速切底稿/重进编辑器（如切 sheet 触发新 refresh）会 abort 在飞的详情请求。
  it('⑨ axios CanceledError（message=canceled）→ 保持 loading，不置 error', async () => {
    const canceled: any = new Error('canceled')
    canceled.code = 'ERR_CANCELED'
    canceled.name = 'CanceledError'
    mockGet.mockRejectedValueOnce(canceled)
    const guard = useWpDetailGuard(projectId, wpId)
    await new Promise(r => setTimeout(r, 50))
    // 不落 error 假失败屏；保持 loading（有新请求在路上/交后续收敛）
    expect(guard.state.value).toBe('loading')
    expect(guard.errorMessage.value).toBe('')
  })

  // ⑩ 反向守卫：只认 canceled 三种标记；不带这些标记的普通 abort 文案仍须置 error（防短路过宽）
  it('⑩ 普通错误（无 canceled 标记）仍置 error（反向验证短路不过宽）', async () => {
    mockGet.mockRejectedValueOnce(new Error('ECONNRESET'))
    const guard = useWpDetailGuard(projectId, wpId)
    await new Promise(r => setTimeout(r, 50))
    expect(guard.state.value).toBe('error')
    expect(guard.errorMessage.value).toContain('ECONNRESET')
  })
})
