/**
 * GtAuditSheet.spec.ts — 审定表核心可编辑表格组件单元测试（Task 9）
 *
 * 验证：
 * 1. tableData 从 htmlData.audit_rows 构建并合并 tb_values 只读字段
 * 2. 自动计算：审定数 = 本期未审 + 调整 + 重分类
 * 3. 自动计算：变动额 = 审定数 - 期初审定；变动率 = 变动额 ÷ 期初审定
 * 4. 期初审定为 0 时变动率返回 null（显示 —）
 * 5. 行类型判定：分节行(isSection)/合计行(isComputed)/缩进渲染
 * 6. field-change 事件在编辑列变更时触发，readonly 不触发
 *
 * Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtAuditSheet, { type AuditSheetHtmlData } from '../GtAuditSheet.vue'

const globalStubs = {
  'el-empty': { template: '<div class="el-empty"><slot /></div>', props: ['description', 'imageSize'] },
  'el-alert': { template: '<div class="el-alert"><slot name="title" /></div>', props: ['type', 'closable'] },
  'el-dialog': {
    template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'appendToBody'],
  },
  'el-button': {
    template:
      '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled'],
    emits: ['click'],
  },
  'el-table': {
    template: '<div class="el-table"><slot /></div>',
    props: ['data', 'border', 'size', 'headerCellStyle', 'rowClassName'],
  },
  'el-table-column': {
    template:
      '<div class="el-table-column" :data-label="label"><template v-if="$slots.default"><div class="gas-cell" v-for="(r, i) in rows" :key="i"><slot :row="r" :$index="i" /></div></template></div>',
    props: ['label', 'width', 'minWidth', 'align', 'fixed'],
    computed: {
      rows(): Record<string, any>[] {
        const self = this as any
        const data = self.$parent?.$attrs?.data || self.$parent?.data || []
        return Array.isArray(data) ? data : []
      },
    },
  },
  'el-input-number': {
    template:
      '<input class="el-input-number" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', Number($event.target.value)); $emit(\'change\', Number($event.target.value))" />',
    props: ['modelValue', 'precision', 'controls', 'disabled', 'placeholder', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-input': {
    template:
      '<input class="el-input" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)" />',
    props: ['modelValue', 'disabled', 'placeholder', 'size'],
    emits: ['update:modelValue', 'change'],
  },
}

function buildHtmlData(): AuditSheetHtmlData {
  return {
    audit_rows: [
      {
        id: 'row-1',
        item: '一、应收票据',
        indent: 0,
        bold: true,
        isSection: true,
        isComputed: false,
        account_code: null,
        adj_amount: null,
        reclass_amount: null,
        reason: '',
      },
      {
        id: 'row-2',
        item: '原值',
        indent: 1,
        bold: false,
        isSection: false,
        isComputed: false,
        account_code: '1121',
        adj_amount: 5000,
        reclass_amount: 1000,
        reason: '确认坏账',
      },
      {
        id: 'row-3',
        item: '合计',
        indent: 0,
        bold: true,
        isSection: false,
        isComputed: true,
        account_code: null,
        adj_amount: null,
        reclass_amount: null,
        reason: '',
      },
    ],
    tb_values: {
      'row-2': {
        opening_unadjusted: 100000,
        current_unadjusted: 120000,
        sys_aje: 0,
        sys_rje: 0,
      },
    },
  }
}

function mountSheet(htmlData: AuditSheetHtmlData, readonly = false) {
  return mount(GtAuditSheet, {
    props: {
      wpId: 'wp-001',
      sheetName: '审定表D1-1',
      schema: {},
      htmlData,
      readonly,
    },
    global: { stubs: globalStubs },
  })
}

describe('GtAuditSheet — tableData 构建与 TB 合并', () => {
  it('从 audit_rows 构建 tableData 并合并 tb_values 只读字段', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.tableData.length).toBe(3)
    const detail = vm.tableData[1]
    expect(detail.id).toBe('row-2')
    expect(detail.opening_unadjusted).toBe(100000)
    expect(detail.current_unadjusted).toBe(120000)
  })

  it('htmlData 变化时重建 tableData', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    await wrapper.setProps({
      htmlData: {
        audit_rows: [
          { id: 'row-x', item: '新项目', indent: 1, account_code: '1122' },
        ],
        tb_values: { 'row-x': { current_unadjusted: 50000, opening_unadjusted: 40000 } },
      },
    })
    await nextTick()
    expect(vm.tableData.length).toBe(1)
    expect(vm.tableData[0].current_unadjusted).toBe(50000)
  })
})

describe('GtAuditSheet — 自动计算', () => {
  it('审定数 = 本期未审 + 账项调整 + 重分类', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const row = vm.tableData[1]
    // 120000 + 5000 + 1000
    expect(vm.auditedAmount(row)).toBe(126000)
  })

  it('期初审定 = 期初未审', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.openingAudited(vm.tableData[1])).toBe(100000)
  })

  it('变动额 = 审定数 - 期初审定', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    // 126000 - 100000
    expect(vm.changeAmount(vm.tableData[1])).toBe(26000)
  })

  it('变动率 = 变动额 ÷ 期初审定', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    // 26000 / 100000 = 0.26
    expect(vm.changeRate(vm.tableData[1])).toBeCloseTo(0.26, 6)
  })

  it('期初审定为 0 时变动率返回 null', () => {
    const wrapper = mountSheet({
      audit_rows: [{ id: 'row-1', item: '无期初', indent: 1, current_unadjusted: 8000 }],
      tb_values: { 'row-1': { opening_unadjusted: 0, current_unadjusted: 8000 } },
    })
    const vm = wrapper.vm as any
    expect(vm.openingAudited(vm.tableData[0])).toBe(0)
    expect(vm.changeRate(vm.tableData[0])).toBeNull()
  })

  it('调整/未审为 null 时按 0 计算审定数', () => {
    const wrapper = mountSheet({
      audit_rows: [{ id: 'row-1', item: '空值行', indent: 1 }],
      tb_values: {},
    })
    const vm = wrapper.vm as any
    expect(vm.auditedAmount(vm.tableData[0])).toBe(0)
  })
})

describe('GtAuditSheet — 行类型与渲染', () => {
  it('分节行/合计行/bold 行加粗判定', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.isBoldRow(vm.tableData[0])).toBe(true) // isSection
    expect(vm.isBoldRow(vm.tableData[1])).toBe(false) // 普通明细
    expect(vm.isBoldRow(vm.tableData[2])).toBe(true) // isComputed
  })

  it('可编辑行判定：分节行/合计行不可编辑', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.isEditableRow(vm.tableData[0])).toBe(false) // isSection
    expect(vm.isEditableRow(vm.tableData[1])).toBe(true) // 明细可编辑
    expect(vm.isEditableRow(vm.tableData[2])).toBe(false) // isComputed
  })

  it('缩进层级正确保留', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.tableData[0].indent).toBe(0)
    expect(vm.tableData[1].indent).toBe(1)
  })

  it('空 audit_rows 显示空态', () => {
    const wrapper = mountSheet({ audit_rows: [], tb_values: {} })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })
})

describe('GtAuditSheet — field-change 事件', () => {
  it('编辑列变更触发 field-change', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const row = vm.tableData[1]
    // 通过查找编辑列 input 触发 change，断言 field-change 携带正确 rowId
    const numberInputs = wrapper.findAll('.el-input-number')
    expect(numberInputs.length).toBeGreaterThan(0)
    await numberInputs[0].setValue('9999')
    await numberInputs[0].trigger('input')
    await nextTick()
    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
    expect((emitted![0][0] as any).rowId).toBe(row.id)
  })

  it('readonly 模式下编辑列禁用', () => {
    const wrapper = mountSheet(buildHtmlData(), true)
    const numberInputs = wrapper.findAll('.el-input-number')
    // readonly 透传到 disabled
    expect((numberInputs[0].element as HTMLInputElement).disabled).toBe(true)
  })
})

describe('GtAuditSheet — 保存（持久化分层）', () => {
  it('点击保存 emit save，载荷形如 { audit_rows }', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const saveBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('保存'))
    expect(saveBtn).toBeDefined()
    await saveBtn!.trigger('click')
    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as AuditSheetHtmlData
    expect(Array.isArray(payload.audit_rows)).toBe(true)
    expect(payload.audit_rows!.length).toBe(3)
  })

  it('保存载荷剥离 TB 实时值（opening/current_unadjusted/sys_aje/sys_rje）', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const payload = vm.buildSavePayload() as AuditSheetHtmlData
    // row-2 有合并的 TB 值，但保存载荷必须剥离
    const detail = payload.audit_rows!.find((r) => r.id === 'row-2')!
    expect(detail).toBeDefined()
    expect('opening_unadjusted' in detail).toBe(false)
    expect('current_unadjusted' in detail).toBe(false)
    expect('sys_aje' in detail).toBe(false)
    expect('sys_rje' in detail).toBe(false)
    // 也不带 tb_values 顶层字段
    expect('tb_values' in payload).toBe(false)
  })

  it('保存载荷保留用户编辑列 + 行结构字段', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const payload = vm.buildSavePayload() as AuditSheetHtmlData
    const detail = payload.audit_rows!.find((r) => r.id === 'row-2')!
    // 用户编辑列
    expect(detail.adj_amount).toBe(5000)
    expect(detail.reclass_amount).toBe(1000)
    expect(detail.reason).toBe('确认坏账')
    // 行结构字段
    expect(detail.item).toBe('原值')
    expect(detail.indent).toBe(1)
    expect(detail.account_code).toBe('1121')
    expect(detail.isSection).toBe(false)
    expect(detail.isComputed).toBe(false)
    // 分节行结构标记保留
    const section = payload.audit_rows!.find((r) => r.id === 'row-1')!
    expect(section.isSection).toBe(true)
    expect(section.bold).toBe(true)
  })

  it('保存载荷反映用户最新编辑值', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    // 模拟用户编辑明细行
    vm.tableData[1].adj_amount = 8888
    vm.tableData[1].reason = '改后原因'
    const payload = vm.buildSavePayload() as AuditSheetHtmlData
    const detail = payload.audit_rows!.find((r) => r.id === 'row-2')!
    expect(detail.adj_amount).toBe(8888)
    expect(detail.reason).toBe('改后原因')
  })

  it('readonly 模式点击保存不 emit；按钮禁用', async () => {
    const wrapper = mountSheet(buildHtmlData(), true)
    const saveBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('保存'))
    expect(saveBtn).toBeDefined()
    expect((saveBtn!.element as HTMLButtonElement).disabled).toBe(true)
    // 即便强制触发也不应 emit
    const vm = wrapper.vm as any
    vm.onSave()
    expect(wrapper.emitted('save')).toBeUndefined()
  })
})

/**
 * Task 14 — TB 消费 + 用户覆盖回退逻辑
 *
 * audited = current_unadjusted + (adj_amount ?? sys_aje ?? 0) + (reclass_amount ?? sys_rje ?? 0)
 *   - adj_amount === null/undefined → 回退 sys_aje
 *   - adj_amount === 0（用户显式填 0）→ 用 0（覆盖，不回退）
 *   - adj_amount 有值 → 覆盖 sys_aje
 *   reclass_amount/sys_rje 同矩阵
 * 自动计算列随 TB / 用户编辑联动重算
 *
 * Validates: Requirements 3.1, 3.4, 1.4
 */
