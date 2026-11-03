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
        wp_ref: item.wp_ref ?? null,
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
