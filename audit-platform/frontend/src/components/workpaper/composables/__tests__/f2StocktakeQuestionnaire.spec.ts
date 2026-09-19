/**
 * F2-21 盘点计划问卷 v2 — schema / 迁移
 */
import { describe, it, expect } from 'vitest'
import {
  emptyQuestionnaire,
  migrateLegacyToQuestionnaire,
  normalizeQuestionnaire,
  isQuestionnaireFilled,
  F21_TEXT_QUESTIONS,
} from '../../f2/stocktake/f2StocktakeQuestionnaire'

describe('f2StocktakeQuestionnaire', () => {
  it('emptyQuestionnaire 含全部题号', () => {
    const q = emptyQuestionnaire()
    expect(q.version).toBe(2)
    expect(q.locations).toHaveLength(1)
    expect(q.personnel).toHaveLength(1)
    for (const t of F21_TEXT_QUESTIONS) {
      expect(q.answers[t.id]).toBe('')
    }
    expect(q.answers.q22_1).toBe('')
    expect(q.answers.q22_2).toBe('')
  })

  it('从 OO 地点行迁移到 locations', () => {
    const rows = JSON.stringify([
      { location: 'A仓', inventoryType: '原材料', sharePct: '30', countDate: '2025-12-31' },
      { location: 'B仓', inventoryType: '产成品', sharePct: '70', countDate: '2026-01-02' },
    ])
    const data = migrateLegacyToQuestionnaire({}, rows)
    expect(data.version).toBe(2)
    expect(data.locations).toHaveLength(2)
    expect(data.locations[0].location).toBe('A仓')
    expect(data.locations[0].countTime).toBe('2025-12-31')
    expect(data.locations[1].inventoryType).toBe('产成品')
  })

  it('从旧扁平字段迁移 answers / personnel', () => {
    const data = migrateLegacyToQuestionnaire({
      expertNeeded: '需化学品专家',
      remoteWarehouse: '第三方仓一处',
      fraudRisk: '存在转移风险',
      auditors: '张三\n李四',
      clientStaff: '王五',
    })
    expect(data.answers.q3).toContain('化学品')
    expect(data.answers.q13).toContain('第三方')
    expect(data.answers.q21).toContain('转移')
    expect(data.personnel.filter((p) => p.name).map((p) => p.name)).toEqual(['张三', '李四', '王五'])
  })

  it('normalizeQuestionnaire 识别已是 v2', () => {
    const raw = {
      version: 2,
      locations: [{ id: '1', location: '主仓', inventoryType: '', sharePct: '', countTime: '' }],
      personnel: [{ id: '2', name: '赵六', location: '', role: '', competence: '', phone: '' }],
      answers: { q3: '无专家', q22_1: 'yes', q22_2: '无缺陷' },
    }
    const data = normalizeQuestionnaire(raw)
    expect(data.locations[0].location).toBe('主仓')
    expect(data.answers.q3).toBe('无专家')
    expect(data.answers.q22_1).toBe('yes')
  })

  it('isQuestionnaireFilled 统计进度', () => {
    const data = emptyQuestionnaire()
    let p = isQuestionnaireFilled(data)
    expect(p.filled).toBe(0)
    expect(p.total).toBe(2 + F21_TEXT_QUESTIONS.length + 2)

    data.locations[0].location = '主仓'
    data.answers.q3 = '无'
    data.answers.q22_1 = 'yes'
    p = isQuestionnaireFilled(data)
    expect(p.filled).toBe(3)
    expect(p.q1).toBe(true)
    expect(p.q22).toBe(true)
  })
})