describe('GtAuditSheet — TB 消费 + 用户覆盖回退（Task 14）', () => {
  /** 单明细行 fixture：可注入 adj/reclass 用户值 + sys_aje/sys_rje 系统参考值 */
  function singleRow(overrides: Record<string, unknown>): AuditSheetHtmlData {
    return {
      audit_rows: [
        {
          id: 'row-1',
          item: '原值',
          indent: 1,
          isSection: false,
          isComputed: false,
          account_code: '1121',
          adj_amount: null,
          reclass_amount: null,
          reason: '',
          ...overrides,
        },
      ],
      tb_values: {
        'row-1': {
          opening_unadjusted: 100000,
          current_unadjusted: 120000,
          sys_aje: 0,
          sys_rje: 0,
          // tb_values 注入的系统值可被 overrides 内 audit_rows 行内字段覆盖
          ...(overrides._tb as Record<string, unknown> | undefined),
        },
      },
    }
  }

  // ─── 账项调整（adj_amount）↔ sys_aje 回退矩阵 ───
  it('adj_amount=null + sys_aje 有值 → audited 用 sys_aje 回退', () => {
    const wrapper = mountSheet(singleRow({ adj_amount: null, _tb: { sys_aje: 3000 } }))
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    expect(vm.effectiveAdj(row)).toBe(3000)
    // 120000 + 3000(sys_aje 回退) + 0
    expect(vm.auditedAmount(row)).toBe(123000)
  })

  it('adj_amount=0（用户显式填 0）+ sys_aje 有值 → audited 用 0（覆盖，不回退）', () => {
    const wrapper = mountSheet(singleRow({ adj_amount: 0, _tb: { sys_aje: 3000 } }))
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    expect(vm.effectiveAdj(row)).toBe(0)
    // 120000 + 0(用户显式 0 覆盖) + 0
    expect(vm.auditedAmount(row)).toBe(120000)
  })

  it('adj_amount 有值 + sys_aje 有值 → 用户值覆盖 sys_aje', () => {
    const wrapper = mountSheet(singleRow({ adj_amount: 5000, _tb: { sys_aje: 3000 } }))
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    expect(vm.effectiveAdj(row)).toBe(5000)
    // 120000 + 5000(用户覆盖) + 0
    expect(vm.auditedAmount(row)).toBe(125000)
  })

  it('adj_amount=null + sys_aje=null → 回退 0', () => {
    const wrapper = mountSheet(singleRow({ adj_amount: null, _tb: { sys_aje: null } }))
    const vm = wrapper.vm as any
    expect(vm.effectiveAdj(vm.tableData[0])).toBe(0)
  })

  // ─── 重分类（reclass_amount）↔ sys_rje 回退矩阵 ───
  it('reclass_amount=null + sys_rje 有值 → audited 用 sys_rje 回退', () => {
    const wrapper = mountSheet(singleRow({ reclass_amount: null, _tb: { sys_rje: 2000 } }))
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    expect(vm.effectiveReclass(row)).toBe(2000)
    // 120000 + 0 + 2000(sys_rje 回退)
    expect(vm.auditedAmount(row)).toBe(122000)
  })

  it('reclass_amount=0（用户显式填 0）+ sys_rje 有值 → audited 用 0（覆盖，不回退）', () => {
    const wrapper = mountSheet(singleRow({ reclass_amount: 0, _tb: { sys_rje: 2000 } }))
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    expect(vm.effectiveReclass(row)).toBe(0)
    expect(vm.auditedAmount(row)).toBe(120000)
  })

  it('reclass_amount 有值 + sys_rje 有值 → 用户值覆盖 sys_rje', () => {
    const wrapper = mountSheet(singleRow({ reclass_amount: 1500, _tb: { sys_rje: 2000 } }))
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    expect(vm.effectiveReclass(row)).toBe(1500)
    // 120000 + 0 + 1500(用户覆盖)
    expect(vm.auditedAmount(row)).toBe(121500)
  })

  it('reclass_amount=null + sys_rje=null → 回退 0', () => {
    const wrapper = mountSheet(singleRow({ reclass_amount: null, _tb: { sys_rje: null } }))
    const vm = wrapper.vm as any
    expect(vm.effectiveReclass(vm.tableData[0])).toBe(0)
  })

  // ─── 双列同时回退 ───
  it('adj/reclass 均 null → audited 同时回退 sys_aje + sys_rje', () => {
    const wrapper = mountSheet(
      singleRow({ adj_amount: null, reclass_amount: null, _tb: { sys_aje: 3000, sys_rje: 2000 } }),
    )
    const vm = wrapper.vm as any
    // 120000 + 3000(sys_aje) + 2000(sys_rje)
    expect(vm.auditedAmount(vm.tableData[0])).toBe(125000)
  })

  // ─── 联动重算：用户编辑 adj_amount 后 audited 重算 ───
  it('用户编辑 adj_amount 后 audited/change/rate 重算（覆盖系统回退）', () => {
    const wrapper = mountSheet(singleRow({ adj_amount: null, _tb: { sys_aje: 3000 } }))
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    // 初始用 sys_aje 回退
    expect(vm.auditedAmount(row)).toBe(123000)
    // 用户编辑 → 覆盖
    row.adj_amount = 9000
    expect(vm.effectiveAdj(row)).toBe(9000)
    // 120000 + 9000 + 0
    expect(vm.auditedAmount(row)).toBe(129000)
    // 变动额 = 129000 - 100000；变动率 = 29000/100000
    expect(vm.changeAmount(row)).toBe(29000)
    expect(vm.changeRate(row)).toBeCloseTo(0.29, 6)
  })

  // ─── 联动重算：tb_values 变化（重新导入 TB）后 audited 重算 ───
  it('tb_values 变化（setProps 新 htmlData）后 audited 随 TB 重算', async () => {
    const wrapper = mountSheet(singleRow({ adj_amount: null, _tb: { sys_aje: 3000 } }))
    const vm = wrapper.vm as any
    expect(vm.auditedAmount(vm.tableData[0])).toBe(123000)

    // 模拟重新导入 TB：current_unadjusted + sys_aje 都变化
    await wrapper.setProps({
      htmlData: {
        audit_rows: [
          {
            id: 'row-1',
            item: '原值',
            indent: 1,
            isSection: false,
            isComputed: false,
            account_code: '1121',
            adj_amount: null,
            reclass_amount: null,
            reason: '',
          },
        ],
        tb_values: {
          'row-1': {
            opening_unadjusted: 100000,
            current_unadjusted: 200000,
            sys_aje: 8000,
            sys_rje: 0,
          },
        },
      },
    })
    await nextTick()
    const row = vm.tableData[0]
    // 200000 + 8000(新 sys_aje 回退) + 0
    expect(row.current_unadjusted).toBe(200000)
    expect(row.sys_aje).toBe(8000)
    expect(vm.auditedAmount(row)).toBe(208000)
  })

  // ─── 系统参考值 placeholder 提示 ───
  it('未编辑调整时 placeholder 展示系统参考值；无系统值显示 —', () => {
    const wrapper = mountSheet(
      singleRow({ adj_amount: null, reclass_amount: null, _tb: { sys_aje: 3000, sys_rje: null } }),
    )
    const vm = wrapper.vm as any
    const row = vm.tableData[0]
    // sys_aje=3000 → 千分位格式提示
    expect(vm.adjPlaceholder(row)).toBe('3,000.00')
    // sys_rje=null → —
    expect(vm.reclassPlaceholder(row)).toBe('—')
  })
})

