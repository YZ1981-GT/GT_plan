/**
 * useQueryRowLinks.ts — 业务视图结果行的「打开」与「复制引用」（advanced-query-linkage-closure 任务 28 / 29；R7.1~R7.3、R7.5）
 *
 * 弹窗与页面版共用，规则都在 `queryResultLinks.ts`（ADR-AQL-01 / 18 的唯一实现），这里只把它们接到一页结果上：
 * - 「打开」：`buildRowDrill` 按数据源键映射到权威页面，新标签打开（`openRowDrill`，不加 noopener）；打不开给原因。
 * - 「复制引用」：试算表 TB、报表 ROW、附注 NOTE（行标签取该表首列、取值列取第二列）、底稿格 WP；每页结果出来后整页批量
 *   校验一次（`validatePageRefs`，带响应 `meta.ref_context` 的准则类型），校验通过才可复制，不可用时显示原因。
 * 结果只读：这里没有任何回写入口（ADR-AQL-02）。上下文（数据源、项目、年度）取本次结果所属的查询，不取界面当前选择。
 */
import { copyText } from '@/utils/clipboard'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  buildFormulaRef, buildRowDrill, openRowDrill, validatePageRefs, type RefCheck, type RowDrill,
} from './queryResultLinks'

type Row = Record<string, unknown>

/** 附注章节表结果的固定前三列（后端 `fetchers.disclosure.NOTE_BASE_COLUMNS`），之后才是该表表头 */
export const NOTE_BASE_COLUMNS: ReadonlySet<string> = new Set(['note_section', 'section_title', 'table_name'])

export interface QueryRowLinkContext {
  /** 本次结果所属的数据源键 */
  source: () => string
  projectId: () => string | null | undefined
  year: () => number | null | undefined
  columns: () => readonly string[]
  /** 响应 `meta.ref_context.template_type`（缺省时由地址库按项目判定） */
  templateType: () => string | null | undefined
  /** 附注表格当前是该章节第几张表 */
  tableIndex?: () => number | null | undefined
}

export function useQueryRowLinks(ctx: QueryRowLinkContext) {
  const router = useRouter()
  const refChecks = ref<Map<string, RefCheck>>(new Map())
  const refsPending = ref(false)
  let round = 0

  function drillOf(row: Row): RowDrill | null {
    return buildRowDrill({
      kind: 'source', key: ctx.source(), projectId: ctx.projectId(), year: ctx.year(), tableIndex: ctx.tableIndex?.(),
    }, row)
  }

  /** 附注表格：行标签列 = 表头第一列，引用取值列 = 表头第二列 */
  function noteKeys(): [string | undefined, string | undefined] {
    const keys = ctx.columns().filter((c) => !NOTE_BASE_COLUMNS.has(c))
    return [keys[0], keys[1]]
  }

  function refOf(row: Row): string | null {
    const source = ctx.source()
    if (source.startsWith('disclosure_note:')) {
      const [labelKey, valueKey] = noteKeys()
      return buildFormulaRef(source, row, valueKey, { labelKey })
    }
    return buildFormulaRef(source, row)
  }

  /** 本页引用整页批量校验（每页结果出来后调用一次；过期轮次的回包丢弃） */
  async function validateRefs(rows: readonly Row[]): Promise<void> {
    const mine = ++round
    refChecks.value = new Map()
    const refs = rows.map(refOf)
    if (!refs.some(Boolean)) {
      refsPending.value = false
      return
    }
    refsPending.value = true
    const checks = await validatePageRefs(refs, {
      projectId: ctx.projectId(), year: ctx.year(), templateType: ctx.templateType(),
    })
    if (mine !== round) return
    refChecks.value = checks
    refsPending.value = false
  }

  function refUsable(row: Row): boolean {
    const r = refOf(row)
    return !!r && !refsPending.value && !!refChecks.value.get(r)?.ok
  }

  function refHint(row: Row): string {
    const r = refOf(row)
    if (!r) return ''
    const check = refsPending.value ? undefined : refChecks.value.get(r)
    if (!check) return '正在校验引用…'
    return check.ok ? `复制 ${r}` : (check.reason || '该引用不可用')
  }

  async function copyRef(row: Row): Promise<void> {
    const r = refOf(row)
    if (!r || !refUsable(row)) return
    try {
      await copyText(r)
      ElMessage.success(`已复制引用 ${r}`)
    } catch {
      ElMessage.warning(`复制失败，请手动复制：${r}`)
    }
  }

  async function openRow(row: Row): Promise<void> {
    const drill = drillOf(row)
    if (!drill) return
    const reason = await openRowDrill(drill, router)
    if (reason) ElMessage.warning(reason)
  }

  function reset(): void {
    round += 1
    refChecks.value = new Map()
    refsPending.value = false
  }

  return { drillOf, refOf, refUsable, refHint, copyRef, openRow, validateRefs, reset, refsPending }
}
