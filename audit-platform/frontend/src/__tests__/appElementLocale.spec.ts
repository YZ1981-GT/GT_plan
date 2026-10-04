/**
 * App 根组件挂 Element Plus 中文语言包（UI 全中文化）
 *
 * 未配置 locale 时 Element Plus 内置文案默认英文：空表格「No Data」、分页「Go to」、日期面板英文月名等。
 * 全站 el-table 绝大多数没有单独写 empty-text ⇒ 根因在根组件没挂 ElConfigProvider（2026-09-30 实测
 * 公式管理「公式推送」页空表格显示英文 No Data 时发现）。
 *
 * 🔴 两个用例的顺序有意义：Element Plus 的全局配置是模块级单例，首个 ElConfigProvider 挂载后即写入，
 * 之后同文件里不经 App 渲染的组件也会拿到中文 ⇒ 反向对照必须先跑。
 */
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { ElTable, ElTableColumn } from 'element-plus'
import App from '@/App.vue'

const EmptyTable = defineComponent({
  name: 'EmptyTableProbe',
  render: () => h(ElTable, { data: [] }, () => [h(ElTableColumn, { prop: 'a', label: '列' })]),
})

describe('App 根组件 Element Plus 语言包', () => {
  it('反向对照：不经 App 渲染的空表格是英文 No Data（证明判据有区分度）', async () => {
    const w = mount(EmptyTable)
    await flushPromises()
    expect(w.text()).toContain('No Data')
    w.unmount()
  })

  it('经 App 渲染：空表格显示中文「暂无数据」', async () => {
    const w = mount(App, {
      global: { plugins: [createPinia()], components: { RouterView: EmptyTable } },
    })
    await flushPromises()
    expect(w.text()).toContain('暂无数据')
    expect(w.text()).not.toContain('No Data')
    w.unmount()
  })
})
