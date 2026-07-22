import { describe, it, expect } from 'vitest'
import { calcAreaDiff, suggestMatchConsistent, isAreaAnomaly, resolveProjectClientName } from '../h3TitleRowModel'

describe('useH3TitleCheck helpers', () => {
  it('resolveProjectClientName 从 project_context 解析被审计单位', () => {
    expect(resolveProjectClientName(null)).toBe('')
    expect(resolveProjectClientName({ project_context: { client_name: '  测试公司  ' } })).toBe('测试公司')
    expect(resolveProjectClientName({ projectContext: { entity_name: '备选名称' } })).toBe('备选名称')
  })

  it('calcAreaDiff = 证载面积 - 账面面积', () => {
    expect(calcAreaDiff(120, 100)).toBe(20)
    expect(calcAreaDiff(0, 50)).toBe(-50)
  })

  it('suggestMatchConsistent 识别权属与面积异常', () => {
    expect(suggestMatchConsistent({
      isAuditEntity: '否',
      areaDiff: 0,
      certArea: 100,
      bookArea: 100,
      certPurpose: '商业',
      actualPurpose: '商业',
      inconsistentReason: '',
    })).toBe('否')

    expect(suggestMatchConsistent({
      isAuditEntity: '是',
      areaDiff: 20,
      certArea: 120,
      bookArea: 100,
      certPurpose: '商业',
      actualPurpose: '商业',
      inconsistentReason: '',
    })).toBe('否')

    expect(isAreaAnomaly(100.3, 100)).toBe(false)

    expect(suggestMatchConsistent({
      isAuditEntity: '是',
      areaDiff: 0,
      certArea: 100,
      bookArea: 100,
      certPurpose: '商业',
      actualPurpose: '商业',
      inconsistentReason: '',
    })).toBe('是')
  })
})
