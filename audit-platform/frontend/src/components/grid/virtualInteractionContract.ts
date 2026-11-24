/**
 * 虚拟化表交互契约（spec platform-capacity-acceptance-and-heavy-defect-closure C1）
 *
 * ═══ 为什么需要它 ═══
 *
 * GridKernel 的几何（gridDom.buildRawTableGeometry / buildElTableGeometry）按
 * **实时 DOM** 建坐标：行 = 可见 `tr`，选区标记直接写在 `<td>` 上。虚拟化表
 * （el-table-v2）只渲染可视窗口 ± overscan 的行，离屏行随时被销毁 ——
 * 把 GridKernel 直接接上去会发生四类静默错误：
 *
 * 1. 选区丢失：选了第 100 行，滚动到 900 行再回来，`<td>` 已换新节点，标记没了；
 * 2. 选区错位：行序号是「DOM 序号」不是「数据序号」，窗口滑动后 r=5 指向另一行业务数据；
 * 3. 编辑丢失：正在编辑的格滚出窗口被回收，值既没提交也没还原；
 * 4. 无障碍错读：`columnLabel` 按表头 DOM 读，虚拟表头与数据列可能不同步。
 *
 * 本模块定义**逻辑坐标契约**：选区、编辑、批注一律以稳定 key（行 key + 列 key）
 * 记账，DOM 只在渲染窗口内投影。GtVirtualTable 接入层实现该契约，
 * TB canary（C2）与附注 / 合并表（C3）按同一协议接入。
 *
 * ═══ 与 GridKernel 的关系 ═══
 *
 * 单测对拍先行（本文件 + virtualInteractionContract.spec.ts）：契约层的语义
 * （跨窗口选区保持、回收提交、复制矩阵、无障碍文案）与 GridKernel 在非虚拟表上
 * 的既有行为逐条对拍 —— 契约行为偏离 GridKernel 既有语义即红（任何既有能力回退即阻断）。
 * 真实 1000/5000 行 Playwright 取证属 C2（容量环境）。
 */

// ─────────────────────────────────────────────────────────────────────────────
// 一、坐标与身份：稳定 key 是唯一权威
// ─────────────────────────────────────────────────────────────────────────────

/** 列描述（接入层把 GtVirtualTableColumn / VirtualColumn 映射成它）。 */
export interface VirtualGridColumn {
  /** 稳定列 key（列宽拖拽、排序、批注锚点都用它；禁止用列序号）。 */
  key: string
  title: string
  align?: 'left' | 'center' | 'right'
  /** 只读列（复制照常、编辑跳过 —— 与 GridKernel 只读格同语义）。 */
  readonly?: boolean
  /** 公式列：value 取 data[formulaField]，display 由 formatter 投影。 */
  formulaField?: string
}

/** 行身份：稳定行 key。业务行用业务主键，合成行（期初 / 小计）用类型 + 位置占位。 */
export type VirtualRowKey = string

/** 行 key 提取器：接入层必须提供（与 LedgerPenetration.rowKeyOf 同职责，收敛到这里）。 */
export type RowKeyFn<R> = (row: R, rowIndex: number) => VirtualRowKey

/** 逻辑单元格坐标：(rowKey, colKey)。**不是** (r, c) 数字下标。 */
export interface VirtualCellRef {
  rowKey: VirtualRowKey
  colKey: string
}

export function cellRefKey(ref: VirtualCellRef): string {
  return `${ref.rowKey}\u0000${ref.colKey}`
}

export function sameCellRef(a: VirtualCellRef, b: VirtualCellRef): boolean {
  return a.rowKey === b.rowKey && a.colKey === b.colKey
}

// ─────────────────────────────────────────────────────────────────────────────
// 二、离屏逻辑选区：窗口滑动不丢、数据重排跟随行 key
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 逻辑选区：矩形用 **行列 key 索引**（不是坐标数字）。
 * - 排序 / 筛选后行 key 集合变化：矩形收缩到仍存在的 key（与 Excel「排序后选区跟行走」一致）；
 * - 行被删除：矩形相应收缩；全删则选区清空；
 * - 离屏（不在渲染窗口）完全不影响选区状态。
 */
