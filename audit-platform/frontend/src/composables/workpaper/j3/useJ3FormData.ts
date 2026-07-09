/**
 * useJ3FormData — J3 股份支付 selfLoad 数据管理
 *
 * 核心特殊：**无单一 TB 回写！** J3 跨多科目（资本公积3002/管理费用6602/应付职工薪酬2211），
 * 费用确认走 EventBus → M4(权益结算)/J1(现金结算)/K8K9(管理费用)。
 *
 * 职责：
 * - selfLoad 从 render-config 获取 html_data
 * - checklist_responses 存取
 * - EventBus publish 费用确认事件
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 1.9, 1.10, 6.1-6.4
 */
import { ref, computed, type Ref } from 'vue'
import { http } from '@/utils/http'

export interface J3FormDataOptions {
  wpId: string
  projectId: string
  year?: string | number
  htmlData?: Record<string, unknown> | null
}

export interface J3Plan {
  id: string
  name: string                     // 方案名称
  type: 'equity' | 'cash'         // 权益结算 / 现金结算
  grantDate: string               // 授予日
  exercisePrice: number           // 行权价
  sharesCount: number             // 标的股数
  vestingPeriod: number           // 等待期（年）
  vestingDate: string             // 可行权日
  expiryDate: string              // 有效期截止
  unitFairValue: number           // 单位公允价值
  priorCumulative: number         // 以前累计确认
  currentExpense: number          // 本期确认
  cumulativeExpense: number       // 累计确认
  remainingExpense: number        // 剩余待确认
  serviceYears: number            // 已服务年数
  status: 'vesting' | 'exercisable' | 'expired' | 'cancelled'
}

export function useJ3FormData(options: J3FormDataOptions) {
  const isLoading = ref(false)
  const isSaving = ref(false)
  const plans: Ref<J3Plan[]> = ref([])
  const responses: Ref<Record<string, unknown>> = ref({})

  // ── selfLoad ──────────────────────────────────────────────────────────────

  async function loadData() {
    isLoading.value = true
    try {
      // 优先使用传入的 htmlData（bundle 场景）
      if (options.htmlData) {
        parseHtmlData(options.htmlData)
        return
      }
      // selfLoad 从 render-config 获取
      const res = await http.get(`/api/workpapers/${options.wpId}/render-config`)
      const sheets = res.data?.data?.sheets || res.data?.sheets || []
      if (sheets.length > 0 && sheets[0].html_data) {
        parseHtmlData(sheets[0].html_data)
      }
    } catch (e) {
      console.error('[J3 FormData] selfLoad failed:', e)
    } finally {
      isLoading.value = false
    }
  }

  function parseHtmlData(data: Record<string, unknown>) {
    if (data.plans && Array.isArray(data.plans)) {
      plans.value = data.plans as J3Plan[]
    }
    if (data.responses && typeof data.responses === 'object') {
      responses.value = data.responses as Record<string, unknown>
    }
  }

  // ── checklist_responses 存取 ─────────────────────────────────────────────

  function getResponse(key: string): unknown {
    return responses.value[key]
  }

  function setResponse(key: string, value: unknown) {
    responses.value[key] = value
  }

  async function saveResponses() {
    isSaving.value = true
    try {
      const items = Object.entries(responses.value).map(([key, val]) => ({
        item_id: `J3-${key}`,
        content: typeof val === 'string' ? val : JSON.stringify(val),
      }))
      await http.put(`/api/workpapers/${options.wpId}/checklist-responses`, { items })
    } catch (e) {
      console.error('[J3 FormData] save failed:', e)
    } finally {
      isSaving.value = false
    }
  }

  // ── EventBus 费用确认（无TB回写！） ────────────────────────────────────────

  async function publishExpenseRecognized(plan: J3Plan) {
    const event = plan.type === 'equity'
      ? 'share-payment:equity-settled'
      : 'share-payment:cash-settled'

    try {
      await http.post(`/api/projects/${options.projectId}/events/publish`, {
        event_type: event,
        payload: {
          planName: plan.name,
          amount: plan.currentExpense,
          settlementType: plan.type,
          wpId: options.wpId,
        },
      })
    } catch (e) {
      console.warn('[J3 FormData] EventBus publish failed (联动底稿可能未就绪):', e)
    }
  }

  // ── computed ──────────────────────────────────────────────────────────────

  const totalCurrentExpense = computed(() =>
    plans.value.reduce((sum, p) => sum + (p.currentExpense || 0), 0),
  )
  const equityPlans = computed(() => plans.value.filter(p => p.type === 'equity'))
  const cashPlans = computed(() => plans.value.filter(p => p.type === 'cash'))

  return {
    isLoading,
    isSaving,
    plans,
    responses,
    loadData,
    getResponse,
    setResponse,
    saveResponses,
    publishExpenseRecognized,
    totalCurrentExpense,
    equityPlans,
    cashPlans,
  }
}
