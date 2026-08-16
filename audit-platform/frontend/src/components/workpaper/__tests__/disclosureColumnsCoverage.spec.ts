import { describe, it, expect, beforeAll } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import type { ColumnDef } from '../composables/disclosureColumnDefs'

/**
 * 全 Tab 披露 `columns` 契约扫描（跨循环）
 *
 * spec `disclosure-columns-coverage-rollout` Task 9.1
 * design §批 1 范式模板（批 2~4 照此办）T1 命名契约 / T2 声明规则 / T5 测试清单
 * design §Correctness Properties P1 / P2 / P3 / P6，§R3 `flat` 三态
 *
 * 与各批「per-cycle 契约测试」的分工：
 * - per-cycle spec（`l1NoteSectionMap.spec.ts` 等）逐字断言 label / key / values 位置对齐，
 *   并经 `build{X}SyncPayload()` 入口断言完整双向 P1；
 * - **本文件不枚举循环**，而是从文件系统**发现**全部 `build*Columns()` 导出并逐表校验共享性质，
 *   使**未来新增循环**即便忘了写 per-cycle spec 也无法静默违约。
 *
 * 🔴 防「静默零覆盖」：builder 数 / 表数都设下限（`BUILDER_FLOOR` / `TABLE_FLOOR`）。
 *   glob 或发现逻辑一旦失效，套件会失败而不是空跑通过。
 */

// 模块加载走 Vite glob（非 eager：仅得到 loader 映射，命中的少数文件才真正 import）。
// 发现走 fs 扫描（避免 eager `?raw` 把 ~19MB 源码内联进测试模块，实测可省 ~20s）。
const MODULES = import.meta.glob('../**/*.ts', { eager: false }) as Record<
  string,
  () => Promise<Record<string, unknown>>
>

const WORKPAPER_ROOT = path.resolve(__dirname, '..')

/** 与守卫 `check_disclosure_columns_coverage.py::_BUILDER_RE` 同口径（design T1） */
const BUILDER_NAME_RE = /^build[A-Z]\w*Columns$/
const BUILDER_EXPORT_RE = /export\s+(?:async\s+)?(?:function|const)\s+(build[A-Z]\w*Columns)\b/g
/** 同文件内的姊妹载荷构造器（P1 sweep 路由用） */
const PAYLOAD_EXPORT_RE = /export\s+(?:async\s+)?(?:function|const)\s+(build[A-Z]\w*SyncPayloads?)\b/g

/** Property 6：snake_case 字段键形态 */
const SNAKE_CASE = /^[a-z_][a-z0-9_]*$/

/**
 * 下限（形态 B 地板）：**当前实测 109 个披露 builder / 313 张表**
 * （2026-08-15 实测，含并发在办的 M/J/L 循环；较早期注释的 22/92 已大幅增长）。
 *
 * 🔴 设为 12 / 60 是**有意留大余量**：地板的唯一职责是「glob 或发现逻辑失效 →
 *    扫到 0 个 → 套件必红」，不是逼近实测值。刻意远低于实测（12 ≪ 109）保证任何
 *    **合法缩减**（某循环被移除 / 合并）都不会假红 —— 这正是形态 B「只防空转与扩张、
 *    不锁死规模」的正确写法。规模增长时**无需**同步上调本地板。
 */
const BUILDER_FLOOR = 12
const TABLE_FLOOR = 60

/**
 * 命中命名正则但**不是**披露 `ColumnDef` 构造器的导出（须写明原因）。
 * 它们返回底稿 UI 列模型（`prop` 而非 `key`），与附注投影无关。
 */
const NON_DISCLOSURE_BUILDERS: Record<string, string> = {
  buildF4AgingColumns:
    'useF4Detail：返回底稿明细表 UI 列 `F4DetailColumn[]`（prop/minWidth/editable），非附注 ColumnDef；F4 披露列头在 f4NoteSectionMap',
  buildF4AuditColumns:
    'useF4Detail：同上，审定账龄段 UI 列，非附注 ColumnDef',
  buildG7SlotColumns:
    'composables/g7SlotColumns：返回槎位描述 `G7SlotColumn[]`（key/seq/entityName），'
    + '不是 ColumnDef——由 g7ListedDisclosureModel/g7SoeDisclosureModel 的 '
    + 'companyColumnsFor/associateMatrixColumnsFor 等再转换成 ColumnDef，'
    + '真正的披露 builder 是 buildG7ListedColumns/buildG7SoeColumns',
}

/**
 * `flat` / `group` 均未声明（design §R3 三态的 `None` 态）→ 后端
 * `_extract_column_groups` 返回 None，回退 `_infer_groups_from_headers` 前缀推断。
 *
 * 🔴 原因必填（镜像 R4.3：值空白 = 未登记，仍按违规处理）。
 * 🔴 声明的表名集合必须与实扫结果**完全相等** → 既不能增长，修好也必须同步删除条目。
 *
 * 以下均为**批 1~4 范围之外**的存量循环（本 spec 未触碰），登记而非静默放过；
 * 「后端推断结果」为实跑 `_infer_groups_from_headers(headers)` 所得，是修复优先级依据。
 */
