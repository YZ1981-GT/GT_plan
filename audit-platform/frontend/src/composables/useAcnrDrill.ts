/**
 * useAcnrDrill — 高级查询结果列「下钻」到底稿格（advanced-query-module Task 18.2）
 *
 * 职责（对应 design.md §Components 3 ColumnMeta / §Architecture CHIP -->|resolveIndex| FR --> JR）：
 * - `normalizeColumns`：把后端 `QueryResult.columns`（`ColumnMeta[]` 或 legacy `string[]`）
 *   归一为前端统一列元数据 `QueryColumnMeta{key,title,addrId,drillable,dtype}`。
 * - `cellAddrId`：裁定某行某列单元格用于下钻的 addr_id（优先行级 `${key}__addr_id`，
 *   回退列级 addr_id）。
 * - `addrIdToIndexRef`：把 ACNR addr_id `{wp_code}/{sheet_code}/{coordinate_key}` 转成
 *   `GtIndexChip` 可解析的索引语法（`cell:{sheet}!{coord}` / `wp:{sheet}`）。
 * - `useAcnrDrill().drill(addrId)`：点击下钻——**经 ACNR resolve 拿 jump_route 跳转**
 *   （不自行拼底稿路由，R4.4），并在**新标签页**打开以**保持当前查询结果视图不变**
 *   （R4.2）；jump_route 已失效 → 提示「目标已失效」、视图不变（R4.6）；下钻目标
 *   越权 → 后端 403 → 提示权限错误、不泄露内容（R4.7）。
 *
 * ACNR 引用不重写：消费 `useAcnr().resolveIndex`（L1 拿 jump_route 模板 + 存在性）与
 * `/api/acnr/resolve-instance`（唯一 wp_id 出口，填充 `{wp_id}` 得到可导航路由并触发
 * 项目归属校验）。二者均为 ACNR 已实现出口。
 *
 * _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
 */
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useAcnr } from '@/services/acnr/useAcnr'

// ─── 列元数据 ─────────────────────────────────────────────────────────────────

/** 前端统一结果列元数据（归一自后端 ColumnMeta / legacy string 列）。 */
export interface QueryColumnMeta {
  key: string
  title: string
  /** 单一可解析源格产生时携带（R4.1）；否则 null → 不可下钻普通文本列（R4.5）。 */
  addrId: string | null
  /** drillable ⇔ addrId 非空（R4.1 / R4.5）。 */
  drillable: boolean
  dtype: string
}

/** 后端 ColumnMeta 原始形态（部分字段可选，容错解析）。 */
interface RawColumnMeta {
  key?: string
  title?: string
  addr_id?: string | null
  drillable?: boolean
  dtype?: string
}

/**
 * 归一后端 `QueryResult.columns` 为 `QueryColumnMeta[]`。
 *
 * 兼容两种形态：
 * - 新契约：`ColumnMeta[]`（对象，含 `key/title/addr_id/drillable/dtype`）。
 * - legacy：`string[]`（列名）→ 不可下钻普通文本列。
 *
 * 不变式：`drillable === (addrId != null)`（以 addr_id 为唯一依据，忽略后端可能
 * 不一致的 drillable 标记，R4.1 / R4.5）。
 */
export function normalizeColumns(
  columns: Array<string | RawColumnMeta> | null | undefined,
): QueryColumnMeta[] {
  if (!Array.isArray(columns)) return []
  const out: QueryColumnMeta[] = []
  for (const col of columns) {
    if (typeof col === 'string') {
      out.push({ key: col, title: col, addrId: null, drillable: false, dtype: 'text' })
      continue
    }
    if (col && typeof col === 'object' && typeof col.key === 'string') {
      const addrId = col.addr_id != null && col.addr_id !== '' ? String(col.addr_id) : null
      out.push({
        key: col.key,
        title: col.title || col.key,
        addrId,
        drillable: addrId != null,
        dtype: col.dtype || 'text',
      })
    }
  }
  return out
}

/**
 * 裁定某行某列单元格用于下钻的 addr_id。
 *
 * 优先行级 `${key}__addr_id`（透视/明细可携带逐格源身份），回退列级 addr_id
 * （单源列，R4.1）。返回 null → 该格不可下钻。
 */
export function cellAddrId(
  row: Record<string, unknown> | null | undefined,
  meta: QueryColumnMeta,
): string | null {
  if (row && typeof row === 'object') {
    const perCell = row[`${meta.key}__addr_id`]
    if (typeof perCell === 'string' && perCell) return perCell
  }
  return meta.addrId
}

// ─── addr_id → 索引语法 ────────────────────────────────────────────────────────

