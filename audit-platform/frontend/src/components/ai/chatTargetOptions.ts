/**
 * 「采纳到…」「转存为笔记」对话框的数据加载与选项映射
 * （spec ai-chat-adopt-and-note-target-picker R1 / R3）。
 *
 * 加载复用既有 service（同端点同语义，不另写一份路径或分页逻辑）；纯映射函数单独导出便于单测。
 * 选中的目标一律经 `useAiHostContext` 的宿主 adapter 构造 —— 宿主形状只有一处实现，
 * 年度传 `null` 由服务端反查（不猜，避免与服务端反查值冲突被判 host_context_mismatch）。
 */
import type { AxiosRequestConfig } from 'axios'
import {
  getDisclosureNoteTree,
  listProjects,
  type DisclosureNoteTreeItem,
  type ProjectListItem,
} from '@/services/auditPlatformApi'
import { listWorkpapers, type WorkpaperDetail } from '@/services/workpaperApi'
import { api } from '@/services/apiProxy'
import { knowledgeLibrary as P_kl } from '@/services/apiPaths'
import { resolveAuditYearFromProject } from '@/utils/resolveAuditYear'
import {
  buildNoteHost,
  buildWorkpaperHost,
  type AiHostRef,
} from '@/composables/useAiHostContext'

export type AdoptTargetKind = 'workpaper' | 'note'

export interface ProjectOption {
  id: string
  label: string
  /** 审计年度（附注目录按年度取）；解析不出为 null */
  year: number | null
}

export interface FileOption {
  id: string
  label: string
}

/** 知识库文件夹树节点（`disabled` = 当前用户不能在此新建文档） */
export interface FolderOption {
  id: string
  name: string
  disabled: boolean
  children: FolderOption[]
}

// ---------------------------------------------------------------------------
// 纯映射
// ---------------------------------------------------------------------------

export function toProjectOptions(items: ProjectListItem[]): ProjectOption[] {
  return (items || [])
    .filter((p) => p && p.id)
    .map((p) => ({
      id: String(p.id),
      label: p.name || p.client_name || '未命名项目',
      year: resolveAuditYearFromProject(p),
    }))
}

export function toWorkpaperOptions(items: WorkpaperDetail[]): FileOption[] {
  return (items || [])
    .filter((w) => w && w.id)
    .map((w) => ({
      id: String(w.id),
      label: [w.wp_code, w.wp_name].filter(Boolean).join(' ') || '未命名底稿',
      code: w.wp_code || '',
    }))
    .sort((a, b) => a.code.localeCompare(b.code, 'zh-CN', { numeric: true }))
    .map(({ id, label }) => ({ id, label }))
}

export function toNoteOptions(items: DisclosureNoteTreeItem[]): FileOption[] {
  return (items || [])
    .filter((n) => n && n.id)
    .slice()
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    .map((n) => ({
      id: String(n.id),
      label: [n.note_section, n.section_title].filter(Boolean).join(' ') || '未命名章节',
    }))
}

export function toFolderOptions(nodes: any[]): FolderOption[] {
  return (Array.isArray(nodes) ? nodes : [])
    .filter((n) => n && n.id)
    .map((n) => ({
      id: String(n.id),
      name: String(n.name ?? ''),
      disabled: !n.can_create,
      children: toFolderOptions(n.children),
    }))
}

/** 在树里按 ID 找节点（返回包含祖先名的完整路径，用于展示保存位置）。 */
export function findFolderPath(nodes: FolderOption[], id: string, prefix: string[] = []): string[] | null {
  for (const n of nodes) {
    const path = [...prefix, n.name]
    if (n.id === id) return path
    const hit = findFolderPath(n.children, id, path)
    if (hit) return hit
  }
  return null
}

export function isCreatableFolder(nodes: FolderOption[], id: string | null | undefined): boolean {
  if (!id) return false
  for (const n of nodes) {
    if (n.id === id) return !n.disabled
    if (isCreatableFolder(n.children, id)) return true
  }
  return false
}

/** 选中的底稿 / 附注章节 → 采纳目标宿主（经宿主 adapter 构造；非法 ID 返回 null）。 */
export function buildAdoptTargetHost(
  kind: AdoptTargetKind,
  fileId: string,
  projectId: string,
): AiHostRef | null {
  const request = kind === 'workpaper'
    ? buildWorkpaperHost({ wpId: fileId, projectId, auditYear: null })
    : buildNoteHost({ noteId: fileId, projectId, year: null })
  return request.available ? request.host : null
}

// ---------------------------------------------------------------------------
// 加载
// ---------------------------------------------------------------------------

export async function loadProjectOptions(): Promise<ProjectOption[]> {
  return toProjectOptions(await listProjects())
}

/** 加载目标文件；`hint` 为空列表 / 无法加载时给用户的中文原因。 */
export async function loadFileOptions(
  kind: AdoptTargetKind,
  project: ProjectOption,
): Promise<{ options: FileOption[]; hint: string }> {
  if (kind === 'workpaper') {
    const options = toWorkpaperOptions(await listWorkpapers(project.id))
    return { options, hint: options.length ? '' : '该项目暂无已生成的底稿' }
  }
  if (!project.year) {
    return { options: [], hint: '该项目未设置审计年度，无法列出附注章节' }
  }
  const emptyHint = `该项目 ${project.year} 年度尚未生成附注`
  let raw: any
  try {
    // 附注未生成时后端 404「附注数据不存在，请先生成附注」是正常空态（2026-10-21 实测），
    // 静默请求、由对话框给出原因，不弹全局错误也不报「加载失败」
    raw = await getDisclosureNoteTree(project.id, project.year, { _silent: true } as AxiosRequestConfig)
  } catch (e: any) {
    if (e?.response?.status === 404) return { options: [], hint: emptyHint }
    throw e
  }
  const options = toNoteOptions(Array.isArray(raw) ? raw : (raw?.items ?? []))
  return { options, hint: options.length ? '' : emptyHint }
}

export async function loadFolderOptions(): Promise<FolderOption[]> {
  const data: any = await api.get(P_kl.tree)
  return toFolderOptions(Array.isArray(data) ? data : (data?.items ?? []))
}
