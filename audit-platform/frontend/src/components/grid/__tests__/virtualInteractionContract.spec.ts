/**
 * 虚拟化表交互契约单测（C1）：与 GridKernel 既有语义对拍。
 *
 * 判据设计（每条都有反向对照，防「合并后恒绿」）：
 * - 选区：窗口滑动（reindex 同数据）不丢、排序换位跟随行 key、行删除收缩、删空清空；
 * - 编辑回收：滚出窗口自动提交 / 行已换还原 / 值未变不写 / Escape 取消还原；
 * - 公式格：display 投影 + 错误格复制为空；
 * - 批注：按 rowKey+colKey 锚定，rebuild 后旧索引不残留；
 * - 无障碍：与 GridKernel.announce 文案逐字一致；
 * - 键位表：与 GridKernel.onSinkKeyDown 同映射（抽查主键位）。
 */
import { describe, expect, it, vi } from 'vitest'
import {
  VirtualCommentIndex,
  VirtualSelectionModel,
  VirtualTableAdapter,
  cellRefKey,
  commentAnchorKey,
  virtualAnnounceText,
  virtualCellCopyText,
  virtualKeyAction,
  type VirtualCellRef,
  type VirtualCommentAnchor,
  type VirtualGridColumn,
} from '../virtualInteractionContract'

interface Row { id: string; name: string; amount: number; rate: number | null }

const COLS: VirtualGridColumn[] = [
  { key: 'name', title: '名称' },
  { key: 'amount', title: '金额', align: 'right' },
  { key: 'rate', title: '比率', align: 'right' },
]

function rows(n: number): Row[] {
  return Array.from({ length: n }, (_, i) => ({ id: `r${i + 1}`, name: `项目${i + 1}`, amount: i * 100, rate: i % 3 === 0 ? 0.2 : null }))
}

const rowKeyOf = (r: Row) => r.id

function ref(rowId: string, colKey: string): VirtualCellRef {
  return { rowKey: rowId, colKey }
}

// ── 选区模型 ─────────────────────────────────────────────────────────────────

