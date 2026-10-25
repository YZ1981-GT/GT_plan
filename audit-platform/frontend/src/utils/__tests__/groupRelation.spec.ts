/**
 * 与上级关系默认规则 —— 与后端 test_group_relation.py 逐条跑同一份共享夹具（属性 P11）。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  effectiveParentCode,
  inferRelationFromName,
  relationLabel,
  RELATION_OPTIONS,
  SELF_REFERENCE_CONFIRM,
  selfReferenceKind,
} from '../groupRelation'

interface RelationCase { name: string; expected: 'subsidiary' | 'branch'; real?: boolean }
interface SelfCase {
  label: string
  own: string
  parent: string | null
  ultimate: string | null
  effective_parent: string | null
  kind: 'top' | 'ultimate' | null
}

const CASES_PATH = resolve(__dirname, '../../../../../backend/data/relation_to_parent_cases.json')
const FIXTURE = JSON.parse(readFileSync(CASES_PATH, 'utf-8'))
const CASES: RelationCase[] = FIXTURE.cases
const SELF_CASES: SelfCase[] = FIXTURE.self_reference_cases

describe('上级代码 = 本企业代码（需求 1.5，共享夹具）', () => {
  it('夹具非空转：三种含义都有', () => {
    expect(new Set(SELF_CASES.map((c) => c.kind))).toEqual(new Set(['top', 'ultimate', null]))
  })

  it.each(SELF_CASES.map((c) => [c.label, c] as const))('%s', (_label, c) => {
    expect(effectiveParentCode(c.own, c.parent)).toBe(c.effective_parent)
    expect(selfReferenceKind(c.own, c.parent, c.ultimate)).toBe(c.kind)
  })

  it('确认文案分两种，措辞与用户口径一致', () => {
    expect(SELF_REFERENCE_CONFIRM.top).toContain('确认本企业就是上级企业')
    expect(SELF_REFERENCE_CONFIRM.top).toContain('不会重复生成上级节点')
    expect(SELF_REFERENCE_CONFIRM.ultimate).toContain('本企业即为最终控制方（集团总部或母公司）')
  })
})

describe('groupRelation 共享夹具', () => {
  it('夹具非空转：两类结论都有且含真库名称', () => {
    expect(new Set(CASES.map((c) => c.expected))).toEqual(new Set(['subsidiary', 'branch']))
    expect(CASES.filter((c) => c.real).length).toBeGreaterThanOrEqual(7)
  })

  it.each(CASES.map((c) => [c.name || '<空>', c] as const))('%s', (_label, c) => {
    expect(inferRelationFromName(c.name)).toBe(c.expected)
  })
})

describe('groupRelation 标签与选项', () => {
  it('relationLabel 只认两种取值', () => {
    expect(relationLabel('subsidiary')).toBe('子公司')
    expect(relationLabel('branch')).toBe('分公司')
    expect(relationLabel(null)).toBe('')
    expect(relationLabel('associate')).toBe('')
  })

  it('下拉选项恰为子公司与分公司', () => {
    expect(RELATION_OPTIONS.map((o) => o.value)).toEqual(['subsidiary', 'branch'])
  })
})
