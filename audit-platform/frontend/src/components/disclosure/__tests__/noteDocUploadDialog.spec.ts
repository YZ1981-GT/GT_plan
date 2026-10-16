/**
 * NoteDocUploadDialog 接线（第二轮复盘第 9 组 · Task 35）
 *
 * - AC-2.1：双栏放在可拖拽分栏里，左右两个面板都设最小宽度（拖不没）；
 * - AC-2.2：预览后左栏逐来源显示匹配状态，与右栏同一份服务端预览；未预览时不显示。
 * useNoteTextBatch 整体换成可控 ref：这里只验弹窗接线，组合式函数自身由 useNoteTextBatch.spec 覆盖。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed, nextTick, ref } from 'vue'
import type { ParsedSection, PreviewItem, PreviewResponse } from '@/composables/useNoteTextBatch'

const h = vi.hoisted(() => ({ batch: null as unknown }))
vi.mock('@/composables/useNoteTextBatch', () => ({ useNoteTextBatch: () => h.batch, toSelection: vi.fn() }))
vi.mock('@/composables/useKnowledge', () => ({ useKnowledge: () => ({ pickDocuments: vi.fn() }) }))
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: vi.fn() } }))

import NoteDocUploadDialog from '@/components/disclosure/NoteDocUploadDialog.vue'
import NoteTextDiffDialog from '@/components/disclosure/NoteTextDiffDialog.vue'
import NoteTextPreviewList from '@/components/disclosure/NoteTextPreviewList.vue'

const stubs = {
  'el-dialog': { props: ['modelValue', 'title'], template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-splitter': { template: '<div class="el-splitter"><slot /></div>' },
  'el-splitter-panel': { props: ['size', 'min'], template: '<div class="el-splitter-panel" :data-size="size" :data-min="min"><slot /></div>' },
  'el-button': { props: ['disabled', 'loading', 'type', 'size', 'link'], emits: ['click'],
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  'el-tag': { props: ['type', 'effect', 'size'], template: '<span class="el-tag" :data-type="type"><slot /></span>' },
  'el-alert': { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
  NoteTextPreviewList: { template: '<div class="preview-list-stub" />' },
  NoteTextDiffDialog: true,
}

function sec(source_id: string, title: string, level = 2): ParsedSection {
  return { source_id, title, level, html: '<p>正文</p>', confidence: 'candidate', warnings: [] }
}

function item(over: Partial<PreviewItem>): PreviewItem {
  return {
    source_id: 'docx-s1', source_title: '会计期间', target_note_id: 'n1', target_note_section: '四、会计期间',
    target_section_title: '会计期间', match_kind: 'title_exact', evidence: '', confidence: 'candidate',
    category: 'review', default_selected: false, unavailable_reason: null, before_html: '', before_hash: 'b'.repeat(64),
    proposed_html: '<p>新</p>', proposed_hash: 'p'.repeat(64), append_html: null, append_hash: null,
    expected_updated_at: null, default_mode: 'replace', quality_flags: [], replacements: [], ...over,
  }
}

function mountDialog(sections: ParsedSection[]) {
  const previewResult = ref<PreviewResponse | null>(null)
  h.batch = {
    parsedSections: ref(sections), previewResult, editedSourceIds: ref<string[]>([]), manualMappings: ref(new Map()),
    revokedReplacementIds: ref(new Set()), sourceKind: ref('upload'),
    parsedSource: ref({ source_metadata: { file_name: '附注.docx' } }), previewStale: ref(false), lastError: ref(null),
    loading: ref(false), previewLoading: ref(false), applyLoading: ref(false),
    canApply: computed(() => false), isDirty: computed(() => false),
  }
  const wrapper = mount(NoteDocUploadDialog, { props: { visible: true, projectId: 'p1', year: 2025 }, global: { stubs } })
  return { wrapper, previewResult }
}

describe('NoteDocUploadDialog', () => {
  it('AC-2.1：左右两栏放在可拖拽分栏里，两个面板都有最小宽度', () => {
    const { wrapper } = mountDialog([sec('docx-s1', '会计期间')])
    const panels = wrapper.findAll('.el-splitter > .el-splitter-panel')
    expect(panels).toHaveLength(2)
    expect(panels.every(p => Number(p.attributes('data-min')) > 0)).toBe(true)
    expect(panels[0].text()).toContain('会计期间')
    expect(panels[1].find('.gt-ndu-pane').exists()).toBe(true)
  })

  it('AC-2.2：预览前左栏无匹配状态；预览后逐来源显示，被跳过的来源带原因', async () => {
    const { wrapper, previewResult } = mountDialog([
      sec('docx-s1', '会计期间'), sec('docx-s2', '（1）子节', 3), sec('docx-s3', '某某专项说明')])
    expect(wrapper.findAll('.gt-ndu-match')).toHaveLength(0)

    previewResult.value = {
      preview_digest: 'd'.repeat(64), summary: {}, warnings: [],
      items: [item({}), item({ source_id: 'docx-s3', target_note_id: null, target_note_section: null,
        target_section_title: null, category: 'unavailable', unavailable_reason: '未找到匹配的目标章节' })],
      skipped_sources: [{ source_id: 'docx-s2', match_kind: 'folded' }],
    }
    await nextTick()
    expect(wrapper.findAll('.gt-ndu-match')).toHaveLength(3)
    const shown = Object.fromEntries(wrapper.findAll('.gt-ndu-source').map(s =>
      [s.find('strong').text(), `${s.find('.gt-ndu-match').attributes('data-type')}:${s.find('.gt-ndu-match').text()}`]))
    expect(shown).toEqual({ '会计期间': 'warning:需复核', '（1）子节': 'info:已并入上级章节', '某某专项说明': 'info:未匹配' })
    expect(wrapper.find('.gt-ndu-match').attributes('title')).toBe('四、会计期间 会计期间')
  })

  it('第 26 组：重新预览后追加不再增加内容 ⇒ 已选的「追加」退回「替换」（仍增加内容则保留）', async () => {
    const { wrapper, previewResult } = mountDialog([sec('docx-s1', '会计期间')])
    const preview = (over: Partial<PreviewItem>): PreviewResponse => ({
      preview_digest: 'd'.repeat(64), summary: {}, warnings: [], skipped_sources: [],
      items: [item({ before_html: '<p>旧</p>', append_html: '<p>旧</p><p>新</p>', append_hash: 'a'.repeat(64), ...over })],
    })
    previewResult.value = preview({})
    await nextTick()
    wrapper.findComponent(NoteTextPreviewList).vm.$emit('open-diff', previewResult.value.items[0])
    await nextTick()
    const diff = () => wrapper.findComponent(NoteTextDiffDialog)
    diff().vm.$emit('update:mode', 'append')
    await nextTick()
    expect(diff().props('mode')).toBe('append')

    previewResult.value = preview({ before_html: '<p>旧</p><p>补</p>', append_html: '<p>旧</p><p>补</p><p>新</p>' })
    await nextTick()
    expect(diff().props('mode')).toBe('append')  // 对照：仍增加内容，保留用户的选择

    previewResult.value = preview({ before_html: '<p>旧</p><p>新</p>', append_html: '<p>旧</p><p>新</p>' })
    await nextTick()
    expect(diff().props('mode')).toBe('replace')
  })
})
