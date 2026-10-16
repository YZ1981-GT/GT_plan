/**
 * 附注正文批量写入：预览列表 + 差异弹窗（第二轮复盘 R-21 / R-24 / AC-3.3 / AC-9.1）
 *
 * - 质量标志显示中文、不可用项显示章节标题而非内部 source_id（R-21）；
 * - 高风险章节不能直接勾选，须在差异弹窗逐项核对后采用；
 * - 差异弹窗 v-model 为 boolean（R-24）。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import NoteTextPreviewList from '@/components/disclosure/NoteTextPreviewList.vue'
import NoteTextDiffDialog from '@/components/disclosure/NoteTextDiffDialog.vue'
import {
  canAppend, describeSource, sourceBadgeText, sourceDepths, sourceMatchStatuses, splitMappingTargets,
} from '@/components/disclosure/noteTextBatchLabels'
import type { PreviewItem, TargetSection } from '@/composables/useNoteTextBatch'

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
  'el-select': { props: ['placeholder'], template: '<div class="el-select" :data-placeholder="placeholder"><slot /></div>' },
  'el-option-group': { props: ['label'], template: '<div class="el-option-group" :data-label="label"><slot /></div>' },
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

const REVIEW = item({ target_chapter_title: '重要会计政策、会计估计' })
const RISKY = item({ source_id: 'docx-s2', source_title: '公司基本情况', target_note_section: '一、1', target_section_title: '公司基本情况',
  quality_flags: ['source_entity', 'date'], target_note_id: 'n2', target_chapter_title: '公司基本情况' })
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

  it('类别内按目标所属一级章分组（AC-2.3），同章归一组、保持预览顺序；无目标归「未匹配目标章节」', () => {
    const SAME_CHAPTER = item({ source_id: 'docx-s4', source_title: '记账本位币', target_note_id: 'n4',
      target_note_section: '四、记账本位币', target_chapter_title: '重要会计政策、会计估计' })
    const wrapper = mount(NoteTextPreviewList, {
      props: { items: [REVIEW, RISKY, SAME_CHAPTER, UNAVAILABLE], selected: [], modes: {} }, global: { stubs },
    })
    const chapters = (cls: string) => wrapper.find(`.gt-ntp-${cls}`).findAll('.gt-ntp-chapter').map(c => c.text())
    expect(chapters('review')).toEqual(['重要会计政策、会计估计（2）', '公司基本情况（1）'])
    expect(chapters('unavailable')).toEqual(['未匹配目标章节（1）'])
    expect(wrapper.find('.gt-ntp-review').findAll('[data-source-id]').map(r => r.attributes('data-source-id')))
      .toEqual(['docx-s1', 'docx-s4', 'docx-s2'])
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

  it('左栏来源匹配状态（AC-2.2）：未预览为空；预览项与右栏三分组同口径，被跳过的来源带原因', () => {
    expect(sourceMatchStatuses(null).size).toBe(0)
    const map = sourceMatchStatuses({
      items: [item({ source_id: 'docx-s5', category: 'recommended' }), REVIEW, UNAVAILABLE,
        item({ source_id: 'docx-s6', category: 'unavailable', unavailable_reason: '来源正文为空' })],
      skipped_sources: [{ source_id: 'docx-s7', match_kind: 'folded' }, { source_id: 'docx-s8', match_kind: 'out_of_scope' }],
    })
    expect(Object.fromEntries([...map].map(([k, v]) => [k, `${v.type}:${v.label}:${v.hint}`]))).toEqual({
      'docx-s5': 'success:推荐引用:四、会计期间 会计期间',
      'docx-s1': 'warning:需复核:四、会计期间 会计期间',
      'docx-s3': 'info:未匹配:未找到匹配的目标章节',
      'docx-s6': 'info:不可用:来源正文为空',
      'docx-s7': 'info:已并入上级章节:',
      'docx-s8': 'info:不在可填范围:',
    })
  })

  it('编辑器来源标记（Task 50）：三类来源各自的名称与版本，写入后改过另标，悬停看写入人与模式', () => {
    const base = { application_id: 'a', mode: 'append' as const, source_title: null, applied_at: '2026-10-02T08:00:00',
      applied_by_name: null, modified_after: false }
    expect(sourceBadgeText({ ...base, source_kind: 'upload', file_name: '附注.docx' })).toEqual({
      text: '📄 来自上传文档「附注.docx」', hint: '2026/10/02 批量写入（追加）', modified: false })
    expect(sourceBadgeText({ ...base, source_kind: 'knowledge', modified_after: true,
      documents: [{ document_name: '政策汇编.md', doc_version: 3 }, { document_name: '旧制度.md', doc_version: null }] }).text)
      .toBe('📚 来自知识库「政策汇编.md（v3）、旧制度.md」（之后有修改）')
    expect(sourceBadgeText({ ...base, source_kind: 'content_template', template_name: null, version_no: null }).text)
      .toBe('📋 来自内容模板「未命名模板」')
    // 后端给 UTC：北京时间 10-02 早上 7 点半写入不得显示成 10-01
    vi.stubEnv('TZ', 'Asia/Shanghai')
    try {
      expect(sourceBadgeText({ ...base, source_kind: 'content_template', template_name: '集团模板', version_no: 3,
        mode: 'replace', applied_at: '2026-10-01T23:30:00+00:00', applied_by_name: '审计助理甲' })).toEqual({
        text: '📋 来自内容模板「集团模板」v3', hint: '2026/10/02 审计助理甲 批量写入（替换）', modified: false })
    } finally {
      vi.unstubAllEnvs()
    }
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

  // 第 26 组：后端预演的追加结果 = 现有内容（来源段落已全在现有正文里）⇒ 追加是空写入，后端 apply 422 拒收
  const NO_GAIN = { before_html: '<p>旧</p><p>新</p>', append_html: '<p>旧</p><p>新</p>', append_hash: 'a'.repeat(64) }

  it('追加不会增加内容 ⇒ 不提供「追加」并说明原因（不误报「目标为空」）', () => {
    const wrapper = mountDiff(NO_GAIN)
    expect(wrapper.find('.el-radio-group').exists()).toBe(false)
    expect(wrapper.text()).toContain('追加不会增加内容')
    expect(wrapper.text()).not.toContain('目标章节当前为空')
    expect(canAppend(item(NO_GAIN))).toBe(false)
    expect(canAppend(item({ ...NO_GAIN, append_html: '<p>旧</p><p>新</p><p>补充</p>' }))).toBe(true)
  })

  it('父组件仍传「追加」时按替换显示拟写入内容', () => {
    const wrapper = mount(NoteTextDiffDialog, {
      props: { modelValue: true, item: item({ ...RISKY, ...NO_GAIN }), mode: 'append', revokedIds: [], stale: false },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('拟写入内容（替换后）')
    expect(wrapper.findAll('.gt-ntd-pane')[1].html()).toContain('<p>新</p>')
    expect(wrapper.findAll('.gt-ntd-pane')[1].html()).not.toContain('<p>旧</p>')
  })
})

describe('按章节树定位（第 23 组）', () => {
  function target(id: string, kind: string, sectionId: string | null, parent: string | null = null): TargetSection {
    return { id, note_section: id, section_title: id, section_kind: kind, has_content: false,
      section_id: sectionId, parent_section_id: parent }
  }
  const TARGETS = [
    target('一', 'container', 'ch-01'), target('一、1', 'narrative', 's-01', 'ch-01'),
    target('八', 'container', 'ch-08'), target('八、1', 'account_explanation', 's-08', 'ch-08'),
    target('四、记账基础', 'narrative', null),  // 不在树上：只能当写入节
  ]

  it('手工下拉分两类：有子节点的章作锚点，可写入的节按来源类型（上传只填叙述）', () => {
    const upload = splitMappingTargets(TARGETS, 'upload')
    expect(upload.anchors.map(t => t.id)).toEqual(['一', '八'])
    expect(upload.leaves.map(t => t.id)).toEqual(['一、1', '四、记账基础'])
    expect(splitMappingTargets(TARGETS, 'content_template').leaves.map(t => t.id)).toEqual(['一、1', '八、1', '四、记账基础'])
  })

  it('左栏按树深缩进：章 H1 下节是 H3 也只缩一格；没有上级信息时退回按级别', () => {
    const tree = sourceDepths([
      { source_id: 'c', parent_source_id: null, level: 1 }, { source_id: 'a', parent_source_id: 'c', level: 3 },
      { source_id: 'b', parent_source_id: 'a', level: 4 }])
    expect([...tree]).toEqual([['c', 0], ['a', 1], ['b', 2]])
    expect([...sourceDepths([{ source_id: 'x', level: 2 }, { source_id: 'y', level: 1 }])]).toEqual([['x', 1], ['y', 0]])
  })

  it('左栏状态：已定位到章的来源标绿并带定位说明', () => {
    const map = sourceMatchStatuses({ items: [], skipped_sources: [
      { source_id: 'docx-s1', match_kind: 'anchor', evidence: '已定位到「八 财务报表主要项目注释」，其下小标题在该章内定位' }] })
    expect(map.get('docx-s1')).toEqual({ label: '已定位到章', type: 'success',
      hint: '已定位到「八 财务报表主要项目注释」，其下小标题在该章内定位' })
  })

  it('未定位的有子标题来源：下拉先列目标章（锚点）再列写入章节；无子标题的只列写入章节', () => {
    const anchors = TARGETS.slice(0, 1)
    const leaves = [TARGETS[1]]
    const STRUCTURAL = { ...UNAVAILABLE, source_id: 'docx-s9', source_title: '自定义的章', structural: true,
      unavailable_reason: '一级章里找不到「自定义的章」' }
    const wrapper = mount(NoteTextPreviewList, {
      props: { items: [STRUCTURAL, UNAVAILABLE], selected: [], modes: {}, targets: leaves, anchors },
      global: { stubs },
    })
    const groups = (sid: string) => wrapper.find(`[data-source-id="${sid}"]`).findAll('.el-option-group')
      .map(g => [g.attributes('data-label'), g.findAll('.el-option').map(o => o.text())])
    expect(groups('docx-s9')).toEqual([
      ['目标章（其下小标题在该章内定位）', ['【章】一 一']], ['写入章节（其下小标题一并并入）', ['一、1 一、1']]])
    expect(groups('docx-s3')).toEqual([['写入章节', ['一、1 一、1']]])
  })
})
