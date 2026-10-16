/**
 * NoteContentTemplateApplyDialog 头部（第二轮复盘第 10 组）
 *
 * - AC-8.2：来源、版本与保存人 / 时间；保存人缺失（用户已删除）只显示时间；
 * - AC-8.3 / 8.4：预览钉在所选版本的 version_id + content_hash；选的不是当前版本时提示已有更新版本。
 * useNoteTextBatch 换成可控 ref：只验弹窗接线，组合式函数自身由 useNoteTextBatch.spec 覆盖。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import type { ContentTemplateItem, ContentTemplateVersion } from '@/composables/useNoteContentTemplate'

const h = vi.hoisted(() => ({ batch: null as unknown }))
vi.mock('@/composables/useNoteTextBatch', () => ({ useNoteTextBatch: () => h.batch, toSelection: vi.fn() }))

import NoteContentTemplateApplyDialog from '@/components/disclosure/NoteContentTemplateApplyDialog.vue'
import NoteTextDiffDialog from '@/components/disclosure/NoteTextDiffDialog.vue'
import NoteTextPreviewList from '@/components/disclosure/NoteTextPreviewList.vue'
import type { PreviewItem, PreviewResponse } from '@/composables/useNoteTextBatch'

const stubs = {
  'el-dialog': { props: ['modelValue', 'title'], template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-button': { props: ['disabled', 'loading', 'type'], template: '<button class="el-button" :disabled="disabled"><slot /></button>' },
  'el-alert': { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
  NoteTextPreviewList: true,
  NoteTextDiffDialog: true,
}

const V1: ContentTemplateVersion = {
  id: 'v1', version_no: 1, source_project_name: '子甲', source_year: 2025, template_type: 'soe', report_scope: 'standalone',
  quality_summary: { total: 3, with_content: 2, high_risk: 0 }, content_hash: 'h'.repeat(64), byte_size: 10,
  created_by_name: '经理甲', created_at: '2026-10-01T08:00:00',
}
const V2: ContentTemplateVersion = { ...V1, id: 'v2', version_no: 2, content_hash: 'k'.repeat(64) }

function mountDialog(version: ContentTemplateVersion, current: ContentTemplateVersion = version) {
  const useTemplateVersion = vi.fn()
  const previewResult = ref<PreviewResponse | null>(null)
  h.batch = {
    previewResult, previewStale: ref(false), lastError: ref(null), previewLoading: ref(false),
    applyLoading: ref(false), canApply: computed(() => false), revokedReplacementIds: ref(new Set()),
    useTemplateVersion, fetchPreview: vi.fn(async () => true), toggleRevocation: vi.fn(), applyBatch: vi.fn(),
  }
  const template: ContentTemplateItem = { id: 't1', name: '集团模板', description: null, owner_scope: 'group',
    current_version_id: current.id, current_version: current, created_by: null, created_at: null, updated_at: null }
  const wrapper = mount(NoteContentTemplateApplyDialog, {
    props: { visible: true, projectId: 'p1', year: 2025, template, version }, global: { stubs } })
  return { wrapper, useTemplateVersion, previewResult }
}

describe('NoteContentTemplateApplyDialog', () => {
  it('AC-8.2：头部显示来源、版本与保存人 / 时间；预览钉在所选版本的 id + hash', async () => {
    const { wrapper, useTemplateVersion } = mountDialog(V1)
    await flushPromises()
    const head = wrapper.find('.gt-nta-head').text().replace(/\s+/g, ' ')
    expect(head).toContain('版本 v1 · 来源 子甲 2025 年')
    expect(head).toContain('经理甲 保存于 2026/10/01')
    expect(useTemplateVersion).toHaveBeenCalledWith('v1', 'h'.repeat(64))
    expect(wrapper.find('.el-alert').exists()).toBe(false)
  })

  it('保存人缺失（用户已删除）⇒ 只显示保存时间，不出现空姓名', async () => {
    const { wrapper } = mountDialog({ ...V1, created_by_name: null })
    await flushPromises()
    const head = wrapper.find('.gt-nta-head').text()
    expect(head).toContain('· 保存于 2026/10/01')
    expect(head).not.toMatch(/null|undefined|保存人/)
  })

  it('选的是历史版本 ⇒ 提示已有更新版本，预览仍钉在所选旧版本', async () => {
    const { wrapper, useTemplateVersion } = mountDialog(V1, V2)
    await flushPromises()
    expect(wrapper.find('.el-alert').text()).toContain('该模板已有更新版本 v2')
    expect(useTemplateVersion).toHaveBeenCalledWith('v1', 'h'.repeat(64))
  })

  it('第 26 组：重新预览后追加不再增加内容 ⇒ 已选的「追加」退回「替换」', async () => {
    const { wrapper, previewResult } = mountDialog(V1)
    await flushPromises()
    const preview = (over: Partial<PreviewItem>): PreviewResponse => ({
      preview_digest: 'd'.repeat(64), summary: {}, warnings: [], skipped_sources: [],
      items: [{
        source_id: 'tpl-s1', source_title: '公司基本情况', target_note_id: 'n1', target_note_section: '一、1',
        target_section_title: '公司基本情况', match_kind: 'section_code', evidence: '', confidence: 'confirmed',
        category: 'review', default_selected: false, unavailable_reason: null, before_html: '<p>旧</p>',
        before_hash: 'b'.repeat(64), proposed_html: '<p>新</p>', proposed_hash: 'p'.repeat(64),
        append_html: '<p>旧</p><p>新</p>', append_hash: 'a'.repeat(64), expected_updated_at: null,
        default_mode: 'replace', quality_flags: [], replacements: [], ...over,
      }],
    })
    previewResult.value = preview({})
    await flushPromises()
    wrapper.findComponent(NoteTextPreviewList).vm.$emit('open-diff', previewResult.value.items[0])
    await flushPromises()
    const diff = () => wrapper.findComponent(NoteTextDiffDialog)
    diff().vm.$emit('update:mode', 'append')
    await flushPromises()
    expect(diff().props('mode')).toBe('append')

    previewResult.value = preview({ before_html: '<p>旧</p><p>新</p>', append_html: '<p>旧</p><p>新</p>' })
    await flushPromises()
    expect(diff().props('mode')).toBe('replace')
  })
})
