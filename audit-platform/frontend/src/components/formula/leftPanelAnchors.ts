/**
 * leftPanelAnchors.ts — 公式管理中心左栏「数据源」当前页 anchors 的单一真源
 *                        （Task 3.2 / ADR-FMC-05）
 *
 * 背景（修复的缺陷 P1-左栏非当前页地址）：
 *   旧左栏默认调 `useAcnr().listSheets()` 建 TB/report/note/wp/aux/合并/表间/数据质量
 *   **全局五域树**（`acnrDrivenTree`，§1 #6 实测），与右栏「当前页公式」口径错位 ——
 *   用户在某一张 sheet 上打开公式管理，左栏却列出全平台所有 sheet 的地址。
 *
 * 本模块把左栏默认行为收敛为**只显精确当前 sheet 的 `addr_id`**（ADR-FMC-05）：
 *   - 默认模式 = 当前页 anchors：据 `{project_id, wp_id, sheet_uid}` 调当前 sheet 的
 *     anchors（`GET /api/acnr/anchors?wp_code&sheet` 即 `useAcnr().listCells`），
 *     只显属于精确当前 sheet（`{wp_code}/{sheet}` 命名空间）的 `addr_id`。
 *   - 「全局浏览」是**独立显式按钮**触发的模式，**不**作为缺上下文时的默认回退。
 *   - 当前页 location identity（project_id + wp_id + sheet_uid）**任一缺失 → fail-closed**：
 *     返回空集 + 显式告警，**不退回全局树**（ADR-FMC-05 硬约束）。
 *   - 左栏每行带同一 location identity（projectId/wpId/sheetUid），与右栏对齐。
 *
 * 纯逻辑抽离（仿 Task 1.2 sheetIdentityMatch.ts / 1.4 formulaRowKind.ts）：本模块不依赖
 * 组件挂载、不发请求；anchors 数据由调用方（FormulaManagerDialog）经 useAcnr().listCells
 * 取得后传入，便于单测直接断言模式决策与树构建、变异反证。
 */

import type { AcnrCellEntry } from '@/services/acnr/useAcnr'

/** 左栏三种模式。current-sheet 为默认；global-browse 为显式按钮；fail-closed 为缺身份兜底。 */
export type LeftPanelMode = 'current-sheet' | 'global-browse' | 'fail-closed'

/** 当前页 location identity（左右栏每行共享的同一身份）。 */
export interface LocationIdentity {
  projectId: string
  wpId: string
  /** 当前 sheet 唯一标识（本仓口径 = 解析后的结构化 sheet_code，如 `E1-1`）。 */
  sheetUid: string
}

/** 左栏当前页 anchor 树节点（每行带同一 location identity）。 */
export interface LeftPanelAnchorNode {
  key: string
  label: string
  icon: string
  /** ACNR addr_id（精确当前 sheet 命名空间内）。 */
  _addrId: string
  /** 左右栏对齐用：同一 location identity 挂在每行。 */
  _identity: LocationIdentity
  /** cell 语义/地址元信息（供右侧或 tooltip 用）。 */
  _cellAddress?: string | null
  _semanticLabel?: string | null
}

/** 左栏默认加载结果（current-sheet 或 fail-closed）。 */
export interface LeftPanelLoadResult {
  mode: LeftPanelMode
  nodes: LeftPanelAnchorNode[]
  /** fail-closed 时的显式告警文案（非 fail-closed 为空串）。 */
  warning: string
  /** 命中的 location identity（current-sheet 模式有值；fail-closed 为 null）。 */
  identity: LocationIdentity | null
}

/**
 * 判定当前页 location identity 是否完整（project_id + wp_id + sheet_uid 三者齐备）。
 * 任一为空/空白 → 不完整（调用方据此 fail-closed）。
 */
export function hasCompleteLocationIdentity(
  identity: Partial<LocationIdentity> | null | undefined,
): identity is LocationIdentity {
  if (!identity) return false
  const pid = (identity.projectId || '').trim()
  const wid = (identity.wpId || '').trim()
  const uid = (identity.sheetUid || '').trim()
  return !!pid && !!wid && !!uid
}

