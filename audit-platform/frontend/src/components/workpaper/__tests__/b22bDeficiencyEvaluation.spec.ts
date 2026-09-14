/**
 * B22B 内部控制缺陷评价表 — Unit Tests (Tasks 6.1–6.12)
 *
 * 验证：
 *  6.1 注册契约测试 — registry + wp_code_overrides
 *  6.2 缺陷列表渲染 — 缺陷条目 + 来源只读 + 已消除
 *  6.3 缺陷分类交互 — 下拉 + 默认映射 + 手动修改
 *  6.4 多维度评价表单 — 报表项目多选 + 金额 + 补偿性控制 + 纠正措施
 *  6.5 重要性水平对比 — 超过/未超过颜色 + B15 不可用手动输入
 *  6.6 严重程度评定 — 建议 + 下拉 + 覆盖需理由 + 已手动调整
 *  6.7 保存行为 — debounce 2s + 即时保存 + emit save
 *  6.8 整体结论汇总 — 自动计算 + 统计 + 审计影响提示
 *  6.9 只读模式 — readonly / reviewed → 全禁用
 *  6.10 复核签字 — 前置条件 + 签字 + emit completed
 *  6.11 Amendment 流程 — 启动 → 原因校验 → 重置复核
 *  6.12 EventBus 联动 — 监听 + 发布
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
  ElMessage: { error: vi.fn(), warning: vi.fn() },
}))

// Mock eventBus
const mockEmit = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (...args: any[]) => mockEmit(...args),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

import type { ChecklistItem, ChecklistResponse } from '../composables/useB22BFormData'
import {
  suggestSeverity,
  computeOverallConclusion,
  compareMateriality,
  computeSeverityStats,
  generateItemId,
  defaultCategory,
  SEVERITY_LEVELS,
  DEFICIENCY_CATEGORIES,
  type SeverityLevel,
  type DeficiencyCategory,
  type EvaluationItem,
} from '../composables/useB22BDeficiency'
import { useB22BDeficiency } from '../composables/useB22BDeficiency'
import { useB22BReview } from '../composables/useB22BReview'

// ─── Helpers ─────────────────────────────────────────────────────────────────

const noopSave = async (_items: ChecklistItem[]) => {}

function makeEvaluationItem(overrides?: Partial<EvaluationItem>): EvaluationItem {
  return {
    source: {
      tab: 1, subPanel: null, index: 1,
      controlPoint: '测试控制要点', deficiencyType: '设计无效', elementName: '控制环境',
    },
    category: null,
    affectedAccounts: [],
    potentialMisstatement: null,
    hasCompensatingControl: null,
    compensatingControlDesc: '',
    hasCorrectiveAction: null,
    correctiveActionDesc: '',
    severity: null,
    severityOverridden: false,
    overrideReason: '',
    eliminated: false,
    ...overrides,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 6.1 注册契约测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 注册契约 (6.1)', () => {
  it('registry 包含 b22b-deficiency-evaluation 条目且字段正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b22b-deficiency-evaluation')
    expect(entry).toBeDefined()
    expect(entry!.componentType).toBe('b22b-deficiency-evaluation')
    expect(entry!.icon).toBe('⚠️')
    expect(entry!.label).toBe('B22B 内部控制缺陷评价表')
    expect(entry!.emits).toEqual(['save', 'completed'])
    expect(entry!.contextProps).toBe('standard')
  })

  it('wp_code_overrides.json 映射 B22B → b22b-control-matrix（方案 A：B22B 恢复为控制矩阵登记册）', () => {
    // 方案 A：B22B wp_code 改指向控制矩阵登记册（致同源模板 B22B 真实结构）；
    // 缺陷评价组件 b22b-deficiency-evaluation 文件保留（兼容期），但 B22B 不再路由它。
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['B22B']).toBe('b22b-control-matrix')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.2 缺陷列表渲染测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 缺陷列表渲染 (6.2)', () => {
  it('syncFromEvent adds items to deficiencyItems list', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [
          { tab: 1, subPanel: null, index: 1, controlPoint: '要点1', deficiencyType: '设计无效', elementName: '控制环境' },
          { tab: 2, subPanel: null, index: 2, controlPoint: '要点2', deficiencyType: '未实施', elementName: '风险评估' },
        ],
        removed: [],
        total: 2,
      })

      expect(deficiency.deficiencyItems.value).toHaveLength(2)
      expect(deficiency.deficiencyItems.value[0].source.controlPoint).toBe('要点1')
      expect(deficiency.deficiencyItems.value[1].source.deficiencyType).toBe('未实施')
    })
    scope.stop()
  })

  it('syncFromFullList reconciles from B22A full snapshot { deficiencies }', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      // 首次全量快照：2 项
      deficiency.syncFromFullList([
        { tab: 1, subPanel: null, index: 1, controlPoint: '要点1', deficiencyType: '设计无效', elementName: '控制环境' },
        { tab: 2, subPanel: null, index: 1, controlPoint: '要点2', deficiencyType: '未实施', elementName: '风险评估' },
      ])
      expect(deficiency.deficiencyItems.value).toHaveLength(2)

      // 更新快照：要点2 消失（改为有效）、新增要点3 → 计算 added/removed
      deficiency.syncFromFullList([
        { tab: 1, subPanel: null, index: 1, controlPoint: '要点1', deficiencyType: '设计无效', elementName: '控制环境' },
        { tab: 5, subPanel: null, index: 1, controlPoint: '要点3', deficiencyType: '设计无效', elementName: '监督' },
      ])
      expect(deficiency.deficiencyItems.value).toHaveLength(2)
      const points = deficiency.deficiencyItems.value.map((i) => i.source.controlPoint)
      expect(points).toContain('要点1')
      expect(points).toContain('要点3')
      expect(points).not.toContain('要点2')
      expect(deficiency.eliminatedItems.value.some((i) => i.source.controlPoint === '要点2')).toBe(true)
    })
    scope.stop()
  })

  it('syncFromEvent removes items and moves to eliminatedItems', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      // First add items
      deficiency.syncFromEvent({
        added: [
          { tab: 1, subPanel: null, index: 1, controlPoint: '要点1', deficiencyType: '设计无效', elementName: '控制环境' },
        ],
        removed: [],
        total: 1,
      })
      expect(deficiency.deficiencyItems.value).toHaveLength(1)

      // Then remove
      deficiency.syncFromEvent({
        added: [],
        removed: [
          { tab: 1, subPanel: null, index: 1, controlPoint: '要点1', deficiencyType: '设计无效', elementName: '控制环境' },
        ],
        total: 0,
      })
      expect(deficiency.deficiencyItems.value).toHaveLength(0)
      expect(deficiency.eliminatedItems.value).toHaveLength(1)
      expect(deficiency.eliminatedItems.value[0].eliminated).toBe(true)
    })
    scope.stop()
  })

  it('source info is readonly (preserved from B22A)', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [{ tab: 3, subPanel: null, index: 5, controlPoint: '信息安全', deficiencyType: '设计无效', elementName: '信息系统' }],
        removed: [],
        total: 1,
      })

      const item = deficiency.deficiencyItems.value[0]
      expect(item.source.tab).toBe(3)
      expect(item.source.index).toBe(5)
      expect(item.source.controlPoint).toBe('信息安全')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.3 缺陷分类交互测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 缺陷分类交互 (6.3)', () => {
  it('defaultCategory auto-populates on sync', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [
          { tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' },
          { tab: 2, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '未实施', elementName: '风险评估' },
        ],
        removed: [],
        total: 2,
      })

      expect(deficiency.deficiencyItems.value[0].category).toBe('设计缺陷')
      expect(deficiency.deficiencyItems.value[1].category).toBe('运行缺陷')
    })
    scope.stop()
  })

  it('setCategory manually changes category', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const savedItems: ChecklistItem[] = []
      const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, saveFn)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setCategory(0, '运行缺陷')
      expect(deficiency.deficiencyItems.value[0].category).toBe('运行缺陷')
      expect(savedItems.some(i => i.conclusion === '运行缺陷')).toBe(true)
    })
    scope.stop()
  })

  it('defaultCategory is pure function: 设计无效→设计缺陷, 未实施→运行缺陷', () => {
    expect(defaultCategory('设计无效')).toBe('设计缺陷')
    expect(defaultCategory('未实施')).toBe('运行缺陷')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.4 多维度评价表单测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 多维度评价表单 (6.4)', () => {
  it('setAffectedAccounts saves accounts as comma-separated remark', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const savedItems: ChecklistItem[] = []
      const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, saveFn)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setAffectedAccounts(0, ['资产', '负债', '收入'])
      expect(deficiency.deficiencyItems.value[0].affectedAccounts).toEqual(['资产', '负债', '收入'])
      const accItem = savedItems.find(i => i.item_id.includes('-accounts'))
      expect(accItem?.remark).toBe('资产,负债,收入')
    })
    scope.stop()
  })

  it('setPotentialMisstatement saves amount as remark string', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const savedItems: ChecklistItem[] = []
      const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, saveFn)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setPotentialMisstatement(0, 500000)
      expect(deficiency.deficiencyItems.value[0].potentialMisstatement).toBe(500000)
      const amtItem = savedItems.find(i => i.item_id.includes('-amount'))
      expect(amtItem?.remark).toBe('500000')
    })
    scope.stop()
  })

  it('setCompensatingControl saves Y/N + description', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const savedItems: ChecklistItem[] = []
      const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, saveFn)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setCompensatingControl(0, true, '有补偿性控制措施')
      expect(deficiency.deficiencyItems.value[0].hasCompensatingControl).toBe(true)
      const compItem = savedItems.find(i => i.item_id.includes('-compensating'))
      expect(compItem?.conclusion).toBe('Y')
      expect(compItem?.remark).toBe('有补偿性控制措施')
    })
    scope.stop()
  })

  it('setCorrectiveAction saves Y/N + description', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const savedItems: ChecklistItem[] = []
      const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, saveFn)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setCorrectiveAction(0, false, '')
      expect(deficiency.deficiencyItems.value[0].hasCorrectiveAction).toBe(false)
      const corrItem = savedItems.find(i => i.item_id.includes('-corrective'))
      expect(corrItem?.conclusion).toBe('N')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.5 重要性水平对比测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 重要性水平对比 (6.5)', () => {
  it('amount > materiality → exceeds=true, color=red', () => {
    const result = compareMateriality(600000, 500000)
    expect(result.exceeds).toBe(true)
    expect(result.color).toBe('red')
    expect(result.difference).toBe(100000)
  })

  it('amount <= materiality → exceeds=false, color=green', () => {
    const result = compareMateriality(300000, 500000)
    expect(result.exceeds).toBe(false)
    expect(result.color).toBe('green')
    expect(result.difference).toBeNull()
  })

  it('materiality null → defaults to non-exceeds green', () => {
    const result = compareMateriality(100000, null)
    expect(result.exceeds).toBe(false)
    expect(result.color).toBe('green')
  })

  it('materiality <= 0 → defaults to non-exceeds green', () => {
    const result = compareMateriality(100000, 0)
    expect(result.exceeds).toBe(false)
    expect(result.color).toBe('green')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.6 严重程度评定测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 严重程度评定 (6.6)', () => {
  it('suggestSeverity: M>T no compensating/corrective → 重大缺陷', () => {
    expect(suggestSeverity(600000, 500000, false, false)).toBe('重大缺陷')
  })

  it('suggestSeverity: M>T with compensating → 重要缺陷', () => {
    expect(suggestSeverity(600000, 500000, true, false)).toBe('重要缺陷')
  })

  it('suggestSeverity: M>T with corrective → 重要缺陷', () => {
    expect(suggestSeverity(600000, 500000, false, true)).toBe('重要缺陷')
  })

  it('suggestSeverity: M<=T → 一般缺陷', () => {
    expect(suggestSeverity(400000, 500000, false, false)).toBe('一般缺陷')
  })

  it('suggestSeverity: null inputs → null', () => {
    expect(suggestSeverity(null, 500000, false, false)).toBeNull()
    expect(suggestSeverity(600000, null, false, false)).toBeNull()
  })

  it('setSeverity sets severity and clears override', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(500000)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setSeverity(0, '重大缺陷')
      expect(deficiency.deficiencyItems.value[0].severity).toBe('重大缺陷')
      expect(deficiency.deficiencyItems.value[0].severityOverridden).toBe(false)
    })
    scope.stop()
  })

  it('setSeverityOverride requires reason (empty reason rejected)', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(500000)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      // Set initial severity
      deficiency.setSeverity(0, '重大缺陷')

      // Attempt override with empty reason → no change
      deficiency.setSeverityOverride(0, '一般缺陷', '')
      expect(deficiency.deficiencyItems.value[0].severity).toBe('重大缺陷')
      expect(deficiency.deficiencyItems.value[0].severityOverridden).toBe(false)
    })
    scope.stop()
  })

  it('setSeverityOverride with reason sets "已手动调整" indicator', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(500000)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setSeverityOverride(0, '一般缺陷', '管理层已采取纠正措施')
      expect(deficiency.deficiencyItems.value[0].severity).toBe('一般缺陷')
      expect(deficiency.deficiencyItems.value[0].severityOverridden).toBe(true)
      expect(deficiency.deficiencyItems.value[0].overrideReason).toBe('管理层已采取纠正措施')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.7 保存行为测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 保存行为 (6.7)', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('saveDebouncedText triggers save after 2000ms', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { useB22BFormData } = await import('../composables/useB22BFormData')
      mockGet.mockResolvedValue([])
      mockPut.mockResolvedValue({})

      const formData = useB22BFormData(ref('wp-1'), ref('proj-1'))

      formData.saveDebouncedText({
        item_id: 'B22B-overall-note',
        conclusion: null,
        remark: '测试文本',
        wp_ref: null,
      })

      // Not saved yet
      expect(mockPut).not.toHaveBeenCalled()

      // Advance timer
      vi.advanceTimersByTime(2000)
      await nextTick()

      expect(mockPut).toHaveBeenCalled()
    })
    scope.stop()
  })

  it('saveImmediate saves without debounce', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const { useB22BFormData } = await import('../composables/useB22BFormData')
      mockGet.mockResolvedValue([])
      mockPut.mockResolvedValue({})

      const formData = useB22BFormData(ref('wp-1'), ref('proj-1'))

      await formData.saveImmediate([{
        item_id: 'B22B-def-1-category',
        conclusion: '设计缺陷',
        remark: null,
        wp_ref: null,
      }])

      expect(mockPut).toHaveBeenCalled()
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.8 整体结论汇总测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 整体结论汇总 (6.8)', () => {
  it('overallConclusion auto-computes from deficiency items', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(500000)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [
          { tab: 1, subPanel: null, index: 1, controlPoint: '要点1', deficiencyType: '设计无效', elementName: '控制环境' },
          { tab: 2, subPanel: null, index: 1, controlPoint: '要点2', deficiencyType: '未实施', elementName: '风险评估' },
        ],
        removed: [],
        total: 2,
      })

      // No severity set → 未发现控制缺陷
      expect(deficiency.overallConclusion.value).toBe('未发现控制缺陷')

      deficiency.setSeverity(0, '重要缺陷')
      expect(deficiency.overallConclusion.value).toBe('存在重要缺陷')

      deficiency.setSeverity(1, '重大缺陷')
      expect(deficiency.overallConclusion.value).toBe('存在重大缺陷')
    })
    scope.stop()
  })

  it('severityStats counts correctly', () => {
    const items: EvaluationItem[] = [
      makeEvaluationItem({ severity: '重大缺陷' }),
      makeEvaluationItem({ severity: '重大缺陷' }),
      makeEvaluationItem({ severity: '重要缺陷' }),
      makeEvaluationItem({ severity: '一般缺陷' }),
      makeEvaluationItem({ severity: '一般缺陷', eliminated: true }),
    ]
    const stats = computeSeverityStats(items)
    expect(stats.material).toBe(2)
    expect(stats.significant).toBe(1)
    expect(stats.general).toBe(1)
    expect(stats.total).toBe(4) // eliminated excluded
  })

  it('showAuditImpactWarning true when 重大 or 重要 exists', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(500000)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [{ tab: 1, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效', elementName: '控制环境' }],
        removed: [],
        total: 1,
      })

      deficiency.setSeverity(0, '一般缺陷')
      expect(deficiency.showAuditImpactWarning.value).toBe(false)

      deficiency.setSeverity(0, '重要缺陷')
      expect(deficiency.showAuditImpactWarning.value).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.9 只读模式测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 只读模式 (6.9)', () => {
  it('readonly=true → isReadonly=true', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const allEvaluated = computed(() => true)
      const deficiencyItems = ref<EvaluationItem[]>([])
      const externalReadonly = ref(true)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, noopSave,
      )

      expect(review.isReadonly.value).toBe(true)
    })
    scope.stop()
  })

  it('reviewed=true → isReadonly=true', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      allResponses.value.set('B22B-review-sign', {
        item_id: 'B22B-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01',
      })
      const allEvaluated = computed(() => true)
      const deficiencyItems = ref<EvaluationItem[]>([])
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, noopSave,
      )

      expect(review.isReviewed.value).toBe(true)
      expect(review.isReadonly.value).toBe(true)
    })
    scope.stop()
  })

  it('reviewInfo shows reviewer and date when reviewed', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      allResponses.value.set('B22B-review-sign', {
        item_id: 'B22B-review-sign', conclusion: 'Y', remark: '张经理', wp_ref: '2026-06-23',
      })
      const allEvaluated = computed(() => true)
      const deficiencyItems = ref<EvaluationItem[]>([])
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, noopSave,
      )

      expect(review.reviewInfo.value).toEqual({ reviewer: '张经理', date: '2026-06-23' })
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.10 复核签字测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — 复核签字 (6.10)', () => {
  it('canReview=false when not all severities evaluated', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const deficiencyItems = ref<EvaluationItem[]>([
        makeEvaluationItem({ severity: '重大缺陷' }),
        makeEvaluationItem({ severity: null }),
      ])
      const allEvaluated = computed(() =>
        deficiencyItems.value.filter(i => !i.eliminated).every(i => i.severity !== null)
      )
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, noopSave,
      )

      expect(review.canReview.value).toBe(false)
    })
    scope.stop()
  })

  it('canReview=true when all severities are set', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const deficiencyItems = ref<EvaluationItem[]>([
        makeEvaluationItem({ severity: '重大缺陷' }),
        makeEvaluationItem({ severity: '一般缺陷' }),
      ])
      const allEvaluated = computed(() =>
        deficiencyItems.value.filter(i => !i.eliminated).every(i => i.severity !== null)
      )
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, noopSave,
      )

      expect(review.canReview.value).toBe(true)
    })
    scope.stop()
  })

  it('doReview saves review sign and sets reviewed', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const deficiencyItems = ref<EvaluationItem[]>([
        makeEvaluationItem({ severity: '一般缺陷' }),
      ])
      const allEvaluated = computed(() => true)
      const savedItems: ChecklistItem[] = []
      const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, saveFn,
      )

      await review.doReview()

      expect(review.isReviewed.value).toBe(true)
      expect(savedItems.some(i => i.item_id === 'B22B-review-sign' && i.conclusion === 'Y')).toBe(true)
    })
    scope.stop()
  })

  it('pendingItems lists items without severity', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const deficiencyItems = ref<EvaluationItem[]>([
        makeEvaluationItem({ severity: '重大缺陷', source: { ...makeEvaluationItem().source, controlPoint: '已评价' } }),
        makeEvaluationItem({ severity: null, source: { ...makeEvaluationItem().source, controlPoint: '未评价' } }),
      ])
      const allEvaluated = computed(() => false)
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, noopSave,
      )

      expect(review.pendingItems.value).toHaveLength(1)
      expect(review.pendingItems.value[0]).toContain('未评价')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.11 Amendment 流程测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — Amendment 流程 (6.11)', () => {
  it('startAmendment resets review sign and saves reason', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      allResponses.value.set('B22B-review-sign', {
        item_id: 'B22B-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01',
      })
      const deficiencyItems = ref<EvaluationItem[]>([])
      const allEvaluated = computed(() => true)
      const savedItems: ChecklistItem[] = []
      const saveFn = async (items: ChecklistItem[]) => { savedItems.push(...items) }
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, saveFn,
      )

      expect(review.isReviewed.value).toBe(true)

      await review.startAmendment('发现新缺陷需补充评价')

      // Review sign should be reset
      expect(review.isReviewed.value).toBe(false)
      // Reason should be saved
      expect(savedItems.some(i => i.item_id.includes('amend') && i.remark === '发现新缺陷需补充评价')).toBe(true)
      // Reset review sign saved
      expect(savedItems.some(i => i.item_id === 'B22B-review-sign' && i.conclusion === null)).toBe(true)
    })
    scope.stop()
  })

  it('startAmendment rejects empty reason', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      allResponses.value.set('B22B-review-sign', {
        item_id: 'B22B-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01',
      })
      const deficiencyItems = ref<EvaluationItem[]>([])
      const allEvaluated = computed(() => true)
      const externalReadonly = ref(false)

      const review = useB22BReview(
        ref('wp-1'), allResponses, allEvaluated,
        deficiencyItems, externalReadonly, noopSave,
      )

      await expect(review.startAmendment('')).rejects.toThrow('修改原因不能为空')
      await expect(review.startAmendment('   ')).rejects.toThrow('修改原因不能为空')

      // Review sign unchanged
      expect(review.isReviewed.value).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.12 EventBus 联动测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22B 内部控制缺陷评价表 — EventBus 联动 (6.12)', () => {
  beforeEach(() => { mockEmit.mockClear() })

  it('syncFromEvent processes control:deficiency-changed payload', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      // Simulate receiving the event payload
      deficiency.syncFromEvent({
        added: [
          { tab: 1, subPanel: null, index: 1, controlPoint: '要点A', deficiencyType: '设计无效', elementName: '控制环境' },
        ],
        removed: [],
        total: 1,
      })

      expect(deficiency.deficiencyItems.value).toHaveLength(1)
      expect(deficiency.deficiencyItems.value[0].source.controlPoint).toBe('要点A')
    })
    scope.stop()
  })

  it('publishSeverityEvent emits deficiency:severity-evaluated with correct payload', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(500000)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      deficiency.syncFromEvent({
        added: [
          { tab: 1, subPanel: null, index: 1, controlPoint: '要点1', deficiencyType: '设计无效', elementName: '控制环境' },
          { tab: 2, subPanel: null, index: 1, controlPoint: '要点2', deficiencyType: '未实施', elementName: '风险评估' },
        ],
        removed: [],
        total: 2,
      })

      deficiency.setSeverity(0, '重大缺陷')
      deficiency.setSeverity(1, '重要缺陷')

      // Verify EventBus was called
      expect(mockEmit).toHaveBeenCalled()
      const lastCall = mockEmit.mock.calls[mockEmit.mock.calls.length - 1]
      expect(lastCall[0]).toBe('deficiency:severity-evaluated')

      const payload = lastCall[1]
      expect(payload.overallConclusion).toBe('存在重大缺陷')
      expect(payload.materialCount).toBe(1)
      expect(payload.significantCount).toBe(1)
      expect(payload.impactsAuditOpinion).toBe(true)
      expect(payload.requiresExtendedProcedures).toBe(true)
    })
    scope.stop()
  })

  it('no duplicates when same item added twice', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, ChecklistResponse>())
      const materialityLevel = ref<number | null>(null)
      const deficiency = useB22BDeficiency(allResponses, materialityLevel, noopSave)

      const item = { tab: 1 as const, subPanel: null, index: 1, controlPoint: '要点', deficiencyType: '设计无效' as const, elementName: '控制环境' }

      deficiency.syncFromEvent({ added: [item], removed: [], total: 1 })
      deficiency.syncFromEvent({ added: [item], removed: [], total: 1 })

      expect(deficiency.deficiencyItems.value).toHaveLength(1)
    })
    scope.stop()
  })
})
