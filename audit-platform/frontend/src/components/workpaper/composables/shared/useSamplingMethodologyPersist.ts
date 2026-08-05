/**
 * useSamplingMethodologyPersist — 宿主侧抽样方法学留痕接线件（sampling-compliance-closure R6.3）
 *
 * 41 个宿主要做同一件事：把 `GtVoucherSamplingEngine` 的 `filled` 载荷里的 `methodology`
 * 落到固定 item key，并在抽凭区把它渲染到底稿正文上（复核与归档看的是底稿，不是后台日志）。
 *
 * **为什么持久化动作要由宿主注入**：实测各循环写库机制并不统一 ——
 * D/E 组是 `props.saveImmediate(itemId, data)`，F3/F4 是
 * `window.dispatchEvent(new CustomEvent('f3:save-items'))`，还有走 per-cycle composable 的。
 * 硬把某一种写进共享件，等于让另外两种循环无法接入（或被迫改写库机制 = 半径失控）。
 * 故共享件只收口「键名 / 序列化 / 读回 / 只读门控」这四件确定的事。
 *
 * Validates: Requirements 6.3
 * Properties: Property 15
 */
import { computed, unref, type ComputedRef, type Ref } from 'vue'
import {
  parseMethodology,
  samplingMethodologyItemKey,
  serializeMethodology,
  type SamplingMethodologySnapshot,
} from './samplingFillTarget'

/** 与平台 `ChecklistResponse` 的最小交集（避免共享件依赖某个循环的类型文件） */
interface MethodologyResponseLike {
  remark?: string | null
}

export interface SamplingMethodologyPersistOptions {
  /** 底稿编码（如 `D3`）；用于构键 `{wpCode}-sampling-methodology` */
  wpCode: string | Ref<string> | ComputedRef<string>
  /** 宿主的 checklist 响应表（读回用） */
  allResponses: Ref<Map<string, MethodologyResponseLike>>
  /**
   * 宿主自己的持久化动作。`remark` 为空串表示「清空该键」。
   * 抛错由调用方处理 —— 本件不吞异常（静默失败会让审计师以为已留痕）。
   */
  persist: (itemId: string, remark: string) => void | Promise<void>
  /** 只读态（复核锁定 / 已定稿）下不写库 */
  isReadonly?: Ref<boolean> | ComputedRef<boolean>
}

export interface SamplingMethodologyPersistApi {
  /** 方法学持久化键 */
  methodologyItemKey: ComputedRef<string>
  /** 从 checklist 读回的方法学（解析失败或无内容 → null，bar 据此不渲染） */
  methodology: ComputedRef<SamplingMethodologySnapshot | null>
  /**
   * 落库。返回是否真的写了：
   * - 只读态 → false
   * - 载荷无实质内容 → false（不写空壳；「没抽过样」与「抽了但没留痕」必须可区分）
   */
  persistMethodology: (
    m: SamplingMethodologySnapshot | null | undefined,
  ) => Promise<boolean>
}

/**
 * 从 render-config 的 `responses_snapshot` 构造一张只读响应表。
 *
 * 给**没有 `allResponses` prop** 的宿主用（G4/G5/G6/G7 这批只拿到 `htmlData`）：
 * 方法学存在 `checklist_responses` 里，没有 `allResponses` 就没有读回通道，
 * 而 render-config 本来就把快照下发了。
 *
 * 两种形态都认（平台两种都存在）：数组 `[{item_id, remark}]` 与对象 `{itemId: {remark}}`。
 * 解析不出返回空表 —— 读回是增强，失败不应阻塞抽凭。
 */
export function snapshotToResponseMap(
  htmlData: unknown,
): Map<string, MethodologyResponseLike> {
  const out = new Map<string, MethodologyResponseLike>()
  const snap = (htmlData as { responses_snapshot?: unknown } | null | undefined)
    ?.responses_snapshot
  if (Array.isArray(snap)) {
    for (const it of snap) {
      const row = it as { item_id?: string; remark?: string | null }
      if (row?.item_id) out.set(row.item_id, { remark: row.remark ?? null })
    }
  } else if (snap && typeof snap === 'object') {
    for (const [k, v] of Object.entries(snap as Record<string, unknown>)) {
      const row = v as { remark?: string | null } | string | null
      out.set(k, typeof row === 'string' ? { remark: row } : { remark: row?.remark ?? null })
    }
  }
  return out
}

/**
 * 平台标准直写出口，给**没有 save prop 也没有 `emit('save')`** 的宿主兜底
 * （G5/G7/H1/H2 这批把持久化封在 per-cycle composable 里，对外不暴露写入口）。
 *
 * 走的是平台既有 checklist-responses 端点（全仓 40+ 处同形），不是新造通道。
 * 有 save prop 的宿主**不要**用它 —— 那会绕过父级的批量/防抖与 autoSnapshot。
 */
export function buildChecklistDirectPersist(opts: {
  wpId: string | Ref<string | undefined> | ComputedRef<string | undefined>
  projectId: string | Ref<string | undefined> | ComputedRef<string | undefined>
}): (itemId: string, remark: string) => Promise<void> {
  return async (itemId: string, remark: string) => {
    const wpId = unref(opts.wpId)
    const projectId = unref(opts.projectId)
    if (!wpId || !projectId) return
    const { default: http } = await import('@/utils/http')
    await http.put(`/api/workpapers/${wpId}/checklist-responses`, {
      project_id: projectId,
      items: [{ item_id: itemId, conclusion: null, remark }],
    })
  }
}

export function useSamplingMethodologyPersist(
  opts: SamplingMethodologyPersistOptions,
): SamplingMethodologyPersistApi {
  const methodologyItemKey = computed(() =>
    samplingMethodologyItemKey(unref(opts.wpCode) ?? ''),
  )

  const methodology = computed<SamplingMethodologySnapshot | null>(() =>
    // 直读 `allResponses.value`：computed 内经 getter 函数取值不保证依赖被追踪
    // （平台已有踩坑：写入后 computed 不更新）
    parseMethodology(opts.allResponses.value.get(methodologyItemKey.value)?.remark ?? null),
  )

  async function persistMethodology(
    m: SamplingMethodologySnapshot | null | undefined,
  ): Promise<boolean> {
    if (unref(opts.isReadonly) === true) return false
    const remark = serializeMethodology(m)
    if (!remark) return false
    await opts.persist(methodologyItemKey.value, remark)
    return true
  }

  return { methodologyItemKey, methodology, persistMethodology }
}
