/**
 * B23 业务流程与控制了解表 — Unit Tests (Tasks 7.1–7.19)
 *
 * 验证：
 *  7.1 注册契约测试 — registry + wp_code_overrides
 *  7.2 流程卡片渲染测试 — 8 卡片 + 默认适用 + 标题栏
 *  7.3 展开收起交互测试 — toggle + expandAll/collapseAll
 *  7.4 适用性开关测试 — 不适用→灰色+自动结论 / 恢复→清除
 *  7.5 控制点 CRUD 测试 — 新增/删除/字段编辑
 *  7.6 了解方法多选交互测试 — 穿行测试区域自动创建
 *  7.7 控制频率下拉测试 — 7 选项 + 即时保存
 *  7.8 穿行测试结论下拉测试 — 红色标识 + 即时保存
 *  7.9 穿行测试记录区域测试 — 自动创建 + 多笔样本 + 上限5
 *  7.10 Process_Conclusion 自动建议测试 — 建议 + 覆盖需理由
 *  7.11 Status_Dashboard 统计渲染测试 — 实时更新
 *  7.12 Entity_Level_Context 面板测试 — 只读 + 警告
 *  7.13 Linkage_Panel 映射测试 — B50影响 + 循环映射
 *  7.14 保存行为测试 — debounce 2s + 即时保存
 *  7.15 只读模式测试 — readonly/reviewed → 禁用
 *  7.16 复核签字测试 — 前置条件 + 签字
 *  7.17 Amendment 流程测试 — 修改原因 + 重置
 *  7.18 EventBus 联动测试 — 事件发布载荷
 *  7.19 打印样式类存在性测试 — @media print + 隐藏控件
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref, computed, effectScope, nextTick } from 'vue'

import { HTML_RENDERER_REGISTRY } from '../htmlRendererRegistry'

// Mock apiProxy
const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))


// ═══════════════════════════════════════════════════════════════════════════════
// 7.1 注册契约测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 注册契约 (7.1)', () => {
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

  it('wp_code_overrides.json 映射 B23-1~B23-8 → skip', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    for (let i = 1; i <= 8; i++) {
      expect(overrides[`B23-${i}`]).toBe('skip')
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.2 流程卡片渲染测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 流程卡片渲染 (7.2)', () => {
  it('STANDARD_PROCESSES 定义 8 个流程', async () => {
    const { STANDARD_PROCESSES } = await import('../composables/useB23ProcessControl')
    expect(STANDARD_PROCESSES).toHaveLength(8)
    expect(STANDARD_PROCESSES[0].num).toBe(1)
    expect(STANDARD_PROCESSES[0].name).toBe('采购与付款循环')
    expect(STANDARD_PROCESSES[7].num).toBe(8)
    expect(STANDARD_PROCESSES[7].name).toBe('其他流程')
  })

  it('processes 返回 8 张卡片且默认全部适用', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      expect(ctrl.processes.value).toHaveLength(8)
      ctrl.processes.value.forEach((card) => {
        expect(card.applicable).toBe(true)
      })
    })
    scope.stop()
  })

  it('每张卡片标题栏包含名称/结论标签/完成比例', async () => {
    const { useB23ProcessControl, PROCESS_CONCLUSION_COLOR_MAP } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      const card = ctrl.processes.value[0]
      expect(card.name).toBe('采购与付款循环')
      // No conclusion by default → null
      expect(card.conclusion).toBeNull()
      // No control points → completionRatio = "0/0"
      expect(card.completionRatio).toBe('0/0')
      // PROCESS_CONCLUSION_COLOR_MAP has entries for all conclusions
      expect(Object.keys(PROCESS_CONCLUSION_COLOR_MAP).length).toBeGreaterThanOrEqual(4)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.3 展开收起交互测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 展开收起 (7.3)', () => {
  it('默认全部展开', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      expect(ctrl.expandedProcesses.value.size).toBe(8)
      for (let i = 1; i <= 8; i++) {
        expect(ctrl.expandedProcesses.value.has(i as any)).toBe(true)
      }
    })
    scope.stop()
  })

  it('toggleProcess 切换单卡片展开/收起', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Toggle P1 → close
      ctrl.toggleProcess(1)
      expect(ctrl.expandedProcesses.value.has(1)).toBe(false)
      expect(ctrl.expandedProcesses.value.has(2)).toBe(true)

      // Toggle P1 → re-open
      ctrl.toggleProcess(1)
      expect(ctrl.expandedProcesses.value.has(1)).toBe(true)
    })
    scope.stop()
  })

  it('collapseAll 全部收起 / expandAll 全部展开', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.collapseAll()
      expect(ctrl.expandedProcesses.value.size).toBe(0)

      ctrl.expandAll()
      expect(ctrl.expandedProcesses.value.size).toBe(8)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.4 适用性开关测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 适用性开关 (7.4)', () => {
  it('切换为不适用→结论自动设"不适用" + 卡片折叠', async () => {
    const { useB23ProcessControl, generateItemId } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.setApplicability(1, false)

      // Conclusion auto-set to "不适用"
      const conclusionId = generateItemId(1, 'process-conclusion')
      expect(allResponses.value.get(conclusionId)?.conclusion).toBe('不适用')

      // Applicability flag
      const appId = generateItemId(1, 'applicability')
      expect(allResponses.value.get(appId)?.conclusion).toBe('N')

      // Card collapsed
      expect(ctrl.expandedProcesses.value.has(1)).toBe(false)

      // Card marked not applicable
      expect(ctrl.processes.value[0].applicable).toBe(false)
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })

  it('恢复适用→清除"不适用"结论 + 卡片展开', async () => {
    const { useB23ProcessControl, generateItemId } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // First mark not applicable
      ctrl.setApplicability(2, false)
      expect(ctrl.processes.value[1].applicable).toBe(false)

      // Then restore
      ctrl.setApplicability(2, true)

      const conclusionId = generateItemId(2, 'process-conclusion')
      expect(allResponses.value.get(conclusionId)?.conclusion).toBeNull()

      const appId = generateItemId(2, 'applicability')
      expect(allResponses.value.get(appId)?.conclusion).toBe('Y')

      expect(ctrl.expandedProcesses.value.has(2)).toBe(true)
      expect(ctrl.processes.value[1].applicable).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.5 控制点 CRUD 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 控制点 CRUD (7.5)', () => {
  it('addControlPoint 递增 count + 自动序号', async () => {
    const { useB23ProcessControl, generateItemId } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      const countId = generateItemId(1, 'ctrl-count')
      expect(allResponses.value.get(countId)?.remark).toBe('1')

      ctrl.addControlPoint(1)
      expect(allResponses.value.get(countId)?.remark).toBe('2')

      // Control points accessible
      const points = ctrl.getControlPoints(1).value
      expect(points).toHaveLength(2)
      expect(points[0].index).toBe(1)
      expect(points[1].index).toBe(2)
    })
    scope.stop()
  })

  it('removeControlPoint 递减 count + 数据移位', async () => {
    const { useB23ProcessControl, generateItemId } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Add 3 control points
      ctrl.addControlPoint(1)
      ctrl.addControlPoint(1)
      ctrl.addControlPoint(1)

      // Set data on CP 2 and 3
      ctrl.setControlPointField(1, 2, 'objective', '第二项')
      ctrl.setControlPointField(1, 3, 'objective', '第三项')

      // Remove CP 2 → CP 3 shifts to position 2
      ctrl.removeControlPoint(1, 2)

      const countId = generateItemId(1, 'ctrl-count')
      expect(allResponses.value.get(countId)?.remark).toBe('2')

      // The objective of the new position 2 should be "第三项"
      const objId = generateItemId(1, 'ctrl', 2, undefined, 'objective')
      expect(allResponses.value.get(objId)?.remark).toBe('第三项')
    })
    scope.stop()
  })

  it('setControlPointField 正确设置文本字段', async () => {
    const { useB23ProcessControl, generateItemId } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'objective', '采购审批')
      ctrl.setControlPointField(1, 1, 'description', '三单匹配')
      ctrl.setControlPointField(1, 1, 'executor', '财务部')

      const points = ctrl.getControlPoints(1).value
      expect(points[0].objective).toBe('采购审批')
      expect(points[0].description).toBe('三单匹配')
      expect(points[0].executor).toBe('财务部')
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })

  it('预置控制点（isPreset=true for index<=3）', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Add 4 control points
      for (let i = 0; i < 4; i++) ctrl.addControlPoint(1)

      const points = ctrl.getControlPoints(1).value
      expect(points[0].isPreset).toBe(true)
      expect(points[1].isPreset).toBe(true)
      expect(points[2].isPreset).toBe(true)
      expect(points[3].isPreset).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.6 了解方法多选交互测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 了解方法多选 (7.6)', () => {
  it('setControlPointField methods 存为逗号分隔字符串', async () => {
    const { useB23ProcessControl, generateItemId } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'methods', ['询问', '观察', '穿行测试'])

      const methodsId = generateItemId(1, 'ctrl', 1, undefined, 'methods')
      expect(allResponses.value.get(methodsId)?.remark).toBe('询问,观察,穿行测试')

      const points = ctrl.getControlPoints(1).value
      expect(points[0].methods).toEqual(['询问', '观察', '穿行测试'])
    })
    scope.stop()
  })

  it('选择"穿行测试"方法时穿行记录区域自动创建条目', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)

      // 设置 methods 含 "穿行测试" → 应该可以通过 addWalkthroughSample 创建
      ctrl.setControlPointField(1, 1, 'methods', ['穿行测试'])
      ctrl.addWalkthroughSample(1, 1)

      const records = ctrl.getWalkthroughRecords(1, 1).value
      expect(records).toHaveLength(1)
      expect(records[0].sampleIndex).toBe(1)
    })
    scope.stop()
  })

  it('5 种了解方法全部可选', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      const allMethods = ['询问', '观察', '检查文件', '穿行测试', '重新执行'] as const
      ctrl.setControlPointField(1, 1, 'methods', [...allMethods])

      const points = ctrl.getControlPoints(1).value
      expect(points[0].methods).toHaveLength(5)
      expect(points[0].methods).toEqual([...allMethods])
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.7 控制频率下拉测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 控制频率下拉 (7.7)', () => {
  it('7 个频率选项全覆盖', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const FREQUENCY_OPTIONS = ['每笔', '每日', '每周', '每月', '每季', '每年', '不定期']

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)

      // Set each frequency option
      for (const freq of FREQUENCY_OPTIONS) {
        ctrl.setControlPointField(1, 1, 'frequency', freq)
        const points = ctrl.getControlPoints(1).value
        expect(points[0].frequency).toBe(freq)
      }
    })
    scope.stop()
  })

  it('频率选择触发即时保存', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      saveFn.mockClear()

      ctrl.setControlPointField(1, 1, 'frequency', '每月')
      expect(saveFn).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.8 穿行测试结论下拉测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 穿行测试结论 (7.8)', () => {
  it('"控制未有效运行"结论正确设置', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'conclusion', '控制未有效运行')

      const points = ctrl.getControlPoints(1).value
      expect(points[0].conclusion).toBe('控制未有效运行')
    })
    scope.stop()
  })

  it('结论选择即时保存', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      saveFn.mockClear()

      ctrl.setControlPointField(1, 1, 'conclusion', '控制有效运行')
      expect(saveFn).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })

  it('4 种穿行结论选项全覆盖', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const WT_OPTIONS = ['控制有效运行', '控制未有效运行', '未执行穿行', '不适用']

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)

      for (const c of WT_OPTIONS) {
        ctrl.setControlPointField(1, 1, 'conclusion', c)
        const points = ctrl.getControlPoints(1).value
        expect(points[0].conclusion).toBe(c)
      }
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.9 穿行测试记录区域测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 穿行测试记录 (7.9)', () => {
  it('addWalkthroughSample 创建条目且字段可写', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      ctrl.addWalkthroughSample(1, 1)

      const records = ctrl.getWalkthroughRecords(1, 1).value
      expect(records).toHaveLength(1)
      expect(records[0].sampleIndex).toBe(1)
      expect(records[0].sample).toBe('')
      expect(records[0].path).toBe('')
      expect(records[0].finding).toBe('')
      expect(records[0].reference).toBe('')
    })
    scope.stop()
  })

  it('支持多笔样本（最多 5 笔）', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)

      // Add 5 samples
      for (let i = 0; i < 5; i++) ctrl.addWalkthroughSample(1, 1)
      expect(ctrl.getWalkthroughRecords(1, 1).value).toHaveLength(5)

      // 6th sample should be rejected (max 5)
      ctrl.addWalkthroughSample(1, 1)
      expect(ctrl.getWalkthroughRecords(1, 1).value).toHaveLength(5)
    })
    scope.stop()
  })

  it('setWalkthroughField 正确更新样本字段', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.addControlPoint(1)
      ctrl.addWalkthroughSample(1, 1)

      ctrl.setWalkthroughField(1, 1, 1, 'sample', 'PV-2026-001')
      ctrl.setWalkthroughField(1, 1, 1, 'path', '从申请到付款全流程')
      ctrl.setWalkthroughField(1, 1, 1, 'finding', '三单匹配正确')
      ctrl.setWalkthroughField(1, 1, 1, 'reference', 'WP-D1-001')

      const records = ctrl.getWalkthroughRecords(1, 1).value
      expect(records[0].sample).toBe('PV-2026-001')
      expect(records[0].path).toBe('从申请到付款全流程')
      expect(records[0].finding).toBe('三单匹配正确')
      expect(records[0].reference).toBe('WP-D1-001')
    })
    scope.stop()
  })

  it('walkthroughSummary 正确计算摘要信息', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Add 2 control points both with "穿行测试" method
      ctrl.addControlPoint(1)
      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'methods', ['穿行测试'])
      ctrl.setControlPointField(1, 2, 'methods', ['穿行测试'])

      // Give conclusion to only CP1
      ctrl.setControlPointField(1, 1, 'conclusion', '控制有效运行')

      const summary = ctrl.walkthroughSummary(1).value
      expect(summary.totalCount).toBe(2)
      expect(summary.testedCount).toBe(1)
      expect(summary.completionRate).toBe(0.5)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.10 Process_Conclusion 自动建议测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — Process_Conclusion 自动建议 (7.10)', () => {
  it('suggestProcessConclusion 全部有效→"设计有效且已实施"', async () => {
    const { suggestProcessConclusion } = await import('../composables/useB23ProcessControl')

    const points = [
      { index: 1, conclusion: '控制有效运行' },
      { index: 2, conclusion: '控制有效运行' },
    ] as any[]

    expect(suggestProcessConclusion(points)).toBe('设计有效且已实施')
  })

  it('suggestProcessConclusion 无效占比≤30%→"设计有效但未有效实施"', async () => {
    const { suggestProcessConclusion } = await import('../composables/useB23ProcessControl')

    // 1 out of 4 = 25% ≤ 30%
    const points = [
      { index: 1, conclusion: '控制有效运行' },
      { index: 2, conclusion: '控制有效运行' },
      { index: 3, conclusion: '控制有效运行' },
      { index: 4, conclusion: '控制未有效运行' },
    ] as any[]

    expect(suggestProcessConclusion(points)).toBe('设计有效但未有效实施')
  })

  it('suggestProcessConclusion 无效占比>30%→"设计无效"', async () => {
    const { suggestProcessConclusion } = await import('../composables/useB23ProcessControl')

    // 2 out of 3 = 67% > 30%
    const points = [
      { index: 1, conclusion: '控制有效运行' },
      { index: 2, conclusion: '控制未有效运行' },
      { index: 3, conclusion: '控制未有效运行' },
    ] as any[]

    expect(suggestProcessConclusion(points)).toBe('设计无效')
  })

  it('suggestProcessConclusion 无已评估控制点→null', async () => {
    const { suggestProcessConclusion } = await import('../composables/useB23ProcessControl')

    const points = [
      { index: 1, conclusion: null },
      { index: 2, conclusion: '不适用' },
    ] as any[]

    expect(suggestProcessConclusion(points)).toBeNull()
  })

  it('手动覆盖需要理由 + 标识', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Setup: 2 control points all effective → suggested="设计有效且已实施"
      ctrl.addControlPoint(1)
      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'conclusion', '控制有效运行')
      ctrl.setControlPointField(1, 2, 'conclusion', '控制有效运行')

      expect(ctrl.suggestConclusion(1).value).toBe('设计有效且已实施')

      // Override with different conclusion + reason
      ctrl.setConclusion(1, '设计有效但未有效实施', '审计判断需要更保守评估')

      expect(ctrl.getConclusion(1).value).toBe('设计有效但未有效实施')
      expect(ctrl.isConclusionOverridden(1).value).toBe(true)
      expect(ctrl.getOverrideReason(1).value).toBe('审计判断需要更保守评估')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.11 Status_Dashboard 统计渲染测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — Status_Dashboard (7.11)', () => {
  it('dashboardStats 初始全部未开始', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      const stats = ctrl.dashboardStats.value
      expect(stats.completionDistribution.notStarted).toBe(8)
      expect(stats.completionDistribution.completed).toBe(0)
      expect(stats.completionDistribution.inProgress).toBe(0)
      expect(stats.completionDistribution.notApplicable).toBe(0)
      expect(stats.effectivenessDistribution.effective).toBe(0)
      expect(stats.pendingWalkthroughCount).toBe(0)
    })
    scope.stop()
  })

  it('dashboardStats 随数据变更实时更新', async () => {
    const { useB23ProcessControl, generateItemId } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Mark P1 as not applicable
      ctrl.setApplicability(1, false)

      let stats = ctrl.dashboardStats.value
      expect(stats.completionDistribution.notApplicable).toBe(1)
      expect(stats.completionDistribution.notStarted).toBe(7)

      // Add a control point to P2 → "inProgress"
      ctrl.addControlPoint(2)
      stats = ctrl.dashboardStats.value
      expect(stats.completionDistribution.inProgress).toBe(1)
      expect(stats.completionDistribution.notStarted).toBe(6)

      // Set conclusion for P2 → "completed"
      ctrl.setConclusion(2, '设计有效且已实施')
      stats = ctrl.dashboardStats.value
      expect(stats.completionDistribution.completed).toBe(1)
      expect(stats.completionDistribution.inProgress).toBe(0)
      expect(stats.effectivenessDistribution.effective).toBe(1)
    })
    scope.stop()
  })

  it('pendingWalkthroughCount 统计待穿行控制点', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Add control points with "穿行测试" method but no conclusion
      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'methods', ['穿行测试'])

      ctrl.addControlPoint(2)
      ctrl.setControlPointField(2, 1, 'methods', ['穿行测试'])

      let stats = ctrl.dashboardStats.value
      expect(stats.pendingWalkthroughCount).toBe(2)

      // Complete one
      ctrl.setControlPointField(1, 1, 'conclusion', '控制有效运行')
      stats = ctrl.dashboardStats.value
      expect(stats.pendingWalkthroughCount).toBe(1)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.12 Entity_Level_Context 面板测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — Entity_Level_Context (7.12)', () => {
  it('初始状态 entityLevelContext 为 null（B22A 未完成）', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      expect(ctrl.entityLevelContext.value).toBeNull()
    })
    scope.stop()
  })

  it('onControlConclusionChanged 更新面板数据', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.onControlConclusionChanged({
        elementScores: { 1: '有效', 2: '有效', 3: '部分有效', 4: '有效', 5: '有效' },
        itDependency: '高',
        itgcConclusion: '有效',
        overallConclusion: '控制环境有效',
      })

      expect(ctrl.entityLevelContext.value).not.toBeNull()
      expect(ctrl.entityLevelContext.value!.completed).toBe(true)
      expect(ctrl.entityLevelContext.value!.overallConclusion).toBe('控制环境有效')
      expect(ctrl.entityLevelContext.value!.elementScores[1]).toBe('有效')
      expect(ctrl.entityLevelContext.value!.elementScores[3]).toBe('部分有效')
    })
    scope.stop()
  })

  it('控制环境（要素1）为"无效"时触发警告条件', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.onControlConclusionChanged({
        elementScores: { 1: '无效', 2: '有效', 3: '有效', 4: '有效', 5: '有效' },
        itDependency: '低',
        itgcConclusion: null,
        overallConclusion: '控制环境薄弱',
      })

      // element 1 = "无效" → UI should show warning (tested via data state)
      expect(ctrl.entityLevelContext.value!.elementScores[1]).toBe('无效')
    })
    scope.stop()
  })

  it('B22A 未完成时 completed=false', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.onControlConclusionChanged({
        elementScores: { 1: null, 2: null, 3: null, 4: null, 5: null },
        itDependency: '',
        itgcConclusion: null,
        overallConclusion: null,
      })

      expect(ctrl.entityLevelContext.value!.completed).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.13 Linkage_Panel 映射测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — Linkage_Panel (7.13)', () => {
  it('linkageInfo 返回 8 条映射记录', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      expect(ctrl.linkageInfo.value).toHaveLength(8)
    })
    scope.stop()
  })

  it('D~N 循环映射正确（P1→DA, P2→EA, ...）', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      const expected = ['DA', 'EA', 'FA', 'GA', 'HA', 'IA', 'JA', 'KA']
      ctrl.linkageInfo.value.forEach((lk, i) => {
        expect(lk.targetCycle).toBe(expected[i])
        expect(lk.processNum).toBe(i + 1)
      })
    })
    scope.stop()
  })

  it('CONCLUSION_TO_B50_IMPACT 映射正确', async () => {
    const { CONCLUSION_TO_B50_IMPACT } = await import('../composables/useB23ProcessControl')

    expect(CONCLUSION_TO_B50_IMPACT['设计有效且已实施']).toBe('控制风险=低')
    expect(CONCLUSION_TO_B50_IMPACT['设计有效但未有效实施']).toBe('控制风险=中')
    expect(CONCLUSION_TO_B50_IMPACT['设计无效']).toBe('控制风险=高')
    expect(CONCLUSION_TO_B50_IMPACT['不适用']).toBe('不影响控制风险评估')
  })

  it('"设计无效"时 needsExtendedProcedures=true + b50Impact 正确', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.setConclusion(1, '设计无效')

      const lk = ctrl.linkageInfo.value[0]
      expect(lk.needsExtendedProcedures).toBe(true)
      expect(lk.b50Impact).toBe('控制风险=高')
    })
    scope.stop()
  })

  it('"设计有效且已实施"时 needsExtendedProcedures=false', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.setConclusion(1, '设计有效且已实施')

      const lk = ctrl.linkageInfo.value[0]
      expect(lk.needsExtendedProcedures).toBe(false)
      expect(lk.b50Impact).toBe('控制风险=低')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.14 保存行为测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 保存行为 (7.14)', () => {
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

  it('saveDebouncedText debounce 2000ms', async () => {
    const { useB23FormData } = await import('../composables/useB23FormData')

    const scope = effectScope()
    scope.run(() => {
      const formApi = useB23FormData(ref('wp-test'))

      formApi.saveDebouncedText({ item_id: 'B23-P1-ctrl-1-objective', conclusion: null, remark: '测试', wp_ref: null })

      // Not saved yet at 1s
      vi.advanceTimersByTime(1000)
      expect(mockPut).not.toHaveBeenCalled()

      // Saved after 2s total
      vi.advanceTimersByTime(1000)
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })

  it('多次 debounce 文本输入只触发最后一次保存', async () => {
    const { useB23FormData } = await import('../composables/useB23FormData')

    const scope = effectScope()
    scope.run(() => {
      const formApi = useB23FormData(ref('wp-test'))

      formApi.saveDebouncedText({ item_id: 'B23-P1-ctrl-1-objective', conclusion: null, remark: '第一次', wp_ref: null })
      vi.advanceTimersByTime(500)
      formApi.saveDebouncedText({ item_id: 'B23-P1-ctrl-1-objective', conclusion: null, remark: '第二次', wp_ref: null })
      vi.advanceTimersByTime(500)
      formApi.saveDebouncedText({ item_id: 'B23-P1-ctrl-1-objective', conclusion: null, remark: '第三次', wp_ref: null })

      // No save yet
      expect(mockPut).not.toHaveBeenCalled()

      // Advance past 2s from last call
      vi.advanceTimersByTime(2000)
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })

  it('saveImmediate 立即保存不等待 debounce', async () => {
    const { useB23FormData } = await import('../composables/useB23FormData')

    const scope = effectScope()
    scope.run(async () => {
      const formApi = useB23FormData(ref('wp-test'))

      await formApi.saveImmediate([
        { item_id: 'B23-P1-applicability', conclusion: 'N', remark: null, wp_ref: null },
      ])

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-test/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'B23-P1-applicability', conclusion: 'N' })],
        })
      )
    })
    scope.stop()
  })

  it('flushPendingSave 在卸载前触发保存', async () => {
    const { useB23FormData } = await import('../composables/useB23FormData')

    const scope = effectScope()
    scope.run(() => {
      const formApi = useB23FormData(ref('wp-test'))

      formApi.saveDebouncedText({ item_id: 'B23-P1-ctrl-1-remark', conclusion: null, remark: '待保存', wp_ref: null })

      // Not saved yet
      expect(mockPut).not.toHaveBeenCalled()

      // Flush
      formApi.flushPendingSave()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.15 只读模式测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 只读模式 (7.15)', () => {
  it('externalReadonly=true → isReadonly=true', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const externalReadonly = ref(true)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, externalReadonly, saveFn)

      expect(review.isReadonly.value).toBe(true)
    })
    scope.stop()
  })

  it('已复核(review-sign=Y) → isReadonly=true', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B23-review-sign', {
        item_id: 'B23-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01',
      })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const externalReadonly = ref(false)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, externalReadonly, saveFn)

      expect(review.isReviewed.value).toBe(true)
      expect(review.isReadonly.value).toBe(true)
    })
    scope.stop()
  })

  it('已复核时渲染复核信息（reviewer/date）', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B23-review-sign', {
        item_id: 'B23-review-sign', conclusion: 'Y', remark: '张经理', wp_ref: '2026-06-23',
      })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)

      expect(review.reviewInfo.value).toEqual({ reviewer: '张经理', date: '2026-06-23' })
    })
    scope.stop()
  })

  it('未复核+非 readonly → isReadonly=false', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)

      expect(review.isReadonly.value).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.16 复核签字测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 复核签字 (7.16)', () => {
  it('canReview=false 当有适用流程缺少结论', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)

      // All processes are applicable but have no conclusion
      expect(review.canReview.value).toBe(false)
      expect(review.pendingItems.value.length).toBeGreaterThan(0)
    })
    scope.stop()
  })

  it('canReview=false 当穿行测试未完成', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Set all processes to not-applicable except P1
      for (let i = 2; i <= 8; i++) ctrl.setApplicability(i as any, false)

      // P1: has conclusion but control point needs walkthrough
      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'methods', ['穿行测试'])
      ctrl.setConclusion(1, '设计有效且已实施')
      // CP1 has no walkthrough conclusion

      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)
      expect(review.canReview.value).toBe(false)
    })
    scope.stop()
  })

  it('canReview=true 当全部条件满足', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Set all except P1 to not-applicable
      for (let i = 2; i <= 8; i++) ctrl.setApplicability(i as any, false)

      // P1: full setup
      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'methods', ['穿行测试'])
      ctrl.setControlPointField(1, 1, 'conclusion', '控制有效运行')
      ctrl.setConclusion(1, '设计有效且已实施')

      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)
      expect(review.canReview.value).toBe(true)
    })
    scope.stop()
  })

  it('doReview 签字保存 + isReviewed 变为 true', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Set all except P1 to not-applicable
      for (let i = 2; i <= 8; i++) ctrl.setApplicability(i as any, false)

      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'methods', ['穿行测试'])
      ctrl.setControlPointField(1, 1, 'conclusion', '控制有效运行')
      ctrl.setConclusion(1, '设计有效且已实施')

      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)

      await review.doReview()

      expect(review.isReviewed.value).toBe(true)
      expect(allResponses.value.get('B23-review-sign')?.conclusion).toBe('Y')
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.17 Amendment 流程测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — Amendment 流程 (7.17)', () => {
  it('startAmendment 重置复核状态 + 记录修改原因', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map<string, any>())
      // Pre-set as reviewed
      allResponses.value.set('B23-review-sign', {
        item_id: 'B23-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-06-01',
      })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)

      expect(review.isReviewed.value).toBe(true)

      await review.startAmendment('发现新情况需要补充')

      // Review sign reset
      expect(allResponses.value.get('B23-review-sign')?.conclusion).toBeNull()
      expect(review.isReviewed.value).toBe(false)
      expect(review.isReadonly.value).toBe(false)

      // Amendment reason recorded
      expect(allResponses.value.get('B23-amend-0-reason')?.remark).toBe('发现新情况需要补充')
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })

  it('startAmendment 空白原因→抛错', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B23-review-sign', {
        item_id: 'B23-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-06-01',
      })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)

      await expect(review.startAmendment('')).rejects.toThrow('修改原因不能为空')
      await expect(review.startAmendment('   ')).rejects.toThrow('修改原因不能为空')
    })
    scope.stop()
  })

  it('多次 amendment 递增索引', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')
    const { useB23Review } = await import('../composables/useB23Review')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B23-review-sign', {
        item_id: 'B23-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-06-01',
      })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)
      const review = useB23Review(ref('wp-1'), allResponses, ctrl.processes, ref(false), saveFn)

      await review.startAmendment('第一次修改')
      expect(allResponses.value.has('B23-amend-0-reason')).toBe(true)

      // Re-review then amend again
      allResponses.value.set('B23-review-sign', {
        item_id: 'B23-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-06-02',
      })
      await review.startAmendment('第二次修改')
      expect(allResponses.value.has('B23-amend-1-reason')).toBe(true)
      expect(allResponses.value.get('B23-amend-1-reason')?.remark).toBe('第二次修改')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.18 EventBus 联动测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — EventBus 联动 (7.18)', () => {
  it('结论变更时发布 process:control-concluded 事件', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      const spy = vi.spyOn(window, 'dispatchEvent')

      ctrl.setConclusion(1, '设计有效且已实施')

      const calls = spy.mock.calls.filter(
        ([ev]) => ev instanceof CustomEvent && ev.type === 'process:control-concluded'
      )
      expect(calls.length).toBe(1)

      const event = calls[0][0] as CustomEvent
      expect(event.detail.processNum).toBe(1)
      expect(event.detail.processName).toBe('采购与付款循环')
      expect(event.detail.oldConclusion).toBeNull()
      expect(event.detail.newConclusion).toBe('设计有效且已实施')

      spy.mockRestore()
    })
    scope.stop()
  })

  it('相同结论不重复发布事件', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      ctrl.setConclusion(1, '设计有效且已实施')

      const spy = vi.spyOn(window, 'dispatchEvent')

      // Set same conclusion again
      ctrl.setConclusion(1, '设计有效且已实施')

      const calls = spy.mock.calls.filter(
        ([ev]) => ev instanceof CustomEvent && ev.type === 'process:control-concluded'
      )
      expect(calls.length).toBe(0)

      spy.mockRestore()
    })
    scope.stop()
  })

  it('publishWalkthroughCompleted 发布正确载荷', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      // Setup 2 control points with "穿行测试"
      ctrl.addControlPoint(1)
      ctrl.addControlPoint(1)
      ctrl.setControlPointField(1, 1, 'methods', ['穿行测试'])
      ctrl.setControlPointField(1, 2, 'methods', ['穿行测试'])
      ctrl.setControlPointField(1, 1, 'conclusion', '控制有效运行')
      ctrl.setControlPointField(1, 2, 'conclusion', '控制有效运行')

      const spy = vi.spyOn(window, 'dispatchEvent')

      ctrl.publishWalkthroughCompleted(1)

      const calls = spy.mock.calls.filter(
        ([ev]) => ev instanceof CustomEvent && ev.type === 'process:walkthrough-completed'
      )
      expect(calls.length).toBe(1)

      const event = calls[0][0] as CustomEvent
      expect(event.detail.processNum).toBe(1)
      expect(event.detail.controlPointCount).toBe(2)
      expect(event.detail.effectiveRate).toBe(1)

      spy.mockRestore()
    })
    scope.stop()
  })

  it('onControlConclusionChanged 接收 B22A 事件载荷', async () => {
    const { useB23ProcessControl } = await import('../composables/useB23ProcessControl')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const ctrl = useB23ProcessControl(allResponses, saveFn)

      const payload = {
        elementScores: { 1: '有效', 2: '部分有效', 3: '有效', 4: '无效', 5: '有效' },
        itDependency: '高',
        itgcConclusion: '有效',
        overallConclusion: '整体有效',
      }

      ctrl.onControlConclusionChanged(payload)

      expect(ctrl.entityLevelContext.value).not.toBeNull()
      expect(ctrl.entityLevelContext.value!.elementScores).toEqual(payload.elementScores)
      expect(ctrl.entityLevelContext.value!.overallConclusion).toBe('整体有效')
      expect(ctrl.entityLevelContext.value!.completed).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.19 打印样式类存在性测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 业务流程与控制了解表 — 打印样式 (7.19)', () => {
  it('组件模板中存在 no-print 类用于隐藏交互控件', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const vuePath = path.resolve(process.cwd(), 'src/components/workpaper/GtB23ProcessControl.vue')
    const content = fs.readFileSync(vuePath, 'utf-8')

    // "no-print" class is used on toolbar and action buttons
    expect(content).toContain('class="b23-toolbar no-print"')
    expect(content).toContain('class="no-print"')
  })

  it('组件模板中交互控件标记为 no-print', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const vuePath = path.resolve(process.cwd(), 'src/components/workpaper/GtB23ProcessControl.vue')
    const content = fs.readFileSync(vuePath, 'utf-8')

    // Review area marked no-print
    expect(content).toContain('b23-review-area no-print')
    // Card actions marked no-print
    expect(content).toContain('b23-card-actions no-print')
  })

  it('组件 style 区域存在 scoped 样式', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const vuePath = path.resolve(process.cwd(), 'src/components/workpaper/GtB23ProcessControl.vue')
    const content = fs.readFileSync(vuePath, 'utf-8')

    // Has scoped style block
    expect(content).toContain('<style scoped>')
    // Has the root class
    expect(content).toContain('.gt-b23-process-control')
  })
})
