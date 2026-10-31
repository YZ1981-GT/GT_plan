/**
 * 序时账「已挂 / 已抽」标识（spec voucher-identity-writeback-and-audit-phase 任务 14，需求 5.2，design §5）
 *
 * 明细层（含序时账 Tab、辅助明细）与凭证层按行上的凭证键批量查这张凭证已挂或已抽于哪些底稿：
 * 底稿编码、来源（挂凭 / 抽凭）、阶段。明细层在日期列的标记里加一个 📎（悬停列出底稿），凭证层显示标签。
 *
 * - 行上的凭证键与后端同一实现（`voucherKeyString`，行上没有年度用当前年度）；合成行（期初、月小计）跳过。
 * - 按键缓存：查过的键（含查无记录的）不再查；一次最多 500 个键，超过分段顺序查（键里有主体名称，走请求体）。
 * - 挂凭成功后 `refresh(keys)` 只重查这几个键；切项目 / 年度清空。
 * - 竞态：每个键记「最近一次为它发起的请求」的序号，晚到的旧响应不覆盖新结果（不比时间戳，见 memory）。
 * - 查不到（网络 / 权限）只是不显示标记，不打断查账；失败的键不进缓存，下次再查。
 * - 凭证层（`linksOfKey`）另并入各可见底稿已取得的凭证证据（spec attachment-voucher-evidence-binding 需求 7，
 *   证据走凭证证据索引按需查）；明细层 📎（`flagOfRow` / `linksOfRow`）照旧只看登记。
 */
import { shallowRef, watch, type Ref } from 'vue'
import {
  queryVoucherLinks, VOUCHER_LINKS_MAX_KEYS, type VoucherLink,
} from '@/components/workpaper/composables/useAttachedVouchers'
import { AUDIT_PHASE_LABEL } from '@/composables/useProjectAuditPhase'
import { voucherEvidenceOf } from '@/composables/useVoucherEvidenceIndex'
import { normText, voucherKeyString } from '@/utils/voucherIdentity'

export type { VoucherLink }

/**
 * 凭证层标签里的「凭证证据」条目（spec attachment-voucher-evidence-binding 需求 7）：某张可见底稿已取得这张凭证的
 * 原件几份。只在凭证层（`linksOfKey`）并入，明细层 📎 照旧只看挂凭 / 抽凭登记。
 */
export interface VoucherEvidenceTag {
  working_paper_id: string
  wp_code: string | null
  wp_name: string | null
  wp_missing: false
  source: 'evidence'
  phase: null
  count: number
  legacy: false
  files: string[]
}
export type VoucherTag = VoucherLink | VoucherEvidenceTag

export const LINK_SOURCE_LABEL: Readonly<Record<VoucherTag['source'], string>> = {
  manual: '挂凭',
  sampling_engine: '抽凭',
  evidence: '凭证证据',
}

/** 「J1 应付职工薪酬 · 抽凭 ×2 · 预审」；底稿已删 / 不在本项目、没指定底稿、旧登记各有说明；证据条目列文件名 */
export function voucherLinkText(link: VoucherTag): string {
  const wp = link.wp_code
    ? `${link.wp_code}${link.wp_name && link.wp_name !== link.wp_code ? ` ${link.wp_name}` : ''}`
    : link.working_paper_id ? '底稿已删除' : '未指定底稿'
  if (link.source === 'evidence') return `${wp} · 已取得凭证证据 ${link.count} 份：${link.files.join('、')}`
  const source = `${LINK_SOURCE_LABEL[link.source] ?? link.source}${link.count > 1 ? ` ×${link.count}` : ''}`
  const phase = link.phase ? AUDIT_PHASE_LABEL[link.phase] : '阶段未标'
  return `${wp} · ${source} · ${phase}${link.legacy ? '（旧登记未记凭证字或主体，同日同号的另一张凭证也会显示）' : ''}`
}

/**
 * 行 → 凭证键；没有凭证号 / 日期的行（期初、小计等合成行）返回 null。
 * 审计年度未知（项目没填，`null`）时只认后端给的 `voucher_key`，不拼键（拼出来的键年度为空，查不到也对不上）。
 */