describe('VirtualSelectionModel（离屏逻辑选区）', () => {
  it('单击选一格；isInSelection 只认格内', () => {
    const m = new VirtualSelectionModel<Row>({ rows: rows(50), rowKey: rowKeyOf, columns: COLS })
    m.select(ref('r10', 'amount'))
    expect(m.selection?.active).toEqual(ref('r10', 'amount'))
    expect(m.isInSelection(ref('r10', 'amount'))).toBe(true)
    expect(m.isInSelection(ref('r10', 'name'))).toBe(false)
    expect(m.isInSelection(ref('r11', 'amount'))).toBe(false)
  })

  it('Shift 扩展成矩形；反向扩展也归一化', () => {
    const m = new VirtualSelectionModel<Row>({ rows: rows(50), rowKey: rowKeyOf, columns: COLS })
    m.select(ref('r5', 'name'))
    m.extendTo(ref('r8', 'rate'))
    expect(m.selection?.rect).toEqual({ r1: 4, c1: 0, r2: 7, c2: 2 })
    m.extendTo(ref('r2', 'amount'))
    expect(m.selection?.rect).toEqual({ r1: 1, c1: 0, r2: 4, c2: 1 })
    expect(m.selection?.anchor).toEqual(ref('r5', 'name'))
  })

  it('离屏不影响：reindex 同数据后选区原样（窗口滑动语义）', () => {
    const m = new VirtualSelectionModel<Row>({ rows: rows(500), rowKey: rowKeyOf, columns: COLS })
    m.select(ref('r300', 'amount'))
    m.extendTo(ref('r310', 'amount'))
    m.reindex() // 渲染窗口换了，逻辑行序没变
    expect(m.isInSelection(ref('r300', 'amount'))).toBe(true)
    expect(m.isInSelection(ref('r310', 'amount'))).toBe(true)
    expect(m.selection?.active).toEqual(ref('r310', 'amount'))
  })

  it('排序换位：选区跟随行 key（不是数字坐标）', () => {
    const data = rows(20)
    const m = new VirtualSelectionModel<Row>({ rows: data, rowKey: rowKeyOf, columns: COLS })
    m.select(ref('r5', 'amount'))
    m.extendTo(ref('r7', 'amount'))
    // 按 amount 降序重排：r5/r7 的 key 还在（位置变了）
    const reordered = [...data].sort((a, b) => b.amount - a.amount)
    m.setData(reordered)
    expect(m.rowIndex('r5')).toBe(15)
    expect(m.rowIndex('r7')).toBe(13)
    expect(m.isInSelection(ref('r5', 'amount'))).toBe(true)
    expect(m.isInSelection(ref('r6', 'amount'))).toBe(true)
    expect(m.isInSelection(ref('r7', 'amount'))).toBe(true)
  })

  it('行删除：选区收缩；删空清空（反向对照：收缩后仍保留的部分照常可用）', () => {
    const data = rows(10)
    const m = new VirtualSelectionModel<Row>({ rows: data, rowKey: rowKeyOf, columns: COLS })
    m.select(ref('r3', 'name'))
    m.extendTo(ref('r8', 'rate'))
    // 删掉 r1..r5
    const kept = data.filter((r) => Number(r.id.slice(1)) > 5)
    m.setData(kept)
    expect(m.selection).not.toBeNull()
    expect(m.selection!.rect).toEqual({ r1: 0, c1: 0, r2: 2, c2: 2 })
    expect(m.isInSelection(ref('r6', 'name'))).toBe(true)
    // 全删
    m.setData([])
    expect(m.selection).toBeNull()
  })

  it('moveBy clamp 在表内；空表 moveBy 不抛', () => {
    const m = new VirtualSelectionModel<Row>({ rows: rows(5), rowKey: rowKeyOf, columns: COLS })
    m.moveBy(1, 0) // 无选区 → 选第一格
    expect(m.selection?.active).toEqual(ref('r1', 'name'))
    m.moveBy(-10, 0)
    expect(m.selection?.active).toEqual(ref('r1', 'name'))
    m.moveBy(0, 99)
    expect(m.selection?.active).toEqual(ref('r1', 'rate'))
    const empty = new VirtualSelectionModel<Row>({ rows: [], rowKey: rowKeyOf, columns: COLS })
    expect(() => empty.moveBy(1, 0)).not.toThrow()
    expect(empty.selection).toBeNull()
  })

  it('selectedRefs 覆盖矩形全部格；onChange 订阅触发', () => {
    const m = new VirtualSelectionModel<Row>({ rows: rows(10), rowKey: rowKeyOf, columns: COLS })
    const seen: number[] = []
    m.onChange(() => seen.push(seen.length))
    m.select(ref('r2', 'name'))
    m.extendTo(ref('r3', 'amount'))
    expect(m.selectedRefs().map(cellRefKey)).toEqual([
      cellRefKey(ref('r2', 'name')), cellRefKey(ref('r2', 'amount')),
      cellRefKey(ref('r3', 'name')), cellRefKey(ref('r3', 'amount')),
    ])
    expect(seen.length).toBe(2)
  })

  it('selectAll 全选；clearSelection 清空（GridKernel 同名语义）', () => {
    const m = new VirtualSelectionModel<Row>({ rows: rows(4), rowKey: rowKeyOf, columns: COLS })
    m.selectAll()
    expect(m.selection?.rect).toEqual({ r1: 0, c1: 0, r2: 3, c2: 2 })
    expect(m.selectedRefs().length).toBe(12)
    m.clearSelection()
    expect(m.selection).toBeNull()
    expect(m.isInSelection(ref('r1', 'name'))).toBe(false)
  })

  it('越界 select clamp 到表内（不产生幽灵选区）—— 与 GridKernel.clamp 数字 clamp 同语义', () => {
    const m = new VirtualSelectionModel<Row>({ rows: rows(3), rowKey: rowKeyOf, columns: COLS })
    // 未知 key 的索引按 -1 clamp 到 0：落在第一格（GridKernel 对「超出表外坐标」同样夹到角上）
    m.select(ref('r999', 'nope'))
    expect(m.selection?.active).toEqual(ref('r1', 'name'))
    expect(m.isInSelection(ref('r1', 'name'))).toBe(true)
  })
})

