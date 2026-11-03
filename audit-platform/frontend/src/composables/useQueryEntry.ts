/**
 * useQueryEntry.ts — 高级查询弹窗的「入口上下文」状态机（advanced-query-linkage-closure 任务 46，design §4.3；ADR-AQL-20）
 *
 * 业务页点「按此查询明细」带着 `QueryEntryRequest` 打开弹窗。本组合式只管上下文本身：
 * - 应用：写项目、年度、数据源与筛选，然后交宿主执行一次；
 * - 切换：换数据源、保留（或按 switch 指定）筛选，再执行；
 * - 行内下钻：压栈（最多 5 层），「← 返回上一查询」出栈回到上一层；
 * - 清除：用户手动换数据源时自动清除，避免把筛选键带到不认它的源而 400。
 *
 * 筛选只经 `filters` 传给后端（键由注册表登记：`account_code` / `wp_code` / `report_row` / `note_section`），
 * 保存模板时写进 `config.filters`。
 */
import { computed, ref } from 'vue'

import type {
  QueryEntryFilters, QueryEntryRequest, QueryEntrySwitch,
} from '@/components/query/queryEntryContext'

/** 下钻层数上限（design §4.3）：到顶后不再压栈，仍然执行本次查询 */
export const MAX_ENTRY_DEPTH = 5

export interface UseQueryEntryHost {
  /** 写入弹窗的项目 / 年度 / 数据源，并执行一次查询（宿主实现，内部不直接碰弹窗状态） */
  apply: (input: { projectId: string; year?: number; source: string }) => void | Promise<void>
}

export function useQueryEntry(host: UseQueryEntryHost) {
  /** 当前上下文（null = 普通查询） */
  const entry = ref<QueryEntryRequest | null>(null)
  /** 下钻栈：栈底是入口本身，当前层不在栈里 */
  const stack = ref<QueryEntryRequest[]>([])

  const active = computed(() => entry.value !== null)
  const filters = computed<QueryEntryFilters>(() => entry.value?.filters ?? {})
  const canGoBack = computed(() => stack.value.length > 0)
  const depth = computed(() => stack.value.length + (entry.value ? 1 : 0))
  const switches = computed<QueryEntrySwitch[]>(() => entry.value?.switches ?? [])

  async function run(next: QueryEntryRequest) {
    entry.value = next
    await host.apply({
      projectId: next.projectId, source: next.source,
      ...(next.year === undefined ? {} : { year: next.year }),
    })
  }

  /** 应用一个新入口：清空下钻栈（这是一条新的查询链） */
  async function applyEntry(next: QueryEntryRequest) {
    stack.value = []
    await run(next)
  }

  /** 切换数据源：沿用当前筛选；switch 自带 `filters` 时按它换（附注章节 → 相关科目） */
  async function switchSource(target: QueryEntrySwitch) {
    const current = entry.value
    if (!current || target.source === current.source) return
    await run({
      ...current, source: target.source,
      filters: target.filters ?? current.filters,
      label: current.label,
    })
  }

  /** 行内下钻：把当前层压栈后执行下一跳；到达层数上限时不再压栈 */
  async function drillDown(next: QueryEntryRequest) {
    const current = entry.value
    if (current && stack.value.length + 1 < MAX_ENTRY_DEPTH) stack.value = [...stack.value, current]
    await run(next)
  }

  /** 返回上一查询 */
  async function goBack() {
    const previous = stack.value[stack.value.length - 1]
    if (!previous) return
    stack.value = stack.value.slice(0, -1)
    await run(previous)
  }

  /** 清除上下文：只丢上下文，不动弹窗当前的数据源与结果（由宿主决定是否重查） */
  function clear() {
    entry.value = null
    stack.value = []
  }

  /**
   * 用户手动换了数据源：不是本上下文认识的源就清除。
   * 经切换按钮换源时 `entry.source` 已先被写成新值，所以这里只会在真正的手动切换时清掉。
   */
  function onSourceChangedByUser(source: string) {
    const current = entry.value
    if (!current) return
    if (source === current.source) return
    if (current.switches.some((item) => item.source === source)) return
    clear()
  }

  return {
    entry, stack, active, filters, switches, canGoBack, depth,
    applyEntry, switchSource, drillDown, goBack, clear, onSourceChangedByUser,
  }
}

export type QueryEntryController = ReturnType<typeof useQueryEntry>
