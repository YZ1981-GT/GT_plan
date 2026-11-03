/**
 * Unit Tests — GtA111SubsequentEventsInquiry.vue 组件
 *
 * Spec: .kiro/specs/a11-1-subsequent-events-inquiry/
 * Tasks: 3.7, 3.8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

// ─── Mock API ────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url.includes('onlyoffice/health')) {
        return Promise.resolve({ healthy: true })
      }
      return Promise.resolve({
        sheets: [{
          html_data: {
            meta_data: {
              inquiry_date: '2026-03-20',
              interviewee: '张三（财务总监）',
              location: '公司会议室',
              team_signature: '李四',
            },
            qa_list: Array.from({ length: 10 }, (_, i) => ({
              number: i + 1,
              answer: i === 0 ? '无新承诺' : null,
            })),
            evidence: '银行对账单',
            project_context: { client_name: '测试公司', balance_sheet_date: '2025-12-31' },
            questions_config: Array.from({ length: 10 }, (_, i) => ({
              number: i + 1,
              title: ['承诺、借款及担保', '资产出售或购置', '资本发行/债务', '政府征用/灾害损失',
                '或有事项进展', '重大调整事项', '持续经营事项', '会计估计变更',
                '资产可收回性', '其他重大事项'][i],
              text: `问题${i + 1}文本`,
              has_guidance: i === 4,
              guidance_text: i === 4 ? '如涉及诉讼案例，请列明案号、诉讼金额、判决结果等详细信息' : null,
            })),
          },
        }],
      })
    }),
    put: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual as any,
    ElMessage: { warning: vi.fn(), error: vi.fn() },
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

describe('GtA111SubsequentEventsInquiry.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function mountComponent(props: Record<string, any> = {}) {
    const { default: GtA111SubsequentEventsInquiry } = await import('../GtA111SubsequentEventsInquiry.vue')
    const wrapper = mount(GtA111SubsequentEventsInquiry, {
      props: { wpId: 'wp-a111', ...props },
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
          ElCollapse: defineComponent({
            props: ['modelValue'],
            template: '<div class="el-collapse-stub"><slot /></div>',
          }),
          ElCollapseItem: defineComponent({
            props: ['title', 'name'],
            template: '<div class="el-collapse-item-stub"><slot /></div>',
          }),
          ElAlert: defineComponent({
            props: ['type', 'closable', 'showIcon'],
            template: '<div class="el-alert-stub" :data-type="type"><slot name="title" /><slot /></div>',
          }),
        },
      },
    })
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 10))
    await wrapper.vm.$nextTick()
    return wrapper
  }

  // ─── 10 Q&A Cards Render ───

  describe('10 Q&A cards render', () => {
    it('renders 10 question cards', async () => {
      const wrapper = await mountComponent()
      const cards = wrapper.findAll('.gt-a111__card')
      // meta card + 10 QA cards + evidence card = 12
      expect(cards.length).toBe(12)
    })

    it('renders numbered titles for questions', async () => {
      const wrapper = await mountComponent()
      const text = wrapper.text()
      // Card headers rendered in slot, check question text body instead
      expect(text).toContain('问题1文本')
      expect(text).toContain('问题5文本')
      expect(text).toContain('问题10文本')
    })

    it('renders question text (read-only)', async () => {
      const wrapper = await mountComponent()
      const questionTexts = wrapper.findAll('.gt-a111__question-text')
      expect(questionTexts.length).toBe(10)
    })

    it('renders answer textarea for each question', async () => {
      const wrapper = await mountComponent()
      const qaBlocks = wrapper.findAll('.gt-a111__qa')
      expect(qaBlocks.length).toBe(10)
    })
  })

  // ─── Meta Form Fields ───

  describe('meta form fields', () => {
    it('renders meta card with 4 fields', async () => {
      const wrapper = await mountComponent()
      const metaCard = wrapper.find('#nav-meta')
      expect(metaCard.exists()).toBe(true)
      // el-card header slot stubbed; check field labels instead
      expect(wrapper.text()).toContain('询问日期')
    })

    it('renders date picker, interviewee, location, signature fields', async () => {
      const wrapper = await mountComponent()
      const fields = wrapper.findAll('.gt-a111__field')
      expect(fields.length).toBeGreaterThanOrEqual(4)
      expect(wrapper.text()).toContain('询问日期')
      expect(wrapper.text()).toContain('受访对象')
      expect(wrapper.text()).toContain('询问地点')
      expect(wrapper.text()).toContain('项目组签字')
    })
  })

  // ─── AI Button Disabled ───

  describe('AI button disabled', () => {
    it('renders AI buttons that are disabled', async () => {
      const wrapper = await mountComponent()
      const aiButtons = wrapper.findAll('.gt-a111__ai-btn')
      expect(aiButtons.length).toBe(10)
      for (const btn of aiButtons) {
        expect(btn.attributes('disabled')).toBeDefined()
      }
    })
  })

  // ─── Navigation 12 Items ───

  describe('navigation 12 items', () => {
    it('renders left navigation with 12 items', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      expect(navItems.length).toBe(12)
    })

    it('first nav item is 元信息', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      expect(navItems[0].text()).toBe('元信息')
    })

    it('last nav item is 证据', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      expect(navItems[11].text()).toBe('证据')
    })

    it('middle items are Q1 through Q10', async () => {
      const wrapper = await mountComponent()
      const navItems = wrapper.findAll('.gt-a111__nav-item')
      for (let i = 1; i <= 10; i++) {
        expect(navItems[i].text()).toBe(`Q${i}`)
      }
    })
  })

  // ─── Mode Switch ───

  describe('mode switch', () => {
    it('defaults to structured view', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a111__layout').exists()).toBe(true)
      expect(wrapper.find('.oo-stub').exists()).toBe(false)
    })

    // 🔴 原来这里是 `expect(找到 el-segmented).toBe(true)` —— 断言「模式开关恒显示」。
    //    spec workpaper-html-onlyoffice-bidirectional-writeback-closure（task 3.5 / AC 1.4、1.5）
    //    把开关可见性改由 entry 级同步能力**单源**决定后，这条断言就成了「断言旧的不诚实行为」：
    //    本 entry（`xlsx/gt-a111-subsequent-events-inquiry`）在 generated manifest 里是
    //    `capability: null` / `adjudicationState: 'pending'` / blockedBy BP-1~BP-9，
    //    也就是**两侧尚未形成已验收的双向链路** —— 此时摆出「结构化视图 / 在线编辑」双选开关，
    //    正是该 spec 要治的「仅能打开 OO 却呈现成双向」。
    //    所以不是删掉断言，而是改成断言**正确行为的两面**。
    it('未裁决为双向时不显示模式开关（而是显示未互通原因）', async () => {
      const wrapper = await mountComponent()
      expect(
        wrapper.find('.el-segmented-stub').exists(),
        '本 entry 仍是 pending，摆出双选开关即「按目标态展示」',
      ).toBe(false)
      // 开关不是无声消失：能力披露组件必须在位，把原因讲清楚
      expect(
        wrapper.findComponent({ name: 'GtEntrySyncCapabilityNotice' }).exists(),
        '隐藏开关却不给原因，比显示一个假开关更糟',
      ).toBe(true)
    })

    // 🔴 本例必须传 `projectId`：`useEntrySyncReadiness` 在三个身份任一为空时走「缺身份」
    //    早退分支（直接用 generated manifest 的静态裁决），**根本不会调** readiness 接口 ——
    //    不传 projectId 时 spy 永不触发，这条判据就会以「单源说可双向却不显示」的形态假红。
    it('单源裁决为可双向时显示模式开关（判据不是恒假）', async () => {
      const api = await import('../sync/workpaperSyncApi')
      const spy = vi.spyOn(api, 'readEntrySyncReadiness').mockResolvedValue({
        entry_id: 'xlsx/gt-a111-subsequent-events-inquiry',
        effective_entry_id: 'xlsx/gt-a111-subsequent-events-inquiry',
        capability: 'bidirectional',
        adjudication_state: 'terminal',
        allowed_modes: ['html', 'oo'],
        can_claim_bidirectional: true,
        runtime: {
          ready: true,
          adapter_id: 'a111',
          authority_model: 'store',
          definition_bundle_id: 'b1',
          definition_bundle_sha256: 'x',
          typed_slots_complete: true,
          typed_slots: [],
          representation_id: 'r1',
          representation_generation: 1,
        },
        acceptance: {
          state: 'passed',
          stale: false,
          run_id: 'run-1',
          required_scenario_set_digest: 'd',
        },
        reason: null,
      } as Awaited<ReturnType<typeof api.readEntrySyncReadiness>>)
      try {
        const wrapper = await mountComponent({ projectId: 'proj-a111' })
        await new Promise((r) => setTimeout(r, 0))
        await wrapper.vm.$nextTick()
        expect(spy, 'readiness 接口未被调用 ⇒ 身份不全走了早退分支，本例测不到东西').toHaveBeenCalled()
        expect(
          wrapper.find('.el-segmented-stub').exists(),
          '单源说可双向却仍不显示开关 ⇒ 上一条就是恒假判据',
        ).toBe(true)
      } finally {
        spy.mockRestore()
      }
    })
  })

  // ─── 模式可用性 ───
  //
  // 🔴 这一组原名「OO Health Check Disable」，断言「OO 健康 ⇒ 两种模式都可用」，取数方式是
  //    `findAll('.el-segmented-stub button')` 期望 2 个按钮。
  //    两件事必须分开说清楚：
  //    ① **它在本轮之前就是红的**（A/B 逐节点归因：同一断言在 HEAD 与候选树都失败，
  //       `expected +0 to be 2`）—— 原因与同步能力无关，是这个 stub 下取不到按钮；
  //       所以不是本轮 task 3.5 弄红的。
  //    ② 但它的**主题**已经被 task 3.5 改掉了：模式是否可用不再由 OO 探活决定，而由 entry
  //       级同步能力单源决定（本 entry 是 pending ⇒ 开关根本不出现，这组断言永远不可能成立）。
  //    留着就是一条永红判据（永红 = 没人看 = 等于没有门禁），故按新口径重写：
  //    单源裁决为可双向时，两个模式选项都在。
  describe('模式可用性由同步能力单源决定（原 OO health check 组）', () => {
    it('单源裁决为可双向时，结构化视图与在线编辑两个选项都在', async () => {
      const api = await import('../sync/workpaperSyncApi')
      const spy = vi.spyOn(api, 'readEntrySyncReadiness').mockResolvedValue({
        entry_id: 'xlsx/gt-a111-subsequent-events-inquiry',
        effective_entry_id: 'xlsx/gt-a111-subsequent-events-inquiry',
        capability: 'bidirectional',
        adjudication_state: 'terminal',
        allowed_modes: ['html', 'oo'],
        can_claim_bidirectional: true,
        runtime: {
          ready: true,
          adapter_id: 'a111',
          authority_model: 'store',
          definition_bundle_id: 'b1',
          definition_bundle_sha256: 'x',
          typed_slots_complete: true,
          typed_slots: [],
          representation_id: 'r1',
          representation_generation: 1,
        },
        acceptance: {
          state: 'passed',
          stale: false,
          run_id: 'run-1',
          required_scenario_set_digest: 'd',
        },
        reason: null,
      } as Awaited<ReturnType<typeof api.readEntrySyncReadiness>>)
      try {
        const wrapper = await mountComponent({ projectId: 'proj-a111' })
        await new Promise((r) => setTimeout(r, 0))
        await wrapper.vm.$nextTick()
        const segmented = wrapper.find('.el-segmented-stub')
        expect(segmented.exists(), '单源说可双向，开关却没出现').toBe(true)
        const labels = (wrapper.vm as unknown as { modeOptions?: Array<{ label?: string }> })
          .modeOptions
        // 不依赖 stub 怎么渲染按钮（原断言正是栽在这上面）：直接核对选项数据本身
        expect(Array.isArray(labels) ? labels.length : 0, '模式选项不是两项').toBe(2)
        expect((labels ?? []).map((o) => o.label)).toEqual(['结构化视图', '在线编辑'])
      } finally {
        spy.mockRestore()
      }
    })
  })

  // ─── Timing Guidance Alert ───

  describe('timing guidance alert', () => {
    it('renders timing alert at top of form', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('问询时间要求')
      expect(wrapper.text()).toContain('尽量接近审计报告日')
    })
  })

  // ─── Guidance el-alert for Q5 ───

  describe('guidance conditional display', () => {
    it('renders guidance alert for Q5 (has_guidance=true)', async () => {
      const wrapper = await mountComponent()
      const guidanceAlerts = wrapper.findAll('.gt-a111__guidance')
      expect(guidanceAlerts.length).toBe(1) // Only Q5 has guidance
      expect(wrapper.text()).toContain('如涉及诉讼案例')
    })
  })

  // ─── Evidence Card ───

  describe('evidence card', () => {
    it('renders evidence section', async () => {
      const wrapper = await mountComponent()
      const evidenceCard = wrapper.find('#nav-evidence')
      expect(evidenceCard.exists()).toBe(true)
      // el-card header slot is stubbed, just verify the card exists
      expect(evidenceCard.exists()).toBe(true)
    })
  })

  // ─── Save Status Indicator ───

  describe('save status', () => {
    it('renders save status area', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.gt-a111__save-status').exists()).toBe(true)
    })
  })
})
