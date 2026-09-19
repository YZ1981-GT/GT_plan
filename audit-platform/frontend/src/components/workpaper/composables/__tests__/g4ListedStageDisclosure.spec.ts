import { describe, expect, it } from 'vitest'
import {
  addStageDetail,
  buildDefaultSoeStageBlocks,
  buildDefaultStageBlocks,
  endingImpairmentTotal,
  methodTotals,
  parseStageBlocks,
  patchStageDetail,
  removeStageDetail,
  serializeStageBlocks,
  stageTotals,
} from '../g4ListedStageDisclosure'

describe('g4ListedStageDisclosure', () => {
  it('默认每组仅 1 条其中行，可动态增减', () => {
    let blocks = buildDefaultStageBlocks()
    const b0 = blocks[0]
    expect(b0.individual.details).toHaveLength(1)
    expect(b0.portfolio.details).toHaveLength(1)

    blocks = addStageDetail(blocks, b0.id, 'individual')
    expect(blocks[0].individual.details).toHaveLength(2)

    blocks = addStageDetail(blocks, b0.id, 'portfolio', '组合A')
    expect(blocks[0].portfolio.details).toHaveLength(2)
    expect(blocks[0].portfolio.details[1].name).toBe('组合A')

    const id = blocks[0].individual.details[0].id
    blocks = removeStageDetail(blocks, b0.id, 'individual', id)
    expect(blocks[0].individual.details).toHaveLength(1)
  })

  it('父级汇总与 ECL / 账面价值联动', () => {
    let blocks = buildDefaultStageBlocks()
    const id = blocks[0].id
    const d0 = blocks[0].individual.details[0].id
    blocks = patchStageDetail(blocks, id, 'individual', d0, {
      bookBalance: 1000,
      impairment: 10,
    })
    blocks = addStageDetail(blocks, id, 'individual')
    const d1 = blocks[0].individual.details[1].id
    blocks = patchStageDetail(blocks, id, 'individual', d1, {
      bookBalance: 500,
      impairment: 25,
    })

    const tot = methodTotals(blocks[0].individual)
    expect(tot.bookBalance).toBe(1500)
    expect(tot.impairment).toBe(35)
    expect(tot.bookValue).toBe(1465)
    expect(tot.ratePct).toBeCloseTo((35 / 1500) * 100, 5)

    expect(stageTotals(blocks[0]).impairment).toBe(35)
  })

  it('序列化往返保留动态其中行', () => {
    let blocks = buildDefaultStageBlocks()
    blocks = addStageDetail(blocks, blocks[1].id, 'portfolio', '组合风险上升')
    const d = blocks[1].portfolio.details[1].id
    blocks = patchStageDetail(blocks, blocks[1].id, 'portfolio', d, {
      bookBalance: 200,
      impairment: 40,
      reason: '评级下调',
    })
    const again = parseStageBlocks(serializeStageBlocks(blocks))
    expect(again).not.toBeNull()
    expect(again![1].portfolio.details).toHaveLength(2)
    expect(again![1].portfolio.details[1].reason).toBe('评级下调')
    expect(endingImpairmentTotal(again!)).toBe(40)
  })

  it('删至 0 时仍保留 1 条空其中行', () => {
    let blocks = buildDefaultStageBlocks()
    const id = blocks[0].id
    const only = blocks[0].individual.details[0].id
    blocks = removeStageDetail(blocks, id, 'individual', only)
    expect(blocks[0].individual.details).toHaveLength(1)
  })

  it('国企默认仅期末三阶段，理由列统一', () => {
    const soe = buildDefaultSoeStageBlocks()
    expect(soe).toHaveLength(3)
    expect(soe.every((b) => b.period === 'ending')).toBe(true)
    expect(soe.every((b) => b.reasonHeader === '理由')).toBe(true)
    soe.forEach((b) => {
      expect(b.individual.details).toHaveLength(1)
      expect(b.portfolio.details).toHaveLength(1)
    })
  })
})
