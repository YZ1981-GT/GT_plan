/**
 * 通用 checklist 持久化编解码 helper（J/K 循环共享）。
 *
 * 与 k5/k5Persistence.ts 等价，但不绑定单一循环，供 Wave 4 分循环迁移复用：
 *   - normalizeChecklistRemark：历史双层 `{remark:"..."}` 读兼容 → 新写单层 JSON。
 *   - collectChecklistResponses：合并 render-config responses_snapshot / allResponses /
 *     checklist_responses（数组或 { [item_id]: {...} } 两种形态），后写胜出。
 *   - toChecklistPatch：把子组件 `@save(itemId, value)` 的裸值/信封转成 Adapter patch，
 *     只序列化一次，避免双层包裹。
 *
 * Feature: workpaper-maintainability-convergence / Task 5.2
 * Validates: Requirements 3.4, 3.2
 */
import type { ChecklistResponse } from '@/composables/workpaper/useChecklistPersistence'
import { decodeRemark, encodeRemark, type JsonValue } from '@/composables/workpaper/remarkCodec'

/** 规范化 remark：保留纯文本；历史双层 JSON 解一次再单层写回。 */
export function normalizeChecklistRemark(value: unknown): string | null {
  if (value == null) return null
  const decoded = decodeRemark(value)
  if (typeof value === 'string' && decoded === value) return value
  return encodeRemark(decoded as JsonValue)
}

function responseFrom(itemId: string, source: unknown): ChecklistResponse | null {
  if (source == null) return null
  const raw = typeof source === 'object' && !Array.isArray(source)
    ? source as Record<string, unknown>
    : { remark: source }
  const id = typeof raw.item_id === 'string' ? raw.item_id : itemId
  if (!id) return null
  return {
    ...raw,
    item_id: id,
    remark: normalizeChecklistRemark(raw.remark),
    // 历史 render-config 会把数据库 null 投影为空串；仅更新 remark 时若原样回传空串，
    // 会触发后端 conclusion 白名单 422，故空串归一为 null。
    conclusion: raw.conclusion == null || raw.conclusion === '' ? null : String(raw.conclusion),
  } as ChecklistResponse
}

/** 合并多来源 responses（render-config 快照 + API 数组），后写胜出。 */
export function collectChecklistResponses(...sources: unknown[]): ChecklistResponse[] {
  const merged = new Map<string, ChecklistResponse>()
  for (const source of sources) {
    const entries = source instanceof Map
      ? [...source.entries()]
      : Array.isArray(source)
        ? source.map((item, index) => [String((item as any)?.item_id ?? index), item] as const)
        : source && typeof source === 'object'
          ? Object.entries(source as Record<string, unknown>)
          : []
    for (const [key, value] of entries) {
      const response = responseFrom(String(key), value)
      if (response) merged.set(response.item_id, response)
    }
  }
  return [...merged.values()]
}

/** 把子组件 save 值转成 Adapter patch，不做双层序列化。 */
export function toChecklistPatch(value: unknown): Partial<ChecklistResponse> {
  const envelope = value && typeof value === 'object' && !Array.isArray(value)
    && ('remark' in value || 'conclusion' in value) ? value as Record<string, unknown> : null
  const patch: Partial<ChecklistResponse> = {
    remark: normalizeChecklistRemark(envelope ? envelope.remark : value),
  }
  if (envelope && Object.prototype.hasOwnProperty.call(envelope, 'conclusion')) {
    patch.conclusion = envelope.conclusion == null || envelope.conclusion === ''
      ? null
      : String(envelope.conclusion)
  }
  return patch
}
