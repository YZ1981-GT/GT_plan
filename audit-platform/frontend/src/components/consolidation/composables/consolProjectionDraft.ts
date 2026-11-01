import { clonePlain } from '@/utils/cloneable'

interface ProjectionCompany {
  name: string
  code?: string
}

export interface ProjectionDraftRows {
  overrides: Record<string, Record<string, unknown>>
  manualRows: Record<string, unknown>[]
}

const IDENTITY_FIELDS = new Set(['companyName', 'companyCode', '_editable', '_manual'])

/**
 * 将已保存的投影表拆回“自动行覆盖 + 手工行”。批 3 接 canonical projection 前，
 * 这里只保证现有 JSON 可逐值恢复，不把持久化值反推成第二份分录事实。
 */
export function splitPersistedProjectionRows(
  companies: ProjectionCompany[],
  savedRows: unknown,
): ProjectionDraftRows {
  const overrides: Record<string, Record<string, unknown>> = {}
  const manualRows: Record<string, unknown>[] = []
  if (!Array.isArray(savedRows)) return { overrides, manualRows }

  for (const raw of savedRows) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue
    const row = raw as Record<string, unknown>
    const code = String(row.companyCode || '')
    const name = String(row.companyName || '')
    const company = companies.find((item) => (code && item.code === code) || (!code && item.name === name))
    if (!company || row._manual === true) {
      manualRows.push(clonePlain(row))
      continue
    }
    const values: Record<string, unknown> = {}
    for (const [field, value] of Object.entries(row)) {
      if (!IDENTITY_FIELDS.has(field)) values[field] = clonePlain(value)
    }
    overrides[company.name] = values
  }
  return { overrides, manualRows }
}
