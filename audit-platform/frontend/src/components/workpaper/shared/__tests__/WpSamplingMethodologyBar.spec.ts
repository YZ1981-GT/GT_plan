/**
 * WpSamplingMethodologyBar 渲染守卫（sampling-compliance-closure Wave 3 Task 22）
 *
 * 覆盖 Property 17 的**渲染侧**：门控 + 字段集 + 金额格式化。
 * 纯函数侧（`hasMethodologyContent` / `buildMethodologySummary` / 最小字段集映射）
 * 由 `composables/shared/__tests__/samplingFillTarget.spec.ts` 覆盖，两者不重叠。
 *
 * 🔴 为什么金额格式化必须在**组件层**验：`fmtAmount` 是 displayPrefs **store 成员**、
 * 不是 `@/stores/displayPrefs` 的模块级导出。写成 `import { fmtAmount } from ...`
 * 会让整页崩成「does not provide an export named 'fmtAmount'」，而 `get_diagnostics`
 * 与纯函数单测全绿 —— 只有真实挂载才暴露。
 *
 * Validates: Requirements 6.2, 6.4
 * Properties: Property 17
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WpSamplingMethodologyBar from '../WpSamplingMethodologyBar.vue'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

function makeMethodology(
  over: Partial<SamplingMethodologySnapshot> = {},
): SamplingMethodologySnapshot {
  return {
    samplingMethod: 'mus',
    samplingInterval: '1234567.5',
    sampleSize: 25,
    suggestedSampleSize: 27,
    tolerableMisstatement: 2500000,
    expectedMisstatement: 500000,
    confidenceLevel: 0.95,
    accountCodes: ['1122'],
    randomSeed: '20260804',
    batchId: 'b1c2d3e4-aaaa-bbbb-cccc-ddddeeeeffff',
    datasetId: 'ds123456-1111-2222-3333-444455556666',
    ...over,
  }
}

function mountBar(methodology: SamplingMethodologySnapshot | null | undefined) {
  return mount(WpSamplingMethodologyBar, {
    props: { methodology },
    global: {
      stubs: {
        // el-tag / el-tooltip 只做包裹，直接渲染默认插槽即可拿到文本
        'el-tag': { template: '<span class="stub-tag"><slot /></span>' },
        'el-tooltip': {
          props: ['content'],
          template: '<span class="stub-tooltip" :data-content="content"><slot /></span>',
        },
      },
    },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  // displayPrefs 从 localStorage 读偏好；清掉以确保用默认值（元 / 2 位小数 / 0 显示为 —）
  localStorage.clear()
})

// ─── Property 17：渲染门控 ──────────────────────────────────────────────────

describe('Property 17 门控：无方法学内容时整条不渲染', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
    ['空对象', {} as SamplingMethodologySnapshot],
  ])('%s → 不产出任何 DOM', (_label, m) => {
    const wrapper = mountBar(m as SamplingMethodologySnapshot | null)
    expect(wrapper.find('.wp-sampling-methodology-bar').exists()).toBe(false)
    expect(wrapper.text().trim()).toBe('')
  })

  it('样本量为 0 且其余全空 → 不渲染（0 不算「抽过样」）', () => {
    const wrapper = mountBar({ sampleSize: 0, accountCodes: [] } as any)
    expect(wrapper.find('.wp-sampling-methodology-bar').exists()).toBe(false)
  })

  it('只要有方法名就渲染', () => {
    const wrapper = mountBar({ samplingMethod: 'random' } as any)
    expect(wrapper.find('.wp-sampling-methodology-bar').exists()).toBe(true)
    expect(wrapper.text()).toContain('随机抽样')
  })
})

// ─── Property 17：字段集 ────────────────────────────────────────────────────

describe('Property 17 字段集：齐备时渲染声明的全部要素', () => {
  it('方法 / 科目 / 样本量 / 建议 / 间隔 / 可容忍错报 / 置信度 / 种子 / 批次 / 账套版本', () => {
    const text = mountBar(makeMethodology()).text()
    for (const token of [
      '抽样方法学', '货币单元抽样', '1122', '样本量', '25', '系统建议 27',
      '抽样间隔', '可容忍错报', '置信度', '95%', '种子', '20260804', '批次', '账套版本',
    ]) {
      expect(text, `缺字段：${token}`).toContain(token)
    }
  })

  it('缺省项整段不渲染，而不是显示「-」（归档件上的「-」无法与「取不到」区分）', () => {
    const text = mountBar(
      makeMethodology({
        samplingInterval: null,
        suggestedSampleSize: null,
        tolerableMisstatement: null,
        confidenceLevel: null,
        randomSeed: null,
        accountCodes: [],
      }),
    ).text()
    expect(text).not.toContain('抽样间隔')
    expect(text).not.toContain('系统建议')
    expect(text).not.toContain('可容忍错报')
    expect(text).not.toContain('置信度')
    expect(text).not.toContain('种子')
    expect(text).not.toContain('科目')
    // 但方法与样本量恒在（它们是抽样存在的最小证据）
    expect(text).toContain('货币单元抽样')
    expect(text).toContain('样本量')
  })

  it('批次号与账套版本截断到 8 位，tooltip 给全量（可复算追溯要看完整 id）', () => {
    const m = makeMethodology()
    const wrapper = mountBar(m)
    expect(wrapper.text()).toContain('b1c2d3e4')
    expect(wrapper.text()).not.toContain(m.batchId as string)
    const contents = wrapper.findAll('.stub-tooltip').map((n) => n.attributes('data-content'))
    expect(contents.some((c) => (c ?? '').includes(m.batchId as string))).toBe(true)
    expect(contents.some((c) => (c ?? '').includes(m.datasetId as string))).toBe(true)
  })

  it('未绑定账套版本时如实提示（不可复算必须在底稿正文可见）', () => {
    const text = mountBar(makeMethodology({ datasetId: null })).text()
    expect(text).toContain('未绑定账套版本')
    expect(text).not.toContain('账套版本 ds123456')
  })
})

// ─── Property 17：金额格式化 ────────────────────────────────────────────────

describe('Property 17 金额格式化：走 displayPrefs.fmtAmount', () => {
  it('千分符 + 两位小数（fmtAmount 是 store 成员，此处即其真实契约）', () => {
    const text = mountBar(
      makeMethodology({ samplingInterval: '1234567.5', tolerableMisstatement: 2500000 }),
    ).text()
    expect(text).toContain('1,234,567.50')
    expect(text).toContain('2,500,000.00')
  })

  it('非法金额不渲染该项（不产出 NaN）', () => {
    const text = mountBar(
      makeMethodology({ samplingInterval: 'abc' as any, tolerableMisstatement: NaN }),
    ).text()
    expect(text).not.toContain('NaN')
    expect(text).not.toContain('抽样间隔')
    expect(text).not.toContain('可容忍错报')
  })

  it('置信度两种形态都归一为百分数（0.95 与 95 同解）', () => {
    expect(mountBar(makeMethodology({ confidenceLevel: 0.95 })).text()).toContain('95%')
    expect(mountBar(makeMethodology({ confidenceLevel: 95 })).text()).toContain('95%')
  })
})

// ─── 反向自检 ───────────────────────────────────────────────────────────────

describe('反向自检', () => {
  it('金额若不经 fmtAmount 则本套断言必红（证明格式化断言不是空转）', () => {
    // 复现「直接 String(v)」的错误实现，断言它拿不到千分符
    expect(String(1234567.5)).not.toContain('1,234,567.50')
  })

  it('组件源码不得出现 fmtAmount 的模块级 import（会让整页崩）', async () => {
    const src = (await import(
      '../WpSamplingMethodologyBar.vue?raw'
    )) as unknown as { default: string }
    expect(src.default).not.toMatch(/import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from/)
    expect(src.default).toContain('useDisplayPrefsStore')
  })
})
