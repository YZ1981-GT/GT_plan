/**
 * queryTemplateRestore.ts — 模板「载入」：模板 config → 查询界面状态（advanced-query-linkage-closure 任务 33；R9.4，design §4.2）
 *
 * 弹窗与页面版共用同一个模板选择组件（MyTemplatesDialog），选中的模板由本模块翻成界面状态：数据源、条件、列、排序、
 * 每页行数，以及弹窗的底稿选区 / 本页筛选、单元格取值目标（acnr_targets，用户裁决 Q0：原样带上）。
 * 项目与年度不从模板取：模板执行与查询的年度都取当前请求年度，否则目标项目审计年度（R9.3，后端 `config_to_request`
 * 同样不用模板里存的 year）。数据源缺省用模板的 `data_source`（页面版保存的 config 不含 source，原先「载入」即报配置不完整）。
 */
import type { QuerySort } from '@/components/custom-query/queryPayloads'
import { fromSavedConditions, normalizeConditionLogic, type ConditionState } from './queryConditions'

/** 结果翻页的每页行数（QueryResultPager 的档位）；模板里存的不在其中就不还原 */
export const QUERY_PAGE_SIZES: readonly number[] = [100, 200, 500]

/** `GET /api/custom-query/templates` 列表项（后端 `_serialize_template`） */
export interface QueryTemplateItem {
  id: string
  name: string
  description?: string | null
  data_source: string
  config: Record<string, unknown> | null
  scope: string
  is_owner: boolean
  created_by?: string
  created_at?: string | null
  updated_at?: string | null
  shared_project_ids?: string[]
}

export interface RestoredTemplateQuery {
  source: string
  /** 条件编辑器状态（兼容旧写法 operator / contains、大写 AND / OR） */
  condition: ConditionState
  /** 所选列（selected_columns，旧写法 columns） */
  columns: string[]
  /** 页面版保存的可选列（available_columns） */
  availableColumns: string[]
  sort: QuerySort | null
  pageSize: number | null
  cellRange: string
  sheetName: string
  filterText: string
  acnrTargets: string[]
}

function strings(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === 'string' && x !== '') : []
}

function text(raw: unknown): string {
  return typeof raw === 'string' ? raw : ''
}

/** 模板的数据源：config.source，缺省模板的 data_source */
export function templateSourceOf(tpl: Pick<QueryTemplateItem, 'config' | 'data_source'>): string {
  return text(tpl.config?.source).trim() || text(tpl.data_source).trim()
}

/** 排序：config.sort（取第一项），缺省 sort_field / sort_order（与后端 config_to_request 同一读法） */
function sortOf(cfg: Record<string, unknown>): QuerySort | null {
  const first = Array.isArray(cfg.sort) ? cfg.sort[0] : null
  if (first && typeof first === 'object' && typeof (first as any).field === 'string' && (first as any).field) {
    return { field: (first as any).field, direction: String((first as any).direction).toLowerCase() === 'desc' ? 'desc' : 'asc' }
  }
  const field = text(cfg.sort_field)
  if (!field) return null
  return { field, direction: ['desc', 'descending'].includes(text(cfg.sort_order).toLowerCase()) ? 'desc' : 'asc' }
}

/** 模板 → 界面状态；模板没有数据源时为 null（无法载入） */
export function restoreTemplateQuery(tpl: Pick<QueryTemplateItem, 'config' | 'data_source'>): RestoredTemplateQuery | null {
  const source = templateSourceOf(tpl)
  if (!source) return null
  const cfg = tpl.config && typeof tpl.config === 'object' ? tpl.config : {}
  const size = Number(cfg.page_size ?? cfg.limit)
  return {
    source,
    condition: { conditions: fromSavedConditions(cfg.conditions), logic: normalizeConditionLogic(cfg.condition_logic) },
    columns: strings(cfg.selected_columns).length ? strings(cfg.selected_columns) : strings(cfg.columns),
    availableColumns: strings(cfg.available_columns),
    sort: sortOf(cfg),
    pageSize: QUERY_PAGE_SIZES.includes(size) ? size : null,
    cellRange: text(cfg.cell_range),
    sheetName: text(cfg.sheet_name),
    filterText: text(cfg.filter_text),
    acnrTargets: strings(cfg.acnr_targets),
  }
}
