/**
 * l0SheetRegistry — L0 债务循环函证：sheet「定位值 / 展示值」分离真源
 *
 * spec: l0-confirmation-source-alignment，Task 18（Requirements 6.1 ~ 6.4）
 *
 * 沿用 G0 已确立的裁决：**定位用 tab 名 / 展示用底稿目录索引号 + tooltip 标注笔误**。
 *
 * 两个真源，各管一件事：
 *   - `sheetName` ← 源模板真实 tab 名（`backend/wp_templates/L/L0 债务循环函证.xlsx`
 *     的 `wb.sheetnames`）。**一切定位（render-config sheet 请求 / `?sheet=` 深链）只许用它。**
 *   - `indexLabel` ← 底稿目录 `底稿目录!F4:F11` 的索引号（**索引号唯一裁决者**）。
 *     一切 UI 展示只许用它。
 *
 * 🔴 源模板笔误（**源模板事实**，SHALL NOT 改写源 xlsx，也 SHALL NOT 静默改写展示值 ——
 *    必须在 tooltip 里说明，R6.2）：
 *      `函证程序表F0A`  tab 写 **F0A**（F 不是 L），底稿目录 `F4` 为 **L0A**
 *
 * 另两处笔误不在本注册表（它们是**列标签/交叉引用**而非 tab 名，各归其位）：
 *      `L0-1!V6` 字面「调节索引（F0-4）」应为 L0-4 → `confirmationColumnSpec` 的 label override
 *      `L0-2!AA6` 字面「跟函函证控制过程（F0-3）」应为 L0-3 → entityVerify 列标签
 *
 * 🔴 `L0-1!S33` 的「（L0-6）」是**正确索引号**（底稿目录 `F10=L0-6`），不在笔误之列 ——
 *    判索引号对错一律回查底稿目录 `F4:F11`，别看见括号就当笔误。
 *
 * 🔴 L0 的 **10 张 sheet = 9 visible + 1 hidden**（`函证差异检查表（示例）`）。
 *    该 hidden sheet 在 **D0 / F0 中是 visible**（三处模板 openpyxl 实证）→ 不得按裸
 *    sheet 名标 `skip`，处置见 Task 17 的 `{wp_code}-{sheet_name}` 复合键。
 *    本注册表的 `diffChecklist` 因此为 `null`（与 `cycleConfirmationMeta.L0` 一致）。
 *
 * 交叉锁死：`__tests__/l0SheetMeta.spec.ts` 把本文件的 `sheetName` 与后端
 * `backend/tests/test_l0_source_template_facts.py::EXPECTED_VISIBLE_SHEETS`
 * （openpyxl 直读源 xlsx）双向比对。
 */

import type {
  ConfirmationSheetRef,
  ConfirmationSheetSlot,
} from '../coordination/cycleConfirmationMeta'

/**
 * L0 注册表的键 = 函证槽位 + `directory`（底稿目录本身）。
 *
 * `directory` 不属于 `CycleConfirmationMeta.sheets` 的槽位集合（它不是函证表），
 * 但必须登记 —— 否则「注册表 sheetName ↔ 源模板可见 sheet」这条双射断言凑不齐。
 */
export type L0SheetKey = 'directory' | ConfirmationSheetSlot

/** 源模板可见 sheet 张数（另有 1 张 hidden，不计入）；数量锚点 */
export const L0_VISIBLE_SHEET_COUNT = 9

/** 源模板 hidden sheet（**不渲染**，且不得按裸名标 skip —— D0/F0 中它是 visible） */
export const L0_HIDDEN_SHEET_NAME = '函证差异检查表（示例）'

function typoNote(tabIndex: string, directoryIndex: string): string {
  return `源模板 tab 名索引号为 ${tabIndex}，底稿目录为 ${directoryIndex}，以目录为准`
}

/**
 * L0 逐 sheet 声明（`sheetName` 为 null = L0 无此表，不得编造）。
 *
 * 顺序 = 源模板 tab 顺序（前 9 条可见），便于与 `wb.sheetnames` 逐位比对。
 */
export const L0_SHEET_REGISTRY: Readonly<Record<L0SheetKey, ConfirmationSheetRef | null>> =
  Object.freeze({
    directory: { sheetName: '底稿目录', indexLabel: '底稿目录' },
    program: {
      // 🔴 tab 名带 F0A 是源模板索引号笔误；底稿目录 F4=L0A 才是真源。
      //    后端 `resolve_program_template_code('函证程序表F0A','L0')` 已能解析到 L0A
      //    （前提是 `tables.L0A` 存在，见 spec Task 2）。
      sheetName: '函证程序表F0A',
      indexLabel: 'L0A',
      indexTypoNote: typoNote('F0A', 'L0A'),
    },
    summary: { sheetName: '函证结果汇总表L0-1', indexLabel: 'L0-1' },
    entityVerify: { sheetName: '核实被函证单位信息L0-2', indexLabel: 'L0-2' },
    followup: { sheetName: '跟函函证过程控制L0-3', indexLabel: 'L0-3' },
    diff: { sheetName: '函证差异调节表L0-4', indexLabel: 'L0-4' },
    altPrimary: { sheetName: '长期应付款替代程序L0-5', indexLabel: 'L0-5' },
    reliability: { sheetName: '邮件传真回函可靠性验证L0-6', indexLabel: 'L0-6' },
    fraud: { sheetName: '函证程序舞弊风险评价表L0-7', indexLabel: 'L0-7' },
    // ── L0 无此三表 ──────────────────────────────────────────────────────
    // `diffChecklist`：源模板的 `函证差异检查表（示例）` 是 **hidden** → 不渲染（R5.1）
    diffChecklist: null,
    // `altSecondary`：L0 只有一张替代程序表
    altSecondary: null,
    // `diffSecurities`：证券差异专表仅 G0 有
    diffSecurities: null,
  })

/** 供 `cycleConfirmationMeta` 的 `sheets` 字段使用的槽位子集（剔除 `directory`） */
export const L0_CONFIRMATION_SHEETS: Readonly<
  Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>
> = Object.freeze(
  Object.fromEntries(
    Object.entries(L0_SHEET_REGISTRY).filter(([k]) => k !== 'directory'),
  ) as Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>,
)

/** 全部非 null 的定位值（= 源模板 9 张可见 sheet 的 tab 名，顺序同源模板） */
export const L0_SHEET_NAMES: readonly string[] = Object.freeze(
  Object.values(L0_SHEET_REGISTRY)
    .map((ref) => ref?.sheetName ?? null)
    .filter((n): n is string => !!n),
)

/** 取某槽位的 sheet 引用（无此表返回 null） */
export function l0SheetRef(slot: L0SheetKey): ConfirmationSheetRef | null {
  return L0_SHEET_REGISTRY[slot] ?? null
}

/**
 * 展示用索引号的 tooltip（含笔误说明后缀）。
 * 无笔误时返回 base tooltip 原样 → 其余六枢纽不受影响（它们没有 `indexTypoNote`）。
 */
export function l0IndexTooltip(ref: ConfirmationSheetRef, baseTooltip: string): string {
  return ref.indexTypoNote ? `${baseTooltip}（${ref.indexTypoNote}）` : baseTooltip
}
