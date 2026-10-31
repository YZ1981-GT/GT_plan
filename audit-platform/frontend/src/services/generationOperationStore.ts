import { newUuid } from '@/utils/uuid'
export interface StoredGenerationOperation {
  projectId: string
  operationId: string
  requestKey: string
  templateSetId: string
  year: number
  codes: string[]
  savedAt: number
}

const PREFIX = 'gt:wp-generation-operation:'

export function generationRequestKey(input: {
  projectId: string
  templateSetId: string
  year: number
  codes: string[]
}): string {
  return JSON.stringify({
    projectId: input.projectId,
    templateSetId: input.templateSetId,
    year: input.year,
    codes: [...new Set(input.codes.map((code) => code.trim().toUpperCase()).filter(Boolean))].sort(),
  })
}

function storage(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage
  } catch {
    return null
  }
}

export function loadGenerationOperation(projectId: string, requestKey?: string): StoredGenerationOperation | null {
  const raw = storage()?.getItem(`${PREFIX}${projectId}`)
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as StoredGenerationOperation
    const requestMatches = requestKey == null || value.requestKey === requestKey
    return value.projectId === projectId && requestMatches && !!value.operationId
      && !!value.templateSetId && Number.isInteger(value.year) && Array.isArray(value.codes)
      ? value : null
  } catch {
    return null
  }
}

export function rememberGenerationOperation(value: StoredGenerationOperation): void {
  storage()?.setItem(`${PREFIX}${value.projectId}`, JSON.stringify(value))
}

export function clearGenerationOperation(projectId: string, operationId: string): void {
  const store = storage()
  if (!store) return
  const key = `${PREFIX}${projectId}`
  try {
    const current = JSON.parse(store.getItem(key) || 'null') as StoredGenerationOperation | null
    if (current?.operationId === operationId) store.removeItem(key)
  } catch {
    store.removeItem(key)
  }
}

export function newGenerationOperationId(): string {
  return newUuid()
}
