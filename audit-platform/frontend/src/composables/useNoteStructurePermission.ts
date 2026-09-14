/**
 * 附注结构编辑权限判断
 *
 * 编辑规则（Requirements 3.4）：
 * - 普通内容编辑（content 模式）：仅允许编辑 data/custom/note_tip/footnote 行
 * - 结构编辑（structure 模式）：允许编辑 table_title/group_header/subtotal/total 行（需更高权限）
 * - blank 行在任何模式下均不可编辑
 * - undefined/未知 row_type 默认可编辑（向后兼容旧数据）
 *
 * Validates: Requirements 3.4
 */

import type { NoteRowType } from '@/types/noteSemantic'

/** 编辑模式：content=普通内容编辑，structure=高权限结构编辑 */
export type EditMode = 'content' | 'structure'

// 结构锁定行类型（普通编辑模式下不可修改）
const STRUCTURE_LOCKED_TYPES: Set<NoteRowType> = new Set([
  'table_title',
  'group_header',
  'subtotal',
  'total',
])

// 普通可编辑行类型（content 模式允许）
const CONTENT_EDITABLE_TYPES: Set<NoteRowType> = new Set([
  'data',
  'custom',
  'note_tip',
  'footnote',
])

// 结构编辑模式额外可编辑的类型（在 content 基础上追加）
const STRUCTURE_EDITABLE_TYPES: Set<NoteRowType> = new Set([
  ...CONTENT_EDITABLE_TYPES,
  'table_title',
  'group_header',
  'subtotal',
  'total',
])

/**
 * 判断指定行类型在给定编辑模式下是否可编辑
 *
 * @param rowType - 行类型，可能为 undefined（旧数据兼容）
 * @param editMode - 编辑模式
 * @returns 是否可编辑
 */
export function isRowEditable(
  rowType: NoteRowType | string | undefined,
  editMode: EditMode,
): boolean {
  // undefined/未知类型 → 向后兼容，默认可编辑
  if (rowType === undefined || rowType === null || rowType === '') {
    return true
  }

  // blank 行在任何模式下均不可编辑
  if (rowType === 'blank') {
    return false
  }

  if (editMode === 'structure') {
    return STRUCTURE_EDITABLE_TYPES.has(rowType as NoteRowType)
  }

  // content 模式：仅允许普通可编辑行
  return CONTENT_EDITABLE_TYPES.has(rowType as NoteRowType)
}

/**
 * 判断行类型是否为结构锁定行（普通编辑模式下不可修改）
 *
 * @param rowType - 行类型
 * @returns 是否为结构锁定行
 */
export function isStructureLockedRow(
  rowType: NoteRowType | string | undefined,
): boolean {
  if (!rowType) return false
  return STRUCTURE_LOCKED_TYPES.has(rowType as NoteRowType)
}

/**
 * 根据编辑模式返回可编辑的行类型集合
 *
 * @param editMode - 编辑模式
 * @returns 可编辑行类型集合
 */
export function getEditableRowTypes(editMode: EditMode): Set<NoteRowType> {
  if (editMode === 'structure') {
    return new Set(STRUCTURE_EDITABLE_TYPES)
  }
  return new Set(CONTENT_EDITABLE_TYPES)
}
