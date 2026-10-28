/**
 * 程序表控制台的行级控制（spec procedure-trim-generation-delegation-chain 需求 6 / 7）。
 *
 * - 行归属：`GET /api/workpapers/{wpId}/program-row-access` —— 本人能改哪些行（受限用户只能改派给自己的行，
 *   其余只读并显示执行人）、能否裁剪（只有项目委派人：经理 / 合伙人 / admin）。读到之前 / 读不到时整表只读
 *   并给出原因与重试（`accessState`；原先读不到按全权放开，spec procedure-chain-hardening-and-java-contracts R7）。
 *   服务端保存时按同一判定合并兜底，并回报没有生效的程序号（`ignoredProgramsText`）。
 * - 按行裁剪 / 恢复：先调细裁接口落到程序行任务（委派与可见性都认它），成功后调用方才改页面状态；失败不改并提示。
 *   没有任务又不是模板程序的行（如自加的行）服务端回 422 `row_trim_unsupported` —— 这种行本就委派不了，
 *   只在页面上标记、按成功处理，并提示「仅页面标记，未写入任务」。没有页名（整册嵌入的控制台）照常请求，
 *   服务端按底稿编码定位程序表（R6）。恢复回执带原执行人（恢复后须重新委派，R4）。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getProgramRowAccess, setProgramRowApplicability, type ProgramRowAccess } from '@/services/commonApi'
import { newRequestId } from '@/components/workpaper/composables/procedureConsoleOverlay'

export interface ProgramRowRef {
  program_no: number | string
}

export const ROW_TRIM_UNSUPPORTED = 'row_trim_unsupported'

function errorStatus(e: any): number | undefined {
  return e?.response?.status ?? e?.status
}

function errorDetail(e: any): any {
  return e?.response?.data?.detail ?? e?.response?.data?.data?.detail ?? e?.data?.detail
}

/** 只能在页面上标记的行（没有程序行任务、也不是模板程序）。 */
export function isPageOnlyRow(e: any): boolean {
  return errorStatus(e) === 422 && errorDetail(e)?.error === ROW_TRIM_UNSUPPORTED
}

/** 按行裁剪 / 恢复失败的人话。 */
export function rowTrimErrorText(e: any): string {
  if (errorStatus(e) === 403) return '只有项目经理 / 合伙人可以裁剪或恢复程序'
  const d = errorDetail(e)
  if (typeof d === 'string' && d) return d
  if (d && typeof d === 'object' && d.message) return String(d.message)
  return '请求失败，请稍后重试'
}

/** 行归属读不到的人话（读不到时整表只读）。 */
export function rowAccessErrorText(e: any): string {
  const status = errorStatus(e)
  if (status === 403 || status === 404) return '没有这张底稿的访问权限'
  const d = errorDetail(e)
  return typeof d === 'string' && d ? d : '网络或服务异常'
}

/** 按行裁剪 / 恢复的结果。 */
export interface RowApplyResult {
  /** 已生效的程序号（含只在页面上标记的） */
  done: Set<string>
  /** 其中只在页面上标记、没写入程序行任务的 */
  pageOnly: Set<string>
  /** 恢复：原执行人姓名（恢复后执行人清空，须重新委派） */
  previousAssignees: string[]
  /** 恢复：有任务回到待委派 */
  requiresReassign: boolean
}

/** 行归属读取状态：idle = 没有底稿（没有可写的服务端，不限制）；loading / error 时整表只读。 */
export type RowAccessState = 'idle' | 'loading' | 'ready' | 'error'

/** `/save` 回执里没有生效的程序号 → 提示文案（没有返回空串）。 */
export function ignoredProgramsText(nos: unknown): string {
  const list = Array.isArray(nos) ? nos.map((n) => String(n)).filter(Boolean) : []
  if (!list.length) return ''
  return `第 ${list.join('、')} 条程序的修改没有保存：只能修改派给自己的程序行，裁剪 / 恢复须由项目经理或合伙人操作`
}

/** HTML 保存通道（WorkpaperEditor）用：回执里有没生效的程序号就提示，免得用户以为都存上了
 *  （程序表里非本人行 / 非委派人的裁剪恢复，服务端保留原值并回报程序号）。 */
export function warnIgnoredPrograms(res: any): void {
  const text = ignoredProgramsText(res?.ignored_program_nos)
  if (text) ElMessage.warning(text)
}