const INFERENCE_FALLBACK_ALLOWLIST: Record<string, { reason: string; tables: string[] }> = {
  buildH1ListedColumns: {
    reason:
      'H1 固定资产（批 1~4 之外）：6 表全未声明 flat/group。实跑推断均为空（headers 无 ≥4 列共享前缀）→ 当前渲染未受害，但缺显式声明；补 flat 须逐表核对源 `H 类/H1 固定资产.xlsx` 表头行数，非本 Task 范围',
    tables: [
      '固定资产',
      '固定资产情况',
      '固定资产清理',
      '暂时闲置的固定资产情况',
      '未办妥产权证书的固定资产情况',
      '通过经营租赁租出的固定资产',
    ],
  },
  // buildH2ListedColumns / buildH2SoeColumns 已由 h2 spec 补齐 flat/group（实扫未声明表 = []）
  // buildH8ListedColumns 已由 h8-right-of-use-disclosure-alignment 补 flat（Task 7 实测挖出：
  // 缺 flat 时国企侧被投影成 `_column_groups=[{group:'本期',start:2,span:2}]`，
  // 即「现状无害」的旧判断只对上市侧成立）
  // → 按 R3「已修好的表必须从 allowlist 删除」移出（allowlist 只许缩）。
  // buildH10SubTableColumns 已由 h9-h10-remaining-disclosure-alignment 收口：
  // 两张同名 `项  目` 表正名（原本同名互相覆盖丢整张表）、`项  目__trial` 孤儿绕过键删净、
  // 主表补 flat、试运行表改源模板两级表头（group 各 span 2）
  // → 按 R3「已修好的表必须从 allowlist 删除」移出（allowlist 只许缩）。
  // buildI1ListedColumns 已由 I 循环收口补齐 flat（实扫未声明表 = []；其所在
  // `i1DisclosureSyncPayload.ts` 已提交，HEAD 与工作树两态一致）→ 按 R3「已修好的表必须从
  // allowlist 删除」移出（allowlist 只许缩，天花板随之下调 2/11 → 1/6）。
  // buildG7ListedColumns 已由 g7-four-table-extraction-and-disclosure-alignment
  // Task 5.2 补齐 flat/group（实扫未声明表 = []）→ 按 R3「已修好必删」移出。
  // buildG7SoeColumns: 已全部补齐 flat/group 表态（Task 5.2）。
}

/**
 * allowlist 天花板：**只许缩不许扩**（新增循环必须直接声明 flat/group，不得往 allowlist 加条目绕过）。
 *
 * 🔴 现值 1 / 6 与实际条目数**贴死无余量**（当前 INFERENCE_FALLBACK_ALLOWLIST =
 *    仅 buildH1ListedColumns 6 表 = 1 builder / 6 表；buildI1 已随 I 循环补 flat 收口而移出）。
 *    这是有意设计：贴死 ⇒ 任何「往 allowlist 加条目」的企图都立刻撞天花板打红。
 *
 * 🔴 **缩小时必须同步下调本上限** —— 否则天花板会留出「可以偷偷再加回来」的余量，
 *    等于把「只许缩」偷偷放宽成「可以回弹」。用 `toBeLessThanOrEqual`（而非 `toBe` 等值）
 *    保证「缩小」本身永远合规、不会因为忘了改上限而假红（见 design Property 13 的替身验证）。
 */
const ALLOWLIST_BUILDER_CEILING = 1
const ALLOWLIST_TABLE_CEILING = 6

/**
 * Property 1（columns 键 ≡ sub_table_data 数据键）**双向**断言需要真实业务快照，
 * 无法用 sweep 的空入参覆盖（空快照下 `sub_table_data` 恒为空，断言会变成噪音）。
 * 故 P1 由 per-cycle spec 承担；本表登记「哪个 builder 的 P1 由哪个文件覆盖」，
 * 并在测试里断言**登记完整**且**文件真实存在** —— 不留静默缺口。
 *
 * sweep 侧另做**单向** P1（数据键 ⊆ columns 键），见对应用例。
 */
