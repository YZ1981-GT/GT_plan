/**
 * useWpEvidenceLinks — 按（项目, 底稿）共享的证据链接仓（spec attachment-evidence-intake ADR-AEI-08）
 *
 * 一张底稿上可能挂几十个 ItemAttachment（表格每行一个）。每个实例各发一次列表请求既浪费，
 * 同 URL 并发 GET 还会被 http 去重取消先发的那个 ⇒ 这里按底稿只发一次（单飞），请求带 `_dedupe: false`。
 *
 * - 链接行带附件元数据（后端 GET …/evidence 已 join 附件，附件软删的不返回）
 * - 上传 / 移除后调 `invalidateWpEvidenceLinks`：纪元 +1，旧纪元的在途结果不回写；有使用方才立即重取
 */
import { computed, onScopeDispose, reactive, toValue, watch, type MaybeRefOrGetter } from 'vue'
import http from '@/utils/http'
import { attachments as P_att } from '@/services/apiPaths'

export interface EvidenceAttachmentBrief {
  id: string
  file_name: string
  file_size: number | null
  file_type: string | null
  attachment_type: string | null
  ocr_status: string | null
  created_at: string | null
}

export interface WpEvidenceLink {
  id: string
  wp_id: string
  sheet_name: string | null
  cell_ref: string | null
  attachment_id: string
  page_ref: string | null
  evidence_type: string | null
  check_conclusion: string | null
  /** 凭证键规范串（凭证检查行的原件按凭证身份挂，spec attachment-voucher-evidence-binding）；旧链接为 null */
  voucher_key?: string | null
  created_by: string
  created_at: string | null
  attachment: EvidenceAttachmentBrief
}

/** 一张凭证在本底稿的一份证据（同一附件的全部链接） */
export interface VoucherEvidenceGroup {
  attachmentId: string
  attachment: EvidenceAttachmentBrief
  links: WpEvidenceLink[]
}

interface Slot {
  links: WpEvidenceLink[]
  loaded: boolean
  loading: boolean
  error: boolean
  /** 失效纪元：每次失效 +1，旧纪元的在途结果不回写 */
  epoch: number
  /** 正在使用本仓的组件数（为 0 时失效只标记，不立即重取） */
  users: number
}

const slots = reactive(new Map<string, Slot>()) as Map<string, Slot>
const inflight = new Map<string, { epoch: number; promise: Promise<WpEvidenceLink[]> | null }>()

const keyOf = (projectId: string, wpId: string) => `${projectId}::${wpId}`

function slotOf(key: string): Slot {
  if (!slots.has(key)) {
    slots.set(key, { links: [], loaded: false, loading: false, error: false, epoch: 0, users: 0 })
  }
  return slots.get(key) as Slot
}

function normalizeLinks(raw: unknown): WpEvidenceLink[] {
  const body = (raw ?? {}) as { items?: unknown }
  const items = Array.isArray(raw) ? raw : Array.isArray(body.items) ? body.items : []
  return (items as WpEvidenceLink[]).filter(
    (row) => !!row && !!row.id && !!row.attachment_id && !!row.attachment,
  )
}

/** 取本底稿证据链接；已加载且未失效直接返回缓存，同一纪元的并发调用共用一次请求。 */
export function loadWpEvidenceLinks(
  projectId: string,
  wpId: string,
  opts: { force?: boolean } = {},
): Promise<WpEvidenceLink[]> {
  if (!projectId || !wpId) return Promise.resolve([])
  const key = keyOf(projectId, wpId)
  const slot = slotOf(key)
  if (slot.loaded && !opts.force) return Promise.resolve(slot.links)
  const running = inflight.get(key)
  if (running?.promise && running.epoch === slot.epoch && !opts.force) return running.promise
  const epoch = slot.epoch
  const entry: { epoch: number; promise: Promise<WpEvidenceLink[]> | null } = { epoch, promise: null }
  inflight.set(key, entry)
  slot.loading = true
  entry.promise = (async () => {
    try {
      const res = await http.get(P_att.evidenceLinks(projectId, wpId), { _dedupe: false, _silent: true } as any)
      const links = normalizeLinks(res?.data)
      if (slot.epoch === epoch) {
        slot.links = links
        slot.loaded = true
        slot.error = false
      }
      return links
    } catch (err) {
      if (slot.epoch === epoch) slot.error = true
      throw err
    } finally {
      if (inflight.get(key) === entry) inflight.delete(key)
      if (slot.epoch === epoch) slot.loading = false
    }
  })()
  return entry.promise
}

