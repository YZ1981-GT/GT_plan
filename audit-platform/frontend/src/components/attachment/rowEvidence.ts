/**
 * 行内识别 / 上传的附件挂到「本行」（spec attachment-inline-preview ADR-AIP-03）
 *
 * 底稿识别端点（Spec B 入口 `intake_ocr_upload`）收两个可选表单字段：`evidence_sheet`（表页键）、
 * `evidence_cell`（单元格 / 行槽位）。带上它们，新建的附件只写行级证据链接，`RowEvidenceEye` 按同一位置
 * 从本底稿共享链接仓里取出来显示小眼睛。行数据本身不加字段（行数据同步到在线编辑与导出）。
 *
 * 位置键：有稳定行 id 用 `row:{id}`；行没有 id 的表用 `row:{序号}`（序号从 1 起），删行时调
 * `shiftIndexedRowEvidence` 让附件随行前移。
 */
import { toValue, type MaybeRefOrGetter } from 'vue'
import { useRoute } from 'vue-router'
import http from '@/utils/http'
import { attachments as P_att } from '@/services/apiPaths'
import { invalidateWpEvidenceLinks, loadWpEvidenceLinks } from '@/composables/useWpEvidenceLinks'

/** 行槽位：`row:{行 id}`。 */
export function rowEvidenceCell(rowKey: string | number): string {
  return `row:${rowKey}`
}

/** `row:{n}`（n 为正整数）⇒ n；其他写法 ⇒ null。 */
function indexedRowNo(cellRef: string | null | undefined): number | null {
  const m = /^row:(\d+)$/.exec(cellRef ?? '')
  return m ? Number(m[1]) : null
}

/**
 * 行没有稳定 id、按序号挂附件的表（位置 = `row:{序号}`，序号从 1 起）删掉第 `removedNo` 行之后调用：
 * 被删行的附件转为表页级（仍在本底稿附件里，不丢），其后各行的附件随行前移一位。
 * 不调整的话，删行后数据前移、附件不动，附件会显示在别的合同行上。
 * 逐条「先建新位置、再删旧位置」，单条失败不影响其余；返回失败条数（> 0 时调用方提示去右侧附件页签核对）。
 */
export async function shiftIndexedRowEvidence(
  projectId: string | null | undefined,
  wpId: string | null | undefined,
  sheetKey: string,
  removedNo: number,
): Promise<number> {
  if (!projectId || !wpId || !sheetKey || !(removedNo >= 1)) return 0
  let links
  try {
    links = await loadWpEvidenceLinks(projectId, wpId, { force: true })
  } catch {
    return 0
  }
  const affected = links
    .map((link) => ({ link, no: indexedRowNo(link.cell_ref) }))
    .filter((it): it is { link: (typeof links)[number]; no: number } =>
      (it.link.sheet_name ?? null) === sheetKey && it.no !== null && it.no >= removedNo)
    .sort((a, b) => a.no - b.no)
  if (!affected.length) return 0
  let failed = 0
  for (const { link, no } of affected) {
    try {
      await http.post(P_att.evidenceLinkCreate(projectId, wpId), {
        attachment_id: link.attachment_id,
        sheet_name: sheetKey,
        cell_ref: no === removedNo ? null : rowEvidenceCell(no - 1),
        page_ref: link.page_ref,
        evidence_type: link.evidence_type,
        check_conclusion: link.check_conclusion,
        voucher_key: link.voucher_key ?? null, // 凭证身份随行前移保留（唯一索引带位置，先建后删不相撞）
      }, { _silent: true } as any)
      await http.delete(P_att.evidenceLink(projectId, wpId, link.id), { _silent: true } as any)
    } catch {
      failed += 1
    }
  }
  await invalidateWpEvidenceLinks(projectId, wpId).catch(() => [])
  return failed
}

/**
 * 凭证检查行的凭证键（抽凭 / 挂凭写入行元数据 `_gt.vk`，spec voucher-identity-writeback-and-audit-phase）；
 * 手工行、非凭证检查行为 null。
 */
export function rowVoucherKey(row: unknown): string | null {
  const meta = (row as { _gt?: { vk?: unknown } } | null | undefined)?._gt
  return meta && typeof meta.vk === 'string' && meta.vk ? meta.vk : null
}

/**
 * 给识别 / 上传表单带上位置：表页键必填；单元格 / 行槽位可空（空 = 表页级，如「上传合同识别」这类整页一个的按钮）。
 * 超长（表页 / 单元格各 100 字）由后端 400 拒绝。
 *
 * `row` 是凭证检查行时一并带上凭证键（`evidence_voucher_key`）：原件按凭证身份挂，别的底稿抽到同一张凭证时
 * 能查到并引用；缺省证据类型随之记「凭证 / 原始单据」（spec attachment-voucher-evidence-binding ADR-AVE-04/05）。
 */
export function appendRowEvidence(form: FormData, sheetKey: string, cellRef?: string | null, row?: unknown): void {
  const voucherKey = rowVoucherKey(row)
  if (voucherKey) form.append('evidence_voucher_key', voucherKey)
  if (!sheetKey) return
  form.append('evidence_sheet', sheetKey)
  if (cellRef) form.append('evidence_cell', cellRef)
}

/** 识别 / 上传成功后：本底稿共享链接仓失效重取，同页所有行内小眼睛立即看到新文件。 */
export function refreshRowEvidence(projectId: string | null | undefined, wpId: string | null | undefined): void {
  if (!projectId || !wpId) return
  void invalidateWpEvidenceLinks(projectId, wpId).catch(() => [])
}

/** 路由里的项目 id（底稿编辑页 `projects/:projectId/workpapers/:wpId/edit`）；不在路由上下文时为空。 */
export function routeProjectId(): string {
  try {
    const raw = useRoute()?.params?.projectId
    return typeof raw === 'string' ? raw : Array.isArray(raw) ? String(raw[0] || '') : ''
  } catch {
    return ''
  }
}

/**
 * 页面 / composable 用：项目 id 缺省取路由参数（不少页面只有底稿 id）。须在 setup 中调用。
 * 返回普通函数（不返回 ref，避免模板里漏 `.value`）。
 */
export function useRowEvidence(wpId: MaybeRefOrGetter<string | null | undefined>, projectId?: MaybeRefOrGetter<string | null | undefined>) {
  const fallback = routeProjectId()
  const pid = () => toValue(projectId) || fallback
  return {
    projectId: pid,
    /** `row` 为凭证检查行时一并带凭证键（见 appendRowEvidence） */
    append: (form: FormData, sheetKey: string, cellRef?: string | null, row?: unknown) =>
      appendRowEvidence(form, sheetKey, cellRef, row),
    refresh: () => refreshRowEvidence(pid(), toValue(wpId)),
    /** 按序号挂附件的表删掉第 removedNo 行后调用（见 shiftIndexedRowEvidence）；返回失败条数 */
    shiftAfterRemove: (sheetKey: string, removedNo: number) =>
      shiftIndexedRowEvidence(pid(), toValue(wpId), sheetKey, removedNo),
  }
}
