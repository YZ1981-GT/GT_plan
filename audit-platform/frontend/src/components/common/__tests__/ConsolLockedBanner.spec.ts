/**
 * ConsolLockedBanner — 合并锁定横幅组件单测（consol-phase1-arch-lock 需求 4.1/4.2/4.3）
 *
 * 验证：
 * - checkLockStatus 返回 locked=false → 不渲染
 * - 返回包装体 {data:{locked:true}} → 渲染橙色横幅（修复 .data 解包 bug）
 * - 返回已解包 {locked:true} → 渲染（双形态兼容）
 * - 拉取失败 → 不误报锁定（不渲染，与后端 EH4 放行一致）
 * - consol-lock:detected 事件触发刷新
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import ConsolLockedBanner from '../ConsolLockedBanner.vue'

// ─── Mock useAuditContext ───
const mockProjectId = ref('proj-1')
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({
    projectId: computed(() => mockProjectId.value),
    year: computed(() => 2024),
    applicableStandard: computed(() => 'soe'),
    isArchived: computed(() => false),
    canEdit: computed(() => true),
    onContextChange: () => () => {},
  }),
}))

// ─── Mock checkLockStatus ───
const mockCheckLockStatus = vi.fn()
vi.mock('@/services/commonApi', () => ({
  checkLockStatus: (...args: any[]) => mockCheckLockStatus(...args),
}))

// ─── Mock eventBus ───
const handlers: Record<string, ((p: any) => void)[]> = {}
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: (evt: string, cb: (p: any) => void) => { (handlers[evt] ||= []).push(cb) },
    off: (evt: string, cb: (p: any) => void) => { handlers[evt] = (handlers[evt] || []).filter((h) => h !== cb) },
    emit: (evt: string, p: any) => { (handlers[evt] || []).forEach((h) => h(p)) },
  },
}))

describe('ConsolLockedBanner', () => {
  beforeEach(() => {
    mockProjectId.value = 'proj-1'
    mockCheckLockStatus.mockReset()
    Object.keys(handlers).forEach((k) => delete handlers[k])
  })

  it('未锁定（locked=false）时不渲染', async () => {
    mockCheckLockStatus.mockResolvedValue({ code: 200, data: { locked: false } })
    const wrapper = mount(ConsolLockedBanner)
    await flushPromises()
    expect(wrapper.find('.consol-locked-banner').exists()).toBe(false)
  })

  it('包装体 {data:{locked:true}} → 渲染橙色横幅（.data 解包修复）', async () => {
    mockCheckLockStatus.mockResolvedValue({ code: 200, message: 'success', data: { locked: true, locked_by: 'u1' } })
    const wrapper = mount(ConsolLockedBanner)
    await flushPromises()
    expect(wrapper.find('.consol-locked-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('已被合并项目锁定')
  })

  it('已解包 {locked:true} → 同样渲染（双形态兼容）', async () => {
    mockCheckLockStatus.mockResolvedValue({ locked: true })
    const wrapper = mount(ConsolLockedBanner)
    await flushPromises()
    expect(wrapper.find('.consol-locked-banner').exists()).toBe(true)
  })

  it('拉取失败 → 不误报锁定（不渲染，EH4 放行）', async () => {
    mockCheckLockStatus.mockRejectedValue(new Error('network'))
    const wrapper = mount(ConsolLockedBanner)
    await flushPromises()
    expect(wrapper.find('.consol-locked-banner').exists()).toBe(false)
  })

  it('无 projectId → 不调 API 不渲染', async () => {
    mockProjectId.value = ''
    const wrapper = mount(ConsolLockedBanner)
    await flushPromises()
    expect(mockCheckLockStatus).not.toHaveBeenCalled()
    expect(wrapper.find('.consol-locked-banner').exists()).toBe(false)
  })

  it('consol-lock:detected 事件触发刷新锁定态', async () => {
    // 初次未锁定
    mockCheckLockStatus.mockResolvedValueOnce({ data: { locked: false } })
    const wrapper = mount(ConsolLockedBanner)
    await flushPromises()
    expect(wrapper.find('.consol-locked-banner').exists()).toBe(false)

    // 后端 423 → 触发事件 → 刷新拿到锁定态
    mockCheckLockStatus.mockResolvedValueOnce({ data: { locked: true } })
    handlers['consol-lock:detected']?.forEach((h) => h({}))
    await flushPromises()
    expect(wrapper.find('.consol-locked-banner').exists()).toBe(true)
  })
})
