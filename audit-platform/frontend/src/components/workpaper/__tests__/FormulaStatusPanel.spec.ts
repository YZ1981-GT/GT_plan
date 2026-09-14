/**
 * FormulaStatusPanel vitest
 *
 * spec: d-cycle-four-table-extraction-formulas Task 4.1 / 4.2
 *   (Requirements 5.1–5.7 / Property 5, 6, 7, 11)
 *
 * 覆盖：
 * - 真实端点数据渲染（items + extraction.tierA/tierB 按 sheet 分组）
 * - extraction 缺失（灰度关 / 非 D 循环）→ 仅 items 不崩溃
 * - Tier A 编辑 → PUT 携正确 payload
 * - 422（FORMULA_UNSUPPORTED_FUNCTION / FORMULA_REF_NOT_FOUND）清晰 ElMessage
 * - 恢复默认 → DELETE 对应 formula id
 * - 禁用 → PUT category='__disabled__'
 * - 只读角色 → Tier A 操作按钮不渲染
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FormulaStatusPanel from '../FormulaStatusPanel.vue'

// ── mocks ──────────────────────────────────────────────
const mockApiGet = vi.fn()
const mockApiPut = vi.fn()
const mockApiDelete = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...a: any[]) => mockApiGet(...a),
    put: (...a: any[]) => mockApiPut(...a),
    delete: (...a: any[]) => mockApiDelete(...a),
  },
}))

const mockError = vi.fn()
const mockSuccess = vi.fn()
const mockWarning = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: {
    error: (...a: any[]) => mockError(...a),
    success: (...a: any[]) => mockSuccess(...a),
    warning: (...a: any[]) => mockWarning(...a),
    info: vi.fn(),
  },
}))

let mockCanDo = vi.fn().mockReturnValue(true)
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ canDo: (...a: any[]) => mockCanDo(...a) }),
}))

// ── 测试数据 ────────────────────────────────────────────
function fullResponse() {
  return {
    wp_id: 'wp-1',
    count: 1,
    items: [
      {
        id: 'f-1',
        sheet_name: 'D6-1',
        target_cell: 'D6-1-block1-priorUnadjusted',
        expression: "TB('1141','期初余额')",
        category: null,
        description: '期初未审',
        formula_type: 'auto_calc',
      },
    ],
    extraction: {
      wp_code: 'D6',
      enabled: true,
      note: '测试说明文案',
      tierA: [
        {
          wp_code: 'D6',
          sheet_name: 'D6-1',
          anchor: 'D6-1-block1-endUnadjusted',
          expression: "TB('1141','期末余额')",
          formula_type: 'auto_calc',
          description: '合同资产原值-期末未审',
          source: 'preset',
          tier: 'A',
          value: 123456,
        },
        {
          wp_code: 'D6',
          sheet_name: 'D6-1',
          anchor: 'D6-1-block1-priorUnadjusted',
          expression: "TB('1141','期初余额')",
          formula_type: 'auto_calc',
          description: '期初未审',
          source: 'custom',
          tier: 'A',
          value: null,
        },
      ],
      tierB: [
        {
          wp_code: 'D6',
          sheet_name: 'D6-2',
          anchor: 'D6-2-rows',
          description: '明细 ← tb_aux_balance 1141 归集',
          source: 'prefill',
          editable: false,
          tier: 'B',
          value: null,
        },
      ],
    },
  }
}

const stubs = {
  ElTag: { template: '<span class="el-tag"><slot /></span>' },
  ElEmpty: { template: '<div class="el-empty">{{ description }}</div>', props: ['description'] },
  ElButton: {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    inheritAttrs: false,
  },
  ElDialog: {
    template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>',
    props: ['modelValue'],
  },
  ElForm: { template: '<form><slot /></form>' },
  ElFormItem: { template: '<div class="el-form-item"><slot /></div>' },
  ElInput: {
    template: '<input class="el-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue'],
  },
}

function mountPanel() {
  return mount(FormulaStatusPanel, {
    props: { projectId: 'p-1', wpId: 'wp-1', year: 2025 },
    global: {
      stubs,
      directives: { loading: {} },
    },
  })
}

/** 按文本找按钮 */
function findBtnByText(wrapper: any, text: string) {
  return wrapper.findAll('button.el-button').filter((b: any) => b.text() === text)
}

