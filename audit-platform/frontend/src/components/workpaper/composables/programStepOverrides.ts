/**
 * 循环底稿「回填程序表」统一写入（G8~G12 原来各写一份）—— spec audit-year-calendar-fallback-ratchet R0 / 任务 0.3
 *
 * 写读必须同一个 (scope, 年度)：读取方（render-config `a-program-console` 生成分支）按表码 scope + 项目审计年度读。
 * 原写法拿整张表名当 scope（「其他权益工具投资实质性程序表G8A」）、年度缺省取今年 ⇒ 回填的「已完成」刷新后一条都看不到。
 * - scope：`procedure_table:` + 表码（`extractCycleProcedureSheetCode`，与循环程序表壳传给控制台的 sheetName 同源）
 * - 年度：调用方传了有效年度就用（组件的 year 来自 render-config 的审计年度）；没传按项目审计年度现取，取不到 ⇒ 不写、提示、返回 0
 */
import { extractCycleProcedureSheetCode } from './cycleProcedureSheets'
import { parseAuditYear } from '@/utils/resolveAuditYear'

// 请求相关模块按需加载（同原各 markGxA 函数）：这些 helper 文件的纯函数在单测里大量直接 import

export async function writeProgramStepOverrides(opts: {
  projectId: string
  year?: number | null
  /** 程序表表名或表码 */
  sheet: string
  programNos: readonly number[]
  status: string
  linkedWorkpapers?: string
  executionSummary?: string
}): Promise<number> {
  if (!opts.projectId || !opts.programNos.length) return 0
  const code = extractCycleProcedureSheetCode(opts.sheet)
  if (!code) {
    console.warn('[programStepOverrides] 不是已登记的循环程序表，未回填：', opts.sheet)
    return 0
  }
  let year = parseAuditYear(opts.year)
  if (year == null) {
    const { requireProjectAuditYear } = await import('@/composables/useProjectAuditYear')
    year = await requireProjectAuditYear(opts.projectId, '回填程序表')
  }
  if (year == null) return 0
  const { api } = await import('@/services/apiProxy')
  const { ElMessage } = await import('element-plus')
  const scope = `procedure_table:${code}`
  const items = buildProgramStepOverrideItems(scope, opts)
  // 批量端点：一次请求一次提交，不能写的项逐条回报（spec procedure-chain-hardening-and-java-contracts R8：
  // 原先逐字段单发、失败静默吞掉 ⇒ 403「只能填写派给本人的程序行」用户完全看不到）
  const saved: Array<{ field: string }> = []
  const failed: Array<{ item_key: string; reason: string }> = []
  for (let i = 0; i < items.length; i += OVERRIDE_BATCH_SIZE) {
    try {
      const res: any = await api.post('/api/workpapers/field-overrides/batch', {
        project_id: opts.projectId, year, items: items.slice(i, i + OVERRIDE_BATCH_SIZE),
      }, { _silent: true } as any)
      saved.push(...(res?.saved ?? []))
      failed.push(...(res?.failed ?? []))
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      ElMessage.warning(`回填程序表失败：${typeof detail === 'string' && detail ? detail : '请稍后重试'}`)
      return saved.filter((s) => s.field === 'status').length
    }
  }
  if (failed.length) {
    const shown = failed.slice(0, 3).map((f) => `第 ${f.item_key} 条：${f.reason}`).join('；')
    ElMessage.warning(`回填程序表有 ${failed.length} 项没有写入 —— ${shown}${failed.length > 3 ? ' 等' : ''}`)
  }
  return saved.filter((s) => s.field === 'status').length
}

/** 后端单次批量上限 200（`wp_field_overrides.MAX_BATCH_ITEMS`） */
export const OVERRIDE_BATCH_SIZE = 200

/** 每个程序号：状态（必写）+ 关联底稿 / 执行说明（有值才写）。 */
export function buildProgramStepOverrideItems(scope: string, opts: {
  programNos: readonly number[]
  status: string
  linkedWorkpapers?: string
  executionSummary?: string
}): Array<{ scope: string; item_key: string; field: string; value: unknown }> {
  return opts.programNos.flatMap((programNo) => {
    const item_key = String(programNo)
    const list: Array<{ scope: string; item_key: string; field: string; value: unknown }> = [
      { scope, item_key, field: 'status', value: opts.status },
    ]
    if (opts.linkedWorkpapers) list.push({ scope, item_key, field: 'linked_workpapers', value: opts.linkedWorkpapers })
    if (opts.executionSummary) list.push({ scope, item_key, field: 'execution_summary', value: opts.executionSummary })
    return list
  })
}