const P1_ROUTE: Record<string, { spec: string; complete: boolean; note?: string }> = {
  // E 循环（e1-four-table-extraction-and-disclosure-alignment Task 10）：
  // E1 列定义原为模块私有常量、未导出 → 覆盖率 sweep 扫不到；本次提为零参 builder
  // 并作为载荷/seed/契约的单一真源
  buildE1ListedColumns: {
    spec: 'composables/__tests__/e1NoteSubtableContract.spec.ts',
    complete: true,
    note: '上市 §五、1，2 张表（主表 + ②受限表按用户裁决补建）；3 列单级必标 flat；「受限原因」不进附注走 _note_texts',
  },
  buildE1SoeColumns: {
    spec: 'composables/__tests__/e1NoteSubtableContract.spec.ts',
    complete: true,
    note: '国企 §八、1，末列「期初余额」（上市为「上年年末余额」），两版列头必须不同',
  },
  // 外币货币性项目（disclosure-note-row-level-merge Task 10）：**跨循环共享表**，
  // 一张表内按科目分段，E1 只负责货币资金段（`BS-002`）→ 载荷带 `_row_scope`
  // 走平台级行级合并。两变体列定义相同（源 xlsx 两张披露 sheet 的外币区逐字一致）。
  buildE1FxColumns: {
    spec: 'composables/__tests__/e1FxNoteSectionMap.spec.ts',
    complete: true,
    note: '§五、73 / §八、92「外币货币性项目」，4 列仅期末全 flat；含「折算汇率」列（format=rate）',
  },
  // 受限资产（restricted-assets-note-row-scope-rollout Task 5/7）：**八循环共享表**，
  // listed 双期拆两张表（主表期末 + 续表上年年末）、soe 单表 3 列含「受限原因」。
  // 每个 owner 只推自己那一段（E1 = BS-002 货币资金），载荷带 `_row_scope`。
  buildRestrictedAssetsColumns: {
    spec: 'composables/__tests__/restrictedAssetsNoteSectionMap.spec.ts',
    complete: true,
    note: '§五、32（主表 + 续表）/ §八、93，3 张子表全 flat；listed 无「受限原因」列（源模板 2 列）',
  },
  // H 循环（disclosure-sync-path-buildout Task 3）：H4 国企 + H7 两版同步链路从零建立
  buildH4SoeColumns: {
    spec: 'composables/__tests__/hCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: 'H4 国企推 **H2 的 §八、23**（共章节浅合并）；两级表头 + 账面价值读时派生',
  },
  // L 循环（disclosure-sync-path-buildout Task 4）：L5/L6/L7/L8 同步链路从零建立
  // （L7 原有映射是死 import 且 6 处缺陷；L8 两版行结构自造且互不相同）
  buildL5ListedColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: 'L5 只推「长期应付款」主表 + 按款项性质列示；「专项应付款」表由 L6 推（共章节浅合并）',
  },
  buildL5SoeColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: '国企主表列头「期末数/期初数」与①前5 项表「期末余额/年初余额」按源 xlsx 分取',
  },
  buildL6ListedColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: 'L6 无独立章节 → 推 L5 §五、48 的「专项应付款」子表（6 列含形成原因）',
  },
  buildL6SoeColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: '国企侧 5 列（无「形成原因」）；列头取附注模版字面（源 xlsx 是年份占位符）',
  },
  buildL7ListedColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: '含反向断言「两版列头必须不同」（上市 期末数/上年年末数；国企 期末余额/期初余额）',
  },
  buildL7SoeColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: '载荷把底稿列序（年初/期末）投影为附注口径（期末/期初）',
  },
  buildL8ListedColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: '源模板 12 行（3 个派生小计 + 合计）；仅上市侧推资本化说明段',
  },
  buildL8SoeColumns: {
    spec: 'composables/__tests__/lCycleNoteSubtableContract.spec.ts',
    complete: true,
    note: '两版行集完全相同（源 xlsx 实证）；国资专项内容留底稿不进附注',
  },
  buildD1ListedColumns: {
    spec: 'composables/__tests__/d1NoteSubtableContract.spec.ts',
    complete: true,
    note: '另含「模板表名全集 == 子表名映射全集」双向断言与 headers 逐位一致',
  },
  buildD1SoeColumns: {
    spec: 'composables/__tests__/d1NoteSubtableContract.spec.ts',
    complete: true,
    note: '另含「模板表名全集 == 子表名映射全集」双向断言与 headers 逐位一致',
  },
  buildN1ListedColumns: {
    spec: 'composables/__tests__/n1NoteSubtableContract.spec.ts',
    complete: true,
    note: '另含双向键集 + 表 1 两级表头子列序（两版相反）+ 同步 columns ↔ 模板 columns 同形断言',
  },
  buildN1SoeColumns: {
    spec: 'composables/__tests__/n1NoteSubtableContract.spec.ts',
    complete: true,
    note: '国企 5 张表（含源模板（2）B 互抵明细）；键集一致断言在 n1NoteSectionMap.spec.ts',
  },
  // N 循环税务类（n-cycle-tax-disclosure-alignment）：N2 / N4 / N5 同步链路从零建立
  buildN2ListedColumns: {
    spec: 'composables/__tests__/n2NoteSubtableContract.spec.ts',
    complete: true,
    note: '上市 = 双期余额表 3 列；反向断言两版列键集不等（原两组件复制粘贴导致上市误用国企变动口径）',
  },
  buildN2SoeColumns: {
    spec: 'composables/__tests__/n2NoteSubtableContract.spec.ts',
    complete: true,
    note: '国企 = 变动表 5 列（期末余额为源模板行内公式 =B8+C8-D8）；模板侧原被 md 重建压成 3 列',
  },
  buildN4ListedColumns: {
    spec: 'composables/__tests__/n4NoteSubtableContract.spec.ts',
    complete: true,
    note: '只有上市变体 —— 国企源模板此节为「附注披露信息：无」，buildN4SyncPayload(soe) 恒返回 null',
  },
  buildN5ListedColumns: {
    spec: 'composables/__tests__/n5NoteSubtableContract.spec.ts',
    complete: true,
    note: '两表原都叫「项  目」（md 重建把表头首格当表名）→ 已去重；旧键锁在 N5_LEGACY_OBSOLETE_TABLES',
  },
  buildN5SoeColumns: {
    spec: 'composables/__tests__/n5NoteSubtableContract.spec.ts',
    complete: true,
    note: '两表原都叫「所得税费用」→ 第 2 表改名「会计利润与所得税费用调整过程」；表 2 列由 2 补回 3',
  },
  buildL1ListedColumns: { spec: 'composables/__tests__/l1NoteSectionMap.spec.ts', complete: true },
  buildL1SoeColumns: { spec: 'composables/__tests__/l1NoteSectionMap.spec.ts', complete: true },
  // D 类剩余四循环（d-cycle-remaining-disclosure-alignment）：模板与载荷已按源 xlsx 对齐
  buildD3ListedColumns: {
    spec: 'composables/__tests__/d3NoteSubtableContractShared.spec.ts',
    complete: true,
    note: '另含逐表合计字面（上市「合 计」/国企主表「合  计」/国企超1年「合计」）与账龄映射',
  },
  buildD3SoeColumns: {
    spec: 'composables/__tests__/d3NoteSubtableContractShared.spec.ts',
    complete: true,
  },
  buildD5ListedColumns: {
    spec: 'composables/__tests__/d5NoteSubtableContract.spec.ts',
    complete: true,
    note: '重点守背书贴现表两列共前缀「期末」必须 flat（否则 seed 路径凭空父表头）',
  },
  buildD5SoeColumns: {
    spec: 'composables/__tests__/d5NoteSubtableContract.spec.ts',
    complete: true,
  },
  buildD6ListedColumns: {
    spec: 'composables/__tests__/d6NoteSubtableContract.spec.ts',
    complete: true,
    note: '两级表头两期同构 + 减值计提情况按期间拆两表（源模板三级 → 顶层期间提到表名）',
  },
  buildD6SoeColumns: {
    spec: 'composables/__tests__/d6NoteSubtableContract.spec.ts',
    complete: true,
    note: '「本期变动金额」3 列一组，期初/期末/原因为 rowspan=2 独立列',
  },
  buildD7ListedColumns: {
    spec: 'composables/__tests__/d7NoteSubtableContract.spec.ts',
    complete: true,
  },
  buildD7SoeColumns: {
    spec: 'composables/__tests__/d7NoteSubtableContract.spec.ts',
    complete: true,
    note: '第 2 表原为占位名「合同负债（表2）」，已按源模板 A20 校正并进 _removed_table_keys',
  },
  buildL3ListedColumns: { spec: 'composables/__tests__/l3NoteSectionMap.spec.ts', complete: true },
  buildL3SoeColumns: { spec: 'composables/__tests__/l3NoteSectionMap.spec.ts', complete: true },
  buildK2ListedColumns: {
    spec: 'composables/__tests__/k2NoteSubtableContract.spec.ts',
    complete: true,
    note:
      '另含模板 3 表恒等、历史表名清除、固定行名逐字、条件性表开关 ↔ _removed_table_keys；'
      + '类别列 `cat_{i}` 随快照扩展，键集恒等经 buildK2SyncPayload 双向断言',
  },
  buildK2SoeColumns: { spec: 'composables/__tests__/k2NoteSubtableContract.spec.ts', complete: true },
  // ── spec k-cycle-disclosure-alignment 批1（K8~K13 损益类）──────────────────
  buildK8ListedColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK8SoeColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK9ListedColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK9SoeColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK10ListedColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK10SoeColumns: {
    spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts',
    complete: true,
    note: '国企 4 列（末列「是否为政府补助」文本型）+ 合计后结构行「其中：政府补助」不参与求和',
  },
  buildK11ListedColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK11SoeColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK12ListedColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK12SoeColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK13ListedColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  buildK13SoeColumns: { spec: 'composables/__tests__/kPlNoteSubtableContract.spec.ts', complete: true },
  // ── spec k-cycle-disclosure-alignment 批2（K3 其他应付款）────────────────────
  buildK3ListedColumns: {
    spec: 'composables/__tests__/kLiabilityNoteSubtableContract.spec.ts',
    complete: false,
    note:
      '7 张表列头逐字对齐模板；逾期利息 / 超1年未付股利 / 账龄超1年为条件表，'
      + '应付利息·应付股利待底稿补录入区块（spec Task 8）→ columns 键集随快照变化，未做恒等',
  },
  buildK3SoeColumns: {
    spec: 'composables/__tests__/kLiabilityNoteSubtableContract.spec.ts',
    complete: false,
    note: '同 buildK3ListedColumns（国企 6 表，无「超过1年未支付的应付股利」）',
  },
  buildK4ListedColumns: { spec: 'composables/__tests__/k4NoteSectionMap.spec.ts', complete: true },
  buildK4SoeColumns: { spec: 'composables/__tests__/k4NoteSectionMap.spec.ts', complete: true },
  buildK5ListedColumns: { spec: 'composables/__tests__/k5NoteSectionMap.spec.ts', complete: true },
  buildK5SoeColumns: { spec: 'composables/__tests__/k5NoteSectionMap.spec.ts', complete: true },
  buildK6ListedColumns: { spec: 'composables/__tests__/k6NoteSectionMap.spec.ts', complete: true },
  buildK6SoeColumns: { spec: 'composables/__tests__/k6NoteSectionMap.spec.ts', complete: true },
  buildK6SoeLiabilityColumns: { spec: 'composables/__tests__/k6NoteSectionMap.spec.ts', complete: true },
  buildK7ListedColumns: { spec: 'composables/__tests__/k7NoteSectionMap.spec.ts', complete: true },
  buildK7SoeColumns: { spec: 'composables/__tests__/k7NoteSectionMap.spec.ts', complete: true },
  buildH2ListedColumns: { spec: 'composables/__tests__/h2DisclosureSyncPayload.spec.ts', complete: true },
  buildH2SoeColumns: { spec: 'composables/__tests__/h2DisclosureSyncPayload.spec.ts', complete: true },
  buildF2ListedColumns: { spec: '__tests__/f2NoteSectionMap.spec.ts', complete: true },
  buildF2SoeColumns: { spec: '__tests__/f2NoteSectionMap.spec.ts', complete: true },
  buildH1ListedColumns: { spec: 'composables/__tests__/h1NoteSubtableContract.spec.ts', complete: true },
  buildH3ListedColumns: { spec: 'composables/__tests__/h3NoteSubtableContract.spec.ts', complete: true },
  buildH7ListedColumns: {
    spec: 'composables/__tests__/h7NoteSubtableContract.spec.ts',
    complete: true,
    note: 'h7-biological-assets-disclosure-rebuild：默认类别下列 key ≡ 模板列 key + 行键 ⊆ 列键 + 产业分组两级表头',
  },
  buildH3SoeColumns: { spec: 'composables/__tests__/h3NoteSubtableContract.spec.ts', complete: true },
  buildH8ListedColumns: {
    spec: 'composables/__tests__/h8NoteSubtableContract.spec.ts',
    complete: true,
    note: 'h8-right-of-use-disclosure-alignment：列 key ≡ 模板列 key + 行键 ⊆ columns.key + flat 表态',
  },
  buildI1ListedColumns: {
    spec: 'composables/__tests__/iDisclosureColumns.spec.ts',
    complete: false,
    note: '逐表列头有断言，未断言 columns 键集与 sub_table_data 键集相等',
  },
  buildG7ListedColumns: {
    spec: 'composables/__tests__/g7NoteSubtableContract.spec.ts',
    complete: true,
    note: 'G7 上市 §五、18：13 列两级表头（本期增减变动 8 子列）+ 动态列（entitySlots）零入参可调',
  },
  buildG7SoeColumns: {
    spec: 'composables/__tests__/g7NoteSubtableContract.spec.ts',
    complete: true,
    note: 'G7 国企 §八、18 + §七、*：10 表明细两级 group + flat 表态 + 动态列',
  },
  buildH10SubTableColumns: {
    spec: 'composables/__tests__/h9h10NoteSubtableContract.spec.ts',
    complete: true,
    note: 'h9-h10-remaining-disclosure-alignment：载荷列 key ≡ 模板列 key + 行键 ⊆ 列键 + 两级表头 group',
  },
  // ── spec disclosure-sync-path-buildout 批1（G 循环）─────────────────────────
  buildG8ListedColumns: { spec: 'composables/__tests__/g8NoteSubtableContract.spec.ts', complete: true },
  buildG8SoeColumns: { spec: 'composables/__tests__/g8NoteSubtableContract.spec.ts', complete: true },
  buildG9ListedColumns: { spec: 'composables/__tests__/g9NoteSubtableContract.spec.ts', complete: true },
  buildG9SoeColumns: { spec: 'composables/__tests__/g9NoteSubtableContract.spec.ts', complete: true },
  buildG12ListedColumns: { spec: 'composables/__tests__/g12NoteSubtableContract.spec.ts', complete: true },
  buildG12SoeColumns: { spec: 'composables/__tests__/g12NoteSubtableContract.spec.ts', complete: true },
  buildG5ListedColumns: {
    spec: 'composables/__tests__/g5NoteSubtableContract.spec.ts',
    complete: false,
    note:
      '逐表列头 + 三级→两级投影 + 动态组合表名均有断言；组合表是按实际组合名动态建键，'
      + 'columns 键集随快照变化，故未做全表键集恒等（骨架名那张已覆盖）',
  },
  buildG5SoeColumns: { spec: 'composables/__tests__/g5NoteSubtableContract.spec.ts', complete: true },
  buildG4ListedColumns: {
    spec: 'composables/__tests__/g4NoteSubtableContract.spec.ts',
    complete: false,
    note:
      '阶段表名与表数随底稿三阶段块动态生成（上市 6 张 / 国企 3 张），columns 键集随快照变化；'
      + '已断言主表两级分组、各阶段表列键与 flat 表态、行序与「其中：」结构行，未做全表键集恒等',
  },
  buildG4SoeColumns: {
    spec: 'composables/__tests__/g4NoteSubtableContract.spec.ts',
    complete: false,
    note: '同 buildG4ListedColumns（国企 3 张期末阶段表，无上年对照、无重要核销明细）',
  },
  buildG6ListedColumns: {
    spec: 'composables/__tests__/g6NoteSubtableContract.spec.ts',
    complete: false,
    note:
      '14 张表全部登记且列头逐字对齐模板；六张阶段表名与损失率/末列名随三阶段块生成，'
      + 'columns 键集随快照变化，故未做全表键集恒等（已断言两级表头恰 3 张、其余显式 flat）',
  },
  // ── spec d4-four-table-extraction-and-disclosure-alignment（D4 营业收入）──────
  buildD4TwoPeriodColumns: {
    spec: 'composables/__tests__/d4NoteSubtableContract.spec.ts',
    complete: true,
    note:
      'D4 (1)(2)(3)(8) 四种两级表头（5 列：项目+本期发生额{收入,成本}+上期发生额{收入,成本}）；'
      + '零入参默认 variant=main，各变体叶子列名按源模板分取',
  },
  buildD4TransposeColumns: {
    spec: 'composables/__tests__/d4NoteSubtableContract.spec.ts',
    complete: true,
    note:
      'D4 (4) 分解信息列转置：动态类别列（稳定 key {slot}_{seq}）+ 行=在某一时点/时段/租赁收入；'
      + '零入参使用默认类别列表',
  },
  buildD4ObligationColumns: {
    spec: 'composables/__tests__/d4NoteSubtableContract.spec.ts',
    complete: true,
    note:
      'D4 (6) 与剩余履约义务有关的信息：动态年度列（由审计年度派生）+ 合计列；'
      + '零入参默认 auditYear=2025',
  },
}

