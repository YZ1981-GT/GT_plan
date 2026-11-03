/**
 * 表格 → 内核登记（spec excel-style-table-editing ADR-1 / ADR-3）。
 *
 * 内核按「所属组件实例」登记：el-table 用 ElTable 的内部实例（全局 mixin 在挂载时 attach），
 * 原生表格用 GtGridTable 的实例。编辑器按父链找到实例，再从这里拿内核。
 */
import type { ComponentInternalInstance } from 'vue'
import { GridKernel } from './GridKernel'
import { buildElTableGeometry, buildRawTableGeometry } from './gridDom'
import type { CellContext } from './cellDetect'

const byOwner = new WeakMap<object, GridKernel>()

interface ElTableInternal extends ComponentInternalInstance {
  store?: { states?: { columns?: { value?: Array<{ id: string; label?: string }> } } }
}

export function kernelForElTable(table: ComponentInternalInstance): GridKernel {
  let k = byOwner.get(table)
  if (!k) {
    k = new GridKernel({
      kind: 'el-table',
      owner: table,
      geometry: () => {
        const cols = (table as ElTableInternal).store?.states?.columns?.value ?? []
        return buildElTableGeometry(
          (table.vnode.el as HTMLElement | null) ?? null,
          cols.map((c) => ({ id: c.id, label: c.label })),
        )
      },
    })
    byOwner.set(table, k)
  }
  return k
}

export function kernelForRawTable(owner: ComponentInternalInstance, getTable: () => HTMLTableElement | null): GridKernel {
  let k = byOwner.get(owner)
  if (!k) {
    k = new GridKernel({ kind: 'raw-table', owner, geometry: () => buildRawTableGeometry(getTable()) })
    byOwner.set(owner, k)
  }
  return k
}

/** 编辑器所在表格的内核；el-table 还没被 mixin attach（例如单测没装插件）时就地 attach。 */
export function kernelForContext(ctx: CellContext | null): GridKernel | null {
  if (!ctx) return null
  if (ctx.kind === 'el-table') {
    const k = kernelForElTable(ctx.table)
    const el = ctx.table.vnode.el as HTMLElement | null
    if (!k.root && el instanceof HTMLElement) k.attach(el)
    return k
  }
  if (ctx.kind === 'raw-table') return byOwner.get(ctx.grid) ?? null
  return null
}
