/**
 * UniverSheetNav.spec.ts — Sprint 2 Task 2.7
 *
 * 视觉适配：
 * 1. 含 priority 字段时按升序渲染（D 循环）
 * 2. 不含 priority 时保持原顺序（E 循环向后兼容）
 * 3. sheet.readonly === true 时渲染 🔒 徽章 + readonly class
 * 4. 折叠态同样按 priority 排序
 */

import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import UniverSheetNav from '../UniverSheetNav.vue'
import type { SheetGroup } from '@/composables/useUniverSheetNav'

function buildGroups(): SheetGroup[] {
  // 模拟 D 循环：故意打乱 priority 顺序输入，期望排序后 1 → 2 → 11 → 99
  return [
    {
      category: '历史遗留',
      icon: '🗄️',
      color: '#9e9e9e',
      priority: 99,
      sheets: [{ id: 's-hist', name: '修订前D4A', index: 5, category: '历史遗留' }],
    },
    {
      category: '附注披露',
      icon: '📝',
      color: '#795548',
      priority: 11,
      sheets: [
        { id: 's-note', name: '附注披露信息', index: 4, category: '附注披露', readonly: true },
      ],
    },
    {
      category: '总控台',
      icon: '🎯',
      color: '#1976d2',
      priority: 1,
      sheets: [{ id: 's-ctrl', name: 'D2A 总控台', index: 0, category: '总控台' }],
    },
    {
      category: '审定表',
      icon: '✅',
      color: '#388e3c',
      priority: 2,
      sheets: [{ id: 's-ver', name: 'D2-1 审定表', index: 1, category: '审定表' }],
    },
  ]
}

function buildEGroups(): SheetGroup[] {
  // 模拟 E 循环：无 priority 字段 → 保持原顺序
  return [
    {
      category: 'B',
      icon: '📑',
      color: '#aaa',
      sheets: [{ id: 'b1', name: 'B-sheet', index: 0, category: 'B' }],
    },
    {
      category: 'A',
      icon: '📋',
      color: '#bbb',
      sheets: [{ id: 'a1', name: 'A-sheet', index: 1, category: 'A' }],
    },
  ]
}

describe('UniverSheetNav — task 2.7 视觉适配', () => {
  it('含 priority 字段时按升序渲染（D 循环）', () => {
    const wrapper = mount(UniverSheetNav, {
      props: {
        groups: buildGroups(),
        activeSheetId: '',
        totalCount: 4,
        collapsed: false,
      },
    })
    const labels = wrapper.findAll('.gt-usn__group-label').map((n) => n.text())
    expect(labels).toEqual(['总控台', '审定表', '附注披露', '历史遗留'])
  })

  it('不含 priority 时保持原顺序（E 循环向后兼容）', () => {
    const wrapper = mount(UniverSheetNav, {
      props: {
        groups: buildEGroups(),
        activeSheetId: '',
        totalCount: 2,
        collapsed: false,
      },
    })
    const labels = wrapper.findAll('.gt-usn__group-label').map((n) => n.text())
    // 输入顺序：B → A，无 priority 应原样保留
    expect(labels).toEqual(['B', 'A'])
  })

  it('sheet.readonly=true 时渲染 🔒 徽章 + readonly class', () => {
    const wrapper = mount(UniverSheetNav, {
      props: {
        groups: buildGroups(),
        activeSheetId: '',
        totalCount: 4,
        collapsed: false,
      },
    })
    const readonlySheet = wrapper.find('.gt-usn__sheet--readonly')
    expect(readonlySheet.exists()).toBe(true)
    const badge = readonlySheet.find('.gt-usn__sheet-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('🔒')
  })

  it('非 readonly 的 sheet 不渲染 🔒 徽章', () => {
    const wrapper = mount(UniverSheetNav, {
      props: {
        groups: buildGroups(),
        activeSheetId: '',
        totalCount: 4,
        collapsed: false,
      },
    })
    // 总控台 sheet 不是 readonly
    const allBadges = wrapper.findAll('.gt-usn__sheet-badge')
    expect(allBadges.length).toBe(1) // 只有附注披露 1 个
  })

  it('折叠态同样按 priority 排序', () => {
    const wrapper = mount(UniverSheetNav, {
      props: {
        groups: buildGroups(),
        activeSheetId: '',
        totalCount: 4,
        collapsed: true,
      },
    })
    const titles = wrapper.findAll('.gt-usn__icon-only').map((n) => n.attributes('title') || '')
    // 期望按 priority 升序：总控台 → 审定表 → 附注披露 → 历史遗留
    expect(titles[0]).toContain('总控台')
    expect(titles[1]).toContain('审定表')
    expect(titles[2]).toContain('附注披露')
    expect(titles[3]).toContain('历史遗留')
  })
})
