/**
 * 底稿列表页定位某张底稿（`?highlight=` / `?wp_code=` / `?search=`，spec wp-deeplink-locate-residual-closure 需求 2.1）。
 *
 * 外壳（WorkpaperList）解析入口参数后把 `{ code, seq }` 放进上下文 `locateTarget`；本组合函数在工作台 SFC 的列表视图里执行：
 * 每个 seq 只执行一次（之后刷新列表、切视图都不再跳回），要等列表至少取到过一次。
 * - 编码精确相等（不分大小写）→ 没有时按连字符向前找最近的上级底稿（D2-1 → D2）并提示；
 * - 都没有：在已生成底稿里但被筛选掉 / 只在底稿索引里（尚未生成）/ 本项目没有，分别提示；
 * - 找到：左栏选中所在循环、翻到所在页、设为当前行，渲染后滚到该行并高亮（与单元格定位同一实现）。
 */
import { nextTick, shallowRef, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { highlightElement } from '@/composables/useCellLocate'

export interface WpListLocateTarget {
  code: string
  seq: number
}

export interface WpListLocateRow {
  id: string
  wp_code: string
}

interface LocateTable {
  setCurrentRow?: (row?: unknown) => void
  $el?: Element | null
}

type ReadRef<T> = { readonly value: T }

export interface WorkpaperListLocateDeps {
  target: ReadRef<WpListLocateTarget | null | undefined>
  /** 列表取到过至少一次（首屏取数前不判「没有」） */
  loaded: ReadRef<boolean>
  loading: ReadRef<boolean>
  /** 当前列表（已按筛选，未按左栏循环） */
  rows: ReadRef<readonly WpListLocateRow[]>
  /** 左栏选中循环后的列表（翻页的依据） */
  cycleRows: ReadRef<readonly WpListLocateRow[]>
  /** 已生成底稿的编码（筛选前） */
  generatedCodes: () => Iterable<string>
  /** 底稿索引里的编码（含尚未生成的） */
  indexCodes: () => Iterable<string>
  staleFilterOn: () => boolean
  /** 列表视图在显示（工作台 / 手册与列表共用一个组件实例；缺省视为在显示） */
  active?: () => boolean
  selectCycle: (cycle: string) => void
  page: Ref<number>
  pageSize: ReadRef<number>
  table: ReadRef<LocateTable | null>
  notify?: { info: (message: string) => void; warning: (message: string) => void }
}

export const wpNotInProjectMessage = (code: string) => `本项目没有底稿 ${code}`
export const wpNotGeneratedMessage = (code: string) => `底稿 ${code} 尚未生成`
export const wpFilteredOutMessage = (code: string, stale: boolean) =>
  stale ? `底稿 ${code} 不在「仅看待重算」的结果里` : `底稿 ${code} 不在当前筛选结果里`
export const wpParentFallbackMessage = (code: string, parent: string) => `没有编码为 ${code} 的底稿，已定位到 ${parent}`

const upper = (s: string) => String(s || '').trim().toUpperCase()
export const cycleOfCode = (code: string) => (code || '?')[0].toUpperCase()

/** 按连字符向前找列表里最近的上级编码（D2-1-3 → D2-1 → D2） */
export function nearestListedParent(code: string, listed: ReadonlySet<string>): string {
  let cut = code.lastIndexOf('-')
  while (cut > 0) {
    const candidate = code.slice(0, cut)
    if (listed.has(candidate)) return candidate
    cut = code.lastIndexOf('-', cut - 1)
  }
  return ''
}

export function useWorkpaperListLocate(deps: WorkpaperListLocateDeps) {
  const notify = deps.notify ?? { info: (m: string) => { ElMessage.info(m) }, warning: (m: string) => { ElMessage.warning(m) } }
  const done = new Set<number>()
  /** 当前要执行的目标：外壳的入口目标，或本视图内点出的（手册视图点底稿，seq 取负数不与外壳撞号） */
  const current = shallowRef<WpListLocateTarget | null>(null)
  let localSeq = 0
  watch(() => deps.target.value, (t) => { if (t) current.value = t }, { immediate: true })

  /** 本视图内定位（手册视图点底稿编码 → 切到列表并标出该行） */
  function locateCode(code: string): void {
    current.value = { code, seq: --localSeq }
  }

  async function locate(): Promise<void> {
    const t = current.value
    if (!t || !t.code || done.has(t.seq) || deps.loading.value || !deps.loaded.value) return
    if (deps.active && !deps.active()) return
    done.add(t.seq)
    const want = upper(t.code)
    const byCode = new Map(deps.rows.value.map((r) => [upper(r.wp_code), r] as const))
    let row = byCode.get(want)
    const parent = row ? '' : nearestListedParent(want, new Set(byCode.keys()))
    if (!row && parent) row = byCode.get(parent)
    if (!row) {
      const has = (codes: Iterable<string>) => [...codes].some((c) => upper(c) === want)
      if (has(deps.generatedCodes())) notify.warning(wpFilteredOutMessage(t.code, deps.staleFilterOn()))
      else notify.warning(has(deps.indexCodes()) ? wpNotGeneratedMessage(t.code) : wpNotInProjectMessage(t.code))
      return
    }
    const target = row
    deps.selectCycle(cycleOfCode(target.wp_code))
    await nextTick()
    const index = deps.cycleRows.value.findIndex((r) => r.id === target.id)
    if (index < 0) return
    const size = Math.max(1, deps.pageSize.value)
    deps.page.value = Math.floor(index / size) + 1
    await nextTick()
    const table = deps.table.value
    table?.setCurrentRow?.(target)
    await nextTick()
    const tr = table?.$el?.querySelectorAll?.('.el-table__body-wrapper tbody tr.el-table__row')?.[index % size]
    if (tr) highlightElement(tr, `wp-list:${target.id}`)
    if (parent) notify.info(wpParentFallbackMessage(t.code, target.wp_code))
  }

  watch(() => [current.value?.seq, deps.loading.value, deps.loaded.value, deps.rows.value.length, deps.active?.() ?? true] as const,
    () => { void locate() }, { immediate: true })

  return { locate, locateCode }
}

/** 列表上下文里定位要用的字段（结构类型；WorkpaperList 外壳 provide 的上下文满足它） */
export interface WpListLocateContext<W> {
  locateTarget?: ReadRef<WpListLocateTarget | null | undefined>
  listLoaded?: ReadRef<boolean>
  loading: ReadRef<boolean>
  wpList: ReadRef<readonly W[]>
  wpIndex: ReadRef<readonly { wp_code: string }[]>
  filterStale?: ReadRef<boolean>
  viewMode: ReadRef<string>
}

export type WpListLocateViewDeps = Pick<WorkpaperListLocateDeps, 'rows' | 'cycleRows' | 'page' | 'pageSize' | 'selectCycle' | 'notify'>

/**
 * 工作台 SFC 用：入口目标、取数状态、编码清单、待重算筛选取自列表上下文，只在列表视图显示时执行；
 * 表格引用在这里建（模板 `ref=` 绑返回的 `table`），视图只给行、分页、左栏循环与底稿编码的读法。
 */
export function useWorkpaperListLocateInView<W>(ctx: WpListLocateContext<W>, codeOf: (w: W) => string, view: WpListLocateViewDeps) {
  const table = shallowRef<LocateTable | null>(null)
  const api = useWorkpaperListLocate({
    ...view, table,
    target: ctx.locateTarget ?? { value: null }, loaded: ctx.listLoaded ?? { value: true }, loading: ctx.loading,
    generatedCodes: () => ctx.wpList.value.map(codeOf), indexCodes: () => ctx.wpIndex.value.map((i) => i.wp_code),
    staleFilterOn: () => !!ctx.filterStale?.value, active: () => ctx.viewMode.value === 'list',
  })
  return { ...api, table }
}
