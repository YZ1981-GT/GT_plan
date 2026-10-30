/**
 * 附注单元格最终来源诊断（只读，spec note-chain-followup-optimizations R2）：坐标类型、请求与状态文案。
 *
 * 后端 `GET /api/disclosure-notes/{pid}/{year}/{section}/cell-sources` 按写入方的实际行为判定这一格的数是谁写的
 * （人工 / 锁定 → 附注公式 → 模板取数 → 公式推送 → 底稿披露表同步），并列出对不上的地方。
 */
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'

/** 一格的存储坐标：投影表（底稿来源）带 subTableKey + 来源行号 + 业务列键；存储表是表序号 + 行 + 列（列不含行名列）。 */
export interface CellSourceRef {
  tableIndex: number
  row: number
  col: number
  subTableKey?: string
  valueKey?: string
}

export interface CellSourceStep {
  kind: string
  label: string
  status: string
  detail: string
}

export interface CellSourcesResult {
  target?: string
  target_label?: string
  value?: unknown
  projected?: boolean
  storage?: { kind: string; text: string }
  final?: { kind: string; label: string; detail: string }
  steps?: CellSourceStep[]
  conflicts?: Array<{ kind: string; message: string }>
  error?: string
  message?: string
}

export function fetchCellSources(
  projectId: string, year: number, section: string, ref: CellSourceRef,
): Promise<CellSourcesResult> {
  const params: Record<string, string | number> = { table_index: ref.tableIndex, row: ref.row, col: ref.col }
  if (ref.subTableKey) params.sub_table_key = ref.subTableKey
  if (ref.valueKey) params.value_key = ref.valueKey
  // 失败由弹窗就地提示（全局拦截器不再弹一次）
  return api.get(P.disclosureNotes.cellSources(projectId, year, section), { params, _silent: true } as any)
}

type TagType = 'success' | 'warning' | 'danger' | 'info' | 'primary'

export const STEP_STATUS: Record<string, { text: string; type: TagType }> = {
  final: { text: '最终来源', type: 'success' },
  overridden: { text: '被覆盖', type: 'info' },
  consistent: { text: '核对一致', type: 'success' },
  kept: { text: '保留底稿值', type: 'warning' },
  pending: { text: '待补空', type: 'primary' },
  conflict: { text: '不一致', type: 'danger' },
  blocked: { text: '不写入', type: 'info' },
  info: { text: '仅供参考', type: 'info' },
  inactive: { text: '不适用', type: 'info' },
}

export function stepStatus(status: string): { text: string; type: TagType } {
  return STEP_STATUS[status] || { text: status, type: 'info' }
}
