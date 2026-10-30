import { ref } from 'vue'

import {
  loadWorksheetData,
  saveWorksheetData,
  WorksheetVersionConflictError,
  type WorksheetLoadResult,
  type WorksheetSaveResult,
} from '@/services/consolWorksheetDataApi'

export interface TbSummaryPersistContext {
  projectId: string
  year: number
  sheetKey: string
}

export interface TbSummaryPersistRow {
  row_code?: string
  row_name?: string
  unadjusted?: unknown
  aje_dr?: unknown
  aje_cr?: unknown
  rcl_dr?: unknown
  rcl_cr?: unknown
  formula_detached?: boolean
  manual_rcl_dr?: boolean
  manual_rcl_cr?: boolean
  [key: string]: unknown
}

export type TbSummaryRclField = 'rcl_dr' | 'rcl_cr'

type LoadFn = (
  projectId: string,
  year: number,
  sheetKey: string,
) => Promise<WorksheetLoadResult>

type SaveFn = (
  projectId: string,
  year: number,
  sheetKey: string,
  data: Record<string, any>,
  expectedVersion?: number,
) => Promise<WorksheetSaveResult>

interface PendingSave {
  key: string
  context: TbSummaryPersistContext
  generation: number
  revision: number
  rows: TbSummaryPersistRow[]
}

export interface TbSummaryPersistenceOptions {
  getContext: () => TbSummaryPersistContext | null
  getRows: () => TbSummaryPersistRow[]
  canSave: () => boolean
  delayMs?: number
  load?: LoadFn
  save?: SaveFn
  onError?: (message: string, error: unknown) => void
}

export function tbSummaryContextKey(context: TbSummaryPersistContext): string {
  return `${context.projectId}:${context.year}:${context.sheetKey}`
}
export function markManualRcl(row: TbSummaryPersistRow, field: TbSummaryRclField): void {
  if (field === 'rcl_dr') row.manual_rcl_dr = true
  else row.manual_rcl_cr = true
}

export function serializeTbSummaryRows(rows: TbSummaryPersistRow[]): TbSummaryPersistRow[] {
  return rows.map((row) => ({
    row_code: row.row_code,
    row_name: row.row_name,
    unadjusted: row.unadjusted ?? null,
    aje_dr: row.aje_dr ?? null,
    aje_cr: row.aje_cr ?? null,
    rcl_dr: row.rcl_dr ?? null,
    rcl_cr: row.rcl_cr ?? null,
    formula_detached: row.formula_detached === true,
    manual_rcl_dr: row.manual_rcl_dr === true,
    manual_rcl_cr: row.manual_rcl_cr === true,
  }))
}

/** 合并影子表数据；只有带手工标记的 RJE 格可以覆盖非空的审批计算值。 */
export function mergeSavedTbSummaryRows(
  currentRows: TbSummaryPersistRow[],
  savedRows: TbSummaryPersistRow[],
): void {
  const byCode = new Map(savedRows.filter((row) => row.row_code).map((row) => [row.row_code, row]))
  for (const row of currentRows) {
    const saved = byCode.get(row.row_code)
    if (!saved) continue
    if (saved.formula_detached) {
      row.formula_detached = true
      if (saved.unadjusted !== null && saved.unadjusted !== undefined) row.unadjusted = saved.unadjusted
    } else if (!row.unadjusted && saved.unadjusted) {
      row.unadjusted = saved.unadjusted
    }

    const legacyDetached = saved.formula_detached === true
      && saved.manual_rcl_dr === undefined
      && saved.manual_rcl_cr === undefined
    if (saved.manual_rcl_dr === true || (legacyDetached && saved.rcl_dr != null)) {
      row.manual_rcl_dr = true
      row.rcl_dr = saved.rcl_dr ?? null
    } else if (!row.rcl_dr && saved.rcl_dr) {
      row.rcl_dr = saved.rcl_dr
    }
    if (saved.manual_rcl_cr === true || (legacyDetached && saved.rcl_cr != null)) {
      row.manual_rcl_cr = true
      row.rcl_cr = saved.rcl_cr ?? null
    } else if (!row.rcl_cr && saved.rcl_cr) {
      row.rcl_cr = saved.rcl_cr
    }
  }
}