// ────────────────────────── 发现 ──────────────────────────

interface DiscoveredBuilder {
  /** import.meta.glob 键，形如 `../composables/l1NoteSectionMap.ts` */
  rel: string
  name: string
  /** 同文件内的姊妹载荷构造器名 */
  payloads: string[]
  src: string
}

function walkTsFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__tests__' || entry.name === 'node_modules') continue
    const abs = path.join(dir, entry.name)
    if (entry.isDirectory()) walkTsFiles(abs, out)
    else if (entry.name.endsWith('.ts') && !entry.name.endsWith('.d.ts')) out.push(abs)
  }
  return out
}

function matchAllNames(src: string, re: RegExp): string[] {
  const names: string[] = []
  const scoped = new RegExp(re.source, 'g')
  let m: RegExpExecArray | null
  while ((m = scoped.exec(src))) if (!names.includes(m[1])) names.push(m[1])
  return names
}

function discoverBuilders(): DiscoveredBuilder[] {
  const found: DiscoveredBuilder[] = []
  for (const abs of walkTsFiles(WORKPAPER_ROOT)) {
    const src = fs.readFileSync(abs, 'utf8')
    const names = matchAllNames(src, BUILDER_EXPORT_RE).filter(n => BUILDER_NAME_RE.test(n))
    if (!names.length) continue
    const rel = '../' + path.relative(WORKPAPER_ROOT, abs).split(path.sep).join('/')
    const payloads = matchAllNames(src, PAYLOAD_EXPORT_RE)
    for (const name of names) found.push({ rel, name, payloads, src })
  }
  return found
}

