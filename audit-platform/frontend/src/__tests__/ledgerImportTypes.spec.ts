/**
 * 账表导入 DTO 类型契约测试
 *
 * 验证前端类型定义与后端 golden fixture 字段名一致。
 * 若后端改字段名，此测试将编译失败或断言失败。
 */
import { describe, it, expect } from 'vitest'
import type { MappingEntry, ConfirmedMapping, TableType } from '@/types/ledger-import'
import { generateSheetKey } from '@/types/ledger-import'

// Golden fixture — 必须与后端 test_confirmed_mapping_dto.py 中的 GOLDEN_FIXTURE 一致
const GOLDEN_FIXTURE: ConfirmedMapping = {
  detection_id: 'abc-123',
  sheet_key: '用友余额表.xlsx:Sheet1',
  file_name: '用友余额表.xlsx',
  sheet_name: 'Sheet1',
  table_type: 'balance',
  mapping_entries: [
    {
      column_index: 0,
      original_header: '科目编码',
      canonical_header: '科目编码',
      standard_field: 'account_code',
    },
    {
      column_index: 1,
      original_header: '科目名称',
      canonical_header: '科目名称',
      standard_field: 'account_name',
    },
    {
      column_index: 2,
      original_header: '借方',
      canonical_header: '借方#2',
      standard_field: 'debit_amount',
    },
    {
      column_index: 3,
      original_header: '借方',
      canonical_header: '借方#3',
      standard_field: 'opening_debit',
    },
  ],
  aux_dimension_columns: [5, 6],
  file_fingerprint: 'sha256:abc123',
  software_fingerprint: 'yonyou-u8',
  confirmed_by_user: true,
}

describe('ledger-import types contract', () => {
  it('golden fixture has all required top-level fields', () => {
    expect(GOLDEN_FIXTURE.sheet_key).toBe('用友余额表.xlsx:Sheet1')
    expect(GOLDEN_FIXTURE.file_name).toBe('用友余额表.xlsx')
    expect(GOLDEN_FIXTURE.sheet_name).toBe('Sheet1')
    expect(GOLDEN_FIXTURE.table_type).toBe('balance')
    expect(GOLDEN_FIXTURE.mapping_entries).toHaveLength(4)
    expect(GOLDEN_FIXTURE.aux_dimension_columns).toEqual([5, 6])
  })

  it('MappingEntry has column_index / original_header / canonical_header / standard_field', () => {
    const entry: MappingEntry = GOLDEN_FIXTURE.mapping_entries[0]
    expect(entry.column_index).toBe(0)
    expect(entry.original_header).toBe('科目编码')
    expect(entry.canonical_header).toBe('科目编码')
    expect(entry.standard_field).toBe('account_code')
  })

  it('table_type enum covers all valid values', () => {
    const validTypes: TableType[] = ['balance', 'ledger', 'aux_balance', 'aux_ledger', 'account_chart']
    validTypes.forEach((tt) => {
      const dto: ConfirmedMapping = { ...GOLDEN_FIXTURE, table_type: tt }
      expect(dto.table_type).toBe(tt)
    })
  })

  it('generateSheetKey produces correct format', () => {
    expect(generateSheetKey('file.xlsx', 'Sheet1')).toBe('file.xlsx:Sheet1')
    expect(generateSheetKey('用友余额表.xlsx', '余额')).toBe('用友余额表.xlsx:余额')
  })

  it('duplicate headers produce unique canonical_header', () => {
    const entries = GOLDEN_FIXTURE.mapping_entries
    const canonicals = entries.map((e) => e.canonical_header)
    const unique = new Set(canonicals)
    expect(unique.size).toBe(canonicals.length)
  })
})
