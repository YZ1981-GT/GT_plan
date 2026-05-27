/**
 * useNoteCustomTemplate — 自定义附注模板的薄层封装（Sprint 3 Task 3.1/3.4/3.5）
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3
 * Reqs:   R4.1 / R4.3 验收 29 / 32 / 36
 *
 * 提供：
 * - loadCurrent: 拉取当前自定义模板（含 sections 数组）
 * - addOrUpdateSection: union sections + 写回（D3 union 算法）
 * - removeSection:    删除指定章节（保留快照作 30 天回收期语义）
 *
 * 为了让 DisclosureEditor.vue 的 add-section / delete-custom-section 流程
 * 可被独立单测，将 IO + sections 数组操作放在此处；视图层只负责 UX。
 */
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'

export interface CustomNoteSection {
  section_number: string
  section_title: string
  account_name?: string
  sort_order?: number
  scope?: 'both' | 'standalone_only' | 'consolidated_only'
  /** 项目级标记：自定义章节（基线模板章节没有此字段） */
  _custom?: boolean
  [key: string]: any
}

export interface CustomNoteTemplatePayload {
  version: number
  updated_at: string
  history: Array<{ version: number; snapshot_path: string; updated_at: string }>
  sections: CustomNoteSection[]
}

export interface SaveResult {
  version: number
  updated_at: string
  history: CustomNoteTemplatePayload['history']
}

/**
 * 拉取当前自定义模板；不存在/网络错误时返回空 sections（不抛错）.
 */
export async function loadCurrentCustomTemplate(
  projectId: string,
): Promise<CustomNoteTemplatePayload> {
  try {
    const data = await api.get<Partial<CustomNoteTemplatePayload>>(
      P.noteCustomTemplate.load(projectId),
    )
    return {
      version: typeof data?.version === 'number' ? data.version : 0,
      updated_at: typeof data?.updated_at === 'string' ? data.updated_at : '',
      history: Array.isArray(data?.history) ? data.history! : [],
      sections: Array.isArray(data?.sections) ? data.sections! : [],
    }
  } catch {
    return { version: 0, updated_at: '', history: [], sections: [] }
  }
}

/**
 * union 当前 sections + 新章节（同 section_number 覆盖），写回保存.
 *
 * @returns SaveResult（含新版本号 + history）
 */
export async function addOrUpdateCustomSection(
  projectId: string,
  newSection: CustomNoteSection,
): Promise<SaveResult> {
  if (!newSection?.section_number) {
    throw new Error('section_number is required')
  }
  const current = await loadCurrentCustomTemplate(projectId)
  const sections = [...current.sections]
  const idx = sections.findIndex(s => s?.section_number === newSection.section_number)
  const merged: CustomNoteSection = { _custom: true, ...newSection }
  if (idx >= 0) {
    sections[idx] = { ...sections[idx], ...merged }
  } else {
    sections.push(merged)
  }
  return await api.post<SaveResult>(P.noteCustomTemplate.save(projectId), { sections })
}

/**
 * 删除指定 section_number 的自定义章节，写回保存.
 *
 * 后端 D8 storage 的 v{N}.json 不可变快照天然提供"30 天保留期"回滚能力：
 * 删除产生新版本 v{N+1}，旧 v{N} 仍可在版本历史中回滚。
 *
 * @returns SaveResult；若该章节本来不存在则返回 null（调用方 UX 处理）
 */
export async function removeCustomSection(
  projectId: string,
  sectionNumber: string,
): Promise<SaveResult | null> {
  if (!sectionNumber) {
    throw new Error('sectionNumber is required')
  }
  const current = await loadCurrentCustomTemplate(projectId)
  const next = current.sections.filter(s => s?.section_number !== sectionNumber)
  if (next.length === current.sections.length) {
    // 当前自定义模板未包含此章节
    return null
  }
  return await api.post<SaveResult>(P.noteCustomTemplate.save(projectId), { sections: next })
}

export default {
  loadCurrentCustomTemplate,
  addOrUpdateCustomSection,
  removeCustomSection,
}
