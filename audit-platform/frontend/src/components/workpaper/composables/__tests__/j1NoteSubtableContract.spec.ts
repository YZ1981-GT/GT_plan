/**
 * J1 披露子表 ↔ note_template 契约（接共享 helper 的 5 条 Property）
 *
 * 这套守卫正是能拦住本次 P0 的那一条：soe 八、40 第 3 张表原与第 2 张重名
 * （都叫「短期薪酬列示」），而前端推「设定提存计划列示」→ 模板里不存在该表名
 * → 孤儿子表（附注 TAB 永空 + 底稿数据丢失）。P1 会直接报红。
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/ Task 8.2
 */
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  J1_NOTE_SECTION,
  J1_SUB_TABLE_KEYS,
  j1MovementColumns,
} from '../j1NoteSectionMap'

/** 三张表共用同一份 5 列定义（附注模板三表 headers 相同） */
function columnsFor(variant: 'listed' | 'soe') {
  const cols = j1MovementColumns()
  return Object.fromEntries(
    Object.values(J1_SUB_TABLE_KEYS[variant]).map((name) => [name, cols]),
  )
}

runDisclosureSubtableContract({
  cycle: 'J1',
  variants: [
    {
      variant: 'listed',
      section: J1_NOTE_SECTION.listed,
      subtables: J1_SUB_TABLE_KEYS.listed,
      columns: columnsFor('listed'),
    },
    {
      variant: 'soe',
      section: J1_NOTE_SECTION.soe,
      subtables: J1_SUB_TABLE_KEYS.soe,
      columns: columnsFor('soe'),
    },
  ],
})
