/**
 * useH5IndustryGuard — H5油气资产行业适用性守卫
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 1.3
 * Requirements: 1.11, 1.12, 12.1-12.3
 *
 * 职责：
 * - inject('projectContext') 从 GtWpRenderer 父组件获取项目上下文
 * - 检查 project.industry 是否在 ['oil_gas', 'mining'] 中
 * - 非适用行业返回 { isApplicable: false, message: '本底稿仅适用于石油天然气/采矿行业项目' }
 * - 无 context（null/undefined）时默认 isApplicable = true（允许渲染）
 */
import { ref, inject, type Ref } from 'vue'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 适用行业白名单 */
export const APPLICABLE_INDUSTRIES = ['oil_gas', 'mining'] as const

/** 非适用行业提示信息 */
export const INDUSTRY_GUARD_MESSAGE = '本底稿仅适用于石油天然气/采矿行业项目'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface IndustryGuardResult {
  /** 当前项目行业是否适用此底稿 */
  isApplicable: Ref<boolean>
  /** 不适用时的提示信息（适用时为空字符串） */
  message: Ref<string>
  /** 重新检查行业适用性（手动触发） */
  check: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5IndustryGuard(): IndustryGuardResult {
  const isApplicable = ref(true)
  const message = ref('')

  // inject projectContext（由 GtWpRenderer 或父组件 provide）
  const projectContext = inject<any>('projectContext', null)

  function check(): void {
    // 无 context 时默认放行
    if (!projectContext) {
      isApplicable.value = true
      message.value = ''
      return
    }

    // 兼容 Ref<object> 和普通 object 两种注入形态
    const ctx = projectContext?.value ?? projectContext
    if (!ctx) {
      isApplicable.value = true
      message.value = ''
      return
    }

    // 从 context 中提取 industry 字段（兼容嵌套 project.industry）
    const industry: string = ctx?.industry || ctx?.project?.industry || ''

    // 如果 industry 为空（未设置），默认放行
    if (!industry) {
      isApplicable.value = true
      message.value = ''
      return
    }

    // 检查是否在适用行业白名单中
    if ((APPLICABLE_INDUSTRIES as readonly string[]).includes(industry)) {
      isApplicable.value = true
      message.value = ''
    } else {
      isApplicable.value = false
      message.value = INDUSTRY_GUARD_MESSAGE
    }
  }

  // 初始执行一次检查
  check()

  return {
    isApplicable,
    message,
    check,
  }
}

export default useH5IndustryGuard
