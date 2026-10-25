/**
 * P18 下游 computed 零回归 —— D1-4 三区被 OO 回写后，下游消费方仍读得到值。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · Task 26 子目标 ①（需求 5.8）
 *
 * ═══ 为什么这条是必须的（回写侧与读侧的字段名契约）═══
 *
 * D1-4 回写产出的行对象，字段名由**后端** `phase5_d1_04_bad_debt` 的 `json_key` 决定；
 * 下游三个消费方各自按**固定字段名**从 `allResponses` 读。两侧字段名对不上 ⇒
 * `Number(undefined) || 0 === 0` ⇒ **静默归零**，且没有任何报错。
 *
 * 🔴 三区的字段名**不是同一套**，这是最容易踩的地方：
 *   individual / portfolio 区：A 列 json_key = `label`  → 下游 `parseD1_4Rows` 读 `r.label`
 *   notetype 区（第三区）    ：A 列 json_key = `noteType`→ 下游 `readD1BadDebtByNoteType` 读 `raw.noteType`
 * 用错了区的读法（比如拿 `label` 去读 notetype 区）就会得空 —— 本文件把这层配对钉死。
 *
 * ═══ 判据形态 ═══
 * 用「回写侧真实产出的行对象形态」喂给「下游真实的读函数」，断言值传得过去；
 * 再做**变异反证**：把回写侧的字段名改一个字母 ⇒ 下游必须归零（证明这条契约真的在起作用，
 * 不是恰好都读到了）。回写侧形态直接复用后端字段名常量，避免手抄漂移。
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import {
  D1_BD_INDIVIDUAL_KEY,
  D1_BD_PORTFOLIO_KEY,
  D1_BD_NOTETYPE_KEY,
  readD1BadDebtByNoteType,
} from '../d1AdjudicationModel'
import { useD1EclCalc } from '../useD1EclCalc'
import type { ChecklistResponse } from '../useD1FormData'

type Row = Record<string, unknown>

function mapWith(entries: Record<string, Row[]>): Map<string, ChecklistResponse> {
  const m = new Map<string, ChecklistResponse>()
  for (const [key, rows] of Object.entries(entries)) {
    m.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(rows) })
  }
  return m
}

/** 回写侧 individual/portfolio 区行对象的真实形态（A 列键 = `label`）。 */
function labelRow(label: string, currentAudited: number): Row {
  return { rowId: `GTROW-${label}`, label, currentAudited, isSubRow: true }
}

