/**
 * 底稿工具栏只读时禁用会写底稿的按钮（spec workpaper-multi-window-lock-gaps R2.1）。
 *
 * 原先工具栏没有只读入参：编辑锁在别的窗口时「导入」照样可点，子组件直接调后端导入接口写库。
 * 导出、关联附件（抽屉自己按可编辑控制）、全屏照常可用。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import GtWpToolbar from '../GtWpToolbar.vue'

function buttons(readonly: boolean) {
  const wrapper = mount(GtWpToolbar, { props: { readonly }, global: { plugins: [ElementPlus] } })
  const byText = (text: string) => wrapper.findAll('button').find((b) => b.text().includes(text))!
  return { wrapper, byText }
}

describe('GtWpToolbar 只读', () => {
  it('只读：导入、增行禁用且不发事件；导出、关联附件、全屏可用', async () => {
    const { wrapper, byText } = buttons(true)
    for (const text of ['导入', '增行']) expect(byText(text).attributes('disabled'), text).toBeDefined()
    for (const text of ['导出模板', '导出数据', '关联附件', '全屏']) expect(byText(text).attributes('disabled'), text).toBeUndefined()
    await byText('导入').trigger('click')
    expect(wrapper.emitted('import-data')).toBeUndefined()
  })

  it('可编辑：导入、增行可用并发事件', async () => {
    const { wrapper, byText } = buttons(false)
    expect(byText('导入').attributes('disabled')).toBeUndefined()
    await byText('导入').trigger('click')
    await byText('增行').trigger('click')
    expect(wrapper.emitted('import-data')).toHaveLength(1)
    expect(wrapper.emitted('add-row')).toHaveLength(1)
  })
})
