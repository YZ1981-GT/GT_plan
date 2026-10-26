/**
 * 程序表控制台的行级控制（spec procedure-trim-generation-delegation-chain 需求 6 / 7）。
 *
 * - 行归属：`GET /api/workpapers/{wpId}/program-row-access` —— 本人能改哪些行（受限用户只能改派给自己的行，
 *   其余只读并显示执行人）、能否裁剪（只有项目委派人：经理 / 合伙人 / admin）。读不到时按原行为放开，
 *   服务端保存时按同一判定合并兜底，并回报没有生效的程序号（`ignoredProgramsText`）。
 * - 按行裁剪 / 恢复：先调细裁接口落到程序行任务（委派与可见性都认它），成功后调用方才改页面状态；失败不改并提示。
 *   没有任务又不是模板程序的行（如自加的行）服务端回 422 `row_trim_unsupported` —— 这种行本就委派不了，
 *   只在页面上标记，按成功处理。宿主没传程序表页名时定位不到任务，同样只在页面上标记（与改前相同）。
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
  const ownNos = computed(() => new Set((access.value?.own_program_nos ?? []).map(String)))
  const fullPower = computed(() => !access.value || access.value.full_power)
  const canTrim = computed(() => !access.value || access.value.can_trim)

  async function loadAccess(): Promise<void> {
    access.value = null
    const wpId = ctx.wpId()
    const sheetName = ctx.sheetName()
    if (!wpId || !sheetName) return
    try {
      const got = await getProgramRowAccess(wpId, sheetName)
      if (ctx.wpId() === wpId && ctx.sheetName() === sheetName) access.value = got
    } catch {
      access.value = null // 读不到按原行为放开，服务端保存时兜底
    }
  }

  const canEditRow = (row: ProgramRowRef): boolean => fullPower.value || ownNos.value.has(String(row.program_no))
  const assigneeOf = (row: ProgramRowRef): string => access.value?.assignees?.[String(row.program_no)] || ''

  /** 逐行调细裁接口；返回已生效（含只在页面上标记）的程序号，失败的逐条提示。 */
  async function applyRows(action: 'trim' | 'restore', rows: ProgramRowRef[], reason?: string): Promise<Set<string>> {
    const done = new Set<string>()
    const failed: string[] = []
    if (!ctx.wpId() || !ctx.sheetName()) {
      // 宿主没传程序表页名（A10~A17 / B 类汇总包内嵌的控制台）⇒ 定位不到程序行任务，与改前一样只在页面上标记
      rows.forEach((row) => done.add(String(row.program_no)))
      return done
    }
    for (const row of rows) {
      const no = String(row.program_no)
      try {
        await setProgramRowApplicability(ctx.projectId(), ctx.wpId(), action, {
          sheet_name: ctx.sheetName(), program_no: no, reason, request_id: newRequestId(),
        })
        done.add(no)
      } catch (e: any) {
        if (action === 'trim' && isPageOnlyRow(e)) done.add(no)
        else failed.push(`第 ${no} 条：${rowTrimErrorText(e)}`)
      }
    }
    if (failed.length) ElMessage.warning(`${action === 'trim' ? '裁剪' : '恢复'}没有生效 —— ${failed.join('；')}`)
    return done
  }

  return { access, fullPower, canTrim, canEditRow, assigneeOf, loadAccess, applyRows }
}
