import { describe, it, expect } from 'vitest'
import { normalizeAProgramRow, parseProgramSubSteps } from '../parseProgramSubSteps'

describe('parseProgramSubSteps', () => {
  it('解析换行子步骤（D4A 样式）', () => {
    const { parentDesc, subSteps } = parseProgramSubSteps(
      '获取明细表并完成以下工作：\n（1）复核加计正确；\n（2）检查折算汇率。',
    )
    expect(parentDesc).toContain('获取明细表')
    expect(subSteps).toHaveLength(2)
    expect(subSteps[0].text).toContain('复核加计')
  })

  it('解析同行连续子步骤（G4A xlsx 样式）', () => {
    const { parentDesc, subSteps } = parseProgramSubSteps(
      '获取债权投资明细表，完成以下工作：（1）检查初始确认；（2）与总账核对。',
    )
    expect(parentDesc).toContain('债权投资')
    expect(subSteps).toHaveLength(2)
  })

  it('normalizeAProgramRow 收敛 program_desc', () => {
    const row = normalizeAProgramRow({
      id: '1',
      program_desc: '总体：（1）子项A；（2）子项B。',
    })
    expect(row.sub_steps).toHaveLength(2)
    expect(row.program_desc).toBe('总体')
  })
})
