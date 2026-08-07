# Implementation Plan: 母公司附注章节结构与取数修复

## Overview

5 波 / 18 任务，**18/18 全完成（2026-08-07）**。修母公司附注章节的结构错位与零取数，并让报表母公司列复用同一口径。

收口状态：6 个后端守卫 412 passed / 前端 23 passed / 幂等 `--check` 0 欠账 / 变异检验 13/13 RED / CI 2 job / 真实库诚实报告 `UNVERIFIABLE`（本库无合并项目）。详见 Notes §2026-08-07 收口轮实录。

**开工前必读**：

- 判据真源是 `docs/模版/` 下两份 docx，**不是** `note_template_*.json`（后者是 md 重建产物）。docx 章号是 Word 自动编号，段落文本不含「十二、」，定位必须按 `Heading 1` 样式而非正则匹配章号。
- 母公司章**禁删**。此前曾被误判为「孤儿重复章」并建议 `--apply` 删除，该判断已撤回（详见 requirements Glossary「已裁决事项」）。
- 结构改动一律走幂等脚本；两份模板 JSON 巨大（listed 1.35 MB / soe 851 KB）且并发会话会互相回退，禁手改。
- 本 spec **无 DB 迁移**。母公司身份由 `projects` 既有三元组 `(company_code, audit_year, report_scope)` 推导。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "事实基线与判据守卫", "tasks": ["1", "2"], "depends_on": [] },
    { "wave": 2, "name": "结构修订（幂等脚本）", "tasks": ["3", "4", "5", "6", "7"], "depends_on": ["1"] },
    { "wave": 3, "name": "口径 helper", "tasks": ["8", "9"], "depends_on": [] },
    { "wave": 4, "name": "取数接线与报表修正", "tasks": ["10", "11", "12", "13", "14"], "depends_on": ["2", "3", "8"] },
    { "wave": 5, "name": "守卫收口与验收", "tasks": ["15", "16", "17", "18"], "depends_on": ["4", "5", "6", "7", "9", "10", "11", "12", "13", "14"] }
  ]
}
```

Wave 1 与 Wave 3 无依赖关系，可并行。Wave 3 的 helper 是 Wave 4 两个方向（附注取数 / 报表列）的共同前置，必须先完成。

## Tasks

- [x] 1. 建立母公司章事实基线提取器
  - 新建 `backend/scripts/diagnose/extract_parent_company_chapter_facts.py`（只读，默认输出到 stdout + `--out` 落盘）
  - 用 python-docx 按 `Heading 1` 定位两版母公司章（listed「公司财务报表主要项目注释」/ soe「母公司财务报表的主要项目附注」）
  - 逐子节输出：Heading 层级、标题原文、是否含「披露格式参考附注五、X」字样、自有表数量、每表 `rows`/`cols`/两行表头/首列样本
  - 同时输出两版合并章中母公司对应科目的表结构，供「同构子节」比对
  - 源 docx 缺失时**明确报错并打印期望路径**，不得静默返回空
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 2. 母公司章判据守卫（先于任何修订，必须先打红）
  - 新建 `backend/tests/test_note_parent_company_chapter.py`
  - 直读源 docx 与两份模板 JSON 做三向比对；断言母公司章与 6+6 子节存在（Property 1）
  - 断言两版子节集合不对称：listed 独有「应收票据」、soe 独有「现金流量表补充资料」（Property 3）
  - 断言「同构子节」在源 docx 无自有表、「自有表子节」有表且表数匹配（Property 4）
  - 断言国企源 docx 14 个 Heading 1 不含「股份支付」（Property 5 后半）
  - listed 标题偏差双向锁死：JSON 为「母公司财务报表主要项目注释」且 docx 为「公司财务报表主要项目注释」（Property 8）
  - **本任务完成时守卫应对当前 JSON 打红**（soe 章名仍是「股份支付」、columns 全 0），红得准才说明判据有效
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.4, 3.1, 3.2, 3.3_

- [x] 3. soe 第十二章标题与标识修正
  - 新建 `backend/scripts/fix/fix_note_parent_company_chapter.py`，复用 `_note_structure_kit`（`rule`/`run_section`/`apply_plan`/`build_cli`）
  - 第 12 章 `section_title` → 「母公司财务报表的主要项目附注」；`section_id` → `chapter-12-mu-gong-si-cai-wu-bao-biao-de-zhu-yao-xiang-mu-fu-zhu`
  - 6 子节 `parent_section_id` 与 `section_id` 前缀同步改写；旧 slug 追加进 `legacy_aliases`
  - `sort_index` 保持 12 不变
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x] 4. 表名唯一化（须在补列之前执行）
  - 同一脚本内实现，处理顺序排在补 `columns` **之前**（列规则按表名索引，先补列会落空）
  - listed 侧表头首格泄漏名（`种  类`×3 / `类 别`×2 / `承兑人名称`×2 / `名  称`×2）与空名表 → 按 `{科目名}（表N）` 正名
  - 沿用 soe 侧既有自动编号范式，**不臆造业务表名**
  - 旧名 → 新名映射登记进 `legacy_aliases`；确认废弃的进 `_removed_table_keys` 语义
  - **覆盖面（需求 6.5）**：实测受影响的全部 6 个子节（listed 应收票据/应收账款/其他应收款/长期股权投资/营业收入与营业成本 + soe 其他应收款）逐个正名；listed 应收账款的 6 张空名表逐张获得稳定唯一名（现状 6 张塌成 1 键）
  - **唯一性判据（需求 6.6）**：`check_names_unique` 按「同子节内表名集合大小 == 表数量」断言（不是只查空串），消息体逐子节输出实际表数 / 去重后键数 / 塌键张数便于定位规模；`PARENT_TABLE_CENSUS` 逐子节冻结表数作规模锚点
  - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6_

- [x] 5. 长期股权投资两级表头还原
  - listed 3 表列数还原为 7 / 9 / 13；soe 3 表列数还原为 5 / 7 / 12
  - 两级表头走 `ColumnDef.group` + 叶子 `label`；**`key` 保持不变**（改 key 会让既有数据丢落点）
  - 源 docx 的 `…` 可扩行与 `一、合营企业`/`二、联营企业` 分组行保留，不得当占位删除
  - _Requirements: 4.3, 4.4, 4.5, 4.6_

- [x] 6. 同构子节表结构对齐合并章
  - listed：应收票据←五、4 / 应收账款←五、5 / 其他应收款←五、8 / 营业收入和营业成本←五、62
  - soe：应收账款、其他应收款、营业收入与营业成本 ← 合并章对应科目
  - 对齐口径 = 表集合与列结构一致；**投资收益与长期股权投资不参与对齐**（自有表）
  - _Requirements: 4.1, 4.2, 4.7, 4.8_

- [x] 7. 补齐列元数据与编制指引
  - 母公司章全部表补 `columns`，每张表显式表态 `group` 或 `flat`（禁留 `None` 触发前缀推断）
  - 补 `guidance`，内容仅取源 docx 红字/括注/章首说明（含 soe 章首「应参照上述相应项目的要求加以注释」及反向购买、资本公积弥补亏损两条），纯文本无 markdown 粗体
  - `--check` 在修订后 0 欠账 exit 0；连续两次 `--apply` 逐字节一致
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8. 母公司口径 helper（单一真源）
  - 新建 `backend/app/services/parent_company_scope.py`
  - `resolve_parent_standalone_project(db, consol_project)`：按 `(company_code, audit_year, report_scope='standalone')` 定位，三条件齐备
  - `resolve_consolidated_sibling(db, standalone_project)` + `is_parent_company_project(db, project)`
  - 入参非 `consolidated` → None；找不到 → None + INFO 日志，不抛异常
  - 同代码多条 standalone（唯一索引理论上不可能）→ 断言并记 ERROR
  - 模块 docstring 登记需求 8.6 的决定：不扩展 `normalize_report_scope` 取值域，母公司口径由「合并项目 + 跨项目取数」表达，`parent_only` 不进附注层
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.6_

- [x] 9. helper 守卫与展示层交叉锁死
  - 新建 `backend/tests/test_parent_company_scope.py`
  - 源码级断言三个查询条件齐备（去掉 `report_scope` 或 `audit_year` 必红）
  - 行为断言边界：非合并入参 / 无兄弟 / 同代码多条
  - 交叉锁死：`is_parent_company_project()` 判为母公司的集合 == `project_display.get_project_display_name()` 加「（母公司）」后缀的集合（**函数名逐字为 `get_project_display_name`**，按 `build_*` 写会 0 命中空转；须 import 真实符号，并把 ORM 对象投影成 dict 再喂给它）
  - _Requirements: 7.6, 8.6_

- [x] 10. variant_matrix 增母公司维度（additive）
  - 给母公司章覆盖的科目加顶层可选字段 `parent_company_sections: {listed, soe}`
  - **不新增变体键**、不改既有 `variants` 任何取值（102 科目逐字不变）
  - 提供幂等生成/校验脚本入口，并在 `backend/tests/test_variant_matrix.py` 侧加 additive 断言
  - _Requirements: 8.1, 10.4_

- [x] 11. 母公司章 report_row_code 对账
  - 母公司章各表的 `report_row_code` 按 `report_config` 实证对账填入（现状全 None）
  - 取值必须能在 `report_config` 中查到，且行名与该 row_code 的 `row_name` 可比对；查不到就留 None 并登记理由（宁缺勿造）
  - **落地形态**：`PARENT_ROW_CODE_PLAN`（`RowCodePlan` 逐子节声明 ref / main_table / 留 None 理由）+ `apply_report_row_codes` + `check_report_row_codes`
  - **实测填码 6 张、留 None 5 个子节**（每条带 report_config 对账依据）：
    listed 应收票据 `BS-005` / 其他应收款 `BS-009` / 长期股权投资 `BS-024` / 投资收益 `IS-011`；
    soe 其他应收款 `BS-009` / 长期股权投资 `BS-024` / 投资收益 `IS-011`
  - **留 None 的三类理由（宁缺勿造）**：① 应收账款（两版）—— 已与合并章同构，17/13 张全是账龄/坏账/组合/核销/前五名等分类维度，**无汇总主表**，任填一张都会让下游把某维度当整行取数；② 营业收入与营业成本（两版）—— 对应**两个**报表行 `IS-001「一、营业收入」`+`IS-002「减：营业成本」`，且全库无 row_name 为「营业收入」/「营业成本」（不带序号/「减：」）的行，表级只能挂一个码；③ soe 现金流量表补充资料 —— 对应**整张报表** `report_type=cash_flow_supplement`（30 行），无代表整表的单一 row_code
  - _Requirements: 8.3_

- [x] 12. 母公司章取数接线
  - 取数入口按 `parent_company_sections` 判定当前章节属母公司章
  - 属母公司章 → 经 `resolve_parent_standalone_project()` 拿到项目 id → 走既有 `trial_balance` / 底稿取数链路（**不新建取数管道**）
  - 兄弟项目缺失 → 载荷标 `parent_project_missing: true`，金额字段为 `None` 而非 0
  - **落地**：新建 `app/services/parent_company_note_sections.py`（判定 + 口径切换单一入口）+ `disclosure_engine` 三处接线（`_parent_scope` 惰性缓存 / `_build_resolver_ctx` 切 `project_id`+`_tb_cache` / `_build_table_data` legacy 路径同步切换并清空 `_wp_cache`·`_wp_fine_cache`）
  - **🔴 本轮补齐三处缺口（此前均静默失效，四层验证全绿）**：
    ① **P0 `_attach_parent_source_meta` 返回 `None` 且不容忍 `ctx=None`** —— legacy 路径写的是 `return self._attach_parent_source_meta({...}, parent_ctx)`，故对**每一张无 binding 的表**返回 `None`（整章表格凭空消失）；且非母公司章时 `parent_ctx` 就是 `None` → `AttributeError: 'NoneType' has no attribute 'get'` **全线崩**。实测探针：`section_number=None` 时 legacy 路径抛异常。已改为**返回 `table_data`** + `if not isinstance(table_data, dict) or not ctx: return table_data`
    ② **`resolution_failed` 未被处置** —— `if not scope.is_consolidated: return ctx` 排在前面，把「口径解析失败」和「确定不是合并项目」合并成一态 ⇒ DB 抖动时母公司章静默显示**合并口径金额**（错数，比取不到更坏）。已在 `is_consolidated` 判断**之前**加 `resolution_failed` 留空分支
    ③ **`refill_sections` 的 ctx 在循环外构造一次并复用** ⇒ 母公司章 refill 拿合并项目的 `_tb_cache`。已收敛到 `_build_resolver_ctx` 唯一入口（逐 note 构造；非母公司章零额外查询，母公司口径经 `_parent_scope_cache` 每实例只解析一次）
  - _Requirements: 8.2, 8.4_

- [x] 13. 母公司取数溯源展示
  - 载荷补 `source_project_name` / `source_company_code` / `source_scope`
  - 前端复用既有溯源面板范式呈现；`parent_project_missing` 时显示「本项目未建母公司单体」灰态
  - **🔴 接手时后端 payload 已就绪但前端消费方为 0**（`_parent_company_source` / `parent_project_missing` / 「母公司单体」全前端各 0 命中）= dead output。本轮补前端：
    - 新建纯函数 `views/composables/parentCompanyNoteSource.ts`（**三态** `none`/`missing`/`resolved`，把 `missing` 与 `none` 合并会让「未建母公司单体」静默无提示、用户看到空表以为是自己没填）
    - `DisclosureEditor.vue` 挂横幅（表级取 `activeTableData`，`missing` 用 warning / `resolved` 用 info）+ `DisclosureEditor.css` 补样式
    - 口径英文值中文化（`standalone` → 「单体（母公司）」），未知值原样透出便于排查
  - _Requirements: 8.5_

- [x] 14. 报表侧母公司列口径修正
  - `report_excel_exporter._load_parent_row_index()` 改用 `resolve_parent_standalone_project()`
  - 移除 `parent_company_code` 定位；补齐 `report_scope` 与 `audit_year` 过滤
  - 保持 fail-open：定位不到返回空 dict、该列留空不崩；`:parent` 占位与 `current_parent` 坐标语义不变
  - _Requirements: 9.1, 9.2, 9.3, 9.5_

- [x] 15. 报表侧反向自检守卫
  - 新建 `backend/tests/test_report_parent_column_scope.py`
  - 构造「同代码同年度同时存在 consolidated 与 standalone 两条项目」场景
  - 断言旧实现会取到合并项目（复现即打红）、新实现取到单体项目
  - 断言源码不再引用 `parent_company_code`；**判据必须剥 docstring** —— Task 14 实测该函数内代码级 0 处、docstring 3 处（那 3 处是需求 9.1 要求的「同代码 standalone 兄弟 ≠ 上级公司」对比说明），裸 `src.count()` 会误红
  - **同步修正既有 `backend/tests/test_financial_template_cell_mapping.py::test_exporter_resolves_parent_column`**（Task 14 实测它是唯一新增失败，属「测试镜像 bug」不是回归）：其 fixture 是 `PARENT01`（上级公司，代码不同）+ 两侧 `audit_year=None`，断言母公司列取到上级公司的 2000.0 = 被修掉的旧错口径；改为「同 `company_code` + 同 `audit_year` 的 standalone 兄弟」，并把「上级公司不得被使用」拆成独立反向自检。不改它会留一条永久红
  - Task 14 已实证可覆盖的四态（供构造场景复用）：同代码同年度 standalone 兄弟 → 填入 / 上级公司 → 留空 / 同代码只有 consolidated → 留空 / 兄弟 `audit_year` 不同 → 留空
  - **落地**：`test_report_parent_column_scope.py`（20 例）—— Property 25 源码级（剥 docstring 后代码级 0 处 + docstring 仍留 ≥3 处口径对比说明，两条互为对照证明剥注释器有效）/ Property 26 **真跑旧查询**复现（旧口径确实命中上级公司、候选集里确实含合并项目）/ Property 27 fail-open 含 `AssertionError` 也要兜住 + `:parent` 占位正则 + `current_parent`·`prior_parent` 坐标键 + `parent_row_index` 三处接线未断
  - **同步修正 `test_financial_template_cell_mapping.py::test_exporter_resolves_parent_column`**（原 fixture 是 `PARENT01` 上级公司 + `audit_year=None`，断言母公司列取到上级公司的 2000.0 = 被修掉的旧错口径）：改为同 `company_code`+同 `audit_year` 的 standalone 兄弟；「上级公司不得被使用」拆成独立反向自检 `test_exporter_ignores_upper_level_company`；`_add_project` 补 `audit_year=2024` 默认值（为 NULL 时 helper 判「定位字段不齐」直接返 None ⇒ 公司列必然留空）
  - **两处判据写法坑（已写进文件 docstring）**：① `_func_src`/`_func_code` 必须对**整份文件**做一次 AST 解析后按行号裁切 —— 对「缩进的方法片段」单独 `ast.parse` 会 `SyntaxError`；② 方法名逐字为 `_fill_by_placeholders`（首版按 `_fill_inline_placeholders` 写，被「按错名必抛」的护栏直接打红）
  - _Requirements: 9.1, 9.4_

- [x] 16. 取数守卫与零回归 characterization
  - 新建 `backend/tests/test_parent_company_note_sourcing.py`（Property 19~23，**63 例**）
  - 合并章 characterization：listed 第 5 章 / soe 第 8 章 `tables`/`rows`/`columns`/`text_sections` 逐字节不变
  - `variant_matrix` 102 科目 `variants` 快照比对
  - **🔴 Property 28 的判据形态刻意改为「apply 前后对照」而非「冻结合并章快照」**：合并章由别的 spec（营业收入披露侧）持续在改 —— 2026-08-07 实测它给「营业收入、营业成本按分解信息」表的标签列加了 `flat: True` ⇒ 冻结快照会变成与本 spec 无因果的假红发生器。新判据 = 内存里跑一遍完整 apply 管道（7 个 `apply_*`），断言合并章 `五、4/五、5/五、8/五、62` 与 `八、5/八、9/八、64` 序列化后逐字节不变，并配「同一管道确实改动了母公司章」的反向自检防空转
  - **`variant_matrix` 侧已由 `test_variant_matrix.py` 的 102 科目冻结基线覆盖**（`variants` + `legacy_aliases` 双重比对 + 顶层键白名单 + 生成器 carry-over 接线断言），本任务不重造
  - _Requirements: 10.3, 10.4_

- [x] 17. 变异检验与 CI 接入
  - 对全部新增守卫逐条做变异检验并记录结果（改一处必红 + 已还原）
  - **落地**：`backend/scripts/diagnose/mutate_parent_company_note_guards.py`（**13 个变异，实测 13/13 RED**）
  - **判据是失败测试名的差集而非退出码**，三态区分 `RED` / `GREEN`（守卫缺陷）/ `ANCHOR-MISS`（脚本缺陷，此时「测试仍绿」不能作为任何结论）
  - 覆盖 tasks.md 原列 9 个 + 本轮新增 4 个：`_attach_parent_source_meta` 改回返回 None / 改回不容忍 `ctx=None` / 删掉 `resolution_failed` 留空分支 / 删掉前端溯源横幅渲染
  - 还原：每个变异单独 `try/finally` 按**字节**写回 + 事后 sha256 核验（防「变异脚本被 Ctrl+C 中断留下残留」）；实测收尾 `*.mutbak` 残留 0
  - `.github/workflows/governance-checks.yml` 新增 **2 个 job**：`parent-company-note-chapter`（6 个后端守卫 + `--check` + 变异检验 + live 烟测）与 `parent-company-note-frontend`（Task 13 前端守卫）
  - YAML 实测可解析、job 数 **117(HEAD) → 124**、我的 2 个在内、0 个被移除、无重名
  - _Requirements: 10.1, 10.2, 10.5_

- [x] 18. 真实库验收（诚实报告）
  - 新建 `backend/scripts/diagnose/verify_parent_company_note_live.py`（只读，默认 dry-run）
  - 覆盖「合并项目 + 母公司单体项目」这一对的端到端取数
  - **真实库当前 8 个项目全为 `standalone`、无一 `consolidated`** ⇒ 脚本必须明确输出「无法验收：本库无合并项目」，禁用 fixture 冒充通过
  - **实测输出**：判据侧 4 项 PASS（两版母公司章节号 6+6 非空 / 两版集合交集为空 / 逐字命中可用 / 非母公司章不被误判）+ 项目盘点 `{'standalone': 8}` + 结论 `UNVERIFIABLE`，**退出码 0**（诚实报告不算失败）
  - `--strict` 把「不可验收」也视为失败，供将来建了合并项目后在 CI 强制要求真实验收
  - _Requirements: 10.6_

## Notes

### 事实基线（2026-08-05 实测，供实现时核对）

**listed 第 16 章「公司财务报表主要项目注释」**（docx idx=2593，Heading 1）：

| 子节 | Heading | 自有表 | 说明 |
|---|---|---|---|
| 应收票据（披露格式参考附注五、4） | H2 | 0 | 同构 |
| 应收账款（披露格式参考附注五、5） | H2 | 0 | 同构 |
| 其他应收款（披露格式参考附注五、8） | H2 | 0 | 同构 |
| 长期股权投资 | H2 | 3 | 7 列 / 9 列 / 13 列，均两级 |
| 营业收入和营业成本（披露格式参考附注五、62） | H2 | 0 | 同构 |
| 投资收益（注：以下不存在的项目可以删除） | H2 | 1 | 3 列 16 行 |

**soe 第 12 章「母公司财务报表的主要项目附注」**（docx idx=1660，Heading 1）：

| 子节 | Heading | 自有表 | 说明 |
|---|---|---|---|
| 应收账款 | H3 | 0 | 同构 |
| 其他应收款 | H3 | 0 | 同构 |
| 长期股权投资 | H3 | 1（+2 子表） | 5 列；子表 7 列 / 12 列两级 |
| 营业收入与营业成本 | H3 | 0 | 同构 |
| 投资收益 | H3 | 1 | 3 列 21 行 |
| 现金流量表补充资料 | H3 | 1 | 3 列 31 行 |

soe 长期股权投资 T1 首列样本：`对子公司投资 / 对合营企业投资 / 对联营企业投资 / 小 计 / 减：长期股权投资减值准备 / 合 计`
soe 长期股权投资 T3 首列样本：`一、合营企业 / … / 二、联营企业 / …`（`…` 是可扩行）

**JSON 现状**（待修）：

| 侧 | 子节表数 | 问题 |
|---|---|---|
| listed 十六 | 应收票据 14 / 应收账款 15 / 其他应收款 18 / 长期股权投资 3 / 营业收入与营业成本 6 / 投资收益 1 | columns 全 0；长期股权投资列压成 3/4/4；表名重名+空名 |
| soe 十二 | 应收账款 11 / 其他应收款 15 / 长期股权投资 3 / 营业收入与营业成本 5 / 投资收益 1 / 现金流量表补充资料 1 | 章名错为「股份支付」；columns 全 0；长期股权投资列压成 4/4/4 |

### 2026-08-07 收口轮实录（Task 11~13 / 15~18，18/18）

**接手时的复选框可信度**：Task 11 标 `[ ]` 而**早已完整交付**（`PARENT_ROW_CODE_PLAN` 逐子节声明 + `--check` exit 0 / 0 欠账）= 假红；Task 12/13 的**服务层**已交付而 `disclosure_engine` 接线有 3 处静默失效、前端消费方为 0。⇒ 又一次印证「复选框的 `[ ]` 与 `[x]` 都不可信，接手必须逐个探针」。

**本轮修掉的 P0（比缺功能更严重，四层验证全绿）**：`_attach_parent_source_meta` 返回 `None` 且不容忍 `ctx=None` ⇒ legacy 路径（`section_number` 未命中 binding）对**每一张表**返回 `None` 或抛 `AttributeError`。实测探针：`_build_table_data(..., section_number=None)` 抛 `AttributeError: 'NoneType' object has no attribute 'get'`。**该 P0 未被任何既有测试覆盖** —— HEAD-swap 基线实测 152 个失败两侧逐条相同（新增 0 / 消失 0），说明它既不打红也不被抓；现已补 `test_legacy_path_returns_table_for_non_parent_section` + `test_attach_meta_returns_table_and_tolerates_none_ctx` 两条钉子，并进变异清单。

**修掉的守卫自身缺陷**：`test_source_code_has_no_prefix_matching` 用裸子串 `"in code"` 判「不得用子串包含匹配」，而**合法的集合成员判定** `code in codes` 含子串 `"in code"` ⇒ 该断言对正确实现恒红、对错误实现也红 = 零信号。改为词边界 `\bin\s+code\b` 并配「对子串匹配实现必红 + 不误伤集合成员判定」双向自检。

**与并发 spec 的一次真实撞车（处置可复用）**：会话中途（08:28）营业收入披露侧的并发会话给**合并章**「营业收入、营业成本按分解信息」表（listed 五、62 表[3] / soe 八、64 表[3]）的标签列加了 `flat: True`，而其余 8 列带 `group`。`note_sub_table_projector._extract_column_groups` 的 `if any(d.get("flat") ...): return []` ⇒ **`flat` 标在任意一列即对整表生效并丢弃全部 `group`**，该表两级表头静默降级成单级。这是**上游缺陷**（归营业收入披露侧），但同构子节忠实镜像后让本 spec 的 columns 判据打红。

处置 = **登记 + 双向锁死，不修上游也不在母公司侧自行纠正**（自行纠正会与合并章分叉 ⇒ `check_isomorphic` 深相等永远报欠账、`--apply` 每轮报变更、幂等空操作永不成立；而合并章是本 spec 只读源）：
- `UPSTREAM_MERGED_COLUMN_CONFLICTS` 登记 2 条（含合并章章节号 + 表名 + 依据）
- 豁免**只放行 flat/group 并存这一条**，其余判据（columns 缺失/未表态/标签列带 group/label 空）一律不豁免，配 4 段反向自检（含「不传豁免时登记表也必须打红」证明豁免确实在起作用、「未登记表的并存必须打红」证明豁免不外溢）
- `test_upstream_conflict_registry_still_reproduces` 与合并章双向锁死：上游修好后登记项即 stale 必打红，提醒移除 ⇒ 豁免不会变成永久盲区
- 顺带跑 `--apply` 把两个同构子节重新对齐到（改动后的）合并章 —— 这正是 Task 6 幂等脚本的设计用途，`--check` 回到 0 欠账

**验证汇总**：本 spec 6 个后端守卫文件 **412 passed / 0 failed** · 前端 **23 passed** · 幂等 `--check` exit 0 / 0 欠账 · 变异检验 **13/13 RED** 且残留 0 · Vite transform `DisclosureEditor.vue`/`parentCompanyNoteSource.ts`/`DisclosureEditor.css` 全 200 · CI job 117→124 · 真实库验收诚实输出 `UNVERIFIABLE`。
**零回归判据**：把 `disclosure_engine.py` 换成 HEAD 版跑同一组（`-k "disclosure or note_ or variant_matrix or refill"`，`--ignore` 本 spec 4 个新测试文件以免 HEAD 侧收集崩），两侧失败集合**逐条相同 152 项** ⇒ 新增失败 0。

**预存在红（与本 spec 无因果，勿误认领）**：`test_variant_matrix.py::test_every_matrix_code_exists_in_index` —— `gong_yun_jia_zhi_bian_dong_shou_yi`/`xin_yong_jian_zhi_sun_shi`/`suo_de_shui_fei_yong` 三个科目的 listed 侧取值是 `三、xxx`（会计政策章）而该测试只认「项目注释章」（listed=五 / soe=八）。已核实 matrix 的 `variants`、`section_code_index.json`、该测试函数**三者都与 HEAD 逐字相同**（`test_variant_matrix.py` 只有 569 insertions / 0 deletions），属 memory 已登记的「variant_matrix 假 null / 落点在别名章」议题，归 spec C/B。

### 未纳入本 spec 的关联缺陷（另立）

- 国企↔上市转换：`execute_conversion` 的 Step 3/4/5 是空操作、Step 4 返回 `count(*)` 冒充 `mapped_notes`、`convert_disclosure_notes_v2` 是孤儿（11 测试 / 0 生产调用方）
- `note_soe_listed_diff.json` `is_mock=True` 且与实时计算不一致（common 106 vs 107 / listed_only 71 vs 70 / format_diff 33 vs 39）、`field_mapping` 全 null、format_diff 无 `section_id` 键
- 合并附注 V2 与跨模板翻译两个灰度开关默认关

### 实现顺序提示

Task 4（表名正名）必须排在 Task 7（补列）之前；Task 8（helper）是 Task 12 与 Task 14 的共同前置。Wave 1 的守卫要求**先对当前 JSON 打红**，不要等修完再写守卫（先改后写无法区分「守卫有效」与「空转」）。
