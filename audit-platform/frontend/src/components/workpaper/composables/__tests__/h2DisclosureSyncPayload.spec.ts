/**
 * H2 披露 → 附注 sync payload 契约测试
 * spec: h2-disclosure-linkage-and-prefill（Property 1 / 2 / 5 / 11）
 *
 * 契约以后端为权威（勿改回 `{label, values:[]}` 行形态）：
 * - `note_sub_table_projector.project_sub_tables` 按 `row.get(colDef.key)` 取值，
 *   故 sub_table_data 的行必须是 keyed dict，键与 columns[key][].key 一致；
 * - 叙述正文放 `sub_table_data['_note_texts']`（服务端 `_extract_note_texts` pop
 *   后写 text_content）；`SyncFromWorkpaperRequest` 无顶层 `_note_texts` 字段；
 * - 子表键集合 = 模板 tables[].name（listed 五、23 恰 6 张 / soe 八、23 恰 4 张）。
 *   受限（抵押）在建工程不在模板内 → 走 _note_texts，不产子表。
 */
import { describe, it, expect } from 'vitest'
import {
  buildH2SyncPayload,
  buildH2ListedColumns,
  buildH2SoeColumns,
  buildH2ListedSyncPayloads,
  buildH2SoeSyncPayloads,
  type H2ListedSyncSnapshot,
  type H2SoeSyncSnapshot,
} from '../h2DisclosureSyncPayload'
import { H2_LISTED_SUBTABLE, H2_SOE_SUBTABLE } from '../h2NoteSectionMap'
import { createDefaultListedMaterials, createDefaultListedSummary } from '../h2ListedDisclosureModel'
import { createDefaultSoeSummary } from '../h2SoeDisclosureModel'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function emptyListedSnapshot(): H2ListedSyncSnapshot {
  return {
    summary: createDefaultListedSummary(),
    detail: [],
    projects: [],
    impairment: [],
    materials: createDefaultListedMaterials(),
    mortgage: [],
    noteImpairment: '',
    noteFundSource: '',
    noteMortgage: '',
  }
}

function populatedListedSnapshot(): H2ListedSyncSnapshot {
  return {
    ...emptyListedSnapshot(),
    detail: [{ rowId: 'd1', name: '厂房工程', endBook: 600000, endImpairment: 50000, priorBook: 500000, priorImpairment: 30000 }],
    projects: [{
      rowId: 'p1', name: '厂房扩建', beginBalance: 500000, increase: 200000, transferToFA: 100000, otherDecrease: 0,
      interestCapAccum: 10000, interestCapCurrent: 5000, interestCapRate: 4.5,
      budget: 2000000, cumInputPct: 35, accumulatedInput: 700000, progress: '35%', fundSource: '自筹',
    }],
    impairment: [{ rowId: 'i1', name: '厂房工程', beginBalance: 30000, provision: 20000, decrease: 0 }],
    mortgage: [{ rowId: 'm1', name: '厂房扩建', amount: 300000, description: '银行借款抵押', remark: '' }],
    noteImpairment: '已执行减值测试',
  }
}

function emptySoeSnapshot(): H2SoeSyncSnapshot {
  return {
    summary: createDefaultSoeSummary(),
    detail: [],
    projects: [],
    impairment: [],
    noteImpairment: '',
  }
}

function populatedSoeSnapshot(): H2SoeSyncSnapshot {
  return {
    ...emptySoeSnapshot(),
    projects: [{
      rowId: 'p1', name: '码头', beginBalance: 0, increase: 500000, transferToFA: 0, otherDecrease: 0,
      interestCapAccum: 0, interestCapCurrent: 0, interestCapRate: 0,
      budget: 1000000, cumInputPct: 50, accumulatedInput: 500000, progress: '在建', fundSource: '贷款',
    }],
    impairment: [{ rowId: 'i1', name: '码头', provisionAmount: 5000, reason: '停工' }],
    noteImpairment: '本期计提减值',
  }
}

function tableKeys(data: Record<string, unknown>): string[] {
  return Object.keys(data).filter((k) => !k.startsWith('_'))
}

// ─── Property 1 / 2：子表键完整性 ─────────────────────────────────────────────