export function useProgramRowControl(ctx: {
  projectId: () => string
  wpId: () => string
  sheetName: () => string
}) {
  const access = ref<ProgramRowAccess | null>(null)
  const accessState = ref<RowAccessState>('idle')
  const accessError = ref('')
  let loadSeq = 0
  const ownNos = computed(() => new Set((access.value?.own_program_nos ?? []).map(String)))
  const ready = computed(() => accessState.value === 'ready' && !!access.value)
  const fullPower = computed(() => accessState.value === 'idle' || (ready.value && !!access.value?.full_power))
  const canTrim = computed(() => accessState.value === 'idle' || (ready.value && !!access.value?.can_trim))

  async function loadAccess(): Promise<void> {
    const seq = ++loadSeq
    access.value = null
    accessError.value = ''
    const wpId = ctx.wpId()
    const sheetName = ctx.sheetName()
    if (!wpId) { accessState.value = 'idle'; return }
    accessState.value = 'loading'
    const stale = () => seq !== loadSeq || ctx.wpId() !== wpId || ctx.sheetName() !== sheetName
    try {
      const got = await getProgramRowAccess(wpId, sheetName) // 页名为空 ⇒ 服务端按底稿编码定位程序表
      if (stale()) return
      access.value = got
      accessState.value = 'ready'
    } catch (e: any) {
      if (stale()) return
      accessState.value = 'error'
      accessError.value = rowAccessErrorText(e)
    }
  }

  // 读到之前 / 读不到时 access 为空 ⇒ ownNos 为空 ⇒ 只有 idle（没有底稿）放开
  const canEditRow = (row: ProgramRowRef): boolean => fullPower.value || ownNos.value.has(String(row.program_no))
  const assigneeOf = (row: ProgramRowRef): string => access.value?.assignees?.[String(row.program_no)] || ''

  /** 逐行调细裁接口；失败的逐条提示，只在页面上标记的另行提示。 */
  async function applyRows(action: 'trim' | 'restore', rows: ProgramRowRef[], reason?: string): Promise<RowApplyResult> {
    const result: RowApplyResult = { done: new Set(), pageOnly: new Set(), previousAssignees: [], requiresReassign: false }
    const wpId = ctx.wpId()
    if (!wpId) { // 没有底稿 ⇒ 没有可写的程序行任务，与改前一样只在页面上标记
      rows.forEach((row) => { result.done.add(String(row.program_no)); result.pageOnly.add(String(row.program_no)) })
      return result
    }
    const failed: string[] = []
    for (const row of rows) {
      const no = String(row.program_no)
      try {
        const res = await setProgramRowApplicability(ctx.projectId(), wpId, action, {
          sheet_name: ctx.sheetName() || '', program_no: no, reason, request_id: newRequestId(),
        })
        result.done.add(no)
        if (res?.requires_reassign) result.requiresReassign = true
        for (const name of res?.previous_assignees ?? []) {
          if (name && !result.previousAssignees.includes(name)) result.previousAssignees.push(name)
        }
      } catch (e: any) {
        if (action === 'trim' && isPageOnlyRow(e)) { result.done.add(no); result.pageOnly.add(no) }
        else failed.push(`第 ${no} 条：${rowTrimErrorText(e)}`)
      }
    }
    const verb = action === 'trim' ? '裁剪' : '恢复'
    if (failed.length) ElMessage.warning(`${verb}没有生效 —— ${failed.join('；')}`)
    if (result.pageOnly.size) {
      ElMessage.info(`第 ${[...result.pageOnly].join('、')} 条仅页面标记，未写入任务：这一行没有程序行任务（如自加的行），委派与可见性看不到这次${verb}`)
    }
    return result
  }

  return { access, accessState, accessError, fullPower, canTrim, canEditRow, assigneeOf, loadAccess, applyRows }
}

/** 恢复执行成功后的提示（原执行人已清除，须重新委派）。 */
export function restoredRowText(result: Pick<RowApplyResult, 'previousAssignees' | 'requiresReassign'>): string {
  if (!result.requiresReassign) return '已恢复执行'
  const who = result.previousAssignees.length ? `（原执行人：${result.previousAssignees.join('、')}）` : ''
  return `已恢复执行，原执行人已清除${who}，请重新委派`
}
