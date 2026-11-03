/**
 * 汇总表行的函证附件计数 + 附件抽屉状态（spec attachment-confirmation-evidence-loop 需求 1.1、1.2，ADR-ACE-01）
 *
 * 计数来自函证中心列表接口（每条带 `outbound_count` / `inbound_count`），按行上的 `_hub_confirmation_id` 对应。
 * 汇总表挂载时 `_backflowFromHub` 已经取过一次列表 ⇒ 用 `ingest` 复用那份结果，不再另发同一个 GET
 * （同 URL 并发时 http 的 GET 去重会取消先发的那一个）；抽屉里有改动 / 同步到函证中心之后 `reload`（不去重）。
 */
import { reactive, ref } from 'vue'
import http from '@/utils/http'

export interface HubAttachmentCount {
  outbound: number
  inbound: number
}

export interface HubCountRow {
  _hub_confirmation_id?: string
  entity_name?: string
}

export function useHubAttachmentCounts(projectId: () => string | null | undefined) {
  const counts = ref<Record<string, HubAttachmentCount>>({})

  function ingest(items: ReadonlyArray<Record<string, any>> | null | undefined): void {
    const next: Record<string, HubAttachmentCount> = {}
    for (const it of items ?? []) {
      if (!it?.id) continue
      next[String(it.id)] = { outbound: Number(it.outbound_count) || 0, inbound: Number(it.inbound_count) || 0 }
    }
    counts.value = next
  }

  async function reload(): Promise<void> {
    const pid = projectId()
    if (!pid) return
    try {
      const res: any = await http.get(`/api/projects/${pid}/confirmations`, { _silent: true, _dedupe: false } as any)
      ingest(res?.data?.items ?? res?.items ?? [])
    } catch {
      // 计数取不到不影响编制：保留上一次的计数
    }
  }

  const drawer = reactive({ visible: false, confirmationId: '', counterparty: '' })

  /** 只对已同步到函证中心的行打开（未同步的行没有函证可挂） */
  function open(row: HubCountRow): void {
    if (!row?._hub_confirmation_id) return
    drawer.confirmationId = row._hub_confirmation_id
    drawer.counterparty = row.entity_name || ''
    drawer.visible = true
  }

  return { counts, ingest, reload, drawer, open }
}
