/**
 * 预审样本存续核对的底稿内注册表（任务 17，需求 8）。
 *
 * `GtWpRenderer` 只挂一条全局横幅，而各循环的预审凭证行分散在 62 个 `useVoucherCheckFill` 实例中。
 * 共享回填函数把自己的表 refs / 元数据更新 / persist 注册到这里；横幅按 workpaperId 汇总、去重 lfp，
 * 一次调后端后把结果写回全部同 lfp 行。模块级 registry 是父 Renderer 与子宿主之间的桥，revision 是唯一响应式信号。
 */
import { ref } from 'vue'

export type SurvivalStatus = 'unchanged' | 'modified' | 'renumbered' | 'deleted'

export interface SurvivalRequestRow {
  row_key: string
  lfp: string
  vk: string
  account_code: string
  side: 'D' | 'C' | 'X'
  amount: string
  previous_dataset_id: string | null
  previous_status: SurvivalStatus | null
  acknowledged: boolean
}

export interface RegisteredSurvivalRow {
  request: SurvivalRequestRow | null
  /** 预审行没有可用 lfp 时为 true；不能静默从分母消失 */
  unsupported: boolean
}

export interface SurvivalResultWire {
  row_key: string
  lfp: string
  status: SurvivalStatus
  acknowledged: boolean
  current_line_id?: string
  current_voucher?: { voucher_key?: string; line_count?: number; lines?: Array<Record<string, unknown>>; truncated?: boolean }
  candidates?: Array<{ voucher_key?: string; voucher_date?: string; voucher_type?: string; voucher_no?: string }>
}

export interface SurvivalCheckWire {
  check_id: string
  dataset_id: string
  checked_by: string
  checked_at: string
  total: number
  unchanged: number
  modified: number
  renumbered: number
  deleted: number
  unacked: number
  results: SurvivalResultWire[]
}

interface HostRegistration {
  collect: () => RegisteredSurvivalRow[]
  apply: (result: SurvivalCheckWire) => boolean
  acknowledge: (lfp: string, ackBy: string, ackAt: string) => boolean
  persist: () => unknown
}

const hosts = new Map<string, Map<symbol, HostRegistration>>()
export const voucherSurvivalRegistryRevision = ref(0)

function bump(): void {
  voucherSurvivalRegistryRevision.value += 1
}

export function registerVoucherSurvivalHost(workpaperId: string, host: HostRegistration): () => void {
  if (!workpaperId) return () => undefined
  const id = Symbol(workpaperId)
  const bucket = hosts.get(workpaperId) ?? new Map<symbol, HostRegistration>()
  bucket.set(id, host)
  hosts.set(workpaperId, bucket)
  bump()
  return () => {
    const current = hosts.get(workpaperId)
    current?.delete(id)
    if (current?.size === 0) {
      hosts.delete(workpaperId)
      storedContext.delete(workpaperId)
    }
    bump()
  }
}

export function notifyVoucherSurvivalRowsChanged(): void {
  bump()
}

export function collectVoucherSurvivalRows(workpaperId: string): {
  rows: SurvivalRequestRow[]
  preliminaryCount: number
  unsupportedCount: number
} {
  const deduped = new Map<string, SurvivalRequestRow>()
  let preliminaryCount = 0
  let unsupportedCount = 0
  for (const host of hosts.get(workpaperId)?.values() ?? []) {
    for (const row of host.collect()) {
      preliminaryCount += 1
      if (!row.request) {
        if (row.unsupported) unsupportedCount += 1
        continue
      }
      // 一对多展开的多行共用一条原始分录 lfp：存续状态与确认都按源分录计一次。
      deduped.set(row.request.lfp, row.request)
    }
  }
  return { rows: [...deduped.values()], preliminaryCount, unsupportedCount }
}

export async function applyVoucherSurvivalResult(workpaperId: string, result: SurvivalCheckWire): Promise<void> {
  const changed: HostRegistration[] = []
  for (const host of hosts.get(workpaperId)?.values() ?? []) {
    if (host.apply(result)) changed.push(host)
  }
  await Promise.all(changed.map(host => Promise.resolve(host.persist())))
  bump()
}

export interface SurvivalAckProjection {
  checkId: string
  datasetId: string
  unacked: number
}

/** 先把逐行 ack 元数据持久化，再由调用方 PATCH 汇总；PATCH 失败时项目概览只会保守地多报未确认，不会少报。 */
export async function acknowledgeVoucherSurvivalRow(
  workpaperId: string,
  lfp: string,
  ackBy: string,
  ackAt: string,
): Promise<SurvivalAckProjection | null> {
  const changed: HostRegistration[] = []
  for (const host of hosts.get(workpaperId)?.values() ?? []) {
    if (host.acknowledge(lfp, ackBy, ackAt)) changed.push(host)
  }
  if (!changed.length) return null
  await Promise.all(changed.map(host => Promise.resolve(host.persist())))
  const state = collectVoucherSurvivalRows(workpaperId)
  const current = state.rows.find(row => row.lfp === lfp)
  if (!current?.previous_dataset_id) return null
  // host.collect 在 ack 后把 acknowledged=true；所有当前版本的非 unchanged 源分录去重计数。
  const currentRows = state.rows.filter(row => row.previous_dataset_id === current.previous_dataset_id)
  const unacked = currentRows.filter(row => row.previous_status !== 'unchanged' && !row.acknowledged).length
  const registration = findStoredContext(workpaperId, lfp)
  bump()
  return registration ? { ...registration, unacked } : null
}

/** 从 host.collect 之外读取 checkId 不在请求模型里；host.apply 会给 registry 保存一份 lfp→上下文。 */
const storedContext = new Map<string, Map<string, { checkId: string; datasetId: string }>>()

export function rememberVoucherSurvivalContext(workpaperId: string, lfp: string, checkId: string, datasetId: string): void {
  const bucket = storedContext.get(workpaperId) ?? new Map<string, { checkId: string; datasetId: string }>()
  bucket.set(lfp, { checkId, datasetId })
  storedContext.set(workpaperId, bucket)
}

function findStoredContext(workpaperId: string, lfp: string): { checkId: string; datasetId: string } | null {
  return storedContext.get(workpaperId)?.get(lfp) ?? null
}

/** 测试 / workpaper 切换清理；生产 host 卸载由 register 返回的函数处理。 */
export function __resetVoucherSurvivalRegistry(): void {
  hosts.clear()
  storedContext.clear()
  bump()
}
