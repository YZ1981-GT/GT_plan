# 需求文档：科目底稿多文件聚合、联动与行业可扩展

## 简介

致同审计模板中一个会计科目的底稿常拆为多个 Excel 文件（应收账款 D2 = 审定表明细 / 分析程序 / 检查程序 3 个文件，共 14+ sheet）。当前 D2 父码渲染只回退到 `D2-1`，仅显示第 1 个文件的部分 sheet，D2-5 分析表、D2-6~D2-13 检查表全部丢失；且 3 个文件同名 sheet（底稿目录、附注披露）内容不同未合并。

平台已有 `account_package_registry.json` + `account_package_registry_service.py`（D1/D2 科目工作包注册表，已声明全部 sheet 来源），但 **render-config 尚未消费它**，导致聚合未生效。

本特性在复用已有注册表基础上：①让 render-config 消费注册表实现 3 文件聚合到一个底稿；②修正前端格式选型（HTML 优先，确保能显示）；③完善底稿间联动（与四表库/调整分录/明细表/披露表）；④支持行业可扩展（当前模板偏制造业，需兼容其他行业 + 用户自定义"导出模板→编辑→导入"）。

## 术语

- **科目工作包**：以 `D2` 等父码标识、代表整个会计科目的底稿集合（已有 `account_package_registry.json` 定义）
- **聚合**：将一个科目所有源文件的全部 sheet 合并到父码底稿统一展现
- **同名合并**：多文件同名 sheet 内容不同时按来源拼接，相同则去重
- **四表库**：`trial_balance`（试算表）/ `tb_aux_balance`（辅助余额表）等账表数据
- **componentType / 前端格式**：sheet 渲染采用的前端形态——HTML 表单(d-form-table) / HTML 表格(audit-sheet/c-note-table/bad-debt-sheet) / 程序中控台(a-program-console) / OnlyOffice 网格(univer)
- **行业模板包**：按行业（制造业/商贸/服务/金融等）组织的底稿模板集合

## 需求

### 需求 1：消费注册表实现多文件聚合

**用户故事**：作为审计人员，打开应收账款 D2 时希望看到该科目全部 3 个文件的底稿内容（程序表/审定表/明细表/分析表/检查表 D2-6~D2-13/披露表/调整分录），在一个底稿内完成全部工作。

#### 验收准则

1. WHEN 打开父码科目底稿（如 D2）THEN 系统 SHALL 读取 `account_package_registry.json` 中该科目声明的全部 sheet 清单
2. WHEN 注册表声明 sheet 来自不同 source_wp_code THEN 系统 SHALL 从对应模板文件提取各 sheet，聚合为完整 sheet 列表（不遗漏 D2-5/D2-6~D2-13）
3. WHEN 注册表为某科目定义 sheet_type THEN 系统 SHALL 用 sheet_type 决定该 sheet 的前端 componentType（见需求 2）
4. WHEN 科目无注册表条目 THEN 系统 SHALL 回退到现有 `get_classification` 行为（零回归）
5. WHEN `GT_Custom` 等占位 sheet THEN 系统 SHALL 跳过（skip）

### 需求 2：前端格式选型修正（确保可显示）

**用户故事**：作为审计人员，上次聚合后部分 sheet 显示不出来，我希望每类 sheet 用正确且能正常渲染的前端格式（HTML 优先），界面美观。

#### 验收准则

1. WHEN sheet_type 为 control_panel/procedure THEN 系统 SHALL 用 `a-program-console`（HTML 程序中控台）
2. WHEN sheet_type 为 audit_sheet/detail_table THEN 系统 SHALL 用 `audit-sheet`（HTML 可编辑表格）
3. WHEN sheet_type 为 analysis THEN 系统 SHALL 用 HTML 表格类组件（audit-sheet 或 analytical-review），不得用渲染不出的 univer 占位
4. WHEN sheet_type 为 disclosure THEN 系统 SHALL 用 `c-note-table`（HTML 附注表）
5. WHEN sheet_type 为 adjustment THEN 系统 SHALL 用 HTML 表格（d-form-table/audit-sheet），仅当含复杂公式/DCF/图表时才保留 OnlyOffice(univer)
6. WHEN sheet 渲染 THEN 系统 SHALL 保证有内容（schema 或模板提取数据），不出现空白"暂无数据"占位
7. WHEN componentType 选定 THEN 前端 SHALL 在已注册渲染组件白名单内（避免 fallback 到不支持类型）

### 需求 3：同名 Sheet 内容合并

**用户故事**：作为审计人员，多个文件中同名 sheet（如"附注披露信息(上市公司)"）应把各文件内容合并展示，不遗漏。

#### 验收准则