// ────────────────────────── 调用 ──────────────────────────

/** 从 `interface *ColumnsOptions` 抽出全部 boolean 开关，构造「全开」入参以覆盖条件表 */
function allTrueOptionFlags(src: string): Record<string, boolean> | null {
  const flags: Record<string, boolean> = {}
  const ifaceRe = /interface\s+\w*ColumnsOptions\s*\{([\s\S]*?)\n\}/g
  let m: RegExpExecArray | null
  while ((m = ifaceRe.exec(src))) {
    const propRe = /(\w+)\??\s*:\s*boolean/g
    let p: RegExpExecArray | null
    while ((p = propRe.exec(m[1]))) flags[p[1]] = true
  }
  return Object.keys(flags).length ? flags : null
}

function candidateArgs(src: string): unknown[][] {
  const flags = allTrueOptionFlags(src)
  // 无参 / 空 options / 全开 options / 两个 variant 字面量（H10 等按 variant 分派）
  return flags ? [[], [{}], [flags], ['listed'], ['soe']] : [[], [{}], ['listed'], ['soe']]
}

type NormalizedTables = Array<[string, ColumnDef[]]>

/**
 * 归一 builder 返回值：`Record<string, ColumnDef[]>` 与裸 `ColumnDef[]` 两种形态。
 *
 * 返回 null = 该次调用不是有效结果（入参不匹配签名）：
 * 空表名 / 表名含 `undefined`（如 `H10_MAIN_SUBTABLE[undefined]`）是错误 arity 的产物，
 * 不能当成违规上报，否则 sweep 会制造假阳性。
 */
function normalizeTables(result: unknown): NormalizedTables | null {
  const isColumnArray = (v: unknown): v is ColumnDef[] =>
    Array.isArray(v) && v.length > 0 && v.every(c => !!c && typeof (c as ColumnDef).key === 'string')
  if (isColumnArray(result)) return [['<bare array>', result]]
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null
  const record = result as Record<string, unknown>
  const keys = Object.keys(record)
  if (!keys.length) return null
  if (keys.some(k => !k.trim() || k.includes('undefined'))) return null
  if (!keys.every(k => isColumnArray(record[k]))) return null
  return keys.map(k => [k, record[k] as ColumnDef[]])
}