export function rowVoucherKey(row: Record<string, unknown> | null | undefined, year: number | null): string | null {
  if (!row || (typeof row._type === 'string' && row._type !== 'normal')) return null
  if (!normText(row.voucher_no) || !row.voucher_date) return null
  if (typeof row.voucher_key === 'string' && row.voucher_key) return row.voucher_key
  return year == null ? null : voucherKeyString(row, year)
}

export function useVoucherLinkTags(projectId: Ref<string>, year: Ref<number | null>) {
  /** 凭证键 → 已挂记录；查过但没有记录的键存空数组 */
  const links = shallowRef<Map<string, VoucherLink[]>>(new Map())
  let seq = 0
  /** 每个键最近一次为它发起的请求序号：晚到的旧响应不覆盖 */
  const latest = new Map<string, number>()

  function clear(): void {
    links.value = new Map()
    latest.clear()
    seq += 1
  }
  watch([projectId, year], clear)

  async function fetchKeys(keys: string[]): Promise<void> {
    const pid = projectId.value
    const yr = year.value
    if (yr == null) return // 项目没填审计年度：不查（已挂登记按年度存）
    for (let i = 0; i < keys.length; i += VOUCHER_LINKS_MAX_KEYS) {
      const chunk = keys.slice(i, i + VOUCHER_LINKS_MAX_KEYS)
      const mine = ++seq
      for (const k of chunk) latest.set(k, mine)
      let found: Record<string, VoucherLink[]>
      try {
        found = await queryVoucherLinks(pid, yr, chunk)
      } catch {
        for (const k of chunk) if (latest.get(k) === mine) latest.delete(k)
        continue
      }
      if (pid !== projectId.value || yr !== year.value) return
      const next = new Map(links.value)
      for (const k of chunk) {
        if (latest.get(k) === mine) next.set(k, found[k] ?? [])
      }
      links.value = next
    }
  }

  /** 给一批行补标识（已查过的键跳过） */
  async function loadForRows(rows: ReadonlyArray<Record<string, unknown>>): Promise<void> {
    const keys = new Set<string>()
    for (const row of rows) {
      const k = rowVoucherKey(row, year.value)
      if (k && !links.value.has(k) && !latest.has(k)) keys.add(k)
    }
    if (keys.size) await fetchKeys([...keys])
  }

  /** 挂凭之后重查这几个键（不论缓存） */
  async function refresh(keys: ReadonlyArray<string | null | undefined>): Promise<void> {
    const todo = [...new Set(keys.filter((k): k is string => !!k))]
    if (todo.length) await fetchKeys(todo)
  }

  function registrationsOf(key: string | null | undefined): VoucherLink[] {
    return (key && links.value.get(key)) || []
  }

  /** 凭证层标签：挂凭 / 抽凭登记 + 各可见底稿已取得的凭证证据（证据按需查，查到前只有登记） */
  function linksOfKey(key: string | null | undefined): VoucherTag[] {
    const evidence: VoucherEvidenceTag[] = voucherEvidenceOf(projectId.value, year.value, key).map((e) => ({
      working_paper_id: e.working_paper_id, wp_code: e.wp_code, wp_name: e.wp_name, wp_missing: false,
      source: 'evidence', phase: null, count: e.attachments.length, legacy: false,
      files: e.attachments.map((a) => a.file_name),
    }))
    return [...registrationsOf(key), ...evidence]
  }

  function linksOfRow(row: Record<string, unknown> | null | undefined): VoucherLink[] {
    return registrationsOf(rowVoucherKey(row, year.value))
  }

  /** 明细层日期列的标记（与 ⚠️ 🔴 📅 同一套 { icon, tip }）；没挂没抽返回 null */
  function flagOfRow(row: Record<string, unknown> | null | undefined): { icon: string; tip: string } | null {
    const list = linksOfRow(row)
    if (!list.length) return null
    return { icon: '📎', tip: `已挂 / 已抽于：${list.map(voucherLinkText).join('；')}` }
  }

  return { links, loadForRows, refresh, clear, linksOfKey, linksOfRow, flagOfRow }
}
