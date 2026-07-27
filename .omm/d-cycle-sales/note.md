# 说明

本目录按 [oh-my-mermaid](https://github.com/oh-my-mermaid/oh-my-mermaid) 的 `.omm/` 约定手工产出，
**未安装 omm CLI、未跑 `/omm-scan`、未接云端**。

- 目录结构 = 元素树：`.omm/{perspective}/{element}/{nested}/`
- 每个元素最多 7 个字段文件：`description` `diagram` `context` `constraint` `concern` `todo` `note`
- `diagram.mmd` 是 Mermaid 源码，IDE 预览即可看；若后续装了 CLI，`omm view` 能自动从目录嵌套渲染成可展开分组

## 事实来源与可信度

图与说明中的以下内容**已在本仓库核实**：

- componentType 注册名 → `audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts`
- 后端 render 策略模块 → `backend/app/routers/wp_render_strategies/__init__.py`
- 主入口与 Tab 组件文件名 → `components/workpaper/GtD*.vue` 与 `components/workpaper/d1..d7/`
- TB 回写科目码 → `useD1FormData`（参数化）/ `useD3FormData` 2203 / `useD5FormData` 1124 / `useD6FormData` 1402 / `useD7FormData` 2205
- D2 读 `standard_account_code === '1122'` 作核对 → `useD2FormData` / `useD2VcAuditSummary` / `useD2VcMethodology`

标注为"待核实"的（如 D4 是否应有 TB 回写）请勿当作既有事实引用。

## 维护约定

代码改动后此处会 stale。建议只在**结构性改动**（新增 sheet / 改数据流方向 / 改跨表键契约）时更新，
不追逐每次字段级修改；`concern.md` 与 `todo.md` 允许比图更新得勤。
