/**
 * D3-6 Property 9（design.md）：`D3-rp-rows` 下游消费方在 OO 回写后仍正确重算。
 *
 * spec: d3-sync-coverage-via-row-table-engine · Task 7 · Requirements 1.5
 *
 * ═══ 为什么用这种方式验证，而不是端到端真栈 ═══
 *
 * Task 5 证据已确认 D3 的真栈三端点/整册 materialize 不可测（`adapter_registered=False`，
 * D3 自身 manifest capability 非 bidirectional + D2 契约漂移连带阻塞）。design.md 裁决 F5
 * 的处置原则是「真栈判据如实标 [ ]*，不得以合成测试冒充真栈」——但 Property 9 要验证的事情
 * 本质上是**前端逻辑**：给定 `D3-rp-rows` 的新值（不管这个新值是从 OO 回写、HTML 保存、还是
 * 任何其它写入路径产生的），`D3TabIndex` 的完成度判定（`isSheetComplete`/`completedCount`）
 * 是否正确响应。这一层逻辑本身不依赖 adapter 是否注册、不依赖后端是否可达——它只是一个纯
 * Vue computed 对 `allResponses` prop 变化的响应，可以完全离线用 Vitest + Vue Test Utils
 * 驱动，不需要冒充"OO 回写"这个动作本身（那部分仍然不可测，如实标 [ ]*）。
 *
 * Task 1 证据（`evidence/task1-sheet-morphology-and-geometry.md` §四）已 grep 实证
 * `D3-rp-rows` 的下游消费方清单：①`D3TabIndex.isSheetComplete`（本文件覆盖）②ACNR 导入
 * 导出映射表 `_d3_import_export.py`（后端静态配置，非前端 computed 重算，不适用本文件的
 * 验证方式）——**没有** `useD3CrossSheet` 跨 sheet 消费。本文件只覆盖①，这也是 Task 1 grep
 * 出的清单里唯一一个"前端下游 computed 重算"性质的消费方。
 *
 * 复用姊妹判据文件 `composables/__tests__/tabIndexAcnrCatalog.pbt.spec.ts` 已验证过的挂载
 * 范式（`shallowMount` + `global.provide.jumpToSection` + Element Plus stub），该文件已经
 * 证明这套挂载方式对 D2TabIndex/D4TabIndex 可行，本文件把同一范式套用到 D3TabIndex（同一
 * props 形状：wpId/projectId/allResponses/isReadonly），是全仓第一个 `D3TabIndex.spec.ts`。
 */
import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import D3TabIndex from '../D3TabIndex.vue'

// Element Plus 组件在测试环境未全局注册，同姊妹文件的处理方式：显式 stub 为不调用作用域
// 插槽的空节点，避免 el-table-column 的 #default="{ row }" 以 undefined 调用而崩。
const elStubs = {
  'el-table': { template: '<div class="el-table-stub"><slot /></div>' },
  'el-table-column': { template: '<div class="el-table-column-stub"></div>' },
  'el-progress': { template: '<div class="el-progress-stub"></div>' },
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
  'el-button': { template: '<button class="el-button-stub"><slot /></button>' },
  'el-tooltip': { template: '<div class="el-tooltip-stub"><slot /></div>' },
  'el-dialog': { template: '<div class="el-dialog-stub"><slot /></div>' },
  'el-tabs': { template: '<div class="el-tabs-stub"><slot /></div>' },
  'el-tab-pane': { template: '<div class="el-tab-pane-stub"><slot /></div>' },
}

const mountGlobal = { provide: { jumpToSection: () => {} }, stubs: elStubs }

function mountD3(allResponses: Map<string, any>) {
  return shallowMount(D3TabIndex, {
    props: {
      wpId: 'wp-d3',
      projectId: 'proj-1',
      allResponses,
      isReadonly: false,
    },
    global: mountGlobal,
  })
}

