/**
 * B23 业务流程与控制了解表 — Unit Tests
 *
 * ═══ 2026-09-06 按循环模型重写 ═══
 *
 * 本文件原先针对**已废弃的 8 流程模型**（`STANDARD_PROCESSES` / `processes` /
 * `toggleProcess` / `suggestProcessConclusion` / `addWalkthroughSample` /
 * `walkthroughSummary` / `pendingWalkthroughCount` 等），而生产实现早在
 * commit `a25ddebf`（全循环改造）就换成了**16 循环模型**：真源是
 * `b23CycleConfig.B23_CYCLES`（c1~c15 + cxx5），composable 返回 `cycles`，
 * 宿主 `GtB23ProcessControl.vue` 消费的也是 `cycles`。
 *
 * 于是 42 条用例长期红（`STANDARD_PROCESSES` 为 undefined、`ctrl.processes`
 * 为 undefined）。判定依据：生产组件与 composable 都只认循环模型 ⇒ **测试过期**，
 * 不是实现缺陷。本次按新契约逐条重写，覆盖面不缩：
 *   注册契约 / 循环卡片 / 展开收起 / 适用性 / 控制点 CRUD / 穿行与控制测试 /
 *   缺陷 / 结论建议与覆盖 / 仪表盘 / Entity_Level_Context / 联动 / 保存行为
 *
 * 🔴 不新增对生产代码的期望：所有断言都从 `B23_CYCLES` 与 composable 的真实
 * 返回值现算，不写死循环个数/名称的第二份清单（写死会在模板改动时变成第二真源）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref, effectScope } from 'vue'

import { HTML_RENDERER_REGISTRY } from '../htmlRendererRegistry'
import { B23_CYCLES } from '../composables/b23CycleConfig'

// Mock apiProxy
const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))

/** 造一个空响应 Map + 假保存函数；返回 composable 实例与 saveFn 便于断言。 */
async function makeCtrl(seed?: Map<string, any>) {
  const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
  const allResponses = ref(seed ?? new Map<string, any>())
  const saveFn = vi.fn().mockResolvedValue(undefined)
  const ctrl = useB23ProcessControl(allResponses, saveFn)
  return { ctrl, saveFn, allResponses }
}

/** 把 saveFn 收到的 items 落回 allResponses，模拟保存后回读。 */
function applySaved(allResponses: any, saveFn: any): void {
  for (const call of saveFn.mock.calls) {
    for (const item of call[0] ?? []) {
      allResponses.value.set(item.item_id, {
        item_id: item.item_id,
        conclusion: item.conclusion ?? null,
        remark: item.remark ?? null,
      })
    }
  }
  allResponses.value = new Map(allResponses.value)
}

