/**
 * 生成计划弹窗的纯函数（spec trim-generation-plan-linkage R2）。
 *
 * 🔴 发送给生成接口的编码只从计划的 items 推导（状态为「将生成」的），不另存一份清单；
 *    勾选只到循环一级，逐个底稿的排除走程序裁剪页。
 */
import type { GenerationPlan, PlanCycle, PlanItem, PlanItemState, TrimState } from '@/services/generationPlanApi'
import { fmtDate, parseServerTime } from '@/utils/formatters'

/** 循环展示顺序（与程序裁剪页页签一致），其余排后 */
export const CYCLE_ORDER = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'A', 'S'] as const

/** 与程序裁剪页页签同名 */
export const CYCLE_LABELS: Record<string, string> = {
  B: 'B 初步业务', C: 'C 控制测试', D: 'D 收入', E: 'E 货币资金', F: 'F 存货', G: 'G 投资',
  H: 'H 固定资产', I: 'I 无形资产', J: 'J 职工薪酬', K: 'K 管理', L: 'L 债务', M: 'M 权益',
  N: 'N 税金', A: 'A 完成阶段', S: 'S 专项',
}

export function cycleLabel(cycle: string): string {
  return CYCLE_LABELS[cycle] || cycle
}

export function cycleRank(cycle: string): number {
  const i = (CYCLE_ORDER as readonly string[]).indexOf(cycle)
  return i >= 0 ? i : CYCLE_ORDER.length
}

export function orderCycles<T extends { cycle: string }>(cycles: T[]): T[] {
  return [...cycles].sort((a, b) => cycleRank(a.cycle) - cycleRank(b.cycle) || a.cycle.localeCompare(b.cycle))
}

/** 可勾选 = 本循环有「将生成」的底稿 */
export function isCycleSelectable(cycle: PlanCycle): boolean {
  return cycle.counts.to_create > 0
}

/** 默认勾选：给了初始循环只勾它（且可勾时），否则勾全部可勾的循环 */
export function defaultSelectedCycles(plan: GenerationPlan | null, initialCycle?: string | null): string[] {
  if (!plan) return []
  const selectable = plan.cycles.filter(isCycleSelectable).map((c) => c.cycle)
  if (initialCycle) return selectable.includes(initialCycle) ? [initialCycle] : []
  return selectable
}

/** 本次发送的编码：所选循环里状态为「将生成」的（循环按展示顺序，循环内保持模板集顺序） */
export function codesToGenerate(plan: GenerationPlan | null, selected: Iterable<string>): string[] {
  if (!plan) return []
  const chosen = new Set(selected)
  return orderCycles(plan.cycles)
    .filter((c) => chosen.has(c.cycle))
    .flatMap((c) => c.items.filter((it) => it.state === 'to_create').map((it) => it.wp_code))
}

/** 有底稿要生成、但粗裁没人保存过（或没打开过）的循环：提醒先去程序裁剪确认 */
export function pendingTrimCycles(plan: GenerationPlan | null): PlanCycle[] {
  if (!plan) return []
  return plan.cycles.filter((c) => c.trim_state !== 'confirmed' && c.counts.to_create + c.counts.category_excluded > 0)
}

export interface ProgramGroup {
  key: string
  /** 程序行编码；没有程序行覆盖的底稿归「尚无程序行」 */
  code: string | null
  label: string
  status: string | null
  items: PlanItem[]
}

/** 展开行：按决定它的程序行分组（跟随下级的科目母码单列一组，组顺序 = 程序行顺序，尚无程序行的排最后） */
export function groupItemsByProgram(cycle: PlanCycle): ProgramGroup[] {
  const programs = new Map(cycle.programs.map((p) => [p.code.trim().toUpperCase(), p]))
  const groups = new Map<string, ProgramGroup>()
  const order = (key: string) => {
    if (key === '__follow__') return -1
    if (key === '__none__') return Number.MAX_SAFE_INTEGER
    const i = cycle.programs.findIndex((p) => p.code.trim().toUpperCase() === key)
    return i >= 0 ? i : Number.MAX_SAFE_INTEGER - 1
  }
  for (const it of cycle.items) {
    const owner = it.decided_by ? it.decided_by.trim().toUpperCase() : null
    const key = it.follows_children ? '__follow__' : owner ?? '__none__'
    if (!groups.has(key)) {
      const p = owner ? programs.get(owner) : undefined
      groups.set(key, {
        key,
        code: it.follows_children ? null : owner,
        label: it.follows_children
          ? '科目审定表（跟随本科目的程序行）'
          : owner
            ? `${p?.code ?? owner} ${p?.name ?? ''}`.trim()
            : '尚无程序行（打开程序裁剪页后可裁剪）',
        status: it.follows_children ? null : p?.status ?? null,
        items: [],
      })
    }
    groups.get(key)!.items.push(it)
  }
  return [...groups.values()].sort((a, b) => order(a.key) - order(b.key))
}

export const TRIM_STATE_TEXT: Record<TrimState, string> = {
  not_initialized: '未打开',
  unconfirmed: '未保存',
  confirmed: '已保存',
}

/** 「已保存（王经理 2026/10/28）」：日期按本地时区（后端是 UTC，截前 10 位会把北京时间 0~8 点显示成前一天） */
export function trimStateText(cycle: Pick<PlanCycle, 'trim_state' | 'confirmed_at' | 'confirmed_by'>): string {
  if (cycle.trim_state !== 'confirmed') return TRIM_STATE_TEXT[cycle.trim_state]
  const day = cycle.confirmed_at ? fmtDate(parseServerTime(cycle.confirmed_at)) : ''
  const parts = [cycle.confirmed_by, day && day !== '-' ? day : ''].filter(Boolean)
  return parts.length ? `已保存（${parts.join(' ')}）` : '已保存'
}

export interface ItemStateMeta {
  text: string
  tag: 'success' | 'info' | 'warning' | 'danger' | 'primary'
}

export const ITEM_STATE_META: Record<PlanItemState, ItemStateMeta> = {
  to_create: { text: '将生成', tag: 'success' },
  existing: { text: '已生成', tag: 'info' },
  in_recycle: { text: '在回收站', tag: 'warning' },
  trimmed: { text: '已裁剪', tag: 'danger' },
  category_excluded: { text: '业务分类不生成', tag: 'warning' },
}

/** 底部「将生成」合计（所选循环） */
export function selectedSummary(plan: GenerationPlan | null, selected: Iterable<string>): { cycles: number; codes: number } {
  const list = [...selected]
  return { cycles: list.length, codes: codesToGenerate(plan, list).length }
}
