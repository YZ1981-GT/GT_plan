/**
 * `_disclosureSubtableContract.helper` 自检
 *
 * 用 **K1**（已有完整链路且模板已对齐）反向验证 helper：若 helper 本身有 bug，
 * 这里会红；各循环接入时才能信任它。同时验证 `columnDeclState` 三态判定。
 *
 * Spec: .kiro/specs/disclosure-sync-path-buildout/ Task 1.2
 */
import { describe, expect, it } from 'vitest'
import {
  columnDeclState,
  runDisclosureSubtableContract,
  type ContractColumnDef,
} from './_disclosureSubtableContract.helper'
import { K1_LISTED_SUBTABLE, K1_NOTE_SECTION, K1_SOE_SUBTABLE } from '../k1NoteSectionMap'
import { K1_LISTED_COLUMNS, K1_SOE_COLUMNS } from '../k1DisclosureSyncPayload'

describe('columnDeclState 三态判定', () => {
  const label: ContractColumnDef = { key: 'label', label: '项目', is_label: true }

  it('无列 → none', () => {
    expect(columnDeclState([])).toBe('none')
    expect(columnDeclState(undefined)).toBe('none')
  })

  it('只有列无 group/flat → none（会落入前缀推断）', () => {
    expect(columnDeclState([label, { key: 'a', label: 'A' }])).toBe('none')
  })

  it('任一列标 flat → flat', () => {
    expect(columnDeclState([{ ...label, flat: true }, { key: 'a', label: 'A' }])).toBe('flat')
  })

  it('任一列有 group → group', () => {
    expect(columnDeclState([label, { key: 'a', label: 'A', group: '期末' }])).toBe('group')
  })

  it('两者并存 → conflict', () => {
    expect(
      columnDeclState([{ ...label, flat: true }, { key: 'a', label: 'A', group: '期末' }]),
    ).toBe('conflict')
  })
})

// ── 用 K1 真实数据跑一遍完整契约（helper 自检）─────────────────
const K1_PENDING_REASON =
  'K1 同步载荷未声明 group/flat，依赖后端 _infer_groups_from_headers 前缀推断；属 k1-other-receivable-disclosure-alignment 范围，本 helper 自检不代为修复'

// K1 的同步载荷 columns 全部未声明 group/flat（实测 `flat:` / `group:` 出现次数均为 0），
// 两级表头靠模板侧 `_column_groups` + 后端前缀推断兜住。这是 K1 自身的历史状态，
// 与 helper 正确性无关 → 显式登记为 pending（**不是放宽断言**）：
// helper 的「columnsPending 不得残留已补齐的表」会在 K1 补上 group/flat 后自动转红，提醒移出。
const K1_LISTED_PENDING: Record<string, string> = {
  '按账龄披露': K1_PENDING_REASON,
  '按款项性质披露': K1_PENDING_REASON,
  '期末处于第一阶段的坏账准备': K1_PENDING_REASON,
  '期末处于第二阶段的坏账准备': K1_PENDING_REASON,
  '期末处于第三阶段的坏账准备': K1_PENDING_REASON,
  '上年年末处于第一阶段的坏账准备': K1_PENDING_REASON,
  '上年年末处于第二阶段的坏账准备': K1_PENDING_REASON,
  '上年年末处于第三阶段的坏账准备': K1_PENDING_REASON,
  '本期计提、收回或转回的坏账准备情况': K1_PENDING_REASON,
  '本期转回或收回金额重要的坏账准备': K1_PENDING_REASON,
  '本期实际核销的其他应收款情况': K1_PENDING_REASON,
  '重要的其他应收款核销情况（逐项披露）': K1_PENDING_REASON,
  '按欠款方归集的其他应收款期末余额前五名单位情况': K1_PENDING_REASON,
}
const K1_SOE_PENDING: Record<string, string> = {
  '按账龄披露其他应收款项': K1_PENDING_REASON,
  '按坏账准备计提方法分类披露其他应收款项': K1_PENDING_REASON,
  '续：': K1_PENDING_REASON,
  '单项计提坏账准备的其他应收款项': K1_PENDING_REASON,
  '账龄组合': K1_PENDING_REASON,
  '采用余额百分比法或其他组合方法计提坏账准备的其他应收款项': K1_PENDING_REASON,
  '其他应收款项坏账准备计提情况': K1_PENDING_REASON,
  '其他应收款项账面余额变动': K1_PENDING_REASON,
  '收回或转回的坏账准备': K1_PENDING_REASON,
  '本期实际核销的其他应收款项': K1_PENDING_REASON,
  '按欠款方归集的期末余额前五名的其他应收款项': K1_PENDING_REASON,
  '涉及政府补助的应收款项': K1_PENDING_REASON,
  '由金融资产转移而终止确认的其他应收款项': K1_PENDING_REASON,
  '其他应收款项转移继续涉入形成的资产、负债的金额': K1_PENDING_REASON,
}

runDisclosureSubtableContract({
  cycle: 'K1（helper 自检）',
  variants: [
    {
      variant: 'listed',
      section: K1_NOTE_SECTION.listed,
      subtables: K1_LISTED_SUBTABLE,
      columns: K1_LISTED_COLUMNS as Record<string, ContractColumnDef[]>,
      columnsPending: K1_LISTED_PENDING,
    },
    {
      variant: 'soe',
      section: K1_NOTE_SECTION.soe,
      subtables: K1_SOE_SUBTABLE,
      columns: K1_SOE_COLUMNS as Record<string, ContractColumnDef[]>,
      columnsPending: K1_SOE_PENDING,
    },
  ],
})
