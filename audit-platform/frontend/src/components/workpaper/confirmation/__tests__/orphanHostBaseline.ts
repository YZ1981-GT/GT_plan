/**
 * 函证域「无渲染宿主」基线登记表
 *
 * spec: confirmation-orphan-and-amount-format-closure（Requirement 2 / Property 4·5）
 *
 * ## 为什么需要这张表
 *
 * G0 Task 23 实测命名了缺陷模式「链条上游合格、整条链仍是死的」：
 * `CrossWorkpaperNav.vue` 的修复正确，但它自己**没有渲染宿主** → 用户不可达。
 * 既有守卫只断言「`buildCrossWorkpaperNavDefs` 有真实非测试消费方」，
 * 而消费方正是那个孤儿组件 —— **A 有消费方 B，但 B 自己没有消费方**。
 *
 * 故本基线要求「消费方存在性」递归到**有渲染宿主**为止：
 * 组件必须被某个非测试 `.vue` 以标签形式渲染（或进 `htmlRendererRegistry`）；
 * 模块必须被某个非测试 `.vue`/`.ts` 引用。
 *
 * ## 两张清单只许缩短
 *
 * 新增孤儿一律打红。要移除某条必须**真的接线或真的删除**，不许改基线绕过。
 * `owner` 指明谁来收口（spec 名或循环名），`reason` 说明当前为何还留着。
 *
 * ## 🔴 数字来自实测，不是立项估计（三处与 spec 文本的分歧，照实证走）
 *
 * 立项时按 G0 复盘估「组件孤儿 0 / 模块孤儿 3（H0·K0·L0 的 ImportExport 包装）」，
 * 实扫得 **组件 2 / 模块 23**（与本表条目数一致，由 orphanHostCoverage.spec.ts 的
 * 「条目数不得增长」断言封顶）。逐条复核过「生产消费方」与「测试消费方」两个维度，
 * 未发现扫描器解析缺陷（多数条目连测试消费方都是 0 = 纯孤儿，不是被 import 形态骗过）。
 *
 * 1. **`useH0ImportExport.ts` 不是孤儿，故不登记**：requirements.md「范围外」把 H0/K0/L0
 *    三个同族包装并列，但实测 `confirmation/alternativeH05/composables/useH0ImportExport.ts`
 *    被 `GtConfirmationAlternativeH05.vue` 真实 import → 有生产消费方。只有 K0/L0 两个是孤儿。
 *    （若强行登记，`基线内每条当前确实仍是孤儿` 那条 stale 断言会立刻打红。）
 * 2. **`g06SourceFidelity.ts` 已接活**：Task 10 让 `GtConfirmationAlternativeG06.vue` 消费它，
 *    故不在本表（Property 4 曾因它打红，现已自愈）。
 * 3. **`blockColumnAmountRegistry.ts` 仍是孤儿，留在本表**：Task 9 的 8 个区块配置文件消费的是
 *    `BlockColumnDef.render` 字段本身，而这张登记表的消费方只有幂等脚本
 *    `backend/scripts/fix/fix_block_column_amount_render.py`（python，不在前端扫描面）
 *    与 `blockColumnAmountRender.spec.ts`（测试，按判据不算生产消费方）→ 按设计不进生产代码。
 *
 * ## 组件基线与 Req 2.4 的关系
 *
 * Req 2.4 的目标是「函证域清零 ⇒ 组件基线为空数组」。本 spec **未能达成**：
 * 剩余 2 条都归属其它 spec（`e0-confirmation-completion` 的 E0 下区四块 /
 * `e0-send-list-dedicated-components` 0/18 未开工），接线需先定
 * 「E0 下区 vs 七枢纽共享下区」的边界 —— 属那两个 spec 的半径，本 spec 只登记不接线。
 * 守卫用「集合精确等于这 2 条 + 条目数封顶 2」把差距钉死，接线一条就把上限减一。
 */

export interface OrphanEntry {
  /** 相对 `components/workpaper/` 的路径 */
  readonly path: string
  /** 谁负责收口（spec 名 / 循环名），不得为空 */
  readonly owner: string
  /** 为何仍留着（≥8 字，禁写「待处理」这类占位） */
  readonly reason: string
}

/**
 * 无渲染宿主的**组件**（`.vue`）。
 *
 * 判据：全仓非测试文件里既无 `<PascalName` / `<kebab-name` 标签，
 * 也不被 `htmlRendererRegistry.ts` 按 componentType 引用。
 */