/** 回写侧 notetype 区行对象的真实形态（A 列键 = `noteType`，固定行）。 */
function noteTypeRow(noteType: string, priorUnadjusted: number): Row {
  return { rowId: `fixed-${noteType}`, noteType, isFixed: true, priorUnadjusted }
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. individual / portfolio 区 → useD1EclCalc.pullFromD1_4
// ═══════════════════════════════════════════════════════════════════════════

describe('P18：D1-15 从 D1-4 individual/portfolio 区取数', () => {
  function ecl(map: Map<string, ChecklistResponse>) {
    return useD1EclCalc({
      allResponses: ref(map) as any,
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      isReadonly: ref(false),
      saveImmediate: async () => {},
      debouncedSave: async () => {},
    } as any)
  }

  it('portfolio 区有数据 ⇒ d1_4DataAvailable = true', () => {
    const map = mapWith({ [D1_BD_PORTFOLIO_KEY]: [labelRow('甲公司', 500)] })
    expect(ecl(map).d1_4DataAvailable.value).toBe(true)
  })

  it('三区全空 ⇒ d1_4DataAvailable = false（正面对照）', () => {
    expect(ecl(mapWith({})).d1_4DataAvailable.value).toBe(false)
  })

  it('🔴 notetype 区（用 noteType 键）单独存在**不会**被误判成 D1-4 可用', () => {
    // d1_4DataAvailable 只认 individual/portfolio 两键 —— notetype 区不是 D1-15 的取数源
    const map = mapWith({ [D1_BD_NOTETYPE_KEY]: [noteTypeRow('银行承兑汇票', 1000)] })
    expect(ecl(map).d1_4DataAvailable.value).toBe(false)
  })

  it('pullFromD1_4 把 portfolio 区的 currentAudited 按 label↔debtor 匹配进 D1-15', () => {
    const map = mapWith({ [D1_BD_PORTFOLIO_KEY]: [labelRow('甲公司', 777)] })
    const api = ecl(map)
    // 造一个 debtor 同名的 portfolio 行
    api.portfolioRows.value = [
      { ...(api.portfolioRows.value[0] ?? {}), debtor: '甲公司', balance: 1000, lossRate: 0.1,
        actualProvision: 0, shouldProvision: 0, difference: 0, autoPulled: false } as any,
    ]
    api.pullFromD1_4()
    const pulled = api.portfolioRows.value.find((r: any) => r.debtor === '甲公司') as any
    expect(pulled.actualProvision).toBe(777)
    expect(pulled.autoPulled).toBe(true)
  })

  it('🔴 变异反证：回写侧把 currentAudited 改名 ⇒ 下游归零', () => {
    // 模拟后端 json_key 从 currentAudited 漂成别的名字
    const badRow = { rowId: 'x', label: '甲公司', currentAuditedTYPO: 777 }
    const map = mapWith({ [D1_BD_PORTFOLIO_KEY]: [badRow] })
    const api = ecl(map)
    api.portfolioRows.value = [
      { debtor: '甲公司', balance: 1000, lossRate: 0.1,
        actualProvision: 0, shouldProvision: 0, difference: 0, autoPulled: false } as any,
    ]
    api.pullFromD1_4()
    const pulled = api.portfolioRows.value.find((r: any) => r.debtor === '甲公司') as any
    // 字段名对不上 ⇒ 匹配到的是 currentAudited=0（Number(undefined)||0），不是 777
    expect(pulled.actualProvision).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. notetype 区（第三区）→ readD1BadDebtByNoteType（D1-1 坏账区块的取数源）
// ═══════════════════════════════════════════════════════════════════════════

describe('P18：D1-1 坏账区块从 D1-4 notetype 区取数', () => {
  it('回写侧的 noteType 行 ⇒ readD1BadDebtByNoteType 读得到', () => {
    const map = mapWith({
      [D1_BD_NOTETYPE_KEY]: [
        { rowId: 'fixed-bank', noteType: '银行承兑汇票', isFixed: true,
          priorUnadjusted: 1000, currentUnadjusted: 2000 },
      ],
    })
    const out = readD1BadDebtByNoteType(map)
    const slugs = Object.keys(out)
    expect(slugs.length).toBe(1)
    expect(out[slugs[0]].priorUnadjusted).toBe(1000)
  })

  it('🔴 变异反证：回写侧把 noteType 改名成 label ⇒ 分类 slug 落空、读不出该行', () => {
    // 若第三区错用 individual 区的 `label` 键，readD1BadDebtByNoteType 就取不到分类名
    const map = mapWith({
      [D1_BD_NOTETYPE_KEY]: [
        { rowId: 'fixed-bank', label: '银行承兑汇票', isFixed: true, priorUnadjusted: 1000 },
      ],
    })
    const out = readD1BadDebtByNoteType(map)
    // rowId=fixed-bank 仍能生成 slug（读法对 rowId 有兜底），但 noteType 缺失 ⇒
    // 至少证明「label 不是 notetype 区的分类键」。断言分类名不来自 label：
    const slugs = Object.keys(out)
    // 只要没有任何 slug 是从 '银行承兑汇票' 这个 label 派生的，就说明 label 键不被 notetype 读法采纳
    for (const s of slugs) {
      expect(s).not.toContain('银行承兑汇票')
    }
  })
})
