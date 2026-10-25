/**
 * L8-2 财务费用明细表 —— 骨架行身份（与 OnlyOffice 侧模板行身份对齐）
 *
 * 🔴 L8-2 受管表是**模板预置带标签骨架行**：R9~R21 共 13 行固定科目（利息费用总额 / 减：利息资本化 /
 * …… / 汇兑净损失 / 手续费及其他），instrumentation 发布 substrate 时给这 13 行 X 列各注入了模板行身份
 * `GTROW-L82-{行号4位}`（现算 substrate X 列确认 GTROW-L82-0009…GTROW-L82-0021）。
 *
 * 若 HTML 骨架行自铸随机 UUID（`l82det-*`），两侧身份命名空间不相交 —— 真 OO 往返 extract 回来的
 * projection 同时含 13 条 GTROW 骨架行 + HTML 自铸行，merge 把 13 条 GTROW 行当「base_rows 里没有的
 * 新行」新建 target（无 monthly list）→ set_json_path('monthly/0') fail-closed。与 J1-6 短期薪酬区同型
 * （见 `j1/inspection/j1AccrualRowIdentity.ts`）。
 *
 * 处置（方案 D1：10 输入骨架行双向 + 3 派生行只读模板计算，用户裁决 2026-10-02）：
 *   - 13 行骨架行**全部显示**（用户看到完整的财务费用结构），身份用模板身份 `GTROW-L82-NNNN`、按**位置**认领。
 *   - 其中 **3 个跨行派生行**（R11 利息费用=R9-R10 / R13 利息净支出=R11-R12 / R20 汇兑净损失=R17-R18-R19）
 *     的 1~12 月格是模板预置跨行减法公式，审计上本就该由上方科目算出 ⇒ HTML 侧**只读**（用户不可编辑）、
 *     且**不进 store 载荷**（`L8-2-full-data` 只存 10 个输入行 + 用户新增行）。其值由前端按同口径跨行减法
 *     算出来**仅作显示**；真 OO 往返时这 3 行不在 projection 的 row_keys 里 ⇒ 引擎 `_emit` 不碰它们 ⇒
 *     模板跨行公式原样幸存（`is_template_skeleton_identity` 另保护它们不被当 stale 删）。
 *   - 用户 addRow 新增的明细行自铸 `l82det-*`（走 shared/rowIdentity.newRowIdentity）。
 *   merge 时 GTROW-L82-*（10 输入行）命中 base_rows 里已存在的骨架行 target 回填、不新建；
 *   l82det-* 是真新增行走建新 target —— 分流靠「输入骨架行恒在 base_rows 里」而非 merge 层特判。
 *
 * 🔴 **为什么派生行不能双向**（引擎层坐实，2026-10-02）：B~M 列对全部 13 行只能有一个列级 mode
 *   （editable 或 formula）。派生行要「formula 只读」而输入行要「editable」是**列内 per-row 混合**，
 *   现有 `excel_materialize` 表达不了：只要派生行进 store（在 projection 的 wanted 里），materialize 的
 *   `_emit` 就按 editable 写它的 B~M（HTML 发 0/None/不发都会把 =B9-B10 清成 0）。唯一让公式幸存的办法
 *   是**派生行不进 store**（实测 materialize 后 B11/B13/B20 公式全幸存、输入行 B9 正常写入）。
 *
 * 真 OO 往返守卫：backend/scripts/e2e/verify_l8_oo94_roundtrip.py
 * 后端身份真源：phase5_l8_sheets（TEMPLATE_ID='L82'、FIRST_DATA_ROW=9、DERIVED_ROWS=R11/R13/R20）。
 */

/** 模板 ID（与后端 phase5_l8_sheets.TEMPLATE_ID 一致）。 */
export const L82_TEMPLATE_ID = 'L82'
/** 受管区首个数据行（R9，与后端 FIRST_DATA_ROW 一致）。 */
export const L82_FIRST_DATA_ROW = 9
const TEMPLATE_ROW_ID_PREFIX = 'GTROW-'