export interface VirtualSelection {
  /** 锚点（Shift 扩展的起点）。 */
  anchor: VirtualCellRef
  /** 活动格（键盘焦点所在）。 */
  active: VirtualCellRef
  /** 矩形（含端点）；单格时 r1===r2 && c1===c2。 */
  rect: { r1: number; c1: number; r2: number; c2: number }
}

export interface VirtualSelectionModelOptions<R> {
  /** 逻辑行序（当前排序 / 筛选后的全量行，不只是渲染窗口）。 */
  rows: readonly R[]
  rowKey: RowKeyFn<R>
  columns: readonly VirtualGridColumn[]
}

/**
 * 逻辑选区模型 —— GridKernel 选区语义在虚拟表上的等价物。
 *
 * 与 GridKernel 对拍点（单测逐条钉住）：
 * - 单击选一格、Shift 扩展成矩形、Ctrl 追加区域（这里收敛成单矩形 + anchor，多区域后续按需加）；
 * - 合并单元格：虚拟表（el-table-v2）不支持 rowspan，契约**不支持**合并扩展，
 *   接入层若出现合并需求须先扩本契约（禁止在接入层私改语义）；
 * - clearSelection / isInSelection / moveBy / selectRect 的行为与 GridKernel 同名方法一致。
 */
export class VirtualSelectionModel<R> {
  private rowKeys: VirtualRowKey[] = []
  private keyIndex = new Map<VirtualRowKey, number>()
  private colKeys: string[] = []
  private colIndex = new Map<string, number>()
  private sel: VirtualSelection | null = null
  private listeners = new Set<() => void>()

  constructor(private readonly opts: VirtualSelectionModelOptions<R>) {
    this.reindex()
  }

  /** 数据 / 列变化后重算索引；选区收缩到仍存在的 key（GridKernel「行被换掉选区按坐标重贴」的虚拟化对应）。 */
  reindex(): void {
    this.rowKeys = this.opts.rows.map((row, i) => this.opts.rowKey(row, i))
    this.keyIndex = new Map(this.rowKeys.map((k, i) => [k, i]))
    this.colKeys = this.opts.columns.map((c) => c.key)
    this.colIndex = new Map(this.colKeys.map((k, i) => [k, i]))
    if (this.sel) this.sel = this._clampSelection(this.sel)
    this.emit()
  }

  /**
   * 数据重取 / 排序 / 筛选后同步（不改实例，监听器保持有效）。
   * 选区矩形按「仍存在的行 key」收缩：取原矩形覆盖的行 key 里仍存在的最小闭包 ——
   * 与 Excel「排序后选区跟行走」一致（r3..r8 删掉 r1..r5 后剩 r6..r8 的连续块）。
   */
  setData(rows: readonly R[], columns?: readonly VirtualGridColumn[]): void {
    // 先按旧数据把当前矩形展开成 key 集合（旧序还在 this.opts 里）
    const prevRowKeys: VirtualRowKey[] = []
    const prevColKeys: string[] = []
    if (this.sel) {
      for (let r = this.sel.rect.r1; r <= this.sel.rect.r2; r++) {
        const k = this.rowKeyAt(r)
        if (k) prevRowKeys.push(k)
      }
      for (let c = this.sel.rect.c1; c <= this.sel.rect.c2; c++) {
        const k = this.colKeyAt(c)
        if (k) prevColKeys.push(k)
      }
    }
    const prevSel = this.sel
    this.opts = { ...this.opts, rows, columns: columns ?? this.opts.columns }
    this.reindex()
    if (!prevSel) return
    const keptRows = prevRowKeys.filter((k) => this.keyIndex.has(k))
    const keptCols = prevColKeys.filter((k) => this.colIndex.has(k))
    if (!keptRows.length || !keptCols.length) { this.sel = null; this.emit(); return }
    const r1 = Math.min(...keptRows.map((k) => this.keyIndex.get(k)!))
    const r2 = Math.max(...keptRows.map((k) => this.keyIndex.get(k)!))
    const c1 = Math.min(...keptCols.map((k) => this.colIndex.get(k)!))
    const c2 = Math.max(...keptCols.map((k) => this.colIndex.get(k)!))
    const anchor = this.keyIndex.has(prevSel.anchor.rowKey) && this.colIndex.has(prevSel.anchor.colKey)
      ? prevSel.anchor
      : { rowKey: this.rowKeyAt(r1)!, colKey: this.colKeyAt(c1)! }
    const active = this.keyIndex.has(prevSel.active.rowKey) && this.colIndex.has(prevSel.active.colKey)
      ? prevSel.active
      : { rowKey: this.rowKeyAt(r2)!, colKey: this.colKeyAt(c2)! }
    this.sel = { anchor, active, rect: { r1, c1, r2, c2 } }
    this.emit()
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }

  private emit(): void {
    for (const cb of Array.from(this.listeners)) {
      try { cb() } catch { /* 订阅方错误不影响表格 */ }
    }
  }

  get selection(): VirtualSelection | null {
    return this.sel
  }

  get rowCount(): number { return this.rowKeys.length }
  get colCount(): number { return this.colKeys.length }

  rowIndex(key: VirtualRowKey): number { return this.keyIndex.get(key) ?? -1 }
  colIndex_(key: string): number { return this.colIndex.get(key) ?? -1 }
  rowKeyAt(i: number): VirtualRowKey | null { return this.rowKeys[i] ?? null }
  colKeyAt(i: number): string | null { return this.colKeys[i] ?? null }

  /** 选中一格（ScrollTo 由接入层负责；模型只管逻辑状态）。 */
  select(ref: VirtualCellRef): void {
    const clamped = this._clampRef(ref)
    const ri = this.rowIndex(clamped.rowKey)
    const ci = this.colIndex_(clamped.colKey)
    this.sel = { anchor: clamped, active: clamped, rect: { r1: ri, c1: ci, r2: ri, c2: ci } }
    this.emit()
  }

  /** Shift 扩展：从 anchor 到 ref 的矩形。 */
  extendTo(ref: VirtualCellRef): void {
    if (!this.sel) { this.select(ref); return }
    const clamped = this._clampRef(ref)
    const r1 = this.rowIndex(this.sel.anchor.rowKey)
    const c1 = this.colIndex_(this.sel.anchor.colKey)
    const r2 = this.rowIndex(clamped.rowKey)
    const c2 = this.colIndex_(clamped.colKey)
    this.sel = {
      anchor: this.sel.anchor,
      active: clamped,
      rect: {
        r1: Math.min(r1, r2), c1: Math.min(c1, c2),
        r2: Math.max(r1, r2), c2: Math.max(c1, c2),
      },
    }
    this.emit()
  }

  /** 键盘 / 编程移动（GridKernel.moveBy 同语义：clamp 到表内）。 */
  moveBy(dr: number, dc: number, opts: { extend?: boolean } = {}): void {
    if (!this.sel) {
      const first = this.rowKeyAt(0)
      const firstCol = this.colKeyAt(0)
      if (first && firstCol) this.select({ rowKey: first, colKey: firstCol })
      return
    }
    const ri = Math.max(0, Math.min(this.rowCount - 1, this.rowIndex(this.sel.active.rowKey) + dr))
    const ci = Math.max(0, Math.min(this.colCount - 1, this.colIndex_(this.sel.active.colKey) + dc))
    const ref = { rowKey: this.rowKeyAt(ri)!, colKey: this.colKeyAt(ci)! }
    if (opts.extend) this.extendTo(ref)
    else this.select(ref)
  }

  isInSelection(ref: VirtualCellRef): boolean {
    if (!this.sel) return false
    const ri = this.rowIndex(ref.rowKey)
    const ci = this.colIndex_(ref.colKey)
    if (ri < 0 || ci < 0) return false
    const { r1, c1, r2, c2 } = this.sel.rect
    return ri >= r1 && ri <= r2 && ci >= c1 && ci <= c2
  }

  /** 选区内全部逻辑格（只算存在的 key —— 行删除后自动收缩）。 */
  selectedRefs(): VirtualCellRef[] {
    if (!this.sel) return []
    const out: VirtualCellRef[] = []
    for (let r = this.sel.rect.r1; r <= this.sel.rect.r2; r++) {
      for (let c = this.sel.rect.c1; c <= this.sel.rect.c2; c++) {
        const rowKey = this.rowKeyAt(r)
        const colKey = this.colKeyAt(c)
        if (rowKey && colKey) out.push({ rowKey, colKey })
      }
    }
    return out
  }

  clearSelection(): void {
    this.sel = null
    this.emit()
  }