describe('FormulaStatusPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCanDo = vi.fn().mockReturnValue(true)
  })

  it('调真实端点并解析 items + extraction，按 sheet 分组三层展示（R5.1/5.2）', async () => {
    mockApiGet.mockResolvedValue(fullResponse())
    const wrapper = mountPanel()
    await flushPromises()

    // 真实端点（不再是 projects 作用域）
    expect(mockApiGet).toHaveBeenCalledWith('/api/workpapers/wp-1/formulas')

    const text = wrapper.text()
    // 汇总计数
    expect(text).toContain('持久化 1')
    expect(text).toContain('Tier A 2')
    expect(text).toContain('Tier B 1')
    // 说明文案
    expect(text).toContain('测试说明文案')
    // 分组 sheet 标题
    expect(text).toContain('D6-1')
    expect(text).toContain('D6-2')
    // 三层标题
    expect(text).toContain('持久化公式')
    expect(text).toContain('Tier A 提取公式（可编辑）')
    expect(text).toContain('Tier B 自动预填来源（只读）')
    // 值复用 seed（不重求值）
    expect(text).toContain('123,456')
    // source 徽标
    expect(text).toContain('预设')
    expect(text).toContain('自定义')
    expect(text).toContain('自动预填来源')
  })

  it('Tier A 展示后端求值结果 value（有值显示数字、None 显示 —）（d-cycle-tier-a-writeback Task 3.1 / R2）', async () => {
    mockApiGet.mockResolvedValue(fullResponse())
    const wrapper = mountPanel()
    await flushPromises()

    // 收集全部 Tier A「当前值：...」文本
    const valueTexts = wrapper
      .findAll('.formula-value')
      .map((n: any) => n.text())
    // 有值绑定（value=123456）→ 显示千分位真实求值结果（不再恒 —）
    expect(valueTexts.some((t: string) => t.includes('当前值：123,456'))).toBe(true)
    // value=null 绑定 → 显示 —（占位）
    expect(valueTexts.some((t: string) => t.includes('当前值：—'))).toBe(true)
  })

  it('extraction 缺失时仅展示 items，不崩溃（R7.1）', async () => {
    mockApiGet.mockResolvedValue({ wp_id: 'wp-1', count: 1, items: fullResponse().items })
    const wrapper = mountPanel()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('持久化 1')
    expect(text).toContain('Tier A 0')
    expect(text).toContain('Tier B 0')
    expect(text).toContain('持久化公式')
    // 无 extraction → 无 Tier A/B 分层
    expect(text).not.toContain('Tier A 提取公式（可编辑）')
    expect(text).not.toContain('Tier B 自动预填来源（只读）')
  })

  it('编辑 Tier A → PUT 携正确 payload（R5.2）', async () => {
    mockApiGet.mockResolvedValue(fullResponse())
    mockApiPut.mockResolvedValue({ saved: {} })
    const wrapper = mountPanel()
    await flushPromises()

    // 第一个「编辑」= preset 绑定（D6-1-block1-endUnadjusted）
    await findBtnByText(wrapper, '编辑')[0].trigger('click')
    await flushPromises()
    // 弹窗保存
    await findBtnByText(wrapper, '保存')[0].trigger('click')
    await flushPromises()

    expect(mockApiPut).toHaveBeenCalledTimes(1)
    const [url, body] = mockApiPut.mock.calls[0]
    expect(url).toBe('/api/workpapers/wp-1/formulas')
    expect(body.target_cell).toBe('D6-1-block1-endUnadjusted')
    expect(body.sheet_name).toBe('D6-1')
    expect(body.expression).toBe("TB('1141','期末余额')")
    expect(body.year).toBe(2025)
    expect(body.category).toBeNull()
    expect(mockSuccess).toHaveBeenCalled()
  })

  it('422 FORMULA_UNSUPPORTED_FUNCTION → 清晰 ElMessage（Property 6）', async () => {
    mockApiGet.mockResolvedValue(fullResponse())
    mockApiPut.mockRejectedValue({
      response: {
        data: {
          detail: {
            error_code: 'FORMULA_UNSUPPORTED_FUNCTION',
            unsupported_functions: ['AUX'],
            message: '公式含不受支持的函数 AUX',
          },
        },
      },
    })
    const wrapper = mountPanel()
    await flushPromises()
    await findBtnByText(wrapper, '编辑')[0].trigger('click')
    await flushPromises()
    await findBtnByText(wrapper, '保存')[0].trigger('click')
    await flushPromises()

    expect(mockError).toHaveBeenCalledWith('公式含不受支持的函数 AUX')
  })

  it('422 FORMULA_REF_NOT_FOUND → 清晰 ElMessage（Property 7）', async () => {
    mockApiGet.mockResolvedValue(fullResponse())
    mockApiPut.mockRejectedValue({
      response: {
        data: {
          detail: {
            error_code: 'FORMULA_REF_NOT_FOUND',
            issues: ["TB('9999','期末余额') 引用不存在"],
          },
        },
      },
    })
    const wrapper = mountPanel()
    await flushPromises()
    await findBtnByText(wrapper, '编辑')[0].trigger('click')
    await flushPromises()
    await findBtnByText(wrapper, '保存')[0].trigger('click')
    await flushPromises()

    expect(mockError).toHaveBeenCalledWith(
      expect.stringContaining("TB('9999','期末余额') 引用不存在"),
    )
  })

  it('恢复默认 → DELETE 对应 formula id（R5.4）', async () => {
    mockApiGet.mockResolvedValue(fullResponse())
    mockApiDelete.mockResolvedValue({ deleted: 'f-1' })
    const wrapper = mountPanel()
    await flushPromises()

    // 恢复默认仅出现在 custom 绑定（D6-1-block1-priorUnadjusted → 匹配 item f-1）
    const restoreBtns = findBtnByText(wrapper, '恢复默认')
    expect(restoreBtns.length).toBe(1)
    await restoreBtns[0].trigger('click')
    await flushPromises()

    expect(mockApiDelete).toHaveBeenCalledWith('/api/workpapers/wp-1/formulas/f-1')
    expect(mockSuccess).toHaveBeenCalled()
  })

  it('禁用 → PUT category=__disabled__（R5.5）', async () => {
    mockApiGet.mockResolvedValue(fullResponse())
    mockApiPut.mockResolvedValue({ saved: {} })
    const wrapper = mountPanel()
    await flushPromises()

    // 第一个「禁用」= preset 绑定
    await findBtnByText(wrapper, '禁用')[0].trigger('click')
    await flushPromises()

    expect(mockApiPut).toHaveBeenCalledTimes(1)
    const [, body] = mockApiPut.mock.calls[0]
    expect(body.category).toBe('__disabled__')
    expect(body.target_cell).toBe('D6-1-block1-endUnadjusted')
  })

  it('只读角色 → Tier A 操作按钮不渲染（R5.7）', async () => {
    mockCanDo = vi.fn().mockReturnValue(false)
    mockApiGet.mockResolvedValue(fullResponse())
    const wrapper = mountPanel()
    await flushPromises()

    expect(findBtnByText(wrapper, '编辑').length).toBe(0)
    expect(findBtnByText(wrapper, '恢复默认').length).toBe(0)
    expect(findBtnByText(wrapper, '禁用').length).toBe(0)
    // 但内容仍可查看
    expect(wrapper.text()).toContain('Tier A 提取公式（可编辑）')
  })
})
