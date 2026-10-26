/**
 * AuditYearMissingResult —— 底稿页年度缺失 / 读取中 / 读取失败三态
 *
 * 「还没取到」「取失败」都不能说成「未设置审计年度」（后者会让用户去改项目信息，而年度其实填着）。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AuditYearMissingResult from '../AuditYearMissingResult.vue'

const STUBS = {
  'el-result': {
    props: ['title', 'icon'],
    template: '<div class="result" :data-icon="icon"><h3 class="title">{{ title }}</h3>'
      + '<div class="sub"><slot name="sub-title" /></div><div class="extra"><slot name="extra" /></div></div>',
  },
  'el-button': {
    emits: ['click'], // 不声明的话 @click 还会作为原生监听透传到 <button>，一次点击触发两次
    template: '<button class="btn" @click="$emit(\'click\')"><slot /></button>',
  },
}

function mountWith(props: Record<string, unknown>) {
  return mount(AuditYearMissingResult, { props, global: { stubs: STUBS } })
}

describe('AuditYearMissingResult', () => {
  it('读取中：只显示占位，不出现「未设置审计年度」', () => {
    const w = mountWith({ loading: true })
    expect(w.text()).toContain('正在读取项目审计年度')
    expect(w.text()).not.toContain('未设置审计年度')
  })

  it('读取失败：显示失败与重试，不出现「未设置审计年度」', async () => {
    const w = mountWith({ failed: true })
    expect(w.find('.title').text()).toBe('读取项目信息失败')
    expect(w.text()).not.toContain('未设置审计年度')
    const buttons = w.findAll('.btn')
    expect(buttons.map((b) => b.text())).toEqual(['重试', '← 返回'])
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
    expect(w.emitted('back')).toHaveLength(1)
  })

  it('取到项目但没填年度：显示「未设置审计年度」与返回，没有重试', async () => {
    const w = mountWith({})
    expect(w.find('.title').text()).toBe('未设置审计年度')
    const buttons = w.findAll('.btn')
    expect(buttons.map((b) => b.text())).toEqual(['← 返回'])
    await buttons[0].trigger('click')
    expect(w.emitted('back')).toHaveLength(1)
    expect(w.emitted('retry')).toBeUndefined()
  })

  it('读取中优先于失败（重试发出后先回到占位）', () => {
    const w = mountWith({ loading: true, failed: true })
    expect(w.text()).toContain('正在读取项目审计年度')
    expect(w.text()).not.toContain('读取项目信息失败')
  })
})