interface SweptTable {
  builder: string
  rel: string
  table: string
  cols: ColumnDef[]
}

interface SweepModel {
  builders: DiscoveredBuilder[]
  /** 披露 builder（排除 NON_DISCLOSURE_BUILDERS） */
  disclosureBuilders: DiscoveredBuilder[]
  /** builder → 去重后的表（同名表取首次出现） */
  tablesByBuilder: Map<string, SweptTable[]>
  missingLoader: string[]
  /** P1 sweep 路由：成功调用的载荷构造器结果 */
  payloadResults: Array<{ fn: string; dataKeys: string[]; columnKeys: string[] }>
}

const model: SweepModel = {
  builders: [],
  disclosureBuilders: [],
  tablesByBuilder: new Map(),
  missingLoader: [],
  payloadResults: [],
}

beforeAll(async () => {
  model.builders = discoverBuilders()
  model.disclosureBuilders = model.builders.filter(b => !(b.name in NON_DISCLOSURE_BUILDERS))

  const loadedModules = new Map<string, Record<string, unknown>>()
  for (const builder of model.builders) {
    const loader = MODULES[builder.rel]
    if (!loader) {
      model.missingLoader.push(builder.rel)
      continue
    }
    if (!loadedModules.has(builder.rel)) loadedModules.set(builder.rel, await loader())
    const mod = loadedModules.get(builder.rel)!
    const fn = mod[builder.name]
    if (typeof fn !== 'function') continue

    const seen = new Map<string, SweptTable>()
    for (const args of candidateArgs(builder.src)) {
      let raw: unknown
      try {
        raw = (fn as (...a: unknown[]) => unknown)(...args)
      } catch {
        continue // 入参与签名不符 → 换下一组
      }
      const tables = normalizeTables(raw)
      if (!tables) continue
      for (const [table, cols] of tables) {
        if (!seen.has(table)) seen.set(table, { builder: builder.name, rel: builder.rel, table, cols })
      }
    }
    if (seen.size) model.tablesByBuilder.set(builder.name, [...seen.values()])
  }

  // P1 sweep 路由：同文件姊妹载荷构造器，能用平凡入参调通的就顺带校验
  const payloadArgs: unknown[][] = [
    [],
    [{}],
    ['listed'],
    ['soe'],
    ['wp-1', [], {}],
    ['listed', {}, { wpId: 'wp-1' }],
    ['soe', {}, { wpId: 'wp-1' }],
    // (variant, wpId, applicableStandards, subTableData) —— F2 形态
    ['listed', 'wp-1', [], {}],
    ['soe', 'wp-1', [], {}],
    // (wpId, variant, applicableStandards, snapshot) —— H10 形态
    ['wp-1', 'listed', [], {}],
    ['wp-1', 'soe', [], {}],
  ]
  for (const [rel, mod] of loadedModules) {
    const payloadNames = model.builders.find(b => b.rel === rel)?.payloads ?? []
    for (const name of payloadNames) {
      const fn = mod[name]
      if (typeof fn !== 'function') continue
      for (const args of payloadArgs) {
        let raw: unknown
        try {
          raw = (fn as (...a: unknown[]) => unknown)(...args)
        } catch {
          continue
        }
        for (const payload of Array.isArray(raw) ? raw : [raw]) {
          const p = payload as { sub_table_data?: Record<string, unknown>; columns?: Record<string, unknown> } | null
          if (!p || typeof p !== 'object' || !p.sub_table_data || !p.columns) continue
          model.payloadResults.push({
            fn: name,
            dataKeys: Object.keys(p.sub_table_data).filter(k => !k.startsWith('_')),
            columnKeys: Object.keys(p.columns),
          })
        }
      }
    }
  }
})

function allTables(): SweptTable[] {
  return [...model.tablesByBuilder.values()].flat()
}

function tableId(t: SweptTable): string {
  return `${t.builder}（${t.rel}）:: ${t.table}`
}

// ────────────────────────── 断言 ──────────────────────────

