/**
 * 程序裁剪页 ↔ 生成底稿联动（spec trim-generation-plan-linkage R3 / R5）。
 *
 * 裁剪页（4000+ 行）只接这里的函数：
 * - 加载循环：委派人先走初始化接口（把模板里没有程序行管的、业务分类适用性不同的编码补成程序行，幂等），
 *   没有委派权限 / 初始化失败退回只读读取；只读成员不触发补齐，也不再对没打开过的循环调初始化（原先必 403）。
 * - 粗裁状态：未打开 / 未保存 / 已保存（谁、何时），表格工具栏显示。
 * - 业务分类建议：后端按项目业务分类给的 `category_hint`（本行底稿全部不适用）→ 一键标为裁剪并填好理由，仍需保存。
 * - 保存粗裁后：生成本循环底稿 / 前往委派 / 留在本页。
 */
import { computed, ref, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { LocationQuery } from 'vue-router'
import { api } from '@/services/apiProxy'
import { procedures as P_proc } from '@/services/apiPaths'
import { getProcedures } from '@/services/commonApi'
import { getScopeConfirmations, type ScopeConfirmation } from '@/services/generationPlanApi'
import { useProjectStore } from '@/stores/project'
import { useRoleContextStore } from '@/stores/roleContext'
import { trimStateText } from '@/components/workpaper/generation/generationPlanModel'

export interface CategoryHint {
  reason: string
  codes: string[]
}

/** 裁剪页程序行里本组合式函数读写的字段（其余字段原样保留） */
export interface TrimLinkRow {
  _applicable: boolean
  status?: string
  skip_reason?: string | null
  category_hint?: CategoryHint | null
}

export type AfterSaveChoice = 'generate' | 'delegate' | 'stay'

export function useTrimGenerationLink(projectId: Ref<string>, cycleCodes: readonly string[]) {
  const known = new Set(cycleCodes)
  const cycleLoads = new Map<string, Promise<any[]>>()
  const confirmations = ref<Record<string, ScopeConfirmation>>({})
  const confirmationLoadFailed = ref(false)
  let confirmationSeq = 0
  /**
   * 生成底稿与底稿列表页同一门槛：本项目可编辑、项目未归档。
   * store 在计算时才取：裁剪页原先不依赖 Pinia，既有挂载用例没装 Pinia，取不到按「不能生成」。
   */
  const canGenerate = computed(() => {
    try {
      return useRoleContextStore().canEditInProject && useProjectStore().projectStatus !== 'archived'
    } catch {
      return false
    }
  })

  /** `?cycle=D`（从生成弹窗「去程序裁剪」跳过来）；不是已知循环的忽略 */
  function initialCycleFromRoute(query: LocationQuery): string | null {
    const raw = Array.isArray(query.cycle) ? query.cycle[0] : query.cycle
    const code = typeof raw === 'string' ? raw.trim().toUpperCase() : ''
    return known.has(code) ? code : null
  }

  async function loadCycleRows(cycle: string, canInit: boolean): Promise<any[]> {
    const key = `${projectId.value}:${cycle}:${canInit ? 'init' : 'read'}`
    const running = cycleLoads.get(key)
    if (running) return running
    const request = (async () => {
      if (canInit) {
        try {
          const res = await api.post<{ procedures?: any[] }>(P_proc.init(projectId.value, cycle), {}, { _silent: true } as any)
          if (Array.isArray(res?.procedures)) return res.procedures
        } catch {
          /* 不是本项目委派人等：退回只读读取 */
        }
      }
      return (await getProcedures(projectId.value, cycle)) || []
    })()
    cycleLoads.set(key, request)
    try {
      return await request
    } finally {
      if (cycleLoads.get(key) === request) cycleLoads.delete(key)
    }
  }

  async function loadConfirmations(): Promise<void> {
    const mine = ++confirmationSeq
    const requestedProject = projectId.value
    try {
      const list = await getScopeConfirmations(requestedProject)
      if (mine !== confirmationSeq || requestedProject !== projectId.value) return
      confirmations.value = Object.fromEntries(list.map((c) => [c.cycle, c]))
      confirmationLoadFailed.value = false
    } catch {
      if (mine === confirmationSeq && requestedProject === projectId.value) confirmationLoadFailed.value = true
      // 保留上一次成功值：瞬时失败不把「已保存」误写成「状态未知」。
    }
  }

  function confirmationText(cycle: string): string {
    const c = confirmations.value[cycle]
    return c ? trimStateText(c) : '状态未知'
  }

  function isConfirmed(cycle: string): boolean {
    return confirmations.value[cycle]?.trim_state === 'confirmed'
  }

  /** 执行中、且后端给了业务分类建议的行 */
  function categoryHintRows<T extends TrimLinkRow>(rows: T[]): T[] {
    return rows.filter((r) => r._applicable && !!r.category_hint)
  }

  /** 按业务分类建议标为裁剪（理由用后端给的说明）；只改页面上的行，仍需「保存粗裁」 */
  function adoptCategoryHint(row: TrimLinkRow): void {
    if (!row.category_hint) return
    row._applicable = false
    row.status = 'not_applicable'
    row.skip_reason = row.category_hint.reason
  }

  function adoptAllCategoryHints(rows: TrimLinkRow[]): number {
    const targets = categoryHintRows(rows)
    targets.forEach(adoptCategoryHint)
    return targets.length
  }

  /** 保存粗裁后的下一步（能生成时三选一；不能生成时只问是否去委派） */
  async function promptAfterSave(): Promise<AfterSaveChoice> {
    try {
      if (!canGenerate.value) {
        await ElMessageBox.confirm(
          '粗裁已保存。是否前往「人员委派」界面，将保留执行的程序委派给审计人员？',
          '前往人员委派',
          { type: 'success', confirmButtonText: '前往委派', cancelButtonText: '暂不' },
        )
        return 'delegate'
      }
      await ElMessageBox.confirm(
        '粗裁已保存。可以按保存的结果生成本循环底稿，或前往「人员委派」把保留执行的程序委派给审计人员。',
        '粗裁已保存',
        { type: 'success', confirmButtonText: '生成本循环底稿', cancelButtonText: '前往委派', distinguishCancelAndClose: true },
      )
      return 'generate'
    } catch (action) {
      return canGenerate.value && action === 'cancel' ? 'delegate' : 'stay'
    }
  }

  return {
    canGenerate,
    confirmations,
    confirmationLoadFailed,
    initialCycleFromRoute,
    loadCycleRows,
    loadConfirmations,
    confirmationText,
    isConfirmed,
    categoryHintRows,
    adoptCategoryHint,
    adoptAllCategoryHints,
    promptAfterSave,
  }
}
