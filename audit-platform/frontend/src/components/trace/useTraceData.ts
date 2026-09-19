/**
 * useTraceData — 溯源链数据加载 composable
 *
 * Feature: platform-global-hardening
 * Requirements: 8.1, 8.2
 *
 * 加载「四表→报表→审定→底稿→调整→附注」完整溯源链。
 * 当前后端端点尚未实现，返回 mock 数据以支撑 UI 开发与测试。
 */
import { ref, watch, type Ref } from 'vue'

/** 溯源链中的一个节点（跳） */
export interface TraceNode {
  /** 节点类型 */
  type: 'raw_data' | 'report' | 'audited' | 'workpaper' | 'adjustment' | 'note'
  /** 节点中文标签 */
  label: string
  /** 节点描述（如"试算表 · 1122 应收账款"） */
  description: string
  /** 该节点金额 */
  amount: number | null
  /** 跳转目标（底稿 wp_code / 单元格坐标 / 调整分录 ID / 附注 section） */
  target: string
  /** 跳转目标可达 */
  reachable: boolean
}

/** useTraceData 的返回类型 */
export interface UseTraceDataReturn {
  /** 溯源链节点数组（有序） */
  chain: Ref<TraceNode[]>
  /** 加载中状态 */
  loading: Ref<boolean>
  /** 错误信息 */
  error: Ref<string>
  /** 主动刷新 */
  reload: () => Promise<void>
}

/**
 * 节点类型到中文标签映射
 */
const NODE_LABELS: Record<TraceNode['type'], string> = {
  raw_data: '四表',
  report: '报表',
  audited: '审定',
  workpaper: '底稿',
  adjustment: '调整',
  note: '附注',
}

/**
 * 生成 mock 溯源链数据
 * TODO: 对接后端 GET /api/projects/{pid}/trace/{addr_id} 后移除
 */
function buildMockChain(targetValue: number | null, targetAddr: string): TraceNode[] {
  const amount = targetValue ?? 0
  return [
    {
      type: 'raw_data',
      label: NODE_LABELS.raw_data,
      description: `试算表 · ${targetAddr}`,
      amount: amount * 1.05,
      target: `tb:${targetAddr}`,
      reachable: true,
    },
    {
      type: 'report',
      label: NODE_LABELS.report,
      description: `资产负债表 · ${targetAddr}`,
      amount: amount * 1.02,
      target: `report:BS-${targetAddr}`,
      reachable: true,
    },
    {
      type: 'audited',
      label: NODE_LABELS.audited,
      description: `审定汇总 · ${targetAddr}`,
      amount,
      target: `wp:${targetAddr.slice(0, 2)}-1`,
      reachable: true,
    },
    {
      type: 'workpaper',
      label: NODE_LABELS.workpaper,
      description: `明细底稿 · ${targetAddr}`,
      amount,
      target: `wp:${targetAddr.slice(0, 2)}-2`,
      reachable: true,
    },
    {
      type: 'adjustment',
      label: NODE_LABELS.adjustment,
      description: `调整分录 · AJE`,
      amount: amount * 0.03,
      target: `adj:${targetAddr}`,
      reachable: true,
    },
    {
      type: 'note',
      label: NODE_LABELS.note,
      description: `附注披露 · ${targetAddr}`,
      amount,
      target: `note:${targetAddr}`,
      reachable: true,
    },
  ]
}

/**
 * 溯源链数据加载 composable
 *
 * @param projectId - 项目 ID
 * @param targetAddr - 目标地址（addr_id 或坐标）
 * @param targetValue - 目标金额
 */
export function useTraceData(
  projectId: Ref<string>,
  targetAddr: Ref<string>,
  targetValue: Ref<number | null>,
): UseTraceDataReturn {
  const chain = ref<TraceNode[]>([])
  const loading = ref(false)
  const error = ref('')

  async function reload() {
    if (!projectId.value || !targetAddr.value) {
      chain.value = []
      return
    }

    loading.value = true
    error.value = ''

    try {
      // TODO: 对接真实后端端点
      // const res = await api.get(`/api/projects/${projectId.value}/trace/${targetAddr.value}`)
      // chain.value = res.chain

      // 暂用 mock 数据
      await new Promise(resolve => setTimeout(resolve, 300))
      chain.value = buildMockChain(targetValue.value, targetAddr.value)
    } catch (e: any) {
      error.value = e?.message ?? '加载溯源链失败'
      chain.value = []
    } finally {
      loading.value = false
    }
  }

  // 参数变化时自动重新加载
  watch(
    [projectId, targetAddr],
    ([pid, addr]) => {
      if (pid && addr) {
        reload()
      }
    },
    { immediate: true },
  )

  return { chain, loading, error, reload }
}
