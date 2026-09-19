/**
 * Runtime Hosts 组件测试
 * Requirements: 2.2, 7.1, 7.3
 */
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import GtWorkpaperRuntimeHosts from '../GtWorkpaperRuntimeHosts.vue'

function mountHosts(projectId = 'project-1') {
  const openDrawer = vi.fn()
  const versionTrailRef = ref<{ openDrawer: () => void } | null>(null)
  const versionToolbar = {
    versionTrailRef,
    openVersionHistory: () => versionTrailRef.value?.openDrawer(),
    scheduleAutoSnapshot: vi.fn(),
    wrapSaveImmediate: vi.fn(),
  }
  const VersionTrailStub = defineComponent({
    name: 'GtWpVersionTrail',
    props: ['workpaperId', 'projectId'],
    setup(_, { expose }) {
      expose({ openDrawer })
      return () => h('div', { class: 'version-host' })
    },
  })
  const ReviewHostStub = defineComponent({
    name: 'GtWpReviewDialogHost',
    setup: () => () => h('div', { class: 'review-host' }),
  })
  const wrapper = mount(GtWorkpaperRuntimeHosts, {
    props: { wpId: 'wp-1', projectId },
    global: {
      provide: { versionToolbar },
      stubs: { GtWpVersionTrail: VersionTrailStub, GtWpReviewDialogHost: ReviewHostStub },
    },
  })
  return { wrapper, openDrawer, versionToolbar }
}

describe('GtWorkpaperRuntimeHosts', () => {
  it('挂载真实复核与版本 Host，并连接 openVersionHistory', async () => {
    const { wrapper, openDrawer, versionToolbar } = mountHosts()
    await nextTick()
    expect(wrapper.find('.review-host').exists()).toBe(true)
    expect(wrapper.find('.version-host').exists()).toBe(true)
    versionToolbar.openVersionHistory()
    expect(openDrawer).toHaveBeenCalledOnce()
    wrapper.unmount()
    expect(versionToolbar.versionTrailRef.value).toBeNull()
  })

  it('上下文缺失时保留复核 Host 且不挂载无效版本 Host', () => {
    const { wrapper } = mountHosts('')
    expect(wrapper.find('.review-host').exists()).toBe(true)
    expect(wrapper.find('.version-host').exists()).toBe(false)
  })
})