function persistenceError(error: any): string {
  if (error instanceof WorksheetVersionConflictError) return '自动保存冲突：数据已被他人修改，请刷新后再保存'
  const status = error?.response?.status
  if (status === 403) return '自动保存失败：没有编辑权限'
  if (status === 423) return '自动保存失败：项目已归档'
  const detail = error?.response?.data?.detail ?? error?.response?.data?.message
  if (typeof detail === 'string' && detail.trim()) return `自动保存失败：${detail}`
  return '自动保存失败，请点击保存重试'
}
export function useTbSummaryPersistence(options: TbSummaryPersistenceOptions) {
  const saving = ref(false)
  const dirty = ref(false)
  const blocked = ref(false)
  const errorMessage = ref('')
  const savedRevision = ref(0)
  const delay = options.delayMs ?? 200
  const load = options.load ?? loadWorksheetData
  const save = options.save ?? saveWorksheetData
  const versions = new Map<string, number>()
  const generations = new Map<string, number>()
  let loadedKey = ''
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: PendingSave | null = null
  let inFlight: Promise<boolean> | null = null
  let revision = 0
  let disposed = false

  function clearTimer(): void {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function prime(context: TbSummaryPersistContext, version: number): void {
    const key = tbSummaryContextKey(context)
    generations.set(key, (generations.get(key) ?? 0) + 1)
    versions.set(key, version)
    loadedKey = key
    if (pending?.key === key) {
      pending = null
      clearTimer()
    }
    blocked.value = false
    errorMessage.value = ''
    dirty.value = pending !== null
  }

  function invalidate(context: TbSummaryPersistContext): void {
    const key = tbSummaryContextKey(context)
    generations.set(key, (generations.get(key) ?? 0) + 1)
    versions.delete(key)
    if (loadedKey === key) loadedKey = ''
    if (pending?.key === key) {
      pending = null
      clearTimer()
    }
    blocked.value = false
    errorMessage.value = ''
    dirty.value = pending !== null
  }

  function capture(): PendingSave | null {
    if (disposed || !options.canSave()) return null
    const value = options.getContext()
    if (!value) return null
    const context = { ...value }
    const key = tbSummaryContextKey(context)
    if (key !== loadedKey || !versions.has(key)) return null
    return {
      key,
      context,
      generation: generations.get(key) ?? 0,
      revision: ++revision,
      rows: serializeTbSummaryRows(options.getRows()),
    }
  }

  function queue(): boolean {
    const job = capture()
    if (!job) {
      if (options.canSave()) {
        dirty.value = true
        errorMessage.value = '自动保存暂不可用，请刷新试算平衡表后重试'
      }
      return false
    }
    pending = job
    dirty.value = true
    if (blocked.value) return false
    clearTimer()
    timer = setTimeout(() => { timer = null; void drain() }, delay)
    return true
  }
  async function runPending(): Promise<boolean> {
    while (pending && !blocked.value && !disposed) {
      const job = pending
      pending = null
      if ((generations.get(job.key) ?? 0) !== job.generation) continue
      const expectedVersion = versions.get(job.key)
      if (expectedVersion === undefined) {
        dirty.value = true
        blocked.value = true
        errorMessage.value = '自动保存暂不可用，请刷新试算平衡表后重试'
        return false
      }
      saving.value = true
      try {
        const result = await save(
          job.context.projectId,
          job.context.year,
          job.context.sheetKey,
          { rows: job.rows },
          expectedVersion,
        )
        if (disposed) return false
        if ((generations.get(job.key) ?? 0) === job.generation) {
          versions.set(job.key, result.version)
          savedRevision.value = job.revision
          errorMessage.value = ''
        }
      } catch (error) {
        if (!disposed && (generations.get(job.key) ?? 0) === job.generation) {
          dirty.value = true
          blocked.value = true
          errorMessage.value = persistenceError(error)
          options.onError?.(errorMessage.value, error)
        }
        return false
      } finally {
        saving.value = false
      }
    }
    dirty.value = blocked.value || pending !== null
    return !dirty.value
  }

  async function drain(): Promise<boolean> {
    clearTimer()
    if (inFlight) {
      const result = await inFlight
      if (pending && !blocked.value && !disposed) return drain()
      return result && !dirty.value
    }
    inFlight = runPending()
    try {
      return await inFlight
    } finally {
      inFlight = null
    }
  }

  async function flush(force = false): Promise<boolean> {
    if (force) {
      blocked.value = false
      errorMessage.value = ''
      const job = capture()
      if (!job) {
        if (options.canSave()) errorMessage.value = '保存暂不可用，请刷新试算平衡表后重试'
        return false
      }
      pending = job
      dirty.value = true
    }
    if (!pending && !inFlight) return !dirty.value
    return drain()
  }

  async function hydrate(context: TbSummaryPersistContext): Promise<boolean> {
    const key = tbSummaryContextKey(context)
    const loaded = await load(context.projectId, context.year, context.sheetKey)
    const current = options.getContext()
    if (disposed || !current || tbSummaryContextKey(current) !== key) return false
    const version = loaded.versions[context.sheetKey]
    if (loaded.status === 'error' || typeof version !== 'number') {
      invalidate(context)
      return false
    }
    prime(context, version)
    const savedRows = Array.isArray(loaded.data?.rows) ? loaded.data.rows : []
    mergeSavedTbSummaryRows(options.getRows(), savedRows)
    return true
  }

  function discard(): void {
    const context = options.getContext()
    if (context) {
      invalidate(context)
      return
    }
    clearTimer()
    pending = null
    blocked.value = false
    errorMessage.value = ''
    dirty.value = false
  }

  function dispose(): void {
    disposed = true
    clearTimer()
    pending = null
  }

  return {
    saving,
    dirty,
    blocked,
    errorMessage,
    savedRevision,
    prime,
    invalidate,
    queue,
    flush,
    hydrate,
    discard,
    dispose,
    versionOf: (context: TbSummaryPersistContext) => versions.get(tbSummaryContextKey(context)),
  }
}
