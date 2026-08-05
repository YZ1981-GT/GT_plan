/**
 * g0SheetRegistry — G0 投资循环函证：sheet「定位值 / 展示值」分离真源
 *
 * spec: g0-confirmation-source-alignment，Task 10（Requirement 5.4/5.5/6.1~6.5）
 * 裁决门 B（2026-08-04 用户裁决）= **定位用 tab 名 / 展示用底稿目录索引号 + tooltip 标注笔误**。
 *
 * 两个真源，各管一件事：
 *   - `sheetName`  ← 源模板真实 tab 名（`backend/wp_templates/G/G0 投资循环函证.xlsx`
 *                    的 `wb.sheetnames`，10 张全 visible，逐字含全/半角括号）。
 *                    **一切定位（render-config sheet 请求 / `?sheet=` 深链）只许用它。**
 *   - `indexLabel` ← 底稿目录 `底稿目录!F4:F12` 的索引号（**索引号唯一裁决者**）。
 *                    一切 UI 展示只许用它。
 *
 * 🔴 源模板三处 tab 名索引号笔误（是**源模板事实**，SHALL NOT 改写源 xlsx，
 *    也 SHALL NOT 静默改写展示值 —— 必须在 tooltip 里说明，见 R6.3）：
 *      `函证差异核对表G0-3（证券投资）`  tab 写 G0-3，目录为 G0-4（全角括号）
 *      `函证差异核对表G0-4(非证券投资)`  tab 写 G0-4，目录为 G0-5（半角括号）
 *      `函证程序舞弊风险评价表F0-8`      tab 写 F0-8（F 不是 G），目录为 G0-8
 *
 * 🔴 G0 是**单 `wp_code` 多 sheet 工作簿**：`wp_index` 实测只有 `G0` 与遗留族
 *    `G0-1..G0-5`（无 `G0-6`/`G0-7`/`G0-8`/`G0-3S`），且遗留族语义与底稿目录相反
 *    （`G0-4=投资函证差异调节` / `G0-5=投资函证替代程序`）→ 同工作簿内跳转必须走
 *    `?sheet=<sheetName>` 深链（`utils/normalizeSheetName.resolveSheetNameByDeepLink`），
 *    **不能走 `wp-id-by-code`**（会 404 或跳到语义相反的遗留底稿）。
 *
 * 交叉锁死：`__tests__/g0SheetRegistry.spec.ts`（Property 14 / 15）把本文件的 10 个
 * `sheetName` 与后端 `backend/tests/test_g0_source_template_facts.py::SHEET_NAMES`
 * （openpyxl 直读源 xlsx）以及 `backend/app/data/wp_code_overrides.json` 的三条
 * **全名键**三向比对。
 */

import type {
  ConfirmationSheetRef,
  ConfirmationSheetSlot,
} from '../confirmation/coordination/cycleConfirmationMeta'

/**
 * G0 注册表的键 = 11 个函证槽位 + `directory`（底稿目录本身）。
 *
 * `directory` 不属于 `CycleConfirmationMeta.sheets` 的槽位集合（它不是函证表），
 * 但必须登记 —— 否则「注册表 10 个 sheetName ↔ 源模板 10 张 sheet」这条双射断言
 * （Property 15）凑不齐，注册表就无法证明自己覆盖了整册工作簿。
 */
export type G0SheetKey = 'directory' | ConfirmationSheetSlot

/** 源模板 sheet 张数（全 visible）；Property 15 的数量锚点 */
export const G0_SOURCE_SHEET_COUNT = 10

function typoNote(tabIndex: string, directoryIndex: string): string {
  return `源模板 tab 名索引号为 ${tabIndex}，底稿目录为 ${directoryIndex}，以目录为准`
}

/**
 * G0 逐 sheet 声明（`sheetName` 为 null = G0 无此表，不得编造）。
 *
 * 顺序 = 源模板 tab 顺序（前 10 条），便于与 `wb.sheetnames` 逐位比对。
 */
export const G0_SHEET_REGISTRY: Readonly<Record<G0SheetKey, ConfirmationSheetRef | null>> =
  Object.freeze({
    directory: { sheetName: '底稿目录', indexLabel: '底稿目录' },
    program: { sheetName: '函证程序表G0A', indexLabel: 'G0A' },
    summary: { sheetName: '函证结果汇总表G0-1', indexLabel: 'G0-1' },
    entityVerify: { sheetName: '核实被函证单位信息G0-2', indexLabel: 'G0-2' },
    followup: { sheetName: '跟函函证过程控制G0-3', indexLabel: 'G0-3' },
    diffSecurities: {
      sheetName: '函证差异核对表G0-3（证券投资）',
      indexLabel: 'G0-4',
      indexTypoNote: typoNote('G0-3', 'G0-4'),
    },
    diff: {
      sheetName: '函证差异核对表G0-4(非证券投资)',
      indexLabel: 'G0-5',
      indexTypoNote: typoNote('G0-4', 'G0-5'),
    },
    altPrimary: { sheetName: '替代程序检查表G0-6', indexLabel: 'G0-6' },
    reliability: { sheetName: '邮件传真回函可靠性验证G0-7', indexLabel: 'G0-7' },
    fraud: {
      sheetName: '函证程序舞弊风险评价表F0-8',
      indexLabel: 'G0-8',
      indexTypoNote: typoNote('F0-8', 'G0-8'),
    },
    // ── G0 无此两表（源模板 10 张 sheet 里没有差异检查表与第二张替代程序表） ──
    diffChecklist: null,
    altSecondary: null,
  })

/** 供 `cycleConfirmationMeta` 的 `sheets` 字段使用的 11 槽位子集（剔除 `directory`） */
export const G0_CONFIRMATION_SHEETS: Readonly<
  Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>
> = Object.freeze(
  Object.fromEntries(
    Object.entries(G0_SHEET_REGISTRY).filter(([k]) => k !== 'directory'),
  ) as Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>,
)

/** 全部非 null 的定位值（= 源模板 10 张 sheet 的 tab 名，顺序同源模板） */
export const G0_SHEET_NAMES: readonly string[] = Object.freeze(
  Object.values(G0_SHEET_REGISTRY)
    .map((ref) => ref?.sheetName ?? null)
    .filter((n): n is string => !!n),
)

/** 取某槽位的 sheet 引用（无此表返回 null） */
export function g0SheetRef(slot: G0SheetKey): ConfirmationSheetRef | null {
  return G0_SHEET_REGISTRY[slot] ?? null
}

/**
 * 展示用索引号（含笔误说明的 tooltip 后缀）。
 * 无笔误时返回 base tooltip 原样 —— 六枢纽由此不受影响（它们没有 `indexTypoNote`）。
 */
export function g0IndexTooltip(ref: ConfirmationSheetRef, baseTooltip: string): string {
  return ref.indexTypoNote ? `${baseTooltip}（${ref.indexTypoNote}）` : baseTooltip
}