describe('GtAuditSheet — 工具栏（全屏/公式/还原）', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('全屏按钮切换 isFullscreen 并绑定 .gt-fullscreen 根类', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.isFullscreen).toBe(false)
    expect(wrapper.find('.gt-audit-sheet').classes()).not.toContain('gt-fullscreen')

    const fsBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('全屏'))
    expect(fsBtn).toBeDefined()
    await fsBtn!.trigger('click')
    await nextTick()

    expect(vm.isFullscreen).toBe(true)
    expect(wrapper.find('.gt-audit-sheet').classes()).toContain('gt-fullscreen')
    expect(fsBtn!.text()).toContain('退出全屏')

    // 再次点击退出全屏
    await fsBtn!.trigger('click')
    await nextTick()
    expect(vm.isFullscreen).toBe(false)
    expect(wrapper.find('.gt-audit-sheet').classes()).not.toContain('gt-fullscreen')
  })

  it('全屏按钮在 readonly 下仍可用（非编辑动作）', () => {
    const wrapper = mountSheet(buildHtmlData(), true)
    const fsBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('全屏'))
    expect(fsBtn).toBeDefined()
    expect((fsBtn!.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('公式按钮 emit open-formula，携带 sheetName 上下文', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const formulaBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('公式'))
    expect(formulaBtn).toBeDefined()
    await formulaBtn!.trigger('click')

    const emitted = wrapper.emitted('open-formula')
    expect(emitted).toBeDefined()
    expect((emitted![0][0] as any).sheetName).toBe('审定表D1-1')
  })

  it('还原按钮 confirm 后 emit restore', async () => {
    const confirmSpy = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValueOnce({ action: 'confirm' } as any)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => ({}) as any)

    const wrapper = mountSheet(buildHtmlData())
    const restoreBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('还原'))
    expect(restoreBtn).toBeDefined()
    await restoreBtn!.trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('restore')).toBeDefined()
  })

  it('还原按钮用户取消时不 emit restore', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValueOnce('cancel')

    const wrapper = mountSheet(buildHtmlData())
    const restoreBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('还原'))
    await restoreBtn!.trigger('click')
    await flushPromises()

    expect(wrapper.emitted('restore')).toBeUndefined()
  })

  it('readonly 模式禁用 公式 / 还原 / 保存（全屏不禁用）', () => {
    const wrapper = mountSheet(buildHtmlData(), true)
    const btns = wrapper.findAll('.el-button')
    const find = (label: string) => btns.find((b) => b.text().includes(label))

    expect((find('公式')!.element as HTMLButtonElement).disabled).toBe(true)
    expect((find('还原')!.element as HTMLButtonElement).disabled).toBe(true)
    expect((find('保存')!.element as HTMLButtonElement).disabled).toBe(true)
    // 全屏始终可用
    expect((find('全屏')!.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('readonly 模式强制调用 onOpenFormula/onRestore 不 emit', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({ action: 'confirm' } as any)
    const wrapper = mountSheet(buildHtmlData(), true)
    const vm = wrapper.vm as any
    vm.onOpenFormula()
    await vm.onRestore()
    await flushPromises()
    expect(wrapper.emitted('open-formula')).toBeUndefined()
    expect(wrapper.emitted('restore')).toBeUndefined()
    // readonly 提前 return，confirm 不应被调用
    expect(confirmSpy).not.toHaveBeenCalled()
  })
})
