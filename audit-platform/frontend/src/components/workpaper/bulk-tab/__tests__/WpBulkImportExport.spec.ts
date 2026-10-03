/**
 * WpBulkImportExport.spec.ts — 项目级底稿批量 Tab 导入导出组件测试
 *
 * Spec: .kiro/specs/workpaper-bulk-tab-import-export/
 * Task: 6.5（组件挂载 + 报告状态渲染）
 * Requirements: 5.1, 2.5
 *
 * 覆盖：
 * - WpBulkImportReport：逐 sheet 状态标签渲染（success/partial/failed/missing/
 *   unlisted/blocked_by_status/conflict_rejected）+ 汇总标签 + 错误/告警/原因展示 +
 *   DryRun 与正式导入报告标题区分
 * - WpBulkDialog：三按钮入口挂载 + 选择操作进入配置步骤
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mount } from '@vue/test-utils'
import type { ImportReport } from '@/composables/useBulkTabImportExport'

// ── 隔离 composable 依赖（http/sse），避免真实网络/鉴权 ──
const exportTemplates = vi.fn().mockResolvedValue(undefined)
const exportData = vi.fn().mockResolvedValue(undefined)
const importData = vi.fn()
vi.mock('@/composables/useBulkTabImportExport', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useBulkTabImportExport')>()
  return {
    ...actual,
    useBulkTabImportExport: () => ({
      loading: { value: false },
      error: { value: null },
      busy: { value: false },
      exportTemplates,
      exportData,
      importData,
      rollback: vi.fn(),
      subscribeProgress: vi.fn(() => () => {}),
      closeProgress: vi.fn(),
    }),
  }
})

import WpBulkImportReport from '../WpBulkImportReport.vue'
import WpBulkDialog from '../WpBulkDialog.vue'

const ELEMENT_STUBS = {
  'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><span>{{ label }}</span><slot /></div>', props: ['label'] },
  'el-checkbox-group': { template: '<div><slot /></div>' },
  'el-checkbox': { template: '<label><slot /></label>' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio': { template: '<label><slot /></label>' },
  'el-switch': true,
  'el-upload': { template: '<div><slot name="trigger" /><slot /><slot name="tip" /></div>' },
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-alert': { template: '<div class="el-alert" :data-title="title"><slot /></div>', props: ['title', 'type'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-table': {
    template: '<table><slot /></table>',
    props: ['data'],
  },
  'el-table-column': {
    // 对每一行渲染默认插槽，模拟 el-table 行作用域
    template: '<div><template v-for="(row, i) in rows" :key="i"><slot :row="row" /></template></div>',
    props: ['prop', 'label'],
    computed: {
      rows(this: any) {
        const parent = this.$parent
        const data = parent?.data ?? parent?.$props?.data ?? []
        return Array.isArray(data) ? data : []
      },
    },
  },
  'el-empty': { template: '<div class="el-empty"><slot /></div>' },
  'el-progress': true,
  Loading: true,
}

function makeReport(overrides: Partial<ImportReport> = {}): ImportReport {
  return {
    import_id: 'imp-1',
    strategy: 'overwrite',
    dry_run: false,
    snapshots: [],
    sheets: [
      { sheet_code: 'D2-2', status: 'success', rows: 42 },
      { sheet_code: 'D2-1', status: 'partial', rows: 10, warnings: ['row_limit_exceeded: 520 > 500'] },
      { sheet_code: 'D2-7', status: 'blocked_by_status', reason: 'review_passed' },
      { sheet_code: 'D2-3', status: 'missing' },
      { sheet_code: 'D2-4', status: 'failed', errors: ['解析失败: 表头不匹配'] },
      { sheet_code: 'D2-5', status: 'conflict_rejected', reason: '目标已有非空数据' },
      { sheet_code: 'D2-6', status: 'unlisted' },
    ],
    summary: {
      success: 1,
      partial: 1,
      failed: 1,
      blocked: 1,
      missing: 1,
      unlisted: 1,
      conflict_rejected: 1,
    },
    ...overrides,
  }
}

describe('WpBulkImportReport — 逐 sheet 报告渲染', () => {
  it('挂载并渲染汇总标签', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport(), dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    expect(wrapper.exists()).toBe(true)
    const text = wrapper.text()
    expect(text).toContain('成功: 1')
    expect(text).toContain('部分: 1')
    expect(text).toContain('失败: 1')
    expect(text).toContain('受阻: 1')
    expect(text).toContain('缺失: 1')
    expect(text).toContain('未登记: 1')
    expect(text).toContain('冲突拒绝: 1')
  })

  it('渲染每种 sheet 状态的中文标签', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport(), dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    const text = wrapper.text()
    // statusLabel 映射
    expect(text).toContain('成功')
    expect(text).toContain('部分成功')
    expect(text).toContain('失败')
    expect(text).toContain('状态受阻')
    expect(text).toContain('文件缺失')
    expect(text).toContain('冲突拒绝')
    expect(text).toContain('未登记')
  })

  it('展示错误信息（errors 优先于 reason/warnings）', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: {
        report: makeReport({
          sheets: [{ sheet_code: 'D2-4', status: 'failed', errors: ['解析失败: 表头不匹配'] }],
        }),
        dryRun: false,
      },
      global: { stubs: ELEMENT_STUBS },
    })
    expect(wrapper.text()).toContain('解析失败: 表头不匹配')
  })

  it('DryRun 报告标题为预检（未写库）', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport({ dry_run: true }), dryRun: true },
      global: { stubs: ELEMENT_STUBS },
    })
    const alert = wrapper.find('.el-alert')
    expect(alert.attributes('data-title')).toContain('预检')
  })

  it('正式导入报告标题为导入报告', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport(), dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    const alert = wrapper.find('.el-alert')
    expect(alert.attributes('data-title')).toContain('导入报告')
  })

  it('report 为 null 时渲染空状态', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: null, dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })
})

/**
 * WpBulkDialog 入口 —— 原「三按钮」已被四场景卡片取代
 * （spec: workpaper-import-export-lifecycle-closure Task 18 / R3.7、R3.8）。
 *
 * 🔴 这里的 mock 文案**故意是占位串**（`场景N-产物` 之类），不抄后端真实文案。
 *
 * 真实文案的单一真源是 `backend/app/services/bulk_tab/scenario_registry.py`，
 * 由后端守卫 `test_bulk_scenario_ui_single_source.py` 负责比对；本测试只验
 * **渲染管线**：拿到几条就渲染几张卡、字段是否绑上、disabled 是否生效。
 * 若在这里写死真实中文，本文件就成了第二份文案源 —— 后端改文案后此处 stale
 * 且不会打红，正是要避免的那类假绿。
 */
