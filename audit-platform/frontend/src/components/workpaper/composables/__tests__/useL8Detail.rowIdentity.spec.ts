/**
 * useL8Detail.rowIdentity.spec.ts — L8-2 明细表混合行身份测试（方案 D1）
 *
 * Task: l8-true-bidirectional 第1步 + D1 收尾
 *
 * 方案 D1：13 行骨架行用模板身份 `GTROW-L82-NNNN`（与 OO 侧对齐），其中 3 个派生行
 * （利息费用/利息净支出/汇兑净损失）只读、不进 store；用户 addRow 新增行自铸 `l82det-*`。
 *
 * 覆盖：
 * 1. 骨架行认领稳定模板槽位（GTROW-L82-NNNN，按位置，顺序稳定）
 * 2. 用户新增行自铸 l82det 唯一身份
 * 3. 删中间用户行其余不变、骨架行身份不随增删漂移
 * 4. 派生行不进 store 载荷（rowsForStore 过滤）
 * 5. restore 从 store（10 输入行）复原完整 13 行 + 用户行、派生行占位、历史自铸按位置认领
 * 6. 派生行月度格 updateMonthly 兜底不接受编辑
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// addRow 走 ElMessageBox.prompt：mock 成直接返回项目名称
const promptMock = vi.fn().mockResolvedValue({ value: '测试项目' })
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: (...args: any[]) => promptMock(...args) },
}))

import {
  useL8Detail,
  L8_DETAIL_DEFAULT_ITEMS,
  createL8DefaultRows,
  restoreL8RowsForDisplay,
  type L8DetailRow,
} from '../useL8Detail'
import { newRowIdentity } from '../shared/rowIdentity'
import {
  L82_SKELETON_ITEMS,
  l82TemplateRowId,
  isL82TemplateRowId,
  isL82DerivedRowKey,
  rowsForStore,
} from '../../l8/core/l8DetailRowIdentity'

// ─── formData stub（useL8Detail 只用 debouncedSave） ──────────────────────────

function makeFormDataStub() {
  const calls: Array<{ key: string; payload: any }> = []
  return {
    stub: {
      debouncedSave: vi.fn((key: string, payload: any) => { calls.push({ key, payload }) }),
    } as any,
    calls,
  }
}

function emptyRow(key: string, itemName = ''): L8DetailRow {
  return {
    key,
    itemName,
    monthly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    periodUnadjusted: 0,
    aje: 0,
    rje: 0,
    periodAudited: 0,
    ratio: 0,
    crossRef: '',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
  }
}

describe('L8-2 明细表混合行身份（方案 D1）', () => {
  beforeEach(() => {
    promptMock.mockClear()
  })

  it('13 行骨架：默认项补齐汇兑净损失，模板身份按位置稳定对齐', () => {
    expect(L8_DETAIL_DEFAULT_ITEMS).toHaveLength(13)
    expect(L82_SKELETON_ITEMS).toContain('汇兑净损失')
    const rows = createL8DefaultRows()
    expect(rows).toHaveLength(13)
    rows.forEach((r, i) => {
      expect(r.key).toBe(l82TemplateRowId(i))
      expect(isL82TemplateRowId(r.key)).toBe(true)
    })
    // R9=GTROW-L82-0009 … R21=GTROW-L82-0021
    expect(rows[0].key).toBe('GTROW-L82-0009')
    expect(rows[12].key).toBe('GTROW-L82-0021')
    // 身份唯一
    expect(new Set(rows.map(r => r.key)).size).toBe(13)
  })

  it('3 个派生行用模板身份且判为派生（利息费用 idx2 / 利息净支出 idx4 / 汇兑净损失 idx11）', () => {
    expect(isL82DerivedRowKey(l82TemplateRowId(2))).toBe(true)
    expect(isL82DerivedRowKey(l82TemplateRowId(4))).toBe(true)
    expect(isL82DerivedRowKey(l82TemplateRowId(11))).toBe(true)
    // 输入骨架行不是派生行
    expect(isL82DerivedRowKey(l82TemplateRowId(0))).toBe(false)
    // 用户自铸行不是派生行
    expect(isL82DerivedRowKey('l82det-abc')).toBe(false)
  })

  it('newRowIdentity(l82det) 生成 l82det 前缀且连续生成互不相同', () => {
    const ids = new Set<string>()
    for (let i = 0; i < 50; i++) {
      const id = newRowIdentity('l82det')
      expect(id.startsWith('l82det-')).toBe(true)
      ids.add(id)
    }
    expect(ids.size).toBe(50)
  })

  it('用户新增行自铸 l82det 唯一身份（非模板身份、非随机旧前缀）', async () => {
    const detailRows = ref<L8DetailRow[]>([])
    const { addRow } = useL8Detail(makeFormDataStub().stub, detailRows)

    await addRow()
    await addRow()

    expect(detailRows.value).toHaveLength(2)
    const [r1, r2] = detailRows.value
    expect(r1.key).not.toBe(r2.key)
    expect(r1.key.startsWith('l82det-')).toBe(true)
    expect(r2.key.startsWith('l82det-')).toBe(true)
    expect(isL82TemplateRowId(r1.key)).toBe(false)
    expect(r1.key.startsWith('l8-detail-')).toBe(false)
  })

  it('删中间用户行其余不变；骨架行身份不随增删漂移', () => {
    const detailRows = ref<L8DetailRow[]>([
      ...createL8DefaultRows(), // 13 骨架
      emptyRow('l82det-aaa', '甲'),
      emptyRow('l82det-bbb', '乙'),
      emptyRow('l82det-ccc', '丙'),
    ])
    const { removeRow } = useL8Detail(makeFormDataStub().stub, detailRows)
    const skeletonKeysBefore = detailRows.value.slice(0, 13).map(r => r.key)

    removeRow(14) // 删中间用户行（乙，下标 13+1）

    expect(detailRows.value).toHaveLength(15)
    // 骨架 13 行身份原封不动
    expect(detailRows.value.slice(0, 13).map(r => r.key)).toEqual(skeletonKeysBefore)
    // 用户行甲/丙保留
    expect(detailRows.value[13].key).toBe('l82det-aaa')
    expect(detailRows.value[14].key).toBe('l82det-ccc')
  })

  it('派生行不进 store 载荷（rowsForStore 剔除 3 派生行，保留 10 输入 + 用户行）', () => {
    const rows = [
      ...createL8DefaultRows(),       // 13 骨架（含 3 派生）
      emptyRow('l82det-user1', '用户项目'),
    ]
    const stored = rowsForStore(rows)
    expect(stored).toHaveLength(11) // 10 输入 + 1 用户
    // 派生行 key 全部被剔除
    for (const r of stored) expect(isL82DerivedRowKey(r.key)).toBe(false)
    // 用户行保留
    expect(stored.some(r => r.key === 'l82det-user1')).toBe(true)
    // 输入骨架行保留（R9/R21 在、派生 R11/R13/R20 不在）
    const keys = new Set(stored.map(r => r.key))
    expect(keys.has('GTROW-L82-0009')).toBe(true)
    expect(keys.has('GTROW-L82-0021')).toBe(true)
    expect(keys.has(l82TemplateRowId(2))).toBe(false)  // 利息费用
    expect(keys.has(l82TemplateRowId(4))).toBe(false)  // 利息净支出
    expect(keys.has(l82TemplateRowId(11))).toBe(false) // 汇兑净损失
  })

  it('_triggerSave 写 L8-2-full-data 时派生行已被剔除', () => {
    const { stub, calls } = makeFormDataStub()
    const detailRows = ref<L8DetailRow[]>(createL8DefaultRows())
    const { updateRow } = useL8Detail(stub, detailRows)
    updateRow(0, 'aje', 1000) // 触发保存
    const fullData = calls.filter(c => c.key === 'L8-2-full-data').at(-1)
    expect(fullData).toBeTruthy()
    const saved = JSON.parse(fullData!.payload.remark) as L8DetailRow[]
    expect(saved).toHaveLength(10) // 只有 10 输入行
    for (const r of saved) expect(isL82DerivedRowKey(r.key)).toBe(false)
  })

  it('restore 从 store（10 输入行）复原完整 13 行 + 派生占位 + 用户行', () => {
    // 模拟 store 载荷：10 输入行（带数据）+ 1 用户行
    const inputRows = createL8DefaultRows().filter(r => !isL82DerivedRowKey(r.key))
    inputRows[0].monthly[0] = 1000 // R9 填了 1 月
    const stored = [...inputRows, emptyRow('l82det-user1', '用户手续费')]

    const restored = restoreL8RowsForDisplay(stored)
    // 13 骨架 + 1 用户 = 14
    expect(restored).toHaveLength(14)
    // 骨架按顺序、派生行占位回来了
    restored.slice(0, 13).forEach((r, i) => expect(r.key).toBe(l82TemplateRowId(i)))
    // R9 的数据保留
    expect(restored[0].monthly[0]).toBe(1000)
    // 派生行占位存在
    expect(restored.some(r => r.key === l82TemplateRowId(2))).toBe(true)
    // 用户行在末尾
    expect(restored[13].key).toBe('l82det-user1')
    expect(restored[13].itemName).toBe('用户手续费')
  })

  it('restore 兼容历史自铸身份：按位置认领输入槽位（跳过派生槽位）', () => {
    // 旧载荷：10 行随机自铸身份（无 GTROW），模拟历史用户数据
    const legacy = Array.from({ length: 10 }, (_, i) =>
      emptyRow(`l8-detail-old-${i}`, `历史项目${i}`))
    legacy[0].monthly[5] = 500

    const restored = restoreL8RowsForDisplay(legacy)
    // 复原成 13 行骨架（无额外用户行，因为 10 行恰好认领 10 个输入槽位）
    expect(restored).toHaveLength(13)
    restored.forEach((r, i) => expect(r.key).toBe(l82TemplateRowId(i)))
    // 第一个输入槽位（R9=idx0）认领了 legacy[0] 的数据
    expect(restored[0].monthly[5]).toBe(500)
  })

  it('computedRows 把派生行月度算成上方科目跨行减法（只读显示）', () => {
    const rows = createL8DefaultRows()
    // R9 利息费用总额 1 月 = 1000；R10 减利息资本化 1 月 = 300
    rows[0].monthly[0] = 1000
    rows[1].monthly[0] = 300
    const detailRows = ref<L8DetailRow[]>(rows)
    const { computedRows } = useL8Detail(makeFormDataStub().stub, detailRows)
    // R11 利息费用（idx2）= R9 - R10 = 700
    const r11 = computedRows.value[2]
    expect(isL82DerivedRowKey(r11.key)).toBe(true)
    expect(r11.monthly[0]).toBe(700)
  })

  it('派生行月度格 updateMonthly 兜底不接受编辑', () => {
    const detailRows = ref<L8DetailRow[]>(createL8DefaultRows())
    const { updateMonthly } = useL8Detail(makeFormDataStub().stub, detailRows)
    // idx2 = 利息费用（派生）
    updateMonthly(2, 0, 9999)
    expect(detailRows.value[2].monthly[0]).toBe(0) // 未被写入
    // idx0 = 利息费用总额（输入行）可写
    updateMonthly(0, 0, 1234)
    expect(detailRows.value[0].monthly[0]).toBe(1234)
  })
})