// ═══════════════════════════════════════════════════════════════════════════════
// 注册契约
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 注册契约', () => {
  it('registry 包含 b23-process-control 条目且字段正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b23-process-control')
    expect(entry).toBeDefined()
    expect(entry!.componentType).toBe('b23-process-control')
    expect(entry!.icon).toBe('🔄')
    expect(entry!.label).toBe('B23 业务流程与控制了解表')
    expect(entry!.emits).toEqual(['save', 'completed'])
    expect(entry!.contextProps).toBe('standard')
  })

  it('wp_code_overrides.json 映射 B23 → b23-process-control', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['B23']).toBe('b23-process-control')
  })

  it('每个循环的子底稿 wp_code 都在 overrides 里登记为 skip', () => {
    // 🔴 分母取自 `B23_CYCLES`（唯一真源），不写死 1~8 —— 循环从 8 扩到 16 时
    // 原来那条硬编码用例会漏掉新增子码，属静默缺口。
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    const notSkipped = B23_CYCLES
      .map(c => c.wpCode)
      .filter(code => overrides[code] !== 'skip')
    expect(
      notSkipped,
      'B23 子底稿必须 skip（由父 B23 一体化渲染），否则会各自渲染成空白底稿',
    ).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 循环卡片渲染
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 循环卡片渲染', () => {
  it('B23_CYCLES 是卡片的唯一真源，code/wpCode/name 均非空且唯一', () => {
    expect(B23_CYCLES.length).toBeGreaterThan(0)
    const codes = B23_CYCLES.map(c => c.code)
    const wpCodes = B23_CYCLES.map(c => c.wpCode)
    expect(new Set(codes).size).toBe(codes.length)
    expect(new Set(wpCodes).size).toBe(wpCodes.length)
    for (const c of B23_CYCLES) {
      expect(c.code.trim()).not.toBe('')
      expect(c.wpCode.trim()).not.toBe('')
      expect(c.name.trim()).not.toBe('')
    }
  })

  it('cycles 返回与 B23_CYCLES 等量的卡片且默认全部适用', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      expect(ctrl.cycles.value).toHaveLength(B23_CYCLES.length)
      expect(ctrl.cycles.value.map(c => c.code)).toEqual(B23_CYCLES.map(c => c.code))
      for (const card of ctrl.cycles.value) {
        expect(card.applicable).toBe(true)
        expect(card.conclusion).toBeNull()
      }
    })
    scope.stop()
  })

  it('每张卡片带名称/结论/完成比例/关键控制数等标题栏字段', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      const card = ctrl.cycles.value[0]
      expect(card.name).toBe(B23_CYCLES[0].name)
      expect(card.wpCode).toBe(B23_CYCLES[0].wpCode)
      expect(typeof card.completionRatio).toBe('string')
      expect(typeof card.keyControlCount).toBe('number')
      expect(typeof card.deficiencyCount).toBe('number')
      expect(card.conclusionOverridden).toBe(false)
    })
    scope.stop()
  })

  it('PROCESS_CONCLUSION_COLOR_MAP 覆盖全部循环结论枚举', async () => {
    const { PROCESS_CONCLUSION_COLOR_MAP, CYCLE_CONCLUSION_OPTIONS } =
      await import('../composables/useB23ProcessControl')
    for (const opt of CYCLE_CONCLUSION_OPTIONS) {
      expect(
        PROCESS_CONCLUSION_COLOR_MAP[opt],
        `结论「${opt}」缺颜色映射 → 卡片标签会渲染成无样式裸文本`,
      ).toBeDefined()
      expect(PROCESS_CONCLUSION_COLOR_MAP[opt].label.trim()).not.toBe('')
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 展开收起
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 展开收起', () => {
  it('toggleCycle 切换单卡片展开/收起', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      const code = B23_CYCLES[0].code
      const before = ctrl.expandedCycles.value.has(code)
      ctrl.toggleCycle(code)
      expect(ctrl.expandedCycles.value.has(code)).toBe(!before)
      ctrl.toggleCycle(code)
      expect(ctrl.expandedCycles.value.has(code)).toBe(before)
    })
    scope.stop()
  })

  it('expandAll 展开全部 / collapseAll 收起全部', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      ctrl.expandAll()
      expect(ctrl.expandedCycles.value.size).toBe(B23_CYCLES.length)
      for (const c of B23_CYCLES) {
        expect(ctrl.expandedCycles.value.has(c.code)).toBe(true)
      }
      ctrl.collapseAll()
      expect(ctrl.expandedCycles.value.size).toBe(0)
      // collapseAll 同时清空选中卡片（否则右侧详情会指向已收起的循环）
      expect(ctrl.selectedCycle.value).toBe('')
    })
    scope.stop()
  })

  it('selectCycle 设置当前循环', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      const code = B23_CYCLES[2].code
      ctrl.selectCycle(code)
      expect(ctrl.selectedCycle.value).toBe(code)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 适用性开关
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 适用性开关', () => {
  it('置为不适用 → 结论自动设「不适用」且卡片折叠', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl, saveFn, allResponses } = await makeCtrl()
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code

      ctrl.expandAll()
      ctrl.setApplicability(code, false)

      expect(saveFn).toHaveBeenCalled()
      const saved: any[] = saveFn.mock.calls.flatMap((c: any) => c[0])
      const applic = saved.find(i => i.item_id === generateItemId(code, 'applicability'))
      expect(applic?.conclusion).toBe('N')
      const concl = saved.find(i => i.item_id === generateItemId(code, 'cycle-conclusion'))
      expect(concl?.conclusion).toBe('不适用')
      // 不适用 → 折叠
      expect(ctrl.expandedCycles.value.has(code)).toBe(false)

      applySaved(allResponses, saveFn)
      expect(ctrl.getApplicability(code)).toBe(false)
      expect(ctrl.getConclusion(code)).toBe('不适用')
    })
    scope.stop()
  })

  it('恢复适用 → 清除自动写入的「不适用」结论', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[1].code
      // 先造出「不适用」的既有状态
      const seed = new Map<string, any>([
        [generateItemId(code, 'applicability'), { conclusion: 'N', remark: null }],
        [generateItemId(code, 'cycle-conclusion'), { conclusion: '不适用', remark: null }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)
      expect(ctrl.getApplicability(code)).toBe(false)

      ctrl.setApplicability(code, true)
      const saved: any[] = saveFn.mock.calls.flatMap((c: any) => c[0])
      const concl = saved.find(i => i.item_id === generateItemId(code, 'cycle-conclusion'))
      expect(concl).toBeDefined()
      expect(concl.conclusion).toBeNull()

      applySaved(allResponses, saveFn)
      expect(ctrl.getApplicability(code)).toBe(true)
      expect(ctrl.getConclusion(code)).toBeNull()
    })
    scope.stop()
  })

  it('恢复适用时不覆盖人工填写的非「不适用」结论', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[2].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'applicability'), { conclusion: 'N', remark: null }],
        [generateItemId(code, 'cycle-conclusion'), { conclusion: '设计无效', remark: null }],
      ])
      const { ctrl, saveFn } = await makeCtrl(seed)
      ctrl.setApplicability(code, true)
      const saved: any[] = saveFn.mock.calls.flatMap((c: any) => c[0])
      // 只应写 applicability，不得把人工结论抹掉
      expect(saved.some(i => i.item_id === generateItemId(code, 'cycle-conclusion'))).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 控制点 CRUD
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 控制点 CRUD', () => {
  it('addControlPoint 递增 ctrl-count', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl, saveFn, allResponses } = await makeCtrl()
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code

      expect(ctrl.getControlPoints(code)).toHaveLength(0)
      ctrl.addControlPoint(code)

      const saved: any[] = saveFn.mock.calls.flatMap((c: any) => c[0])
      const cnt = saved.find(i => i.item_id === generateItemId(code, 'ctrl-count'))
      expect(cnt?.remark).toBe('1')

      applySaved(allResponses, saveFn)
      expect(ctrl.getControlPoints(code)).toHaveLength(1)
      expect(ctrl.getControlPoints(code)[0].index).toBe(1)
    })
    scope.stop()
  })

  it('setControlPointField 写入文本字段并可回读', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '1' }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)

      ctrl.setControlPointField(code, 1, 'subProcess', '客户信用管理')
      applySaved(allResponses, saveFn)
      expect(ctrl.getControlPoints(code)[0].subProcess).toBe('客户信用管理')
    })
    scope.stop()
  })

  it('removeControlPoint 递减 count 且后续行上移（不留空洞）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '3' }],
        [generateItemId(code, 'ctrl', 1, undefined, 'subProcess'), { conclusion: null, remark: '第一项' }],
        [generateItemId(code, 'ctrl', 2, undefined, 'subProcess'), { conclusion: null, remark: '第二项' }],
        [generateItemId(code, 'ctrl', 3, undefined, 'subProcess'), { conclusion: null, remark: '第三项' }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)
      expect(ctrl.getControlPoints(code)).toHaveLength(3)

      ctrl.removeControlPoint(code, 2)
      applySaved(allResponses, saveFn)

      const after = ctrl.getControlPoints(code)
      expect(after).toHaveLength(2)
      // 删第 2 项 ⇒ 原第 3 项上移到位置 2
      expect(after[0].subProcess).toBe('第一项')
      expect(after[1].subProcess).toBe('第三项')
    })
    scope.stop()
  })

  it('控制点数量有上限（addControlPoint 到顶后不再增长）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '30' }],
      ])
      const { ctrl, saveFn } = await makeCtrl(seed)
      ctrl.addControlPoint(code)
      // 到上限即静默不写（不得抛错打断录入）
      expect(saveFn).not.toHaveBeenCalled()
    })
    scope.stop()
  })

  it('枚举字段存 conclusion、文本字段存 remark（两条通道不得混）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '1' }],
      ])
      const { ctrl, saveFn } = await makeCtrl(seed)

      ctrl.setControlPointField(code, 1, 'isKeyControl', '是')
      ctrl.setControlPointField(code, 1, 'subProcess', '纯文本')

      const saved: any[] = saveFn.mock.calls.flatMap((c: any) => c[0])
      const enumItem = saved.find(
        i => i.item_id === generateItemId(code, 'ctrl', 1, undefined, 'isKeyControl'),
      )
      const textItem = saved.find(
        i => i.item_id === generateItemId(code, 'ctrl', 1, undefined, 'subProcess'),
      )
      expect(enumItem?.conclusion).toBe('是')
      expect(textItem?.remark).toBe('纯文本')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 穿行测试（验设计）与控制测试（验运行）
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 穿行测试与控制测试', () => {
  it('穿行记录数与控制点数同构（每个控制点一条）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '2' }],
      ])
      const { ctrl } = await makeCtrl(seed)
      expect(ctrl.getWalkthroughs(code)).toHaveLength(2)
      expect(ctrl.getControlTests(code)).toHaveLength(2)
      expect(ctrl.getWalkthroughs(code).map(w => w.ctrlIndex)).toEqual([1, 2])
    })
    scope.stop()
  })

  it('setWalkthroughField：asDesigned 走 conclusion，其余走 remark', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '1' }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)

      ctrl.setWalkthroughField(code, 1, 'asDesigned', '是')
      ctrl.setWalkthroughField(code, 1, 'interviewee', '张三')

      const saved: any[] = saveFn.mock.calls.flatMap((c: any) => c[0])
      expect(
        saved.find(i => i.item_id === generateItemId(code, 'wt', 1, undefined, 'asDesigned'))
          ?.conclusion,
      ).toBe('是')
      expect(
        saved.find(i => i.item_id === generateItemId(code, 'wt', 1, undefined, 'interviewee'))
          ?.remark,
      ).toBe('张三')

      applySaved(allResponses, saveFn)
      const wt = ctrl.getWalkthroughs(code)[0]
      expect(wt.asDesigned).toBe('是')
      expect(wt.interviewee).toBe('张三')
    })
    scope.stop()
  })

  it('setControlTestField：operatingEffective 走 conclusion', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '1' }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)

      ctrl.setControlTestField(code, 1, 'operatingEffective', '无效')
      applySaved(allResponses, saveFn)
      expect(ctrl.getControlTests(code)[0].operatingEffective).toBe('无效')
    })
    scope.stop()
  })

  it('eligibleForTest 只放关键控制点进测试对象集合', async () => {
    const { eligibleForTest } = await import('../composables/useB23ProcessControl')
    expect(eligibleForTest({ isKeyControl: '是' } as any)).toBe(true)
    expect(eligibleForTest({ isKeyControl: '否' } as any)).toBe(false)
    expect(eligibleForTest({ isKeyControl: null } as any)).toBe(false)
  })

  it('suggestControlTest：关键控制 ∧ 穿行按设计执行 才建议做控制测试', async () => {
    const { suggestControlTest } = await import('../composables/useB23ProcessControl')
    const key = { isKeyControl: '是' } as any
    const nonKey = { isKeyControl: '否' } as any
    expect(suggestControlTest(key, { asDesigned: '是' } as any)).toBe(true)
    expect(suggestControlTest(key, { asDesigned: '否' } as any)).toBe(false)
    expect(suggestControlTest(key, undefined)).toBe(false)
    expect(suggestControlTest(nonKey, { asDesigned: '是' } as any)).toBe(false)
  })

  it('deficiencyHints：设计无效或穿行未按设计执行必有提示', async () => {
    const { deficiencyHints } = await import('../composables/useB23ProcessControl')
    expect(deficiencyHints({ designEffective: '否' } as any, undefined).length).toBeGreaterThan(0)
    expect(
      deficiencyHints({ designEffective: '是' } as any, { asDesigned: '否' } as any).length,
    ).toBeGreaterThan(0)
    expect(deficiencyHints({ designEffective: '是' } as any, { asDesigned: '是' } as any)).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 缺陷记录
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 缺陷记录', () => {
  it('addDeficiency 递增 def-count 并可回读', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const { ctrl, saveFn, allResponses } = await makeCtrl()

      expect(ctrl.getDeficiencies(code)).toHaveLength(0)
      ctrl.addDeficiency(code)
      const saved: any[] = saveFn.mock.calls.flatMap((c: any) => c[0])
      expect(saved.find(i => i.item_id === generateItemId(code, 'def-count'))?.remark).toBe('1')

      applySaved(allResponses, saveFn)
      expect(ctrl.getDeficiencies(code)).toHaveLength(1)
    })
    scope.stop()
  })

  it('setDeficiencyField 写入并回读；removeDeficiency 上移不留空洞', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'def-count'), { conclusion: null, remark: '2' }],
        [generateItemId(code, 'def', 1, undefined, 'subProcess'), { conclusion: null, remark: '缺陷一' }],
        [generateItemId(code, 'def', 2, undefined, 'subProcess'), { conclusion: null, remark: '缺陷二' }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)
      expect(ctrl.getDeficiencies(code)).toHaveLength(2)

      ctrl.removeDeficiency(code, 1)
      applySaved(allResponses, saveFn)
      const after = ctrl.getDeficiencies(code)
      expect(after).toHaveLength(1)
      expect(after[0].subProcess).toBe('缺陷二')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 循环结论：自动建议 + 人工覆盖
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 循环结论自动建议（30% 阈值）', () => {
  it('全部运行有效 → 设计有效且已实施', async () => {
    const { suggestCycleConclusion } = await import('../composables/useB23ProcessControl')
    const tests = [
      { operatingEffective: '有效' },
      { operatingEffective: '有效' },
    ] as any[]
    expect(suggestCycleConclusion(tests, [])).toBe('设计有效且已实施')
  })

  it('无效占比 ≤30% → 设计有效但未有效实施', async () => {
    const { suggestCycleConclusion } = await import('../composables/useB23ProcessControl')
    const tests = [
      { operatingEffective: '无效' },
      { operatingEffective: '有效' },
      { operatingEffective: '有效' },
      { operatingEffective: '有效' },
    ] as any[]
    expect(suggestCycleConclusion(tests, [])).toBe('设计有效但未有效实施')
  })

  it('无效占比 >30% → 设计无效', async () => {
    const { suggestCycleConclusion } = await import('../composables/useB23ProcessControl')
    const tests = [
      { operatingEffective: '无效' },
      { operatingEffective: '无效' },
      { operatingEffective: '有效' },
    ] as any[]
    expect(suggestCycleConclusion(tests, [])).toBe('设计无效')
  })

  it('无已评估控制测试 → null（不猜结论）', async () => {
    const { suggestCycleConclusion } = await import('../composables/useB23ProcessControl')
    expect(suggestCycleConclusion([], [])).toBeNull()
    expect(suggestCycleConclusion([{ operatingEffective: null }] as any[], [])).toBeNull()
  })

  it('人工结论与自动建议不同 → 记为覆盖且理由可回读', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      // 🔴 必须先造出**自动建议**：`setConclusion` 的覆盖判据是
      // `suggested !== null && conclusion !== suggested` —— 没有控制测试数据时
      // 建议为 null，此时人工填结论**不算覆盖**（没有建议就谈不上推翻它）。
      // 这里造 2 条「有效」控制测试 ⇒ 建议 = 设计有效且已实施。
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '2' }],
        [generateItemId(code, 'ct', 1, undefined, 'operatingEffective'), { conclusion: '有效', remark: null }],
        [generateItemId(code, 'ct', 2, undefined, 'operatingEffective'), { conclusion: '有效', remark: null }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)
      expect(ctrl.suggestConclusion(code)).toBe('设计有效且已实施')

      ctrl.setConclusion(code, '设计无效', '管理层凌驾于控制之上')
      applySaved(allResponses, saveFn)

      expect(ctrl.getConclusion(code)).toBe('设计无效')
      expect(ctrl.isConclusionOverridden(code)).toBe(true)
      expect(ctrl.getOverrideReason(code)).toBe('管理层凌驾于控制之上')
    })
    scope.stop()
  })

  it('人工结论与自动建议一致 → 不记为覆盖（清除覆盖标记）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '1' }],
        [generateItemId(code, 'ct', 1, undefined, 'operatingEffective'), { conclusion: '有效', remark: null }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)

      ctrl.setConclusion(code, '设计有效且已实施')
      applySaved(allResponses, saveFn)
      expect(ctrl.isConclusionOverridden(code)).toBe(false)
      expect(ctrl.getOverrideReason(code)).toBe('')
    })
    scope.stop()
  })

  it('无自动建议时人工填结论不算覆盖（没建议谈不上推翻）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const code = B23_CYCLES[0].code
      const { ctrl, saveFn, allResponses } = await makeCtrl()
      expect(ctrl.suggestConclusion(code)).toBeNull()

      ctrl.setConclusion(code, '设计无效', '理由')
      applySaved(allResponses, saveFn)
      expect(ctrl.getConclusion(code)).toBe('设计无效')
      expect(ctrl.isConclusionOverridden(code)).toBe(false)
    })
    scope.stop()
  })

  it('applicableCycles 幂等过滤（只留适用循环）', async () => {
    const { applicableCycles } = await import('../composables/useB23ProcessControl')
    const input = [
      { applicable: true, code: 'a' },
      { applicable: false, code: 'b' },
      { applicable: true, code: 'c' },
    ]
    const once = applicableCycles(input)
    expect(once.map(c => c.code)).toEqual(['a', 'c'])
    // 幂等：再过滤一次结果不变
    expect(applicableCycles(once)).toEqual(once)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 仪表盘统计
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 仪表盘统计', () => {
  it('初始态：全部适用、零控制点、零缺陷', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      const s = ctrl.dashboardStats.value
      expect(s.applicableCount).toBe(B23_CYCLES.length)
      expect(s.completedCount).toBe(0)
      expect(s.totalControlPoints).toBe(0)
      expect(s.totalKeyControls).toBe(0)
      expect(s.totalDeficiencies).toBe(0)
    })
    scope.stop()
  })

  it('置一个循环为不适用后 applicableCount 减一（computed 实时联动）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'applicability'), { conclusion: 'N', remark: null }],
      ])
      const { ctrl } = await makeCtrl(seed)
      expect(ctrl.dashboardStats.value.applicableCount).toBe(B23_CYCLES.length - 1)
    })
    scope.stop()
  })

  it('关键控制点计入 totalKeyControls；待穿行数随 asDesigned 减少', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const code = B23_CYCLES[0].code
      const seed = new Map<string, any>([
        [generateItemId(code, 'ctrl-count'), { conclusion: null, remark: '2' }],
        [generateItemId(code, 'ctrl', 1, undefined, 'isKeyControl'), { conclusion: '是', remark: null }],
        [generateItemId(code, 'ctrl', 2, undefined, 'isKeyControl'), { conclusion: '是', remark: null }],
      ])
      const { ctrl, saveFn, allResponses } = await makeCtrl(seed)
      expect(ctrl.dashboardStats.value.totalControlPoints).toBe(2)
      expect(ctrl.dashboardStats.value.totalKeyControls).toBe(2)
      const pendingBefore = ctrl.dashboardStats.value.pendingWalkthroughCount
      expect(pendingBefore).toBe(2)

      ctrl.setWalkthroughField(code, 1, 'asDesigned', '是')
      applySaved(allResponses, saveFn)
      expect(ctrl.dashboardStats.value.pendingWalkthroughCount).toBe(pendingBefore - 1)
    })
    scope.stop()
  })

  it('effectivenessDistribution 各档之和不超过适用循环数', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      const d = ctrl.dashboardStats.value.effectivenessDistribution
      const sum = d.effective + d.partiallyEffective + d.ineffective + d.notApplicable
      expect(sum).toBeLessThanOrEqual(B23_CYCLES.length)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Entity_Level_Context（B22A 只读联动）
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — Entity_Level_Context', () => {
  it('初始为 null（B22A 未完成）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      expect(ctrl.entityLevelContext.value).toBeNull()
    })
    scope.stop()
  })

  it('onControlConclusionChanged 更新面板数据', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      ctrl.onControlConclusionChanged({
        elementScores: { 1: '有效', 2: '有效', 3: '基本有效', 4: '有效', 5: '有效' },
        itDependency: '中',
        overallConclusion: '整体有效',
        completed: true,
      } as any)

      const ctx = ctrl.entityLevelContext.value
      expect(ctx).not.toBeNull()
      expect(ctx!.completed).toBe(true)
      expect(ctx!.overallConclusion).toBe('整体有效')
      expect(ctx!.elementScores[1]).toBe('有效')
    })
    scope.stop()
  })

  it('B22A 未完成时 completed=false 如实透传', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      ctrl.onControlConclusionChanged({
        elementScores: { 1: null, 2: null, 3: null, 4: null, 5: null },
        itDependency: '',
        overallConclusion: null,
        completed: false,
      } as any)
      expect(ctrl.entityLevelContext.value!.completed).toBe(false)
    })
    scope.stop()
  })

  it('控制环境（要素1）无效时面板如实记录，供宿主渲染警告', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      ctrl.onControlConclusionChanged({
        elementScores: { 1: '无效', 2: '有效', 3: '有效', 4: '有效', 5: '有效' },
        itDependency: '高',
        overallConclusion: '存在重大缺陷',
        completed: true,
      } as any)
      expect(ctrl.entityLevelContext.value!.elementScores[1]).toBe('无效')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 联动（B50 / 实质性程序）
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 联动映射', () => {
  it('linkageInfo 每个适用循环一条，且字段来自 B23_CYCLES', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { ctrl } = await makeCtrl()
      const info = ctrl.linkageInfo.value
      expect(info).toHaveLength(B23_CYCLES.length)
      expect(info.map(i => i.code)).toEqual(B23_CYCLES.map(c => c.code))
      expect(info.map(i => i.name)).toEqual(B23_CYCLES.map(c => c.name))
    })
    scope.stop()
  })

  it('CONCLUSION_TO_B50_IMPACT 覆盖全部结论枚举且非空', async () => {
    const { CONCLUSION_TO_B50_IMPACT, CYCLE_CONCLUSION_OPTIONS } =
      await import('../composables/useB23ProcessControl')
    for (const opt of CYCLE_CONCLUSION_OPTIONS) {
      expect(
        CONCLUSION_TO_B50_IMPACT[opt],
        `结论「${opt}」缺 B50 影响映射 → 风险评估联动会丢这一档`,
      ).toBeTruthy()
    }
  })

  it('「设计无效」→ 需扩展实质性程序；「设计有效且已实施」→ 不需要', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { generateItemId } = await import('../composables/useB23ProcessControl')
      const bad = B23_CYCLES[0].code
      const good = B23_CYCLES[1].code
      const seed = new Map<string, any>([
        [generateItemId(bad, 'cycle-conclusion'), { conclusion: '设计无效', remark: null }],
        [generateItemId(good, 'cycle-conclusion'), { conclusion: '设计有效且已实施', remark: null }],
      ])
      const { ctrl } = await makeCtrl(seed)
      const info = ctrl.linkageInfo.value
      const badRow = info.find(i => i.code === bad)!
      const goodRow = info.find(i => i.code === good)!
      expect(badRow.needsExtendedProcedures).toBe(true)
      expect(goodRow.needsExtendedProcedures).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 保存行为（useB23FormData，与循环模型无关）
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 — 保存行为', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue({ data: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
    mockGet.mockReset()
    mockPut.mockReset()
  })

  it('saveDebouncedText 在 2000ms 后才落库', async () => {
    const { useB23FormData } = await import('../composables/useB23FormData')
    const scope = effectScope()
    scope.run(() => {
      const formApi = useB23FormData(ref('wp-test'))
      formApi.saveDebouncedText({
        item_id: 'B23-c1-ctrl-1-subProcess', conclusion: null, remark: '测试', wp_ref: null,
      })
      vi.advanceTimersByTime(1000)
      expect(mockPut).not.toHaveBeenCalled()
      vi.advanceTimersByTime(1000)
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })

  it('连续输入只触发最后一次保存', async () => {
    const { useB23FormData } = await import('../composables/useB23FormData')
    const scope = effectScope()
    scope.run(() => {
      const formApi = useB23FormData(ref('wp-test'))
      for (const text of ['第一次', '第二次', '第三次']) {
        formApi.saveDebouncedText({
          item_id: 'B23-c1-ctrl-1-subProcess', conclusion: null, remark: text, wp_ref: null,
        })
        vi.advanceTimersByTime(500)
      }
      expect(mockPut).not.toHaveBeenCalled()
      vi.advanceTimersByTime(2000)
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })
})
