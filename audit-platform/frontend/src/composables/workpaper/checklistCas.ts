import type { AxiosRequestConfig } from 'axios'

import { api } from '@/services/apiProxy'

/** checklist 保存所需的最小 wire 形态。 */
export interface ChecklistCasItem {
  item_id: string
  conclusion?: string | null
  remark?: string | null
  wp_ref?: string | null
  version?: string
  updated_at?: string
}

export interface ChecklistCasSaveInput {
  wpId: string
  projectId?: string
  items: readonly ChecklistCasItem[]
  config?: AxiosRequestConfig
}

export type ChecklistPut = (
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
) => Promise<unknown>

function sourceItems(source: unknown): ChecklistCasItem[] {
  if (Array.isArray(source)) return source.filter(isItem)
  if (!source || typeof source !== 'object') return []
  const value = source as Record<string, unknown>
  if (isItem(value)) return [value]
  for (const key of ['data', 'items', 'responses']) {
    if (!(key in value)) continue
    const nested = sourceItems(value[key])
    if (nested.length > 0 || Array.isArray(value[key])) return nested
  }
  return []
}

function isItem(value: unknown): value is ChecklistCasItem {
  return Boolean(
    value
    && typeof value === 'object'
    && typeof (value as Record<string, unknown>).item_id === 'string',
  )
}

function versionOf(item: ChecklistCasItem): string | undefined {
  const value = item.version ?? item.updated_at
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

/** 可恢复本地草稿必须带“编辑时所见”的版本；恢复时不能拿新 GET 版本替旧载荷背书。 */
export interface ChecklistDraftEnvelope<T extends ChecklistCasItem> {
  readonly item: T
  readonly baseVersion?: string
  /** 该草稿来自被原子拒绝的批次，必须由用户再次确认，不能按版本相等自动重放。 */
  readonly requiresConfirmation?: boolean
}

export function makeChecklistDraft<T extends ChecklistCasItem>(
  item: T,
  baseVersion: string | undefined,
  requiresConfirmation = false,
): ChecklistDraftEnvelope<T> {
  return {
    item,
    ...(baseVersion ? { baseVersion } : {}),
    ...(requiresConfirmation ? { requiresConfirmation: true } : {}),
  }
}

/** 同时兼容本轮前直接存 item 的旧草稿；旧草稿不含基线，调用方必须 fail-closed 处理。 */
export function readChecklistDraft<T extends ChecklistCasItem>(source: unknown): ChecklistDraftEnvelope<T> | null {
  if (!source || typeof source !== 'object') return null
  const record = source as Record<string, unknown>
  if (isItem(record.item)) {
    const baseVersion = typeof record.baseVersion === 'string' && record.baseVersion ? record.baseVersion : undefined
    const requiresConfirmation = record.requiresConfirmation === true
    return {
      item: record.item as T,
      ...(baseVersion ? { baseVersion } : {}),
      ...(requiresConfirmation ? { requiresConfirmation: true } : {}),
    }
  }
  return isItem(record) ? { item: record as T } : null
}

/**
 * 4xx 代表版本冲突、编辑锁、权限或载荷校验等确定性拒绝；重试同一份本地快照
 * 不会恢复成功，只会重复请求。网络错误和 5xx 由 queue 的显式 retry 策略短退避，
 * 绝不能用新 GET 版本替旧 payload 自动重放。
 */
function checklistErrorStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object') return null
  const candidate = error as { status?: unknown; response?: { status?: unknown } }
  const rawStatus = candidate.response?.status ?? candidate.status
  const status = typeof rawStatus === 'number'
    ? rawStatus
    : (typeof rawStatus === 'string' && /^\d+$/.test(rawStatus) ? Number(rawStatus) : NaN)
  return Number.isInteger(status) ? status : null
}

/** 401/403 是身份或项目权限边界，本地草稿不能在该会话中恢复到界面。 */
export function isChecklistDraftAccessDenied(error: unknown): boolean {
  const status = checklistErrorStatus(error)
  return status === 401 || status === 403
}

export function isNonRetryableChecklistSaveError(error: unknown): boolean {
  const status = checklistErrorStatus(error)
  return status !== null && status >= 400 && status < 500
}

/**
 * 渐进式 checklist CAS 客户端。
 *
 * 版本只取服务端 GET/PUT 回执，不自行生成。严格请求更新既有行却没有版本时，后端会
 * 返回 428；这里不偷偷补一次 GET，因为那会把“本地是基于哪一版编辑的”改写成当前版。
 */
export function createChecklistCasClient(put: ChecklistPut = api.put): {
  remember(source: unknown): void
  version(itemId: string): string | undefined
  save(input: ChecklistCasSaveInput): Promise<unknown>
} {
  const versions = new Map<string, string>()

  function remember(source: unknown): void {
    for (const item of sourceItems(source)) {
      const version = versionOf(item)
      if (version) versions.set(item.item_id, version)
    }
  }

  async function save(input: ChecklistCasSaveInput): Promise<unknown> {
    const items = input.items.map((item) => {
      const version = versions.get(item.item_id) ?? versionOf(item)
      if (version) versions.set(item.item_id, version)
      return {
        item_id: item.item_id,
        conclusion: item.conclusion ?? null,
        remark: item.remark ?? null,
        // `undefined` 表示此编辑器没有该字段，不能把既有交叉引用清成 null；
        // 显式 null 仍是用户要求清空 wp_ref 的唯一 wire 形态。
        ...(item.wp_ref !== undefined ? { wp_ref: item.wp_ref } : {}),
        ...(version ? { if_match: version } : {}),
      }
    })
    const body: Record<string, unknown> = {
      items,
      require_if_match: true,
    }
    if (input.projectId) body.project_id = input.projectId
    const result = await put(
      `/api/workpapers/${input.wpId}/checklist-responses`,
      body,
      { _dedupe: false, ...(input.config ?? {}) } as AxiosRequestConfig,
    )
    remember(result)
    return result
  }

  return {
    remember,
    version: (itemId: string) => versions.get(itemId),
    save,
  }
}
