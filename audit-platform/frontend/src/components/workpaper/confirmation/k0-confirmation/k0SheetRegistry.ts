/**
 * k0SheetRegistry — K0 管理循环函证：sheet「定位值 / 展示值」分离真源
 *
 * spec: k0-confirmation-source-alignment，Task 12（Requirements 2.2 / 6.1 / 6.2）
 *
 * 沿用 G0/L0 已确立的裁决：**定位用 tab 名 / 展示用底稿目录索引号 + tooltip 标注笔误**。
 *
 * 两个真源，各管一件事：
 *   - `sheetName` ← 源模板真实 tab 名（`backend/wp_templates/K/K0 管理循环函证.xlsx`
 *     的 `wb.sheetnames`）。**一切定位（render-config sheet 请求 / `?sheet=` 深链）只许用它。**
 *   - `indexLabel` ← 底稿目录 `底稿目录!F5:F13` 的索引号（**索引号唯一裁决者**）。
 *     一切 UI 展示只许用它。
 *
 * ─── K0 与 G0/L0 的两处不同（勿照抄它们的结论） ─────────────────────────────
 *
 * **① K0 的 tab 名索引号与底稿目录逐个一致，没有 tab 名笔误。**
 * G0 有两处（非证券差异表 tab 写 G0-4 而目录为 G0-5 等）、L0 有一处（`函证程序表F0A`），
 * 而 K0 十张 tab 的尾码与目录 `F5:F13` 逐位相符（后端 `test_k0_source_template_facts.py::
 * test_index_sheet_nine_rows` 已把这条双射钉死）。
 *
 * **② K0 的三条索引号笔误是「跨表引用文案」而不是 tab 名。**
 * 它们写在单元格正文里（`K0-1!V6` / `K0-1!S32` / `K0-2!AA6`），指向的目标表本身命名正确。
 * 故 `indexTypoNote` 在 K0 这里承载的语义是「**该目标表在源模板别处被写错了索引号**」，
 * 与 G0/L0 的「本表 tab 名索引号写错」是两种成因 —— 两者都落在同一个 tooltip 出口
 * （`buildCrossWorkpaperNavDefs` 的 `tooltipOf`），因为对用户而言要回答的是同一个问题：
 * 「我在源模板上看到的那个索引号，为什么和这里显示的不一样」。
 *
 * 三条 tooltip 文案**从 `K0_INDEX_TYPO_MAP` 派生**（`k0LowerZoneSpec.ts` 是笔误唯一真源），
 * 不在本文件抄第二份中文 —— 否则改一处另一处不动，就是双真源。
 *
 * ─── 接注册表的另一重收益：让三张表可达 ──────────────────────────────────────
 *
 * 🔴 库侧实证（2026-08-07，`wp_index`）：K0 只有整册 `K0` 与遗留单 sheet
 *    `K0-1`~`K0-5`，**没有 `K0-6` / `K0-7` / `K0-8`** —— 而这三个恰是
 *    `altSecondaryCode` / `reliabilityCode` / `fraudCode` 三个槽位。
 *    改造前 K0 走 `deriveSheetsFromCodes`（`sheetName === indexLabel === 'K0-6'`），
 *    `isSameWorkbookNavTarget()` 恒 false ⇒ 跳转按 wp_code 解析 ⇒ **这三张表跳不过去**。
 *    接注册表后 `sheetName` 是真实 tab 名 ⇒ 走同工作簿 `?sheet=` 深链 ⇒ 可达。
 *    这与 L0 的裁决依据（其 `wp_index` 同样缺 L0-6/L0-7）逐字同构。
 *
 * 交叉锁死：`__tests__/k0SheetRegistry.spec.ts` 把本文件的 `sheetName` 与后端
 * `backend/tests/test_k0_source_template_facts.py::EXPECTED_VISIBLE_SHEETS`
 * （openpyxl 直读源 xlsx）双向比对，并断言三条 tooltip 确实由笔误真源派生。
 */

import type {
  ConfirmationSheetRef,
  ConfirmationSheetSlot,
} from '../coordination/cycleConfirmationMeta'
import { K0_INDEX_TYPO_MAP, type K0IndexTypo } from './k0LowerZoneSpec'

/**
 * K0 注册表的键 = 函证槽位 + `directory`（底稿目录本身）。
 *
 * `directory` 不属于 `CycleConfirmationMeta.sheets` 的槽位集合（它不是函证表），
 * 但必须登记 —— 否则「注册表 sheetName ↔ 源模板可见 sheet」这条双射断言凑不齐。
 */
export type K0SheetKey = 'directory' | ConfirmationSheetSlot

/** 源模板可见 sheet 张数（另有 1 张 `GT_Custom` hidden，不计入）；数量锚点 */
export const K0_VISIBLE_SHEET_COUNT = 10

