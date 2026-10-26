/**
 * 程序表字段覆盖（状态 / 执行说明）的写入位置 —— spec audit-year-calendar-fallback-ratchet R0 / 任务 0.3
 *
 * 写读必须同一个 (scope, 年度)。读取方是 render-config `a-program-console` 生成分支：按表码 scope + 项目审计年度读，
 * 并在 html_data 里回传 `override_scope`。原写法「sheetName 拼 scope + 路由年度 → 今年」两头都对不上，执行人改的状态 /
 * 执行说明刷新后看不到。
 * - scope：html_data / 自加载结果的 `override_scope` → 按表名解析循环程序表码（与循环程序表壳同一函数）→ 调用方给的固定表码 → 都没有不写
 * - 年度：项目审计年度（useProjectAuditYear），取不到不写
 */
import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useProjectAuditYear } from '@/composables/useProjectAuditYear'
import { extractCycleProcedureSheetCode } from '@/components/workpaper/composables/cycleProcedureSheets'

export const PROGRAM_OVERRIDE_SCOPE_PREFIX = 'procedure_table:'
export const UNKNOWN_SCOPE_MESSAGE = '无法确定程序表的保存位置，本次修改未保存，请刷新页面后重试'

export function useProgramOverrideTarget(opts: {
  projectId: MaybeRefOrGetter<string>
  /** 当前 html_data（render-config 回传 override_scope） */
  htmlData: () => { override_scope?: string | null } | null | undefined
  /** 表名或表码（循环程序表壳传的是表码） */
  sheetName?: () => string | null | undefined
  /** A1 / A2 / A3 这类不靠表名解析的固定表码 */
  fallbackCode?: () => string | null | undefined
}) {
  const scope = ref('')
  // 只采纳、不清空：整表保存回写的 html_data 可能不带 override_scope
  watch(() => opts.htmlData()?.override_scope, (v) => { if (v) scope.value = v }, { immediate: true })

  /** 自加载拿到的 render-config 结果里有 override_scope 时采纳 */
  function adoptScope(value?: string | null): void {
    if (value) scope.value = value
  }

  function resolveScope(): string {
    if (scope.value) return scope.value
    const code = extractCycleProcedureSheetCode(opts.sheetName?.() || '') || opts.fallbackCode?.() || ''
    return code ? `${PROGRAM_OVERRIDE_SCOPE_PREFIX}${code}` : ''
  }

  const { ensureAuditYear, requireAuditYear } = useProjectAuditYear(opts.projectId)

  /** 写一个字段：位置或年度取不到 ⇒ 不发请求、已提示，返回 false；请求失败照常抛给调用方 */
  async function writeField(programNo: number | string, field: string, value: unknown): Promise<boolean> {
    const target = resolveScope()
    if (!target) {
      ElMessage.warning(UNKNOWN_SCOPE_MESSAGE)
      return false
    }
    const year = await requireAuditYear()
    if (year == null) return false
    await api.post('/api/workpapers/field-overrides', {
      project_id: toValue(opts.projectId),
      year,
      scope: target,
      item_key: String(programNo),
      field,
      value,
    })
    return true
  }

  return { overrideScope: scope, adoptScope, resolveScope, ensureAuditYear, requireAuditYear, writeField }
}
