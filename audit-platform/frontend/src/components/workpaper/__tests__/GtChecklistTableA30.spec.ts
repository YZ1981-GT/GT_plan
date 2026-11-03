/**
 * A30 电子底稿归档检查表接线（spec attachment-archive-and-a-class-evidence 需求 8）：
 * 模板声明的结论选项生效（是 / 否 / 不适用，批量标记同口径）、只有 A30 且非只读才有「按项目底稿建议」按钮。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtChecklistTable from '../GtChecklistTable.vue'
import GtChecklistSection from '../GtChecklistSection.vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'proj-001' }, query: {} }) }))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}) },
}))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<typeof import('element-plus')>('element-plus')
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }
})

const template = (wp_code: string, conclusion_mode?: 'completion' | 'disclosure') => ({
  template: {
    wp_code, title: '电子底稿归档检查表', conclusion_mode,
    sections: [{ id: 'A30-S-D', title: 'D 销售收入', items: [
      { id: 'A30-D2', type: 'actionable' as const, standard_ref: 'D2', content: '营业收入', children: [] },
    ] }],
    toc: [{ id: 'A30-S-D', title: 'D 销售收入', applicable: true }],
    stats: { total_actionable: 1, total_guidance: 0, total_sections: 1 },
  },
  responses: {},
})

const stubs = {
  'el-tree': true, 'el-input': true, 'el-select': true, 'el-option': true, 'el-progress': true, 'el-checkbox': true,
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' }, 'el-dialog': { template: '<div><slot /></div>' },
  'el-popover': { template: '<div><slot /><slot name="reference" /></div>' },
}

function mountTable(data: ReturnType<typeof template>, readonly = false) {
  return mount(GtChecklistTable, { props: { wpId: 'wp-a30', htmlData: data, readonly }, global: { stubs } })
}

describe('GtChecklistTable · A30', () => {
  it('模板声明 completion ⇒ 结论选项是 / 否 / 不适用；有建议按钮', () => {
    const w = mountTable(template('A30', 'completion'))
    expect(w.findComponent(GtChecklistSection).props('conclusionMode')).toBe('completion')
    expect(w.text()).toContain('按项目底稿建议')
  })

  it('未声明时按编码（非 A17-5 ⇒ disclosure），非 A30 没有建议按钮', () => {
    const w = mountTable(template('A1-15'))
    expect(w.findComponent(GtChecklistSection).props('conclusionMode')).toBe('disclosure')
    expect(w.text()).not.toContain('按项目底稿建议')
  })

  it('只读没有建议按钮', () => {
    expect(mountTable(template('A30', 'completion'), true).text()).not.toContain('按项目底稿建议')
  })

  it('本章节批量标记与结论选项同口径：completion 只给「是 / 不适用」，disclosure 照旧四项', () => {
    const ddStubs = {
      ...stubs,
      'el-dropdown': { template: '<div><slot /><slot name="dropdown" /></div>' },
      'el-dropdown-menu': { template: '<ul><slot /></ul>' },
      'el-dropdown-item': { props: ['command'], template: '<li :data-command="command"><slot /></li>' },
    }
    const commands = (data: ReturnType<typeof template>) =>
      mount(GtChecklistTable, { props: { wpId: 'wp-x', htmlData: data, readonly: false }, global: { stubs: ddStubs } })
        .findAll('.toolbar__batch li').map((li) => li.attributes('data-command'))
    expect(commands(template('A30', 'completion'))).toEqual(['是', '不适用'])
    expect(commands(template('A1-15'))).toEqual(['Y', 'X/I', 'X/W', 'N/A'])
  })

  it('首次打开（无适用性记录）弹章节适用性；只读（如已归档）存不了，不弹', async () => {
    const dlgStubs = {
      ...stubs,
      'el-dialog': { props: ['modelValue', 'title'], template: '<div v-if="modelValue" class="dlg" :data-title="title"><slot /></div>' },
    }
    const dialogs = async (readonly: boolean) => {
      const w = mount(GtChecklistTable, {
        props: { wpId: 'wp-a30', htmlData: template('A30', 'completion'), readonly }, global: { stubs: dlgStubs },
      })
      await nextTick()
      await nextTick()
      return w.findAll('.dlg').map((d) => d.attributes('data-title'))
    }
    expect(await dialogs(false)).toContain('章节适用性设置')
    expect(await dialogs(true)).not.toContain('章节适用性设置')
  })
})
