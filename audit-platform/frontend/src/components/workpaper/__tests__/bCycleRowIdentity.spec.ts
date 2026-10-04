/**
 * B 循环行身份守卫 — B22B / B22C / B50 三条 entry 的 BC-53 / BC-48 改造。
 *
 * spec: b-class-shared-base-carrier-lanes（BC-53 / BC-48 / BC-56）
 *
 * 🔴 三条 entry 的缺陷形态各不相同，判据也不同：
 *   - B22B：落库键含数组下标（`B22B-row-{n}-{field}`，0-based）→ 改行数组
 *   - B22C：落库键含序号（`B22C-{block}-def-{n}-{field}`，1-based）→ 加 rowid 同组落库
 *   - B50 ：身份即科目名（label-as-key）→ 本轮只修渲染 key，存储层登记为欠账
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...a: any[]) => mockGet(...a),
    put: (...a: any[]) => mockPut(...a),
  },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockGet.mockResolvedValue([])
  mockPut.mockResolvedValue({})
})

// ═══════════════════════════════════════════════════════════════════════════
// B22B — 落库形态从「下标展开」改为「行数组」
// ═══════════════════════════════════════════════════════════════════════════

describe('B22B 控制矩阵：行身份非位置化（BC-53）', () => {
  it('新行自带稳定 rowId，两行不撞', async () => {
    const { useB22BControlMatrix } = await import('../composables/useB22BControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      m.addRow()
      m.addRow()
      const ids = m.rows.value.map((r: any) => r.rowId)
      expect(ids[0]).toBeTruthy()
      expect(ids[0]).not.toBe(ids[1])
    })
    scope.stop()
  })

  it('落库只写一条行数组 + count 校验值（不再 12×N 条单字段键）', async () => {
    const { useB22BControlMatrix } = await import('../composables/useB22BControlMatrix')
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      m.addRow({ controlName: '甲' })
      await flushPromises()

      const payload = mockPut.mock.calls[mockPut.mock.calls.length - 1][1]
      const ids = payload.items.map((i: any) => i.item_id)
      expect(ids).toContain('B22B-rows')
      // 改造前一行会产生 12 条 `B22B-row-0-*`，现在 0 条
      expect(ids.filter((i: string) => /^B22B-row-\d+-/.test(i))).toHaveLength(0)
    })
    scope.stop()
  })

  it('🔴 删中间行：身份与内容保持绑定（shift 搬迁下必红）', async () => {
    const { useB22BControlMatrix } = await import('../composables/useB22BControlMatrix')
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      m.addRow({ controlName: '甲' })
      m.addRow({ controlName: '乙' })
      m.addRow({ controlName: '丙' })
      const before = m.rows.value.map((r: any) => r.rowId)

      m.removeRow(1)
      await flushPromises()

      expect(m.rows.value.map((r: any) => r.rowId)).toEqual([before[0], before[2]])
      expect(m.rows.value.map((r: any) => r.controlName)).toEqual(['甲', '丙'])
    })
    scope.stop()
  })

  it('legacy 下标数据自动迁移：值不变 + 身份确定性（多会话一致）', async () => {
    mockGet.mockResolvedValue([
      { item_id: 'B22B-row-count', remark: '2' },
      { item_id: 'B22B-row-0-controlName', remark: '甲' },
      { item_id: 'B22B-row-1-controlName', remark: '乙' },
    ])
    const { useB22BControlMatrix } = await import('../composables/useB22BControlMatrix')
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      await m.loadAll()

      expect(m.rows.value).toHaveLength(2)
      expect(m.rows.value.map((r: any) => r.controlName)).toEqual(['甲', '乙'])
      // 🔴 确定性身份：含原下标，两次迁移产出一致（随机铸造会产生两套身份）
      expect(m.rows.value[0].rowId).toBe('B22B-row-legacy-0')
      expect(m.rows.value[1].rowId).toBe('B22B-row-legacy-1')
    })
    scope.stop()
  })

  it('已迁移项目不重复迁移（读到行数组就直接用）', async () => {
    mockGet.mockResolvedValue([
      {
        item_id: 'B22B-rows',
        remark: JSON.stringify([{ rowId: 'KEEP-1', controlName: '甲' }]),
      },
      // 同时存在 legacy 键：不应被使用
      { item_id: 'B22B-row-count', remark: '5' },
      { item_id: 'B22B-row-0-controlName', remark: '不该出现' },
    ])
    const { useB22BControlMatrix } = await import('../composables/useB22BControlMatrix')
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      await m.loadAll()

      expect(m.rows.value).toHaveLength(1)
      expect(m.rows.value[0].rowId).toBe('KEEP-1')
      expect(m.rows.value[0].controlName).toBe('甲')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B22C — 序号键旁挂 rowid（1-based，与 B22B 的 0-based 不同基准 BC-56）
// ═══════════════════════════════════════════════════════════════════════════

describe('B22C 设计有效性：缺陷条目行身份（BC-53 / BC-56）', () => {
  it('新增缺陷自带稳定 rowId', async () => {
    const { useB22CDesignEffectiveness, BLOCK_KEYS } = await import(
      '../composables/useB22CDesignEffectiveness'
    )
    const scope = effectScope()
    scope.run(() => {
      const m = useB22CDesignEffectiveness(ref('wp-1'), ref('proj-1'))
      const block = BLOCK_KEYS[0]
      m.addDeficiency(block)
      m.addDeficiency(block)
      // blocks 是 BlockData[] 数组（按 BLOCK_KEYS 顺序），不是按 key 索引的对象
      const defs = m.blocks.value.find((b: any) => b.key === block)!.deficiencies
      expect(defs[0].rowId).toBeTruthy()
      expect(defs[0].rowId).not.toBe(defs[1].rowId)
    })
    scope.stop()
  })

  it('🔴 删中间条目：身份与描述保持绑定', async () => {
    const { useB22CDesignEffectiveness, BLOCK_KEYS } = await import(
      '../composables/useB22CDesignEffectiveness'
    )
    const scope = effectScope()
    scope.run(() => {
      const m = useB22CDesignEffectiveness(ref('wp-1'), ref('proj-1'))
      const block = BLOCK_KEYS[0]
      m.addDeficiency(block)
      m.addDeficiency(block)
      m.addDeficiency(block)
      const defs = () =>
        m.blocks.value.find((b: any) => b.key === block)!.deficiencies
      m.setDeficiencyField(block, 0, 'desc' as any, '甲')
      m.setDeficiencyField(block, 1, 'desc' as any, '乙')
      m.setDeficiencyField(block, 2, 'desc' as any, '丙')
      const before = defs().map((d: any) => d.rowId)

      m.removeDeficiency(block, 1)

      expect(defs()).toHaveLength(2)
      expect(defs().map((d: any) => d.rowId)).toEqual([before[0], before[2]])
      expect(defs().map((d: any) => d.desc)).toEqual(['甲', '丙'])
    })
    scope.stop()
  })

  it('身份随业务字段同组落库（-rowid 键）', async () => {
    const { useB22CDesignEffectiveness, BLOCK_KEYS } = await import(
      '../composables/useB22CDesignEffectiveness'
    )
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22CDesignEffectiveness(ref('wp-1'), ref('proj-1'))
      const block = BLOCK_KEYS[0]
      m.addDeficiency(block)
      await flushPromises()

      const payload = mockPut.mock.calls[mockPut.mock.calls.length - 1][1]
      const ids: string[] = payload.items.map((i: any) => i.item_id)
      // 1-based 序号（与 B22B 的 0-based 并存，迁移禁统一假设 BC-56）
      expect(ids.some((i) => /-def-1-rowid$/.test(i))).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B50 — label-as-key 渲染侧修复（存储层欠账已登记）
// ═══════════════════════════════════════════════════════════════════════════

describe('B50 风险矩阵：渲染身份非 label（BC-48）', () => {
  it('每个科目行有唯一 rowKey', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = ref({ items: new Map() }) as any
      const save = vi.fn()
      const m = useB50RiskMatrix(tab3, save)
      m.addAccount('应收账款')
      m.addAccount('存货')

      const keys = m.accounts.value.map((r: any) => r.rowKey)
      expect(keys[0]).toBeTruthy()
      expect(keys[0]).not.toBe(keys[1])
    })
    scope.stop()
  })

  it('🔴 同名科目 rowKey 仍不撞（用 row.name 作 key 会撞）', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')
    const scope = effectScope()
    scope.run(() => {
      const tab3 = ref({ items: new Map() }) as any
      const m = useB50RiskMatrix(tab3, vi.fn())
      m.addAccount('其他应收款')
      m.addAccount('其他应收款')

      const rows = m.accounts.value
      // 🔴 全部 rowKey 互不相同（含预置行）；用 row.name 作 key 时同名行会撞
      const keys = rows.map((r: any) => r.rowKey)
      expect(new Set(keys).size).toBe(keys.length)

      // 若实现允许同名入库，则至少存在一对同名而 rowKey 不同的行
      const sameName = rows.filter((r: any) => r.name === '其他应收款')
      if (sameName.length >= 2) {
        expect(sameName[0].rowKey).not.toBe(sameName[1].rowKey)
      }
    })
    scope.stop()
  })

  it('宿主模板不再用 row.name 作渲染 key', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const host = path.resolve(
      __dirname, '..', 'GtB50RiskAssessment.vue',
    )
    const text = fs.readFileSync(host, 'utf-8')
    // 数据行的三处 :key 已改绑 rowKey
    expect(text).not.toContain(':key="row.name"')
    expect(text).not.toContain(':key="`${row.name}-${a}`"')
    expect(text).toContain('row.rowKey')
  })
})
