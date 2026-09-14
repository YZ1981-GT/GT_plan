/**
 * H 循环披露子表契约（H4 在建工程·国企）
 *
 * 复用共享 helper 的 P1~P6，另加本批专属断言：
 * - H4 国企**推 H2 的章节**（§八、23，共章节浅合并）→ 表名必须取 `H2_SOE_SUBTABLE`
 * - H4 汇总表是两级表头（期末/期初 × 账面余额/减值准备/账面价值），账面价值派生
 * - H5 上市**豁免**反向锁死：variant matrix 的 listed 为 null
 *
 * 🔴 **H7 不在此契约内**：源模板 §五、24/八、24 是转置成本矩阵 +公允价值变动表，
 *    现有组件无法在不自造的前提下映射 → 保留在 MISSING_SYNC_PATH，待结构对齐重建。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 3.1 / 3.4
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import { H2_NOTE_SECTION, H2_SOE_SUBTABLE } from '../h2NoteSectionMap'
import {
  buildH4SoeColumns,
  buildH4SoeSyncPayloads,
} from '../h4SoeDisclosureSyncPayload'
import { createDefaultH4SoeSummary } from '../h4SoeDisclosureModel'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function loadMatrix(): { accounts: Array<{ section_title?: string; variants?: Record<string, string | null> }> } {
  const p = resolve(REPO_ROOT, 'backend/data/note_template_variant_matrix.json')
  return JSON.parse(readFileSync(p, 'utf-8'))
}

// ─── P1~P6 共享契约 ──────────────────────────────────────────────────────────

runDisclosureSubtableContract({
  cycle: 'H4(soe→H2 §八、23)',
  variants: [
    {
      variant: 'soe',
      section: H2_NOTE_SECTION.soe,
      subtables: { summary: H2_SOE_SUBTABLE.summary },
      columns: buildH4SoeColumns(),
    },
  ],
})

// ─── H4 专属 ─────────────────────────────────────────────────────────────────

describe('H4 在建工程（国企）披露映射', () => {
  it('推 H2 的章节与子表名（共章节浅合并，不另造表名）', () => {
    const payloads = buildH4SoeSyncPayloads('wp-1', null, {
      summary: createDefaultH4SoeSummary(),
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(H2_NOTE_SECTION.soe)
    expect(Object.keys(payloads[0].sub_table_data)).toEqual([H2_SOE_SUBTABLE.summary])
  })

  it('汇总表是两级表头（期末余额 / 期初余额 × 账面余额·减值准备·账面价值）', () => {
    const cols = buildH4SoeColumns()[H2_SOE_SUBTABLE.summary]
    expect(cols.some((c) => c.group)).toBe(true)
    expect(cols.some((c) => c.flat)).toBe(false)
    expect(cols.filter((c) => c.group === '期末余额').map((c) => c.label))
      .toEqual(['账面余额', '减值准备', '账面价值'])
    expect(cols.filter((c) => c.group === '期初余额').map((c) => c.label))
      .toEqual(['账面余额', '减值准备', '账面价值'])
    // 标签列不得带 group
    expect(cols[0].group).toBeUndefined()
    expect(cols[0].is_label).toBe(true)
  })

  it('账面价值读时派生 = 账面余额 − 减值准备，合计行由明细汇总', () => {
    const payloads = buildH4SoeSyncPayloads('wp-1', null, {
      summary: [
        { key: 'cip', label: '在建工程', endBook: 1000, endImpairment: 100, beginBook: 800, beginImpairment: 50 },
        { key: 'materials', label: '工程物资', endBook: 200, endImpairment: 0, beginBook: 150, beginImpairment: 0 },
      ],
    })
    const rows = payloads[0].sub_table_data[H2_SOE_SUBTABLE.summary]
    expect(rows[0].end_carrying).toBe(900)
    expect(rows[1].end_carrying).toBe(200)
    const total = rows[rows.length - 1]
    expect(total.is_total).toBe(true)
    expect(total.end_book).toBe(1200)
    expect(total.end_impairment).toBe(100)
    expect(total.end_carrying).toBe(1100)
    expect(total.begin_carrying).toBe(900)
  })

  it('合计行字面带空格（源模板「合  计」）', () => {
    const payloads = buildH4SoeSyncPayloads('wp-1', null, { summary: createDefaultH4SoeSummary() })
    const rows = payloads[0].sub_table_data[H2_SOE_SUBTABLE.summary]
    expect(String(rows[rows.length - 1].label).replace(/\s+/g, '')).toBe('合计')
  })

  it('不适用变体返回空数组（跳过同步）', () => {
    expect(buildH4SoeSyncPayloads('wp-1', ['listed_standalone'], {
      summary: createDefaultH4SoeSummary(),
    })).toEqual([])
  })
})

// ─── H5 上市豁免反向锁死 ─────────────────────────────────────────────────────

describe('H5 油气资产上市侧豁免（有意无链路）', () => {
  it('variant matrix 的 listed 为 null → 上市公司无油气资产附注章节', () => {
    const matrix = loadMatrix()
    const acct = matrix.accounts.find((a) => a.section_title === '油气资产')
    expect(acct, 'variant matrix 缺「油气资产」条目').toBeDefined()
    expect(
      acct!.variants!.listed_standalone,
      '若上市侧出现章节号，H5TabDisclosureListed 就该补链路并从 MISSING_SYNC_PATH 移出',
    ).toBeNull()
    expect(acct!.variants!.soe_standalone).toBe('八、25')
  })
})
