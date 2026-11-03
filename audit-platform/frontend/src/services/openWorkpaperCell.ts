/**
 * openWorkpaperCell — 打开底稿编辑器并定位到 sheet / 单元格（spec wp-deeplink-locate-coverage-closure 需求 3）。
 *
 * 溯源弹窗（试算表 / 未更正错报 / 合并 / 报表）、溯源面板的跨底稿节点、复核意见列表、附注→底稿穿透共用：
 * - `wpId` 是实例 UUID 时直接用；否则按 `wpCode` 经 `resolveWorkpaperByCode` 取本项目实例；sheet 级编码
 *   （如 D2-1）在本项目没有独立底稿时回落父底稿（D2），并把原编码当作 `sheet`（与后端 bind_wp_code 同口径）；
 * - 成功 `router.push` 到编辑器并带 `?sheet=&cell=`（编辑器交给渲染器 / Univer 定位），返回 null；
 * - 取不到返回中文原因，由调用方提示。
 * 不再发 `workpaper:locate-cell` 事件：这些入口所在页面没有渲染器，事件无人接收。
 */
import type { Router } from 'vue-router'
import { resolveWorkpaperByCode } from './resolveWorkpaperByCode'
import { workpaperEditorRoute } from '@/composables/useWorkpaperNavigation'

export interface WorkpaperCellTarget {
  projectId: string
  wpId?: string | null
  wpCode?: string | null
  sheet?: string | null
  cell?: string | null
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SHEET_CODE_RE = /^([A-Z]\d+)-[0-9A-Za-z-]+$/

export const OPEN_WORKPAPER_MESSAGES = {
  noProject: '缺少项目，无法打开底稿',
  noCode: '缺少底稿编码，无法打开底稿',
  notFound: (code: string) => `本项目未找到底稿 ${code}（可能尚未生成）`,
} as const

/** 编辑器深链参数（空值不带） */
export function workpaperCellQuery(target: Pick<WorkpaperCellTarget, 'sheet' | 'cell'>): Record<string, string> | undefined {
  const query: Record<string, string> = {}
  const sheet = String(target.sheet ?? '').trim()
  const cell = String(target.cell ?? '').trim()
  if (sheet) query.sheet = sheet
  if (cell) query.cell = cell
  return Object.keys(query).length ? query : undefined
}

export async function openWorkpaperCell(
  router: Pick<Router, 'push'>, target: WorkpaperCellTarget,
): Promise<string | null> {
  const projectId = String(target.projectId ?? '').trim()
  if (!projectId) return OPEN_WORKPAPER_MESSAGES.noProject
  let wpId = String(target.wpId ?? '').trim()
  let sheet = target.sheet ?? null
  if (!UUID_RE.test(wpId)) {
    const wpCode = String(target.wpCode ?? '').trim()
    if (!wpCode) return OPEN_WORKPAPER_MESSAGES.noCode
    let found = await resolveWorkpaperByCode(projectId, wpCode, true)
    const parent = SHEET_CODE_RE.exec(wpCode)?.[1]
    if (!found && parent) {
      found = await resolveWorkpaperByCode(projectId, parent, true)
      if (found && !String(sheet ?? '').trim()) sheet = wpCode
    }
    if (!found) return OPEN_WORKPAPER_MESSAGES.notFound(wpCode)
    wpId = found.wpId
  }
  await router.push(workpaperEditorRoute(projectId, wpId, workpaperCellQuery({ sheet, cell: target.cell })))
  return null
}
