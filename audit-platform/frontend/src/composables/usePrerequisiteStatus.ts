/**
 * usePrerequisiteStatus — B/C 类前置底稿状态查询（E1 Sprint 2 Task 2.16）
 *
 * 锚定 requirements F5.6 前置状态横幅。
 *
 * 功能：
 * - 查询 B23-2（控制了解）/B51-3（舞弊风险评估）/C3（控制测试结论）三个前置底稿
 * - 三态：✅ 已完成 / ⚠ 进行中 / ❌ 未开始
 * - 整体规则：全 ✅ → 绿色横幅；任一 ⚠ → 黄色；任一 ❌ → 红色
 *
 * 后端端点：GET /api/projects/{pid}/workpapers/prerequisite-status?wp_code=E1
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

export type PrerequisiteState = 'completed' | 'in_progress' | 'pending' | 'not_applicable'

export interface PrerequisiteItem {
  wp_code: string
  wp_name: string
  state: PrerequisiteState
  conclusion?: string | null
  /** 可选：风险等级（B51-3 的舞弊风险） */
  risk_level?: string | null
  /** 跳转 URL */
  navigate_url?: string
}

export interface PrerequisiteStatusResp {
  items: PrerequisiteItem[]
  /** 整体状态: ready=全绿 / partial=部分黄 / blocked=红 */
  overall: 'ready' | 'partial' | 'blocked'
  message?: string
}

const E1_PREREQUISITES = [
  { wp_code: 'B23-2', wp_name: '货币资金控制了解' },
  { wp_code: 'C3', wp_name: '货币资金控制测试结论' },
  { wp_code: 'B51-3', wp_name: '舞弊风险评估' },
]

// D 循环前置底稿（B23-1 了解内控 / C2 控制测试 / B51-5 舞弊风险评估）
const D_CYCLE_PREREQUISITES = [
  { wp_code: 'B23-1', wp_name: '了解内部控制' },
  { wp_code: 'C2', wp_name: '控制测试结论' },
  { wp_code: 'B51-5', wp_name: '舞弊风险评估' },
]

// F 循环前置底稿（B23-3 采购存货循环业务层面控制 / C4 采购存货循环控制测试 / B51-4 存货舞弊风险评估）
const F_CYCLE_PREREQUISITES = [
  { wp_code: 'B23-3', wp_name: '采购存货循环业务层面控制' },
  { wp_code: 'C4', wp_name: '采购存货循环控制测试结论' },
  { wp_code: 'B51-4', wp_name: '存货舞弊风险评估' },
]

// H 循环前置底稿（C6 固定资产控制测试 / C7 在建工程控制测试 / C14 租赁循环控制测试）
// C7 仅 H2 路径强制 / C14 仅 H8/H9 路径强制 / C6 所有 H 底稿共用
const H_CYCLE_PREREQUISITES = [
  { wp_code: 'C6', wp_name: '固定资产循环控制测试' },
  { wp_code: 'C7', wp_name: '在建工程循环控制测试' },
  { wp_code: 'C14', wp_name: '租赁循环控制测试' },
]

/**
 * 根据 H 循环具体 wp_code 返回适用的前置底稿列表
 * - C6: 所有 H 底稿共用（H0~H10）
 * - C7: 仅 H2（在建工程）路径强制
 * - C14: 仅 H8/H9（使用权资产/租赁负债）路径强制
 */
function getHCyclePrerequisites(wpCode: string): typeof H_CYCLE_PREREQUISITES {
  // 提取 wp_code 前缀（如 H2-5 → H2, H8 → H8, H9-1 → H9）
  const match = wpCode.match(/^H(\d+)/i)
  const hNum = match ? parseInt(match[1], 10) : -1

  const result: typeof H_CYCLE_PREREQUISITES = [
    { wp_code: 'C6', wp_name: '固定资产循环控制测试' },
  ]

  // C7 仅 H2 路径强制
  if (hNum === 2) {
    result.push({ wp_code: 'C7', wp_name: '在建工程循环控制测试' })
  }

  // C14 仅 H8/H9 路径强制
  if (hNum === 8 || hNum === 9) {
    result.push({ wp_code: 'C14', wp_name: '租赁循环控制测试' })
  }

  return result
}

// I 无形资产循环前置底稿（C8 无形资产及其他长期资产循环控制测试 / C9 研发循环控制测试）
// C8 所有 I 底稿共用（I1/I3/I4/I5）/ C9 仅 I2/I6 路径强制（研发活动相关）
const I_CYCLE_PREREQUISITES = [
  { wp_code: 'C8', wp_name: '无形资产及其他长期资产循环控制测试' },
  { wp_code: 'C9', wp_name: '研发循环控制测试' },
]

// G 投资循环前置底稿（C5 投资循环控制测试，G0~G14 共用）
// G-F9 task 2.23 — Sprint 0 实测确认仅 C5 单一前置（无 B23-X / B51-X 投资专项）
const G_CYCLE_PREREQUISITES = [
  { wp_code: 'C5', wp_name: '投资循环控制测试' },
]

// J 职工薪酬循环前置底稿（C10 薪酬循环控制测试，J1~J3 共用）
// J-F5 task 2.3 — Sprint 0 实测确认仅 C10 单一前置（无 B23-X / B51-X 薪酬专项）
const J_CYCLE_PREREQUISITES = [
  { wp_code: 'C10', wp_name: '薪酬循环控制测试' },
]

