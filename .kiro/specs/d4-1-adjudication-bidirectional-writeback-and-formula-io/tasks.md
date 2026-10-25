# D4-1 任务

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":[1,2],"description":"模板核定与契约"},{"wave":2,"tasks":[3,4,5],"description":"内容合并、scope取数、动态行"},{"wave":3,"tasks":[6,7],"description":"公式effective definition与前端预览"},{"wave":4,"tasks":[8,9],"description":"导入导出与人工TB发布"},{"wave":5,"tasks":[10,11,12],"description":"守卫、浏览器和收口"}]}
```

## Wave 1
- [ ] 1.1 读取运行时模板 finder/index 与权威 xlsx，形成 D4-1 descriptor；不预设同册、tab、列号、行数或 UUID 列。
- [ ] 1.2 增加 descriptor 契约测试，核对行身份、字段、公式 mask、模板版本；失败即阻塞后续实现。

## Wave 2
- [ ] 2.1 让 HTML/OO projection 统一经 ContentMutationService、版本校验、三方合并和 durable callback；冲突 fail-closed。
- [ ] 2.2 复用 four_table ReportLineAccountSpec、scope、select_leaves、aggregate_leaves 和 render 的 tb_source_codes；缺码拒绝或人工。
- [ ] 2.3 对齐 D4-1-rows 与六个 per-field 键，支持动态行增删但不写旧整行 JSON；保留 accountCode/sectionKey/source。

## Wave 3
- [ ] 3.1 通过 F-SHELL 建立 preset/custom/effective definition 的 wp_formula 版本、refs、params、hash 和权限校验。
- [ ] 3.2 接入 HTML/OO 同定义求值与来源 tooltip；公式失败标 failed/blocked，不写值、不转零。

## Wave 4
- [ ] 4.1 对齐十列导入导出和动态键；缺 accountCode/scope 拒绝或人工，派生列只重算。
- [ ] 4.2 将确认审定做成独立人工 TB 发布动作，读取 D4-1 快照，差异超过阈值二次确认；切模式不得触发。

## Wave 5
- [ ] 5.1 编写行为守卫和变异测试，覆盖三方合并、mask、F-SHELL、scope、旧键、快照来源和失败闭环。
- [ ] 5.2 Playwright 实测 OO→HTML、HTML→OO、真库 per-field、公式编辑、缺码拒绝和人工发布。
- [ ] 5.3 校验本文 AC/Property/tasks 引用、唯一 waves JSON、任务为数字且未勾选，并清理本目录临时产物。