/**
 * 13 行模板骨架行的 A 列科目名称（R9~R21），顺序即 Excel 行序。
 * 🔴 含「汇兑净损失」（R20 派生行）—— 旧 HTML 的 12 默认项缺这一项，方案 D 补齐为 13 行与模板 1:1。
 */
export const L82_SKELETON_ITEMS: readonly string[] = [
  '利息费用总额', // R9
  '减：利息资本化', // R10
  '利息费用', // R11（派生：=R9-R10）
  '减：利息收入', // R12
  '利息净支出', // R13（派生：=R11-R12）
  '未确认融资费用', // R14
  '减：未实现融资收益', // R15
  '承兑汇票贴息', // R16
  '汇兑损失', // R17
  '减：汇兑收益', // R18
  '减：汇兑损益资本化', // R19
  '汇兑净损失', // R20（派生：=R17-R18-R19）
  '手续费及其他', // R21
]

/**
 * 跨行派生行的骨架行下标（0 起）：R11=idx2 / R13=idx4 / R20=idx11。
 * 这些行的 1~12 月格是模板预置公式 ⇒ HTML 标只读、不进 store 载荷、模板公式幸存。
 */
export const L82_DERIVED_ROW_INDICES: readonly number[] = [2, 4, 11]

/**
 * 派生行的跨行减法源（下标 0 起，前端只读显示时按同口径算；= 后端模板公式）：
 *   R11(idx2) = R9(idx0) - R10(idx1)
 *   R13(idx4) = R11(idx2) - R12(idx3)
 *   R20(idx11) = R17(idx8) - R18(idx9) - R19(idx10)
 * 加项 `+`、减项 `-`；按 L82_SKELETON_ITEMS 下标引用。
 */
export const L82_DERIVED_ROW_SOURCES: Readonly<Record<number, ReadonlyArray<readonly [number, 1 | -1]>>> = {
  2: [[0, 1], [1, -1]],
  4: [[2, 1], [3, -1]],
  11: [[8, 1], [9, -1], [10, -1]],
}

/** 第 index 条骨架行（0 起）对应的模板行身份 `GTROW-L82-NNNN`。 */
export function l82TemplateRowId(index: number): string {
  if (!Number.isInteger(index) || index < 0 || index >= L82_SKELETON_ITEMS.length) {
    throw new RangeError(`非法骨架行下标 ${index}`)
  }
  const row = String(L82_FIRST_DATA_ROW + index).padStart(4, '0')
  return `${TEMPLATE_ROW_ID_PREFIX}${L82_TEMPLATE_ID}-${row}`
}

/** 是否为模板骨架行身份（`GTROW-L82-*`）。 */
export function isL82TemplateRowId(id: unknown): boolean {
  return typeof id === 'string' && id.startsWith(TEMPLATE_ROW_ID_PREFIX)
}

/** 第 index 条骨架行是否为跨行派生行（月度格只读）。 */
export function isL82DerivedRow(index: number): boolean {
  return L82_DERIVED_ROW_INDICES.includes(index)
}

/** 3 个派生行的模板身份集合（供「不进 store 载荷」过滤）。 */
export const L82_DERIVED_ROW_KEYS: ReadonlySet<string> = new Set(
  L82_DERIVED_ROW_INDICES.map(i => l82TemplateRowId(i)),
)

/**
 * 某行 key 是否为跨行派生行的骨架身份（供 UI 判月度格只读 + store 过滤）。
 * 只认模板身份；用户自铸行永远可编辑。
 */
export function isL82DerivedRowKey(key: unknown): boolean {
  return typeof key === 'string' && L82_DERIVED_ROW_KEYS.has(key)
}

/**
 * 剔除派生行后的 store 载荷（方案 D1：`L8-2-full-data` 只存 10 输入骨架行 + 用户新增行）。
 * 派生行是模板计算只读行，不持久化；真 OO 往返时不在 projection ⇒ 模板跨行公式幸存。
 */
export function rowsForStore<T extends { key: string }>(rows: readonly T[]): T[] {
  return rows.filter(r => !isL82DerivedRowKey(r.key))
}
