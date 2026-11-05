/**
 * 税审底稿 / 汇算申报表单表的悬浮来源卡片（spec citar-cell-source-hover R1~R3）：两个单表面板共用。
 * - 来源：GET /cell-sources/tax-sheet/{编号}（首次悬停请求，本表取值刷新后作废）+ 本地补（样表预置值、空填写格）+ 操作提示
 * - 链接：同类表 → 派发 TAX_CELL_LOCATE_EVENT 由本页切表定位；别的页 → 有未保存修改先确认，再跳页（格子定位经 sessionStorage）
 * - locate(sheet, ref)：本表读完值后滚到格子并高亮
 */
import { computed, nextTick, ref, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { cellSources as P_src } from '@/services/apiPaths'
import {
  TAX_CELL_LOCATE_EVENT, cellSourceLink, savePendingTaxLocate,
  type CellSource, type CellSourceLink, type CellSourceResponse, type TaxCellLocate,
} from '@/citar/cellSource'
import { useCellSourceHover } from '@/citar/useCellSourceHover'
import { useCitarProject } from '@/citar/useCitarProject'
import { taxCellHint, taxLocalSource } from './taxCellHint'
import { formatTaxValue, type TaxSheetPartValues, type TaxSheetResult } from './taxWorkpaperApi'
import type { TaxWorkpaperCell, TaxWorkpaperSheetDefinition } from './taxWorkpaperSheets'

export interface TaxSheetSourcesOptions {
  domain: TaxCellLocate['domain']
  projectId: () => string
  year: () => number | null
  code: () => string
  definition: () => TaxWorkpaperSheetDefinition | undefined
  result: () => TaxSheetResult | null
  partValues: (sheet: string) => TaxSheetPartValues
  drafts: () => Record<string, Record<string, number | string | null>>
  restoredOf: (sheet: string) => ReadonlySet<string>
  manualEdit: () => boolean
  readonly: () => boolean
  dirty: () => boolean
  container: Ref<HTMLElement | null>
}

interface CellEntry {
  sheet: string
  cell: TaxWorkpaperCell
  rowLabel: string
}

const LINE_NO = /^[\d.\s]+$/

/** 每个带地址格子的行名：同行左侧最近的文字（项目名称），没有时取本行第一个文字；纯数字（行次）跳过 */
function rowLabels(row: TaxWorkpaperCell[]): Map<TaxWorkpaperCell, string> {
  const texts = row.map(c => (!c.ref && c.text?.trim() && !LINE_NO.test(c.text.trim()) ? c.text.trim() : ''))
  const first = texts.find(Boolean) ?? ''
  const out = new Map<TaxWorkpaperCell, string>()
  let last = ''
  row.forEach((c, i) => {
    if (texts[i]) last = texts[i]
    else if (c.ref) out.set(c, last || first)
  })
  return out
}

export function useTaxSheetSources(opts: TaxSheetSourcesOptions) {
  const { goSegment } = useCitarProject()
  const located = ref<{ sheet: string; ref: string } | null>(null)

  const index = computed(() => {
    const map = new Map<string, CellEntry>()
    for (const part of opts.definition()?.parts ?? []) {
      for (const row of part.rows) {
        const labels = rowLabels(row)
        for (const cell of row) if (cell.ref) map.set(`${part.source}!${cell.ref}`, { sheet: part.source, cell, rowLabel: labels.get(cell) ?? '' })
      }
    }
    return map
  })

  async function load(): Promise<Record<string, CellSource>> {
    const year = opts.year()
    if (!year) throw new Error('项目未设置审核年度')
    const res = (await api.get(P_src.taxSheet(opts.projectId(), opts.code()), {
      params: { year, domain: opts.domain }, _silent: true,
    } as any)) as CellSourceResponse
    return res?.cells ?? {}
  }

  function resolve(key: string, sources: Record<string, CellSource> | null): CellSource | null {
    const entry = index.value.get(key)
    if (!entry) return null
    const { sheet, cell } = entry
    const ref = cell.ref as string
    const part = opts.partValues(sheet)
    const meta = part.cells[ref]
    const sheetDrafts = opts.drafts()[sheet] ?? {}
    const hint = taxCellHint({
      cell, meta, draft: ref in sheetDrafts ? sheetDrafts[ref] : undefined,
      restored: opts.restoredOf(sheet).has(ref), manualEdit: opts.manualEdit(), readonly: opts.readonly(),
    })
    const remote = sources?.[key]
    if (remote) return { ...remote, hint }
    // 后端来源还没到：只有样表预置值能本地确定，其余格子显示「正在读取」（填写格是否有手工值要等后端）
    if (!sources && cell.role !== 'c') return null
    const shown = formatTaxValue(part.values[ref], cell.fmt) || null
    const local = taxLocalSource(cell, shown)
    return local ? { ...local, hint } : null
  }

  /** 属性选择器转义（与 useCitarRowLocate 同口径；jsdom 没有 CSS.escape） */
  const bySrc = (key: string) => `[data-src="${key.replace(/["\\]/g, '\\$&')}"]`

  const hover = useCellSourceHover(opts.container, {
    load,
    resolve,
    // 正在编辑的格子不弹
    disabled: key => Boolean(opts.container.value?.querySelector(`${bySrc(key)} input`)),
  })

  const cardLabel = computed(() => {
    const entry = index.value.get(hover.card.value.key)
    if (!entry) return ''
    return [opts.code(), entry.cell.ref, entry.rowLabel].filter(Boolean).join(' ')
  })

  async function confirmLeave(): Promise<boolean> {
    if (!opts.dirty()) return true
    try {
      await ElMessageBox.confirm('本表有未保存的修改，离开后修改会丢失。仍要去看数据来源吗？', '未保存的修改', {
        type: 'warning', confirmButtonText: '离开', cancelButtonText: '留在本页',
      })
      return true
    } catch {
      return false
    }
  }

  /** 卡片里点链接 */
  async function open(l: CellSourceLink) {
    hover.close()
    if ((l.page === 'workpaper' || l.page === 'tax_return') && l.code && l.ref) {
      const target: TaxCellLocate = { domain: l.page, code: l.code, sheet: l.sheet ?? l.code, ref: l.ref }
      if (l.page === opts.domain) {
        // 本页：页面切表（有未保存修改时它会确认）再定位
        window.dispatchEvent(new CustomEvent<TaxCellLocate>(TAX_CELL_LOCATE_EVENT, { detail: target }))
        return
      }
      if (!(await confirmLeave())) return
      savePendingTaxLocate(opts.projectId(), target)
    } else if (!(await confirmLeave())) {
      return
    }
    const link = cellSourceLink(l)
    if (link) goSegment(link.segment, link.query)
  }

  /** 本表读完值后定位格子；找不到时提示 */
  async function locate(sheet: string, ref: string) {
    await nextTick()
    const key = `${sheet}!${ref}`
    const el = opts.container.value?.querySelector<HTMLElement>(bySrc(key))
    if (!el) {
      located.value = null
      ElMessage.info(`本表没有格子 ${ref}，或该格不在打印区`)
      return
    }
    located.value = { sheet, ref }
    el.scrollIntoView?.({ behavior: 'smooth', block: 'center', inline: 'center' })
  }

  // 本表取值换了（取数 / 保存 / 换年度）：来源作废，下次悬停重取
  watch(() => opts.result(), () => hover.invalidate())

  function locatedRefOf(sheet: string): string | null {
    return located.value?.sheet === sheet ? located.value.ref : null
  }

  return { card: hover.card, cardLabel, onCardEnter: hover.onCardEnter, onCardLeave: hover.onCardLeave, open, locate, locatedRefOf, close: hover.close }
}
