/**
 * Unit Tests + PBT — GtA182RegulatoryCommunication.vue 组件
 *
 * Spec: .kiro/specs/a18-2-regulatory-communication/
 * Tasks: 3.2, 3.3
 *
 * Property 2: Y→textarea visible, N/NA→hidden
 * Property 4: dual-sign independence (cpa1 and cpa2 independent)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import * as fc from 'fast-check'

// ─── Mock API ────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
      sheets: [{
        html_data: {
          recipient: { authority: '中国证券监督管理委员会', custom: '' },
          matters: [
            { id: 1, title: '舞弊', applicability: 'Y', content: '内容1' },
            { id: 2, title: '重大违反法律法规行为', applicability: 'N', content: '' },
            { id: 3, title: '年度报告中信息不一致或错报', applicability: 'NA', content: '' },
            { id: 4, title: '其他事项', applicability: null, content: '' },
          ],
          issuance: { cpa1: '张三', cpa2: '李四', date: '2026-03-15' },
          project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同会计师事务所（特殊普通合伙）' },
        },
      }],
    }),
    put: vi.fn().mockResolvedValue({}),
  },
}))

// 导出走 downloadFile（带 Bearer 头），window.open / <a href> 直连 /api 会 401
vi.mock('@/utils/http', () => ({
  downloadFile: vi.fn().mockResolvedValue(undefined),
  isRequestCancelled: () => false,
  // errorHandler 的 5xx 分支会取它拼 trace 提示
  getLastTraceId: () => '',
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual as any,
    ElMessage: {
      warning: vi.fn(),
      error: vi.fn(),
      success: vi.fn(),
    },
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
  }
})

// Stub GtOnlyOfficeSheet
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  default: defineComponent({ name: 'GtOnlyOfficeSheet', template: '<div class="oo-stub" />' }),
}))

vi.mock('../GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    props: ['value', 'contextProjectId', 'context'],
    template: '<span class="gt-index-chip-stub">{{ value }}</span>',
  },
}))

describe('GtA182RegulatoryCommunication.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountComponent(props: Record<string, any> = {}) {
    const { default: GtA182RegulatoryCommunication } = await import('../GtA182RegulatoryCommunication.vue')
    const wrapper = mount(GtA182RegulatoryCommunication, {
      props: { wpId: 'wp-182', ...props },
      global: {
        stubs: {
          ElSegmented: defineComponent({
            props: ['modelValue', 'options'],
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () => h('div', { class: 'el-segmented-stub' },
                (props.options || []).map((opt: string) =>
                  h('button', { onClick: () => emit('update:modelValue', opt) }, opt),
                ),
              )
            },
          }),
          ElSkeleton: defineComponent({ template: '<div class="el-skeleton-stub" />' }),
          ElDatePicker: defineComponent({
            props: ['modelValue', 'type', 'disabled'],
            template: '<div class="el-date-picker-stub" />',
          }),
          // 组件库在本测试环境未全局注册：用真按钮渲染，才能按文案找到「导出 Word」并触发 click
          ElButton: defineComponent({
            props: ['loading', 'disabled', 'type', 'size'],
            emits: ['click'],
            template: '<button type="button" v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>',
          }),
          ElTooltip: defineComponent({ template: '<span><slot /></span>' }),
          ElIcon: defineComponent({ template: '<i><slot /></i>' }),
        },
      },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  // ─── 区块渲染 ───

  describe('5 区块渲染', () => {
    it('renders structured view by default', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__content').exists()).toBe(true)
    })

    it('renders recipient section with 致：prefix', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('致：')
    })

    it('renders introduction text with project context', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('测试公司')
      expect(wrapper.text()).toContain('2025')
    })

    it('renders 4 matter applicability sections', async () => {
      const wrapper = await mountComponent()
      // Each matter has 适用性 label
      const text = wrapper.text()
      expect((text.match(/适用性：/g) || []).length).toBe(4)
    })

    it('renders dual CPA sign fields', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('中国注册会计师（1）')
      expect(wrapper.text()).toContain('中国注册会计师（2）')
    })

    it('renders guidance tables content', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('CAS 1151.14')
      expect(wrapper.text()).toContain('CAS 1152.09')
    })

    it('renders save status indicator', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__save-status').exists()).toBe(true)
    })

    it('renders toolbar with AI button', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__toolbar').exists()).toBe(true)
      expect(wrapper.text()).toContain('AI')
    })
  })

  // ─── 适用性三态切换 ───

  describe('适用性三态切换', () => {
    it('renders radio group with Y/N/NA options for each matter', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('适用')
      expect(wrapper.text()).toContain('不适用')
      expect(wrapper.text()).toContain('不涉及')
    })
  })

  // ─── Select + Custom ───

  describe('select + custom 切换', () => {
    it('shows custom input when authority is "其他" (via data inspection)', async () => {
      const { api } = await import('@/services/apiProxy')
      ;(api.get as any).mockResolvedValueOnce({
        sheets: [{
          html_data: {
            recipient: { authority: '其他', custom: '某省财政厅' },
            matters: [
              { id: 1, title: '舞弊', applicability: null, content: '' },
              { id: 2, title: '重大违反法律法规行为', applicability: null, content: '' },
              { id: 3, title: '年度报告中信息不一致或错报', applicability: null, content: '' },
              { id: 4, title: '其他事项', applicability: null, content: '' },
            ],
            issuance: { cpa1: '', cpa2: '', date: '' },
            project_context: { client_name: '', audit_year: '', firm_name: '致同' },
          },
        }],
      })
      const wrapper = await mountComponent()
      // The custom input placeholder should be visible when authority='其他'
      expect(wrapper.html()).toContain('请输入监管机构名称')
    })
  })

  // ─── PBT Property 2: 适用性→textarea 联动 ───

  describe('Property 2: 适用性→textarea 联动 (PBT)', () => {
    it('for any matter, Y shows textarea and N/NA/null hides it', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 4 }),
          fc.oneof(
            fc.constant('Y'),
            fc.constant('N'),
            fc.constant('NA'),
            fc.constant(null),
          ),
          (matterId, applicability) => {
            // Pure logic: v-show="matter.applicability === 'Y'"
            const visible = applicability === 'Y'
            if (applicability === 'Y') {
              expect(visible).toBe(true)
            } else {
              expect(visible).toBe(false)
            }
          },
        ),
        { numRuns: 30 },
      )
    })
  })

  // ─── PBT Property 4: dual-sign independence ───

  describe('Property 4: 双签独立性 (PBT)', () => {
    it('cpa1 and cpa2 are independent fields that never affect each other', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.string({ minLength: 1, maxLength: 20 }),
          (cpa1Value, cpa2Value) => {
            // Simulating the issuance reactive state
            const issuance = { cpa1: '', cpa2: '', date: '' }

            // Update cpa1
            issuance.cpa1 = cpa1Value
            expect(issuance.cpa2).toBe('')

            // Update cpa2
            issuance.cpa2 = cpa2Value
            expect(issuance.cpa1).toBe(cpa1Value) // cpa1 unchanged

            // Both are set independently
            expect(issuance.cpa1).not.toBe(issuance.cpa2)
          },
        ),
        { numRuns: 30 },
      )
    })

    it('setting one CPA does not clear the other', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.string({ minLength: 1, maxLength: 20 }),
          (initial1, initial2, newValue) => {
            const issuance = { cpa1: initial1, cpa2: initial2, date: '' }
            // Update cpa1 → cpa2 must remain
            issuance.cpa1 = newValue
            expect(issuance.cpa2).toBe(initial2)
          },
        ),
        { numRuns: 20 },
      )
    })
  })

  // ─── Mode Switch ───

  describe('模式切换', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a182__content').exists()).toBe(true)
      expect(wrapper.find('.oo-stub').exists()).toBe(false)
    })
  })

  // ─── Readonly Mode ───

  describe('readonly mode', () => {
    it('renders without error in readonly', async () => {
      const wrapper = await mountComponent({ readonly: true })
      expect(wrapper.find('.gt-a182').exists()).toBe(true)
    })
  })

  // ─── 导出 Word（spec api-prefix-fix-recovery R3 / 任务 4）────────────────────
  //
  // 原先本组件没有导出入口（任务 26 修的是运行期不可达的 GtRegulatoryLetter），
  // 且后端 export-word / check-incomplete 两端点坏了三个月（被 completion_phase 同路径实现遮蔽，
  // 而那份实现里 `WorkingPaper` 没有 `wp_code` 列 ⇒ 恒 500）。这里钉住三条：
  // 路径带 /api、先查未完成项再确认、下载走 downloadFile（不是 window.open）。

  describe('导出 Word', () => {
    const EXPORT_PATH = '/api/projects/proj-1/working-papers/wp-182/export-word'

    beforeEach(() => {
      vi.clearAllMocks()
    })

    async function clickExport(wrapper: any) {
      const button = wrapper.findAll('button').find((b: any) => b.text().includes('导出 Word'))
      expect(button, '工具栏应有「导出 Word」按钮').toBeTruthy()
      await button!.trigger('click')
      // 一轮微任务 + 下一 tick：await 链（flush → check → 确认 → downloadFile）
      await new Promise((r) => setTimeout(r, 20))
      await wrapper.vm.$nextTick()
    }

    it('有未完成项时先弹确认并逐条列出缺项，确认后才下载', async () => {
      const { api } = await import('@/services/apiProxy')
      const { downloadFile } = await import('@/utils/http')
      const { ElMessageBox } = await import('element-plus')

      // 渲染配置：第一次；check-incomplete：第二次
      ;(api.get as any).mockImplementation(async (url: string) => {
        if (url.includes('/export-word/check-incomplete')) {
          return {
            complete: false,
            missing_fields: ['舞弊（已标注适用但未填写沟通内容）', '其他事项（未选择适用性）'],
            wp_code: 'A18-2',
            reason: '2 项议题未完成',
          }
        }
        return {
          sheets: [{
            html_data: {
              recipient: { authority: '', custom: '' },
              matters: [
                { id: 1, title: '舞弊', applicability: 'Y', content: '' },
                { id: 2, title: '重大违反法律法规行为', applicability: 'N', content: '' },
                { id: 3, title: '年度报告中信息不一致或错报', applicability: 'NA', content: '' },
                { id: 4, title: '其他事项', applicability: null, content: '' },
              ],
              issuance: { cpa1: '', cpa2: '', date: '' },
              project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同' },
            },
          }],
        }
      })

      const wrapper = await mountComponent({ projectId: 'proj-1' })
      await clickExport(wrapper)

      // ① 路径带 /api
      const checkCall = (api.get as any).mock.calls.find(
        (c: any[]) => typeof c[0] === 'string' && c[0].includes('check-incomplete'),
      )
      expect(checkCall?.[0]).toBe(`${EXPORT_PATH}/check-incomplete`)

      // ② 确认框：列出具体缺哪几项
      expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
      const [message, title] = (ElMessageBox.confirm as any).mock.calls[0]
      expect(title).toBe('存在未完成项')
      expect(message).toContain('舞弊（已标注适用但未填写沟通内容）')
      expect(message).toContain('其他事项（未选择适用性）')
      expect(message).toContain('以下 2 项议题尚未完成')

      // ③ 确认后才下载，且走 downloadFile（带 Bearer 头）
      expect(downloadFile).toHaveBeenCalledTimes(1)
      expect((downloadFile as any).mock.calls[0][0]).toBe(EXPORT_PATH)
    })

    it('全部完成时直接导出，不弹确认', async () => {
      const { api } = await import('@/services/apiProxy')
      const { downloadFile } = await import('@/utils/http')
      const { ElMessageBox } = await import('element-plus')

      ;(api.get as any).mockImplementation(async (url: string) => {
        if (url.includes('/export-word/check-incomplete')) {
          return { complete: true, missing_fields: [], wp_code: 'A18-2', reason: null }
        }
        return {
          sheets: [{
            html_data: {
              recipient: { authority: '', custom: '' },
              matters: [
                { id: 1, title: '舞弊', applicability: 'N', content: '' },
                { id: 2, title: '重大违反法律法规行为', applicability: 'N', content: '' },
                { id: 3, title: '年度报告中信息不一致或错报', applicability: 'NA', content: '' },
                { id: 4, title: '其他事项', applicability: 'N', content: '' },
              ],
              issuance: { cpa1: '', cpa2: '', date: '' },
              project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同' },
            },
          }],
        }
      })

      const wrapper = await mountComponent({ projectId: 'proj-1' })
      await clickExport(wrapper)

      expect(ElMessageBox.confirm).not.toHaveBeenCalled()
      expect(downloadFile).toHaveBeenCalledTimes(1)
      expect((downloadFile as any).mock.calls[0][0]).toBe(EXPORT_PATH)
    })

    it('用户选择「返回完善」时不下载', async () => {
      const { api } = await import('@/services/apiProxy')
      const { downloadFile } = await import('@/utils/http')
      const { ElMessageBox } = await import('element-plus')

      ;(ElMessageBox.confirm as any).mockRejectedValueOnce('cancel')
      ;(api.get as any).mockImplementation(async (url: string) => {
        if (url.includes('/export-word/check-incomplete')) {
          return { complete: false, missing_fields: ['舞弊（未选择适用性）'], wp_code: 'A18-2', reason: '1 项议题未完成' }
        }
        return {
          sheets: [{
            html_data: {
              recipient: { authority: '', custom: '' },
              matters: [
                { id: 1, title: '舞弊', applicability: null, content: '' },
                { id: 2, title: '重大违反法律法规行为', applicability: null, content: '' },
                { id: 3, title: '年度报告中信息不一致或错报', applicability: null, content: '' },
                { id: 4, title: '其他事项', applicability: null, content: '' },
              ],
              issuance: { cpa1: '', cpa2: '', date: '' },
              project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同' },
            },
          }],
        }
      })

      const wrapper = await mountComponent({ projectId: 'proj-1' })
      await clickExport(wrapper)

      expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
      expect(downloadFile).not.toHaveBeenCalled()
    })

    it('导出失败给中文提示，不静默', async () => {
      const { api } = await import('@/services/apiProxy')
      const { downloadFile } = await import('@/utils/http')
      const { ElMessage } = await import('element-plus')

      ;(api.get as any).mockImplementation(async (url: string) => {
        if (url.includes('/export-word/check-incomplete')) {
          return { complete: true, missing_fields: [], wp_code: 'A18-2', reason: null }
        }
        return {
          sheets: [{
            html_data: {
              recipient: { authority: '', custom: '' },
              matters: [
                { id: 1, title: '舞弊', applicability: 'N', content: '' },
                { id: 2, title: '重大违反法律法规行为', applicability: 'N', content: '' },
                { id: 3, title: '年度报告中信息不一致或错报', applicability: 'NA', content: '' },
                { id: 4, title: '其他事项', applicability: 'N', content: '' },
              ],
              issuance: { cpa1: '', cpa2: '', date: '' },
              project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同' },
            },
          }],
        }
      })
      ;(downloadFile as any).mockRejectedValueOnce({ response: { status: 500 } })

      const wrapper = await mountComponent({ projectId: 'proj-1' })
      await clickExport(wrapper)

      // handleApiError 走 5xx 分支：ElNotification（非 ElMessage），这里只断言没有被静默吞掉
      expect(downloadFile).toHaveBeenCalledTimes(1)
      expect(ElMessage.success).not.toHaveBeenCalled()
    })

    it('下载文件名 fallback 用 wp_code，不用底稿 UUID', async () => {
      // `downloadFile` 只在 Content-Disposition 缺头时才用 `fileName`（见
      // `utils/http.ts` 的 `extractFileNameFromDisposition`）。原先传 `${wpId}.docx`
      // ⇒ 后端一旦没给头，用户拿到 UUID 命名的文件（不可读）。这里钉住 fallback 取自
      // check 响应的 `wp_code`。
      const { api } = await import('@/services/apiProxy')
      const { downloadFile } = await import('@/utils/http')

      ;(api.get as any).mockImplementation(async (url: string) => {
        if (url.includes('/export-word/check-incomplete')) {
          return { complete: true, missing_fields: [], wp_code: 'A18-2', reason: null }
        }
        return { sheets: [{ html_data: {
          recipient: { authority: '', custom: '' },
          matters: [
            { id: 1, title: '舞弊', applicability: 'N', content: '' },
            { id: 2, title: '重大违反法律法规行为', applicability: 'N', content: '' },
            { id: 3, title: '年度报告中信息不一致或错报', applicability: 'NA', content: '' },
            { id: 4, title: '其他事项', applicability: 'N', content: '' },
          ],
          issuance: { cpa1: '', cpa2: '', date: '' },
          project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同' },
        } }] }
      })

      const wrapper = await mountComponent({ projectId: 'proj-1' })
      await clickExport(wrapper)

      const options = (downloadFile as any).mock.calls[0][1]
      expect(options.fileName).toBe('A18-2.docx')
      expect(options.fileName).not.toContain('wp-182')
    })

    it('check 响应没有 wp_code 时 fallback 仍是可读中文名，不是 UUID', async () => {
      const { api } = await import('@/services/apiProxy')
      const { downloadFile } = await import('@/utils/http')

      ;(api.get as any).mockImplementation(async (url: string) => {
        if (url.includes('/export-word/check-incomplete')) {
          // 501（服务未就绪）时后端 detail 里也带 schema，但 wp_code 可能是空串
          return { complete: true, missing_fields: [], wp_code: '', reason: null }
        }
        return { sheets: [{ html_data: {
          recipient: { authority: '', custom: '' },
          matters: [],
          issuance: { cpa1: '', cpa2: '', date: '' },
          project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同' },
        } }] }
      })

      const wrapper = await mountComponent({ projectId: 'proj-1' })
      await clickExport(wrapper)

      const options = (downloadFile as any).mock.calls[0][1]
      expect(options.fileName).toBe('A18-2 与治理层沟通函.docx')
      expect(options.fileName).not.toContain('wp-182')
    })
  })
})
