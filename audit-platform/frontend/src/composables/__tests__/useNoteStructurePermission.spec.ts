/**
 * 附注结构编辑权限判断测试
 *
 * Validates: Requirements 3.4
 * - 普通编辑模式禁止修改结构行（table_title/group_header/subtotal/total）
 * - 高权限结构编辑模式允许修改结构行
 * - blank 行在任何模式下均不可编辑
 * - undefined row_type 默认可编辑（向后兼容）
 */

import { describe, it, expect } from 'vitest'
import {
  isRowEditable,
  isStructureLockedRow,
  getEditableRowTypes,
} from '../useNoteStructurePermission'
import type { NoteRowType } from '@/types/noteSemantic'

describe('useNoteStructurePermission', () => {
  describe('isRowEditable - content 模式', () => {
    const contentEditableTypes: NoteRowType[] = ['data', 'custom', 'note_tip', 'footnote']
    const structureLockedTypes: NoteRowType[] = ['table_title', 'group_header', 'subtotal', 'total']

    it.each(contentEditableTypes)(
      '普通模式下 %s 行可编辑',
      (rowType) => {
        expect(isRowEditable(rowType, 'content')).toBe(true)
      },
    )

    it.each(structureLockedTypes)(
      '普通模式下 %s 行不可编辑（结构锁定）',
      (rowType) => {
        expect(isRowEditable(rowType, 'content')).toBe(false)
      },
    )

    it('普通模式下 blank 行不可编辑', () => {
      expect(isRowEditable('blank', 'content')).toBe(false)
    })
  })

  describe('isRowEditable - structure 模式', () => {
    const allEditableInStructure: NoteRowType[] = [
      'data', 'custom', 'note_tip', 'footnote',
      'table_title', 'group_header', 'subtotal', 'total',
    ]

    it.each(allEditableInStructure)(
      '结构编辑模式下 %s 行可编辑',
      (rowType) => {
        expect(isRowEditable(rowType, 'structure')).toBe(true)
      },
    )

    it('结构编辑模式下 blank 行仍不可编辑', () => {
      expect(isRowEditable('blank', 'structure')).toBe(false)
    })
  })

  describe('isRowEditable - 向后兼容', () => {
    it('undefined row_type 默认可编辑', () => {
      expect(isRowEditable(undefined, 'content')).toBe(true)
      expect(isRowEditable(undefined, 'structure')).toBe(true)
    })

    it('空字符串 row_type 默认可编辑', () => {
      expect(isRowEditable('', 'content')).toBe(true)
      expect(isRowEditable('', 'structure')).toBe(true)
    })

    it('null row_type 默认可编辑', () => {
      expect(isRowEditable(null as unknown as undefined, 'content')).toBe(true)
    })
  })

  describe('isStructureLockedRow', () => {
    it('table_title 是结构锁定行', () => {
      expect(isStructureLockedRow('table_title')).toBe(true)
    })

    it('group_header 是结构锁定行', () => {
      expect(isStructureLockedRow('group_header')).toBe(true)
    })

    it('subtotal 是结构锁定行', () => {
      expect(isStructureLockedRow('subtotal')).toBe(true)
    })

    it('total 是结构锁定行', () => {
      expect(isStructureLockedRow('total')).toBe(true)
    })

    it('data 不是结构锁定行', () => {
      expect(isStructureLockedRow('data')).toBe(false)
    })

    it('custom 不是结构锁定行', () => {
      expect(isStructureLockedRow('custom')).toBe(false)
    })

    it('note_tip 不是结构锁定行', () => {
      expect(isStructureLockedRow('note_tip')).toBe(false)
    })

    it('footnote 不是结构锁定行', () => {
      expect(isStructureLockedRow('footnote')).toBe(false)
    })

    it('blank 不是结构锁定行', () => {
      expect(isStructureLockedRow('blank')).toBe(false)
    })

    it('undefined 不是结构锁定行', () => {
      expect(isStructureLockedRow(undefined)).toBe(false)
    })

    it('空字符串 不是结构锁定行', () => {
      expect(isStructureLockedRow('')).toBe(false)
    })
  })

  describe('getEditableRowTypes', () => {
    it('content 模式返回 data/custom/note_tip/footnote', () => {
      const types = getEditableRowTypes('content')
      expect(types).toEqual(new Set(['data', 'custom', 'note_tip', 'footnote']))
      expect(types.size).toBe(4)
    })

    it('structure 模式返回 content 类型 + 结构类型', () => {
      const types = getEditableRowTypes('structure')
      expect(types).toEqual(new Set([
        'data', 'custom', 'note_tip', 'footnote',
        'table_title', 'group_header', 'subtotal', 'total',
      ]))
      expect(types.size).toBe(8)
    })

    it('content 模式不包含 blank', () => {
      const types = getEditableRowTypes('content')
      expect(types.has('blank')).toBe(false)
    })

    it('structure 模式不包含 blank', () => {
      const types = getEditableRowTypes('structure')
      expect(types.has('blank')).toBe(false)
    })
  })

  describe('普通助理不能修改 locked structure row（集成场景）', () => {
    it('模拟普通编辑者尝试修改 table_title 行被阻止', () => {
      const editMode = 'content' // 普通助理使用 content 模式
      const rowType: NoteRowType = 'table_title'

      const canEdit = isRowEditable(rowType, editMode)
      const isLocked = isStructureLockedRow(rowType)

      expect(canEdit).toBe(false)
      expect(isLocked).toBe(true)
    })

    it('模拟普通编辑者尝试修改 group_header 行被阻止', () => {
      const editMode = 'content'
      const rowType: NoteRowType = 'group_header'

      expect(isRowEditable(rowType, editMode)).toBe(false)
      expect(isStructureLockedRow(rowType)).toBe(true)
    })

    it('模拟高权限用户通过结构编辑模式修改 table_title', () => {
      const editMode = 'structure'
      const rowType: NoteRowType = 'table_title'

      expect(isRowEditable(rowType, editMode)).toBe(true)
      expect(isStructureLockedRow(rowType)).toBe(true) // 仍被标记为结构行
    })

    it('普通编辑者可以修改 data 行', () => {
      expect(isRowEditable('data', 'content')).toBe(true)
      expect(isStructureLockedRow('data')).toBe(false)
    })
  })
})