describe('WpBulkDialog — 四场景入口', () => {
  /** 与后端 `scenarios_for_ui()` 同构的最小载荷（文案用占位串） */
  const FAKE_SCENARIOS = [
    {
      key: 'blank_template',
      label: '场景1',
      artifactNote: '场景1-产物',
      timingNote: '场景1-时点',
      exportEndpoint: '/x/export-templates',
      importEndpoint: null,
      mode: 'template',
      direction: 'export',
      archivedAllowed: true,
      disabled: false,
      disabledReason: null,
    },
    {
      key: 'fill_back',
      label: '场景2',
      artifactNote: '场景2-产物',
      timingNote: '场景2-时点',
      exportEndpoint: null,
      importEndpoint: '/x/import',
      mode: 'template',
      direction: 'import',
      archivedAllowed: false,
      disabled: true,
      disabledReason: '占位-禁用原因',
    },
    {
      key: 'refresh_edit',
      label: '场景3',
      artifactNote: '场景3-产物',
      timingNote: '场景3-时点',
      exportEndpoint: '/x/export-data',
      importEndpoint: '/x/import',
      mode: 'data',
      direction: 'round_trip',
      archivedAllowed: false,
      disabled: false,
      disabledReason: null,
    },
    {
      key: 'archive_export',
      label: '场景4',
      artifactNote: '场景4-产物',
      timingNote: '场景4-时点',
      exportEndpoint: '/x/export-data',
      importEndpoint: null,
      mode: 'data',
      direction: 'export',
      archivedAllowed: true,
      disabled: false,
      disabledReason: null,
    },
  ]

  /**
   * 与后端 `cycle_options_for_ui()` 同构的最小循环清单（Req 8.5）。
   *
   * 对话框改造后 `cycles` 缺失即**显式报错**（不退回写死列表），所以每个挂载都得带上它。
   * 这里故意混入两条 `supported: false`，对应真实 catalog 里 E / J 一张可导入导出的
   * Tab 都没有的情况。
   */
  const FAKE_CYCLES = [
    { code: 'D', name: '销售收入', supported: true, unsupportedReason: '' },
    { code: 'E', name: '货币资金', supported: false, unsupportedReason: '占位-未接入原因' },
    { code: 'F', name: '采购存货', supported: true, unsupportedReason: '' },
    { code: 'J', name: '薪酬', supported: false, unsupportedReason: '占位-未接入原因' },
  ]

  async function mountWithScenarios(overrides: Record<string, unknown> = {}) {
    const http = (await import('@/utils/http')).default as any
    http.get = vi.fn().mockResolvedValue({
      data: {
        data: {
          isArchived: false,
          projectStatus: 'execution',
          scenarios: FAKE_SCENARIOS,
          cycles: FAKE_CYCLES,
          ...overrides,
        },
      },
    })
    const wrapper = mount(WpBulkDialog, {
      props: { modelValue: true, projectId: 'proj-1' },
      global: { stubs: ELEMENT_STUBS },
    })
    // 等 loadScenarios 的微任务链落地
    await flushPromises()
    await wrapper.vm.$nextTick()
    return wrapper
  }

  beforeEach(() => {
    exportTemplates.mockClear()
    exportData.mockClear()
    importData.mockClear()
  })

  it('渲染的卡片数 == 后端返回的场景数（不写死四张）', async () => {
    const wrapper = await mountWithScenarios()
    const cards = wrapper.findAll('[data-testid^="bulk-scenario-"]')
    expect(cards.length).toBe(FAKE_SCENARIOS.length)
  })

  it('每张卡片都渲染了 label / artifactNote / timingNote 三段', async () => {
    const wrapper = await mountWithScenarios()
    for (const sc of FAKE_SCENARIOS) {
      const card = wrapper.find(`[data-testid="bulk-scenario-${sc.key}"]`)
      expect(card.exists(), `${sc.key} 的卡片未渲染`).toBe(true)
      const text = card.text()
      expect(text, `${sc.key} 缺 label`).toContain(sc.label)
      expect(text, `${sc.key} 缺 artifactNote`).toContain(sc.artifactNote)
      expect(text, `${sc.key} 缺 timingNote`).toContain(sc.timingNote)
    }
  })

  it('后端标 disabled 的卡片带禁用类，未标的不带（R3.8）', async () => {
    const wrapper = await mountWithScenarios()
    for (const sc of FAKE_SCENARIOS) {
      const card = wrapper.find(`[data-testid="bulk-scenario-${sc.key}"]`)
      expect(card.classes().includes('is-disabled'), `${sc.key} 禁用态渲染不符`).toBe(
        sc.disabled,
      )
    }
  })

  it('点可用场景进入配置步骤（循环多选）', async () => {
    const wrapper = await mountWithScenarios()
    await wrapper.find('[data-testid="bulk-scenario-blank_template"]').trigger('click')
    expect(wrapper.text()).toContain('选择审计循环')
  })

  it('点禁用场景不进入配置步骤（点击被代码拦住，不只靠样式）', async () => {
    const wrapper = await mountWithScenarios()
    await wrapper.find('[data-testid="bulk-scenario-fill_back"]').trigger('click')
    expect(wrapper.find('[data-testid="bulk-scenario-recap"]').exists()).toBe(false)
  })

  it('round_trip 场景显示切腿选择，单向场景不显示', async () => {
    const wrapper = await mountWithScenarios()
    await wrapper.find('[data-testid="bulk-scenario-refresh_edit"]').trigger('click')
    expect(wrapper.find('[data-testid="bulk-roundtrip-leg"]').exists()).toBe(true)

    const wrapper2 = await mountWithScenarios()
    await wrapper2.find('[data-testid="bulk-scenario-blank_template"]').trigger('click')
    expect(wrapper2.find('[data-testid="bulk-roundtrip-leg"]').exists()).toBe(false)
  })

  /**
   * 🔴 模板导出也显示「密码保护（可选）」框，但原先 `exportTemplates(cycles)` 不传密码 ⇒
   * 设了密码仍拿到明文 ZIP（spec environment-hygiene-deps-and-scratch-schemas Req 4.4）。
   * 判据落在真实 DOM：往密码框输入 → 点执行 → 断言 composable 收到同一个值。
   */
  it.each([
    ['blank_template', 'exportTemplates'],
    ['archive_export', 'exportData'],
  ] as const)('%s：密码框的值传给 %s', async (scenarioKey, fnName) => {
    const PASSWORD_STUBS = {
      ...ELEMENT_STUBS,
      // 声明 emits：否则父组件的 @click 既作为原生监听透传到根 <button>、又被 $emit 一次 ⇒ 一次点击执行两次
      'el-button': { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
      'el-input': {
        props: ['modelValue'],
        emits: ['update:modelValue'],
        template:
          '<input data-testid="bulk-password" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
      },
    }
    const http = (await import('@/utils/http')).default as any
    http.get = vi.fn().mockResolvedValue({
      data: {
        data: {
          isArchived: false,
          projectStatus: 'execution',
          scenarios: FAKE_SCENARIOS,
          cycles: FAKE_CYCLES,
        },
      },
    })
    const wrapper = mount(WpBulkDialog, {
      props: { modelValue: true, projectId: 'proj-1' },
      global: { stubs: PASSWORD_STUBS },
    })
    await flushPromises()
    await wrapper.find(`[data-testid="bulk-scenario-${scenarioKey}"]`).trigger('click')
    await wrapper.find('[data-testid="bulk-password"]').setValue('pw-9')
    const execute = wrapper.findAll('button').find((b) => b.text().startsWith('开始'))
    expect(execute, '找不到执行按钮').toBeTruthy()
    await execute!.trigger('click')
    await flushPromises()

    const called = fnName === 'exportTemplates' ? exportTemplates : exportData
    const other = fnName === 'exportTemplates' ? exportData : exportTemplates
    expect(called).toHaveBeenCalledTimes(1)
    expect(other).not.toHaveBeenCalled()
    expect(called.mock.calls[0]).toContain('pw-9')
  })

  it('拉取失败时显示错误且不渲染任何卡片（不静默降级到硬写默认值）', async () => {
    const http = (await import('@/utils/http')).default as any
    http.get = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(WpBulkDialog, {
      props: { modelValue: true, projectId: 'proj-1' },
      global: { stubs: ELEMENT_STUBS },
    })
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('[data-testid^="bulk-scenario-"]').length).toBe(0)
    expect(wrapper.text()).toContain('无法读取导入导出场景说明')
  })
})

