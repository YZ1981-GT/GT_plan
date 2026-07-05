/**
 * useDeviationDecisionTree — Cx-2 六步偏差评价决策树纯函数
 *
 * 纯函数，无副作用、无 API 调用、确定性输出。
 * 复刻致同 2025 修订版模板 Cx-2 偏差评价的 6 步 IF 公式链：
 *
 * Step 1: 控制例外情况是否属于控制偏差？ (是/否)
 *   否 → 进入步骤六
 *   是 → 进入步骤二
 * Step 2: 确定偏差性质 (系统性偏差/人为偏差/随机性偏差)
 *   系统性/人为 → 属于控制缺陷，进入步骤五
 *   随机性 → 进入步骤三
 * Step 3: 随机性偏差应对措施 (扩大样本量/直接认定为偏差)
 *   直接认定 → 进入步骤五
 *   扩大样本量 → 进入步骤四
 * Step 4: 扩大样本量后是否发现新偏差 (是/否)
 *   否 → 控制有效
 *   是 → 控制无效，进入步骤五
 * Step 5: 评价控制缺陷 → 进入A14内控缺陷评价底稿
 * Step 6: 非偏差例外是否表明设计缺陷 (是/否)
 *   否 → 不构成偏差或缺陷
 *   是 → 存在设计缺陷，回到步骤五
 */

// ─── 类型定义 ───────────────────────────────────────────────

/** 决策树状态：各步骤当前选择 */
export interface DecisionTreeState {
  /** 步骤一：控制例外是否属于控制偏差 */
  step1: '是' | '否' | null
  /** 步骤二：偏差性质 */
  step2: '系统性偏差' | '人为偏差' | '随机性偏差' | null
  /** 步骤三：随机性偏差应对措施 */
  step3: '扩大样本量' | '直接认定为偏差' | null
  /** 步骤四：扩大样本量后是否发现新偏差 */
  step4: '是' | '否' | null
  /** 步骤五：是否进入A14（自动推导，不可选） */
  step5: boolean
  /** 步骤六：非偏差例外是否表明设计缺陷 */
  step6: '是' | '否' | null
}

/** 决策树推导结果 */
export interface DecisionTreeResult {
  /** 当前应展示到哪一步 (1-6) */
  currentStep: number
  /** 下一步指引文本 */
  nextStepHint: string
  /** 最终评价结论 (null if incomplete) */
  conclusion: string | null
  /** 是否需要跳转A14 */
  goToA14: boolean
  /** 匹配的决策路径 */
  path: 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | null
}

/** 步骤选项 */
export interface StepOption {
  value: string
  label: string
}

// ─── 常量 ───────────────────────────────────────────────────

/** 步骤问题文本 */
const STEP_QUESTIONS: Record<number, string> = {
  1: '控制例外情况是否属于控制偏差？',
  2: '确定偏差性质',
  3: '随机性偏差应对措施',
  4: '扩大样本量后是否发现新偏差？',
  5: '评价控制缺陷（进入A14内控缺陷评价底稿）',
  6: '非偏差例外是否表明设计缺陷？',
}

/** 步骤选项映射 */
const STEP_OPTIONS: Record<number, StepOption[]> = {
  1: [
    { value: '是', label: '是（属于控制偏差）' },
    { value: '否', label: '否（不属于控制偏差）' },
  ],
  2: [
    { value: '系统性偏差', label: '系统性偏差' },
    { value: '人为偏差', label: '人为偏差' },
    { value: '随机性偏差', label: '随机性偏差' },
  ],
  3: [
    { value: '扩大样本量', label: '扩大样本量' },
    { value: '直接认定为偏差', label: '直接认定为偏差' },
  ],
  4: [
    { value: '是', label: '是（发现新偏差）' },
    { value: '否', label: '否（未发现新偏差）' },
  ],
  5: [], // 步骤五无选项，自动推导
  6: [
    { value: '是', label: '是（存在设计缺陷）' },
    { value: '否', label: '否（不构成偏差或缺陷）' },
  ],
}

// ─── 核心纯函数 ─────────────────────────────────────────────

/**
 * 评估决策树状态，推导当前步骤、结论、路径
 *
 * 决策路径：
 * | Path | Input Combination | Final Conclusion | goToA14 |
 * |------|---------|---------|:---:|
 * | A | Step1=否 → Step6=否 | 不构成偏差或缺陷，控制有效 | ✗ |
 * | B | Step1=否 → Step6=是 | 存在设计缺陷 → Step5 | ✓ |
 * | C | Step1=是 → Step2=系统性/人为 | 属于控制缺陷 → Step5 | ✓ |
 * | D | Step1=是 → Step2=随机 → Step3=直接认定 | Step5 | ✓ |
 * | E | Step1=是 → Step2=随机 → Step3=扩大 → Step4=否 | 控制有效 | ✗ |
 * | F | Step1=是 → Step2=随机 → Step3=扩大 → Step4=是 | 控制无效 → Step5 | ✓ |
 */
