/**
 * Tests for useWpCompletionRate composable
 *
 * Feature: workpaper-editor-slimdown Sprint 4
 * Task 9.1 + 9.4: 底稿填写完成度可视化
 *
 * **Validates: Requirements US-8**
 *
 * 验证要点：
 * 1. A 类：已决策/总程序
 * 2. D 类：已答/总问题
 * 3. E 类：已完成步骤/总步骤
 * 4. B 类：已填编制信息字段/总必填字段
 * 5. C 类：已填子表行数/schema 定义最小行数
 * 6. 边界情况：空数据、全完成、未知类型
 */

import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useWpCompletionRate,
  calcACompletion,
  calcDCompletion,
  calcECompletion,
  calcBCompletion,
  calcCCompletion,
  buildRate,
} from '../useWpCompletionRate'

// ─── buildRate 基础测试 ─────────────────────────────────────────────────────

describe('buildRate', () => {
  it('total=0 返回 empty', () => {
    const r = buildRate(0, 0)
    expect(r).toEqual({ filled: 0, total: 0, percentage: 0, category: 'empty' })
  })

  it('filled=0 返回 empty', () => {
    const r = buildRate(0, 5)
    expect(r).toEqual({ filled: 0, total: 5, percentage: 0, category: 'empty' })
  })

  it('部分完成返回 partial', () => {
    const r = buildRate(3, 5)
    expect(r).toEqual({ filled: 3, total: 5, percentage: 60, category: 'partial' })
  })

  it('全部完成返回 complete', () => {
    const r = buildRate(5, 5)
    expect(r).toEqual({ filled: 5, total: 5, percentage: 100, category: 'complete' })
  })

  it('percentage 不超过 100', () => {
    const r = buildRate(6, 5)
    expect(r.percentage).toBe(100)
    expect(r.category).toBe('complete')
  })
})

// ─── A 类：已决策/总程序 ─────────────────────────────────────────────────────

describe('calcACompletion — A 类程序表', () => {
  it('空 programs 返回 empty', () => {
    const r = calcACompletion({})
    expect(r.category).toBe('empty')
    expect(r.total).toBe(0)
  })

  it('全部 pending 返回 0%', () => {
    const r = calcACompletion({
      programs: [
        { status: 'pending' },
        { status: 'pending' },
        { status: 'pending' },
      ],
    })
    expect(r.filled).toBe(0)
    expect(r.total).toBe(3)
    expect(r.percentage).toBe(0)
    expect(r.category).toBe('empty')
  })

  it('部分决策返回正确百分比', () => {
    const r = calcACompletion({
      programs: [
        { status: 'completed' },
        { status: 'not_applicable' },
        { status: 'pending' },
        { status: 'in_progress' },
      ],
    })
    expect(r.filled).toBe(3) // completed + not_applicable + in_progress
    expect(r.total).toBe(4)
    expect(r.percentage).toBe(75)
    expect(r.category).toBe('partial')
  })

  it('全部决策返回 100%', () => {
    const r = calcACompletion({
      programs: [
        { status: 'completed' },
        { status: 'not_applicable' },
      ],
    })
    expect(r.percentage).toBe(100)
    expect(r.category).toBe('complete')
  })
})

// ─── D 类：已答/总问题 ─────────────────────────────────────────────────────

describe('calcDCompletion — D 类检查表', () => {
  it('空 fields 返回 empty', () => {
    const r = calcDCompletion({})
    expect(r.category).toBe('empty')
  })

  it('使用 fields 数组', () => {
    const r = calcDCompletion({
      fields: [
        { value: '是' },
        { value: '' },
        { value: null },
        { value: '否' },
      ],
    })
    expect(r.filled).toBe(2)
    expect(r.total).toBe(4)
    expect(r.percentage).toBe(50)
  })

  it('使用 questions 数组', () => {
    const r = calcDCompletion({
      questions: [
        { answer: '已确认' },
        { answer: '' },
      ],
    })
    expect(r.filled).toBe(1)
    expect(r.total).toBe(2)
  })

  it('使用 items 数组 + content 字段', () => {
    const r = calcDCompletion({
      items: [
        { content: '填写内容' },
        { content: '' },
        { content: '另一个内容' },
      ],
    })
    expect(r.filled).toBe(2)
    expect(r.total).toBe(3)
  })
})

// ─── E 类：已完成步骤/总步骤 ─────────────────────────────────────────────────

describe('calcECompletion — E 类控制测试', () => {
  it('空 steps 返回 empty', () => {
    const r = calcECompletion({})
    expect(r.category).toBe('empty')
  })

  it('部分完成', () => {
    const r = calcECompletion({
      steps: [
        { completed: true },
        { completed: false },
        { completed: true },
        { completed: false },
      ],
    })
    expect(r.filled).toBe(2)
    expect(r.total).toBe(4)
    expect(r.percentage).toBe(50)
  })

  it('全部完成', () => {
    const r = calcECompletion({
      steps: [
        { completed: true },
        { completed: true },
      ],
    })
    expect(r.percentage).toBe(100)
    expect(r.category).toBe('complete')
  })
})