// K 管理循环前置底稿（C11 管理循环控制测试，K0~K13 共用）
// K-F5 task 2.3 — Sprint 0 实测确认仅 C11 单一前置（无 B23-X / B51-X 管理专项）
const K_CYCLE_PREREQUISITES = [
  { wp_code: 'C11', wp_name: '管理循环控制测试' },
]

// L 筹资循环前置底稿（C13 债务循环业务层面控制测试，L0~L8 共用）
// L-F5 task 2.3 — Sprint 0 实测确认仅 C13 单一前置（无 B23-X / B51-X 筹资专项）
const L_CYCLE_PREREQUISITES = [
  { wp_code: 'C13', wp_name: '债务循环业务层面控制测试' },
]

// M 权益循环无独立 C 类前置底稿（由 A 类总体审计策略覆盖）
// M-F5 task 2.3 — M 循环 M_CYCLE_PREREQUISITES = []（空数组，前置状态始终 ready）
const M_CYCLE_PREREQUISITES: { wp_code: string; wp_name: string }[] = []

// N 税金循环前置底稿（C12 税金循环控制测试，N1~N5 共用）
// N-F5 task 2.3 — Sprint 0 实测确认仅 C12 单一前置
const N_CYCLE_PREREQUISITES = [
  { wp_code: 'C12', wp_name: '税金循环控制测试' },
]

/**
 * 根据 I 循环具体 wp_code 返回适用的前置底稿列表
 * - C8: 所有 I 底稿共用（I0~I6）
 * - C9: 仅 I2 开发支出 / I6 研发费用 路径强制
 */
function getICyclePrerequisites(wpCode: string): typeof I_CYCLE_PREREQUISITES {
  // 提取 wp_code 前缀（如 I1-2 → I1, I2-6 → I2, I6 → I6）
  const match = wpCode.match(/^I(\d+)/i)
  const iNum = match ? parseInt(match[1], 10) : -1

  const result: typeof I_CYCLE_PREREQUISITES = [
    { wp_code: 'C8', wp_name: '无形资产及其他长期资产循环控制测试' },
  ]

  // C9 仅 I2（开发支出）/ I6（研发费用）路径强制
  if (iNum === 2 || iNum === 6) {
    result.push({ wp_code: 'C9', wp_name: '研发循环控制测试' })
  }

  return result
}

export function usePrerequisiteStatus(projectId: string, wpCode: string) {
  const items = ref<PrerequisiteItem[]>([])
  const overall = ref<'ready' | 'partial' | 'blocked'>('ready')
  const loading = ref(false)
  const lastError = ref<string>('')

  const banner = computed(() => {
    if (loading.value) return { type: 'info' as const, message: '正在加载前置状态...' }
    if (overall.value === 'ready') {
      return {
        type: 'success' as const,
        message: '✅ 所有前置底稿已完成，可执行实质性程序',
      }
    }
    if (overall.value === 'partial') {
      const inProgress = items.value.filter((i) => i.state === 'in_progress').map((i) => i.wp_code).join('、')
      return {
        type: 'warning' as const,
        message: `⚠ 前置部分完成，建议先完成 ${inProgress || '前置底稿'}`,
      }
    }
    const pending = items.value.filter((i) => i.state === 'pending').map((i) => i.wp_code).join('、')
    return {
      type: 'error' as const,
      message: `❌ 前置条件未满足: ${pending || '前置底稿'} 尚未完成，可点击跳转`,
    }
  })

  async function refresh() {
    if (!projectId) return
    loading.value = true
    lastError.value = ''
    try {
      const data: PrerequisiteStatusResp = await api.get(
        `/api/projects/${projectId}/workpapers/prerequisite-status`,
        { params: { wp_code: wpCode } },
      )
      items.value = data?.items || []
      overall.value = data?.overall || 'ready'
    } catch (err: any) {
      // 端点可能未实现，降级为静默置空：默认前置全 pending
      lastError.value = err?.message || ''
      const isDCycle = /^D\d/i.test(wpCode)
      const isFCycle = /^F\d/i.test(wpCode)
      const isHCycle = /^H\d/i.test(wpCode)
      const isICycle = /^I\d/i.test(wpCode)
      const isGCycle = /^G\d/i.test(wpCode)
      const isJCycle = /^J\d/i.test(wpCode)
      const isKCycle = /^K\d/i.test(wpCode)
      const isLCycle = /^L\d/i.test(wpCode)
      const isMCycle = /^M\d/i.test(wpCode)
      const isNCycle = /^N\d/i.test(wpCode)
      const fallbackList = isHCycle
        ? getHCyclePrerequisites(wpCode)
        : isICycle
        ? getICyclePrerequisites(wpCode)
        : isGCycle
        ? G_CYCLE_PREREQUISITES
        : isJCycle
        ? J_CYCLE_PREREQUISITES
        : isKCycle
        ? K_CYCLE_PREREQUISITES
        : isLCycle
        ? L_CYCLE_PREREQUISITES
        : isMCycle
        ? M_CYCLE_PREREQUISITES
        : isNCycle
        ? N_CYCLE_PREREQUISITES
        : isFCycle
        ? F_CYCLE_PREREQUISITES
        : isDCycle
        ? D_CYCLE_PREREQUISITES
        : E1_PREREQUISITES
      items.value = fallbackList.map((p) => ({
        wp_code: p.wp_code,
        wp_name: p.wp_name,
        state: 'pending' as PrerequisiteState,
      }))
      // M 循环无前置底稿（空数组），fallback 时直接 ready
      overall.value = fallbackList.length === 0 ? 'ready' : 'blocked'
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    refresh()
  })

  return {
    items,
    overall,
    loading,
    lastError,
    banner,
    refresh,
  }
}
