import { GENERATED_IMPORT_EXPORT } from './cycleImportExportRegistry.generated'

/**
 * 各循环底稿支持导入导出的 sheet 清单（与后端 _f*_import_export.py 对齐）
 */
export interface CycleImportExportEntry {
  apiPrefix: string
  sheets: readonly string[]
}

/** 复合 sheet（一个底稿页含多个可导入区段） */
export interface CompoundImportExportGroup {
  baseSheet: string
  variants: readonly { label: string; sheet: string }[]
}

/**
 * 🔴 手工接管的 I/E 条目 —— **catalog 表达不了的传输层键**才放这里。
 *
 * 为什么不能全交给 catalog 生成（R4.6 零回归的关键）：
 *
 * | 类型 | 例 | catalog 有吗 |
 * |---|---|---|
 * | G0/H0 函证传输键 | `G0-3S` | ❌ 它是后端 `_SHEET_NAME_MAP` 的**键**，不是 `sheet_code` |
 * | F3/F4 复合变体键 | `F3-7-debit` / `F4-8-credit` | ❌ 存在于**后端 specs**，catalog 只登记基础 `sheet_code` |
 *
 * 实测 catalog 的 `f3` 只有 5 个 sheet（`F3-2`~`F3-6`），而后端 specs 有 16 个键；
 * `f4` catalog 4 个 vs 后端 24 个。纯 catalog 生成会**丢掉这些变体键**，
 * 导致既有导入导出下拉直接少掉一半区段。
 *
 * 新增条目前先问：这个 sheet 键在 catalog 的 `sheet_code` 里有吗？
 * 有 ⇒ 交给生成器，不要写在这里（否则 catalog 更新时此处会 stale）。
 *
 * 键集与生成器的 `MANUAL_PREFIXES` 双向锁死（守卫断言）。
 */
