export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

const MAX_LEGACY_UNWRAP_STEPS = 4

function parseJsonOnce(value: string): unknown {
  try {
    return JSON.parse(value) as unknown
  } catch {
    return value
  }
}

function isRemarkWrapper(value: unknown): value is { remark: string } {
  if (
    typeof value !== 'object'
    || value === null
    || Array.isArray(value)
    || Object.keys(value).length !== 1
    || !Object.prototype.hasOwnProperty.call(value, 'remark')
  ) return false

  const remark = (value as { remark: unknown }).remark
  return typeof remark === 'string' && parseJsonOnce(remark) !== remark
}

/** Serialize a business value exactly once for checklist_responses.remark. */
export function encodeRemark(value: JsonValue): string {
  return JSON.stringify(value)
}

/**
 * Decode current single-layer JSON and historical `{ remark: "..." }` wrappers.
 * Each transport/wrapper layer is parsed once; decoded business strings are never
 * parsed again, so JSON-looking strings keep their original type and value.
 */
export function decodeRemark(value: unknown): JsonValue {
  let current: unknown = typeof value === 'string' ? parseJsonOnce(value) : value

  for (let step = 0; step < MAX_LEGACY_UNWRAP_STEPS; step += 1) {
    if (!isRemarkWrapper(current)) break
    current = parseJsonOnce(current.remark)
  }

  return current as JsonValue
}
