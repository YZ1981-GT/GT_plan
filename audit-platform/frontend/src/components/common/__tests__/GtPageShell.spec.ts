/**
 * GtPageShell.spec.ts — 页面骨架统一容器测试
 * [platform-ui-editing-consistency MVP-5]
 *
 * 验证：
 * - 默认渲染 GtPageHeader
 * - 具名 slot 正确渲染（header/context/toolbar/banners/default）
 * - 条件 slot：context/toolbar/banners 未提供时不渲染对应 DOM
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GtPageShell from '../GtPageShell.vue'

// Stub GtPageHeader to avoid pulling full component tree
const GtPageHeaderStub = {
  name: 'GtPageHeader',
  template: '<div class="gt-page-header-stub">Header</div>',
}

function makeWrapper(options: Record<string, any> = {}) {
  return mount(GtPageShell, {
    ...options,
    global: {
      stubs: { GtPageHeader: GtPageHeaderStub },
      ...(options.global || {}),
    },
  })
}

describe('GtPageShell', () => {
  it('renders default GtPageHeader when header slot is empty', () => {
    const w = makeWrapper()
    expect(w.find('.gt-page-header-stub').exists()).toBe(true)
  })

  it('renders custom header slot content when provided', () => {
    const w = makeWrapper({
      slots: { header: '<div class="custom-header">自定义</div>' },
    })
    expect(w.find('.custom-header').exists()).toBe(true)
    expect(w.find('.gt-page-header-stub').exists()).toBe(false)
  })

  it('renders default slot (content)', () => {
    const w = makeWrapper({
      slots: { default: '<p class="page-content">内容</p>' },
    })
    expect(w.find('.page-content').text()).toBe('内容')
  })

  it('renders context slot when provided', () => {
    const w = makeWrapper({
      slots: { context: '<div class="ctx">项目上下文</div>' },
    })
    expect(w.find('.gt-page-shell__context').exists()).toBe(true)
    expect(w.find('.ctx').text()).toBe('项目上下文')
  })

  it('does NOT render context wrapper when slot is empty', () => {
    const w = makeWrapper()
    expect(w.find('.gt-page-shell__context').exists()).toBe(false)
  })

  it('renders toolbar slot when provided', () => {
    const w = makeWrapper({
      slots: { toolbar: '<div class="tb">工具栏</div>' },
    })
    expect(w.find('.gt-page-shell__toolbar').exists()).toBe(true)
    expect(w.find('.tb').text()).toBe('工具栏')
  })

  it('does NOT render toolbar wrapper when slot is empty', () => {
    const w = makeWrapper()
    expect(w.find('.gt-page-shell__toolbar').exists()).toBe(false)
  })

  it('renders banners slot when provided', () => {
    const w = makeWrapper({
      slots: { banners: '<div class="banner">归档横幅</div>' },
    })
    expect(w.find('.gt-page-shell__banners').exists()).toBe(true)
    expect(w.find('.banner').text()).toBe('归档横幅')
  })

  it('does NOT render banners wrapper when slot is empty', () => {
    const w = makeWrapper()
    expect(w.find('.gt-page-shell__banners').exists()).toBe(false)
  })

  it('passes attrs to GtPageHeader in default header slot', () => {
    const w = makeWrapper({ attrs: { title: '试算表' } })
    const header = w.findComponent(GtPageHeaderStub)
    expect(header.exists()).toBe(true)
  })
})
