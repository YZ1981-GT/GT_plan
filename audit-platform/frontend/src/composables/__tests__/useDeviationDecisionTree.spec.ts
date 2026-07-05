import { describe, it, expect } from 'vitest'
import {
  evaluateDecisionTree,
  getStepOptions,
  getStepQuestion,
  isStepVisible,
  createEmptyState,
  type DecisionTreeState,
  type DecisionTreeResult,
} from '../useDeviationDecisionTree'

// ─── evaluateDecisionTree 六路径完整覆盖 ────────────────────

describe('evaluateDecisionTree', () => {
  describe('Path A: Step1=否 → Step6=否 → 不构成偏差或缺陷，控制有效', () => {
    it('正确推导结论与路径', () => {
      const state: DecisionTreeState = {
        step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '否',
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBe('不构成偏差或缺陷，控制有效')
      expect(r.goToA14).toBe(false)
      expect(r.path).toBe('A')
      expect(r.currentStep).toBe(6)
    })
  })

  describe('Path B: Step1=否 → Step6=是 → 存在设计缺陷 → Step5', () => {
    it('正确推导结论与路径', () => {
      const state: DecisionTreeState = {
        step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '是',
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBe('存在设计缺陷，进入内控缺陷评价')
      expect(r.goToA14).toBe(true)
      expect(r.path).toBe('B')
      expect(r.currentStep).toBe(5)
    })
  })

  describe('Path C: Step1=是 → Step2=系统性/人为 → 控制缺陷 → Step5', () => {
    it('系统性偏差 → 控制缺陷', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: '系统性偏差', step3: null, step4: null, step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBe('属于控制缺陷，进入内控缺陷评价')
      expect(r.goToA14).toBe(true)
      expect(r.path).toBe('C')
      expect(r.currentStep).toBe(5)
    })

    it('人为偏差 → 控制缺陷', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: '人为偏差', step3: null, step4: null, step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBe('属于控制缺陷，进入内控缺陷评价')
      expect(r.goToA14).toBe(true)
      expect(r.path).toBe('C')
    })
  })

  describe('Path D: Step1=是 → Step2=随机 → Step3=直接认定 → Step5', () => {
    it('正确推导结论与路径', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: '随机性偏差', step3: '直接认定为偏差', step4: null, step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBe('直接认定为偏差，进入内控缺陷评价')
      expect(r.goToA14).toBe(true)
      expect(r.path).toBe('D')
      expect(r.currentStep).toBe(5)
    })
  })

  describe('Path E: Step1=是 → Step2=随机 → Step3=扩大 → Step4=否 → 控制有效', () => {
    it('正确推导结论与路径', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '否', step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBe('控制有效')
      expect(r.goToA14).toBe(false)
      expect(r.path).toBe('E')
      expect(r.currentStep).toBe(4)
    })
  })

  describe('Path F: Step1=是 → Step2=随机 → Step3=扩大 → Step4=是 → 控制无效 → Step5', () => {
    it('正确推导结论与路径', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '是', step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBe('控制无效，进入内控缺陷评价')
      expect(r.goToA14).toBe(true)
      expect(r.path).toBe('F')
      expect(r.currentStep).toBe(5)
    })
  })

  describe('未完成状态返回 null 结论', () => {
    it('空状态 → step1 待选', () => {
      const state = createEmptyState()
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBeNull()
      expect(r.currentStep).toBe(1)
      expect(r.path).toBeNull()
      expect(r.goToA14).toBe(false)
    })

    it('step1=否 step6=null → 等待步骤六', () => {
      const state: DecisionTreeState = {
        step1: '否', step2: null, step3: null, step4: null, step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBeNull()
      expect(r.currentStep).toBe(6)
      expect(r.path).toBeNull()
    })

    it('step1=是 step2=null → 等待步骤二', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: null, step3: null, step4: null, step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBeNull()
      expect(r.currentStep).toBe(2)
      expect(r.path).toBeNull()
    })

    it('step1=是 step2=随机 step3=null → 等待步骤三', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: '随机性偏差', step3: null, step4: null, step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBeNull()
      expect(r.currentStep).toBe(3)
      expect(r.path).toBeNull()
    })

    it('step1=是 step2=随机 step3=扩大 step4=null → 等待步骤四', () => {
      const state: DecisionTreeState = {
        step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: null, step5: false, step6: null,
      }
      const r = evaluateDecisionTree(state)
      expect(r.conclusion).toBeNull()
      expect(r.currentStep).toBe(4)
      expect(r.path).toBeNull()
    })
  })

  describe('goToA14 标志正确性', () => {
    it('Path A/E goToA14=false', () => {
      // Path A
      const a = evaluateDecisionTree({ step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '否' })
      expect(a.goToA14).toBe(false)
      // Path E
      const e = evaluateDecisionTree({ step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '否', step5: false, step6: null })
      expect(e.goToA14).toBe(false)
    })

    it('Path B/C/D/F goToA14=true', () => {
      // Path B
      const b = evaluateDecisionTree({ step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '是' })
      expect(b.goToA14).toBe(true)
      // Path C
      const c = evaluateDecisionTree({ step1: '是', step2: '系统性偏差', step3: null, step4: null, step5: false, step6: null })
      expect(c.goToA14).toBe(true)
      // Path D
      const d = evaluateDecisionTree({ step1: '是', step2: '随机性偏差', step3: '直接认定为偏差', step4: null, step5: false, step6: null })
      expect(d.goToA14).toBe(true)
      // Path F
      const f = evaluateDecisionTree({ step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '是', step5: false, step6: null })
      expect(f.goToA14).toBe(true)
    })
  })
})