export const MANUAL_OVERRIDES: Record<string, CycleImportExportEntry> = {
  f1: {
    apiPrefix: 'f1',
    sheets: ['F1-2', 'F1-5', 'F1-6', 'F1-7', 'F1-7-credit', 'F1-7-post'],
  },
  /**
   * 键集 = 后端 `_f2_import_export._SUPPORTED_SHEETS`（真实 import 取值，21 个）：
   *   `set(_F2_SHEET_CONFIGS)`（18 个规则表）| `{'F2-1'}` | `set(_DISCLOSURE_SHEETS)`（2 个附注）
   *
   * 此前这里只有 18 个（恰好等于 `_F2_SHEET_CONFIGS`），漏了 `F2-1` 与两个附注键
   * ⇒ 附注页 `F2TabDisclosureListed/Soe` 已挂着下拉、后端也支持，但 registry 不认
   * ⇒ 批量场景（`scenario_registry`）枚举不到它们。
   *
   * 🔴 `F2-18` **不在**后端白名单，不要加：它是多区段分析表，无 I/E 适配器。
   *    （`F2TabOverallAnalysis.vue` 曾挂过，点击必 400，已删除并在该处留因由。）
   */
  f2: {
    apiPrefix: 'f2',
    sheets: [
      'F2-1',
      'F2-3', 'F2-4', 'F2-5', 'F2-6', 'F2-7', 'F2-8', 'F2-9', 'F2-10', 'F2-11', 'F2-12', 'F2-13',
      'F2-14', 'F2-19', 'F2-20', 'F2-29', 'F2-30', 'F2-31', 'F2-32',
      'F2-note-listed', 'F2-note-soe',
    ],
  },
  'f2-val': {
    apiPrefix: 'f2-val',
    sheets: [
      'F2-33', 'F2-34', 'F2-35',
      'F2-38', 'F2-39', 'F2-40',
      'F2-41', 'F2-42', 'F2-43', 'F2-44',
      'F2-47', 'F2-48', 'F2-49', 'F2-52',
    ],
  },
  'f2-spe': {
    apiPrefix: 'f2-spe',
    sheets: [
      'F2-55', 'F2-56', 'F2-57', 'F2-58',
      'F2-61', 'F2-62', 'F2-63', 'F2-64',
      'F2-65', 'F2-66', 'F2-67', 'F2-68', 'F2-69', 'F2-70', 'F2-71', 'F2-72',
    ],
  },
  'f2-st': {
    apiPrefix: 'f2-st',
    sheets: ['F2-24', 'F2-24-count', 'F2-25', 'F2-25-floor', 'F2-26', 'F2-26-after'],
  },
  f3: {
    apiPrefix: 'f3',
    sheets: [
      'F3-2', 'F3-3', 'F3-4', 'F3-5', 'F3-6',
      'F3-7-debit', 'F3-7-credit', 'F3-7-subsequent',
    ],
  },
  f4: {
    apiPrefix: 'f4',
    sheets: [
      'F4-2', 'F4-3', 'F4-5', 'F4-6',
      'F4-7-payment-window', 'F4-7-estimated-inbound', 'F4-7-unprocessed-invoice',
      'F4-7-subsequent-payment', 'F4-7-subsequent-increase',
      'F4-8-debit', 'F4-8-credit',
      'F4-9',
    ],
  },
  f5: {
    apiPrefix: 'f5',
    sheets: ['F5-2', 'F5-3', 'F5-4', 'F5-5', 'F5-6', 'F5-8'],
  },
  /**
   * 🔴 `sheets` 里的值是**后端 API 的 sheet key，不是 wp_code**（Task 4 勘查纠正）。
   *
   * `G0-3S` 看着像个不存在的底稿编码（`wp_index` 实测 G0 只有 `G0`/`G0-1..G0-5`，
   * 而源模板底稿目录里证券差异表的索引号是 `G0-4`），但它是
   * `_g0_confirmation_import_export._SHEET_NAME_MAP` 的**键**：
   *   `G0-3S` → tab 名 `函证差异核对表G0-3（证券投资）`
   *   `G0-6`  → tab 名 `替代程序检查表G0-6`
   * 前端 `CycleImportExportDropdown` 把它原样放进 `?sheet=` 查询串，后端据此查表。
   * → **改这里的字面量会让 G0 的三个导入导出端点全部 400**（`不支持的sheet`）。
   *
   * 与「展示索引号」是两个不同层：展示层由 `g0SheetRegistry` 的 `indexLabel` 负责
   * （G0-4/G0-5/G0-8 + tooltip 标注源模板笔误），此处是传输层键名，两者刻意不统一。
   *
   * 守卫 `cycleImportExportRegistry.spec.ts` 与后端 `_SHEET_NAME_MAP` 键集双向锁死。
   */
  g0: {
    apiPrefix: 'g0',
    sheets: ['G0-3S', 'G0-6'],
  },
  h0: {
    apiPrefix: 'h0',
    sheets: ['H0-5'],
  },
  /*
   * 🔴 j1 **有意不登记在此** —— 它是 GAP_REGISTRY 的显式豁免项，理由
   * 「specs 抽取失败，需人工核 item_id 后另补」。
   *
   * 2026-08-12 勘查已把「后端能力」这一半核实清楚（真实 import 取值）：
   *   · 三端点真实注册：`/api/workpapers/{wp_id}/j1/export-template|export-data|import-data`
   *     （`router_registry/workpaper.py` 有 include，非死工厂）
   *   · 合法键 12 个 = `_j1_import_export.SHEET_TYPES`
   *     {detail, accrual, allocation, general, non_monetary, severance,
   *      monthly, voucher, industry, adjustment}
   *     | {J1-note-listed, J1-note-soe}
   *   · 前端 `j1/core/J1TabDisclosureListed.vue` / `J1TabDisclosureSoe.vue`
   *     已挂 `CycleImportExportDropdown`（静态 api-prefix="j1"，自带前缀直拼 URL，
   *     故当前功能正常，不受 registry 缺席影响）
   *
   * 但**仍不能登记**，因为 registry 有一条更硬的真源约束：
   * 守卫「registry 每个 apiPrefix 都能在 catalog 找到条目」—— catalog 的 J1 条目
   * （`J1/J1`、`J1/J1-1`…`J1/J1-10`、`J1/J1A`）全都没有 `import_export.api_prefix`。
   * 要补 catalog 就得填 `item_id`，而 item_id 猜错 = 数据错位（比无数据更难发现），
   * 这正是 GAP_REGISTRY 当初豁免它的原因，也是本 spec 既定裁决「不猜 item_id」。
   *
   * ⇒ 登记 j1 的前置条件 = 人工核出 J1 各 sheet 的 item_id 并补 catalog。
   *   在那之前保持豁免；「后端已具备 + 前端已有入口」这半已记录在案，
   *   下一步只差 item_id 核实，不必再从零勘查。
   */
}

