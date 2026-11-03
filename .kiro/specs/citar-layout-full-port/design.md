# 设计：CITAR demo 排版样式全量移植

## 1. 布局切换
`DefaultLayout.vue` 按路由二选一：命中 CITAR 路径时渲染 `CitarLayout`，否则仍渲染 `ThreeColumnLayout`。
不新增顶层路由——同一 path 挂两个布局会让 vue-router 按排名挑一个、另一个静默失效；在布局里分支最简单，守卫、项目上下文加载、`ErrorBoundary` 全部沿用。

CITAR 路径（`isCitarPath`，单一来源 `src/citar/citarRoutes.ts`）：
- `/projects`、`/projects/new` → 列表态（只有顶栏）
- `/projects/:id/home|ledger-import|trial-balance|adjustments|reports|workpapers|disclosure-notes` → 项目态（顶栏 + 项目信息行 + 一级栏）

`/projects/:id/workpapers/:wpId/edit` 等其余子页不命中，仍走三栏。

## 2. 路由
- 新增 `projects/:projectId/home`（`CitarProjectHome`），项目卡片点进来先到这里。
- 六个菜单路由只换 `component`，路由名不变：`LedgerImport` / `TrialBalance` / `Adjustments` / `Reports` / `WorkpaperList` / `DisclosureNotes`；`Projects` 换成 `CitarProjectList`。

## 3. 样式
- CITAR 的 CSS 按文件原样转写为 `src/citar/styles/*.css`，每个组件 `<style scoped src>` 引入，避免 `.sheet-table` 等通用类名泄漏到全站。
- stylelint 禁 `color` / `background` 十六进制与 `font-size` px：转写脚本把这三类声明里的值换成 `var(--citar-*)`，令牌集中在 `citar-tokens.css`（`.citar-root` 上定义，值即 CITAR 原值），渲染结果不变。
- 税务底稿原用的负边距抵消三栏内边距；CITAR 框架内容区本身按路由切换内边距（税务底稿 0），负边距删除。

## 4. 数据对接
| CITAR 字段 | 本平台来源 |
|---|---|
| 项目名 | `short_name`，空则 `name` |
| 客户 / 审核年度 | `client_name` / `audit_year` |
| 项目类型标签 | `statusEnum` 的 `project_type` 标签 |
| 小微企业 / 税收优惠标签 | `small_micro_enterprise_type` / `tax_incentive_type` 有值即打标（与 CITAR `projectTags` 同判据） |
| 当前节点 | 本平台无节点，改显示项目状态（执行中 等） |
| 更新时间 | `updated_at`，无则 `created_at` |
| 签字合伙人 / 项目经理 | `signing_partner_id` / `manager_id` 在 `GET /api/users/` 里取用户名；取不到显示「—」 |
| 现场负责人 | 本平台无此字段，显示「—」 |

## 5. 税务底稿目录开合
`CitarLayout` provide 一个 `subnavOpen` ref；点「税务底稿」时若已在该页则取反，否则进入并置真。`TaxWorkpaperView` inject 后决定是否渲染目录栏（不在 CITAR 框架下 inject 不到时默认显示，兼容单独使用）。

## 6. 取舍
- 账套导入 / 未审 / 调整 / 审定页按 CITAR 现状为静态版式（CITAR 本身未接数据）。原平台这几页的真实取数能力随之下线，原文件保留，改回路由即恢复。
- 建项向导内容不改样式（字段协议与 CITAR 不同：合伙人 / 经理是账号下拉），只换成 CITAR 顶栏外壳。
