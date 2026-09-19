import { describe, it, expect } from 'vitest'
import {
  checkPersonnel,
  type AuthorizedPerson,
  type JeControlSample,
} from '../useC23ControlData'

// ─── 辅助工厂 ───────────────────────────────────────────────

function makeSample(overrides: Partial<JeControlSample> = {}): JeControlSample {
  return {
    seq: 1,
    voucherDate: '2025-01-15',
    voucherNo: '转-001',
    preparer: '张三',
    poster: '李四',
    reviewer: '王五',
    supportDoc: '银行回单',
    approval: '已批准',
    ...overrides,
  }
}

function makeAuthorized(name: string, role: string = '创建'): AuthorizedPerson {
  return { name, role }
}

// ─── checkPersonnel ─────────────────────────────────────────

describe('checkPersonnel', () => {
  it('空样本数组返回空', () => {
    const authorized = [makeAuthorized('张三'), makeAuthorized('李四')]
    expect(checkPersonnel([], authorized)).toEqual([])
  })

  it('所有人员都在授权清单内时 deviation=false', () => {
    const samples = [makeSample()]
    const authorized = [
      makeAuthorized('张三', '创建'),
      makeAuthorized('李四', '记录'),
      makeAuthorized('王五', '授权'),
    ]
    const results = checkPersonnel(samples, authorized)
    expect(results).toHaveLength(1)
    expect(results[0].deviation).toBe(false)
    expect(results[0].deviationDetails).toBe('')
  })

  it('编制人不在清单时标记偏差', () => {
    const samples = [makeSample({ preparer: '赵六' })]
    const authorized = [makeAuthorized('张三'), makeAuthorized('李四'), makeAuthorized('王五')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(true)
    expect(results[0].deviationDetails).toContain('编制人"赵六"不在授权清单')
  })

  it('过账人不在清单时标记偏差', () => {
    const samples = [makeSample({ poster: '陈七' })]
    const authorized = [makeAuthorized('张三'), makeAuthorized('李四'), makeAuthorized('王五')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(true)
    expect(results[0].deviationDetails).toContain('过账人"陈七"不在授权清单')
  })

  it('审核人不在清单时标记偏差', () => {
    const samples = [makeSample({ reviewer: '周八' })]
    const authorized = [makeAuthorized('张三'), makeAuthorized('李四'), makeAuthorized('王五')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(true)
    expect(results[0].deviationDetails).toContain('审核人"周八"不在授权清单')
  })

  it('多个人员不在清单时详情用分号连接', () => {
    const samples = [makeSample({ preparer: '甲', poster: '乙', reviewer: '丙' })]
    const authorized = [makeAuthorized('张三')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(true)
    expect(results[0].deviationDetails).toContain('编制人"甲"')
    expect(results[0].deviationDetails).toContain('过账人"乙"')
    expect(results[0].deviationDetails).toContain('审核人"丙"')
    // 用中文分号连接
    expect(results[0].deviationDetails.split('；').length).toBe(3)
  })

  it('空值字段不标记偏差', () => {
    const samples = [makeSample({ preparer: '', poster: '', reviewer: '' })]
    const authorized: AuthorizedPerson[] = []
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(false)
    expect(results[0].deviationDetails).toBe('')
  })

  it('姓名前后空格去除后匹配', () => {
    const samples = [makeSample({ preparer: '  张三  ' })]
    const authorized = [makeAuthorized('张三'), makeAuthorized('李四'), makeAuthorized('王五')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(false)
  })

  it('授权清单中含空格的姓名也能正确匹配', () => {
    const samples = [makeSample({ preparer: '张三' })]
    const authorized = [makeAuthorized(' 张三 '), makeAuthorized('李四'), makeAuthorized('王五')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(false)
  })

  it('授权清单为空时所有非空人员都标记偏差', () => {
    const samples = [makeSample()]
    const results = checkPersonnel(samples, [])
    expect(results[0].deviation).toBe(true)
  })

  it('多条样本独立检查', () => {
    const samples = [
      makeSample({ seq: 1, preparer: '张三', poster: '李四', reviewer: '王五' }),
      makeSample({ seq: 2, preparer: '赵六', poster: '李四', reviewer: '王五' }),
    ]
    const authorized = [makeAuthorized('张三'), makeAuthorized('李四'), makeAuthorized('王五')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(false)
    expect(results[1].deviation).toBe(true)
    expect(results[1].deviationDetails).toContain('编制人"赵六"')
  })

  it('授权人员角色不影响匹配（只按姓名）', () => {
    const samples = [makeSample({ preparer: '张三' })]
    // 张三的角色是"授权"而非"创建"，但仍应匹配
    const authorized = [makeAuthorized('张三', '授权'), makeAuthorized('李四'), makeAuthorized('王五')]
    const results = checkPersonnel(samples, authorized)
    expect(results[0].deviation).toBe(false)
  })

  it('返回结果保持原始 sample 引用', () => {
    const sample = makeSample()
    const results = checkPersonnel([sample], [makeAuthorized('张三'), makeAuthorized('李四'), makeAuthorized('王五')])
    expect(results[0].sample).toBe(sample)
  })
})
