/**
 * 附注正文批量写入：预览列表 + 差异弹窗（第二轮复盘 R-21 / R-24 / AC-3.3 / AC-9.1）
 *
 * - 质量标志显示中文、不可用项显示章节标题而非内部 source_id（R-21）；
 * - 高风险章节不能直接勾选，须在差异弹窗逐项核对后采用；
 * - 差异弹窗 v-model 为 boolean（R-24）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NoteTextPreviewList from '@/components/disclosure/NoteTextPreviewList.vue'
import NoteTextDiffDialog from '@/components/disclosure/NoteTextDiffDialog.vue'
import { describeSource } from '@/components/disclosure/noteTextBatchLabels'
import type { PreviewItem } from '@/composables/useNoteTextBatch'

const stubs = {
  'el-dialog': { props: ['modelValue', 'title'], template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-button': {
    props: ['disabled', 'type', 'size', 'link', 'plain'], emits: ['click'],
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  'el-checkbox': {
    props: ['modelValue'], emits: ['change', 'update:modelValue'],
    template: '<label class="el-checkbox"><input type="checkbox" :checked="modelValue" @change="$emit(\'change\', $event.target.checked); $emit(\'update:modelValue\', $event.target.checked)" /><slot /></label>',
  },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-input': { props: ['modelValue', 'size'], template: '<input class="el-input" :value="modelValue" />' },
  'el-select': { template: '<div class="el-select"><slot /></div>' },
  'el-option': { props: ['label'], template: '<span class="el-option">{{ label }}</span>' },
  'el-alert': { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
  'el-radio-group': { props: ['modelValue'], template: '<div class="el-radio-group"><slot /></div>' },
  'el-radio-button': { props: ['value'], template: '<span class="el-radio-button"><slot /></span>' },
}

function item(over: Partial<PreviewItem>): PreviewItem {
  return {
    source_id: 'docx-s1', source_title: '会计期间', target_note_id: 'n1', target_note_section: '四、会计期间',
    target_section_title: '会计期间', match_kind: 'title_exact', evidence: '标题规范化一致「会计期间」', confidence: 'candidate',
    category: 'review', default_selected: false, unavailable_reason: null, before_html: '', before_hash: 'b'.repeat(64),
    proposed_html: '<p>新</p>', proposed_hash: 'p'.repeat(64), append_html: null, append_hash: null,
    expected_updated_at: null, default_mode: 'replace', quality_flags: [], replacements: [], ...over,
  }
}

const REVIEW = item({})
const RISKY = item({ source_id: 'docx-s2', source_title: '公司基本情况', target_note_section: '一、1', target_section_title: '公司基本情况',
  quality_flags: ['source_entity', 'date'], target_note_id: 'n2' })
const UNAVAILABLE = item({ source_id: 'docx-s3', source_title: '某某专项说明', target_note_id: null, target_note_section: null,
  target_section_title: null, category: 'unavailable', unavailable_reason: '未找到匹配的目标章节', confidence: 'manual_required' })

describe('NoteTextPreviewList', () => {
  function mountList(selected: string[] = []) {
    return mount(NoteTextPreviewList, {
      props: { items: [REVIEW, RISKY, UNAVAILABLE], selected, modes: {} },
      global: { stubs },
    })
  }

  it('文案中文、显示章节标题而非内部 source_id', () => {
    const text = mountList().text()
    expect(text).toContain('含来源企业名称')
    expect(text).toContain('含具体日期')
    expect(text).toContain('某某专项说明')
    expect(text).toContain('候选（需人工确认）')
    for (const raw of ['source_entity', 'docx-s3', 'candidate', 'manual_required']) expect(text).not.toContain(raw)
  })

  it('普通需复核项可直接勾选；高风险项只能「核对后采用」', async () => {
    const wrapper = mountList()
    const reviewRow = wrapper.find('[data-source-id="docx-s1"]')
    await reviewRow.find('input[type="checkbox"]').setValue(true)
    expect(wrapper.emitted('update:selected')?.[0]).toEqual([['docx-s1']])
    const riskyRow = wrapper.find('[data-source-id="docx-s2"]')
    expect(riskyRow.find('input[type="checkbox"]').exists()).toBe(false)
    await riskyRow.findAll('button').find(b => b.text() === '核对后采用')!.trigger('click')
    expect(wrapper.emitted('open-diff')?.[0]?.[0]).toMatchObject({ source_id: 'docx-s2' })
  })

  it('「仅看高风险」只留高风险章节（设计 §9.3：只看已选 / 高风险 / 未映射）', async () => {
    const wrapper = mountList()
    const box = wrapper.findAll('label.el-checkbox').find(l => l.text() === '仅看高风险')!
    await box.find('input').setValue(true)
    expect(wrapper.findAll('[data-source-id]').map(r => r.attributes('data-source-id'))).toEqual(['docx-s2'])
  })

  it('来源说明：知识库显示文档名称与版本（AC-5.1），上传显示文件名', () => {
    expect(describeSource('knowledge', { documents: [{ document_name: '政策汇编.md', doc_version: 3 },
      { document_name: '旧制度.md', doc_version: null }] })).toBe('知识库：政策汇编.md（v3）、旧制度.md')
    expect(describeSource('upload', { file_name: '附注.docx' })).toBe('文件：附注.docx')
    expect(describeSource('upload', null)).toBe('')
  })

  it('勾选摘要按选择统计（AC-9.6）', () => {
    expect(mountList(['docx-s1', 'docx-s2']).find('.gt-ntp-summary').text())
      .toContain('已选 2 章：新增 2 · 替换 0 · 追加 0 · 高风险 1 · 未映射 1')
  })
})

describe('NoteTextDiffDialog', () => {
  function mountDiff(over: Partial<PreviewItem> = {}) {
    return mount(NoteTextDiffDialog, {
      props: { modelValue: true, item: item({ ...RISKY, ...over }), mode: 'replace', revokedIds: [], stale: false },
      global: { stubs },
    })
  }

  it('关闭时以 boolean 回写 v-model（R-24）', async () => {
    const wrapper = mountDiff()
    await wrapper.findAll('button').find(b => b.text() === '关闭')!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('高风险须逐项核对后才能采用', async () => {
    const wrapper = mountDiff()
    const adopt = () => wrapper.findAll('button').find(b => b.text() === '采用此章')!
    expect(adopt().attributes('disabled')).toBeDefined()
    await wrapper.find('input[type="checkbox"]').setValue(true)  // 仅 source_entity 属高风险（date 只进需复核）
    expect(adopt().attributes('disabled')).toBeUndefined()
    await adopt().trigger('click')
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toMatchObject({ source_id: 'docx-s2' })
  })

  it('换到另一章节 ⇒ 逐项核对清零（同名风险不得沿用上一章的核对）', async () => {
    const wrapper = mountDiff()
    const adopt = () => wrapper.findAll('button').find(b => b.text() === '采用此章')!
    await wrapper.find('input[type="checkbox"]').setValue(true)
    expect(adopt().attributes('disabled')).toBeUndefined()
    await wrapper.setProps({ item: item({ ...RISKY, source_id: 'docx-s9', target_note_id: 'n9' }) })
    expect(adopt().attributes('disabled')).toBeDefined()
  })

  it('禁用按钮之外再兜底：未逐项核对时即使触发「采用此章」也不发出 confirm', async () => {
    // 不认 disabled 的按钮桩：模拟键盘 / 程序化触发绕过按钮禁用态
    // 必须把 disabled 声明为 prop 吞掉：否则作为 attr 透传到 <button> 上，点击仍被禁用态拦下（首版即因此假绿）
    const loose = { ...stubs, 'el-button': { props: ['disabled', 'type'], emits: ['click'], template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>' } }
    const wrapper = mount(NoteTextDiffDialog, {
      props: { modelValue: true, item: RISKY, mode: 'replace', revokedIds: [], stale: false },
      global: { stubs: loose },
    })
    const adopt = () => wrapper.findAll('button').find(b => b.text() === '采用此章')!
    expect(adopt().attributes('disabled')).toBeUndefined()  // 桩确实没有禁用态，点击能到达 onConfirm
    await adopt().trigger('click')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    await wrapper.find('input[type="checkbox"]').setValue(true)  // 正向对照：核对后同一路径能采用
    await adopt().trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('目标为空时不提供「追加」', () => {
    expect(mountDiff({ append_html: null }).find('.el-radio-group').exists()).toBe(false)
    expect(mountDiff({ append_html: '<p>旧</p><p>新</p>', append_hash: 'a'.repeat(64) }).find('.el-radio-group').exists()).toBe(true)
  })
})