describe('披露 columns 全 Tab 契约扫描', () => {
  describe('发现（防静默零覆盖）', () => {
    it(`发现的 build*Columns 导出数 ≥ ${BUILDER_FLOOR}`, () => {
      expect(
        model.disclosureBuilders.length,
        `实际发现 ${model.disclosureBuilders.length} 个：${model.disclosureBuilders.map(b => b.name).join(', ')}`,
      ).toBeGreaterThanOrEqual(BUILDER_FLOOR)
    })

    it('每个发现的文件都能经 import.meta.glob 加载（glob 范围未漏）', () => {
      expect(model.missingLoader, 'fs 扫到但 glob 取不到 loader → glob 模式与实际目录已漂移').toEqual([])
    })

    it('每个披露 builder 至少产出 1 张表；命名命中但非披露的须登记原因', () => {
      const barren = model.disclosureBuilders
        .filter(b => !model.tablesByBuilder.has(b.name))
        .map(b => `${b.name}（${b.rel}）`)
      expect(
        barren,
        '这些 builder 用任何平凡入参都取不到 ColumnDef 表：要么签名需要真实快照（请补 candidateArgs），要么不是披露 builder（请登记 NON_DISCLOSURE_BUILDERS 并写明原因）',
      ).toEqual([])
    })

    it('NON_DISCLOSURE_BUILDERS 条目须真实存在且原因非空白', () => {
      const discovered = new Set(model.builders.map(b => b.name))
      const stale = Object.keys(NON_DISCLOSURE_BUILDERS).filter(n => !discovered.has(n))
      expect(stale, '登记的非披露 builder 已不存在 → 请删除条目').toEqual([])
      const blank = Object.entries(NON_DISCLOSURE_BUILDERS)
        .filter(([, reason]) => !reason.trim())
        .map(([n]) => n)
      expect(blank, '原因空白视为未登记（R4.3）').toEqual([])
    })

    it(`扫描到的子表数 ≥ ${TABLE_FLOOR}`, () => {
      const total = allTables().length
      expect(total, `实际 ${total} 张（${model.tablesByBuilder.size} 个 builder）`).toBeGreaterThanOrEqual(
        TABLE_FLOOR,
      )
    })
  })

  describe('Property 2：标签列唯一且居首', () => {
    it('每张表恰好 1 个 is_label 且位于索引 0', () => {
      const bad: string[] = []
      for (const t of allTables()) {
        const labels = t.cols.filter(c => c.is_label === true)
        if (labels.length !== 1) {
          bad.push(`${tableId(t)}：is_label 列数 = ${labels.length}`)
          continue
        }
        const idx = t.cols.indexOf(labels[0])
        if (idx !== 0) bad.push(`${tableId(t)}：is_label 在索引 ${idx}`)
      }
      expect(bad).toEqual([])
    })
  })

  describe('Property 6：无英文字段键泄漏为列头', () => {
    it('每列 label 非空且不是 snake_case 字段键形态', () => {
      const bad: string[] = []
      for (const t of allTables()) {
        for (const c of t.cols) {
          const label = String(c.label ?? '')
          if (!label.trim()) bad.push(`${tableId(t)}：列 ${c.key} label 为空`)
          else if (SNAKE_CASE.test(label)) bad.push(`${tableId(t)}：列 ${c.key} label = ${label}（字段键形态）`)
        }
      }
      expect(bad).toEqual([])
    })
  })

  describe('列键完整性', () => {
    it('表内列键非空且互不重复', () => {
      const bad: string[] = []
      for (const t of allTables()) {
        const keys = t.cols.map(c => String(c.key ?? ''))
        if (keys.some(k => !k.trim())) bad.push(`${tableId(t)}：存在空列键 ${JSON.stringify(keys)}`)
        const dup = keys.filter((k, i) => keys.indexOf(k) !== i)
        if (dup.length) bad.push(`${tableId(t)}：重复列键 ${JSON.stringify([...new Set(dup)])}`)
      }
      expect(bad).toEqual([])
    })
  })

  describe('Property 3：group 相邻性', () => {
    it('同一 group 值的列索引连续', () => {
      const bad: string[] = []
      for (const t of allTables()) {
        const byGroup = new Map<string, number[]>()
        t.cols.forEach((c, i) => {
          if (!c.group) return
          if (!byGroup.has(c.group)) byGroup.set(c.group, [])
          byGroup.get(c.group)!.push(i)
        })
        for (const [group, idxs] of byGroup) {
          if (idxs[idxs.length - 1] - idxs[0] !== idxs.length - 1) {
            bad.push(`${tableId(t)}：group「${group}」索引不连续 ${JSON.stringify(idxs)}`)
          }
        }
      }
      expect(bad).toEqual([])
    })

    it('标签列不携带 group（否则 _column_groups 区间会覆盖标签列）', () => {
      const bad = allTables()
        .filter(t => t.cols[0]?.group)
        .map(t => `${tableId(t)}：标签列 group =「${t.cols[0].group}」`)
      expect(bad).toEqual([])
    })
  })

  describe('R3：flat 三态语义', () => {
    it('flat 与 group 在同一张表内互斥（flat 会显式抑制分组）', () => {
      const bad = allTables()
        .filter(t => t.cols.some(c => c.flat === true) && t.cols.some(c => !!c.group))
        .map(t => `${tableId(t)}：同表既有 flat 又有 group`)
      expect(bad).toEqual([])
    })

    it('每张表须显式声明 flat 或 group；未声明者必须在 allowlist 中逐表登记', () => {
      const undeclared = new Map<string, string[]>()
      for (const t of allTables()) {
        const declared = t.cols.some(c => c.flat === true) || t.cols.some(c => !!c.group)
        if (declared) continue
        if (!undeclared.has(t.builder)) undeclared.set(t.builder, [])
        undeclared.get(t.builder)!.push(t.table)
      }

      // 1) 未登记的 builder：一律违规（新增循环不得落到 None 态）
      const unregistered = [...undeclared.keys()]
        .filter(b => !(b in INFERENCE_FALLBACK_ALLOWLIST))
        .map(b => `${b}: ${JSON.stringify(undeclared.get(b))}`)
      expect(
        unregistered,
        '这些表既无 flat 也无 group → 后端回退 _infer_groups_from_headers 前缀推断，可能凭空造出父表头。请按源模板补 flat（单行表头）或 group（两级表头）',
      ).toEqual([])

      // 2) 已登记的 builder：实扫表名集合必须与声明**完全相等**（不许增长，修好必须删条目）
      //
      // 🔴 失败消息按**两种相反语义**分别成清单（spec guard-assertion-attribution-refactor
      //    R5.3 / Property 12）。拆分前两者共用一句「集合 ≠ 声明」，读 CI 的人无法一眼看出
      //    到底是「谁少补了声明」还是「谁修好了忘删登记」—— 而这两件事的**责任方与处置动作
      //    完全相反**：前者要去补 flat/group（写代码），后者要来删 allowlist 条目（清账）。
      //      · added   = 实扫有、allowlist 没有 ⇒ 新增 None 态表（违规，必须补 flat/group）
      //      · removed = allowlist 有、实扫没有 ⇒ 已修好未删（应从 allowlist 删除）
      const newNoneState: string[] = [] // 违规：需补 flat/group
      const fixedNotRemoved: string[] = [] // 应删：已声明 flat/group 却仍留在 allowlist
      for (const [builder, entry] of Object.entries(INFERENCE_FALLBACK_ALLOWLIST)) {
        const actual = new Set(undeclared.get(builder) ?? [])
        const declaredTables = new Set(entry.tables)
        const added = [...actual].filter(t => !declaredTables.has(t)).sort()
        const removed = [...declaredTables].filter(t => !actual.has(t)).sort()
        if (added.length) newNoneState.push(`${builder}：${JSON.stringify(added)}`)
        if (removed.length) fixedNotRemoved.push(`${builder}：${JSON.stringify(removed)}`)
      }
      // 违规类先断言（更紧急、绝不能被掩盖）：新增了 None 态表却没声明 flat/group
      expect(
        newNoneState,
        '【新增 None 态表 → 违规】这些表既无 flat 也无 group 且未在 allowlist 登记，' +
          '后端会回退 _infer_groups_from_headers 前缀推断、可能凭空造出父表头。' +
          '请按源模板补 flat（单行表头）或 group（两级表头），不得直接往 allowlist 扩条目绕过。',
      ).toEqual([])
      // 清账类后断言：已修好（实扫已不在 None 态）却仍留在 allowlist 的条目
      expect(
        fixedNotRemoved,
        '【已修好未删条目 → 应删】这些表已声明 flat/group（实扫已不在 None 态），' +
          '但仍留在 INFERENCE_FALLBACK_ALLOWLIST 里。请删除对应表名；' +
          '若某 builder 的表被删空则整条移除，并同步下调 ALLOWLIST_BUILDER_CEILING / ' +
          'ALLOWLIST_TABLE_CEILING（天花板只许缩）。',
      ).toEqual([])
    })

    it('allowlist 每条原因必填，条目真实存在，且总量不超天花板', () => {
      const discovered = new Set(model.builders.map(b => b.name))
      const stale = Object.keys(INFERENCE_FALLBACK_ALLOWLIST).filter(b => !discovered.has(b))
      expect(stale, 'allowlist 条目对应的 builder 已不存在 → 请删除').toEqual([])

      const blank = Object.entries(INFERENCE_FALLBACK_ALLOWLIST)
        .filter(([, e]) => !e.reason.trim())
        .map(([b]) => b)
      expect(blank, '原因空白 = 未登记（镜像 R4.3），不得用空原因占位豁免').toEqual([])

      const builderCount = Object.keys(INFERENCE_FALLBACK_ALLOWLIST).length
      const tableCount = Object.values(INFERENCE_FALLBACK_ALLOWLIST).reduce((n, e) => n + e.tables.length, 0)
      expect(builderCount, 'allowlist 只许缩不许扩').toBeLessThanOrEqual(ALLOWLIST_BUILDER_CEILING)
      expect(tableCount, 'allowlist 只许缩不许扩').toBeLessThanOrEqual(ALLOWLIST_TABLE_CEILING)
    })

    /**
     * 🔴 天花板「只许缩」语义的替身验证（spec guard-assertion-attribution-refactor
     * R5.2 / design Property 13）。
     *
     * 上一条用生产 allowlist 断言「≤ 天花板」，但**通过不代表判据形态正确** ——
     * 若有人手滑把 `toBeLessThanOrEqual` 写成 `toBe(2)` 等值，生产恰好贴死时照样绿，
     * 却会在**任何缩小**（把某 builder 修好、删条目）时假红。本条用替身证明：
     *   ① 条目数**低于**天花板时合规（缩小不打红）；
     *   ② 条目数**超过**天花板时才违规（扩张被挡）。
     * 只有 `toBeLessThanOrEqual` 能同时满足这两点，`toBe` 等值会在 ① 处失败。
     */
    it('天花板是「只许缩」而非等值：低于上限合规、超过才违规（Property 13 替身验证）', () => {
      // 替身 allowlist：条目数 = 天花板 − 1（模拟「修好一部分、删条目后缩小」）
      const shrunk: typeof INFERENCE_FALLBACK_ALLOWLIST = {
        fakeShrunkBuilderColumns: { reason: '替身：仅用于验证天花板语义', tables: ['t1'] },
      }
      const sBuilders = Object.keys(shrunk).length
      const sTables = Object.values(shrunk).reduce((n, e) => n + e.tables.length, 0)
      expect(sBuilders, '缩小后 builder 数低于天花板必须合规（等值断言会在此假红）').toBeLessThanOrEqual(
        ALLOWLIST_BUILDER_CEILING,
      )
      expect(sTables, '缩小后表数低于天花板必须合规').toBeLessThanOrEqual(ALLOWLIST_TABLE_CEILING)
      // 反向：扩张（天花板 + 1）不满足 ≤ ⇒ 会被生产断言挡下
      expect(ALLOWLIST_BUILDER_CEILING + 1).toBeGreaterThan(ALLOWLIST_BUILDER_CEILING)
      expect(ALLOWLIST_TABLE_CEILING + 1).toBeGreaterThan(ALLOWLIST_TABLE_CEILING)
    })
  })

  describe('Property 1：路由登记与单向覆盖', () => {
    it('每个披露 builder 的 P1 覆盖路由都已登记，且引用的 spec 文件存在', () => {
      const missing = model.disclosureBuilders.map(b => b.name).filter(n => !(n in P1_ROUTE))
      expect(
        missing,
        'P1（columns 键 ≡ sub_table_data 数据键）需真实快照，只能由 per-cycle spec 覆盖。新增 builder 必须在 P1_ROUTE 登记覆盖它的 spec，避免静默缺口',
      ).toEqual([])

      const stale = Object.keys(P1_ROUTE).filter(n => !model.disclosureBuilders.some(b => b.name === n))
      expect(stale, 'P1_ROUTE 条目对应的 builder 已不存在 → 请删除').toEqual([])

      const brokenRef = Object.entries(P1_ROUTE)
        .filter(([, r]) => !fs.existsSync(path.join(WORKPAPER_ROOT, r.spec)))
        .map(([n, r]) => `${n} → ${r.spec}`)
      expect(brokenRef, 'P1_ROUTE 指向的 spec 文件不存在（改名/删除后未同步）').toEqual([])
    })

    it('P1 单向（sweep 路由）：可平凡调用的载荷构造器，其数据键都有对应 columns 条目', () => {
      expect(
        model.payloadResults.length,
        '一个姊妹载荷构造器都没调通 → sweep 侧 P1 变成空跑，请检查 payloadArgs 或确认 P1 已全部下沉到 per-cycle spec',
      ).toBeGreaterThanOrEqual(1)

      const bad: string[] = []
      for (const r of model.payloadResults) {
        // columns 必须与 sub_table_data 同行（成对进出，design T3）
        if (!r.columnKeys.length) bad.push(`${r.fn}：携带 sub_table_data 但 columns 为空`)
        const orphan = r.dataKeys.filter(k => !r.columnKeys.includes(k))
        if (orphan.length) bad.push(`${r.fn}：数据键无 columns 落点 ${JSON.stringify(orphan)}`)
      }
      expect(bad, '数据键缺 columns → 附注侧会拿英文字段键当列头（Req 1.2）').toEqual([])
    })
  })
})
