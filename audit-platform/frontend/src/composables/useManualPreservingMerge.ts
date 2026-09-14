export interface DisclosureCell<T = unknown> {
  value?: T
  manual_value?: T
  manual?: boolean
  mode?: string
  provenance?: Array<Record<string, unknown>>
  trace?: Array<Record<string, unknown>>
  addr_id?: string
  [key: string]: unknown
}

type AnyRecord = Record<string, any>

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue)
  if (value && typeof value === 'object') {
    return Object.keys(value as AnyRecord).sort().reduce<AnyRecord>((out, key) => {
      out[key] = stableValue((value as AnyRecord)[key])
      return out
    }, {})
  }
  return value
}

function appendUnique<T>(current: T[] | undefined, incoming: T[] | undefined): T[] {
  const seen = new Set<string>()
  return [...(current ?? []), ...(incoming ?? [])].filter((item) => {
    const key = JSON.stringify(stableValue(item))
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function isManual(cell: unknown, mode?: string): boolean {
  return mode === 'manual'
    || (!!cell && typeof cell === 'object'
      && ((cell as DisclosureCell).manual === true || (cell as DisclosureCell).mode === 'manual'))
}

export function mergeDisclosureCell<T>(
  current: DisclosureCell<T>,
  incoming: DisclosureCell<T>,
): DisclosureCell<T> {
  const manual = isManual(current)
  const merged: DisclosureCell<T> = {
    ...current,
    ...incoming,
    value: manual ? current.value : incoming.value,
    provenance: appendUnique(current.provenance, incoming.provenance),
    trace: appendUnique(current.trace, incoming.trace),
    addr_id: current.addr_id ?? incoming.addr_id,
  }
  if (manual) {
    merged.manual = true
    merged.mode = 'manual'
    if ('manual_value' in current) merged.manual_value = current.manual_value
  }
  return merged
}

function mergeCellValue(current: unknown, incoming: unknown, currentMode?: string): unknown {
  if (isManual(current, currentMode)) return current
  if (current && incoming && typeof current === 'object' && typeof incoming === 'object') {
    return mergeDisclosureCell(current as DisclosureCell, incoming as DisclosureCell)
  }
  return incoming
}

function rowIdentity(row: AnyRecord, index: number): string {
  return String(row.row_id ?? row.id ?? row.label ?? index)
}

function mergeRow(current: AnyRecord | undefined, incoming: AnyRecord): AnyRecord {
  if (!current) return incoming
  const currentModes = current._cell_modes ?? {}
  const incomingModes = incoming._cell_modes ?? {}
  const mergedModes = { ...currentModes, ...incomingModes }
  const currentValues = current.cells ?? current.values ?? []
  const incomingValues = incoming.cells ?? incoming.values ?? []
  const values = incomingValues.map((cell: unknown, index: number) => {
    if (currentModes[String(index)] === 'manual') mergedModes[String(index)] = 'manual'
    return mergeCellValue(currentValues[index], cell, currentModes[String(index)])
  })
  const metaKeys = new Set([
    ...Object.keys(current._cell_meta ?? {}),
    ...Object.keys(incoming._cell_meta ?? {}),
  ])
  const mergedMeta: AnyRecord = {}
  metaKeys.forEach((key) => {
    mergedMeta[key] = mergeDisclosureCell(current._cell_meta?.[key] ?? {}, incoming._cell_meta?.[key] ?? {})
  })
  const merged = { ...current, ...incoming, _cell_modes: mergedModes, _cell_meta: mergedMeta }
  if (Array.isArray(incoming.cells)) merged.cells = values
  else merged.values = values
  return merged
}

function mergeRows(current: AnyRecord[] | undefined, incoming: AnyRecord[] | undefined): AnyRecord[] | undefined {
  if (!incoming) return incoming
  const byId = new Map((current ?? []).map((row, index) => [rowIdentity(row, index), row]))
  return incoming.map((row, index) => mergeRow(byId.get(rowIdentity(row, index)), row))
}

function tableIdentity(table: AnyRecord, index: number): string {
  return String(table.table_id ?? table.id ?? table.name ?? index)
}

export function mergeQueryIntoDisclosure<T extends AnyRecord>(current: T, incoming: T): T {
  const merged: AnyRecord = { ...current, ...incoming }
  if (Array.isArray(incoming._tables)) {
    const currentTables = new Map(
      (current._tables ?? []).map((table: AnyRecord, index: number) => [tableIdentity(table, index), table]),
    )
    merged._tables = incoming._tables.map((table: AnyRecord, index: number) => ({
      ...currentTables.get(tableIdentity(table, index)),
      ...table,
      rows: mergeRows(currentTables.get(tableIdentity(table, index))?.rows, table.rows),
    }))
  } else if (Array.isArray(incoming.rows)) {
    merged.rows = mergeRows(current.rows, incoming.rows)
  }
  return merged as T
}

export function markDisclosureCellManual<T extends AnyRecord>(
  row: T,
  columnIndex: number,
  value?: unknown,
): T {
  const key = String(columnIndex)
  const result: AnyRecord = {
    ...row,
    _cell_modes: { ...(row._cell_modes ?? {}), [key]: 'manual' },
  }
  const source = row.cells ?? row.values ?? []
  const values = [...source]
  const cell = source[columnIndex]
  if (cell && typeof cell === 'object') {
    values[columnIndex] = {
      ...cell,
      ...(value !== undefined ? { value } : {}),
      manual: true,
      mode: 'manual',
    }
  } else if (value !== undefined) {
    values[columnIndex] = value
  }
  if (Array.isArray(row.cells)) result.cells = values
  else result.values = values
  return result as T
}
