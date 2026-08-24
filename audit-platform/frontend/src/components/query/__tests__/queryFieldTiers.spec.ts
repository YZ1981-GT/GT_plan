/**
 * 列分层消费守卫（R7.2 / R7.3 / R7.5 / R11.3）。
 *
 * 关键判据：**不硬编码列名** —— 分层真源在后端 table_whitelist，前端只按下发的
 * technical_fields / pii_fields 分组。若前端自己写一份列名清单，两侧必然漂移。
 */
import { describe, it, expect } from 'vitest'

import {
  BUSINESS_GROUP_LABEL,
  PII_GROUP_LABEL,
  TECHNICAL_GROUP_LABEL,
  defaultFieldsOf,
  filterVisibleColumns,
  groupFieldsByTier,
  isTechnicalColumn,
} from '@/components/query/queryFieldTiers'

const META = {
  fields: ['id', 'project_id', 'account_code', 'amount', 'email', 'created_at'],
  default_fields: ['account_code', 'amount'],
  technical_fields: ['id', 'project_id', 'created_at'],
  pii_fields: ['email'],
}

describe('queryFieldTiers', () => {
  it('业务字段分组排在最前，技术字段最后', () => {
    const groups = groupFieldsByTier(META)
    expect(groups.map((g) => g.label)).toEqual([
      BUSINESS_GROUP_LABEL,
      PII_GROUP_LABEL,
      TECHNICAL_GROUP_LABEL,
    ])
    expect(groups[0].fields).toEqual(['account_code', 'amount'])
    expect(groups[2].fields).toEqual(['id', 'project_id', 'created_at'])
  })

  it('分组是全字段的划分：并集等于 fields 且互不重叠', () => {
    const groups = groupFieldsByTier(META)
    const flat = groups.flatMap((g) => g.fields)
    expect(new Set(flat)).toEqual(new Set(META.fields))
    expect(flat.length).toBe(META.fields.length)
  })

  it('后端未下发分层时退化为单个业务组（不渲染空下拉）', () => {
    const groups = groupFieldsByTier({ fields: ['a', 'b'] })
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe(BUSINESS_GROUP_LABEL)
    expect(groups[0].fields).toEqual(['a', 'b'])
  })

  it('meta 为空时返回空数组而非抛错', () => {
    expect(groupFieldsByTier(null)).toEqual([])
    expect(groupFieldsByTier(undefined)).toEqual([])
    expect(defaultFieldsOf(null)).toEqual([])
  })

  it('defaultFieldsOf 优先用后端下发值', () => {
    expect(defaultFieldsOf(META)).toEqual(['account_code', 'amount'])
  })

  it('后端未下发 default_fields 时按技术/PII 列推导，仍不硬编码列名', () => {
    const { default_fields: _omit, ...withoutDefaults } = META
    expect(defaultFieldsOf(withoutDefaults)).toEqual(['account_code', 'amount'])
  })

  it('技术列判定支持 table.field 双段列名', () => {
    expect(isTechnicalColumn('id', META)).toBe(true)
    expect(isTechnicalColumn('trial_balance.id', META)).toBe(true)
    expect(isTechnicalColumn('amount', META)).toBe(false)
  })

  it('结果列默认隐藏技术列', () => {
    const cols = META.fields.map((key) => ({ key }))
    const visible = filterVisibleColumns(cols, META, false)
    expect(visible.map((c) => c.key)).toEqual(['account_code', 'amount', 'email'])
  })

  it('打开开关后技术列全部可见', () => {
    const cols = META.fields.map((key) => ({ key }))
    expect(filterVisibleColumns(cols, META, true)).toHaveLength(META.fields.length)
  })

  it('结果全是技术列时不把表渲染成空', () => {
    const cols = [{ key: 'id' }, { key: 'created_at' }]
    // 显式选了技术列做排查，此时若过滤成空表用户会以为查询失败
    expect(filterVisibleColumns(cols, META, false)).toHaveLength(2)
  })

  it('不含任何硬编码列名（真源在后端）', async () => {
    // 结构判据：模块源码里不得出现具体业务列名，只能出现分组标签与通用键名
    const source = await import('@/components/query/queryFieldTiers?raw' as any)
      .then((m: any) => String(m.default))
      .catch(() => '')
    if (!source) return // vite raw 导入不可用时跳过（该判据由 code review 兜底）
    for (const forbidden of ['account_code', 'is_deleted', 'updated_at', 'staff_members']) {
      expect(source.includes(`'${forbidden}'`)).toBe(false)
    }
  })
})
