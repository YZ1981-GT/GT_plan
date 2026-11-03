/**
 * K 系负债/递延类（K3/K4/K5/K7）披露子表 ↔ 附注模板契约 + 载荷断言
 *
 * P1~P5 由共享 helper 覆盖；本文件另断言：
 * - K3 只发送按性质与账龄超一年两张 owner 表，绝不写删 L2/M1 表或共享主表
 * - K3 自有账龄超一年条件表无行时不推且进入 `_removed_table_keys`
 * - K4 债券续表名已由泄漏名 `债券名称` 正名为「短期应付债券（续）」，旧键进 removed
 * - 共享主表派生与三 owner 排列由后端 `test_wp_disclosure_other_payables_owners.py` 验证
 * - 底稿审计分析段（按账龄 / 前五名）不进载荷
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 9
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  K3_DISCLOSURE_SHEET_NAME,
  K3_LEGACY_OBSOLETE_TABLES,
  K3_LISTED_SUBTABLE,
  K3_NOTE_SECTION,
  K3_SOE_SUBTABLE,
  K3_TABLE_SCOPE,
  buildK3ListedColumns,
  buildK3SoeColumns,
  buildK3SyncPayload,
  type K3DisclosureSnapshot,
} from '../k3NoteSectionMap'
import {
  K4_LEGACY_OBSOLETE_TABLES,
  K4_NOTE_SECTION,
  K4_SUBTABLE,
  buildK4ListedColumns,
  buildK4SoeColumns,
  buildK4SyncPayload,
} from '../k4NoteSectionMap'
import {
  K5_NOTE_SECTION,
  K5_SUBTABLE,
  buildK5ListedColumns,
  buildK5SoeColumns,
} from '../k5NoteSectionMap'
import {
  K7_LISTED_SUBTABLE,
  K7_NOTE_SECTION,
  K7_SOE_SUBTABLE,
  buildK7ListedColumns,
  buildK7SoeColumns,
  buildK7SyncPayload,
  grantDetailEndAmount,
  type K7GrantDetailRow,
} from '../k7NoteSectionMap'

// ─── 共享 helper：P1~P5 ──────────────────────────────────────────────────────

runDisclosureSubtableContract({
  cycle: 'K3',
  variants: [
    { variant: 'listed', section: K3_NOTE_SECTION.listed, subtables: K3_LISTED_SUBTABLE, columns: buildK3ListedColumns() },
    { variant: 'soe', section: K3_NOTE_SECTION.soe, subtables: K3_SOE_SUBTABLE, columns: buildK3SoeColumns() },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K4',
  variants: [
    {
      variant: 'listed',
      section: K4_NOTE_SECTION.listed,
      subtables: K4_SUBTABLE,
      columns: buildK4ListedColumns({ includeBond: true, includeBondCont: true }),
    },
    {
      variant: 'soe',
      section: K4_NOTE_SECTION.soe,
      subtables: { summary: K4_SUBTABLE.summary },
      columns: buildK4SoeColumns(),
    },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K5',
  variants: [
    { variant: 'listed', section: K5_NOTE_SECTION.listed, subtables: K5_SUBTABLE, columns: buildK5ListedColumns() },
    { variant: 'soe', section: K5_NOTE_SECTION.soe, subtables: K5_SUBTABLE, columns: buildK5SoeColumns() },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K7',
  variants: [
    { variant: 'listed', section: K7_NOTE_SECTION.listed, subtables: K7_LISTED_SUBTABLE, columns: buildK7ListedColumns() },
    { variant: 'soe', section: K7_NOTE_SECTION.soe, subtables: K7_SOE_SUBTABLE, columns: buildK7SoeColumns() },
  ],
})

// ─── 模板侧结构（fix_note_k_liability_structure.py 成果防回退）───────────────

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

interface NoteTable {
  name?: string
  headers?: string[]
  columns?: Array<Record<string, unknown>>
  guidance?: string
  rows?: Array<Record<string, unknown>>
  _column_groups?: unknown
}

function loadSection(file: string, sectionNumber: string): { tables?: NoteTable[] } {
  const raw = JSON.parse(readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8')) as {
    sections: Array<{ section_number?: string; tables?: NoteTable[] }>
  }
  const hit = raw.sections.find(s => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const FILE_OF = { listed: 'note_template_listed.json', soe: 'note_template_soe.json' } as const

const SECTIONS = [
  ['listed', K3_NOTE_SECTION.listed],
  ['soe', K3_NOTE_SECTION.soe],
  ['listed', K4_NOTE_SECTION.listed],
  ['soe', K4_NOTE_SECTION.soe],
  ['listed', K5_NOTE_SECTION.listed],
  ['soe', K5_NOTE_SECTION.soe],
  ['listed', K7_NOTE_SECTION.listed],
  ['soe', K7_NOTE_SECTION.soe],
] as const

const PLACEHOLDER_ROWS = ['可无限量添加行', '......', '……']
const LEAKED_NAMES = ['项  目', '其他应付款（表6）', '债券名称']

describe('K 系负债/递延类模板结构', () => {
  it.each(SECTIONS)('%s §%s 每张表都有 columns + guidance、显式 flat、无 _column_groups', (variant, section) => {
    const sec = loadSection(FILE_OF[variant], section)
    for (const t of sec.tables ?? []) {
      expect((t.columns ?? []).length, `${t.name} 缺 columns`).toBeGreaterThan(0)
      expect(String(t.guidance ?? '').trim(), `${t.name} 缺 guidance`).not.toBe('')
      expect((t.columns ?? []).some(c => c.flat === true), `${t.name} 未显式 flat`).toBe(true)
      expect((t.columns ?? []).some(c => c.group), `${t.name} 不应有 group`).toBe(false)
      expect(t._column_groups, `${t.name} 标了 flat 却留 _column_groups`).toBeUndefined()
      expect((t.columns ?? []).map(c => String(c.label)), `${t.name} columns/headers 不同形`).toEqual(t.headers)
    }
  })

  it.each(SECTIONS)('%s §%s 无泄漏表名；可扩位标记行只能是 expandable', (variant, section) => {
    const sec = loadSection(FILE_OF[variant], section)
    const names = (sec.tables ?? []).map(t => String(t.name))
    for (const leaked of LEAKED_NAMES) expect(names).not.toContain(leaked)
    for (const t of sec.tables ?? []) {
      // 源模板的「可无限量添加行」「……」是可扩位（平台 `row_type: expandable`，零可见内容、不参与合计；
      // 判据 note_expandable_markers），不是占位数据行 —— 原断言「不得出现」写在 expandable 行型之前，与之相反
      for (const r of t.rows ?? []) {
        if (PLACEHOLDER_ROWS.includes(String(r.label ?? ''))) {
          expect(String(r.row_type ?? ''), `${t.name}「${r.label}」`).toBe('expandable')
        }
      }
      expect((t.rows ?? []).some(r => String(r.row_type ?? '') === 'header_label')).toBe(false)
    }
  })

  it('K3 表数：上市 7 / 国企 6，且子表名映射覆盖全部模板表', () => {
    const listed = loadSection(FILE_OF.listed, K3_NOTE_SECTION.listed)
    const soe = loadSection(FILE_OF.soe, K3_NOTE_SECTION.soe)
    expect((listed.tables ?? []).length).toBe(7)
    expect((soe.tables ?? []).length).toBe(6)
    expect(new Set((listed.tables ?? []).map(t => String(t.name)))).toEqual(
      new Set(Object.values(K3_LISTED_SUBTABLE)),
    )
    expect(new Set((soe.tables ?? []).map(t => String(t.name)))).toEqual(
      new Set(Object.values(K3_SOE_SUBTABLE)),
    )
  })

  it('K4 债券续表已正名（旧名是表头首格泄漏）', () => {
    expect(K4_SUBTABLE.bondCont).toBe('短期应付债券（续）')
    expect(K4_LEGACY_OBSOLETE_TABLES).toContain('债券名称')
    const names = (loadSection(FILE_OF.listed, K4_NOTE_SECTION.listed).tables ?? []).map(t => String(t.name))
    expect(names).toContain('短期应付债券（续）')
    expect(names).not.toContain('债券名称')
  })

  it('K5 两版都是 4 列（末列形成原因，国企按底稿 K5 国企第 6 行，R8.4 批 9b-2）', () => {
    expect(buildK5ListedColumns()[K5_SUBTABLE.provision]).toHaveLength(4)
    expect(buildK5SoeColumns()[K5_SUBTABLE.provision]).toHaveLength(4)
  })

  it('K7 国企含政府补助明细 10 列表（模板侧已补 columns/guidance）', () => {
    const soe = loadSection(FILE_OF.soe, K7_NOTE_SECTION.soe)
    const grant = (soe.tables ?? []).find(t => t.name === K7_SOE_SUBTABLE.grantDetail)
    expect(grant, '模板缺政府补助明细表').toBeDefined()
    expect(grant!.headers).toHaveLength(10)
    expect((grant!.columns ?? []).map(c => String(c.label))).toEqual(grant!.headers)
  })

  it('K7 政府补助明细表只在国企版（上市 五、51 无此表 → 推了就是孤儿表）', () => {
    expect(Object.values(K7_LISTED_SUBTABLE)).not.toContain(K7_SOE_SUBTABLE.grantDetail)
    const listedNames = (loadSection(FILE_OF.listed, K7_NOTE_SECTION.listed).tables ?? [])
      .map(t => String(t.name))
    expect(listedNames).not.toContain(K7_SOE_SUBTABLE.grantDetail)
  })

  it('K7 国企同步 columns 的键与 label 逐位等于模板（防列键漂移）', () => {
    const soe = loadSection(FILE_OF.soe, K7_NOTE_SECTION.soe)
    const cols = buildK7SoeColumns()
    for (const t of soe.tables ?? []) {
      const mine = cols[String(t.name)]
      expect(mine, `${t.name} 缺同步列定义`).toBeDefined()
      expect(mine!.map(c => c.key)).toEqual((t.columns ?? []).map(c => String(c.key)))
      expect(mine!.map(c => c.label)).toEqual(t.headers)
    }
  })

  it('K3 sheet_name 是半角括号（源 xlsx 即如此，勿统一为全角）', () => {
    expect(K3_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息(上市公司)')
    expect(K3_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息(国企)')
  })
})

// ─── K7 载荷：政府补助明细表 ────────────────────────────────────────────────

function grant(overrides: Partial<K7GrantDetailRow> = {}): K7GrantDetailRow {
  return {
    grantItem: '技改专项补助',
    beginBalance: 1000,
    newGrant: 500,
    toPl: 200,
    plLineItem: '其他收益',
    refund: 100,
    otherChange: 50,
    grantKind: '与资产相关',
    refundReason: '未达产能指标',
    ...overrides,
  }
}

const K7_MAIN_ROWS = [{ project: '设备购置补助', beginBalance: 1000, increase: 500, decrease: 350 }]

describe('buildK7SyncPayload 政府补助明细表', () => {
  it('F51-7a~7d：期末 = 期初 + 新增 − 计入损益 − 返还 − 其他变动', () => {
    expect(grantDetailEndAmount(grant())).toBe(1150)
  })

  it('国企有明细行 → 推 2 张表，列定义同步带上第 2 张', () => {
    const p = buildK7SyncPayload('soe', 'wp-1', K7_MAIN_ROWS, '', [grant()])
    const T = K7_SOE_SUBTABLE
    expect(Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))).toEqual([
      T.deferredIncome, T.grantDetail,
    ])
    expect(p.columns[T.grantDetail]).toHaveLength(10)
    const rows = p.sub_table_data[T.grantDetail] as Array<Record<string, unknown>>
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({ grant_item: '技改专项补助', end_amount: 1150, grant_kind: '与资产相关' })
    expect(rows[1]).toMatchObject({ grant_item: '合计', is_total: true, end_amount: 1150, begin_amount: 1000 })
  })

  it('无明细行 → 不推空表 + columns 剔除 + 进 removed（防删空后附注残留孤儿表）', () => {
    const p = buildK7SyncPayload('soe', 'wp-1', K7_MAIN_ROWS, '', [])
    const T = K7_SOE_SUBTABLE
    expect(p.sub_table_data[T.grantDetail]).toBeUndefined()
    expect(p.columns[T.grantDetail]).toBeUndefined()
    expect(p.sub_table_data._removed_table_keys).toEqual([T.grantDetail])
    // 主表始终推送，绝不能被 removed 带走
    expect(p.sub_table_data[T.deferredIncome]).toBeDefined()
    expect(p.sub_table_data._removed_table_keys).not.toContain(T.deferredIncome)
  })

  it('有明细行时不得把本次推送键放进 removed（否则刚推就被删）', () => {
    const p = buildK7SyncPayload('soe', 'wp-1', K7_MAIN_ROWS, '', [grant()])
    const removed = (p.sub_table_data._removed_table_keys ?? []) as string[]
    for (const pushed of Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))) {
      expect(removed).not.toContain(pushed)
    }
  })

  it('全空白骨架行（点了「+补助项目」但未填）不算数据行', () => {
    const blank: K7GrantDetailRow = {
      grantItem: '', beginBalance: 0, newGrant: 0, toPl: 0, refund: 0, otherChange: 0,
    }
    const p = buildK7SyncPayload('soe', 'wp-1', K7_MAIN_ROWS, '', [blank])
    expect(p.sub_table_data[K7_SOE_SUBTABLE.grantDetail]).toBeUndefined()
  })

  it('上市版传了明细行也不推、也不 removed（五、51 无该表，removed 会误伤别的底稿）', () => {
    const p = buildK7SyncPayload('listed', 'wp-1', K7_MAIN_ROWS, '', [grant()])
    expect(Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))).toEqual([
      K7_LISTED_SUBTABLE.deferredIncome,
    ])
    expect(p.columns[K7_SOE_SUBTABLE.grantDetail]).toBeUndefined()
    expect(p.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('P1：行对象业务键 ⊆ columns 键（两张表都查）', () => {
    const p = buildK7SyncPayload('soe', 'wp-1', K7_MAIN_ROWS, '递延收益全部为政府补助', [grant()])
    for (const [name, rows] of Object.entries(p.sub_table_data)) {
      if (name.startsWith('_')) continue
      const colKeys = new Set((p.columns[name] ?? []).map(c => c.key))
      expect(colKeys.size, `${name} 无 columns`).toBeGreaterThan(0)
      for (const row of rows as Array<Record<string, unknown>>) {
        for (const k of Object.keys(row)) {
          if (k === 'is_total' || k === 'label' || k === 'values') continue
          expect(colKeys.has(k), `${name}.${k} 无 columns 落点`).toBe(true)
        }
      }
    }
  })
})

// ─── K3 载荷 ────────────────────────────────────────────────────────────────

function snapshot(overrides: Partial<K3DisclosureSnapshot> = {}): K3DisclosureSnapshot {
  return {
    byNature: [
      { project: '押金', endAmount: 100, priorAmount: 60 },
      { project: '质保金', endAmount: 40, priorAmount: 20 },
    ],
    ...overrides,
  }
}

describe('buildK3SyncPayload', () => {
  it('P1：行对象业务键 ⊆ columns 键', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const p = buildK3SyncPayload(variant, 'wp-1', snapshot({
        interest: [{ project: '企业债券利息', endAmount: 5, priorAmount: 3 }],
        dividend: [{ project: '普通股股利', endAmount: 7, priorAmount: 4 }],
        interestOverdue: [{ unit: '甲银行', amount: 9, reason: '资金紧张' }],
        dividendOverdue: [{ shareholder: '乙股东', amount: 11, reason: '待决议' }],
        agingOver1y: [{ name: '丙单位', endAmount: 13, reason: '尚未结算' }],
      }))
      for (const [name, rows] of Object.entries(p.sub_table_data)) {
        if (name.startsWith('_')) continue
        const colKeys = new Set((p.columns[name] ?? []).map(c => c.key))
        expect(colKeys.size, `${name} 无 columns`).toBeGreaterThan(0)
        for (const row of rows as Array<Record<string, unknown>>) {
          for (const k of Object.keys(row)) {
            if (k === 'is_total') continue
            expect(colKeys.has(k), `${name}.${k} 无 columns 落点`).toBe(true)
          }
        }
      }
    }
  })

  it.each(['listed', 'soe'] as const)('%s 只发送 K3 独占表，主表/利息/股利输入均被忽略', (variant) => {
    const p = buildK3SyncPayload(variant, 'wp-1', snapshot({
      interest: [{ project: '企业债券利息', endAmount: 5, priorAmount: 3 }],
      dividend: [{ project: '普通股股利', endAmount: 7, priorAmount: 4 }],
      interestOverdue: [{ unit: '甲银行', amount: 9 }],
      dividendOverdue: [{ shareholder: '乙股东', amount: 11 }],
      agingOver1y: [{ name: '丙单位', endAmount: 13, reason: '未结算' }],
    }))
    const keys = Object.keys(p.sub_table_data).filter((key) => !key.startsWith('_')).sort()
    expect(keys).toEqual([...K3_TABLE_SCOPE[variant]].sort())
    expect(Object.keys(p.columns).sort()).toEqual([...K3_TABLE_SCOPE[variant]].sort())
    const T = variant === 'listed' ? K3_LISTED_SUBTABLE : K3_SOE_SUBTABLE
    const forbidden: string[] = [T.summary, T.interest, T.interestOverdue, T.dividend]
    if (variant === 'listed') forbidden.push(K3_LISTED_SUBTABLE.dividendOverdue)
    const removed = (p.sub_table_data._removed_table_keys ?? []) as string[]
    for (const name of forbidden) {
      expect(p.sub_table_data[name]).toBeUndefined()
      expect(p.columns[name]).toBeUndefined()
      expect(removed).not.toContain(name)
    }
  })

  it('K3 自有长期挂账表无行 → 不推且进入删除清单', () => {
    const p = buildK3SyncPayload('listed', 'wp-1', snapshot())
    const T = K3_LISTED_SUBTABLE
    const removed = p.sub_table_data._removed_table_keys as string[]
    for (const name of [T.agingOver1y]) {
      expect(p.sub_table_data[name]).toBeUndefined()
      expect(p.columns[name]).toBeUndefined()
      expect(removed).toContain(name)
    }
    for (const legacy of K3_LEGACY_OBSOLETE_TABLES.listed) expect(removed).toContain(legacy)
  })

  it('应付利息 / 应付股利未接线时不推空表（防整表覆盖模板骨架），也不进 removed', () => {
    const p = buildK3SyncPayload('listed', 'wp-1', snapshot())
    const T = K3_LISTED_SUBTABLE
    const removed = (p.sub_table_data._removed_table_keys ?? []) as string[]
    for (const name of [T.interest, T.dividend]) {
      expect(p.sub_table_data[name]).toBeUndefined()
      expect(p.columns[name]).toBeUndefined()
      expect(removed).not.toContain(name)
    }
  })

  it('国企无「超过1年未支付的应付股利」表', () => {
    const p = buildK3SyncPayload('soe', 'wp-1', snapshot({
      dividendOverdue: [{ shareholder: '乙股东', amount: 11 }],
    }))
    expect(Object.keys(p.sub_table_data)).not.toContain('重要的超过1年未支付的应付股利')
  })

  it('入参里的合计行被剔除（防双合计）', () => {
    const p = buildK3SyncPayload('soe', 'wp-1', snapshot({
      byNature: [
        { project: '应付往来款', endAmount: 10, priorAmount: 5 },
        { project: '合  计', endAmount: 10, priorAmount: 5 },
      ],
    }))
    const rows = p.sub_table_data[K3_SOE_SUBTABLE.byNature] as Array<Record<string, unknown>>
    expect(rows.filter(r => r.is_total)).toHaveLength(1)
    expect(rows).toHaveLength(2)
  })

  it('narrativeText 空则不推 _note_texts', () => {
    expect(buildK3SyncPayload('soe', 'wp-1', snapshot()).sub_table_data._note_texts).toBeUndefined()
    expect(
      buildK3SyncPayload('soe', 'wp-1', snapshot({ narrativeText: ' 押金主要为工程履约押金 ' }))
        .sub_table_data._note_texts,
    ).toEqual([{ section: 'k3-note', title: '其他应付款说明', text: '押金主要为工程履约押金' }])
  })
})

describe('buildK4SyncPayload 旧表名清理', () => {
  it('上市载荷携 _removed_table_keys 含旧泄漏名，且不含本次推送键', () => {
    const p = buildK4SyncPayload('listed', 'wp-1', [{ project: '短期应付债券', endAmount: 10, priorAmount: 5 }], '')
    const removed = (p.sub_table_data._removed_table_keys ?? []) as string[]
    expect(removed).toContain('债券名称')
    for (const pushed of Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))) {
      expect(removed).not.toContain(pushed)
    }
  })

  it('国企侧不产生 removed（无表名变更）', () => {
    const p = buildK4SyncPayload('soe', 'wp-1', [{ project: '待转销项税额', endAmount: 1, priorAmount: 1 }], '')
    expect(p.sub_table_data._removed_table_keys).toBeUndefined()
  })
})
