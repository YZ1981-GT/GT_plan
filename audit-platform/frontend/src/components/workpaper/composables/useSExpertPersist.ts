/**
 * useSExpertPersist — S12/S13/S14 专项底稿子表 checklist_responses 持久化接线
 *
 * 背景：S12(cpa-expert)/S13(mgmt-expert)/S14(accounting-estimate) 主入口此前丢弃
 * 后端 responses_snapshot，子表仅用本地 skeleton ref，数据不落库/刷新丢失。
 *
 * 本 composable 提供子表统一的 load(seed) + save 接线：
 * - inject('saveResponse')：由主入口 provide（防抖 PUT /checklist-responses，乐观更新 Map）
 * - seed(bindings)：挂载时从主入口透传的 allResponses(Map) 恢复 ref 值
 * - save(itemId, value)：字段 change 时持久化（结构化数据 JSON 打包进 remark）
 *
 * item_id 约定：{sheetKey}-rows / {sheetKey}-conclusion（前缀 S12-/S13-/S14-），
 * 后端 checklist_responses.py 白名单已对 S12-/S13-/S14- 前缀放行（pass）。
 *
 * ref-unwrap 铁律：主入口 allResponses 为 ref(Map)，经模板 :all-responses 绑定自动
 * 解包为纯 Map 传入子表 props，故 getAllResponses 返回的是纯 Map（无 .value）。
 *
 * Spec: S12/S13/S14 子表持久化接线（feature 级补接）
 */
import { inject, onMounted, type Ref } from 'vue'

type SaveFn = (itemId: string, value: any) => void

export interface SheetBinding {
  itemId: string
  /** 目标 ref（数组行模型 或 结论字符串） */
  ref: Ref<any>
}

/** 从 responses Map 解析某 item 的存储值（remark 优先，兼容 JSON 打包） */
export function parseResponseValue(map: Map<string, any> | undefined, itemId: string): any {
  const raw = map?.get(itemId)
  if (!raw) return undefined
  const v = raw.remark ?? raw.conclusion
  if (v == null || v === '') return undefined
  if (typeof v !== 'string') return v
  try {
    return JSON.parse(v)
  } catch {
    return v
  }
}

/**
 * S12/S13/S14 子表持久化接线。
 *
 * @param getAllResponses 返回主入口透传的 allResponses（纯 Map，已解包）
 */
export function useSExpertPersist(getAllResponses: () => Map<string, any> | undefined) {
  const saveResponse = inject<SaveFn | undefined>('saveResponse', undefined)

  /** 用 responses 中的存储值覆盖 bindings（有值才覆盖，保留 skeleton 结构） */
  function seed(bindings: SheetBinding[]): void {
    const map = getAllResponses()
    if (!map || map.size === 0) return
    for (const { itemId, ref } of bindings) {
      const parsed = parseResponseValue(map, itemId)
      if (parsed === undefined) continue
      if (Array.isArray(ref.value)) {
        // 数组行模型：仅当解析出非空数组才替换（避免空数组抹掉 skeleton）
        if (Array.isArray(parsed) && parsed.length) ref.value = parsed
      } else {
        ref.value = parsed
      }
    }
  }

  /** 挂载时 seed（主入口在 isLoading=false 前已填充 allResponses，子表 mount 时 Map 已就绪） */
  function seedOnMount(bindings: SheetBinding[]): void {
    onMounted(() => seed(bindings))
  }

  /** 持久化单个 item（结构化 value 由主入口 persistResponse 序列化进 remark） */
  function save(itemId: string, value: any): void {
    saveResponse?.(itemId, value)
  }

  return { saveResponse, seed, seedOnMount, save, hasSaver: !!saveResponse }
}

export default useSExpertPersist