/**
 * 循环清单由后端下发 + 密码即时校验
 *
 * spec: environment-hygiene-deps-and-scratch-schemas（Requirement 8.5 / 8.4）
 * 缘起（真栈实测）：对话框写死 D~N 十一个循环且默认全选，而 ACNR catalog 里 E、J
 * 一张可导入导出的 Tab 都没有 ⇒ 用户勾上去、导出「成功」、包里没有它们的任何文件。
 */
describe('WpBulkDialog — 循环清单与密码校验', () => {
  const CYCLES = [
    { code: 'D', name: '销售收入', supported: true, unsupportedReason: '' },
    { code: 'E', name: '货币资金', supported: false, unsupportedReason: '该循环暂未接入批量导入导出' },
    { code: 'F', name: '采购存货', supported: true, unsupportedReason: '' },
  ]

  const SCENARIOS = [
    {
      key: 'blank_template',
      label: '场景1',
      artifactNote: 'n',
      timingNote: 't',
      exportEndpoint: '/x/export-templates',
      importEndpoint: null,
      mode: 'template',
      direction: 'export',
      archivedAllowed: true,
      disabled: false,
      disabledReason: null,
    },
  ]

  /** 暴露 disabled / value / 密码输入，便于对置灰与按钮可用性下断言 */
  const STUBS = {
    ...ELEMENT_STUBS,
    'el-checkbox': {
      props: ['disabled', 'value', 'label', 'title', 'modelValue', 'indeterminate'],
      template:
        '<label :data-cycle="value" :data-disabled="disabled ? \'1\' : \'0\'" :title="title"><slot /></label>',
    },
    'el-button': {
      props: ['disabled'],
      emits: ['click'],
      template:
        '<button :disabled="disabled" :data-disabled="disabled ? \'1\' : \'0\'" @click="$emit(\'click\')"><slot /></button>',
    },
    'el-input': {
      props: ['modelValue'],
      emits: ['update:modelValue'],
      template:
        '<input data-testid="bulk-password" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    },
    'el-form-item': {
      props: ['label', 'error'],
      template: '<div><span>{{ label }}</span><slot /><span class="fi-error">{{ error }}</span></div>',
    },
  }

  async function mountDialog(payload: Record<string, unknown>) {
    const http = (await import('@/utils/http')).default as any
    http.get = vi.fn().mockResolvedValue({
      data: { data: { isArchived: false, projectStatus: 'execution', ...payload } },
    })
    const wrapper = mount(WpBulkDialog, {
      props: { modelValue: true, projectId: 'proj-1' },
      global: { stubs: STUBS },
    })
    await flushPromises()
    await wrapper.vm.$nextTick()
    return wrapper
  }

  beforeEach(() => {
    exportTemplates.mockClear()
    exportData.mockClear()
  })

  it('循环清单来自后端；不支持的置灰并显示原因', async () => {
    const wrapper = await mountDialog({ scenarios: SCENARIOS, cycles: CYCLES })
    await wrapper.find('[data-testid="bulk-scenario-blank_template"]').trigger('click')

    const boxes = wrapper.findAll('[data-cycle]')
    expect(boxes.map((b) => b.attributes('data-cycle'))).toEqual(['D', 'E', 'F'])
    const byCode = Object.fromEntries(boxes.map((b) => [b.attributes('data-cycle'), b]))
    expect(byCode.D.attributes('data-disabled')).toBe('0')
    expect(byCode.F.attributes('data-disabled')).toBe('0')
    // E 不支持 ⇒ 置灰，且原因来自后端（不是前端自己拼的文案）
    expect(byCode.E.attributes('data-disabled')).toBe('1')
    expect(byCode.E.attributes('title')).toBe(CYCLES[1].unsupportedReason)
    expect(wrapper.text()).toContain(CYCLES[1].unsupportedReason)
    // 名称用驾驶舱那份中文，不再是「D - D 销售循环」这种编码重复
    expect(wrapper.text()).toContain('D 销售收入')
    expect(wrapper.text()).not.toContain('D - D')
  })

  it('不支持的循环不默认勾选，也不进导出参数', async () => {
    const wrapper = await mountDialog({ scenarios: SCENARIOS, cycles: CYCLES })
    await wrapper.find('[data-testid="bulk-scenario-blank_template"]').trigger('click')

    const execute = wrapper.findAll('button').find((b) => b.text().startsWith('开始'))
    await execute!.trigger('click')
    await flushPromises()

    expect(exportTemplates).toHaveBeenCalledTimes(1)
    // 🔴 这是本轮最核心的行为判据：E 不能出现在请求里
    expect(exportTemplates.mock.calls[0][0]).toEqual(['D', 'F'])
  })

  it('后端不下发 cycles 时显式报错，不退回写死的列表', async () => {
    const wrapper = await mountDialog({ scenarios: SCENARIOS })  // 故意不给 cycles
    expect(wrapper.findAll('[data-testid^="bulk-scenario-"]').length).toBe(0)
    expect(wrapper.text()).toContain('无法读取导入导出场景说明')
    // 不得出现任何硬写的循环名
    expect(wrapper.text()).not.toContain('销售收入')
  })

  it('中文密码即时报错且执行按钮不可用', async () => {
    const wrapper = await mountDialog({ scenarios: SCENARIOS, cycles: CYCLES })
    await wrapper.find('[data-testid="bulk-scenario-blank_template"]').trigger('click')

    const findExecute = () => wrapper.findAll('button').find((b) => b.text().startsWith('开始'))!
    // 合法初态：按钮可用
    expect(findExecute().attributes('data-disabled')).toBe('0')

    const passwordError = () =>
      wrapper.find('[data-testid="bulk-password-item"] .fi-error').text()

    await wrapper.find('[data-testid="bulk-password"]').setValue('审计-Pa55!')
    await wrapper.vm.$nextTick()
    expect(passwordError()).toContain('不支持的字符')
    expect(findExecute().attributes('data-disabled')).toBe('1')

    // 点了也不会发请求（不只靠样式拦）
    await findExecute().trigger('click')
    await flushPromises()
    expect(exportTemplates).not.toHaveBeenCalled()

    // 改成合法 ASCII ⇒ 恢复可用（正向对照，否则「永远禁用」也会让上面全绿）
    await wrapper.find('[data-testid="bulk-password"]').setValue('Audit-Pa55!')
    await wrapper.vm.$nextTick()
    expect(passwordError()).toBe('')
    expect(findExecute().attributes('data-disabled')).toBe('0')
  })

  it('超长密码同样拦住', async () => {
    const wrapper = await mountDialog({ scenarios: SCENARIOS, cycles: CYCLES })
    await wrapper.find('[data-testid="bulk-scenario-blank_template"]').trigger('click')
    await wrapper.find('[data-testid="bulk-password"]').setValue('x'.repeat(129))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="bulk-password-item"] .fi-error').text()).toContain('过长')
  })
})
