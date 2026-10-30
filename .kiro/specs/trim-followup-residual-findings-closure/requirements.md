# 需求：裁剪生成后续优化复盘的范围外问题收口

来源：`trim-generation-plan-followup-optimizations` design §4 / §5 补记登记的范围外问题（用户 2026-10-29「继续把发现没改的问题改完」），以及现状核对时按同一反模式全仓 grep 出的同类问题。不新增产品功能；真实项目只读，写入只用【测试】项目。

## 现状（2026-10-29 现扫）

- 平台没有项目级行业来源：`projects` 无行业列，向导无行业字段，共享库 `checklist_responses` 也没有任何行业类条目。
- H5 / H7 渲染策略把 `projects.business_category`（质控分类码 A / A1~A8 / B / B1~B6 / C）当行业比对 `oil_gas` / 农林牧渔，永远不命中：H5 对所有项目返回 `industry_error` 且不带已填内容、试算表、四表增强（真实项目和平药房_2025 GET 实测）；H7 四表增强永远不跑。
- M8 渲染返回由不存在属性伪造的 `project_info.industry = ""`，前端宿主据此判「非金融企业」，所有项目整页只见「一般风险准备仅适用金融企业」，金融企业也用不了。
- `/api/h5/industry-check` 查不存在的 `projects.industry` 列必 500 且只校验登录；`/api/workpapers/{wp_id}/h7/industry-check` 读分类码；两个端点前端都没有调用方。
- 同一反模式：B1-3 渲染把分类码预填进「所属行业」，B1 / B1-4 渲染与 B1-4、N2 的 AI 提示词把分类码当行业，A17 AI 上下文读不存在的属性，I4 行业推荐把分类码当关键词。
- 生成弹窗每次打开先 `POST /api/template-sets/seed`；该端点只校验登录，只读账号打开弹窗也会写库（平台没有按 readonly 角色拦写的中间件，前序 design §5 补记「后端对只读账号拒绝」不成立）。模板库「一键加载」的 template_sets 分支导入不存在的模块，恒报 loaded 而不加载。
- 前端按精确码 / 首字母判质控组别：WpPopupSigning `=== 'A'` 让 A1~A8 项目丢独立复核与 EQCR 两行；A1-11 签发表 `requiredFor.includes('A1')` 让 A1 项目 0 个必签槽位、4 个槽位全判不适用；WpPopupChecklist 细分类标签色错、未填写不出 C 类提示；GtA17Bundle / GtA171AuditSummary / GtReviewChecklist 各自私有推导。

## R1 不按不存在的行业判定适用性

1.1 H5 / H7 / M8 渲染不按行业拦截或跳过：任何项目都返回已填内容、试算表数据、溯源科目与四表增强；不再返回由分类码或不存在属性伪造的 `industry` / `is_applicable` / `industry_error` / `client_industry`。
1.2 三个渲染返回 `accounts_found`（本底稿语义科目在本项目试算表里是否找到）。宿主在 `accounts_found === false` 时于页面顶部显示不阻断的提示，写明该底稿通常适用的业务类型，并给「去程序裁剪」入口（裁剪页按循环深链）；为 true 或未知时不提示。M8 去掉整页拦截与只写不读的「标记为不适用」。
1.3 删除两个无调用方的行业校验端点与对应 service 函数；路由安全清单、原生 SQL 列基线同步。
1.4 同类读者一并修：B1-3 不再预填「所属行业」，B1 / B1-4 的 project_context.industry 留空，B1-4 / N2 AI 提示词不再出现取自分类码的行业行，A17 AI 上下文删除读不存在属性的分支与按行号取「行业」的检索词，I4 行业推荐不再拼分类码；前端删除恒放行的 `inject('projectContext')` 行业守卫与只被测试引用的 `useH5IndustryGuard` / `useH7IndustryGuard` / `useM8CrossSheet.isFinancialEntity`；H5 编制手册里与 H7 混写的科目与「农林牧渔」适用说明改正。
1.5 不新增行业字段；需要行业来源另立 spec。

## R2 打开生成弹窗不发写请求

2.1 前端列模板集只 GET；任何角色打开生成弹窗零写请求。
2.2 内置模板集由后端启动任务幂等初始化（best_effort、singleton），与原端点调用同一函数、同一覆盖语义；首次插入撞唯一约束按已存在处理，不让启动报告记失败。
2.3 `/api/template-sets/seed` 收紧为 admin / partner（与模板库「种子加载」面板 ADR D7「后端二次校验」一致）；模板库「一键加载」的 template_sets 分支改调同一函数并如实回报新增 / 更新数。
2.4 前序 spec design §5 补记的错误说法登记勘误（不回填覆盖原文）。

## R3 质控组别判断统一

3.1 前端新增唯一解释函数：优先读后端 `project_classification`，只有原值时按登记码解释（去空白大写、登记码取首字母、空 / 未登记按 C 组且 defaulted）；登记码清单与后端逐值对拍。
3.2 A1-11 签字弹窗与签发表、A1-12 检查表、A17 Bundle、A17-1 签字行、A21 复核清单按组别判断：A1~A8 属 A 组、B1~B6 属 B 组；未填写按 C 类并注明「按 C 类」。
3.3 A1-11 签发表的「鉴证业务分类」只在项目已填分类时预填组别；已保存的细分类读取时折算组别。
3.4 后端 A17-1 渲染的 project_context、A21 review-definitions 的 context 带 `project_classification`；A17 一致性校验按 resolve 判 A 组（中文旧别名保留）。
3.5 前后端直读棘轮基线按实际下调。

## R4 验证

4.1 每个修复有回归测试，按磁盘变异证明能抓到原缺陷；后端聚焦 + 相关回归与 HEAD 失败集合对照；前端聚焦、scoped vue-tsc、ESLint。
4.2 【测试】项目浏览器实测：H5 / H7 / M8 打开即见内容与科目提示、裁剪深链可达；A1-11 / A1-12 / A17 的组别显示；打开生成弹窗期间网络记录零写请求（请求集合与角色无关）。
4.3 不改真实项目数据；测试项目经平台软删；启动任务在共享库只做与原端点相同的幂等写。
