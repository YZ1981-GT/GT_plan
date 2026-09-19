/**
 * useDeliverableLineage — 出品物溯源状态管理 composable
 *
 * Spec: deliverable-lineage-and-writeback Task 5.2/5.3
 * Requirements: 3.1, 3.2, 3.3, 3.5
 *
 * 功能：
 * - 解析 OnlyOffice 书签锚点 → section_code
 * - 调用溯源查询端点获取 LinkageContract 列表
 * - 提供跨层跳转（复用 LinkageContract.route）
 * - 无锚点降级提示
 *
 * 铁律：用 api.get（@/services/apiProxy）调后端——自动附 Authorization token
 *       + 自动解 {code,message,data} 信封（勿再手动解包）
 */
import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import type { LinkageContract } from '@/types/linkageContract'
import { resolveLinkageRoute } from '@/composables/useResolveLinkageRoute'
import { api } from '@/services/apiProxy'

export interface DeliverableTraceResult {
  contracts: LinkageContract[]
  section_state: {
    section_code: string
    is_stale: boolean
    source_snapshot_hash: string | null
    anchor_name: string | null
  } | null
}

/**
 * 锚点名 → section_code 逆映射（前端镜像实现）
 * 'sec_八_1' → '八、1'
 * 规则：去 'sec_' 前缀，'_' 恢复为 '、'（仅第一个下划线后的首个替换为顿号）
 */
export function sectionCodeFromAnchor(anchorName: string): string | null {
  if (!anchorName || !anchorName.startsWith('sec_')) return null
  // 去掉 'sec_' 前缀
  const body = anchorName.slice(4)
  if (!body) return null
  // 逆映射：将第一个 '_' 恢复为 '、'，后续 '_' 保持（因为 section_code 只含一个顿号分隔）
  // 实际规则：anchor_name 中所有 '、' → '_'，'·' → '_'，空格去掉
  // 逆映射：找到中文字符后紧跟的第一个 '_' 恢复为 '、'
  // 示例：'八_1' → '八、1'；'五_12_1' → '五、12·1' 或 '五、12_1'
  // 简化处理：恢复第一个紧跟中文字符后的 '_' 为 '、'
  const idx = body.search(/[\u4e00-\u9fff]_/)
  if (idx >= 0) {
    // 中文字符后的 '_' 恢复为 '、'
    const charPos = idx + 1 // '_' 的位置
    return body.slice(0, charPos) + '、' + body.slice(charPos + 1)
  }
  // 无中文+下划线模式，尝试直接替换第一个下划线
  const firstUnderscore = body.indexOf('_')
  if (firstUnderscore > 0) {
    return body.slice(0, firstUnderscore) + '、' + body.slice(firstUnderscore + 1)
  }
  return body
}

/**
 * section_code → 锚点名（前端镜像实现）
 * '八、1' → 'sec_八_1'
 */
export function anchorNameFromSectionCode(sectionCode: string): string {
  const safe = sectionCode.trim()
    .replace(/、/g, '_')
    .replace(/ /g, '')
    .replace(/·/g, '_')
  return `sec_${safe}`
}

export function useDeliverableLineage(
  wordExportTaskId: Ref<string>,
  projectId: Ref<string>,
) {
  const router = useRouter()

  const currentSectionCode = ref<string | null>(null)
  const currentAnchorName = ref<string | null>(null)
  const contracts = ref<LinkageContract[]>([])
  const sectionState = ref<DeliverableTraceResult['section_state']>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * 从 OnlyOffice 书签名解析并触发溯源查询
   */
  async function traceFromAnchor(anchorName: string): Promise<void> {
    currentAnchorName.value = anchorName
    const sectionCode = sectionCodeFromAnchor(anchorName)
    if (!sectionCode) {
      currentSectionCode.value = null
      contracts.value = []
      sectionState.value = null
      error.value = null
      return
    }
    currentSectionCode.value = sectionCode
    await traceSection(sectionCode)
  }

  /**
   * 直接通过 section_code 触发溯源查询
   */
  async function traceSection(sectionCode: string): Promise<void> {
    if (!wordExportTaskId.value || !projectId.value) return

    loading.value = true
    error.value = null
    contracts.value = []
    sectionState.value = null

    try {
      const url = `/api/projects/${projectId.value}/deliverables/${wordExportTaskId.value}/trace?section_code=${encodeURIComponent(sectionCode)}`
      // api.get 自动附 auth + 自动解 {code,message,data} 信封
      const data = await api.get<DeliverableTraceResult>(url)
      contracts.value = data.contracts || []
      sectionState.value = data.section_state || null
    } catch (e: any) {
      // axios 错误：e.response?.status 取 HTTP 状态码
      if (e?.response?.status === 504) {
        error.value = '溯源查询超时，请稍后重试'
      } else {
        error.value = e?.response?.data?.message || e?.message || '查询失败'
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * 跨层跳转：用 LinkageContract.route 经 vue-router 导航（需求 3.3）
   * 不新建跳转逻辑，复用 resolveLinkageRoute
   */
  async function navigateToSource(contract: LinkageContract): Promise<void> {
    // 优先使用预计算路由
    const route = await resolveLinkageRoute(contract, projectId.value)
    if (route) {
      router.push(route)
    }
  }

  /**
   * 标记当前没有可解析的锚点（旧版本出品物场景）
   */
  function clearSection(): void {
    currentSectionCode.value = null
    currentAnchorName.value = null
    contracts.value = []
    sectionState.value = null
    error.value = null
  }

  return {
    /** 当前解析出的章节编码，null 表示无可解析锚点 */
    currentSectionCode,
    /** 当前锚点名 */
    currentAnchorName,
    /** 溯源契约列表 */
    contracts,
    /** 章节状态（含 stale 标记） */
    sectionState,
    /** 是否加载中 */
    loading,
    /** 错误信息 */
    error,
    /** 从锚点名触发溯源 */
    traceFromAnchor,
    /** 从 section_code 触发溯源 */
    traceSection,
    /** 跨层跳转到上游来源 */
    navigateToSource,
    /** 清除当前选区 */
    clearSection,
  }
}