  /** 全选（Ctrl+A）。 */
  selectAll(): void {
    if (!this.rowCount || !this.colCount) return
    const anchor = { rowKey: this.rowKeyAt(0)!, colKey: this.colKeyAt(0)! }
    const far = { rowKey: this.rowKeyAt(this.rowCount - 1)!, colKey: this.colKeyAt(this.colCount - 1)! }
    this.sel = {
      anchor,
      active: far,
      rect: { r1: 0, c1: 0, r2: this.rowCount - 1, c2: this.colCount - 1 },
    }
    this.emit()
  }

  private _clampRef(ref: VirtualCellRef): VirtualCellRef {
    const ri = Math.max(0, Math.min(this.rowCount - 1, this.rowIndex(ref.rowKey)))
    const ci = Math.max(0, Math.min(this.colCount - 1, this.colIndex_(ref.colKey)))
    return { rowKey: this.rowKeyAt(ri) ?? ref.rowKey, colKey: this.colKeyAt(ci) ?? ref.colKey }
  }

  private _clampSelection(sel: VirtualSelection): VirtualSelection | null {
    const r1 = Math.max(0, sel.rect.r1)
    const c1 = Math.max(0, sel.rect.c1)
    const r2 = Math.min(this.rowCount - 1, sel.rect.r2)
    const c2 = Math.min(this.colCount - 1, sel.rect.c2)
    if (r1 > r2 || c1 > c2) return null
    const anchor = this.keyIndex.has(sel.anchor.rowKey) && this.colIndex.has(sel.anchor.colKey)
      ? sel.anchor
      : { rowKey: this.rowKeyAt(r1)!, colKey: this.colKeyAt(c1)! }
    const active = this.keyIndex.has(sel.active.rowKey) && this.colIndex.has(sel.active.colKey)
      ? sel.active
      : { rowKey: this.rowKeyAt(r2)!, colKey: this.colKeyAt(c2)! }
    return { anchor, active, rect: { r1, c1, r2, c2 } }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 三、编辑器回收：滚出窗口先提交，回来不重放
// ─────────────────────────────────────────────────────────────────────────────

/** 编辑会话：虚拟表上一个正在编辑的格。 */
export interface VirtualEditSession<R> {
  ref: VirtualCellRef
  /** 提交时的行数据快照（回收再挂时校验行没换 —— 行 key 相同但内容可能已重取）。 */
  rowSnapshot: R
  /** 进入编辑时的值（取消 / 回收还原用）。 */
  before: unknown
}

export interface VirtualEditorHostOptions<R> {
  /** 逻辑行序（全量，不是渲染窗口）：按行 key 找当前行用。 */
  rows: readonly R[]
  rowKey: RowKeyFn<R>
  /** 读当前值（编辑器挂载前也算得出来 —— 显示值即模型值）。 */
  readValue(ref: VirtualCellRef, row: R): unknown
  /** 写值：宿主照常收到 change（与 GridKernel「编辑器句柄提交 → 宿主 change」一致）。 */
  commitValue(ref: VirtualCellRef, row: R, value: unknown): void | Promise<void>
  /** 行 key 相同但内容已换（重取 / 排序）时是否仍可提交；默认 true。 */
  stillSameRow?(session: VirtualEditSession<R>, currentRow: R): boolean
}

/**
 * 编辑会话管理 —— 回收协议：
 *
 * 1. `begin(ref, row)`：开始编辑（记录 before 值）；
 * 2. 行滚出渲染窗口：接入层调 `evict(ref)` —— **自动提交**（GridKernel.onBeforeUnmount
 *    对未提交编辑器的同语义：`GtGridCell.onBeforeUnmount` commit）；
 * 3. 提交失败 / 行已换：按 `stillSameRow` 判定，false 时**还原** before（不写脏值）；
 * 4. `cancel(ref)`：显式取消（Escape），还原 before。
 *
 * 禁止：回收时静默丢弃编辑值（丢数据）或跳过校验直接写（可能写错行）。
 */
export class VirtualEditorHost<R> {
  private sessions = new Map<string, VirtualEditSession<R>>()
  private listeners = new Set<() => void>()

  constructor(private opts: VirtualEditorHostOptions<R>) {}

  onChange(cb: () => void): () => void {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }

  private emit(): void {
    for (const cb of Array.from(this.listeners)) {
      try { cb() } catch { /* 同上 */ }
    }
  }

  begin(ref: VirtualCellRef, row: R): VirtualEditSession<R> {
    const key = cellRefKey(ref)
    // 同格重复 begin：先按取消处理（不应发生；防御并发双击）
    const prev = this.sessions.get(key)
    if (prev) void this.cancel(ref)
    const session: VirtualEditSession<R> = { ref, rowSnapshot: row, before: this.opts.readValue(ref, row) }
    this.sessions.set(key, session)
    this.emit()
    return session
  }

  isEditing(ref: VirtualCellRef): boolean {
    return this.sessions.has(cellRefKey(ref))
  }

  editingRefs(): VirtualCellRef[] {
    return Array.from(this.sessions.values()).map((s) => s.ref)
  }

  beforeValue(ref: VirtualCellRef): unknown {
    return this.sessions.get(cellRefKey(ref))?.before
  }

  /** 提交一格（Enter / 失焦 / 回收前）。值与 before 相同不写（与 GridKernel.recordEdit 同语义）。 */
  async commit(ref: VirtualCellRef, value: unknown): Promise<boolean> {
    const key = cellRefKey(ref)
    const session = this.sessions.get(key)
    if (!session) return false
    this.sessions.delete(key)
    if (value === session.before) { this.emit(); return true }
    const currentRow = this._findRow(ref.rowKey)
    const same = currentRow !== undefined && (this.opts.stillSameRow?.(session, currentRow) ?? true)
    if (!same) {
      // 行已换：还原语义 = 什么都不写（before 本来就没写出去）
      this.emit()
      return false
    }
    await this.opts.commitValue(ref, currentRow as R, value)
    this.emit()
    return true
  }

  /** 回收（滚出渲染窗口）：未提交则按当前模型值提交 —— 与 GtGridCell.onBeforeUnmount 同语义。 */
  async evict(ref: VirtualCellRef): Promise<boolean> {
    const key = cellRefKey(ref)
    const session = this.sessions.get(key)
    if (!session) return false
    const currentRow = this._findRow(ref.rowKey)
    const value = currentRow !== undefined ? this.opts.readValue(ref, currentRow) : session.before
    return this.commit(ref, value)
  }

  /** 回收全部（表卸载 / 模式切换）。 */
  async evictAll(): Promise<number> {
    const refs = this.editingRefs()
    let n = 0
    for (const ref of refs) if (await this.evict(ref)) n++
    return n
  }

  async cancel(ref: VirtualCellRef): Promise<void> {
    this.sessions.delete(cellRefKey(ref))
    this.emit()
  }

  /** 数据重取 / 排序后同步行序（编辑会话保留；提交时按新行序找当前行）。 */
  resyncRows(rows: readonly R[]): void {
    this.opts = { ...this.opts, rows }
  }

  private _findRow(rowKey: VirtualRowKey): R | undefined {
    return this.opts.rows.find((row, i) => this.opts.rowKey(row, i) === rowKey)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 四、公式格：显示值 ↔ 公式串投影（只读展示协议）
// ─────────────────────────────────────────────────────────────────────────────

/** 公式格描述：display 为渲染值；formula 非空时格上有「公式提示」且复制按显示值走。 */
export interface FormulaCellInfo {
  /** 公式串（如 `=SUM(A1:A5)`）；null = 普通格。 */
  formula: string | null
  /** 计算后的显示值。 */
  display: string
  /** 计算失败标记（显示「#REF!」等错误串时为 true，复制与统计按 0 处理 —— 与 GridKernel parseLooseNumber 对齐）。 */
  error?: boolean
}

export type FormulaResolver = (ref: VirtualCellRef, row: unknown) => FormulaCellInfo | null

/**
 * 复制 / 统计口径（与 GridKernel.cellValueWithSource 三级来源对拍）：
 * 1. 编辑器值（正在编辑）；
 * 2. `data-gt-value`（原始金额，不受显示单位影响）→ 虚拟表对应 formula/display 投影；
 * 3. 显示文字解析（parseLooseNumber）。
 * 虚拟表接入层按 display 走第 3 级；公式格的 display 必须是**原始数值格式**（千分位可留，
 * 单位换算的倍率字段不允许 —— 同 GtAmountCell data-gt-value 的语义）。
 */
export function virtualCellCopyText(info: FormulaCellInfo | null, display: string): string {
  if (info?.error) return '' // 错误格复制为空（GridKernel 对 #REF! 同口径：parseLooseNumber 解析失败得原文，统计跳过）
  return display
}

// ─────────────────────────────────────────────────────────────────────────────
// 五、批注锚点：行 key + 列 key
// ─────────────────────────────────────────────────────────────────────────────

/** 批注（锚定到业务身份，不是 DOM 位置；行删除批注随之失效由存储方决定）。 */
export interface VirtualCommentAnchor {
  rowKey: VirtualRowKey
  colKey: string
  /** 批注 id（存储方主键）。 */
  commentId: string
}

export function commentAnchorKey(a: VirtualCommentAnchor): string {
  return `${a.rowKey}\u0000${a.colKey}\u0000${a.commentId}`
}

/** 批注索引：按格找批注（渲染角标）与按批注找格（点目录跳转）共用。 */
export class VirtualCommentIndex {
  private byCell = new Map<string, VirtualCommentAnchor[]>()
  private byComment = new Map<string, VirtualCommentAnchor>()

  rebuild(anchors: readonly VirtualCommentAnchor[]): void {
    this.byCell.clear()
    this.byComment.clear()
    for (const a of anchors) {
      const ck = `${a.rowKey}\u0000${a.colKey}`
      const list = this.byCell.get(ck) ?? []
      list.push(a)
      this.byCell.set(ck, list)
      this.byComment.set(a.commentId, a)
    }
  }

  commentsAt(rowKey: VirtualRowKey, colKey: string): VirtualCommentAnchor[] {
    return this.byCell.get(`${rowKey}\u0000${colKey}`) ?? []
  }

  anchorOf(commentId: string): VirtualCommentAnchor | null {
    return this.byComment.get(commentId) ?? null
  }

  /** 该格是否应渲染角标（0 个批注不渲染）。 */
  hasAt(rowKey: VirtualRowKey, colKey: string): boolean {
    return (this.byCell.get(`${rowKey}\u0000${colKey}`)?.length ?? 0) > 0
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 六、无障碍：读屏文案协议（GridKernel.announce 的虚拟表对应）
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 读屏播报文案：`列标题，第 N 行：值（可编辑）`。
 * 与 GridKernel.announce 逐字对拍 —— 契约测试断言两者对同一数据产出相同文案
 * （GridKernel 用 DOM 表头列名，契约用列描述 title；接入层保证两者同源）。
 */
export function virtualAnnounceText(
  colTitle: string,
  rowIndex1based: number,
  display: string,
  editable: boolean,
): string {
  const label = colTitle ? `${colTitle}，` : ''
  return `${label}第 ${rowIndex1based} 行：${display || '空'}${editable ? '（可编辑）' : ''}`
}

// ─────────────────────────────────────────────────────────────────────────────
// 七、键盘导航协议（接入层把 el-table-v2 的 row-event-handlers 翻译到这里）
// ─────────────────────────────────────────────────────────────────────────────

export interface VirtualKeyAction {
  kind: 'move' | 'enter-edit' | 'commit' | 'cancel' | 'copy' | 'paste' | 'clear' | 'none'
  dr?: number
  dc?: number
  extend?: boolean
}

/**
 * 键位 → 动作（与 GridKernel.onSinkKeyDown 同一张表；这里返回声明式动作由接入层执行，
 * 便于单测不挂真 DOM 就能对拍键位语义）。
 */
export function virtualKeyAction(e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>): VirtualKeyAction {
  const ctrl = e.ctrlKey || e.metaKey
  switch (e.key) {
    case 'ArrowUp': return { kind: 'move', dr: -1, dc: 0, extend: e.shiftKey }
    case 'ArrowDown': return { kind: 'move', dr: 1, dc: 0, extend: e.shiftKey }
    case 'ArrowLeft': return { kind: 'move', dr: 0, dc: -1, extend: e.shiftKey }
    case 'ArrowRight': return { kind: 'move', dr: 0, dc: 1, extend: e.shiftKey }
    case 'Home': return { kind: 'move', dr: 0, dc: -Number.MAX_SAFE_INTEGER, extend: e.shiftKey }
    case 'End': return { kind: 'move', dr: 0, dc: Number.MAX_SAFE_INTEGER, extend: e.shiftKey }
    case 'Enter': return ctrl || e.altKey ? { kind: 'none' } : { kind: 'commit' }
    case 'F2': return { kind: 'enter-edit' }
    case 'Escape': return { kind: 'cancel' }
    case 'Delete': return { kind: 'clear' }
    default:
      if (ctrl && e.key.toLowerCase() === 'c') return { kind: 'copy' }
      if (ctrl && e.key.toLowerCase() === 'v') return { kind: 'paste' }
      return { kind: 'none' }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 八、GtVirtualTable 接入层：把契约接到 el-table-v2 的渲染窗口
// ─────────────────────────────────────────────────────────────────────────────

export interface VirtualTableAdapterOptions<R> {
  rows: readonly R[]
  columns: readonly VirtualGridColumn[]
  rowKey: RowKeyFn<R>
  formula?: FormulaResolver
  editor?: Pick<VirtualEditorHostOptions<R>, 'commitValue' | 'stillSameRow'>
}

/**
 * 接入层门面：GtVirtualTable.vue 持有一个实例，把
 * selection / editor / comment / announce 四块协议一起暴露给模板与事件。
 * 契约对象（模型类）可独立单测；本门面只做粘合，不新增语义。
 */
export class VirtualTableAdapter<R> {
  readonly selection: VirtualSelectionModel<R>
  readonly editor: VirtualEditorHost<R>
  readonly comments = new VirtualCommentIndex()
  private visibleWindow = new Set<VirtualRowKey>()
  private _columns: readonly VirtualGridColumn[]
  private _rows: readonly R[]
  private _rowKey: RowKeyFn<R>
  private _formula: FormulaResolver | null

  constructor(opts: VirtualTableAdapterOptions<R>) {
    this._rows = opts.rows
    this._columns = opts.columns
    this._rowKey = opts.rowKey
    this._formula = opts.formula ?? null
    this.selection = new VirtualSelectionModel({ rows: opts.rows, rowKey: opts.rowKey, columns: opts.columns })
    this.editor = new VirtualEditorHost({
      readValue: (ref, row) => {
        const col = this._columns.find((c) => c.key === ref.colKey)
        if (col?.formulaField) return (row as Record<string, unknown>)[col.formulaField]
        return (row as Record<string, unknown>)[ref.colKey]
      },
      commitValue: opts.editor?.commitValue ?? (() => undefined),
      stillSameRow: opts.editor?.stillSameRow,
      rows: opts.rows,
      rowKey: opts.rowKey,
    })
  }

  /** 数据 / 列变化（排序、筛选、重取）后同步：选区按行 key 收缩，编辑会话校验行身份。 */
  syncData(rows: readonly R[], columns?: readonly VirtualGridColumn[]): void {
    this._rows = rows
    if (columns) this._columns = columns
    this.selection.setData(rows, columns)
    this.editor.resyncRows(rows)
  }

  /** 渲染窗口回写（el-table-v2 每次渲染后调）：回收滚出窗口的编辑会话。 */
  async syncVisibleWindow(visibleRowKeys: readonly VirtualRowKey[]): Promise<void> {
    const next = new Set(visibleRowKeys)
    for (const ref of this.editor.editingRefs()) {
      if (!next.has(ref.rowKey)) await this.editor.evict(ref)
    }
    this.visibleWindow = next
  }

  isInWindow(rowKey: VirtualRowKey): boolean {
    return this.visibleWindow.has(rowKey)
  }

  /** 单元格展示投影（cellRenderer 调）：公式列走 resolver，普通列取字段值。 */
  displayOf(ref: VirtualCellRef, row: R): FormulaCellInfo {
    const col = this._columns.find((c) => c.key === ref.colKey)
    if (col?.formulaField) {
      const fv = (row as Record<string, unknown>)[col.formulaField]
      const viaFormula = this._formula?.(ref, row)
      return viaFormula ?? { formula: null, display: fv == null ? '' : String(fv) }
    }
    const raw = (row as Record<string, unknown>)[ref.colKey]
    return { formula: null, display: raw == null ? '' : String(raw) }
  }
}