/** 唯一 hidden sheet —— K0 无「隐藏表被渲染成页签」议题（与 E0 不同） */
export const K0_HIDDEN_SHEET_NAME = 'GT_Custom'

/**
 * 由笔误真源派生 tooltip 文案。
 *
 * 找不到对应条目时抛错而不是静默返回 undefined —— 笔误真源被改动过（删条目 / 改
 * `intended`）时必须立刻暴露，否则 tooltip 静默消失、用户又会被源模板的错索引号误导。
 */
function typoNoteFor(intended: K0IndexTypo['intended']): string {
  const t = K0_INDEX_TYPO_MAP.find((x) => x.intended === intended)
  if (!t) {
    throw new Error(
      `[k0SheetRegistry] K0_INDEX_TYPO_MAP 缺少 intended=${intended} 的条目；` +
        `笔误真源在 k0LowerZoneSpec.ts，不得在本文件另抄一份文案`,
    )
  }
  return `源模板 ${t.sourceRef} 处写作「${t.literal}」，实为 ${t.intended}，以此处显示为准`
}

/**
 * K0 逐 sheet 声明（`sheetName` 为 null = K0 无此表，不得编造）。
 *
 * 顺序 = 源模板 tab 顺序（10 张可见），便于与 `wb.sheetnames` 逐位比对。
 */
export const K0_SHEET_REGISTRY: Readonly<Record<K0SheetKey, ConfirmationSheetRef | null>> =
  Object.freeze({
    directory: { sheetName: '底稿目录', indexLabel: '底稿目录' },
    program: { sheetName: '函证程序表K0A', indexLabel: 'K0A' },
    summary: { sheetName: '函证结果汇总表K0-1', indexLabel: 'K0-1' },
    entityVerify: { sheetName: '核实被函证单位信息K0-2', indexLabel: 'K0-2' },
    followup: {
      sheetName: '跟函函证过程控制K0-3',
      indexLabel: 'K0-3',
      // 源 `核实被函证单位信息K0-2!AA6` 写「跟函函证控制过程（K1-11）」
      indexTypoNote: typoNoteFor('K0-3'),
    },
    diff: {
      sheetName: '函证差异调节表K0-4',
      indexLabel: 'K0-4',
      // 源 `函证结果汇总表K0-1!V6` 写「调节索引（K1-12）」
      indexTypoNote: typoNoteFor('K0-4'),
    },
    altPrimary: { sheetName: '其他应收款替代程序K0-5', indexLabel: 'K0-5' },
    altSecondary: { sheetName: '其他应付款替代程序K0-6', indexLabel: 'K0-6' },
    reliability: {
      sheetName: '邮件传真回函可靠性验证K0-7',
      indexLabel: 'K0-7',
      // 源 `函证结果汇总表K0-1!S32` 的第 3 项标题写「（K0-6）」（K0-6 是其他应付款替代程序）
      indexTypoNote: typoNoteFor('K0-7'),
    },
    fraud: { sheetName: '函证程序舞弊风险评价表K0-8', indexLabel: 'K0-8' },
    // ── K0 无此两表 ──────────────────────────────────────────────────────
    // `diffChecklist`：K0 源模板 10 张可见 sheet 里没有差异检查表（D0/F0 才有 4b）
    diffChecklist: null,
    // `diffSecurities`：证券差异专表仅 G0 有
    diffSecurities: null,
  })

/** 供 `cycleConfirmationMeta` 的 `sheets` 字段使用的槽位子集（剔除 `directory`） */
export const K0_CONFIRMATION_SHEETS: Readonly<
  Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>
> = Object.freeze(
  Object.fromEntries(
    Object.entries(K0_SHEET_REGISTRY).filter(([k]) => k !== 'directory'),
  ) as Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>,
)

/** 全部非 null 的定位值（= 源模板 10 张可见 sheet 的 tab 名，顺序同源模板） */
export const K0_SHEET_NAMES: readonly string[] = Object.freeze(
  Object.values(K0_SHEET_REGISTRY)
    .map((ref) => ref?.sheetName ?? null)
    .filter((n): n is string => !!n),
)

/** 取某槽位的 sheet 引用（无此表返回 null） */
export function k0SheetRef(slot: K0SheetKey): ConfirmationSheetRef | null {
  return K0_SHEET_REGISTRY[slot] ?? null
}

/**
 * 带笔误说明的展示 tooltip。
 * 无笔误时返回 base 原样 → 其余六枢纽不受影响（它们没有 `indexTypoNote`）。
 */
export function k0IndexTooltip(ref: ConfirmationSheetRef, baseTooltip: string): string {
  return ref.indexTypoNote ? `${baseTooltip}（${ref.indexTypoNote}）` : baseTooltip
}