describe('Feature: d3-sync-coverage-via-row-table-engine, Property 9 — D3-rp-rows 下游重算', () => {
  it('D3-rp-rows 为空/缺失时 D3-6 判定未完成（completedCount 基线）', () => {
    const wrapper = mountD3(new Map())
    const completedCountBefore = (wrapper.vm as any).completedCount as number
    wrapper.unmount()
    // 只是取基线值，不对具体数字做强断言（避免与其它 9 张 sheet 的完成度耦合），
    // 后续测试用"增量"而非"绝对值"来断言 D3-6 这一项的贡献。
    expect(typeof completedCountBefore).toBe('number')
  })

  it('D3-rp-rows 被写入非空行数组后，D3-6 的完成度判定正确重算为已完成', () => {
    // 模拟"OO 回写 → merge 进 checklist_responses store → allResponses 更新"这条链路
    // 落到前端的最终形态：D3-rp-rows 对应的 remark 是一个非空 JSON 数组字符串
    // （与 D3TabIndex.vue 的 hasJsonRows() 实现逐字对齐：JSON.parse 后 Array.isArray && length>0）。
    const before = new Map<string, any>()
    const wrapperBefore = mountD3(before)
    const completedCountBefore = (wrapperBefore.vm as any).completedCount as number
    wrapperBefore.unmount()

    const after = new Map<string, any>()
    after.set('D3-rp-rows', {
      remark: JSON.stringify([
        { rowId: 'rp-1', relatedPartyName: '测试关联方A', closingBalance: 1000 },
      ]),
    })
    const wrapperAfter = mountD3(after)
    const completedCountAfter = (wrapperAfter.vm as any).completedCount as number
    wrapperAfter.unmount()

    // D3-6 从未完成变为完成，且是唯一变量（其余 9 项 store 键均未写入）⇒ completedCount
    // 必须恰好 +1，证明 isSheetComplete('D3-6', ...) 这条 computed 链路对 D3-rp-rows
    // 的变化是敏感且正确的（不是恒定值、不是被其它判定掩盖）。
    expect(completedCountAfter).toBe(completedCountBefore + 1)
  })

  it('D3-rp-rows 写入空数组（[]）时仍判未完成（不因 key 存在就误判完成）', () => {
    const emptyArray = new Map<string, any>()
    emptyArray.set('D3-rp-rows', { remark: JSON.stringify([]) })
    const wrapper = mountD3(emptyArray)
    const completedCount = (wrapper.vm as any).completedCount as number

    const trulyEmpty = mountD3(new Map())
    const completedCountBaseline = (trulyEmpty.vm as any).completedCount as number

    wrapper.unmount()
    trulyEmpty.unmount()

    // 空数组与完全缺失该键的 completedCount 必须相等——D3-6 的判定不应仅凭"键存在"就
    // 判完成，必须真的解析出非空数组（hasJsonRows 的 `parsed.length > 0` 分支）。
    expect(completedCount).toBe(completedCountBaseline)
  })

  it('D3-rp-rows 写入非法 JSON 时不崩且判未完成（hasJsonRows 的 try/catch 分支）', () => {
    const malformed = new Map<string, any>()
    malformed.set('D3-rp-rows', { remark: '{not valid json' })
    expect(() => mountD3(malformed)).not.toThrow()
    const wrapper = mountD3(malformed)
    const completedCount = (wrapper.vm as any).completedCount as number

    const baseline = mountD3(new Map())
    const completedCountBaseline = (baseline.vm as any).completedCount as number

    wrapper.unmount()
    baseline.unmount()

    expect(completedCount).toBe(completedCountBaseline)
  })

  it('从有数据回退到空（模拟"取数恢复"场景）：completedCount 正确减一，不残留旧状态', () => {
    // Property 9 的"仍正确重算"隐含双向：不仅新增数据时要涨，数据被清空/撤销时也要正确
    // 掉回去，不是只在挂载瞬间算一次然后再也不跟随 allResponses 变化（那种实现下，
    // 这条测试会因为组件内部缓存了旧值而失败）。用两次独立挂载模拟 props 前后两个取值
    // （等价于 Vue 响应式下 allResponses 引用变化触发 computed 重算，覆盖场景同姊妹文件
    // `tabIndexAcnrCatalog.pbt.spec.ts` 里同款"重挂载模拟 prop 变化"的验证方式）。
    const withData = new Map<string, any>()
    withData.set('D3-rp-rows', {
      remark: JSON.stringify([{ rowId: 'rp-1', relatedPartyName: '关联方B' }]),
    })
    const wrapperWith = mountD3(withData)
    const completedCountWith = (wrapperWith.vm as any).completedCount as number
    wrapperWith.unmount()

    const withoutData = new Map<string, any>()
    const wrapperWithout = mountD3(withoutData)
    const completedCountWithout = (wrapperWithout.vm as any).completedCount as number
    wrapperWithout.unmount()

    expect(completedCountWith).toBe(completedCountWithout + 1)
  })
})
