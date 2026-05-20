/**
 * roles.ts 单元测试 — 角色体系治理验证
 *
 * 覆盖：
 * 1. normalizeRole 别名映射
 * 2. roleDisplayName 中文显示名
 * 3. ROLE_HIERARCHY 继承关系
 * 4. roleIncludes / isPartnerOrAbove / isManagerOrAbove / canDoQC
 * 5. isEqcrEligible 项目级双层判断
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeRole,
  roleDisplayName,
  roleIncludes,
  isPartnerOrAbove,
  isManagerOrAbove,
  canDoQC,
  isEqcrEligible,
  ROLE_HIERARCHY,
} from '../roles'

describe('normalizeRole — 别名映射', () => {
  it('后端枚举值原样返回', () => {
    expect(normalizeRole('admin')).toBe('admin')
    expect(normalizeRole('partner')).toBe('partner')
    expect(normalizeRole('manager')).toBe('manager')
    expect(normalizeRole('auditor')).toBe('auditor')
    expect(normalizeRole('qc')).toBe('qc')
    expect(normalizeRole('readonly')).toBe('readonly')
  })

  it('assistant → auditor', () => {
    expect(normalizeRole('assistant')).toBe('auditor')
  })

  it('quality_control → qc', () => {
    expect(normalizeRole('quality_control')).toBe('qc')
  })

  it('pm / project_manager → manager', () => {
    expect(normalizeRole('pm')).toBe('manager')
    expect(normalizeRole('project_manager')).toBe('manager')
  })

  it('qc_reviewer → qc', () => {
    expect(normalizeRole('qc_reviewer')).toBe('qc')
  })

  it('大小写不敏感', () => {
    expect(normalizeRole('Admin')).toBe('admin')
    expect(normalizeRole('PARTNER')).toBe('partner')
  })

  it('空值返回空字符串', () => {
    expect(normalizeRole(null)).toBe('')
    expect(normalizeRole(undefined)).toBe('')
    expect(normalizeRole('')).toBe('')
  })

  it('未知角色返回空字符串', () => {
    expect(normalizeRole('unknown_role')).toBe('')
    expect(normalizeRole('xyz')).toBe('')
  })
})

describe('roleDisplayName — 中文显示名', () => {
  it('admin → 系统管理员', () => {
    expect(roleDisplayName('admin')).toBe('系统管理员')
  })

  it('partner → 合伙人', () => {
    expect(roleDisplayName('partner')).toBe('合伙人')
  })

  it('manager → 项目经理', () => {
    expect(roleDisplayName('manager')).toBe('项目经理')
  })

  it('auditor → 审计助理', () => {
    expect(roleDisplayName('auditor')).toBe('审计助理')
  })

  it('qc → 质控人员', () => {
    expect(roleDisplayName('qc')).toBe('质控人员')
  })

  it('readonly → 只读用户', () => {
    expect(roleDisplayName('readonly')).toBe('只读用户')
  })

  it('eqcr → EQCR 独立复核', () => {
    expect(roleDisplayName('eqcr')).toBe('EQCR 独立复核')
  })

  it('别名标准化后返回正确显示名', () => {
    expect(roleDisplayName('assistant')).toBe('审计助理')
    expect(roleDisplayName('quality_control')).toBe('质控人员')
    expect(roleDisplayName('pm')).toBe('项目经理')
  })

  it('未知角色返回原值', () => {
    expect(roleDisplayName('unknown')).toBe('unknown')
  })

  it('空值返回空字符串', () => {
    expect(roleDisplayName(null)).toBe('')
  })
})

describe('ROLE_HIERARCHY — 角色继承关系', () => {
  it('partner 包含 manager 和 auditor', () => {
    expect(ROLE_HIERARCHY.partner).toContain('manager')
    expect(ROLE_HIERARCHY.partner).toContain('auditor')
  })

  it('manager 包含 auditor', () => {
    expect(ROLE_HIERARCHY.manager).toContain('auditor')
  })

  it('admin 包含所有角色', () => {
    expect(ROLE_HIERARCHY.admin).toEqual(
      expect.arrayContaining(['admin', 'partner', 'manager', 'auditor', 'qc', 'readonly']),
    )
  })

  it('qc 包含 auditor', () => {
    expect(ROLE_HIERARCHY.qc).toContain('auditor')
  })
})

describe('roleIncludes — 角色继承判断', () => {
  it('partner 包含 manager 权限', () => {
    expect(roleIncludes('partner', 'manager')).toBe(true)
  })

  it('partner 包含 auditor 权限', () => {
    expect(roleIncludes('partner', 'auditor')).toBe(true)
  })

  it('manager 包含 auditor 权限', () => {
    expect(roleIncludes('manager', 'auditor')).toBe(true)
  })

  it('manager 不包含 partner 权限', () => {
    expect(roleIncludes('manager', 'partner')).toBe(false)
  })

  it('auditor 不包含 manager 权限', () => {
    expect(roleIncludes('auditor', 'manager')).toBe(false)
  })

  it('admin 包含所有权限', () => {
    expect(roleIncludes('admin', 'partner')).toBe(true)
    expect(roleIncludes('admin', 'manager')).toBe(true)
    expect(roleIncludes('admin', 'auditor')).toBe(true)
    expect(roleIncludes('admin', 'qc')).toBe(true)
  })

  it('别名通过标准化后正确判断', () => {
    expect(roleIncludes('assistant', 'auditor')).toBe(true)
    expect(roleIncludes('pm', 'auditor')).toBe(true)
  })

  it('空值返回 false', () => {
    expect(roleIncludes(null, 'manager')).toBe(false)
    expect(roleIncludes('', 'manager')).toBe(false)
  })
})

describe('快捷判断函数', () => {
  describe('isPartnerOrAbove', () => {
    it('partner 通过', () => {
      expect(isPartnerOrAbove('partner')).toBe(true)
    })

    it('admin 通过', () => {
      expect(isPartnerOrAbove('admin')).toBe(true)
    })

    it('manager 不通过', () => {
      expect(isPartnerOrAbove('manager')).toBe(false)
    })

    it('auditor 不通过', () => {
      expect(isPartnerOrAbove('auditor')).toBe(false)
    })
  })

  describe('isManagerOrAbove', () => {
    it('partner / admin / manager 通过', () => {
      expect(isManagerOrAbove('partner')).toBe(true)
      expect(isManagerOrAbove('admin')).toBe(true)
      expect(isManagerOrAbove('manager')).toBe(true)
    })

    it('auditor 不通过', () => {
      expect(isManagerOrAbove('auditor')).toBe(false)
    })

    it('assistant 别名识别为 auditor，不通过', () => {
      expect(isManagerOrAbove('assistant')).toBe(false)
    })
  })

  describe('canDoQC', () => {
    it('admin / partner / qc 通过', () => {
      expect(canDoQC('admin')).toBe(true)
      expect(canDoQC('partner')).toBe(true)
      expect(canDoQC('qc')).toBe(true)
    })

    it('manager 不通过', () => {
      expect(canDoQC('manager')).toBe(false)
    })

    it('auditor 不通过', () => {
      expect(canDoQC('auditor')).toBe(false)
    })

    it('quality_control 别名识别为 qc，通过', () => {
      expect(canDoQC('quality_control')).toBe(true)
    })
  })
})

describe('isEqcrEligible — EQCR 项目级双层判断', () => {
  it('系统级 partner + 项目级 eqcr → 通过', () => {
    expect(isEqcrEligible('partner', 'eqcr')).toBe(true)
  })

  it('系统级 admin + 项目级 eqcr → 通过', () => {
    expect(isEqcrEligible('admin', 'eqcr')).toBe(true)
  })

  it('系统级 partner 但项目级非 eqcr → 不通过', () => {
    expect(isEqcrEligible('partner', 'manager')).toBe(false)
    expect(isEqcrEligible('partner', null)).toBe(false)
  })

  it('系统级 manager 即使项目级 eqcr → 不通过（系统级不够格）', () => {
    expect(isEqcrEligible('manager', 'eqcr')).toBe(false)
  })

  it('系统级 auditor + 项目级 eqcr → 不通过', () => {
    expect(isEqcrEligible('auditor', 'eqcr')).toBe(false)
  })
})
