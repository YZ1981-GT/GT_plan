/**
 * F2 存货披露子表 ↔ note_template 契约（接入平台共享 helper）
 *
 * 覆盖 P1~P5（子表名逐字一致 / 章节号存在 / group·flat 表态 / 标签纯文本 /
 * 标签列头对齐 headers[0]），另加 F2 专属两条：
 * - 常量 ↔ 载荷键：`buildF2*SubTableData` 实际产出的键必须落在常量集合内
 *   （防 Vue/TS 里手写中文字面量打错字，helper 只能校验常量本身）
 * - (3) 计提方式二选一：两种 mode 的键集合互斥且都被常量覆盖
 *
 * Spec: .kiro/specs/f2-inventory-disclosure-template-alignment/ Sprint 7 R18/R19/R21
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  F2_NOTE_SECTION,
  F2_LISTED_SUBTABLE,
  F2_SOE_SUBTABLE,
} from '../f2NoteSectionMap'
import {
  buildF2ListedColumns,
  buildF2SoeColumns,
  buildF2ListedSubTableData,
  buildF2SoeSubTableData,
  f2ObsoletePortfolioTables,
  type F2ListedS3Mode,
  type F2ListedSyncSnapshot,
  type F2SoeSyncSnapshot,
} from '../f2DisclosureSyncPayload'

// 两个 mode 的列头合并，覆盖模板里 11 张表（(3) 二选一在同步时才收敛）
const LISTED_ALL_COLUMNS = {
  ...buildF2ListedColumns('portfolio'),
  ...buildF2ListedColumns('aging'),
}

runDisclosureSubtableContract({
  cycle: 'F2',
  variants: [
    {
      variant: 'listed',
      section: F2_NOTE_SECTION.listed,
      subtables: F2_LISTED_SUBTABLE,
      columns: LISTED_ALL_COLUMNS,
    },
    {
      variant: 'soe',
      section: F2_NOTE_SECTION.soe,
      subtables: F2_SOE_SUBTABLE,
      columns: buildF2SoeColumns(),
    },
  ],
})

function listedSnap(s3Mode: F2ListedS3Mode): F2ListedSyncSnapshot {
  const zeroClass = {
    rowKey: 'raw-materials',
    label: '原材料',
    endGross: 0,
    endImpairment: 0,
    endNet: 0,
    priorGross: 0,
    priorImpairment: 0,
    priorNet: 0,
  }
  const zeroMove = {
    rowKey: 'raw-materials',
    label: '原材料',
    opening: 0,
    incProvision: 0,
    incOther: 0,
    decReversal: 0,
    decOther: 0,
    ending: 0,
  }
  return {
    section1Rows: [zeroClass],
    section1Total: { label: '合计', ...(({ rowKey, label, ...rest }) => rest)(zeroClass) },
    section2Rows: [zeroMove],
    section2Total: { label: '合计', ...(({ rowKey, label, ...rest }) => rest)(zeroMove) },
    section2QualRows: [{ rowKey: 'raw-materials', label: '原材料', nrvBasis: '', reversalReason: '' }],
    s3EndRows: [],
    s3PriorRows: [],
    s3Mode,
    s4BorrowText: '',
    s4AmortText: '',
    s5Rows: [],
    s6Rows: [],
    s7Rows: [],
    s8DataResourceRows: [],
    noteCategory: '',
    noteNrv: '',
    noteProvision: '',
    noteRe: '',
  }
}

const soeSnap: F2SoeSyncSnapshot = {
  section1Rows: [],
  section1Total: {
    label: '合计',
    endGross: 0,
    endImpairment: 0,
    endNet: 0,
    priorGross: 0,
    priorImpairment: 0,
    priorNet: 0,
  },
  section2Rows: [],
  section2Total: {
    label: '合计',
    opening: 0,
    incProvision: 0,
    incOther: 0,
    decReversal: 0,
    decWriteOff: 0,
    decOther: 0,
    ending: 0,
  },
  s5DataResourceRows: [],
  noteCategory: '',
  landNote: '',
  s3BorrowText: '',
  s4AmortText: '',
  noteText: '',
}

function dataKeys(sub: Record<string, unknown>): string[] {
  return Object.keys(sub).filter((k) => !k.startsWith('_'))
}

describe('F2 载荷键 ↔ 子表名常量', () => {
  const listedNames = new Set<string>(Object.values(F2_LISTED_SUBTABLE))
  const soeNames = new Set<string>(Object.values(F2_SOE_SUBTABLE))

  it.each(['portfolio', 'aging'] as const)(
    '上市（%s）推送的每个数据键都在常量集合内',
    (mode) => {
      const keys = dataKeys(buildF2ListedSubTableData(listedSnap(mode)))
      const strays = keys.filter((k) => !listedNames.has(k))
      expect(strays, `以下表名不在 F2_LISTED_SUBTABLE 中（疑手写字面量打错）`).toEqual([])
    },
  )

  it('国企推送的每个数据键都在常量集合内', () => {
    const strays = dataKeys(buildF2SoeSubTableData(soeSnap)).filter((k) => !soeNames.has(k))
    expect(strays).toEqual([])
  })

  it('(3) 计提方式二选一：两种 mode 的表名互斥，且列头随之切换', () => {
    const p = dataKeys(buildF2ListedSubTableData(listedSnap('portfolio')))
    const a = dataKeys(buildF2ListedSubTableData(listedSnap('aging')))
    expect(p).toContain(F2_LISTED_SUBTABLE.portfolioEnd)
    expect(p).not.toContain(F2_LISTED_SUBTABLE.agingEnd)
    expect(a).toContain(F2_LISTED_SUBTABLE.agingPrior)
    expect(a).not.toContain(F2_LISTED_SUBTABLE.portfolioPrior)

    for (const mode of ['portfolio', 'aging'] as const) {
      const cols = buildF2ListedColumns(mode)
      const keys = dataKeys(buildF2ListedSubTableData(listedSnap(mode)))
      for (const k of keys) expect(cols[k], `${mode} 缺列头: ${k}`).toBeDefined()
      // 列头不得多出未推送的表（否则附注出孤儿列头）
      expect(Object.keys(cols).sort()).toEqual([...keys].sort())
    }
  })

  it('待删表名恒为未选中的那一组，且不与推送键相交', () => {
    for (const mode of ['portfolio', 'aging'] as const) {
      const sub = buildF2ListedSubTableData(listedSnap(mode))
      const removed = sub._removed_table_keys as unknown as string[]
      expect(removed).toEqual(f2ObsoletePortfolioTables(mode))
      for (const r of removed) expect(dataKeys(sub)).not.toContain(r)
      // 待删表名同样必须是模板里的真实表名
      for (const r of removed) expect(listedNames.has(r)).toBe(true)
    }
  })
})
