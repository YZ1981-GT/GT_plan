import { describe, it, expect } from 'vitest'
import {
  parseAuditYear,
  resolveAuditYearFromProject,
  resolveEffectiveAuditYear,
  yearFromProjectName,
} from '../resolveAuditYear'

describe('resolveAuditYear', () => {
  it('parseAuditYear 过滤无效值', () => {
    expect(parseAuditYear(2025)).toBe(2025)
    expect(parseAuditYear('2025')).toBe(2025)
    expect(parseAuditYear(1999)).toBeNull()
    expect(parseAuditYear(null)).toBeNull()
  })

  it('resolveAuditYearFromProject 按通用优先级解析', () => {
    expect(resolveAuditYearFromProject({ audit_year: 2025, audit_period_end: '2024-12-31' })).toBe(2025)
    expect(resolveAuditYearFromProject({ audit_period_end: '2025-12-31' })).toBe(2025)
    expect(resolveAuditYearFromProject({ audit_period_start: '2025-01-01' })).toBe(2025)
    expect(resolveAuditYearFromProject({ name: '重药控股安徽有限公司_2025' })).toBe(2025)
    expect(resolveAuditYearFromProject({})).toBeNull()
  })

  it('yearFromProjectName 解析命名后缀', () => {
    expect(yearFromProjectName('客户_2025')).toBe(2025)
    expect(yearFromProjectName('客户')).toBeNull()
  })

  it('resolveEffectiveAuditYear prop > config > route > store', () => {
    expect(resolveEffectiveAuditYear({
      propYear: 2026,
      configYear: 2025,
      storeAuditYear: 2024,
    })).toBe(2026)

    expect(resolveEffectiveAuditYear({
      configYear: 2025,
      routeYear: 2024,
      storeAuditYear: 2023,
    })).toBe(2025)

    expect(resolveEffectiveAuditYear({
      storeAuditYear: 2025,
    })).toBe(2025)

    expect(resolveEffectiveAuditYear({
      periodEnd: '2025-12-31',
    })).toBe(2025)
  })
})