export function evaluateDecisionTree(state: DecisionTreeState): DecisionTreeResult {
  // 步骤一未填
  if (state.step1 === null) {
    return {
      currentStep: 1,
      nextStepHint: '请判断控制例外情况是否属于控制偏差',
      conclusion: null,
      goToA14: false,
      path: null,
    }
  }

  // 步骤一 = 否 → 跳到步骤六
  if (state.step1 === '否') {
    if (state.step6 === null) {
      return {
        currentStep: 6,
        nextStepHint: '请判断非偏差例外是否表明设计缺陷',
        conclusion: null,
        goToA14: false,
        path: null,
      }
    }

    // 步骤六 = 否 → Path A：不构成偏差或缺陷，控制有效
    if (state.step6 === '否') {
      return {
        currentStep: 6,
        nextStepHint: '评价完成：不构成偏差或缺陷',
        conclusion: '不构成偏差或缺陷，控制有效',
        goToA14: false,
        path: 'A',
      }
    }

    // 步骤六 = 是 → Path B：存在设计缺陷，进入步骤五
    return {
      currentStep: 5,
      nextStepHint: '存在设计缺陷，请进入A14内控缺陷评价底稿',
      conclusion: '存在设计缺陷，进入内控缺陷评价',
      goToA14: true,
      path: 'B',
    }
  }

  // 步骤一 = 是 → 进入步骤二
  if (state.step2 === null) {
    return {
      currentStep: 2,
      nextStepHint: '请确定偏差性质',
      conclusion: null,
      goToA14: false,
      path: null,
    }
  }

  // 步骤二 = 系统性偏差 / 人为偏差 → Path C：属于控制缺陷，进入步骤五
  if (state.step2 === '系统性偏差' || state.step2 === '人为偏差') {
    return {
      currentStep: 5,
      nextStepHint: '属于控制缺陷，请进入A14内控缺陷评价底稿',
      conclusion: '属于控制缺陷，进入内控缺陷评价',
      goToA14: true,
      path: 'C',
    }
  }

  // 步骤二 = 随机性偏差 → 进入步骤三
  if (state.step3 === null) {
    return {
      currentStep: 3,
      nextStepHint: '请选择随机性偏差的应对措施',
      conclusion: null,
      goToA14: false,
      path: null,
    }
  }

  // 步骤三 = 直接认定为偏差 → Path D：进入步骤五
  if (state.step3 === '直接认定为偏差') {
    return {
      currentStep: 5,
      nextStepHint: '直接认定为偏差，请进入A14内控缺陷评价底稿',
      conclusion: '直接认定为偏差，进入内控缺陷评价',
      goToA14: true,
      path: 'D',
    }
  }

  // 步骤三 = 扩大样本量 → 进入步骤四
  if (state.step4 === null) {
    return {
      currentStep: 4,
      nextStepHint: '请判断扩大样本量后是否发现新偏差',
      conclusion: null,
      goToA14: false,
      path: null,
    }
  }

  // 步骤四 = 否 → Path E：控制有效
  if (state.step4 === '否') {
    return {
      currentStep: 4,
      nextStepHint: '评价完成：控制有效',
      conclusion: '控制有效',
      goToA14: false,
      path: 'E',
    }
  }

  // 步骤四 = 是 → Path F：控制无效，进入步骤五
  return {
    currentStep: 5,
    nextStepHint: '控制无效，请进入A14内控缺陷评价底稿',
    conclusion: '控制无效，进入内控缺陷评价',
    goToA14: true,
    path: 'F',
  }
}

// ─── 辅助纯函数 ─────────────────────────────────────────────

/**
 * 获取指定步骤的选项列表
 */
export function getStepOptions(stepNumber: number): StepOption[] {
  return STEP_OPTIONS[stepNumber] ?? []
}

/**
 * 获取指定步骤的问题文本
 */
export function getStepQuestion(stepNumber: number): string {
  return STEP_QUESTIONS[stepNumber] ?? ''
}

/**
 * 判断某步骤是否应该可见（基于前序步骤的选择）
 *
 * 可见性规则：
 * - Step 1: 始终可见
 * - Step 2: step1 = '是' 时可见
 * - Step 3: step2 = '随机性偏差' 时可见
 * - Step 4: step3 = '扩大样本量' 时可见
 * - Step 5: 自动推导进入时可见（goToA14 = true）
 * - Step 6: step1 = '否' 时可见
 */
export function isStepVisible(state: DecisionTreeState, stepNumber: number): boolean {
  switch (stepNumber) {
    case 1:
      return true
    case 2:
      return state.step1 === '是'
    case 3:
      return state.step1 === '是' && state.step2 === '随机性偏差'
    case 4:
      return state.step1 === '是' && state.step2 === '随机性偏差' && state.step3 === '扩大样本量'
    case 5: {
      // 步骤五在推导结果为 goToA14 时可见
      const result = evaluateDecisionTree(state)
      return result.goToA14
    }
    case 6:
      return state.step1 === '否'
    default:
      return false
  }
}

/**
 * 创建空白决策树状态
 */
export function createEmptyState(): DecisionTreeState {
  return {
    step1: null,
    step2: null,
    step3: null,
    step4: null,
    step5: false,
    step6: null,
  }
}
