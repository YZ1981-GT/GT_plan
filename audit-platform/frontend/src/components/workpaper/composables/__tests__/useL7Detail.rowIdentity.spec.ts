/**
 * useL7Detail.rowIdentity.spec.ts — L7-2 明细表稳定行身份测试
 *
 * Task: l7-true-bidirectional 第1步
 *
 * 验证 L7-2 明细表行身份从随机运行时 ID 换成稳定 rowId（`newRowIdentity('l72det')`）后：
 * 1. 新增两行 rowId 唯一（铸号器不撞）
 * 2. 删中间行其余行 rowId 不变（位置化缺陷反例 —— 若身份绑位置则删行后下游行身份会漂移）
 * 3. 缺 rowId 的旧数据 hydrate 时补铸（兼容旧 full-data 的 key 字段，已有 rowId 优先不重铸）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// addRow 走 ElMessageBox.prompt：mock 成直接返回项目名称
const promptMock = vi.fn().mockResolvedValue({ value: '测试项目' })
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: (...args: any[]) => promptMock(...args) },
}))

import { useL7Detail, type L7DetailRow } from '../useL7Detail'
import { newRowIdentity } from '../shared/rowIdentity'

// ─── formData stub（useL7Detail 只用 debouncedSave） ──────────────────────────

function makeFormDataStub() {
  return {
    debouncedSave: vi.fn(),
  } as any
}

function emptyRow(rowId: string, itemName = ''): L7DetailRow {
  return {
    rowId,
    itemName,
    beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0,
    ajeIncrease: 0, rjeIncrease: 0,
    endAjeIncrease: 0, endRjeDecrease: 0, endAjeDecrease: 0, endRjeIncrease: 0,
    endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0,
    nature: '', reason: '', maturityInfo: '',
  }
}

describe('L7-2 明细表稳定行身份', () => {
  beforeEach(() => {
    promptMock.mockClear()
  })

  it('newRowIdentity(l72det) 生成 l72det 前缀且连续生成互不相同', () => {
    const ids = new Set<string>()
    for (let i = 0; i < 50; i++) {
      const id = newRowIdentity('l72det')
      expect(id.startsWith('l72det-')).toBe(true)
      ids.add(id)
    }
    expect(ids.size).toBe(50) // 唯一，不撞
  })

  it('新增两行 rowId 唯一（且是 l72det 稳定身份而非随机运行时 ID）', async () => {
    const detailRows = ref<L7DetailRow[]>([])
    const { addRow } = useL7Detail(makeFormDataStub(), detailRows)

    await addRow()
    await addRow()

    expect(detailRows.value).toHaveLength(2)
    const [r1, r2] = detailRows.value
    expect(r1.rowId).not.toBe(r2.rowId)
    expect(r1.rowId.startsWith('l72det-')).toBe(true)
    expect(r2.rowId.startsWith('l72det-')).toBe(true)
    // 不再使用旧的随机运行时前缀
    expect(r1.rowId.startsWith('l7-detail-')).toBe(false)
  })

  it('删中间行其余行 rowId 不变（位置化缺陷反例）', () => {
    const detailRows = ref<L7DetailRow[]>([
      emptyRow('l72det-aaa', '甲'),
      emptyRow('l72det-bbb', '乙'),
      emptyRow('l72det-ccc', '丙'),
    ])
    const { removeRow } = useL7Detail(makeFormDataStub(), detailRows)

    removeRow(1) // 删中间行（乙）

    expect(detailRows.value).toHaveLength(2)
    // 若身份绑位置，删行后原第 3 行会"变成"第 2 行身份 —— 这里断言身份跟着行走，不跟位置
    expect(detailRows.value[0].rowId).toBe('l72det-aaa')
    expect(detailRows.value[1].rowId).toBe('l72det-ccc')
    expect(detailRows.value[1].itemName).toBe('丙')
  })

  it('updateRow 改字段不影响 rowId', () => {
    const detailRows = ref<L7DetailRow[]>([
      emptyRow('l72det-aaa', '甲'),
      emptyRow('l72det-bbb', '乙'),
    ])
    const { updateRow } = useL7Detail(makeFormDataStub(), detailRows)

    updateRow(0, 'beginUnadjusted', 1000)

    expect(detailRows.value[0].rowId).toBe('l72det-aaa')
    expect(detailRows.value[0].beginUnadjusted).toBe(1000)
    expect(detailRows.value[1].rowId).toBe('l72det-bbb')
  })

  it('缺 rowId 的旧数据 hydrate 时补铸；兼容旧 key 字段；已有 rowId 优先不重铸', () => {
    // 复刻组件 _restoreRowsFromResponses full-data 分支的行身份归一逻辑
    const hydrate = (raw: any): string => raw.rowId || raw.key || newRowIdentity('l72det')

    // 已有 rowId → 原样
    expect(hydrate({ rowId: 'l72det-keep', itemName: '甲' })).toBe('l72det-keep')
    // 旧 full-data 用过 key → 迁移为 rowId
    expect(hydrate({ key: 'l7-detail-123-abc', itemName: '乙' })).toBe('l7-detail-123-abc')
    // 两者都缺 → 补铸稳定身份
    const minted = hydrate({ itemName: '丙' })
    expect(minted.startsWith('l72det-')).toBe(true)
  })
})
