# 任务 4.1 读取年度收口证据

> 本批基于当前工作树现状实施；不回退并发会话已有改动。目标是：缺少项目审计年度时，底稿 D~N 与其余读取页面不再按日历年份猜测；能由后端按项目上下文解析的请求省略猜测值，不能安全读取的入口显示中文空态/提示。

## 实施范围

- **底稿 D~N**：D/E/F/G/H/I/J/K/L/M/N 的 Tab、顶层宿主、读取 composable 与抽样/序时账/试算表/附注读取入口均改为项目年度或 `null`；年度为空时短路读取并提示，或由 `GtWpRenderer` / `WorkpaperEditor` 显示「未设置审计年度」空态，不挂载年度读取子组件。
- **其余页面/组件**：交付件、公式、导入、项目布局、查询弹窗及 READ 视图改为使用项目/路由年度；年度为空时不发依赖年度的读取/写入请求，保留日历用途豁免（年度下拉上限、年度声明等）。
- **共享读取边界**：`GtWpRenderer` HTML/Univer 两条路径统一年度空态门；`WorkpaperSidePanel`、`WorkpaperWordEditor`、程序表/交付件/公式读取入口不再产生当前年/去年默认值。

## 棘轮现算

- 前端扫描器：源码总命中 = **15 个通用 SINGLE_SOURCE 基线项 + 21 个 CALENDAR 豁免项 = 36**。
- 基线 `auditYearCalendarFallbackBaseline.json` 已从 281 个待收口命中降为 **15 个**通用单一来源项；D~N/READ 命中已移除。混合页面 `ConsolidationIndex`、`LedgerImportHistory`、`LedgerPenetration` 的日历命中仅保留在可证伪豁免表，不再留在待修基线。

## 验证

1. `rtk npx vitest run src/__tests__/auditYearCalendarFallbackRatchet.spec.ts`：**6 passed**。
2. D/H/年度核心定向回归（8 个 test files）：**50 tests passed**。
3. 渲染器/运行时年度边界回归（5 个 test files）：**27 tests passed**。
4. 交付件/公式定向回归（6 个 test files）：**53 tests passed**。
5. `get_diagnostics` 覆盖 `components/workpaper`、`components/deliverable`、`components/formula`、`components/import`、`components/layout`、`components/query`、`views`、`composables`、`utils`：无诊断错误。
6. 全量 `src/components/workpaper` Vitest 曾运行 **180 秒超时**，未得到失败断言摘要；随后按实际受影响边界拆分执行上述定向集合并全部通过。测试期间仅有既有 Element Plus 未注册组件 warning，无新增失败。

## 测试契约更新

- `useProjectAuditYear.spec.ts`、`workpaperSidePanelYear.spec.ts`、`workpaperListYear.spec.ts` 将旧的「缺年度回退去年」断言改为当前 R3.2/B 语义：返回/传递 `null`。
- `DeliverableShortcut.spec.ts` 修正为 mock 实际生产 import 的 `@/services/apiProxy`，并保持有年度时完整性读取回归。
7. 浏览器 smoke：在已运行的 `http://127.0.0.1:3030` 中刷新用户管理页与真实项目底稿管理页（`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`），页面正常渲染，控制台无 error。首次 smoke 发现 `FourColumnContent.vue` 的临时语法错误（守卫插入位置错误），已立即修正；修正后 HMR/整页刷新正常。该问题未被目录级 diagnostics 暴露，已作为运行时验证发现并修复。
8. 追加族回归：G14/K9/N1 3 个既有 test files **44 tests passed**；用于补充 G/K/N 族的业务模型覆盖。