/**
 * D1 四表库 Seed 消费优先级测试
 *
 * Spec: .kiro/specs/d1-four-table-extraction-formula-wiring/
 * Task: 2.3
 *
 * 验证后端 seed（responses_snapshot 中注入的 D1-cat-rows / D1-bd-portfolio-rows）
 * 被前端 composable 正确消费：
 * - Property 2: 手工优先 —— 有持久化数据时 seed 不出现（由后端保证），
 *   但前端要能正确加载任意合法 JSON（无论来源是 seed 还是手动编辑）
 * - Seed 数据格式 = composable 持久化格式（同一 JSON schema），
 *   加载路径无分支 → 无需前端做 "优先级" 判定
 *
 * 测试策略：直接给 allResponses 注入 seed 形式的数据，验证 composable 加载正确；
 * 再验证有数据时外部注入空 seed 不覆盖（watch 路径的幂等性）。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useD1DetailCategory } from '../useD1DetailCategory'
import { useD1BadDebt } from '../useD1BadDebt'
import type { ChecklistResponse } from '../useD1FormData'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeAllResponses(entries: Record<string, string | null> = {}) {
  const map = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    map.set(k, { item_id: k, remark: v, conclusion: null } as ChecklistResponse)
  }
  return ref(map)
}

const noopSave = vi.fn(async () => {})

// ─── D1-cat-rows seed 消费 ──────────────────────────────────────────────────

describe('useD1DetailCategory — seed 消费', () => {
  it('seed 注入的 D1-cat-rows 被正确加载（银行承兑+商业承兑+动态行）', () => {
    // 模拟后端 seed_d1_detail_rows 产出的 responses_snapshot
    const seedRows = [
      {
        rowId: 'fixed-bank',
        category: '银行承兑汇票',
        isFixed: true,
        priorUnadjusted: 5000000,
        priorAje: 0,
        priorRje: 0,
        currentIncrease: 12460611.29,
        currentDecrease: 8000000,
        currentAje: 0,
        currentRje: 0,
      },
      {
        rowId: 'fixed-commercial',
        category: '商业承兑汇票',
        isFixed: true,
        priorUnadjusted: 3000000,
        priorAje: 0,
        priorRje: 0,
        currentIncrease: 7748586.89,
        currentDecrease: 2000000,
        currentAje: 0,
        currentRje: 0,
      },
      {
        rowId: 'dynamic-credit-letter',
        category: '信用证',
        isFixed: false,
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        currentIncrease: 0,
        currentDecrease: 0,
        currentAje: 0,
        currentRje: 0,
      },
    ]

    const allResponses = makeAllResponses({
      'D1-cat-rows': JSON.stringify(seedRows),
    })

    const { rows, subtotalRow } = useD1DetailCategory({
      allResponses,
      wpId: ref('test-wp'),
      projectId: ref('test-proj'),
      saveImmediate: noopSave,
      isReadonly: ref(false),
    })

    // 3 行被正确加载
    expect(rows.value).toHaveLength(3)
    expect(rows.value[0].category).toBe('银行承兑汇票')
    expect(rows.value[0].currentIncrease).toBe(12460611.29)
    expect(rows.value[1].category).toBe('商业承兑汇票')
    expect(rows.value[1].currentIncrease).toBe(7748586.89)
    expect(rows.value[2].category).toBe('信用证')
    expect(rows.value[2].isFixed).toBe(false)

    // 公式字段自动计算：priorAudited = prior + aje + rje
    expect(rows.value[0].priorAudited).toBe(5000000)
    // currentUnadjusted = priorAudited + increase - decrease
    expect(rows.value[0].currentUnadjusted).toBeCloseTo(5000000 + 12460611.29 - 8000000, 2)

    // 小计行 = 各行之和
    expect(subtotalRow.value.currentIncrease).toBeCloseTo(12460611.29 + 7748586.89 + 0, 2)
  })

  it('无 seed 且无持久化数据时回退默认固定行（银行+商业，全零）', () => {
    const allResponses = makeAllResponses({})

    const { rows } = useD1DetailCategory({
      allResponses,
      wpId: ref('test-wp'),
      projectId: ref('test-proj'),
      saveImmediate: noopSave,
      isReadonly: ref(false),
    })

    expect(rows.value).toHaveLength(2)
    expect(rows.value[0].rowId).toBe('fixed-bank')
    expect(rows.value[0].currentIncrease).toBe(0)
    expect(rows.value[1].rowId).toBe('fixed-commercial')
    expect(rows.value[1].currentIncrease).toBe(0)
  })

  it('持久化数据存在时 composable 加载持久化内容（seed 不出现由后端保证）', () => {
    // 用户手工编辑过的数据（比 seed 多了 AJE 调整）
    const userEditedRows = [
      {
        rowId: 'fixed-bank',
        category: '银行承兑汇票',
        isFixed: true,
        priorUnadjusted: 5000000,
        priorAje: 100000, // 用户手工调整
        priorRje: 0,
        currentIncrease: 12460611.29,
        currentDecrease: 8000000,
        currentAje: -50000, // 用户手工调整
        currentRje: 0,
      },
      {
        rowId: 'fixed-commercial',
        category: '商业承兑汇票',
        isFixed: true,
        priorUnadjusted: 3000000,
        priorAje: 0,
        priorRje: 0,
        currentIncrease: 7748586.89,
        currentDecrease: 2000000,
        currentAje: 0,
        currentRje: 0,
      },
    ]

    const allResponses = makeAllResponses({
      'D1-cat-rows': JSON.stringify(userEditedRows),
    })

    const { rows } = useD1DetailCategory({
      allResponses,
      wpId: ref('test-wp'),
      projectId: ref('test-proj'),
      saveImmediate: noopSave,
      isReadonly: ref(false),
    })

    // 加载的是用户编辑过的数据（含 AJE 调整值）
    expect(rows.value[0].priorAje).toBe(100000)
    expect(rows.value[0].currentAje).toBe(-50000)
    // priorAudited 含 AJE
    expect(rows.value[0].priorAudited).toBe(5000000 + 100000)
  })

  it('watch 路径：外部 allResponses 更新后重新加载（模拟 selfLoad 覆写）', async () => {
    const allResponses = makeAllResponses({})

    const { rows } = useD1DetailCategory({
      allResponses,
      wpId: ref('test-wp'),
      projectId: ref('test-proj'),
      saveImmediate: noopSave,
      isReadonly: ref(false),
    })

    // 初始：默认空行
    expect(rows.value).toHaveLength(2)
    expect(rows.value[0].currentIncrease).toBe(0)

    // 模拟 selfLoad 注入 seed 到 allResponses（GtD1NotesReceivable.selfLoad 的行为）
    const seedRows = [
      {
        rowId: 'fixed-bank',
        category: '银行承兑汇票',
        isFixed: true,
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        currentIncrease: 9999999,
        currentDecrease: 0,
        currentAje: 0,
        currentRje: 0,
      },
      {
        rowId: 'fixed-commercial',
        category: '商业承兑汇票',
        isFixed: true,
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        currentIncrease: 1111111,
        currentDecrease: 0,
        currentAje: 0,
        currentRje: 0,
      },
    ]
    const newMap = new Map(allResponses.value)
    newMap.set('D1-cat-rows', { item_id: 'D1-cat-rows', remark: JSON.stringify(seedRows), conclusion: null } as ChecklistResponse)
    allResponses.value = newMap

    await nextTick()

    // watch 触发后重新加载
    expect(rows.value[0].currentIncrease).toBe(9999999)
    expect(rows.value[1].currentIncrease).toBe(1111111)
  })
})

// ─── D1-bd-portfolio-rows seed 消费 ─────────────────────────────────────────

describe('useD1BadDebt — seed 消费', () => {
  it('seed 注入的 D1-bd-portfolio-rows 被正确加载（含转回金额）', () => {
    const seedPortfolioRows = [
      {
        rowId: 'fixed-portfolio',
        category: 'portfolio',
        label: '按组合计提',
        isSubRow: false,
        priorUnadjusted: 3037132.25,
        priorAje: 0,
        priorRje: 0,
        currentProvision: 0,
        currentRecovery: 0,
        currentReversal: 1874844.22, // 转回
        currentWriteOff: 0,
        currentOther: 0,
        currentAje: 0,
        currentRje: 0,
      },
    ]

    const allResponses = makeAllResponses({
      'D1-bd-portfolio-rows': JSON.stringify(seedPortfolioRows),
    })

    const { portfolioRows, subtotalRow } = useD1BadDebt({
      allResponses,
      wpId: ref('test-wp'),
      projectId: ref('test-proj'),
      saveImmediate: noopSave,
      isReadonly: ref(false),
      eclTestTotal: ref(0),
    })

    expect(portfolioRows.value).toHaveLength(1)
    expect(portfolioRows.value[0].priorUnadjusted).toBe(3037132.25)
    expect(portfolioRows.value[0].currentReversal).toBe(1874844.22)
    // currentUnadjusted = priorAudited + provision + recovery - reversal - writeOff + other
    // priorAudited = 3037132.25 + 0 + 0 = 3037132.25
    // currentUnadjusted = 3037132.25 + 0 + 0 - 1874844.22 - 0 + 0 = 1162288.03
    expect(portfolioRows.value[0].currentUnadjusted).toBeCloseTo(1162288.03, 2)
  })

  it('无 seed 无持久化时使用默认空行', () => {
    const allResponses = makeAllResponses({})

    const { individualRows, portfolioRows } = useD1BadDebt({
      allResponses,
      wpId: ref('test-wp'),
      projectId: ref('test-proj'),
      saveImmediate: noopSave,
      isReadonly: ref(false),
      eclTestTotal: ref(0),
    })

    expect(individualRows.value).toHaveLength(1)
    expect(individualRows.value[0].rowId).toBe('fixed-individual')
    expect(individualRows.value[0].priorUnadjusted).toBe(0)

    expect(portfolioRows.value).toHaveLength(1)
    expect(portfolioRows.value[0].rowId).toBe('fixed-portfolio')
    expect(portfolioRows.value[0].priorUnadjusted).toBe(0)
  })

  it('持久化数据存在时加载持久化内容', () => {
    const userRows = [
      {
        rowId: 'fixed-portfolio',
        category: 'portfolio',
        label: '按组合计提',
        isSubRow: false,
        priorUnadjusted: 5000000,
        priorAje: 200000, // 用户手工调整
        priorRje: 0,
        currentProvision: 100000,
        currentRecovery: 0,
        currentReversal: 0,
        currentWriteOff: 0,
        currentOther: 0,
        currentAje: 0,
        currentRje: 0,
      },
    ]

    const allResponses = makeAllResponses({
      'D1-bd-portfolio-rows': JSON.stringify(userRows),
    })

    const { portfolioRows } = useD1BadDebt({
      allResponses,
      wpId: ref('test-wp'),
      projectId: ref('test-proj'),
      saveImmediate: noopSave,
      isReadonly: ref(false),
      eclTestTotal: ref(0),
    })

    expect(portfolioRows.value[0].priorAje).toBe(200000)
    expect(portfolioRows.value[0].currentProvision).toBe(100000)
    // priorAudited = 5000000 + 200000 = 5200000
    expect(portfolioRows.value[0].priorAudited).toBe(5200000)
  })
})