// ─── isStepVisible 可见性 ────────────────────────────────────

describe('isStepVisible', () => {
  it('Step1 始终可见', () => {
    expect(isStepVisible(createEmptyState(), 1)).toBe(true)
  })

  it('Step2 仅 step1=是 时可见', () => {
    expect(isStepVisible({ ...createEmptyState(), step1: '是' }, 2)).toBe(true)
    expect(isStepVisible({ ...createEmptyState(), step1: '否' }, 2)).toBe(false)
    expect(isStepVisible(createEmptyState(), 2)).toBe(false)
  })

  it('Step3 仅 step2=随机性偏差 时可见', () => {
    const visible: DecisionTreeState = { step1: '是', step2: '随机性偏差', step3: null, step4: null, step5: false, step6: null }
    expect(isStepVisible(visible, 3)).toBe(true)

    const notVisible: DecisionTreeState = { step1: '是', step2: '系统性偏差', step3: null, step4: null, step5: false, step6: null }
    expect(isStepVisible(notVisible, 3)).toBe(false)
  })

  it('Step4 仅 step3=扩大样本量 时可见', () => {
    const visible: DecisionTreeState = { step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: null, step5: false, step6: null }
    expect(isStepVisible(visible, 4)).toBe(true)

    const notVisible: DecisionTreeState = { step1: '是', step2: '随机性偏差', step3: '直接认定为偏差', step4: null, step5: false, step6: null }
    expect(isStepVisible(notVisible, 4)).toBe(false)
  })

  it('Step5 仅 goToA14=true 时可见', () => {
    // Path C → goToA14=true
    const pathC: DecisionTreeState = { step1: '是', step2: '系统性偏差', step3: null, step4: null, step5: false, step6: null }
    expect(isStepVisible(pathC, 5)).toBe(true)

    // Path E → goToA14=false
    const pathE: DecisionTreeState = { step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '否', step5: false, step6: null }
    expect(isStepVisible(pathE, 5)).toBe(false)

    // Path A → goToA14=false
    const pathA: DecisionTreeState = { step1: '否', step2: null, step3: null, step4: null, step5: false, step6: '否' }
    expect(isStepVisible(pathA, 5)).toBe(false)
  })

  it('Step6 仅 step1=否 时可见', () => {
    expect(isStepVisible({ ...createEmptyState(), step1: '否' }, 6)).toBe(true)
    expect(isStepVisible({ ...createEmptyState(), step1: '是' }, 6)).toBe(false)
    expect(isStepVisible(createEmptyState(), 6)).toBe(false)
  })

  it('无效步骤号返回 false', () => {
    expect(isStepVisible(createEmptyState(), 0)).toBe(false)
    expect(isStepVisible(createEmptyState(), 7)).toBe(false)
    expect(isStepVisible(createEmptyState(), -1)).toBe(false)
  })
})

// ─── getStepOptions ──────────────────────────────────────────

describe('getStepOptions', () => {
  it('Step1 返回 是/否 两选项', () => {
    const opts = getStepOptions(1)
    expect(opts).toHaveLength(2)
    expect(opts.map(o => o.value)).toEqual(['是', '否'])
  })

  it('Step2 返回三种偏差性质', () => {
    const opts = getStepOptions(2)
    expect(opts).toHaveLength(3)
    expect(opts.map(o => o.value)).toEqual(['系统性偏差', '人为偏差', '随机性偏差'])
  })

  it('Step3 返回两种应对措施', () => {
    const opts = getStepOptions(3)
    expect(opts).toHaveLength(2)
    expect(opts.map(o => o.value)).toEqual(['扩大样本量', '直接认定为偏差'])
  })

  it('Step4 返回 是/否 两选项', () => {
    const opts = getStepOptions(4)
    expect(opts).toHaveLength(2)
    expect(opts.map(o => o.value)).toEqual(['是', '否'])
  })

  it('Step5 无选项（自动推导）', () => {
    const opts = getStepOptions(5)
    expect(opts).toHaveLength(0)
  })

  it('Step6 返回 是/否 两选项', () => {
    const opts = getStepOptions(6)
    expect(opts).toHaveLength(2)
    expect(opts.map(o => o.value)).toEqual(['是', '否'])
  })

  it('无效步骤号返回空数组', () => {
    expect(getStepOptions(0)).toEqual([])
    expect(getStepOptions(7)).toEqual([])
  })
})

// ─── getStepQuestion ─────────────────────────────────────────

describe('getStepQuestion', () => {
  it('Step1~6 均返回非空字符串', () => {
    for (let i = 1; i <= 6; i++) {
      const q = getStepQuestion(i)
      expect(q).toBeTruthy()
      expect(typeof q).toBe('string')
    }
  })

  it('Step1 包含"控制偏差"', () => {
    expect(getStepQuestion(1)).toContain('控制偏差')
  })

  it('Step5 包含"A14"', () => {
    expect(getStepQuestion(5)).toContain('A14')
  })

  it('无效步骤号返回空字符串', () => {
    expect(getStepQuestion(0)).toBe('')
    expect(getStepQuestion(7)).toBe('')
  })
})

// ─── createEmptyState ────────────────────────────────────────

describe('createEmptyState', () => {
  it('所有选择步骤为 null，step5 为 false', () => {
    const s = createEmptyState()
    expect(s.step1).toBeNull()
    expect(s.step2).toBeNull()
    expect(s.step3).toBeNull()
    expect(s.step4).toBeNull()
    expect(s.step5).toBe(false)
    expect(s.step6).toBeNull()
  })
})
