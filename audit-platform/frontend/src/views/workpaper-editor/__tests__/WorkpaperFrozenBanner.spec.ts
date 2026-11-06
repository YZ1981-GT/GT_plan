import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'

import WorkpaperFrozenBanner from '../WorkpaperFrozenBanner.vue'

const AlertStub = defineComponent({
  template: '<div data-testid="alert"><slot /></div>',
})

function render(status?: string) {
  return mount(WorkpaperFrozenBanner, {
    props: { status },
    global: { stubs: { ElAlert: AlertStub } },
  })
}

describe('WorkpaperFrozenBanner', () => {
  it.each([
    ['review_passed', '底稿复核通过'],
    ['archived', '底稿已归档'],
  ])('%s 显示只读与新修订指引', (status, label) => {
    const wrapper = render(status)
    expect(wrapper.get('[data-testid="alert"]').text()).toContain(label)
    expect(wrapper.text()).toContain('创建新修订')
  })

  it.each(['draft', 'edit_complete', 'under_review', undefined])('%s 不显示冻结横幅', (status) => {
    expect(render(status).find('[data-testid="alert"]').exists()).toBe(false)
  })
})