describe('buildH2SyncPayload - 子表键完整性', () => {
  it('listed 子表键严格等于模板 五、23 的 6 张表', () => {
    const payload = buildH2SyncPayload('listed', populatedListedSnapshot(), { wpId: 'wp-001' })!
    expect(payload).not.toBeNull()
    expect(payload.section_id).toBe('五、23')
    expect(tableKeys(payload.sub_table_data).sort()).toEqual([
      H2_LISTED_SUBTABLE.summary,
      H2_LISTED_SUBTABLE.detail,
      H2_LISTED_SUBTABLE.projectMovement,
      H2_LISTED_SUBTABLE.projectCont,
      H2_LISTED_SUBTABLE.impairment,
      H2_LISTED_SUBTABLE.materials,
    ].sort())
  })

  it('soe 子表键严格等于模板 八、23 的 4 张表', () => {
    const payload = buildH2SyncPayload('soe', populatedSoeSnapshot(), { wpId: 'wp-001' })!
    expect(payload.section_id).toBe('八、23')
    expect(tableKeys(payload.sub_table_data).sort()).toEqual([
      H2_SOE_SUBTABLE.summary,
      H2_SOE_SUBTABLE.detail,
      H2_SOE_SUBTABLE.projectMovement,
      H2_SOE_SUBTABLE.impairment,
    ].sort())
  })

  it('受限（抵押）在建工程不产子表（模板无该表，走 _note_texts）', () => {
    const payload = buildH2SyncPayload('listed', populatedListedSnapshot(), { wpId: 'wp-001' })!
    expect(payload.sub_table_data[H2_LISTED_SUBTABLE.restricted]).toBeUndefined()
    const texts = payload.sub_table_data._note_texts as unknown as Array<{ section: string; text: string }>
    expect(texts.find((t) => t.section === 'listed-mortgage')?.text).toContain('厂房扩建')
  })
})

// ─── 列头契约：keyed row（投影器按 colDef.key 取值）─────────────────────────────

describe('列头 ↔ 行字段契约', () => {
  it('listed 每行的字段键覆盖 columns 声明的非标签键（投影器按名取值）', () => {
    const payload = buildH2SyncPayload('listed', populatedListedSnapshot(), { wpId: 'wp-001' })!
    const columns = buildH2ListedColumns()
    for (const key of tableKeys(payload.sub_table_data)) {
      const defs = columns[key]
      expect(defs, `columns 缺 ${key}`).toBeTruthy()
      const valueKeys = defs.filter((d) => !d.is_label).map((d) => d.key)
      for (const row of payload.sub_table_data[key]) {
        // 行必须是 keyed dict（不是 values 数组），且每个声明列在行上都有键
        expect(Array.isArray((row as Record<string, unknown>).values)).toBe(false)
        for (const vk of valueKeys) {
          expect(Object.prototype.hasOwnProperty.call(row, vk), `${key} 行缺字段 ${vk}`).toBe(true)
        }
      }
    }
  })

  it('soe 每行的字段键覆盖 columns 声明的非标签键', () => {
    const payload = buildH2SyncPayload('soe', populatedSoeSnapshot(), { wpId: 'wp-001' })!
    const columns = buildH2SoeColumns()
    for (const key of tableKeys(payload.sub_table_data)) {
      const valueKeys = columns[key].filter((d) => !d.is_label).map((d) => d.key)
      for (const row of payload.sub_table_data[key]) {
        for (const vk of valueKeys) {
          expect(Object.prototype.hasOwnProperty.call(row, vk), `${key} 行缺字段 ${vk}`).toBe(true)
        }
      }
    }
  })

  it('columns 键集合 === sub_table_data 子表键集合', () => {
    const listed = buildH2SyncPayload('listed', populatedListedSnapshot(), { wpId: 'wp-001' })!
    expect(Object.keys(listed.columns ?? {}).sort()).toEqual(tableKeys(listed.sub_table_data).sort())
    const soe = buildH2SyncPayload('soe', populatedSoeSnapshot(), { wpId: 'wp-001' })!
    expect(Object.keys(soe.columns ?? {}).sort()).toEqual(tableKeys(soe.sub_table_data).sort())
  })

  it('buildH2ListedColumns 6 键 / buildH2SoeColumns 4 键', () => {
    expect(Object.keys(buildH2ListedColumns())).toHaveLength(6)
    expect(Object.keys(buildH2SoeColumns())).toHaveLength(4)
  })
})

// ─── _note_texts ─────────────────────────────────────────────────────────────