export const KNOWN_ORPHAN_COMPONENTS: readonly OrphanEntry[] = Object.freeze([
  {
    path: 'confirmation/E0SummaryLowerZone.vue',
    owner: 'e0-confirmation-completion',
    reason:
      'E0-1 下区四块专属组件，与 useE0BookAmounts 同批产出后未挂进 GtConfirmationSummary；'
      + 'memory 已登记为 E0 侧遗留，接线需先定 E0 下区与七枢纽共享下区的边界。',
  },
  {
    path: 'confirmation/e0-send-list/SendListConsistencyPanel.vue',
    owner: 'e0-send-list-dedicated-components',
    reason:
      '四张发函清单的一致性面板，其数据源 sendListScopeChecks / sendListE05Checks 同为孤儿；'
      + '该 spec 尚未开工（0/18），整条链一起接才有意义。',
  },
])

/**
 * 无消费方的**模块**（`.ts`）。
 *
 * 判据：全仓非测试 `.vue`/`.ts` 里无 import 该文件、也无引用其导出符号。
 * 有测试消费方**不算**有生产消费方（那恰是「守卫保护着一段死代码」的形态）。
 */
export const KNOWN_ORPHAN_MODULES: readonly OrphanEntry[] = Object.freeze([
  // ── 枚举/字典类：组件内联了同款字面量，未收敛到这些真源 ──
  {
    path: 'confirmation/alternativeD05/alternativeD05Enums.ts',
    owner: 'voucher-check-shared-layer',
    reason:
      '替代程序枚举真源，但 D05 各组件与 blockColumnConfigs 直接内联 options 字面量；'
      + '收敛属七枢纽共享层改造，半径覆盖 8 个区块配置文件。',
  },
  {
    path: 'confirmation/alternativeD06/alternativeD06Enums.ts',
    owner: 'voucher-check-shared-layer',
    reason: '同 alternativeD05Enums：D06 侧枚举真源零消费，组件内联字面量。',
  },
  {
    path: 'confirmation/diffChecklist/diffChecklistEnums.ts',
    owner: 'confirmation-shared-enums-convergence',
    reason: '差异核对清单枚举真源零消费，useDiffChecklistData 内联同款取值域。',
  },
  {
    path: 'confirmation/diffReconcile/diffReconcileEnums.ts',
    owner: 'confirmation-shared-enums-convergence',
    reason: '差异调节枚举真源零消费，DiffReconcileMaster 内联同款取值域。',
  },
  {
    path: 'confirmation/reliability/reliabilityEnums.ts',
    owner: 'confirmation-shared-enums-convergence',
    reason: '回函可靠性枚举真源零消费，ReliabilityGrid 自行渲染列与取值域。',
  },
  {
    path: 'confirmation/entityVerify/entityVerifyEnums.ts',
    owner: 'confirmation-shared-enums-convergence',
    reason: '单位信息核实枚举真源零消费，EntityVerify 组件内联取值域。',
  },

  // ── 共享 composable：被更晚建的 create*/useX 取代，未清理 ──
  {
    path: 'confirmation/composables/useConfirmationAutoFetch.ts',
    owner: 'confirmation-composable-cleanup',
    reason:
      '自动取数包装，已被 useConfirmationData 内的取数分支取代；删除前需确认无外部循环引用。',
  },
  {
    path: 'confirmation/composables/useConfirmationImport.ts',
    owner: 'confirmation-composable-cleanup',
    reason:
      '导入包装，已被页面级 CycleImportExportDropdown + useWorkpaperImportExport 取代。',
  },
  {
    path: 'confirmation/composables/useConfirmationNavigation.ts',
    owner: 'confirmation-composable-cleanup',
    reason:
      '早期跨表导航实现，已被 coordination/crossWorkpaperNav + CrossWorkpaperNav.vue 取代。',
  },
  {
    path: 'confirmation/composables/useEntitySuggestion.ts',
    owner: 'confirmation-composable-cleanup',
    reason: '被询证单位名称建议，EntityVerify 未接；接线前需确认建议数据源仍可用。',
  },
  {
    path: 'confirmation/composables/useE0BookAmounts.ts',
    owner: 'e0-confirmation-completion',
    reason:
      'E0 账面金额取数，与 E0SummaryLowerZone.vue 同批产出且同为孤儿（整条链一起接）。',
  },
  {
    path: 'confirmation/entityVerify/composables/useD01Linkage.ts',
    owner: 'confirmation-composable-cleanup',
    reason:
      'D0-2 与 D0-1 的带入联动，已被 coordination/importFromSummary 统一实现取代。',
  },
  {
    path: 'confirmation/k0-confirmation/composables/useK0ImportExport.ts',
    owner: 'k0-confirmation-source-alignment',
    reason:
      '与已删的 useG0ImportExport 同族包装，页面级下拉已直接用共享 useWorkpaperImportExport；'
      + '留待 K0 spec 收口时一并删（本 spec 只删 G0 侧，避免跨 spec 撞车）。',
  },
  {
    path: 'confirmation/l0-confirmation/composables/useL0ImportExport.ts',
    owner: 'l-cycle-four-table-extraction-and-disclosure-alignment',
    reason: '同 useK0ImportExport 的 L0 侧同族包装，留待 L 循环 spec 收口。',
  },

  // ── 联动/迁移工具：一次性或未接线 ──
  {
    path: 'confirmation/coordination/confirmationLinkageMatrix.ts',
    owner: 'confirmation-linkage-visibility',
    reason:
      '七枢纽联动矩阵声明，只有守卫消费；它是联动关系的声明式真源，接进 UI 可做联动可视化。',
  },
  {
    path: 'confirmation/coordination/migrateDformToConfirmation.ts',
    owner: 'confirmation-legacy-migration',
    reason:
      'd-form-table 旧载荷迁 confirmation 的一次性工具，存量项目仍可能需要，不宜直接删。',
  },
  {
    path: 'confirmation/e0RestrictedToE1.ts',
    owner: 'e0-confirmation-completion',
    reason:
      'E0-3 受限标记推 E1 受限资金的纯函数，E0 spec 尚未接线（memory 已登记为高价值联动缺口）。',
  },
  {
    path: 'confirmation/e0-send-list/sendListScopeChecks.ts',
    owner: 'e0-send-list-dedicated-components',
    reason:
      'E0-3 函证范围完整性红线（零余额/注销账户必须函证），该 spec 0/18 未开工。',
  },
  {
    path: 'confirmation/e0-send-list/sendListE05Checks.ts',
    owner: 'e0-send-list-dedicated-components',
    reason: 'E0-5 一函多票求和校验，与 sendListScopeChecks 同批，随该 spec 一起接。',
  },

  // ── 声明式真源：只被守卫消费，等对应 spec 接线 ──
  {
    path: 'confirmation/confirmationColumnSourceManifest.ts',
    owner: 'confirmation-column-spec',
    reason:
      '列出处登记表，被 confirmationColumnSpec.spec.ts 用作「resolve ⊆ manifest」判据；'
      + '它是守卫专用真源，接进生产代码无收益（列解析本身走 confirmationColumnSpec.ts）。',
  },
  // 🔴 2026-08-07 移出：`confirmation/k0-confirmation/k0LowerZoneSpec.ts` 已由
  //    `K0SummaryLowerZone.vue`（四块渲染）与 `ConfirmationSampling.vue`（isK0 → 6 项）
  //    真实消费（k0 spec Task 10 接线完成）。基线只许缩短，故直接删条目而不是改 reason。
  {
    // 🔴 这条是「有意只被守卫消费」的判据真源，不是待清理的死代码。
    //    七枢纽区块结构（title / sumField 列集 / sourceExtra 登记）的契约基准，
    //    被 alternativeBlockManifestContract.spec.ts 与 alternativeH05SourceFidelity.spec.ts
    //    引用来钉死「实现不得偏离源模板结构」。生产代码消费它反而会形成双真源。
    path: 'confirmation/coordination/alternativeBlockManifest.ts',
    owner: 'confirmation 共享层（替代程序区块契约）',
    reason:
      '契约基准真源，按设计只被守卫消费（区块 title / sumField / sourceExtra 三向锁死）；生产代码引用会造成双真源，故不接线也不删除',
  },
  {
    path: 'confirmation/alternativeD05/blockColumnAmountRegistry.ts',
    owner: 'confirmation-orphan-and-amount-format-closure',
    reason:
      '非金额列登记表，是「哪些 number 列不是金额」的唯一真源；'
      + '由 blockColumnAmountRender.spec.ts 与幂等脚本双向消费，设计上不进生产代码。',
  },
])
