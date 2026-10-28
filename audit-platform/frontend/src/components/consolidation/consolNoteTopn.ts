/**
 * consolNoteTopn — 合并附注「前 N 名」表的说明（spec note-pull-followup-closure R10）
 *
 * 后端 `consol_note_topn.write_topn` 把重排结果写进 `data._topn`：数据叶子按单体附注的前 N 名重排（去掉集团内单位）；
 * 汇总节点只能基于下级已保存的前 N 名合并重排，下级第 N 名之后的单位看不到 ⇒ 近似（`approximate`）。界面据此写明。
 */
export interface ConsolNoteTopnInfo {
  limit?: number
  approximate?: boolean
  units?: string[]
  excluded_group_units?: string[]
  beyond_count?: number
  denominator?: string | null
  denominator_source?: string
  reasons?: string[]
}

export interface ConsolNoteTopnNotice {
  type: 'info' | 'warning'
  title: string
  lines: string[]
}

export function consolNoteTopnNotice(data: unknown): ConsolNoteTopnNotice | null {
  const info = data && typeof data === 'object' ? (data as Record<string, any>)._topn : null
  if (!info || typeof info !== 'object') return null
  const t = info as ConsolNoteTopnInfo
  const n = Number(t.limit) || 5
  const lines: string[] = []
  if (t.approximate) {
    lines.push(`汇总节点按各下级已保存的前 ${n} 名合并重排，是近似结果：下级第 ${n} 名之后的单位没有计入`)
  }
  if (t.excluded_group_units?.length) lines.push(`集团内单位不进排名：${t.excluded_group_units.join('、')}`)
  if (t.denominator && t.denominator_source) lines.push(`比例列分母：${t.denominator_source}（${t.denominator}）`)
  for (const reason of t.reasons || []) lines.push(reason)
  return {
    type: t.approximate || (t.reasons || []).length ? 'warning' : 'info',
    title: `前 ${n} 名：各企业同名单位合并后按期末余额重排取前 ${n}（不需明细映射）`,
    lines,
  }
}