/**
 * ACNR addr_id `{wp_code}/{sheet_code}/{coordinate_key}` → GtIndexChip 可解析索引语法。
 *
 * - 三段（cell 级）→ `cell:{sheet_code}!{coordinate_key}`（parseIndexRef → ns=cell）。
 * - 两段（sheet 级）→ `wp:{sheet_code}`。
 * - 一段 → `wp:{wp_code}`。
 * - 非法 → null。
 *
 * 说明：直接把含 `/` 的 addr_id 传给 `GtIndexChip.value` 会被其 `parseIndexRef`
 * 误判为「多目标」（以 `/` 分隔），故统一转为单目标索引语法。
 */
export function addrIdToIndexRef(addrId: string | null | undefined): string | null {
  if (!addrId || typeof addrId !== 'string') return null
  const parts = addrId.split('/').map((s) => s.trim()).filter(Boolean)
  if (parts.length >= 3) {
    const sheet = parts[1]
    const coord = parts.slice(2).join('/')
    return `cell:${sheet}!${coord}`
  }
  if (parts.length === 2) return `wp:${parts[1]}`
  if (parts.length === 1) return `wp:${parts[0]}`
  return null
}

/** 解析 addr_id 为 {parent, sheet, coord}（供 resolve-instance 填 wp_id）。 */
function parseAddrId(addrId: string): { parent: string; sheet: string; coord: string } {
  const parts = addrId.split('/').map((s) => s.trim())
  const parent = parts[0] || ''
  const sheet = parts[1] || parent
  const coord = parts.slice(2).join('/') || ''
  return { parent, sheet, coord }
}

// ─── 下钻 ─────────────────────────────────────────────────────────────────────

/**
 * 结果列下钻能力。
 *
 * @param getProjectId 返回当前查询上下文的 project_id（用于 resolve-instance 填 wp_id
 *   与项目归属校验）。无 project_id 时下钻按「目标已失效」优雅处理。
 */
export function useAcnrDrill(getProjectId: () => string) {
  const { resolveIndex } = useAcnr()

  /**
   * 下钻到 addr_id 对应的底稿格。
   *
   * 流程（R4.2 / R4.4 / R4.6 / R4.7）：
   * 1. `resolveIndex(index_ref)` 校验存在性并取 jump_route 模板（L1）。found=false → 失效。
   * 2. jump_route 含 `{wp_id}` 模板 → 经 `/api/acnr/resolve-instance` 填 wp_id 得到可
   *    导航路由（唯一 wp_id 出口）；not found → 失效；403 → 权限错误（不泄露内容）。
   * 3. 用 ACNR 返回的 jump_route（仅替换 `{project_id}` 占位符 + 追加 cell 高亮），
   *    在**新标签页**打开，保持当前查询结果视图不变。
   */
  async function drill(addrId: string | null | undefined): Promise<void> {
    if (!addrId) {
      ElMessage.warning('目标已失效')
      return
    }
    const projectId = getProjectId()
    const { parent, sheet, coord } = parseAddrId(addrId)
    const indexRef = addrIdToIndexRef(addrId)
    if (!indexRef) {
      ElMessage.warning('目标已失效')
      return
    }

    // 1) 经 ACNR resolveIndex 校验存在性 + 拿 jump_route（R4.4：用 resolve 返回的路由）
    const res = await resolveIndex(indexRef)
    if (!res.found) {
      // addr_id 不可解析 / 目标已删除 → 提示失效、视图不变（R4.6）
      ElMessage.warning('目标已失效')
      return
    }

    let route = res.jump_route || ''

    // 2) L1 jump_route 为模板（{wp_id} 未填）→ 经 resolve-instance 填 wp_id（wp_id 出口）
    if (!route || route.includes('{wp_id}')) {
      if (!projectId) {
        ElMessage.warning('目标已失效')
        return
      }
      try {
        const resp = await http.get('/api/acnr/resolve-instance', {
          params: { project_id: projectId, parent, sheet_code: sheet },
          _silent: true,
        } as any)
        const inst = (resp?.data ?? resp) as { found?: boolean; jump_route?: string }
        if (!inst?.found || !inst.jump_route) {
          ElMessage.warning('目标已失效') // jump_route 已失效（目标底稿未生成/已删除，R4.6）
          return
        }
        route = inst.jump_route
      } catch (e) {
        const status = (e as { response?: { status?: number }; status?: number })?.response?.status
          ?? (e as { status?: number })?.status
        if (status === 403) {
          // 下钻目标越权 → 拒绝跳转、不泄露内容（R4.7）
          ElMessage.error('无权访问下钻目标底稿，已拒绝跳转')
        } else {
          ElMessage.warning('目标已失效') // 其它解析失败按失效处理，视图不变（R4.6）
        }
        return
      }
    }

    if (projectId) route = route.replace('{project_id}', projectId)
    // 追加单元格高亮（保留 ACNR 提供的底稿+sheet 路由，不自行拼底稿路由）
    if (coord) {
      route += (route.includes('?') ? '&' : '?') + `cell=${encodeURIComponent(coord)}`
    }
    // 新标签页打开，保持当前查询结果视图不变（R4.2）
    window.open(route, '_blank', 'noopener')
  }

  return { drill }
}