describe('_note_texts', () => {
  it('全空文本 → 不产 _note_texts 条目', () => {
    const payload = buildH2SyncPayload('listed', emptyListedSnapshot(), { wpId: 'wp-001' })!
    const texts = payload.sub_table_data._note_texts as unknown as unknown[]
    expect(texts).toHaveLength(0)
  })

  it('非空文本 → 条目含 section/title/text', () => {
    const payload = buildH2SyncPayload('soe', populatedSoeSnapshot(), { wpId: 'wp-001' })!
    const texts = payload.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(texts.length).toBeGreaterThan(0)
    expect(texts[0]).toHaveProperty('section')
    expect(texts[0]).toHaveProperty('title')
    expect(texts[0]).toHaveProperty('text')
  })

  it('_note_texts 只在 sub_table_data 内（后端请求体无顶层字段）', () => {
    const payload = buildH2SyncPayload('listed', populatedListedSnapshot(), { wpId: 'wp-001' })!
    expect((payload as unknown as Record<string, unknown>)._note_texts).toBeUndefined()
    expect(payload.sub_table_data._note_texts).toBeDefined()
  })
})

// ─── 数据流 + 空快照 + 适用性 ────────────────────────────────────────────────

describe('数据流与边界', () => {
  it('工程物资段（listed 项  目）落 materials 表并带合计', () => {
    const snapshot = populatedListedSnapshot()
    snapshot.materials[0].endBalance = 100000
    snapshot.materials[0].priorBalance = 80000
    const payload = buildH2SyncPayload('listed', snapshot, { wpId: 'wp-001' })!
    const rows = payload.sub_table_data[H2_LISTED_SUBTABLE.materials]
    expect(rows[0].label).toBe(snapshot.materials[0].label)
    expect(rows[0].end_balance).toBe(100000)
    expect(rows[0].prior_balance).toBe(80000)
    expect(rows.find((r) => r.is_total)).toBeTruthy()
  })

  it('减值段落 listed 减值准备表（期末 = 期初 + 计提 − 减少）', () => {
    const payload = buildH2SyncPayload('listed', populatedListedSnapshot(), { wpId: 'wp-001' })!
    const rows = payload.sub_table_data[H2_LISTED_SUBTABLE.impairment]
    const row = rows.find((r) => r.label === '厂房工程')!
    expect(row.begin_balance).toBe(30000)
    expect(row.provision).toBe(20000)
    expect(row.decrease).toBe(0)
    expect(row.end_balance).toBe(50000)
  })

  it('soe 减值表按 provision_amount / reason 映射', () => {
    const payload = buildH2SyncPayload('soe', populatedSoeSnapshot(), { wpId: 'wp-001' })!
    const row = payload.sub_table_data[H2_SOE_SUBTABLE.impairment].find((r) => r.label === '码头')!
    expect(row.provision_amount).toBe(5000)
    expect(row.reason).toBe('停工')
  })

  it('空快照 → 各子表仍存在且为数组（不产 null/undefined）', () => {
    for (const [variant, snapshot] of [
      ['listed', emptyListedSnapshot()],
      ['soe', emptySoeSnapshot()],
    ] as const) {
      const payload = buildH2SyncPayload(variant, snapshot, { wpId: 'wp-001' })!
      for (const key of tableKeys(payload.sub_table_data)) {
        expect(Array.isArray(payload.sub_table_data[key])).toBe(true)
      }
    }
  })

  it('适用准则冲突 → 返回 null（per-variant builder 返回空数组）', () => {
    expect(buildH2SyncPayload('listed', emptyListedSnapshot(), { wpId: 'w', applicableStandards: ['soe_standalone'] })).toBeNull()
    expect(buildH2SyncPayload('soe', emptySoeSnapshot(), { wpId: 'w', applicableStandards: ['listed_standalone'] })).toBeNull()
    expect(buildH2ListedSyncPayloads('w', ['soe_standalone'], emptyListedSnapshot())).toHaveLength(0)
    expect(buildH2SoeSyncPayloads('w', ['listed_standalone'], emptySoeSnapshot())).toHaveLength(0)
  })

  it('薄封装与 per-variant builder 结果一致（单一真源）', () => {
    const snapshot = populatedListedSnapshot()
    const viaWrapper = buildH2SyncPayload('listed', snapshot, { wpId: 'wp-001' })
    const viaBuilder = buildH2ListedSyncPayloads('wp-001', [], snapshot)[0]
    expect(viaWrapper).toEqual(viaBuilder)
  })
})
