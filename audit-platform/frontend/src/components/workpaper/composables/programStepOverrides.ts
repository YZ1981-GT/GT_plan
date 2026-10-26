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
  const scope = `procedure_table:${code}`
  let n = 0
  for (const programNo of opts.programNos) {
    const fields: Array<{ field: string; value: unknown }> = [{ field: 'status', value: opts.status }]
    if (opts.linkedWorkpapers) fields.push({ field: 'linked_workpapers', value: opts.linkedWorkpapers })
    if (opts.executionSummary) fields.push({ field: 'execution_summary', value: opts.executionSummary })
    for (const f of fields) {
      try {
        await api.post('/api/workpapers/field-overrides', {
          project_id: opts.projectId,
          year,
          scope,
          item_key: String(programNo),
          field: f.field,
          value: f.value,
        }, { _silent: true } as any)
        if (f.field === 'status') n += 1
      } catch { /* 单字段失败不阻断其余字段 */ }
    }
  }
  return n
}