/** 本底稿链接已变（上传 / 移除 / 解除关联）：有使用方立即重取，否则下次使用时再取。 */
export function invalidateWpEvidenceLinks(projectId: string, wpId: string): Promise<WpEvidenceLink[]> {
  if (!projectId || !wpId) return Promise.resolve([])
  const slot = slotOf(keyOf(projectId, wpId))
  slot.epoch += 1
  slot.loaded = false
  if (slot.users <= 0) return Promise.resolve([])
  return loadWpEvidenceLinks(projectId, wpId)
}

/** 删除一条证据链接（不删附件），随后让本底稿的仓重取。 */
export async function removeWpEvidenceLink(projectId: string, wpId: string, linkId: string): Promise<void> {
  await http.delete(P_att.evidenceLink(projectId, wpId, linkId), { _silent: true } as any)
  await invalidateWpEvidenceLinks(projectId, wpId).catch(() => [])
}

/** 测试用：清空全部缓存与在途记录。 */
export function resetWpEvidenceLinksForTest(): void {
  slots.clear()
  inflight.clear()
}

export function useWpEvidenceLinks(projectId: MaybeRefOrGetter<string>, wpId: MaybeRefOrGetter<string>) {
  const key = computed(() => {
    const pid = toValue(projectId)
    const wid = toValue(wpId)
    return pid && wid ? keyOf(pid, wid) : ''
  })
  let held = ''
  const release = () => {
    if (!held) return
    const slot = slots.get(held)
    if (slot) slot.users = Math.max(0, slot.users - 1)
    held = ''
  }
  watch(
    key,
    (next) => {
      if (next === held) return
      release()
      if (!next) return
      slotOf(next).users += 1
      held = next
      void loadWpEvidenceLinks(toValue(projectId), toValue(wpId)).catch(() => [])
    },
    { immediate: true },
  )
  onScopeDispose(release)

  const slot = computed(() => (key.value ? slots.get(key.value) ?? null : null))
  const links = computed<WpEvidenceLink[]>(() => slot.value?.links ?? [])
  const loading = computed(() => !!slot.value?.loading)
  const error = computed(() => !!slot.value?.error)

  /** 某个位置（表页 + 单元格 / 行槽位）上的链接；两者都按原值精确匹配。 */
  function linksAt(sheetName: string | null | undefined, cellRef: string | null | undefined): WpEvidenceLink[] {
    const sheet = sheetName ?? null
    const cell = cellRef ?? null
    return links.value.filter((row) => (row.sheet_name ?? null) === sheet && (row.cell_ref ?? null) === cell)
  }

  /**
   * 本底稿上某张凭证的证据，按附件归组（任何位置：本行识别、同一凭证另一行、凭证级上传与引用都算）。
   * 同一附件可能挂在多个位置（每组的 `links`），移除时整组删。
   */
  function voucherEvidenceOf(voucherKey: string | null | undefined): VoucherEvidenceGroup[] {
    if (!voucherKey) return []
    const groups = new Map<string, VoucherEvidenceGroup>()
    for (const row of links.value) {
      if (row.voucher_key !== voucherKey) continue
      const group = groups.get(row.attachment_id)
      if (group) group.links.push(row)
      else groups.set(row.attachment_id, { attachmentId: row.attachment_id, attachment: row.attachment, links: [row] })
    }
    return [...groups.values()]
  }

  return {
    links,
    loading,
    error,
    linksAt,
    voucherEvidenceOf,
    reload: () => invalidateWpEvidenceLinks(toValue(projectId), toValue(wpId)),
  }
}