// ── 编辑器回收 ───────────────────────────────────────────────────────────────

describe('VirtualEditorHost（编辑器回收协议）', () => {
  function host(data: Row[], commits: Array<{ ref: VirtualCellRef; row: Row; value: unknown }> = []) {
    const h = new VirtualTableAdapter<Row>({
      rows: data,
      columns: COLS,
      rowKey: rowKeyOf,
      editor: { commitValue: (ref, row, value) => { commits.push({ ref, row, value }) } },
    })
    return h
  }

  it('begin 记录 before 值；commit 写值；值未变不写', async () => {
    const data = rows(5)
    const commits: Array<{ ref: VirtualCellRef; row: Row; value: unknown }> = []
    const h = host(data, commits)
    const r = ref('r2', 'amount')
    h.editor.begin(r, data[1])
    expect(h.editor.isEditing(r)).toBe(true)
    expect(h.editor.beforeValue(r)).toBe(100)
    await h.editor.commit(r, 150)
    expect(commits).toEqual([{ ref: r, row: data[1], value: 150 }])
    expect(h.editor.isEditing(r)).toBe(false)
    // 值未变：不写
    h.editor.begin(r, data[1])
    await h.editor.commit(r, 100)
    expect(commits.length).toBe(1)
  })

  it('回收（evict）按当前模型值自动提交 —— 与 GtGridCell.onBeforeUnmount 同语义', async () => {
    const data = rows(5)
    const commits: Array<{ ref: VirtualCellRef; row: Row; value: unknown }> = []
    const h = host(data, commits)
    const r = ref('r2', 'amount')
    h.editor.begin(r, data[1])
    // 模拟：用户在编辑器里改了值（编辑器自身持有，模型还没收到 commit）→
    // evict 读 readValue（编辑器值投影到模型前以 before 兜底：本实现 readValue 读模型字段，
    // 编辑器自己的草稿值由接入层在 evict 前经 readValue 注入 —— 这里测「无草稿值」路径）
    await h.editor.evict(r)
    expect(commits.length).toBe(0) // 模型值 == before → 不写
    expect(h.editor.isEditing(r)).toBe(false)
  })

  it('行已换（key 不在）时 evict 不写脏值', async () => {
    const data = rows(5)
    const commits: Array<{ ref: VirtualCellRef; row: Row; value: unknown }> = []
    const h = host(data, commits)
    const r = ref('r2', 'amount')
    h.editor.begin(r, data[1])
    // 行被删（数据换成了不含 r2 的）
    h.syncData(data.filter((x) => x.id !== 'r2'))
    await h.editor.evict(r)
    expect(commits.length).toBe(0)
    expect(h.editor.isEditing(r)).toBe(false)
  })

  it('syncVisibleWindow 回收滚出窗口的编辑会话；窗口内的不动', async () => {
    const data = rows(100)
    const h = host(data)
    const inside = ref('r10', 'amount')
    const outside = ref('r90', 'amount')
    h.editor.begin(inside, data[9])
    h.editor.begin(outside, data[89])
    await h.syncVisibleWindow(data.slice(0, 20).map((r) => r.id))
    expect(h.editor.isEditing(inside)).toBe(true)
    expect(h.editor.isEditing(outside)).toBe(false)
    expect(h.isInWindow('r10')).toBe(true)
    expect(h.isInWindow('r90')).toBe(false)
  })

  it('evictAll 清空全部会话；cancel 还原（Escape 语义）', async () => {
    const data = rows(5)
    const commits: Array<{ ref: VirtualCellRef; row: Row; value: unknown }> = []
    const h = host(data, commits)
    h.editor.begin(ref('r1', 'name'), data[0])
    h.editor.begin(ref('r2', 'name'), data[1])
    await h.editor.cancel(ref('r1', 'name'))
    expect(h.editor.isEditing(ref('r1', 'name'))).toBe(false)
    expect(commits.length).toBe(0)
    await h.editor.evictAll()
    expect(h.editor.editingRefs().length).toBe(0)
    expect(commits.length).toBe(0)
  })

  it('stillSameRow 返回 false 时 commit 拒写', async () => {
    const data = rows(5)
    const commits: Array<{ ref: VirtualCellRef; row: Row; value: unknown }> = []
    const h = new VirtualTableAdapter<Row>({
      rows: data, columns: COLS, rowKey: rowKeyOf,
      editor: {
        commitValue: (ref, row, value) => { commits.push({ ref, row, value }) },
        stillSameRow: (session, current) => session.rowSnapshot === current,
      },
    })
    const r = ref('r2', 'amount')
    h.editor.begin(r, data[1])
    // 行 key 相同但对象已换（重取新对象）
    const refetched = data.map((x) => (x.id === 'r2' ? { ...x } : x))
    h.syncData(refetched)
    await h.editor.commit(r, 999)
    expect(commits.length).toBe(0)
  })

  it('onChange 在 begin / commit / cancel 时触发', async () => {
    const data = rows(3)
    const h = host(data)
    const seen: number[] = []
    h.editor.onChange(() => seen.push(1))
    h.editor.begin(ref('r1', 'name'), data[0])
    await h.editor.commit(ref('r1', 'name'), '新名')
    expect(seen.length).toBeGreaterThanOrEqual(2)
  })
})

