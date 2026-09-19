# 关注点 / 已知脆弱处（A/B/C 循环）

## 1. 🔴 整册纯前端组件被 grid shadow（B 系列高频）

`b22a/b22b/b22c/b23-process-control/b19-bundle/b50-risk-assessment/b60-strategy` 都是整册纯前端聚合组件，
若 render 策略输出 `html_data.cells`（模板 grid）→ `noRendererGridFallback` 抢先用 GtGridSheet 渲染 → **专属组件被 shadow 永不渲染**
（假绿，只 Playwright 能抓；get_diagnostics/Vite 200 查不出）。
解法：注册到 `_SELF_CONTAINED_DEDICATED`（折叠为单 sheet + 清空 html_data），render 返回 `{component_type, project_context}` 无 cells。

## 2. 🔴 `JOIN working_papers` 表名 bug（平台级）

多个跨底稿 loader 写 `JOIN working_papers`（复数），真实表 `working_paper`（单数）→ 查询直接抛错被静默吞。
A9 缺陷函 / A27-1 IT 备忘 / A12-1 律师函 / A10-1 治理沟通 都中招（已修 4 处），其余待排查。

## 3. B23 曾长期"假绿"（composable 齐、模板空、子底稿全 skip 三态矛盾）

`b23-process-control` spec 任务全标 [x] 但只测 composable 纯逻辑、从没测渲染 UI；
`GtB23ProcessControl` template 曾是空壳（只 loading + 附件 Tab），审计师打开只见附件。
且漏加 `_SELF_CONTAINED_DEDICATED` → 模板 grid cells 触发 grid 兜底 shadow 整个组件。已重建。

## 4. B50 风险链断裂（曾）

`risk_for_cycle` / `b50_risk_summary` 等下游 resolver 读 `field_override_service`（scope=risk_assessment），
但 B50 组件只写 checklist_responses → 两存储不相交 → 下游恒空。
已统一：新建 `b50_risk_reader` 从 checklist_responses 单一真源重建，下游 resolver 全改读它。

## 5. B19 关联方列名撞名

消费者曾读 `party_name` / `relationship_type` / `related_party_name`，而 `related_party_registry` 真实列是
`name` / `relation_type` / `is_controlled_by_same_party` → SQL 报错被 try 吞成 []（D5/D6/D7/G1 关联方核对即使主数据补上仍死）。已修。

## 6. B22 科目/结构历史问题

- B22B 源模板是**控制矩阵登记册**（12 列），平台曾映射成缺陷评价 → 真控制矩阵被塞进 B22A 只读导出
- B22A Tab4 曾错标"控制活动"（企业层无控制活动，IT 挂信息与沟通下）
- B22A-4-x IT 详细被压平成 6 个同构通用表（源模板有系统清单/ITGC 分类等结构）

## 7. C24 异常分录逐行存储性能

C24 异常分录曾逐行存 checklist_responses（34 万 × 3 字段 = 102 万行）→ selfLoad 14 秒。
改为 JSON 打包存 1 条（`C24-5-anomaly-notes`）。规则：>100 行动态数据必须 JSON 打包或从源重算。

## 8. C 类缺 render 策略 / DISPATCH 注册

C1/C22/C23/C24 曾因缺 render 策略 py 或忘在 `__init__.py` 注册 DISPATCH → 前端被 onlyoffice-sheet 兜底吞掉
（C22 的 `_c22_itgc.py` 写好但忘注册）。新增 componentType 必须同步 DISPATCH + VALID_COMPONENT_TYPES + 前端 registry。

## 9. A13 是唯一错报消费者

各底稿 `a13:push-misstatement` 的**唯一全局消费者**是 `useA13MisstatementBridge`（挂 WorkpaperEditor Shell，
有 projectId/year 上下文 + 去重窗口）。若不挂或挂错层，全平台"推送错报"按钮都失效（曾是死事件）。

## 10. B60 主底稿曾是 26 自由文本章节（应为 38 结构化表）

`b60-strategy` 曾把主底稿做成 26 章 textarea，源模板实为 38 张结构化表（责任人签名/适用性判断/重要性/
Table26 认定层次应对路由/时间计划等）。已重建为 GtB60MainDoc 结构化。
