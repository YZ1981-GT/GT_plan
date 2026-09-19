/**
 * B22C 设计有效性评价 + B22A FRP / 管理层凌驾 — Unit Tests (Tasks 10.2 + 11.2, Wave 4)
 *
 * 覆盖正确性属性：
 *  P4  缺陷严重程度单一真源  —— setDeficiencyField('severity') 权威，isSignificant 派生（重大/重要→true，一般→false）
 *  P7  迁移幂等（10.2）      —— loadFromUpstream 执行两次不翻倍/不漂移；无法匹配 severity 的缺陷保留（severity=null）
 *  P8  FRP 不适用可空        —— setFrpNa(key,true) → 了解文本可空且不计入 gap；na=false + note 空 → 计入 gap（useB22AControlMatrix）
 *  P13 管理层凌驾归属        —— mo 子区（-IT-mo-）设计无效缺陷归「风险评估过程 - 管理层凌驾于控制之上」，不误判为 ITGC（useB22AControlMatrix）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'

// ─── Mock apiProxy ─────────────────────────────────────────────────────────
const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// ─── Mock element-plus ─────────────────────────────────────────────────────
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

import {
  useB22CDesignEffectiveness,
  severityIsSignificant,
  normalizeSeverity,
  SEVERITY_VALUES,
  type ChecklistResponse,
} from '../composables/useB22CDesignEffectiveness'
import { useB22AControlMatrix, FRP_SUBPROCESSES } from '../composables/useB22AControlMatrix'

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockGet.mockResolvedValue([])
  mockPut.mockResolvedValue({})
})

// ═══════════════════════════════════════════════════════════════════════════
// P4 — 缺陷严重程度单一真源（severity 权威 → isSignificant 派生）
// ═══════════════════════════════════════════════════════════════════════════

describe('B22C — P4 severity 单一真源', () => {
  it('纯函数：severityIsSignificant / normalizeSeverity / SEVERITY_VALUES', () => {
    expect(severityIsSignificant('重大缺陷')).toBe(true)
    expect(severityIsSignificant('重要缺陷')).toBe(true)
    expect(severityIsSignificant('一般缺陷')).toBe(false)
    expect(severityIsSignificant(null)).toBe(false)

    expect(normalizeSeverity('重大缺陷')).toBe('重大缺陷')
    expect(normalizeSeverity('乱码')).toBeNull()
    expect(normalizeSeverity(undefined)).toBeNull()

    expect(SEVERITY_VALUES).toEqual(['重大缺陷', '重要缺陷', '一般缺陷'])
  })

  it('setDeficiencyField(severity) 权威设定，isSignificant 由 severity 派生（口径不分裂）', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-c'), ref('proj-1'))
      c.addDeficiency('env')

      c.setDeficiencyField('env', 0, 'severity', '重大缺陷')
      let d = c.blockState.value.env.deficiencies[0]
      expect(d.severity).toBe('重大缺陷')
      expect(d.isSignificant).toBe(true)

      c.setDeficiencyField('env', 0, 'severity', '重要缺陷')
      d = c.blockState.value.env.deficiencies[0]
      expect(d.severity).toBe('重要缺陷')
      expect(d.isSignificant).toBe(true)

      c.setDeficiencyField('env', 0, 'severity', '一般缺陷')
      d = c.blockState.value.env.deficiencies[0]
      expect(d.severity).toBe('一般缺陷')
      expect(d.isSignificant).toBe(false)
    })
    scope.stop()
  })

  it('非法 severity 归一化为 null，isSignificant=false', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-c'), ref('proj-1'))
      c.addDeficiency('risk')
      c.setDeficiencyField('risk', 0, 'severity', '不存在的等级')
      const d = c.blockState.value.risk.deficiencies[0]
      expect(d.severity).toBeNull()
      expect(d.isSignificant).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// P7 — 迁移幂等（10.2）：loadFromUpstream 两次不翻倍/不漂移 + 保留无匹配 severity
// ═══════════════════════════════════════════════════════════════════════════

describe('B22C — P7 迁移幂等（10.2）', () => {
  const b22aResponses: ChecklistResponse[] = [
    // 控制环境设计无效缺陷（有 B22B 严重程度）
    { item_id: 'B22A-T1-item-1-conclusion', conclusion: '设计无效', remark: null, wp_ref: null },
    { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '控制环境要点A', wp_ref: null },
    // 管理层凌驾（-IT-mo-）设计无效缺陷（无 B22B 严重程度 → severity=null，仍保留）
    { item_id: 'B22A-T2-IT-mo-1-conclusion', conclusion: '设计无效', remark: null, wp_ref: null },
    { item_id: 'B22A-T2-IT-mo-1-point', conclusion: null, remark: '管理层凌驾要点', wp_ref: null },
  ]

  const b22bResponses: ChecklistResponse[] = [
    { item_id: 'B22B-def-count', conclusion: null, remark: '1', wp_ref: null },
    {
      item_id: 'B22B-def-1-source',
      conclusion: null,
      remark: JSON.stringify({ tab: 1, subPanel: null, index: 1 }),
      wp_ref: null,
    },
    { item_id: 'B22B-def-1-severity', conclusion: '重大缺陷', remark: null, wp_ref: null },
  ]

  it('两次 loadFromUpstream：缺陷行数与内容不翻倍/不漂移', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-c'), ref('proj-1'))

      const r1 = c.loadFromUpstream(b22aResponses, b22bResponses)
      expect(r1.added).toBe(2)
      expect(c.blockState.value.env.deficiencies).toHaveLength(1)
      expect(c.blockState.value.risk.deficiencies).toHaveLength(1)

      // 第二次执行：全部已存在（按 desc 去重）→ added=0，行数不变
      const r2 = c.loadFromUpstream(b22aResponses, b22bResponses)
      expect(r2.added).toBe(0)
      expect(c.blockState.value.env.deficiencies).toHaveLength(1)
      expect(c.blockState.value.risk.deficiencies).toHaveLength(1)

      // 内容不漂移
      expect(c.blockState.value.env.deficiencies[0].desc).toBe('控制环境要点A')
      expect(c.blockState.value.risk.deficiencies[0].desc).toBe('管理层凌驾要点')
    })
    scope.stop()
  })

  it('B22B 匹配的缺陷带入 severity（重大 → isSignificant=true）', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-c'), ref('proj-1'))
      c.loadFromUpstream(b22aResponses, b22bResponses)
      const env = c.blockState.value.env.deficiencies[0]
      expect(env.severity).toBe('重大缺陷')
      expect(env.isSignificant).toBe(true)
    })
    scope.stop()
  })

  it('无法匹配 severity 的缺陷保留（severity=null，不丢弃）', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-c'), ref('proj-1'))
      c.loadFromUpstream(b22aResponses, b22bResponses)
      const mo = c.blockState.value.risk.deficiencies[0]
      expect(mo.desc).toBe('管理层凌驾要点')
      expect(mo.severity).toBeNull()
      expect(mo.isSignificant).toBe(false)
    })
    scope.stop()
  })

  it('管理层凌驾归风险评估区（risk），不误判为 ITGC', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-c'), ref('proj-1'))
      c.loadFromUpstream(b22aResponses, b22bResponses)
      // 风险评估区含管理层凌驾缺陷
      expect(c.blockState.value.risk.deficiencies.some((d) => d.desc === '管理层凌驾要点')).toBe(true)
      // ITGC 区不含
      expect(c.blockState.value.itgc.deficiencies).toHaveLength(0)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// P8 — FRP 不适用可空（useB22AControlMatrix）
// ═══════════════════════════════════════════════════════════════════════════

describe('B22A — P8 FRP 不适用可空', () => {
  it('setFrpNa(true) 后了解文本可空且不计入 gap；na=false + note 空 → 计入 gap', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const m = useB22AControlMatrix(allResponses, saveFn)

      const total = FRP_SUBPROCESSES.length
      // 初始：全部子过程 na=false + note 空 → 全部计入 gap
      expect(m.frpApplicableGapCount.value).toBe(total)

      // 标记 closing 不适用 → 了解文本可空，不计入 gap
      m.setFrpNa('closing', true)
      expect(m.getFrp('closing').na).toBe(true)
      expect(m.getFrp('closing').note).toBe('') // 不适用时文本可空
      expect(m.frpApplicableGapCount.value).toBe(total - 1)

      // 取消不适用（na=false）且 note 仍空 → 重新计入 gap
      m.setFrpNa('closing', false)
      expect(m.getFrp('closing').na).toBe(false)
      expect(m.frpApplicableGapCount.value).toBe(total)

      // 填写了解文本 → 不再计入 gap
      m.setFrpNote('closing', '已了解期末结账过程')
      expect(m.getFrp('closing').note).toBe('已了解期末结账过程')
      expect(m.frpApplicableGapCount.value).toBe(total - 1)
    })
    scope.stop()
  })

  it('setFrpNa 通过 saveFn 持久化 conclusion Y/N', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const m = useB22AControlMatrix(allResponses, saveFn)

      m.setFrpNa('consolidation', true)
      expect(saveFn).toHaveBeenCalled()
      const stored = allResponses.value.get('B22A-frp-consolidation-na')
      expect(stored?.conclusion).toBe('Y')

      m.setFrpNa('consolidation', false)
      expect(allResponses.value.get('B22A-frp-consolidation-na')?.conclusion).toBe('N')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// P13 — 管理层凌驾归属（useB22AControlMatrix.deficiencyList）
// ═══════════════════════════════════════════════════════════════════════════

describe('B22A — P13 管理层凌驾归属', () => {
  it('mo 子区（-IT-mo-）设计无效缺陷归风险评估区，不误判为 ITGC', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T2-IT-mo-count', {
        item_id: 'B22A-T2-IT-mo-count', conclusion: null, remark: '1', wp_ref: null,
      })
      allResponses.value.set('B22A-T2-IT-mo-1-point', {
        item_id: 'B22A-T2-IT-mo-1-point', conclusion: null, remark: '管理层凌驾控制点', wp_ref: null,
      })
      allResponses.value.set('B22A-T2-IT-mo-1-conclusion', {
        item_id: 'B22A-T2-IT-mo-1-conclusion', conclusion: '设计无效', remark: null, wp_ref: null,
      })

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const m = useB22AControlMatrix(allResponses, saveFn)

      const list = m.deficiencyList.value
      const mo = list.find((d) => d.subPanel === 'mo')
      expect(mo).toBeDefined()
      expect(mo!.elementName).toBe('风险评估过程 - 管理层凌驾于控制之上')
      expect(mo!.deficiencyType).toBe('设计无效')
      expect(mo!.controlPoint).toBe('管理层凌驾控制点')

      // 不被误判为 ITGC
      expect(list.some((d) => d.subPanel === 'itgc')).toBe(false)
      expect(list.every((d) => !d.elementName.includes('ITGC'))).toBe(true)
    })
    scope.stop()
  })

  it('管理层凌驾未标记缺陷时不出现在 deficiencyList', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T2-IT-mo-count', {
        item_id: 'B22A-T2-IT-mo-count', conclusion: null, remark: '1', wp_ref: null,
      })
      allResponses.value.set('B22A-T2-IT-mo-1-point', {
        item_id: 'B22A-T2-IT-mo-1-point', conclusion: null, remark: '管理层凌驾控制点', wp_ref: null,
      })
      allResponses.value.set('B22A-T2-IT-mo-1-conclusion', {
        item_id: 'B22A-T2-IT-mo-1-conclusion', conclusion: '设计有效', remark: null, wp_ref: null,
      })

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const m = useB22AControlMatrix(allResponses, saveFn)
      expect(m.deficiencyList.value.some((d) => d.subPanel === 'mo')).toBe(false)
    })
    scope.stop()
  })
})