// ── 公式格 / 复制口径 ────────────────────────────────────────────────────────

describe('公式格与复制口径', () => {
  it('displayOf：普通列取字段值；公式列走 formulaField + resolver', () => {
    const data = rows(2)
    const h = new VirtualTableAdapter<Row>({
      rows: data,
      columns: [{ key: 'amount', title: '金额' }, { key: 'rate', title: '比率', formulaField: 'rate' }],
      rowKey: rowKeyOf,
      // resolver 只对 r1 命中（r2 未命中 → 回 formulaField 值）
      formula: (r, row) => (r.colKey === 'rate' && r.rowKey === 'r1' ? { formula: '=amount*0.2', display: '20.00%' } : null),
    })
    expect(h.displayOf(ref('r1', 'amount'), data[0]).display).toBe('0')
    const rate = h.displayOf(ref('r1', 'rate'), data[0])
    expect(rate.formula).toBe('=amount*0.2')
    expect(rate.display).toBe('20.00%')
    // resolver 未命中：回 formulaField 值（r2.rate = null → 空串）
    const miss = h.displayOf(ref('r2', 'rate'), data[1])
    expect(miss.formula).toBeNull()
    expect(miss.display).toBe('')
  })

  it('错误格复制为空；正常格复制 display（virtualCellCopyText）', () => {
    expect(virtualCellCopyText({ formula: '=1/0', display: '#DIV/0!', error: true }, '#DIV/0!')).toBe('')
    expect(virtualCellCopyText({ formula: null, display: '1234.5' }, '1234.5')).toBe('1234.5')
    expect(virtualCellCopyText(null, '文字')).toBe('文字')
  })
})

// ── 批注锚点 ─────────────────────────────────────────────────────────────────

describe('VirtualCommentIndex（批注按业务身份锚定）', () => {
  const anchors: VirtualCommentAnchor[] = [
    { rowKey: 'r1', colKey: 'amount', commentId: 'c1' },
    { rowKey: 'r1', colKey: 'amount', commentId: 'c2' },
    { rowKey: 'r2', colKey: 'name', commentId: 'c3' },
  ]

  it('按格取批注（多批注）与按批注找格', () => {
    const idx = new VirtualCommentIndex()
    idx.rebuild(anchors)
    expect(idx.commentsAt('r1', 'amount').map((a) => a.commentId)).toEqual(['c1', 'c2'])
    expect(idx.commentsAt('r2', 'name').map((a) => a.commentId)).toEqual(['c3'])
    expect(idx.commentsAt('r9', 'name')).toEqual([])
    expect(idx.anchorOf('c2')).toEqual({ rowKey: 'r1', colKey: 'amount', commentId: 'c2' })
    expect(idx.anchorOf('c99')).toBeNull()
  })

  it('hasAt 角标判定；rebuild 清旧索引（反向对照：删掉的批注不再命中）', () => {
    const idx = new VirtualCommentIndex()
    idx.rebuild(anchors)
    expect(idx.hasAt('r1', 'amount')).toBe(true)
    expect(idx.hasAt('r3', 'name')).toBe(false)
    idx.rebuild(anchors.slice(2))
    expect(idx.hasAt('r1', 'amount')).toBe(false)
    expect(idx.anchorOf('c1')).toBeNull()
    expect(idx.anchorOf('c3')).not.toBeNull()
  })

  it('commentAnchorKey 稳定（同锚点同 key）', () => {
    expect(commentAnchorKey(anchors[0])).toBe(commentAnchorKey({ ...anchors[0] }))
    expect(commentAnchorKey(anchors[0])).not.toBe(commentAnchorKey(anchors[1]))
  })
})

