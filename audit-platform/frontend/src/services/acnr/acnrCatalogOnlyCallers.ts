/**
 * acnrCatalogOnlyCallers — 允许无参 `useAcnr()` 的登记表（D9，需求 11.4）
 *
 * useAcnr 默认应带当前 projectId（按项目订阅 SSE 失效 + 隔离解析缓存）。少数消费者本质上
 * 与项目无关，只列目录 sheet / 全局模板库，没有也不需要项目上下文，故保留无参调用。这些文件
 * 在此逐条登记，守卫 `acnrSubscriptionLedger.spec.ts` 用 TS 编译器 API 校验：仓库里零参
 * `useAcnr()` 的文件集合必须恰好等于本登记集合（多一个、少一个、登记了不存在的文件都红）。
 *
 * 路径相对 `audit-platform/frontend/src/`。
 */
export const ACNR_CATALOG_ONLY_CALLERS: readonly string[] = [
  // 全局模板库公式编辑：无具体项目，只按目录候选 resolve（formula-fetch 校验）。
  'components/template-library/FormulaTab.vue',
  // 只列目录 sheet 作索引用途，与任一项目无关。
  'components/workpaper/composables/useAcnrCatalogIndex.ts',
] as const