1. WHEN 多文件含同名 sheet 且内容不同 THEN 系统 SHALL 按文件顺序合并内容为单一 sheet，区块间保留来源标识
2. WHEN 判断重复 THEN 系统 SHALL 比对单元格内容哈希而非仅名称
3. WHEN 同名 sheet 内容完全相同（GT_Custom）THEN 系统 SHALL 去重保留一份
4. WHEN 合并后 THEN 前端 tab 栏对该 sheet 名 SHALL 只显示一个 tab

### 需求 4：底稿间联动完善

**用户故事**：作为审计人员，我希望明细表、调整分录、审定表、披露表之间以及与四表库数据强联动，一处更新全链反映。

#### 验收准则

1. WHEN 审定表（audit_sheet）展示 THEN 系统 SHALL 从 `trial_balance` 按科目编码取期初/未审/调整/审定金额预填
2. WHEN 明细表（detail_table）展示 THEN 系统 SHALL 从 `tb_aux_balance` 按 account_code + aux_name 聚合取数
3. WHEN 明细表合计变化 THEN 审定表对应行 SHALL 可引用明细表合计（ref_index 联动）
4. WHEN 审定表保存 audited_amount THEN 系统 SHALL 回写 `trial_balance.audited_amount` 并发 TRIAL_BALANCE_UPDATED（复用 `_on_d_audit_determination_saved`）
5. WHEN 调整分录汇总表（adjustment）展示 THEN 系统 SHALL 引用项目级 AJE/RJE 归属本科目的分录，审定表调整列反映最新调整
6. WHEN 审定数据确定 THEN 披露表 SHALL 引用审定后金额；披露变更可同步附注模块
7. WHEN 四表库/调整分录变更 THEN 相关 sheet SHALL 标记 stale 并提示刷新
8. WHEN 任一联动取数失败 THEN 系统 SHALL 友好降级（空值+提示），不报错不阻断

### 需求 5：三文件合并为一个底稿入口

**用户故事**：作为审计人员，我希望 3 个 Excel 文件在系统里就是"应收账款"一个底稿，标题为科目名，tab 栏含全部 sheet，底稿目录统一导航。

#### 验收准则

1. WHEN 聚合 THEN 顶部标题 SHALL 显示纯科目名（"应收账款"）
2. WHEN 渲染底稿目录（b-index）THEN 系统 SHALL 按审计阶段（计划/审定/实质性程序/披露与调整）分类展示全部聚合 sheet
3. WHEN tab 栏 THEN SHALL 按审计逻辑顺序排列全部 sheet（程序表→审定→明细→分析→检查→披露→调整→结论）
4. WHEN 点击目录/架构卡片 THEN SHALL 跳转对应 sheet tab
5. WHEN sheet 间有引用 THEN SHALL 提供 ref_index chip 可点击跳转

### 需求 6：行业可扩展与用户自定义模板

**用户故事**：作为不同行业的审计人员，当前模板偏制造业，我希望能兼容其他行业，并能"导出模板→自定义编辑→导入"形成本行业/本所的底稿模板。

#### 验收准则

1. WHEN 系统提供模板 THEN 注册表 / 模板包 SHALL 支持按行业标签（制造业/商贸/服务/金融/通用等）组织
2. WHEN 用户需自定义 THEN 系统 SHALL 提供"导出科目模板"功能，导出含 sheet 结构 + sheet_type + 字段定义的可编辑模板文件（xlsx 或结构化 JSON/YAML）
3. WHEN 用户编辑后导入 THEN 系统 SHALL 校验模板结构（sheet_type 合法 / 必填字段 / componentType 可渲染）并登记为项目级/事务所级自定义科目工作包
4. WHEN 自定义模板导入成功 THEN 该科目底稿 SHALL 按自定义 sheet 清单聚合渲染，与内置模板同等享受联动
5. WHEN 自定义模板与内置冲突 THEN 系统 SHALL 按优先级（项目级 > 事务所级 > 内置行业 > 通用）解析
6. WHEN 导入模板缺字段或非法 THEN 系统 SHALL 给出明确校验错误，不静默失败
7. WHERE 行业未提供专用模板 THE 系统 SHALL 回退到通用模板（不阻断）

### 需求 7：通用性与零回归

#### 验收准则

1. WHEN 任意多文件科目（D4 营业收入等）THEN 聚合机制 SHALL 同样生效
2. WHEN 单文件 / 单 sheet 底稿 THEN 系统 SHALL 保持现有行为完全不变
3. WHEN 运行既有 render-config smoke + cycle 验证套件 THEN 全部 SHALL 通过（零回归）
4. WHEN 聚合执行 THEN 模板解析 SHALL 带 LRU+mtime 缓存，性能不显著劣化