/**
 * 各循环底稿支持导入导出的 sheet 清单 —— **门面**。
 *
 * `GENERATED_IMPORT_EXPORT`（ACNR catalog 派生，49 个前缀）
 *   + `MANUAL_OVERRIDES`（传输层键，10 个前缀，后置覆盖）
 *
 * ## 为什么真源是 catalog 而不是手写
 *
 * 改造前这里只手写了 **10 个 key**，而 catalog 有 **59 个**启用 I/E 的
 * `api_prefix` ⇒ 49 个前缀「后端有能力、用户点不到」。
 *
 * catalog 同时是 `bulk_tab` 全链的路由真源
 * （`manifest_builder` → `list_export_sheets` → `list_import_export` → `catalog.list_sheets`），
 * 前端手抄一份等于平台内并存两套 I/E 目录，改一处忘一处。
 *
 * ⇒ 生成文件由 `backend/scripts/fix/gen_cycle_import_export_registry.py --apply` 产出，
 *   CI 用 `--check` 钉死它与 catalog 一致。
 *
 * ## 展开顺序为何**不**是安全关键（2026-08-10 变异检验修正）
 *
 * 初版注释写「顺序反了会让 catalog 基础码覆盖手工传输键 ⇒ 键丢失 ⇒ 端点 400」。
 * 变异检验证明那是**空操作**：生成器已把 `MANUAL_PREFIXES` 从产出中排除，
 * 两个对象的键集**互斥**，故 `{...A, ...B}` 与 `{...B, ...A}` 结果相同。
 *
 * ⇒ 真正的安全保障是**互斥不变量**，由守卫
 * `generated 与 MANUAL_OVERRIDES 键集互斥` 钉死。一旦某前缀两处都登记，
 * 顺序才会变成活的风险 —— 所以要守的是互斥，不是顺序。
 * 这里保持 MANUAL 后置只是表达意图（手工声明优先），不承担正确性。
 */
export const CYCLE_IMPORT_EXPORT: Record<string, CycleImportExportEntry> = {
  ...GENERATED_IMPORT_EXPORT,
  ...MANUAL_OVERRIDES,
}

export const COMPOUND_IMPORT_EXPORT: Record<string, CompoundImportExportGroup[]> = {
  'f2-st': [
    {
      baseSheet: 'F2-24',
      variants: [
        { label: '截止日核对', sheet: 'F2-24' },
        { label: '盘点日核对', sheet: 'F2-24-count' },
      ],
    },
    {
      baseSheet: 'F2-25',
      variants: [
        { label: '记录→实物', sheet: 'F2-25' },
        { label: '实物→记录', sheet: 'F2-25-floor' },
      ],
    },
    {
      baseSheet: 'F2-26',
      variants: [
        { label: '日后倒推', sheet: 'F2-26-after' },
        { label: '日前顺推', sheet: 'F2-26' },
      ],
    },
  ],
  f4: [
    {
      baseSheet: 'F4-7',
      variants: [
        { label: '期后付款天数', sheet: 'F4-7-payment-window' },
        { label: '暂估入库', sheet: 'F4-7-estimated-inbound' },
        { label: '未处理发票', sheet: 'F4-7-unprocessed-invoice' },
        { label: '期后付款', sheet: 'F4-7-subsequent-payment' },
        { label: '期后增加', sheet: 'F4-7-subsequent-increase' },
      ],
    },
    {
      baseSheet: 'F4-8',
      variants: [
        { label: '借方检查', sheet: 'F4-8-debit' },
        { label: '贷方检查', sheet: 'F4-8-credit' },
      ],
    },
  ],
  f3: [
    {
      baseSheet: 'F3-7',
      variants: [
        { label: '本期借方', sheet: 'F3-7-debit' },
        { label: '本期贷方', sheet: 'F3-7-credit' },
        { label: '日后借方', sheet: 'F3-7-subsequent' },
      ],
    },
  ],
}

export function isImportExportSheet(cycleKey: keyof typeof CYCLE_IMPORT_EXPORT, sheetCode: string): boolean {
  const entry = CYCLE_IMPORT_EXPORT[cycleKey]
  if (!entry) return false
  if (entry.sheets.includes(sheetCode)) return true
  return (COMPOUND_IMPORT_EXPORT[cycleKey] ?? []).some((g) => g.baseSheet === sheetCode)
}

export function resolveImportExportSheet(
  cycleKey: keyof typeof CYCLE_IMPORT_EXPORT,
  sheetCode: string,
): { apiPrefix: string; sheet: string; variants?: CompoundImportExportGroup['variants'] } | null {
  const entry = CYCLE_IMPORT_EXPORT[cycleKey]
  if (!entry) return null
  const group = (COMPOUND_IMPORT_EXPORT[cycleKey] ?? []).find((g) => g.baseSheet === sheetCode)
  if (group) {
    return { apiPrefix: entry.apiPrefix, sheet: group.variants[0].sheet, variants: group.variants }
  }
  if (entry.sheets.includes(sheetCode)) {
    return { apiPrefix: entry.apiPrefix, sheet: sheetCode }
  }
  return null
}

export function getImportExportConfig(cycleKey: keyof typeof CYCLE_IMPORT_EXPORT): CycleImportExportEntry | undefined {
  return CYCLE_IMPORT_EXPORT[cycleKey]
}
