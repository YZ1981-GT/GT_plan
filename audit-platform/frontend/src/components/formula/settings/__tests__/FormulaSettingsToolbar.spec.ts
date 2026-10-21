/**
 * FormulaSettingsToolbar —— 顶栏入口 + 保存后「应用范围」对话框（spec formula-global-settings-sync R7.1）
 *
 * 守护：askApplyScope 对任意域（tb_detail / cross_check / report）都能打开应用范围对话框并传域与公式位；
 * 无项目上下文或空公式位时不弹（保存了但没有真正改动时不打扰）；layerLabel / LAYER_LABELS 层级标签口径。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import FormulaSettingsToolbar from '../FormulaSettingsToolbar.vue'
import { layerLabel, LAYER_LABELS, layerTagType } from '@/composables/formula/useFormulaSettings'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const stubs = {
  'el-button': { template: '<button><slot /></button>' },
  FormulaTemplateSaveDialog: true,
  FormulaTemplateSubscribeDialog: true,
  // 捕获应用范围对话框拿到的 domain / slotKeys / visible
  FormulaApplyScopeDialog: {
    props: ['modelValue', 'projectId', 'domain', 'slotKeys', 'canEditGlobal'],
    template: '<div data-testid="apply" :data-visible="modelValue" :data-domain="domain" ' +
      ':data-slots="(slotKeys || []).join(\',\')" />',
  },
}

function mountToolbar(props: Record<string, unknown> = {}) {
  return mount(FormulaSettingsToolbar, { props: { projectId: 'p1', ...props }, global: { stubs } })
}

describe('FormulaSettingsToolbar.askApplyScope', () => {
  it('对任意域打开应用范围对话框并传入域与公式位', async () => {
    const w = mountToolbar({ domain: 'tb_detail' })
    ;(w.vm as any).askApplyScope('tb_detail', ['1001', 'added:X1'])
    await w.vm.$nextTick()
    const dlg = w.find('[data-testid="apply"]')
    expect(dlg.attributes('data-visible')).toBe('true')
    expect(dlg.attributes('data-domain')).toBe('tb_detail')
    expect(dlg.attributes('data-slots')).toBe('1001,added:X1')
  })

  it('表间审核域同样可弹（域无关）', async () => {
    const w = mountToolbar({ domain: 'cross_check' })
    ;(w.vm as any).askApplyScope('cross_check', ['grp#abc'])
    await w.vm.$nextTick()
    expect(w.find('[data-testid="apply"]').attributes('data-domain')).toBe('cross_check')
  })

  it('空公式位（保存但无改动）不弹', async () => {
    const w = mountToolbar()
    ;(w.vm as any).askApplyScope('tb_detail', [])
    await w.vm.$nextTick()
    expect(w.find('[data-testid="apply"]').attributes('data-visible')).toBe('false')
  })

  it('无项目上下文不弹', async () => {
    const w = mountToolbar({ projectId: '' })
    ;(w.vm as any).askApplyScope('report', ['balance_sheet:BS-001'])
    await w.vm.$nextTick()
    expect(w.find('[data-testid="apply"]').attributes('data-visible')).toBe('false')
  })
})

describe('层级标签口径', () => {
  it('LAYER_LABELS / layerLabel 覆盖五层', () => {
    expect(Object.keys(LAYER_LABELS).sort()).toEqual(['global', 'pinned', 'preset', 'project', 'template'])
    expect(layerLabel('template')).toBe('模板')
    expect(layerLabel('project')).toBe('本项目')
    expect(layerLabel('pinned')).toBe('暂缓采用')
    expect(layerLabel(undefined)).toBe('')
  })

  it('layerTagType 颜色：模板绿 / 本项目橙 / 暂缓红 / 其余灰', () => {
    expect(layerTagType('template')).toBe('success')
    expect(layerTagType('project')).toBe('warning')
    expect(layerTagType('pinned')).toBe('danger')
    expect(layerTagType('global')).toBe('info')
  })
})
