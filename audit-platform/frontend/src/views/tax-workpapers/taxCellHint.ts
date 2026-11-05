/**
 * 税审底稿 / 汇算申报表格子的操作提示与本地来源（悬浮卡片用，spec citar-cell-source-hover）。
 * 原 TaxWorkpaperGrid 原生 title 的文字搬到这里，卡片底部显示；账号未开通「允许修改」时不出「可修改」字样。
 */
import { localSource, type CellSource } from '@/citar/cellSource'
import { formatTaxValue, type TaxCellMeta, type TaxValue } from './taxWorkpaperApi'
import type { TaxWorkpaperCell } from './taxWorkpaperSheets'

export interface TaxCellHintInput {
  cell: TaxWorkpaperCell
  meta?: TaxCellMeta
  /** 本格草稿（undefined = 无草稿） */
  draft?: number | string | null
  restored: boolean
  manualEdit: boolean
  readonly: boolean
}

const AUTO_LABEL: Record<string, string> = { f: '原公式值', c: '样表原值', e: '原取数值' }

function draftValue(v: number | string | null): TaxValue {
  if (v === null) return null
  return typeof v === 'number' ? { n: String(v) } : { s: v }
}

/** 卡片底部一行：恢复 / 草稿 / 已手工修改 / 可点击修改 */
export function taxCellHint(i: TaxCellHintInput): string | null {
  const { cell, meta } = i
  if (i.restored) return '已恢复自动值，保存后生效'
  if (i.draft !== undefined) return `未保存的修改：${formatTaxValue(draftValue(i.draft), cell.fmt) || '空'}，保存后生效`
  if (meta?.origin === 'input') {
    const auto = meta.auto ?? (cell.role === 'c' && cell.text ? { s: cell.text } : undefined)
    const label = AUTO_LABEL[cell.role ?? 'e'] ?? '原值'
    const head = auto !== undefined ? `已手工修改，${label}：${formatTaxValue(auto, cell.fmt) || '空'}` : '已手工修改'
    return i.manualEdit && !i.readonly ? `${head}；点击可改或恢复自动值` : head
  }
  if (!i.manualEdit || i.readonly || !cell.role) return null
  if (cell.role === 'f') return '点击可手工修改（改后不再随公式更新）'
  if (cell.role === 'c') return '样表预置值，点击可修改'
  return '点击填写'
}

/** 后端不返回来源的格子：样表预置值、空的填写格 */
export function taxLocalSource(cell: TaxWorkpaperCell, value: string | null): CellSource | null {
  if (cell.role === 'c') return localSource('preset', '样表预置值', value ?? (cell.text ?? null))
  if (cell.role === 'e') return localSource('none', '手工填写格（尚未填写）', value)
  return null
}