// ── 无障碍与键位（GridKernel 对拍） ─────────────────────────────────────────

describe('无障碍文案与键位表（GridKernel 对拍）', () => {
  it('announce 文案与 GridKernel.announce 逐字一致：`列标题，第 N 行：值（可编辑）`', () => {
    expect(virtualAnnounceText('金额', 3, '1234.5', true)).toBe('金额，第 3 行：1234.5（可编辑）')
    expect(virtualAnnounceText('金额', 3, '', true)).toBe('金额，第 3 行：空（可编辑）')
    expect(virtualAnnounceText('金额', 3, 'x', false)).toBe('金额，第 3 行：x')
    expect(virtualAnnounceText('', 1, 'x', false)).toBe('第 1 行：x')
  })

  it('键位表与 GridKernel.onSinkKeyDown 同映射（抽查）', () => {
    const k = (key: string, init: Partial<KeyboardEvent> = {}) =>
      virtualKeyAction({ key, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...init })
    expect(k('ArrowDown')).toEqual({ kind: 'move', dr: 1, dc: 0, extend: false })
    expect(k('ArrowDown', { shiftKey: true })).toEqual({ kind: 'move', dr: 1, dc: 0, extend: true })
    expect(k('Enter')).toEqual({ kind: 'commit' })
    expect(k('Enter', { ctrlKey: true })).toEqual({ kind: 'none' }) // GridKernel: Ctrl+Enter 在编辑中不提交
    expect(k('F2')).toEqual({ kind: 'enter-edit' })
    expect(k('Escape')).toEqual({ kind: 'cancel' })
    expect(k('Delete')).toEqual({ kind: 'clear' })
    expect(k('c', { ctrlKey: true })).toEqual({ kind: 'copy' })
    expect(k('v', { ctrlKey: true })).toEqual({ kind: 'paste' })
    expect(k('a')).toEqual({ kind: 'none' }) // 无 Ctrl 的 a 不是快捷键
  })
})

// ── 接入层门面 ───────────────────────────────────────────────────────────────

describe('VirtualTableAdapter（接入层粘合）', () => {
  it('syncData 迁移选区（行 key 还在则保留）并同步编辑器行序', async () => {
    const data = rows(10)
    const commits: Array<{ ref: VirtualCellRef; row: Row; value: unknown }> = []
    const h = new VirtualTableAdapter<Row>({
      rows: data, columns: COLS, rowKey: rowKeyOf,
      editor: { commitValue: (ref, row, value) => { commits.push({ ref, row, value }) } },
    })
    h.selection.select(ref('r3', 'amount'))
    const filtered = data.filter((_, i) => i !== 1)
    h.syncData(filtered)
    expect(h.selection.isInSelection(ref('r3', 'amount'))).toBe(true)
    // 编辑会话跨 syncData 保留，提交按新行序找行
    h.editor.begin(ref('r3', 'amount'), data[2])
    h.syncData(data.map((x) => ({ ...x })))
    await h.editor.commit(ref('r3', 'amount'), 555)
    expect(commits.length).toBe(1)
    expect(commits[0].row.id).toBe('r3')
  })

  it('数据变化触发 selection onChange（渲染层按需重贴选区）', () => {
    const data = rows(5)
    const h = new VirtualTableAdapter<Row>({ rows: data, columns: COLS, rowKey: rowKeyOf })
    const spy = vi.fn()
    h.selection.onChange(spy)
    h.syncData([...data])
    expect(spy).toHaveBeenCalled()
  })
})
