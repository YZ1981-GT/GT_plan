/**
 * useL6Detail.rowIdentity.spec.ts — L6-2 专项应付款明细表稳定行身份测试
 *
 * Task: l6-true-bidirectional 第1步
 *
 * 验证 L6-2 明细表行身份从随机运行时 ID（l6-detail-${Date.now()}-${Math.random()}）
 * 换成稳定 rowId（`newRowIdentity('l62det')`）后：
 * 1. 新增两行 rowId 唯一（铸号器不撞）
 * 2. 删中间行其余行 rowId 不变（位置化缺陷反例 —— 若身份绑位置则删行后下游行身份会漂移）
 * 3. 缺 rowId 的旧数据 hydrate 时补铸（兼容旧 L6-L6-2-rows 的 key 字段，已有 rowId 优先不重铸）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// addRow 走 ElMessageBox.prompt：mock 成直接返回项目名称
const promptMock = vi.fn().mockResolvedValue({ value: '测试专项' })
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: (...args: any[]) => promptMock(...args) },
}))

import { useL6Detail, type L6DetailRow } from '../useL6Detail'
import { newRowIdentity } from '../shared/rowIdentity'

// ─── formData stub（useL6Detail 只用 debouncedSave） ──────────────────────────

function makeFormDataStub() {
  return {
    debouncedSave: vi.fn(),
  } as any
}

function emptyRow(rowId: string, project = ''): L6DetailRow {
  return {
    rowId,
    key: rowId,
    seq: 0,
    project,
    fundSource: '', approvalNo: '', purpose: '',
    beginBalance: 0, creditIn: 0, carryForward: 0, refund: 0, endBalance: 0,
    ajeBegin: 0, ajeCredit: 0, ajeCarryFwd: 0, ajeRefund: 0,
    rjeBegin: 0, rjeCredit: 0, rjeCarryFwd: 0, rjeRefund: 0,
    auditedBegin: 0, auditedCredit: 0, auditedCarryFwd: 0, auditedRefund: 0, auditedEnd: 0,
    docRef: '', indexRef: '', completionStatus: '', remark: '',
  }
}

describe('L6-2 明细表稳定行身份', () => {
  beforeEach(() => {
    promptMock.mockClear()
  })

  it('newRowIdentity(l62det) 生成 l62det 前缀且连续生成互不相同', () => {
    const ids = new Set<string>()
    for (let i = 0; i < 50; i++) {
      const id = newRowIdentity('l62det')
      expect(id.startsWith('l62det-')).toBe(true)
      ids.add(id)
    }
    expect(ids.size).toBe(50) // 唯一，不撞
  })

  it('新增两行 rowId 唯一（且是 l62det 稳定身份而非随机运行时 ID）', async () => {
    const detailRows = ref<L6DetailRow[]>([])
    const { addRow } = useL6Detail(makeFormDataStub(), detailRows)

    await addRow()
    await addRow()

    expect(detailRows.value).toHaveLength(2)
    const [r1, r2] = detailRows.value
    expect(r1.rowId).not.toBe(r2.rowId)
    expect(r1.rowId.startsWith('l62det-')).toBe(true)
    expect(r2.rowId.startsWith('l62det-')).toBe(true)
    // key 回落到 rowId，供 el-table :row-key 用
    expect(r1.key).toBe(r1.rowId)
    // 不再使用旧的随机运行时前缀
    expect(r1.rowId.startsWith('l6-detail-')).toBe(false)
  })

  it('删中间行其余行 rowId 不变（位置化缺陷反例）', () => {
    const detailRows = ref<L6DetailRow[]>([
      emptyRow('l62det-aaa', '甲'),
      emptyRow('l62det-bbb', '乙'),
      emptyRow('l62det-ccc', '丙'),
    ])
    const { removeRow } = useL6Detail(makeFormDataStub(), detailRows)

    removeRow(1) // 删中间行（乙）

    expect(detailRows.value).toHaveLength(2)
    // 若身份绑位置，删行后原第 3 行会"变成"第 2 行身份 —— 这里断言身份跟着行走，不跟位置
    expect(detailRows.value[0].rowId).toBe('l62det-aaa')
    expect(detailRows.value[1].rowId).toBe('l62det-ccc')
    expect(detailRows.value[1].project).toBe('丙')
  })

  it('updateRow 改字段不影响 rowId', () => {
    const detailRows = ref<L6DetailRow[]>([
      emptyRow('l62det-aaa', '甲'),
      emptyRow('l62det-bbb', '乙'),
    ])
    const { updateRow } = useL6Detail(makeFormDataStub(), detailRows)

    updateRow(0, 'beginBalance', 1000)

    expect(detailRows.value[0].rowId).toBe('l62det-aaa')
    expect(detailRows.value[0].beginBalance).toBe(1000)
    expect(detailRows.value[1].rowId).toBe('l62det-bbb')
  })

  it('缺 rowId 的旧数据 hydrate 时补铸；兼容旧 key 字段；已有 rowId 优先不重铸', () => {
    // 复刻 L6TabDetail restoreRowsFromResponses 的行身份归一逻辑
    const hydrate = (raw: any): string => raw.rowId || raw.key || newRowIdentity('l62det')

    // 已有 rowId → 原样
    expect(hydrate({ rowId: 'l62det-keep', project: '甲' })).toBe('l62det-keep')
    // 旧 L6-L6-2-rows 用过 key → 迁移为 rowId
    expect(hydrate({ key: 'l6-detail-123-abc', project: '乙' })).toBe('l6-detail-123-abc')
    // 两者都缺 → 补铸稳定身份
    const minted = hydrate({ project: '丙' })
    expect(minted.startsWith('l62det-')).toBe(true)
  })
})
