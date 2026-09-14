import type { ChecklistResponse } from '@/composables/workpaper/useChecklistPersistence'
import { decodeRemark, encodeRemark, type JsonValue } from '@/composables/workpaper/remarkCodec'

/** Canonicalize historical double-wrapped JSON while preserving plain text. */
export function normalizeK5Remark(value: unknown): string | null {
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
    remark: normalizeK5Remark(raw.remark),
    // 历史 render-config 会把数据库 null 投影为空串；若保留空串，
    // 仅更新 remark 时 Adapter 会原样回传并触发后端 conclusion 白名单 422。
    conclusion: raw.conclusion == null || raw.conclusion === '' ? null : String(raw.conclusion),
  } as ChecklistResponse
}

/** Merge render-config response snapshots and API arrays; later sources win. */
export function collectK5Responses(...sources: unknown[]): ChecklistResponse[] {
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

/** Convert child save values into the adapter's standard patch without double serialization. */
export function toK5PersistencePatch(value: unknown): Partial<ChecklistResponse> {
  const envelope = value && typeof value === 'object' && !Array.isArray(value)
    && ('remark' in value || 'conclusion' in value) ? value as Record<string, unknown> : null
  const patch: Partial<ChecklistResponse> = {
    remark: normalizeK5Remark(envelope ? envelope.remark : value),
  }
  if (envelope && Object.prototype.hasOwnProperty.call(envelope, 'conclusion')) {
    patch.conclusion = envelope.conclusion == null || envelope.conclusion === ''
      ? null
      : String(envelope.conclusion)
  }
  return patch
}