/**
 * 决定左栏默认模式。
 *   - identity 完整 → 'current-sheet'（默认只显当前页 anchors）。
 *   - identity 不完整 → 'fail-closed'（空集 + 告警，**不退全局树**）。
 * 注意：'global-browse' **不**由本函数产出 —— 它只能由用户点「全局浏览」按钮显式进入，
 * 故本函数永不返回 'global-browse'（避免缺身份被静默兜底成全局浏览）。
 */
export function decideLeftPanelMode(
  identity: Partial<LocationIdentity> | null | undefined,
): Exclude<LeftPanelMode, 'global-browse'> {
  return hasCompleteLocationIdentity(identity) ? 'current-sheet' : 'fail-closed'
}

/** fail-closed 告警文案（缺当前页身份，不列任何地址、不退全局）。 */
export function buildFailClosedWarning(
  identity: Partial<LocationIdentity> | null | undefined,
): string {
  const missing: string[] = []
  if (!(identity?.projectId || '').trim()) missing.push('项目')
  if (!(identity?.wpId || '').trim()) missing.push('底稿实例')
  if (!(identity?.sheetUid || '').trim()) missing.push('当前页')
  const miss = missing.length ? missing.join('、') : '当前页身份'
  return (
    `缺少${miss}标识，无法定位当前页地址 —— 左栏已置空（不回退全局地址树）。` +
    `请从目标底稿页面打开公式管理，或点「全局浏览」查看全平台地址。`
  )
}

/**
 * 从当前 sheet 的 anchors（`useAcnr().listCells` 返回的 AcnrCellEntry[]）构建左栏节点。
 * 每个节点带同一 location identity（左右栏对齐）；anchors 本就来自
 * `GET /api/acnr/anchors?wp_code&sheet`，命名空间已是精确当前 sheet（`{wp_code}/{sheet}`）。
 *
 * 防御：丢弃无 addr_id 的条目、deprecated 条目（目录已弃用的坐标不进当前页选址）。
 */
export function buildCurrentSheetAnchorNodes(
  cells: AcnrCellEntry[] | null | undefined,
  identity: LocationIdentity,
): LeftPanelAnchorNode[] {
  if (!Array.isArray(cells) || !cells.length) return []
  const nodes: LeftPanelAnchorNode[] = []
  const seen = new Set<string>()
  for (const c of cells) {
    const addrId = (c?.addr_id || '').trim()
    if (!addrId) continue
    if (c?.deprecated) continue
    if (seen.has(addrId)) continue
    seen.add(addrId)
    const label = (c.semantic_label || c.cell_address || addrId) as string
    nodes.push({
      key: `anchor_${addrId}`,
      label,
      icon: '',
      _addrId: addrId,
      _identity: identity,
      _cellAddress: c.cell_address ?? null,
      _semanticLabel: c.semantic_label ?? null,
    })
  }
  return nodes
}

/**
 * 左栏默认加载的唯一入口：据 identity + 当前 sheet anchors 产出 current-sheet 或 fail-closed。
 *
 * - identity 完整：mode='current-sheet'，nodes=当前页 anchors（每行带 identity），warning=''。
 * - identity 不完整：mode='fail-closed'，nodes=[]，warning=显式告警，identity=null。
 *   **绝不**在此退回全局树（全局浏览只能走 buildGlobalBrowse* 的显式按钮）。
 *
 * @param identity 当前页 location identity（project_id/wp_id/sheet_uid）
 * @param cellsLoader 异步取当前 sheet anchors 的函数（注入 useAcnr().listCells 以便单测）
 */
export async function loadCurrentSheetLeftPanel(
  identity: Partial<LocationIdentity> | null | undefined,
  cellsLoader: () => Promise<AcnrCellEntry[]>,
): Promise<LeftPanelLoadResult> {
  if (!hasCompleteLocationIdentity(identity)) {
    return {
      mode: 'fail-closed',
      nodes: [],
      warning: buildFailClosedWarning(identity),
      identity: null,
    }
  }
  const cells = await cellsLoader()
  return {
    mode: 'current-sheet',
    nodes: buildCurrentSheetAnchorNodes(cells, identity),
    warning: '',
    identity,
  }
}
