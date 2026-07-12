/**
 * WpOpinionCard 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 4.3
 *
 * 测试:
 * 1. 渲染 autosize textarea
 * 2. 输入文本时 emit update:modelValue
 * 3. AI 辅助按钮与复核按钮渲染
 * 4. sectionLabel 映射
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WpOpinionCard from '../WpOpinionCard.vue'

function mountCard(propsData: any, provideData: Record<string, any> = {}) {
  return mount(WpOpinionCard, {
    props: propsData,
    global: {
      plugins: [ElementPlus],
      provide: provideData,
    },
  })
}

describe('WpOpinionCard', () => {
  describe('基础渲染', () => {
    it('渲染 el-card 根容器', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'conclusion',
        wpCode: 'D2',
      })
      expect(wrapper.find('.wp-opinion-card').exists()).toBe(true)
    })

    it('section="conclusion" 时标题为 "审计结论"', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'conclusion',
        wpCode: 'D2',
      })
      expect(wrapper.find('.wp-opinion-card__title').text()).toBe('审计结论')
    })

    it('section="opinion" 时标题为 "审计意见"', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'opinion',
        wpCode: 'F1',
      })
      expect(wrapper.find('.wp-opinion-card__title').text()).toBe('审计意见')
    })

    it('section="audit-description" 时标题为 "审计说明"', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'audit-description',
        wpCode: 'K1',
      })
      expect(wrapper.find('.wp-opinion-card__title').text()).toBe('审计说明')
    })

    it('未知 section 直接使用原始值', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'custom-section',
        wpCode: 'D3',
      })
      expect(wrapper.find('.wp-opinion-card__title').text()).toBe('custom-section')
    })
  })

  describe('textarea', () => {
    it('渲染 textarea 元素', () => {
      const wrapper = mountCard({
        modelValue: '测试内容',
        section: 'conclusion',
        wpCode: 'D2',
      })
      const textarea = wrapper.find('textarea')
      expect(textarea.exists()).toBe(true)
    })

    it('textarea 显示 modelValue 内容', () => {
      const wrapper = mountCard({
        modelValue: '经审计核实，坏账准备计提完整。',
        section: 'conclusion',
        wpCode: 'D2',
      })
      const textarea = wrapper.find('textarea')
      expect((textarea.element as HTMLTextAreaElement).value).toBe('经审计核实，坏账准备计提完整。')
    })

    it('输入文本时 emit update:modelValue', async () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'conclusion',
        wpCode: 'D2',
      })
      const textarea = wrapper.find('textarea')
      await textarea.setValue('新审计结论')
      const emitted = wrapper.emitted('update:modelValue')
      expect(emitted).toBeTruthy()
      expect(emitted![emitted!.length - 1][0]).toBe('新审计结论')
    })

    it('placeholder 包含 sectionLabel', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'conclusion',
        wpCode: 'D2',
      })
      const textarea = wrapper.find('textarea')
      expect((textarea.element as HTMLTextAreaElement).placeholder).toContain('审计结论')
    })
  })

  describe('AI 辅助按钮', () => {
    it('渲染 AI 辅助按钮', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'conclusion',
        wpCode: 'D2',
      })
      const actions = wrapper.find('.wp-opinion-card__actions')
      expect(actions.text()).toContain('AI辅助')
    })

    it('点击 AI 按钮调用 inject 的 generateAiText', async () => {
      const mockGenerate = vi.fn().mockResolvedValue('AI生成的结论')
      const wrapper = mountCard(
        { modelValue: '原始内容', section: 'conclusion', wpCode: 'D2' },
        { generateAiText: mockGenerate },
      )
      const aiBtn = wrapper.findAll('.el-button').find(b => b.text().includes('AI辅助'))
      expect(aiBtn).toBeTruthy()
      await aiBtn!.trigger('click')
      // Wait for async
      await new Promise(r => setTimeout(r, 10))
      expect(mockGenerate).toHaveBeenCalledWith('conclusion', '原始内容', '原始内容')
    })

    it('AI 生成成功后 emit update:modelValue', async () => {
      const mockGenerate = vi.fn().mockResolvedValue('AI结论')
      const wrapper = mountCard(
        { modelValue: '', section: 'opinion', wpCode: 'F1' },
        { generateAiText: mockGenerate },
      )
      const aiBtn = wrapper.findAll('.el-button').find(b => b.text().includes('AI辅助'))
      await aiBtn!.trigger('click')
      await new Promise(r => setTimeout(r, 10))
      const emitted = wrapper.emitted('update:modelValue')
      expect(emitted).toBeTruthy()
      expect(emitted![emitted!.length - 1][0]).toBe('AI结论')
    })
  })

  describe('复核按钮', () => {
    it('渲染复核按钮', () => {
      const wrapper = mountCard({
        modelValue: '',
        section: 'conclusion',
        wpCode: 'D2',
      })
      const actions = wrapper.find('.wp-opinion-card__actions')
      expect(actions.text()).toContain('复核')
    })

    it('点击复核按钮调用 inject 的 openReviewDialog', async () => {
      const mockReview = vi.fn()
      const wrapper = mountCard(
        { modelValue: '', section: 'conclusion', wpCode: 'D2' },
        { openReviewDialog: mockReview },
      )
      const reviewBtn = wrapper.findAll('.el-button').find(b => b.text().includes('复核'))
      expect(reviewBtn).toBeTruthy()
      await reviewBtn!.trigger('click')
      expect(mockReview).toHaveBeenCalledWith('conclusion')
    })
  })
})
