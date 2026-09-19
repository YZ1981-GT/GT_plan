/**
 * GtPageShell.spec.ts — 页面骨架统一容器测试
 * [platform-ui-editing-consistency P0-2]
 *
 * 验证：
 * - 默认渲染 GtPageHeader
 * - 具名 slot 正确渲染（header/context/toolbar/banners/default）
 * - 条件 slot：context/toolbar/banners 未提供时不渲染对应 DOM
 * - fullscreen / compact 类名切换
 * - headerProps 透传
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GtPageShell from '../GtPageShell.vue'

// Stub GtPageHeader to avoid pulling full component tree
const GtPageHeaderStub = {
  name: 'GtPageHeader',
  props: ['title', 'showSyncStatus'],
  template: '<div class="gt-page-header-stub">Header: {{ title }}</div>',
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
  // --- 默认 header ---
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

  // --- default slot ---
  it('renders default slot (content)', () => {
    const w = makeWrapper({
      slots: { default: '<p class="page-content">内容</p>' },
    })
    expect(w.find('.page-content').text()).toBe('内容')
  })

  // --- context slot ---
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

  // --- toolbar slot ---
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

  // --- banners slot ---
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

  // --- fullscreen prop ---
  it('applies fullscreen class when fullscreen=true', () => {
    const w = makeWrapper({ props: { fullscreen: true } })
    expect(w.find('.gt-page-shell--fullscreen').exists()).toBe(true)
  })

  it('does NOT apply fullscreen class by default', () => {
    const w = makeWrapper()
    expect(w.find('.gt-page-shell--fullscreen').exists()).toBe(false)
  })

  // --- compact prop ---
  it('applies compact class when compact=true', () => {
    const w = makeWrapper({ props: { compact: true } })
    expect(w.find('.gt-page-shell--compact').exists()).toBe(true)
  })

  // --- headerProps transparent ---
  it('passes headerProps to GtPageHeader in default header slot', () => {
    const w = makeWrapper({
      props: { headerProps: { title: '试算表', showSyncStatus: true } },
    })
    const header = w.findComponent(GtPageHeaderStub)
    expect(header.exists()).toBe(true)
    expect(header.props('title')).toBe('试算表')
  })

  // --- all slots combined ---
  it('renders all slots together correctly', () => {
    const w = makeWrapper({
      slots: {
        context: '<div class="ctx">Context</div>',
        toolbar: '<div class="tb">Toolbar</div>',
        banners: '<div class="bn">Banner</div>',
        default: '<div class="main">Main</div>',
      },
    })
    expect(w.find('.gt-page-shell__context .ctx').exists()).toBe(true)
    expect(w.find('.gt-page-shell__toolbar .tb').exists()).toBe(true)
    expect(w.find('.gt-page-shell__banners .bn').exists()).toBe(true)
    expect(w.find('.gt-page-shell__content .main').exists()).toBe(true)
  })
})
