/**
 * 序时账的查看级别与穿透历史（全部分录 → 凭证 / 科目 → …，「返回」逐级退回）。
 * 历史放在组件外：换级别会改地址栏（?account= / ?voucher=&vdate=），CITAR 布局按 fullPath 给页面作 key
 * ⇒ 整页重挂载，组件里的状态留不住。按「项目 | 年度」各存一份；挂载时地址栏上的级别与记下的不符
 * （从别的入口进来、手工换了筛选）即整份作废。页面刷新后不保留历史（当前级别仍在地址栏上）。
 */

/** 序时账当前看的是哪一级：某科目（含下级；空 = 全部分录）或某张凭证 */
export type JournalView =
  | { kind: 'account'; code: string }
  /** date 为空：凭证号没带日期，列全年同号分录 */
  | { kind: 'voucher'; no: string; date: string | null }

/** 进入某一级时的位置（「返回」回到这里） */
export interface DrillFrame {
  view: JournalView
  pageIndex: number
  /** 科目级的游标栈（全部分录按页码分页、凭证级不分页，不用游标） */
  cursors: (string | null)[]
  total: number | null
  /** 从哪一行点进去的：回到这一级后滚到这一行并高亮 */
  rowId: string
}

interface DrillMemory {
  /** 记下时应当看到的级别 */
  key: string
  stack: DrillFrame[]
  /** 重挂载出的新页面按它读页码、高亮行（只用一次） */
  restore: DrillFrame | null
  /** 读完后把高亮行滚到中间（「返回」时）；否则只高亮、页面停在表头（往下一级时） */
  scrollToRow: boolean
}

const store = new Map<string, DrillMemory>()

const keyOf = (projectId: string, year: number) => `${projectId}|${year}`

export function viewKey(v: JournalView): string {
  return v.kind === 'voucher' ? `v:${v.date ?? ''}|${v.no}` : `a:${v.code}`
}

const cloneFrame = (f: DrillFrame): DrillFrame => ({ ...f, view: { ...f.view }, cursors: [...f.cursors] })

/** 记下穿透历史与新页面要读的位置；栈空且无待恢复位置时清掉 */
export function rememberDrill(
  projectId: string,
  year: number,
  view: JournalView,
  stack: DrillFrame[],
  restore: DrillFrame | null = null,
  scrollToRow = false,
) {
  const key = keyOf(projectId, year)
  if (!stack.length && !restore) {
    store.delete(key)
    return
  }
  store.set(key, { key: viewKey(view), stack: stack.map(cloneFrame), restore: restore ? cloneFrame(restore) : null, scrollToRow })
}

/** 挂载时取回：级别对得上才算数，待恢复位置取走即清 */
export function recallDrill(
  projectId: string,
  year: number,
  view: JournalView,
): { stack: DrillFrame[]; restore: DrillFrame | null; scrollToRow: boolean } {
  const key = keyOf(projectId, year)
  const m = store.get(key)
  if (!m || m.key !== viewKey(view)) {
    store.delete(key)
    return { stack: [], restore: null, scrollToRow: false }
  }
  const restore = m.restore
  m.restore = null
  return { stack: m.stack.map(cloneFrame), restore, scrollToRow: m.scrollToRow }
}

export function forgetDrill(projectId: string, year: number) {
  store.delete(keyOf(projectId, year))
}

/** 测试用：清空全部 */
export function resetDrillMemory() {
  store.clear()
}
