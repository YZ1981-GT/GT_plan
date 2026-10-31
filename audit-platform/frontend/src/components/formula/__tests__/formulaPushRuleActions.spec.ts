/**
 * 推送规则纳入公式治理内核：规则表层级与本项目适配操作（spec formula-governance-coverage-closure R2.8）。
 *
 * 纯函数：ruleActions / ruleStatusText / 触发来源标签 / definitionText 停用与中文算式；
 * 真挂载面板（mock 网络层）：停用、启用（回到上游 / 本项目写启用）、恢复上游、改写公式的请求形状与失败提示。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'

const calls: Array<{ fn: string; args: unknown[] }> = []
const settingsFail: { error: unknown } = { error: null }
const responses: Record<string, any> = {}

const getCalls: Array<{ url: string; cfg: any }> = []
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(async (url: string, cfg?: any) => {
      getCalls.push({ url, cfg })
      const r = responses[`get ${url.split('/').pop()}`]
      if (r instanceof Error) throw r
      return r
    }),
    post: vi.fn(async () => ({})),
  },
}))
vi.mock('@/services/formulaSettingsApi', () => ({
  formulaSettingsApi: {
    saveOverrides: vi.fn(async (...args: unknown[]) => {
      calls.push({ fn: 'saveOverrides', args })
      if (settingsFail.error) throw settingsFail.error
      return { saved: [] }
    }),
    restoreGlobal: vi.fn(async (...args: unknown[]) => {
      calls.push({ fn: 'restoreGlobal', args })
      return { restored: [] }
    }),
  },
}))

import FormulaPushPanel from '../FormulaPushPanel.vue'
import {
  layerTagType, ruleActions, ruleReadonlyText, ruleStatusText, triggersText, type PushRuleView,
} from '../formulaPushView'
import { definitionText } from '@/composables/formula/useFormulaSettings'

const base = {
  stage: 'source', triggers: ['TRIAL_BALANCE_UPDATED', 'manual'], target: { domain: 'workpaper', sheet_code: 'E1-1', item_id: 'x' },
  status: 'active', issue: null, layer: 'preset', layer_label: '系统预设', disabled: false, pending: false,
  has_local: false, local_version: null,
}
const SYSTEM: PushRuleView = {
  ...base, rule_id: 'E1.tb_amount.ending', policy: 'system', description: '试算平衡表数（期末）',
  formula: "TB('1001','期末余额')+TB('1002','期末余额')", preset_formula: "TB('1001','期末余额')+TB('1002','期末余额')",
  editable_formula: true, can_disable: false,
}
const CASH: PushRuleView = {
  ...base, rule_id: 'E1.cash_rows.four_table', policy: 'editable', description: '库存现金明细', formula: '四表明细',
  preset_formula: '四表明细', editable_formula: false, can_disable: true,
}
const DERIVED: PushRuleView = {
  ...base, rule_id: 'E1.cash_detail.ending', stage: 'derived', policy: 'derived', description: '现金合计', formula: '合计',
  preset_formula: '合计', editable_formula: false, can_disable: false,
}
const keys = (rule: PushRuleView, canEdit = true) => ruleActions(rule, canEdit).map((a) => `${a.key}${a.via ? `:${a.via}` : ''}`)

describe('规则操作（纯函数）', () => {
  it('系统值只能改写；可编辑值能停用；派生值只读', () => {
    expect(keys(SYSTEM)).toEqual(['rewrite'])
    expect(keys(CASH)).toEqual(['disable'])
    expect(keys(DERIVED)).toEqual([])
    expect(ruleReadonlyText(DERIVED)).toContain('派生值')
  })

  it('改写过的给「恢复上游」；停用的只给「启用」：本项目层停用 → 回到上游，上游停用 → 本项目写启用', () => {
    expect(keys({ ...SYSTEM, has_local: true, local_version: 2, layer: 'project' })).toEqual(['rewrite', 'restore'])
    expect(keys({ ...CASH, status: 'disabled', disabled: true, has_local: true, local_version: 1 })).toEqual(['enable:restore'])
    expect(keys({ ...CASH, status: 'disabled', disabled: true, layer: 'global' })).toEqual(['enable:save'])
    expect(keys({ ...SYSTEM, status: 'invalid', has_local: true, local_version: 1 })).toEqual(['rewrite', 'restore'])
  })

  it('无编辑权：按钮不可用并写明原因', () => {
    const [a] = ruleActions(CASH, false)
    expect(a.enabled).toBe(false)
    expect(a.reason).toBe('需要本项目编辑权限')
  })

  it('状态标记、层级颜色与触发来源中文', () => {
    expect(ruleStatusText({ ...SYSTEM, status: 'invalid' })).toBe('定义失效，本次未推送')
    expect(ruleStatusText({ ...CASH, status: 'disabled' })).toBe('已停用')
    expect(ruleStatusText({ ...SYSTEM, pending: true })).toBe('有待确认的上游变更')
    expect(ruleStatusText(SYSTEM)).toBe('')
    expect([layerTagType('preset'), layerTagType('global'), layerTagType('project'), layerTagType('template'),
      layerTagType(undefined), layerTagType('')]).toEqual(['info', 'primary', 'warning', 'success', 'info', 'info'])
    expect(triggersText(['FORMULA_CONFIG_CHANGED', 'manual'])).toBe('公式规则变更、手动')
  })

  it('definitionText：停用显示「（已停用）」，无公式字段时用中文算式', () => {
    expect(definitionText({ disabled: true, expression: "TB('1001','期末余额')" })).toBe('（已停用）')
    expect(definitionText({ expression: '', description: 'x' }, { formula_text: ' 库存现金明细 = 四表 ' })).toBe('库存现金明细 = 四表')
    expect(definitionText({ expression: "TB('1001','期末余额')" }, { formula_text: '不用' })).toBe("TB('1001','期末余额')")
    expect(definitionText({ expression: '' })).toBe('（空）')
    expect(definitionText(null)).toBe('（已删除）')
  })
})

const DialogStub = defineComponent({
  name: 'FormulaDefinitionEditDialog',
  props: ['modelValue', 'title', 'execFields', 'descFields', 'definition'],
  emits: ['save', 'update:modelValue'],
  template: '<div class="fde-stub" :data-visible="String(modelValue)" />',
})

function mountPanel(rules: PushRuleView[], props: Record<string, unknown> = {}) {
  responses['get rules'] = { rules }
  responses['get latest'] = { run: null, state_counts: {} }
  responses['get states'] = { states: [] }
  responses['get runs'] = { runs: [] }
  return mount(FormulaPushPanel, {
    props: { projectId: 'p1', year: 2025, wpCode: 'E1', ...props },
    global: { plugins: [ElementPlus], stubs: { FormulaDefinitionEditDialog: DialogStub } },
  })
}
const button = (w: ReturnType<typeof mountPanel>, key: string) => w.find(`[data-testid="fp-rule-${key}"]`)

beforeEach(() => {
  calls.length = 0
  settingsFail.error = null
  vi.restoreAllMocks()
})

describe('面板：规则本项目适配（真挂载）', () => {
  it('层级列与状态标记、只读说明', async () => {
    const w = mountPanel([SYSTEM, { ...CASH, status: 'disabled', disabled: true, layer: 'project', layer_label: '本项目' }, DERIVED])
    await flushPromises()
    const text = w.text()
    for (const s of ['层级', '系统预设', '本项目', '已停用', '派生值：由引擎按规则计算，只读', '本项目适配']) expect(text, s).toContain(s)
  })

  it('本项目停用：确认后按 push 域写停用（无本项目层 ⇒ 不带版本号）', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const w = mountPanel([CASH])
    await flushPromises()
    await button(w, 'disable').trigger('click')
    await flushPromises()
    expect(calls).toEqual([{ fn: 'saveOverrides', args: ['p1', 'push', [{
      slot_key: CASH.rule_id, definition: { disabled: true }, label: `${CASH.rule_id} ${CASH.description}`, expected_version: null,
    }]] }])
  })

  it('启用：本项目层停用的回到上游（删本项目层）；上游停用的在本项目写启用', async () => {
    let w = mountPanel([{ ...CASH, status: 'disabled', disabled: true, has_local: true, local_version: 3 }])
    await flushPromises()
    await button(w, 'enable').trigger('click')
    await flushPromises()
    expect(calls).toEqual([{ fn: 'restoreGlobal', args: ['p1', 'push', [CASH.rule_id], [3]] }])
    calls.length = 0
    w = mountPanel([{ ...CASH, status: 'disabled', disabled: true, layer: 'global' }])
    await flushPromises()
    await button(w, 'enable').trigger('click')
    await flushPromises()
    expect(calls.map((c) => [c.fn, (c.args[2] as any[])[0].definition])).toEqual([['saveOverrides', { disabled: false }]])
  })

  it('改写公式：弹窗带当前公式与说明，保存带本项目版本号；失败给中文原因', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => ({}) as any)
    const rewritten = { ...SYSTEM, has_local: true, local_version: 2, layer: 'project', formula: "TB('1001','期末余额')" }
    const w = mountPanel([rewritten])
    await flushPromises()
    await button(w, 'rewrite').trigger('click')
    await flushPromises()
    const dlg = w.findComponent(DialogStub)
    expect(dlg.props('modelValue')).toBe(true)
    expect(dlg.props('definition')).toEqual({ expression: "TB('1001','期末余额')", description: SYSTEM.description })
    expect(dlg.props('execFields')).toEqual(['expression'])
    dlg.vm.$emit('save', { expression: "TB('1002','期末余额')", description: null })
    await flushPromises()
    expect(calls).toEqual([{ fn: 'saveOverrides', args: ['p1', 'push', [{
      slot_key: SYSTEM.rule_id, definition: { expression: "TB('1002','期末余额')", description: null },
      label: `${SYSTEM.rule_id} ${SYSTEM.description}`, expected_version: 2,
    }]] }])
    settingsFail.error = { response: { status: 400, data: { detail: { message: '科目 1122 不在本底稿推送取数的科目内' } } } }
    dlg.vm.$emit('save', { expression: "TB('1122','期末余额')", description: null })
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('保存推送公式失败：科目 1122 不在本底稿推送取数的科目内')
  })

  it('恢复上游：确认后删除本项目层', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const w = mountPanel([{ ...SYSTEM, has_local: true, local_version: 1, layer: 'project' }])
    await flushPromises()
    await button(w, 'restore').trigger('click')
    await flushPromises()
    expect(calls).toEqual([{ fn: 'restoreGlobal', args: ['p1', 'push', [SYSTEM.rule_id], [1]] }])
  })

  it('无编辑权：适配按钮不可用', async () => {
    const w = mountPanel([CASH], { canEdit: false })
    await flushPromises()
    expect(button(w, 'disable').attributes('disabled')).toBeDefined()
  })
})

describe('反向校验面板：失败原因在面板内显示（不弹「[object Object]」）', () => {
  it('静默请求 + 中文原因', async () => {
    const msgSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => ({}) as any)
    const warnSpy = vi.spyOn(ElMessage, 'warning').mockImplementation(() => ({}) as any)
    const w = mountPanel([])
    await flushPromises()
    const fail = Object.assign(new Error('x'), { response: { status: 403, data: { detail: '无权查看该项目' } } })
    responses['get verify'] = fail
    getCalls.length = 0
    await w.findAll('button').find((b) => b.text().includes('反向校验'))!.trigger('click')
    await flushPromises()
    expect(getCalls.at(-1)?.cfg).toEqual({ _silent: true })
    expect(w.text()).toContain('校验失败：无权查看该项目')
    expect([...msgSpy.mock.calls, ...warnSpy.mock.calls].flat().join('')).not.toContain('[object Object]')
  })
})
