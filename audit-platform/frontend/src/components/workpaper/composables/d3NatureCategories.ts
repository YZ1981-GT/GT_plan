/**
 * d3NatureCategories — D3 预收账款「款项性质」与「关联方类型」枚举单一真源（leaf，零 Vue 依赖）
 *
 * Spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/ Task 26
 *
 * 【为什么需要这个模块】
 * D3-1 审定表「一、按照性质分类」四行的未审/账项调整/重分类金额，源模板是
 *   `B8 = SUMIF('预收账款明细表D3-2'!$C$12:$C$22, '审定表D3-1'!A8, '预收账款明细表D3-2'!$E$12:$E$22)`
 * 即 **D3-2 的 C 列「款项性质」是联动键**，其取值必须与 D3-1 性质行标签逐字相同，
 * 否则该性质行恒为 0（平台侧对应 `useD3CrossSheet.natureAggregation` 按 `row.nature`
 * 字符串分组 → `useD3Adjudication` 用 `natureAgg[label]` 取值）。
 *
 * 改造前 D3-2 明细表 C 列把这四个标签**内联硬编码在 SFC 里**，与 `useD3Adjudication.NATURE_ROWS`
 * 构成双真源 —— 改一处另一处不动即静默断链。本模块作为唯一真源，两侧都从这里取。
 *
 * 【源模板实证】backend/wp_templates/D/D3 预收账款.xlsx（openpyxl 直读，data_only=False）
 * - `审定表D3-1!A8:A11` = 四类性质；`A13='合计'`（`=SUM(B8:B12)`，含 R12 空可扩行）
 * - `预收账款明细表D3-2` 数据验证：
 *     `C12:C22` list = "预收销售固定资产款,预收销售土地使用权款,合同不成立时已收取的对价,其他"
 *     `D12:D23` list = "合并范围内关联方,合并范围外关联方,非关联方"
 *
 * 【源模板自身两处缺陷 —— 按意图实现，不照抄】见 D3_SOURCE_TEMPLATE_DEFECTS
 */

/** 一个「款项性质」分类项。`rowKey` 是 D3-1 审定表持久化键的一段，改名会丢已录数据。 */
export interface D3NatureCategory {
  /** 持久化 rowKey（`D3-adj-nature-{rowKey}-{field}`），**永不改名** */
  readonly rowKey: string
  /** 显示标签 = D3-2 C 列取值 = D3-1 SUMIF 匹配键，必须与源模板逐字一致 */
  readonly label: string
  /** 源模板依据（审定表单元格坐标） */
  readonly sourceRef: string
}

/**
 * D3 款项性质四类（顺序即源模板 R8→R11 顺序，禁重排）。
 *
 * 源真源：`审定表D3-1!A8:A11`；同时是 `预收账款明细表D3-2!C12:C22` 数据验证取值域。
 */
export const D3_NATURE_CATEGORIES: readonly D3NatureCategory[] = Object.freeze([
  Object.freeze({ rowKey: 'fixed-asset-sales', label: '预收销售固定资产款', sourceRef: '审定表D3-1!A8' }),
  Object.freeze({ rowKey: 'land-use-right', label: '预收销售土地使用权款', sourceRef: '审定表D3-1!A9' }),
  Object.freeze({ rowKey: 'contract-invalid', label: '合同不成立时已收取的对价', sourceRef: '审定表D3-1!A10' }),
  Object.freeze({ rowKey: 'other', label: '其他', sourceRef: '审定表D3-1!A11' }),
]) as readonly D3NatureCategory[]

/** 款项性质候选标签（D3-2 C 列 el-select 选项，派生自 D3_NATURE_CATEGORIES） */
export const D3_NATURE_LABELS: readonly string[] = Object.freeze(
  D3_NATURE_CATEGORIES.map((c) => c.label),
) as readonly string[]

/** 性质标签 → rowKey（派生，禁再写第二份字面量 map） */
export const D3_NATURE_LABEL_TO_KEY: Readonly<Record<string, string>> = Object.freeze(
  D3_NATURE_CATEGORIES.reduce<Record<string, string>>((acc, c) => {
    acc[c.label] = c.rowKey
    return acc
  }, {}),
)

/**
 * 关联方类型候选（源真源：`预收账款明细表D3-2!D12:D23` 数据验证）。
 *
 * 🔴 改造前 SFC 硬编码的是另一套 6 项（非关联方/母公司/子公司/联营企业/合营企业/其他关联方），
 * 与源模板不一致。现按源模板收敛为 3 项；历史已录的枚举外值由
 * `d3RelationTypeOptions(current)` 动态补一个选项保住（数据零丢失红线）。
 */
export const D3_RELATION_TYPES: readonly string[] = Object.freeze([
  '合并范围内关联方',
  '合并范围外关联方',
  '非关联方',
]) as readonly string[]

/** D3-2 D 列关联方类型来源单元格（守卫用） */
export const D3_RELATION_TYPE_SOURCE_REF = '预收账款明细表D3-2!D12:D23'

/**
 * 关联方类型下拉候选：源模板 3 项 + 当前值若为枚举外历史值则追加。
 *
 * 不用 `allow-create`（会放任新造枚举），只保住既有数据可见可再保存。
 */
export function d3RelationTypeOptions(current?: string | null): string[] {
    const base = [...D3_RELATION_TYPES]
    const v = (current ?? '').trim()
    if (v && !base.includes(v)) base.push(v)
    return base
}

/**
 * 款项性质下拉候选：源模板 4 项 + 当前值若为枚举外历史值则追加。
 *
 * 追加历史值的同时它**不会**被 D3-1 SUMIF 聚合到任何性质行（会落进
 * `natureAggregation` 的额外键但无对应行）—— 这是如实暴露而非静默丢弃，
 * 审计师改成四类之一即可归位。
 */
export function d3NatureOptions(current?: string | null): string[] {
    const base = [...D3_NATURE_LABELS]
    const v = (current ?? '').trim()
    if (v && !base.includes(v)) base.push(v)
    return base
}

/**
 * 源模板自身缺陷登记（按意图实现，不照抄；守卫据此反向锁死）。
 */
export const D3_SOURCE_TEMPLATE_DEFECTS: readonly { readonly ref: string; readonly note: string }[] =
  Object.freeze([
    Object.freeze({
      ref: '预收账款明细表D3-2!C23',
      note:
        '末行 C23 单独挂了另一套 6 项数据验证（货款,工程款,设备款,服务费,' +
        '建造合同形成的已结算尚未完工款,其他），与 D3-1 SUMIF 匹配的四类性质完全不同，' +
        '疑从其它循环明细表复制残留。平台侧 D3-2 是动态行，四类性质统一适用于全部数据行，不按行号分叉。',
    }),
    Object.freeze({
      ref: "审定表D3-1!B8 SUMIF 范围 $C$12:$C$22 vs 预收账款明细表D3-2!E24=SUM(E12:E23)",
      note:
        'SUMIF 只到 R22 而合计含 R23 ⇒ 在源模板 R23 录入的金额进合计但不进任何性质行，' +
        '产生「性质合计≠账龄合计」假差异。平台侧按性质聚合覆盖全部数据行，无此缺口。',
    }),
  ]) as readonly { readonly ref: string; readonly note: string }[]
