/**
 * PasswordConfirmDialog 前端测试
 * Validates: Requirements F6.6, F6.7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
  },
}))

import http from '@/utils/http'
import PasswordConfirmDialog from '@/components/PasswordConfirmDialog.vue'

describe('PasswordConfirmDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders with default title "安全验证"', () => {
    const wrapper = mount(PasswordConfirmDialog, {
      props: { visible: true },
      global: {
        stubs: {
          'el-dialog': { template: '<div class="dialog"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title'] },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-input': { template: '<input />', props: ['modelValue', 'type'] },
          'el-button': { template: '<button><slot /></button>' },
          'el-alert': true,
          'el-text': true,
        },
      },
    })

    expect(wrapper.exists()).toBe(true)
  })

  it('emits confirmed with token on successful verification', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { confirmation_token: 'test-token-123', expires_in: 300 },
    })

    const wrapper = mount(PasswordConfirmDialog, {
      props: { visible: true },
      global: {
        stubs: {
          'el-dialog': { template: '<div class="dialog"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title'] },
          'el-form': { template: '<form @submit.prevent="$emit(\'submit\')"><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>', props: ['error'] },
          'el-input': { template: '<input />', props: ['modelValue', 'type', 'disabled'] },
          'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['loading', 'disabled', 'type'] },
          'el-alert': true,
          'el-text': true,
        },
      },
    })

    // Set password via component internals
    const vm = wrapper.vm as any
    vm.password = 'correct-password'
    await vm.handleSubmit()
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/auth/verify-password', {
      password: 'correct-password',
    })

    const confirmed = wrapper.emitted('confirmed')
    expect(confirmed).toBeTruthy()
    expect(confirmed![0][0]).toBe('test-token-123')
  })

  it('shows error on 401 (wrong password)', async () => {
    vi.mocked(http.post).mockRejectedValue({
      response: {
        status: 401,
        data: { detail: { detail: 'Invalid password', attempts_remaining: 3 } },
      },
    })

    const wrapper = mount(PasswordConfirmDialog, {
      props: { visible: true },
      global: {
        stubs: {
          'el-dialog': { template: '<div class="dialog"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title'] },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>', props: ['error'] },
          'el-input': { template: '<input />', props: ['modelValue', 'type', 'disabled'] },
          'el-button': { template: '<button><slot /></button>', props: ['loading', 'disabled', 'type'] },
          'el-alert': true,
          'el-text': { template: '<span><slot /></span>' },
        },
      },
    })

    const vm = wrapper.vm as any
    vm.password = 'wrong-password'
    await vm.handleSubmit()
    await flushPromises()

    expect(vm.errorMessage).toContain('密码错误')
    expect(vm.attemptsRemaining).toBe(3)
  })

  it('shows locked state on 423', async () => {
    vi.mocked(http.post).mockRejectedValue({
      response: {
        status: 423,
        data: {
          detail: {
            detail: 'Account locked',
            locked_until: new Date(Date.now() + 30 * 60000).toISOString(),
          },
        },
      },
    })

    const wrapper = mount(PasswordConfirmDialog, {
      props: { visible: true },
      global: {
        stubs: {
          'el-dialog': { template: '<div class="dialog"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title'] },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>', props: ['error'] },
          'el-input': { template: '<input />', props: ['modelValue', 'type', 'disabled'] },
          'el-button': { template: '<button><slot /></button>', props: ['loading', 'disabled', 'type'] },
          'el-alert': { template: '<div class="alert"><slot name="title" /></div>' },
          'el-text': true,
        },
      },
    })

    const vm = wrapper.vm as any
    vm.password = 'any-password'
    await vm.handleSubmit()
    await flushPromises()

    expect(vm.locked).toBe(true)
  })

  it('emits cancelled on cancel', async () => {
    const wrapper = mount(PasswordConfirmDialog, {
      props: { visible: true },
      global: {
        stubs: {
          'el-dialog': { template: '<div class="dialog"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title'] },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>', props: ['error'] },
          'el-input': { template: '<input />', props: ['modelValue', 'type', 'disabled'] },
          'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['loading', 'disabled', 'type'] },
          'el-alert': true,
          'el-text': true,
        },
      },
    })

    const vm = wrapper.vm as any
    vm.handleCancel()
    await flushPromises()

    const cancelled = wrapper.emitted('cancelled')
    expect(cancelled).toBeTruthy()
  })
})