// ─── B 类：已填编制信息字段/总必填字段 ─────────────────────────────────────

describe('calcBCompletion — B 类编制信息', () => {
  it('无 required_fields 返回 complete（无必填项）', () => {
    const r = calcBCompletion({}, {})
    expect(r.category).toBe('complete')
    expect(r.percentage).toBe(100)
  })

  it('部分填写', () => {
    const r = calcBCompletion(
      { fields: { name: '张三', date: '', auditor: '李四' } },
      { required_fields: ['name', 'date', 'auditor'] },
    )
    // fields.name='张三', fields.date='', fields.auditor='李四'
    // 但 calcBCompletion 读 htmlData.fields[fieldName]
    expect(r.filled).toBe(2)
    expect(r.total).toBe(3)
  })

  it('全部填写', () => {
    const r = calcBCompletion(
      { fields: { name: '张三', date: '2025-01-01' } },
      { required_fields: ['name', 'date'] },
    )
    expect(r.percentage).toBe(100)
    expect(r.category).toBe('complete')
  })
})

// ─── C 类：已填子表行数/schema 定义最小行数 ─────────────────────────────────

describe('calcCCompletion — C 类附注表', () => {
  it('无 rows 返回 empty', () => {
    const r = calcCCompletion({}, { min_rows: 3 })
    expect(r.filled).toBe(0)
    expect(r.total).toBe(3)
    expect(r.percentage).toBe(0)
  })

  it('部分填写', () => {
    const r = calcCCompletion(
      { rows: [{ col1: '数据' }, { col1: '' }, { col1: '数据2' }] },
      { min_rows: 5 },
    )
    expect(r.filled).toBe(2)
    expect(r.total).toBe(5)
    expect(r.percentage).toBe(40)
  })

  it('filled 不超过 total', () => {
    const r = calcCCompletion(
      { rows: [{ a: '1' }, { a: '2' }, { a: '3' }] },
      { min_rows: 2 },
    )
    expect(r.filled).toBe(2) // capped at total
    expect(r.total).toBe(2)
    expect(r.percentage).toBe(100)
  })
})

// ─── composable 集成测试 ─────────────────────────────────────────────────────

describe('useWpCompletionRate composable', () => {
  it('A 类 componentType 正确路由到 calcACompletion', () => {
    const componentType = ref('a-program-console')
    const schema = ref({})
    const htmlData = ref({
      programs: [{ status: 'completed' }, { status: 'pending' }],
    })

    const { rate } = useWpCompletionRate(componentType, schema, htmlData)
    expect(rate.value.filled).toBe(1)
    expect(rate.value.total).toBe(2)
    expect(rate.value.percentage).toBe(50)
  })

  it('D 类 componentType 正确路由到 calcDCompletion', () => {
    const componentType = ref('d-form-table')
    const schema = ref({})
    const htmlData = ref({
      fields: [{ value: '是' }, { value: '' }],
    })

    const { rate } = useWpCompletionRate(componentType, schema, htmlData)
    expect(rate.value.filled).toBe(1)
    expect(rate.value.total).toBe(2)
  })

  it('E 类 componentType 正确路由到 calcECompletion', () => {
    const componentType = ref('e-control-test')
    const schema = ref({})
    const htmlData = ref({
      steps: [{ completed: true }, { completed: true }, { completed: false }],
    })

    const { rate } = useWpCompletionRate(componentType, schema, htmlData)
    expect(rate.value.filled).toBe(2)
    expect(rate.value.total).toBe(3)
    expect(rate.value.percentage).toBe(67)
  })

  it('未知 componentType 返回 empty', () => {
    const componentType = ref('univer')
    const schema = ref({})
    const htmlData = ref({})

    const { rate } = useWpCompletionRate(componentType, schema, htmlData)
    expect(rate.value.category).toBe('empty')
    expect(rate.value.total).toBe(0)
  })

  it('响应式更新：htmlData 变化时 rate 自动重算', () => {
    const componentType = ref('e-control-test')
    const schema = ref({})
    const htmlData = ref<Record<string, any>>({
      steps: [{ completed: false }, { completed: false }],
    })

    const { rate } = useWpCompletionRate(componentType, schema, htmlData)
    expect(rate.value.percentage).toBe(0)

    // 模拟步骤完成
    htmlData.value = { steps: [{ completed: true }, { completed: false }] }
    expect(rate.value.percentage).toBe(50)
  })
})
