# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-08-24
**当前分支**：`work/2026-08-23-advanced-query-hardening-closure`
**统计**：Active **3**（2026-08-24 逐目录实扫 `.kiro/specs/*/` 共 **3** 个目录，全部带 `tasks.md`，空壳 **0**）/ Archived **560**（沿用上一轮归档区实扫值，本轮未重算归档目录）

> **2026-08-24 当前实扫**：
> `advanced-query-hardening-wiring-closure` **62/64** ·
> `dsh-agent-panel-integration` **35/35**（尚在 Active，未归档） ·
> `workpaper-html-onlyoffice-bidirectional-writeback-closure` **72/77**（2026-09-02 实扫）。
> 双向回写 spec 当前生成事实为 185 个物理宿主/276 个挂载点/186 个 entry；2026-08-24 独立协议语义复审进行中；当前修订采用单次 business commit、content/representation 分层、immutable authority model + definition bundle、`template → instrumentation → contract → bundle → representation` 发布链、non-current upgrade candidate、frozen forcesave/recovery request、server/client 双基线、room 级多人 callback 与 close-intent singleton、authorization-before-resource/cache、incoming sequence fence及逐 scenario evidence。严格校验现为 **14 Req / 170 AC / 72 Property / 72 Task / 8 Wave**，AC task coverage **170/170**、Property 实现+独立验证双覆盖 **72/72**、DAG 无环；进度 **72/77**（2026-09-02 实扫复选框）。
>
> **2026-09-02 入库与修复（分支 `work/2026-09-02-workpaper-sync-closure`，3 个 commit 已推）**：
> ① 该 spec 的 Task 1~77 全量产物此前一直未提交（235 项 `??` + 99 项 `M` 摞在别人分支的工作树上），已入库 854 个文件；② 修掉「仓库级普查冻进逐字节锁」这一类判据缺陷（同型 5 处：BP-71-8 全树 test 计数 / BP-72-8 `backend/data` 入向普查 / BP-74-1 引用派生辐射面 / Task 71 的传递 / 新发现的 `artifact_git_status`），新增共享模块 `backend/scripts/_census_lock.py`，普查量剔除但**仍现算并断言语义性质**，`report_digest` 改在剔除后内容上算；③ 补掉 5 条 GREEN 变异暴露的守卫洞（等价变异：判据只在合规数据上跑），改成「纯函数 + 合成不合规输入 + 注入口」，5 条全转 RED；④ 修 pre-commit 的假红（残缺 venv 抢 PATH 让行数门从未运行却报超限）。
>
> **剩余 5 个任务全为 `[-]`，阻塞均有实测依据**：`61`（真实 OO 9.4 F2 Word gate）、`63`（9 个 B 子码错型 + S33-REV）、`71`（容量 6000 会话真实负载：3030 未监听 / 无 OO 活动编辑会话 / evidence 五表 0 行）、`72`（Stage A 红：0/3290 required scenario 未真跑、`multi_resolver`=4、Task 66 rollback 隔离门 blocked）、`74`（第二半 261 处迁 `ContentMutationService.commit` 未做；终局判据要 14 条准则全零，`multi_resolver` 归零依赖 Task 36 供给）。
>
> **2026-09-02 关键路径进展**：定位并绕开了 wp_code **幻影码**缺陷 —— manifest 的 `_source_match()` 用正则从宿主 Vue 文件名 CamelCase 抽码，末尾可选字母吞掉下一个词首字母，产出 `D2A`/`G7L`/`H1F`（`wp_index` 里 **0 命中**），导致 Task 76 provisioner 对四份契约全部 unresolved 且给出的原因是错的（宿主底稿其实很多）。**未改那条正则**（一改三个 G7 宿主的码同时收敛到 `G7`，撞 RG-3 `MatcherOverlapError`，需先把 matcher 从「按 wp_code 路由」改成「按 entry 路由」）；改为新增显式裁决 `backend/data/workpaper_sync_entry_wp_code_adjudication.json`（真源 = 契约里冻结的 `template.relative_path` + 受管 `excel_name`），provisioner 改读裁决并 fail-closed。结果：宿主解析从 0/4 变 **3/4**（b60→`B60-1`、d2→`D2-2`、h1→`H1`；g7 按登记原因诚实 unresolved），definition 供给从 **4 契约/1 供给** 变 **4 契约/3 供给**（bundle 3→5、definition artifact 6→14，全 `approved` 且三槽真 definition，业务行一行未改）。
> **首个 published representation 仍为 0**：根因是**数据库外键层面的循环依赖** —— candidate 的 `content_version_id`/`source_representation_id` 都是 NOT NULL 外键指向 0 行的表，故 `finalizeCandidate` 结构上只能给既有 representation 加 generation；唯一首版生产者 `ContentMutationService.commit()` 又要求 adapter（要 representation）或合法 substrate（`canonical/published` 同为循环，或 `incoming/durable` = **一次真实 OO 往返**）。⇒ Task 70 的 0/3290 是这个环的**上游入口**，不是下游。另：`fake_bidirectional`=141 读的是 manifest 的 `migration_state`，与 representation 行数无关，产出首版**不会**让它变 140。
> V153 已应用（`working_paper_representation_candidate_event` 13 列在位）。不得把 spec 修订或 definition 供给当作生产验证。
> **Active 数一律以目录实扫为准，禁按增量推算**（本文件 §四「凭印象禁令」）。

> **2026-08-15 实扫结果（9 个目录逐一，供下一轮比对）**：
> ~~`e-cycle-…completion` **24/24**~~（**本日第二个归档** → `_archive/08-disclosure-notes/`） ·
> `i-cycle-…closure` **23/24**（`[ ]`1） ·
> `k-cycle-…closure` **19/25**（`[ ]`6） · `l-cycle-…completion` 3/26 ·
> ~~`procedure-trim-report-line-account-resolution` 16/16~~（**本日第三个归档** → `_archive/05-business-features/`） ·
> `workpaper-import-export-lifecycle-closure` 24/25（`[-]`1） ·
> ~~`x3-adjustment-entry-import-export` 33/53~~（**2026-08-16 归档，见上**） ·
> ~~`g7-column-alignment-and-extraction-closure` 24/24~~（**本轮已归档** → `_archive/08-disclosure-notes/`）
>
> 🔴 **2026-08-15 实扫又打翻两处旧记载**：①上一轮表头写「8 个目录全部带 tasks.md、无空壳」
> **不成立** —— `procedure-delegation-visibility-isolation` 与 `visibility-isolation-go-live-hardening`
> 两个空壳目录**又出现在 `.kiro/specs/` 下且 git 里是 `??` 未跟踪**（2026-08-12 曾记它们
> 「早在 2026-08-05 清理入归档区」）。故 Active 的准确表述必须区分「目录数 9」与
> 「带 tasks.md 的 spec 数 7」。②下表三行进度数严重过时：`i-cycle` 表内 9/25 而实扫 **23/24**、
> `k-cycle` 表内 5/25 而实扫 **19/25**、`x3` 表内无行而实扫 **33/53**。
> 均属并发会话在办，**未擅自改其详情行**以免与正在写的内容打架，只在此处如实登记实扫值。
> ~~`e-cycle-…completion` 已 **24/24** 全完成，可评估归档（属并发会话，留给其推进方裁决）。~~
> **已于同日（2026-08-15）复盘后归档** —— 复盘按十二维实证而非只看复选框：产物 47 路径
> untracked **0**（主交付 commit `2ee7929e`）· CI 7 个 E job 的 **37/37** 文件引用 exists+tracked
> · 后端 312 passed / 前端 294 passed · 变异**锚点 29/29 OK 0 MISS**（体系未漂移可复现）·
> 3 个幂等 `--check` 全 0 欠账 · 11 Req / **83 AC 零悬挂** · 41 Property 全被 tasks 引用 ·
> design 提到的 16 个符号全在生产代码可定位 · 三件套机器校验零诊断。
> 工作树当时的 4 个 dirty 文件（`governance-checks.yml` / `E1TabDisclosure.vue` /
> `note_template_soe.json` / `_note_structure_kit.py`）经 diff **逐一归因为并发 K 循环在途**
> （`carry_row_codes()` / `rowScopeFailure` 共享件 / K job step），非 E 遗留 ⇒ 未随本次归档提交。
> 🔴 **2026-08-12 实扫修正了表头三处过时记载**：①Active 写 6 而真实是 7；②「另有 3 个无 tasks.md 的空壳目录」已不成立 —— 其中两个（`procedure-delegation-visibility-isolation` / `visibility-isolation-go-live-hardening`）早在 2026-08-05 清理入归档区，而 `workpaper-import-export-lifecycle-closure` **有 tasks.md 且进度 3/25**，把它记成空壳会让一个在办 spec 从索引上消失；③Archived 549 → 550（本轮归档 `procedure-trimming-and-delegation-intelligence`）。再次印证本文件 §四 的「凭印象禁令」：完成度与数量一律实扫，别信上一轮写下的数。
**最高迁移**：**V150**（磁盘 `backend/migrations/V*.sql` 于 2026-08-24 实扫；V147~V150 为 AI chat/地址坐标相关迁移。新迁移实施前仍须再次实扫，`R1xx__` 是配对回滚脚本非同号冲突）
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

---

## 一、Active Specs

| spec | 进度 | 一句话 |
|------|------|--------|
| `workpaper-html-onlyoffice-bidirectional-writeback-closure` | **72/77** | **底稿 HTML ↔ OnlyOffice Excel/Word 真双向回写收口**（2026-08-24 新建，三件套处于 **2026-08-24 独立协议语义复审进行中**）。当前 source-backed 事实为 **185 个物理宿主 / 276 个挂载点 / 186 个 entry / 142 个独立入口 / 43 个父级重复入口 / 1 个不可达旧桩**；现存多数仍是 template-only/reload-only，保持假双向红基线。修订方案采用单次 business `ContentMutationService` commit、content revision ↔ representation generation 分离、template/instrumentation/contract immutable definition artifacts、shared OO room + per-user lease + room 级 callback route、frozen forcesave/close request、server last-applied ↔ client-confirmed 双基线、incoming sequence fence、staged artifact + DB pointer + orphan GC，以及 merged≠incoming 后 refresh/reopen。平台自有 Excel 模板允许受控 instrumentation，但 Excel identity、Word tagged SDT、真实两用户 callback/撤销语义均须先过 OO 9.4 黑盒门。每个 bidirectional entry 必须有持久化 test run、逐 scenario operation/version/representation/trace bundle 与服务端重算 evidence；全局 legacy 删除严格晚于 Task 70。**14 Req / 170 AC / 72 Property / 72 Task / 8 Wave**；当前仅 Task 1/2 的 discovery/characterization 标绿，生产开发继续暂停于 Wave 0 Task 3。终态要求未裁决、假双向、bidirectional 未验收、unreachable、evidence stale 五项全部为 0。；**2026-09-02**：全量产物已入库（分支 `work/2026-09-02-workpaper-sync-closure`，3 commit 已推）；剩余 5 个任务全 `[-]`（61/63/71/72/74），阻塞均有实测依据；definition 供给 4 契约/**3** 供给（bundle 5 条，3 条 projection_contract 全 approved）；published representation 仍 **0**（外键层面循环依赖，入口是 Task 70 的真实 OO 往返） |
| `advanced-query-hardening-wiring-closure` | **62/64** | **高级查询硬化接线收口**（2026-08-23 新建）。性质是**接线 + 关缺口，不是新建能力** —— `backend/app/services/custom_query/` 20 个文件里 **7 个模块在 `backend/app/` 全域 router 引用数为 0**（`query_orchestrator` / `execute_compatibility` / `export_service` / `writeback_preview` / `param_sql_builder` / `template_service` / `template_scope_adapter`），只被同包内部与测试引用 = 「additive 注入即死代码」教科书形态。<br>🔴 **红基线全部已入库**（`git status --porcelain` 实测 0 条，非并发在途）：后端 **75 failed / 20 passed**（`test_advanced_query_hardening_wave012.py` 60 + `test_custom_query_template_scope_hardening.py` 7 + `test_custom_query_templates.py::TestEnsureCustomQueryTables` 8）· 前端 **5 failed / 48 passed**。故任务完成定义 = 对应测试转绿 + 变异打红，不是「代码已写」。<br>**三个 dataclass 与 adapter 互不兼容**（自交付以来必 `AttributeError`）：`execute_compatibility.py:106-107` 已在读 `result.limit` / `result.offset`、`to_legacy_response` 已在读 `column.source`，而 `QueryResult` 无 `limit`/`offset`、`ColumnMeta` 无 `source`、`QueryRequest` 无 `source`/`year`/`filters`/`columns`/`sort`/`limit`/`offset`。<br>**安全侧四条独立实证（浏览器 + 真实 PG，非测试推断）**：① 三个只读端点 `indicators`/`wp-id-by-code`/`wp-sheet-preview` 仅 `Depends(get_db)`，**未认证直连全部 200**（响应约 700335/165/3117 bytes），其中 `wp_sheet_preview` 降级分支会调 `init_workpaper_from_template` **写文件** = 无认证端点触发副作用 ② 构建器 `query_builder.py` **全链零 `project_id` 注入**，认证 token 取 `limit=1000` 仅选 `project_id` 列，实际 **1000 行覆盖 9 个不同项目**，缓存键还写死 `"__query_builder__"` 跨项目共用命名空间 ③ 真实 PG **`statement_timeout = 0`**，全仓该词命中 0 处；`tb_ledger` 约 **6,971,441 行** ④ `JOIN_WHITELIST` 三处仅按 `project_id` 关联（`trial_balance→wp_index` / `adjustments→wp_index` / `projects→8 张业务表`）= 项目内笛卡尔积，且 `LIMIT` 施加在积之后、导出 `fetchmany` 无行数上限。<br>**分页是「声明了但从不存在」**：`custom_query.QueryRequest.offset` 声明后**全文件零使用**（14 个取数器签名均 `(db, pid, year, filters, limit)`，SQL 只拼 `LIMIT :lim`），前端两处却都在传 `offset: 0` ⇒ 业务视图**根本没有第 2 页**；`limit = min(body.limit, 2000)` 压进 SQL 使 `total` 恒等于截断行数。构建器侧 `order_by` 为空即无 `ORDER BY` 却直接 `.offset()`。<br>**两个必然报错/静默失败的存量缺陷**：`custom_query.py:2289` `SELECT id FROM working_paper WHERE wp_code = :code` —— **该表无 `wp_code` 列**（在 `wp_index`，同文件 L825/L921 就是正确 JOIN 写法）⇒ cell-writeback 的 workpaper 分支实际不可用；`except Exception → 200 {"rows":[],"error":str(e)}` 把超时/中断/列不存在全吞成成功 = fail-open。<br>**技术列与 PII**：15 张表 `fields` 全含 `id`/`project_id`/`is_deleted`/`created_at`/`updated_at`，`staff_members` 另含 `email`/`phone`/`user_id`；前端 `dsl.fields=[]` 是默认值 ⇒ 不选字段即命中「无 fields 默认全字段」分支，结果表第一列是 UUID。<br>**纠正一条调研误判**：前端 2 条红报 `canDo is not a function` 曾被判为生产 bug，实测 `usePermissionMatrix.ts:180` **确有 `canDo`**，真因是 `advancedQueryFrontend.spec.ts:48-51` 的 mock 只返回 `currentRole`（测试陈旧）。但它暴露了真问题：前端判据是 `canDo('edit','project_settings')`、后端是 `role ∈ (admin,manager,partner)`，**两套判据会漂移**。<br>指标树实测 **578057 字符 / 3089 节点 / 2766 叶子 / 3391ms** 一次性全量，`CustomQueryTab.loadIndicators` 每次挂载全量拉且无缓存。<br>**12 Req / 74 AC 零悬挂 / 24 Property 全整数且全被 tasks 引用 / 64 子任务分 10 波**（机器自检通过）。单一真源约束：项目可见性→`OwnershipGuard`、白名单门禁→`enforce_query_plan`（当前被私有 `_resolve_table` 旁路绕过）、预算阈值→`export_service`/`writeback_preview`/`PivotConfig` 既有常量、列分层→`table_whitelist`。归档区另有 5 个同域 spec，本 spec 作为其**收口/返工**立项。<br>🔴 **2026-08-23 收口现状：62/64 全交付**（余 19.2/19.3 为收口自身）。**红基线 75+5 → 0**，spec 守卫 **272 passed / 0 failed**；辐射面 42 文件 **593 passed**，相对 HEAD **新增回归 0**（剩 34 条全 pre-existing：33 附注模块 + 1 workpaper，均未触碰）；**变异 48/48 全 RED**（scope 26 + lazy 8 + PBT 14，零 GREEN/ANCHOR-MISS/WRONG-TEST）；**30 条 Hypothesis PBT** 覆盖全部 24 条 Property（`max_examples=100` 已验证真生效）。<br>**接线成果可量化**：立项时 7 个 router 零引用模块 → **仅剩 2 个**（`param_sql_builder` / `cross_sheet_trace_orchestrator`，见遗留）。<br>**浏览器 + 真库端到端实证**：三个只读端点 **200 → 401** · 构建器结果首列 UUID `id` → `年度`（`hasIdCol=false`）· 指标树首屏 **578,028 字符 / 3,089 节点 → 3,229 字符 / 25 节点**（0.56%，底稿分支单独占 539KB 证实其为主体）· 业务视图 **只有第 1 页 → 「本页 100 条 / 共 174 条」且第 2 页数据确为「抵债资产…」74 行** · 4 条 JOIN / 笛卡尔积 JOIN / limit=0 分别 400/400/422 · 表头**零英文残留** · 控制台 **0 errors** · EXPLAIN 实测被移除的 `trial_balance ⋈ wp_index ON project_id` 估算 **163,961 行**（base 1,210 行，放大 135 倍）而保留的 `⋈ account_chart` 仅 **1,505 行**。<br>**过程中抓出 11 个立项时未预料的缺陷**（详见 `#dev-history`），其中最典型五个：① `_apply_pivot` 用 `getattr(grid,"rows",None)` 取 `Grid` 从不存在的属性 ⇒ 透视**恒静默跳过**、total 一直是透视前行数（防御式回退掩盖契约不匹配）② `_canonicalize` 把裸 `object()` 交给 `str()` 得到含**内存地址**的串却判 `cacheable=True` ⇒ 同一逻辑查询每次算出不同缓存键 ③ ORM 数组列缺方言变体 + Python 侧 default ⇒ `test_template_config` 6 条长期红 ④ Dialog 指标树缓存**先发全量请求再查缓存**⇒ 该缓存从未节省过网络 ⑤ `derive_field_tiers` 三层无优先级，列名同时命中技术列与 PII 登记时**两层重叠**、该列会绕过 PII 角色准入（Hypothesis 随机输入抓出，定点守卫因真实数据恰好不重叠而覆盖不到）。<br>**自身守卫缺陷被变异检验抓出 4 处并修**：`MAX_*+1` 算期望值（判据自我实现）· 只断言符号 callable 的 grep 式判据 · 只测纯函数导致编排器丢弃排序键检测不到 · `main()` 出现在 docstring 里被文本判据误判（改 AST）。<br>**两项 UNVERIFIABLE 如实登记**：库中仅 auditor 与 admin（无 manager/partner），故「受限角色作用域过滤」与「manager 无 PII 权限」的真库端到端路径无可登录账号验证（**未为此写库建账号**），由 60 条定点守卫 + PBT + 变异 M11/M12/M22/P08 覆盖。测试对真实审计队列**零污染**（`audit:log:queue` before=0/after=0 实测）。<br>**遗留建议**：`param_sql_builder` 与 `cross_sheet_trace_orchestrator` 仍零引用（前者与构建器的 `_build_select` 功能重复、后者与已接线的 `cross_sheet_resolver` 重复），建议单独立任务裁决删除或明确定位；另 `year` 默认取当年（2026）而数据在 2025 使查询恒 0 行，非本 spec 引入。 |
| `dsh-agent-panel-integration` | 35/35 | **DSH Agent 面板平台化集成**（2026-08-21 新建，同日两轮加固）。把右侧 AI 面板从「iframe 嵌 dsh 原生 Web UI」改为「平台自建 UI + 后端受控引擎」，补四块能力：`@`mention 引用平台文档/地址坐标 · 附件上传+OCR · 输出选中转存项目笔记 · 复核提示词注入。<br>**性质是收敛+补全不是新建** —— 平台已有完整文档级对话链路（`DocAiChatPanel.vue` / `useDocAiChat.ts` / `doc_ai_chat.py` / `doc_ai_context_builder.py`，含 SSE 流式 + token 预算 + `adopt` 确认流），骨架复用，只补入口能力与失败可见性。<br>🔴 **立项三条实证**：① iframe 路线浏览器实测不通（dsh 原生 UI 自带 workspace 选择器 + 文件写入能力 + 无知识库转存/OCR，且 `dsh-sandbox-policy` 默认 `workspace-write` 与「不能改工作区文档」硬冲突）② **`extra_scopes` 是死代码（假绿第①源）**：`fetchAvailableScopes()` 请求 `/api/knowledge/folders` 后端**无此路由**（真实为 `/api/knowledge-library/tree`），404 被空 `catch {}` 吞 ⇒ `availableScopes` 恒空、面板恒显「暂无可选知识范围」，后端 `_search_extra_scopes` + `_check_folder_access` + `_check_doc_access` **自交付以来从未被真实触发** ③ 地址坐标库**无语义检索**（V1 `search()` 纯 substring、ACNR `_find_candidates()` 仅 fuzzy）。<br>**复用清单**（NFR-1 禁重写）：`llm_client` 熔断器/并发限流/单 system 合并 · `KnowledgeIndexService` + `knowledge_index`（pgvector 1024，坐标索引灌进去而非另建向量库）· `UnifiedOCRService.recognize()` · `ReviewPromptService.load_prompt(wp_code, sheet)` 三级降级 · `POST /api/knowledge-library/folders/{id}/documents`（`notes` 预制分类=笔记库，无「项目笔记」专属表故走文件夹承载）· `AIContentMustBeConfirmedRule` 门禁。<br>**失败可见改造三处**（反 fail-open）：`ContextBuilder.build` 失败由 `warning`+空上下文继续 → `error`+SSE 事件+终止 · `llm_client` 的 fail-soft 占位串（`[LLM 服务暂不可用…]` 等）被当正常回复落库 → 新增 `is_llm_placeholder` 判据拦截 · mention/OCR/笔记三链路各自独立 `try`（G7 教训：真操作与收尾共用一个 try 会被成功文案盖掉）。<br>**已交付纳入验收边界**：AC 1.1~1.8 前序会话已完成（`components/ai/DshPanel.vue` 折叠/拖拽 320~800px/badge + `ThreeColumnLayout` 接线 + `start-dev.bat` 集成 + `~/.dsh/storages/workspace.json` 注册），Task 18 保留布局壳换内容层、Task 17 按 `AI_CHAT_ENGINE` 条件化启动、Task 21 补守卫（此前**零守卫**）。<br>引擎二选一由 `settings.AI_CHAT_ENGINE` 单一决定（`native` 直连 vLLM 为默认 / `dsh` 经 Python SDK JSON-RPC stdio），dsh 侧 Cordis 组合只读（不挂 `dsh-tool-fs` 写分支 / `dsh-bash-sandbox` / `dsh-subprocess-local`），不可用时报 `engine_unavailable` **不静默降级**。`D:\DeepHorness` 视为 vendor 只读。<br>迁移 **V147**（枚举加 `address_coordinate`）。**12 Req / 97 AC 零悬挂 / 55 Property 全被 tasks 引用 / 28 Task 分 9 波**。<br>🔴 **第二轮加固（用户质疑「为什么要删 dsh，它能调子 agent 不是更强」后返工，用户对、我错）**：初版把「只读」错误实现为**「不挂任何工具」**，又用 `ContextBuilder` 预塞满上下文 ⇒ 剥夺了 agent 自主决定「需要看什么」的能力，而那正是 agent 的全部价值 ⇒ dsh 退化成「LLM 转发代理」，于是我量化出「12/77 AC 换零独有能力」并建议删掉它 —— **结论对但前提是我自己造成的**。**「只读」的正确定义是语义只读：工具本身只做读，不是没有工具**；审计场景（交叉核对、多循环并查、账龄↔坏账准备匹配性）读多写少，恰是 agent 主场。<br>**找到比原设计干净得多的接入路径**：dsh 原生带 `@deepseek-ai/dsh-mcp-client`（stdio + streamable-http 双传输、自动重连带预算、工具名命名空间隔离），而平台**已有自己的 MCP server**（`tools/gt-plan-mcp/server.py`，FastMCP，5 个只读 tool）⇒ 新建 `tools/audit-data-mcp/`（7 个只读 tool：wp_list/wp_read/tb_query/addr_lookup/kb_search/note_read/review_prompt），**dsh 与 Kiro 共用同一 server**，且不绑 dsh 版本（v0.1 的 breaking change 影响不到 MCP 协议层）。能力分层：`native`=单轮问答（ContextBuilder 预组装，默认）· `dsh`=多步 agent（经 MCP 按需拉取 + 子 agent + PTC）。<br>🔴 **数据安全核心决策（实证驱动）**：`make_bulk_visible_filter` / `gate_wp` / `_check_doc_access` **全是 async 且依赖 db session + current_user**，独立进程的 MCP server 拿不到 ⇒ 若直连 DB 就必须重写权限逻辑＝必然出漏洞 ⇒ **MCP server 零直连数据库、零 DB 凭据，全部数据经 REST 回调带 scoped token**，权限判定 100% 复用既有实现，MCP server 退化为协议转换层。配套 11 条安全 AC：scoped token 四要素（`scope=ai_chat:read` + `project_id` + `session_id` + 短时效 `exp`，**不透传用户长期登录 token**）· stdio 传输不监听端口 · 子进程环境变量清洗 · **`failOnStartupError: true`**（dsh 默认 `false` 会以「零工具」激活让 agent 空口编答案＝fail-open）· 提示注入按数据而非指令定界 · 会话隔离 · MCP 端点独立频率/数据量上限 · 工具调用留痕（审计平台自身操作也要可审计）。<br>**又抓到一个既有漏项**：`ExportMaskService` 已有且 **10 个文件在用**（`wp_chat_service`/`note_ai`/`wp_ai_service` 等），而 **`doc_ai_chat.py` 不在其中** ⇒ 对话链路从未脱敏，agent 自主拉取比单轮问答更需要，本 spec 一并补齐两路同口径。<br>**全本地化实测（AC 12 专章）**：vLLM chat `127.0.0.1:8100` ✅（`Kbenkhaled/Qwen3.5-27B-NVFP4` healthy）· PG/Redis/OnlyOffice/Metabase ✅ · **Embedding bge-m3 `127.0.0.1:8101` 🔴 DOWN** ⇒ Requirement 4 的坐标向量索引依赖它，已把「embedding 可用」写成 Task 7 的**显式前置**（AC 12.6 + Property 54），未就绪则阻塞登记，**不得以「索引已建但检索不到」形态假性交付** · 独立 OCR 容器未见（印证 `OCR_SERVICE_URL` 未配、走 in-process）。<br>**本轮又修了自己两个判据缺陷**：① 「Property 全被引用」判据把守卫任务的**区间引用**（`Property 1~26、36~55`）也计入 ⇒ 变异删掉 Task 18 的单点 `52` 仍判绿 ⇒ 改为**只认实现任务的单点引用**，区间不计（区间会掩盖「某 Property 无实现任务承接」的真实缺口）② 「stdio 不监听端口」查 `"不监听"` 字面，被 `SHALL NOT 监听` 的措辞躲过 ⇒ 改查 `transport: stdio` + 正则 `SHALL NOT\s*监听网络端口` 共现。修后 5 条反向自检全 RED。<br>顺带修 2 个真悬挂 AC（Requirement 2 重写后编号 2.5→2.7，Task 15 仍引旧号；12.6 新增未接任务）。三件套机器校验 + **5 条反向自检全 RED**（故意破坏 Property 连号、Validates 格式、悬挂 AC、漏引 Property、删复选框，各自只打红预期项）。<br>🔴 **立项当日复盘（不看调研二手结论，逐条实证 design 地基）查出 4 个真错 + 3 处漏记，已全部落地修正**：<br>① **迁移枚举类型名错，一跑必报错** —— 初版写 `knowledgesourcetype`（SQLAlchemy 类名小写形态），库中真名是 **`knowledge_source_type_enum`**；先例 V042 早就干过同一件事（枚举加 `knowledge_doc`）却没被参照。顺带从 V042 注释补一条 design 漏记的硬约束：`ALTER TYPE ADD VALUE` 新增值**同事务内不可立即使用** ⇒ 坐标索引首次构建必须在迁移之后的独立运行时调用，不得把 DML 写进同一迁移文件。<br>② **AC 5.5 / Property 11 是永不触发的判据（假绿）** —— 实测 `.env`/`.env.example` **均未配置 `OCR_SERVICE_URL`** ⇒ `UnifiedOCRService.recognize()` 恒走 in-process 分支（L99），而 `OCRServiceUnavailableError` 的三个抛出点（L95/L125/L136）**全在 `if OCR_SERVICE_URL:` 的 HTTP 分支内** ⇒ 该异常在当前环境不可达，写了也验不到。已改为「覆盖两种模式失败形态（HTTP 异常 + in-process 引擎链 Paddle→Tesseract→MinerU 全失败）且判据用注入式，不依赖部署恰好处于某模式」，新增 Property 38 作为 Property 11 的加强版。<br>③ **🔴 发现一个可利用的 XSS（原 spec 完全没覆盖）** —— 现状 `DocAiChatPanel.renderMarkdown()` 是 **8 条手写正则替换后直接 `v-html`，零 sanitize**，除它处理的 5 类语法外其余 HTML 标签原样透传。本 spec 引入 mention 引文档 / OCR 文本 / 知识库内容进上下文后形成真实利用链：攻击者上传含 `<img src=x onerror=...>` 的知识库文档 → 诱导审计师提问使 AI 复述 → 在审计师浏览器执行脚本，而 **token 存于 `localStorage`**。平台**已装 `marked@18` + `dompurify@3.4.5` 且已有 `composables/useSanitize.ts`（5 个文件在用）**，唯独这条渲染路径一处未用。⇒ 新增 **Requirement 10** + Task 20，渲染链改 `marked.parse()` → `useSanitize()` → `v-html`，**删手写正则不留两套路径**，mention/OCR/AI 输出共用同一 sanitize（不为「AI 输出应该安全」开例外），并同步修既有 `DocAiChatPanel`（4 个宿主受益）。全仓 `v-html` 共 8 处 / 7 文件，dompurify 覆盖 5 文件 ⇒ 存在缺口，本 spec 只修对话相关那条。<br>④ **配额约束漏记** —— `LLM_RATE_LIMIT_PER_MINUTE` 默认 **10 次/用户/分钟**（`rate_limiter.py:L112` 强制），对话追问极易触顶且前端无任何提示。⇒ 新增独立配置 `AI_CHAT_RATE_LIMIT_PER_MINUTE`（**不放宽全局值**以免波及底稿 AI 辅助/报告生成等其他调用方）+ `retry_after` 倒计时可见（Property 36/37）。<br>⑤ 死代码机制描述**不精确**：原写「空 `catch {}` 吞掉」，实测是 **`if (res.ok)` 无 else 分支**；且 404 成因已坐实 —— `knowledge_base.py` 只有 `/api/knowledge/libraries`（两段）与 `/api/knowledge/{category}/documents`（三段），前端请求的 `/api/knowledge/folders` 两段但字面不匹配，匹配不上任何路由。<br>⑥ 漏 AC：会话附件 `storage/ai_chat/` **无清理策略会无限增长** ⇒ 补 AC 5.10 + Property 39。<br>⑦ 复盘中还修了**自己的判据缺陷**：回归判据初版用「design 全文不含错名 `knowledgesourcetype`」，被我有意保留的「初版曾写错」历史说明误判成 False ⇒ 改为只扫 `sql` 代码块内的 `ALTER TYPE` 语句 + 附带查「迁移块内无 DML」（判据形态从全文等值型改为归因型）。<br>**已知风险登记**：Task 5 的 token 裁剪顺序（mention 优先于 RAG）是设计决策，实测不佳须回 design 改配额不在实现打补丁 · Task 16 子进程池在 6000 并发目标下不可行，本 spec 只保开发态 · Property 7 的「索引模块内无坐标标签字面量」须 `stripComments()` + 反向自检否则是弱判据。<br>🔴 **2026-08-22 收口现状：35/35 全交付**（Task 35 之后又补四处）。守卫实测 backend **722 passed** / frontend **289 passed / 16 files**；变异 **41/41 真跑全 RED**（M01–M41，GREEN / MISS / WRONG 各 0；含 15 条 Task 33 + 12 条假绿修复 + 8 条 MCP 取数 + 6 条渲染宿主）。<br>**Task 35 之后补的四处都是假绿家族的不同形态**：① **MCP 7 个只读工具的取数责任真空** —— Task 25 拥有工具契约、Task 26 拥有调用方，**取数实现谁都不拥有**，故单开 `dsh-agent-panel-mcp-data` job 用「给定真实数据工具返回非空」补齐（叶子聚合 / JSONB `parsed_data` / 可见集 `UNION ALL` 在 sqlite 上给假绿）；② **Task 33 的 10 条变异只做了静态检查、从未真跑** —— 真跑暴露 **6 GREEN + 1 WRONG**（跑错测试套 · 调用签名写错被 `raises(Exception)` 兜住 · 恒真 `or` 子句 + 惰性 import 无人触达 · grep 式判据 · 判据打在另一套同名实现上 · **多个不同根因共用同一错误码**最隐蔽：`engine_unavailable` 被四处共用，只断言错误码等于什么都没断言 ⇒ 门类判据必须落到「门后副作用一次都没发生」），修完 15/15 全 RED，变异脚本自身也加固（`expect_test` 必须是真实测试名 + 反向自检）；③ **`dsh-agent-panel-backend` job 缺 postgres service** ⇒ 无 PG 时 **183 条守卫静默 skip 而 job 仍以 0 退出**（sqlite 下 310 passed / 183 skipped），补 service 后在**全新空库**上又抓出 3 个只在空库出现的 CI 缺陷（裸 `postgres:16` 无 `vector` 类型使建表整步失败 / 缺 `create_all` 引导致空库直跑迁移 124 个失败而 `run_pending()` 仍返回成功 / V147 约束静默 no-op），空库实测 **508 + 189 + 25 passed、0 skipped**；④ 🔴 **Task 15 的两个组件从未挂载** —— `ChatMentionPicker.vue` 与 `ChatContextInspector.vue` **零宿主引用**（组件都在、各自 vitest 23 条全绿、Task 15 标 `[x]`，但没有任何宿主 import 它们），⇒ 浏览器里用户**打不出 `@`、看不到 Context Manifest**，Requirements 5.1 / 5.4 / 5.7 / 5.9 在运行产品里没实现、Properties 12 / 13 无浏览器落地；判「某能力接没接」必须落到**唯一消费方 + 有渲染宿主**，M36/M37 精确复刻「import 在、标签没了」这个只接一半的形态。<br>**三个 CI job**：`dsh-agent-panel-backend`（floor **697** = `dsh_agent_panel/` 508 + 非 PG 依赖 6 文件 189，两步各带「passed 低于实测基线或出现**任何** skipped 即打红」的数值硬断言，比较用 `python -c` 而非不可维护的 grep 正则）/ `dsh-agent-panel-frontend`（**289**）/ `dsh-agent-panel-mcp-data`（**≥25**）。🔴 带 **pgvector service** 的是 **backend 与 mcp-data 两个**（frontend 是纯 vitest 不连库），两个 job 的引导步骤现已逐字一致。<br>**当前仍属 Active**：产物刚 `git add` 尚未 commit，未归档；clean checkout 下的 CI 有效性待 commit 后才成立。**收口全量实证详见 `.kiro/specs/dsh-agent-panel-integration/CLOSURE.md` 与 `GUARD_MANIFEST.md`**。 |
| ~~`e-cycle-extraction-formula-and-disclosure-completion`~~ | **已归档** | → `_archive/08-disclosure-notes/`（2026-08-15 复盘后归档，全交付 24/24，主交付 commit `2ee7929e`）。E 类（E0/E1）取数/公式/披露收口。**账户级取数**走 `tb_aux_balance` 的 `aux_type='银行账户'` 维度（此前叶子口径恒 1 行「银行存款」汇总，客户 1002 不分户）⇒ E1-3 出 **22 行逐户**（含开户银行 + 账号，同账号跨行按账号聚合）、E1-10 **保留零余额账户**与金额明细的全零过滤口径显式分离。<br>**浏览器实测抓到两处真实缺陷**：① Property 28 端到端失效（`resolveRestrictedRows` 末尾按**数组下标**重算全部行 id，把 `nextRestrictedSeq` 算好的稳定序号覆盖掉 ⇒ 删 `custom_甲_2` 再新增 `custom_乙` 落库 id 仍是 `_2`，按 row id 索引的历史 reason/金额**串到新类别**上）—— **已修**，原 42 例守卫全绿而缺陷仍在，因为没有一条把纯函数结果串到 `resolveRestrictedRows` 输出；② E1-3 multi 版金额被静默抹零（先点`仅人民币`再点`人民币及外币` ⇒ 22 行金额全变 `-` + 一条错的「审定合计 0.00 ≠ TB 4467536.12」横幅）—— **登记未修**，根因是宿主 `seedFromFourTable()` 只在 `onMounted` 跑一次且 `seedRowsKey` 有 persist-first 短路，种子形态一会话内只按当时 variant 定型一次；**非本 spec 引入**（改造前叶子口径在任何路径下都被抹零，本 spec 把它改善为「先开 multi 即正确」＝部分修复），改法要动种子键按 variant 分离＋新守卫，建议单独立任务。<br>**变异检验 29 条全 RED**，且靠**覆盖面分母**（`SPEC_GUARD_FILES` 17 个守卫文件）抓出一个隐蔽欠账：首轮「21 条全 RED」时仍有 **7 个前端守卫文件从未被任何变异打红** ⇒「变异全红」与「全部守卫都被反证过」是两件事，补 M22~M29 补齐。<br>**Property 34 字面冲突查清**：任务原文「原币/汇率列留空」**对本位币账户不成立且必须不成立**（不下发 `openingFc` 会被 multi recalc 抹零，`fxRate:1` 是恒等事实非反推）；只有非本位币才留 0 + `note` 提示。载荷侧键集实测**根本无原币字段可反推**（全库 308 行 `currency_code` 全 CNY、`opening_fc` 全 NULL）。<br>**终态**：后端 `-k "e1 or e_cycle"` **368 passed** / 1 skipped · 前端 137 suites **568 passed** · CI 挂 `e-cycle-extraction` + `e-cycle-frontend` 两个 job（另有 5 个既有 E job）。<br>**listed 侧 4 项 UNVERIFIABLE 如实登记**（全库 8 个项目 `entity_type` 全 `soe`，listed 披露 Tab 恒显「当前项目不适用」，按约束未改任何项目的 `applicable_standard_v2`）＋ 各配 3~4 类替代证据。收口**零写库**（基线/收尾双 SELECT md5 逐条相同 + `updated_at` 全早于会话 + 网络层 181 条无业务写请求三重证据），清掉本 spec 276 个 `_wip_e_*`。 |
| ~~`i-cycle-extraction-formula-and-disclosure-closure`~~ | **已归档** | → `_archive/08-disclosure-notes/`（2026-08-15 复盘后归档，全交付 **26/26**）。<br>🔴 **归档前复盘（Task 25）先解掉一个阻断项：本 spec 的两个 CI job 在干净 checkout 下必红** —— Task 10 的数据产出（4 张表补 `columns`）从未入库（HEAD 里仍 `cols=0`），且 **7 个正式产物 `??` 未跟踪**，其中 4 个被 CI 直接引用（`test_i_cycle_row_code_evidence.py` / `test_i5_absent_account.py` / `iCycleDynamicRows.spec.ts` / `iCycleAdjudicationSeed.spec.ts`）⇒ pytest/vitest 遇不存在路径整 job 红。Task 21 的 CI 接线守卫用 `Path.exists()` 判**工作树**故抓不到，已登记「应改判 `git ls-files --error-unmatch`」。<br>🔴 **复盘抓出 3 个真错：行维度三向从来没人比过**。原三向（Property 16）只比**列**、`_SRC_DYNAMIC_MARK_COUNT` 只锁**源侧**扩位数，于是 ① I1 上市「无形资产情况」第 33/34 行是 `（2）其他减少` + `……`，源模板 `A43:A44` 是 `（2）失效且终止确认的部分` + `（3）其他减少` ⇒ **减值准备减少段丢了一个真实披露项、并凭空多出第 4 个可扩位**（账面原值与累计摊销两层都有该行，只减值准备层没有 = 从 H1 模型复制漏改；`h1/h7/h8ListedDisclosureModel.ts` 同形态，已登记给 H 循环）；② I1 国企同表是 **48 行 / 10 个类别**（缺「其他」、「矿产权」被拆成「采矿权+探矿权」、「特许经营权」写成「特许权」、首类别是「软件」）⇒ 新建项目附注开局即错类别（运行态推送的 52 行是对的，错的只有 seed 路径）；③ `I1_LISTED_DEFAULT_CATEGORIES` 是**第二份类别真源**且 3 个 label 与源模板不符，而**生产消费的正是这份错的**（`useI1Disclosure`×5 + `I1TabDisclosureListed`×2），Task 12 交付的 `resolveI1Categories()` 反倒**生产零消费方 = 死代码**。<br>**为什么全部逃过 38 张列契约 + 12 条扩位基线 + 14 条变异**：前端行模型与模板 rows 是**同一处错**（同批生成）⇒ 任何「模板 ↔ 载荷」自洽型判据两侧一起错、仍自洽。只有拿源 xlsx 当第三边才抓得到。<br>**修复**：前端行模型 + `impairDec` 求和项 + 类别默认值改为派生（key 走 `I1_STANDARD_TO_LEGACY` 保留历史短 key）；幂等脚本新增 `_I1_LISTED_TABLE1_ROW_LABELS`（38 条）+ `_normalize_i1_listed_table1_rows()` **独立前置步**（共享 kit 的 `carry_expandable_rows` 在「新骨架扩位 < 旧数」时会把多出的旧扩位插回来且无 opt-out，而本 spec 边界禁改共享 kit）+ `_i1_soe_table1_rows()`（52 行，类别由 `i1_asset_categories` 派生，脚本内零类别字面量）。<br>**守卫 +16**（后端 Property 43 七条 → 199 passed；前端 Property 44/45 九条 → 24 passed），**免断言项 10 条逐条登记实证理由**（「源侧标记 ↔ 模板 expandable」实测**不是** 1:1，写成断言即锁死错值；我第一版 4 条空话理由被自己的 ≥20 字理由闸打红）。**变异 14 → 19 条，新增 5/5 全 RED**、恢复后零残留。<br>**零回归用归因型判据**（禁 stash/HEAD-swap）：后端辐射面 60 文件 AFTER 32 red / BEFORE 39 red ⇒ 新增 **0**、**顺带修好 7 条**，其中 `test_note_k_row_code_evidence::test_shared_table_manifest_has_no_drift` 是 **K 循环的守卫本来红着被我这处 soe 行修复带绿**（「修对了而不只是自洽」的独立印证）；前端辐射面 94 文件 / 3133 tests，5 个失败文件回退我的改动后失败数完全相同（19/341）⇒ 全属并发会话域。<br>**入库按归因型分区暂存**（`git hash-object -w` + `update-index`，不动工作树）：`note_template_{listed,soe}.json` 只入 I 循环 5 个章节（另 33 个并发会话域章节不带）· `prefill_formula_mapping.json` **在 HEAD 上重放本 spec 幂等脚本**得 desired（工作树里该文件 394 个块跨全循环变动，一个不带）· `wp_code_overrides.json` 只入 `市场平均收益率2017: skip`（不带 L 循环两处）。**入库前用「模拟干净 checkout」跑两个 job 的完整命令，汇总 rc=0**。<br>**另修三件套 10 处错基线**（含 requirements.md **两个重复的 `## Glossary` 段**、「6/6 全部错」实为 11/12、「12 类」实为 11 类、「I3~I6 各 0 处扩位」漏了 I5 两版各 1 处、「`=#REF!` 15 格」实为 20 格、design 把两个**已存在**的 `fix_*` 脚本写成「新建」、`columns` 位置写错、`iCycleAccountScope` 复用工厂的**有意偏离**未登记），新增 AC 5.8/5.9/6.5/7.7 与 Property 43/44/45 承接本轮修复。<br>**如实登记**：Task 6 的 `diagnose_i_cycle_rowcode.py` 磁盘与 git 历史双查皆无（推测当时以 `_wip_*` 形态写、被 Task 24 清理删掉），不被任何 CI 引用且职能已被 `verify_i_cycle_live.py` 的 D1/D4 覆盖 ⇒ 按「功能已覆盖」结案，不为凑文件名重建空壳。<br>**Task 24 的 5 项补测抓出 6 个缺陷**（3 个用户可见）：① 平台级共享件 `adjudicationPrefillPlan` 在**四表余额全为 0** 时谎报「补填 18 格」并把 18 个 0 写库 —— 模块头第 3 条「本项目无此科目 ≠ 为 0，不写 0」只堵了入口 A（槽未命中），漏了入口 B（**槽命中但金额为 0**），新增 `zeroSkipped` 桶，受益 11 个审定表 Tab；② I1 soe「+ 增加资产类别」**四重静默**（无提示/无新行/无库写入/控制台无 error）—— `addI1SoeCategory` 返回 `{layers,key,seq}` 被当数组用抛 `TypeError: layers is not iterable`，再被裸 `catch { /* cancelled */ }` 吞掉；③ I2 上市「删除费用性质」**整页白屏** —— `useI2Disclosure` 写了 `removeNatureRow` 实现却漏在 return 清单，崩溃还打断 debounce 保存致用户刚录的行丢失；④ I5 溯源面板 absent 态被「禁空洞卡片」整块隐藏（两个面板都修，新增平台级三态判据 `isTbSourceAbsent`，注意 I5 实测 `resolved_from` 是 `'fallback'` 不是 `'none'`）；⑤ I1 listed 空名兜底成「其他」造重复列；⑥ `autoFillFromSources` 返回类型漏 `unmatched`/`fuzzyMatched`。<br>**守卫 4 文件 / 72 tests，变异检验全 RED**（`i1DisclosureAddCategory` 的变异复现出**精确异常字符串**）。**新增假绿形态：测了 model 层就以为接通了** —— `iCycleDynamicRows.spec.ts` 把 model 层测足且用法全对，但 composable 层零测试；新建 `iCycleComposableExports.spec.ts` 用「从 SFC 抽真实解构键 → 与 composable return 键做包含断言」锁死。<br>🔴 **工具链两条硬实证**：`get_diagnostics` 对**类型不匹配漏报**两次（TS2345×2 / TS2353×1 全报 No diagnostics），`tsc --noEmit` 精确报出行号（全量 2059 → 2056）；但 `tsc` **不解析 `.vue`**（本仓 805 个 TS2307 即此因）⇒ SFC 解构未导出成员这类**整页崩溃**需 `vue-tsc` 或运行时守卫。<br>**方法论纠正**：一度跑前端全量（1999 files / 483s）得「73 files failed」虚惊，抽样单独复跑只剩 1 真红 ⇒ 绝大多数是 4-worker 资源竞争 flaky；改串行辐射面 230 files / 224 passed，剩 5 红经 `git status` 归因于并发会话改了 `note_template_{listed,soe}.json`（→ 已单独立项 `guard-assertion-attribution-refactor`）。<br>**遗留登记**：I1-10/I1-11 可编辑金额列未接 `WpAmountInput`（同行 `50000.00` 与 `9,871.40` 两种格式）→ 已单独立项 `amount-input-migration-and-column-typing`。实测数据 4 次 `--restore` + `--diff` 全「无漂移」。 |
| ~~`guard-assertion-attribution-refactor`~~ | **已归档** | → `_archive/06-engineering-governance/`（2026-08-16 全交付 **8/8**；收口 commit `9f97e6a2`+`a5040e55`）。**变异 18/18 全 RED**、串行验收 264 passed、后端对照组 61 passed。Task 4 修了初版一个真实假绿：l2l4 用 `stripComments` 全文件 `includes` 对巨型墓碑块不可靠（`raw=2/stripped=2`）⇒ 改 `declaredNoSyncInCoverage` 只截活跃数组体；并发 L2 接线后 `[类A]` 正确变红即真实世界验证。**🔴 Task 4 的 l2l4 修复寄居 l-cycle 未跟踪文件（带其 23 个 TDD 待办红）、不由本 spec 引入 git，随 l-cycle 提交落地**。**守卫判据归因化改造**（全局等值型 → 归因型）。立项直因：`disclosureSharedTableRowScope.spec.ts` **7 条断言全 RED**（`{listed:23,soe:6}` vs 实测 `{24,8}`、29 vs 32、15 vs 18、15 vs 26、4 vs 2…），因果链已实证 —— 2026-08-12 K 循环 `fix_note_k_report_row_codes.py` 改了真源 `note_shared_table_segments.json`，改动方同步了生成器 `EXPECTED_COUNTS` 与后端 `test_note_shared_table_segments.py`（都在后端视野内），**前端守卫属于另两个 spec，改动方 CI 视野里没有它** ⇒ 同一数字 3 处副本、**3 个 blocking job 在干净 checkout 下必挂**、且一条规模数字打死同 `it` 内 6 条仍然成立的归因断言。<br>判据形态分级：A 违规清单为空 / B 地板天花板 / C 包含式重点项（可用）· D 全局等值 / E 跨文件抠数字再等值（**禁用**）。核心替换是把 `counts).toEqual({23,6})` + `tables.length).toBe(29)` 换成**结构不变式** `counts.listed + counts.soe === tables.length`（替代两个硬编码且判据更强）。另拆 `MISSING_SYNC_PATH`（6 = 4 永久豁免 + 2 真实缺口）使「真实缺口应为 0」成为可收敛目标，并解耦 `l2l4DisclosureWiring` 用正则抠数字的形态 E。**4 个被改文件里 3 个属于别的 spec**（判据缺陷的固有属性）。 |
| ~~`amount-input-migration-and-column-typing`~~ | **已归档** | → `_archive/06-engineering-governance/`。**可编辑金额控件迁移与列类型判据**。存量实测：`el-input-number` **4260 处 / 798 文件**，其中带 `:formatter`（EP 2.13.6 无此 prop ⇒ 确定空操作）**80 处 / 13 文件**（memory 记「40+」，实际翻倍）；`WpAmountInput` 已覆盖 682 处 / 118 文件；疑似金额列违规 **1064 处**（粗判候选）。<br>🔴 **判据必须先行**，两条理由都来自 I1-10 浏览器实测：① **旧探针盲区** —— I 循环 Task 18 结论是「`:formatter` 命中 0 处，合规」，而 I1-10/I1-11 用的是 `el-input-number` + `:precision="2"` **根本没写 `:formatter`**，判据应是「金额语义列是否用了非 `WpAmountInput` 控件」（假绿第②源）；② **反向边界是碰巧成立** —— 「年限列不带千分符」成立的原因是 `el-input-number` 对所有列都不做千分符，一换 `WpAmountInput` 就会把「使用期限 1000 年」渲染成 `1,000.00`，而现有反向断言在未迁移代码上**恒真、无区分能力**。<br>实测证据：同一行内 `50000.00`（可编辑）与 `9,871.40`（只读派生）**并排两种格式**。分批：批 1 = 80 处 formatter 空操作 · 批 2 = I1-10/I1-11 · 批 3+ 按循环。探针禁用固定字符窗口（Task 18 首版 400 字符窗口误报 22 处，全是 `width:100%` 的 `%`），一律按 `el-table-column` 块配对扫描。`:precision` 不擅改（`使用期限(年)` 显示 `10.00`，年限是否允许小数待业务确认）。 |
| ~~`k-cycle-extraction-formula-and-disclosure-closure`~~ | **已归档** | → `_archive/08-disclosure-notes/`（2026-08-12 全交付 25/25）。K 循环（K0~K13）「四表入库 → 底稿取数 → 披露表 → 附注模块」全链收口。改正 **9 处 row_code + 4 处方向声明**（分级：4 ACTIVE_WRONG / 1 SILENT_EMPTY / 其余 TRACE_ONLY），K1/K2 收进声明真源，K6 补 `adjudication_prefill`，K1/K2/K4/K6 补三口径 `parent_check`（**真实库当场抓到某项目 `trial_balance` recalc 父子双算，正好 2.00~3.48 倍**，两口径版本查不出 —— 这是三口径存在的全部理由），公式预设 66 项改正 + 26 个披露块建块，附注段首码 4 张共享主表补 6 码（**利息行四准则零命中故不造码**），`expandable` 标记补 26 行（源 29 处，差额 3 处逐处登记），列头两版分变体 12 张**正向锁死差异**，K11「披露表按负数填列」**从零实现**（原状只有注释与界面文案、代码零翻转）。<br>**守卫 24 个文件 / 变异 110 条全 RED**（0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST），CI 挂 `k-cycle-extraction-formula-closure` + `k-cycle-frontend` 两个 job；八个幂等脚本 `--check` 同时归零。<br>**浏览器实测（Task 25）抓到 2 处真缺陷**：① K4 两张表标签列 key 是 `bond_name`（连库查落库 **0 行** ⇒ 改成 `label`；K7 的 `grant_item` 落库 **2 行** ⇒ 登记豁免不改，一刀切会让那 2 个附注的该列数据读不出来且不报错）② 平台共享判据 `isTbSourceAbsent` 漏判 `empty_reason` ⇒ K6 的「本项目无此科目」被伪装成一片 `0.00`（后端算对了、前端判据是另一套，**四层守卫全绿只有浏览器暴露**）。<br>**两项登记待裁决（不在本 spec 作业面）**：`disclosure_notes` 全库 `expandable` 行 = 0（模板 147 个未回填既有 293 个 note，Task 18 成果对既有 8 个项目不可见）· `sync-from-workpaper` 的 409 `STANDARD_MISMATCH` 与 200 都无可见提示（后端话术完全可操作但前端丢掉了）。<br>**🔴 归档 commit 有意不含两个共享数据文件**：`backend/data/prefill_formula_mapping.json`（工作树 +2516 行）与 `note_template_soe.json`（+364 行）混着并发会话对子公司权益章节的列 key 改名（`registeredPlace`/`principalPlace`/`holdingRatio` 等，`_aligned_at` 为 08-09/08-10）—— 那是**行为性**改动、须由其自己的守卫验证，替它提交无法归因（同 g7 归档时的处置）。**代价与恢复手段**：干净 checkout 下 K 循环的数据类守卫会红，跑七个幂等脚本 `--apply` 即可从任意基线重放（`fix_k_cycle_prefill_presets` / `fix_k_cycle_disclosure_presets` / `fix_note_k_report_row_codes` / `fix_note_k_pl_structure` / `fix_note_k_liability_structure` / `fix_note_k_complex_structure` / `fix_note_k_expandable_rows`，本轮已验证从被变异污染的状态一次恢复且 `--check` 全归零）。 |
| ~~`g7-column-alignment-and-extraction-closure`~~ | **已归档** | → `_archive/08-disclosure-notes/`（2026-08-15 全交付 24/24，commit `83ccf630`）。G7 长期股权投资列结构对齐与取数闭合。补上「源 xlsx ↔ 模板 seed ↔ 运行时载荷」三向锁死的第三条边（56 个偏差点 → 0），并新增立项时不存在的**第四边：渲染层**（浏览器实测发现两级表头 **0/38 张从未渲染** —— 模型的 `group` 是 additive 死代码，任何 `.vue` 零引用；修复后 20 张）。契约覆盖面 **11 → 38 张**全部运行时表，顺带修掉 15 处此前三条守卫**结构性看不见**的标签列头原文偏差。<br>**修掉一个平台级假绿**：`_note_structure_kit` 的 `--check` 弱于 `--dry-run`（24 个幂等脚本共用）—— 改坏模板一格从报 0 欠账变为报 2 欠账，此前该假绿让所有幂等证空转。<br>**收口复盘追加修 1 项 fail-open**：两个披露 Tab 的 `syncToDisclosureNotes()` 把真同步与收尾刷新塞进同一个 `try`，同步失败会被收尾的成功文案盖成「同步成功」⇒ 拆两段 try（真同步失败 `console.error` + `ElMessage.error` + **return**），错误文案下沉共享 helper `g7DisclosureSyncFeedback.ts`。<br>**终态**：前端 G7 全域 49 文件 **887 passed** · 后端 G7 主域 **2297 passed**（2 例失败已三层归因为并发 K 循环在途）· 变异 **12/12 全 RED**（GREEN=0/MISS=0/WRONG=0）· `--list` **15 锚点**静态自检通过 · CI 挂 `g7-column-alignment` + `g7-column-alignment-frontend` 两个 job。<br>**立项时记的「10 个正式产物 `??` 未跟踪」已解除**（commit 含 16 个新文件，facts JSON 与全部守卫本体已入库，干净 checkout 下 CI 可跑）。 |
| ~~`l-cycle-extraction-formula-and-disclosure-completion`~~ | **已归档** | → `_archive/08-disclosure-notes/`（2026-08-16 全交付 **26/26**；数据修复 commit `cd298ad1`、脚本健壮性 `445b540b`，此前 `aa51f7b3`/`69fffdfe`/`5ff15c02` 三个 commit 交付守卫与实现）。L 类（L0~L8 借款/应付债券/长期应付款/递延收益）取数公式与披露收口。**改正 5 处审定表科目码错位**（L2 2501→**2231**、L4 2601→**2502**、L5 2502→**2701**、L6 2701→**2711**，L7 2801→**4 × PLACEHOLDER**：递延收益在 L7 无 TB 科目可依，按「宁缺勿造」不硬凑）+ **2 块整块迁移**（`明细表L5-2`→`L4/应付债券明细表L4-2`、`明细表L6-2`→`L5/明细表L5-2`，cells 逐字不动 —— 它们对新归属本就正确）+ **删 1 个幽灵块** `L1/分析程序L1-3`（sheet 在源 xlsx 的 13 张 visible tab 内不存在，真实 tab 是 `调整分录汇总L1-3`；且 `TB_SUM('2001~2501')` 是病态区间，横跨 L1/L2/L3 会把 2231 应付利息扫进「债务合计」= 跨循环双算）。附注侧 13 项：`五、46 t04` **5→9 列** + 四组 `_column_groups`、`八、45`/`八、46` 中文 key → 稳定 ascii key、`八、57` 结构对齐源模板。<br>🔴 **立项直因是一个平台级假绿**：`build_plan()` 只校验 `wp_name`/`account_codes`/`sheet` 三个字段，而 `_build_adjudication_cells()` 虽已定义却**从未被调用**（additive 死代码 = 假绿第①源）⇒ `--check` 长期报「0 项欠账」rc=0，真正错的 `cells[].formula` 实参与 `cells[].description` 科目中文名一处未改。<br>**守卫 189 passed**（判据层 `_l_preset_criteria.py` 520 行 / 用例层 `test_l_preset_account_coherence.py` 624 行，按 800 行门禁**拆分而非加白名单** —— 白名单表头写的是「历史大文件」，新增文件套用属滥用；import 清单由脚本按 tail 实际引用用 `ast` 算出，拒绝手写，漏名 = collection error = 39 断言零执行）+ 前端 **148 passed**。`OUT_OF_SCOPE_WP_CODES` 按 **wp_code 粒度**豁免 L0（先试按块 `("L0","审定表L0-1")` 但配「登记不得过期」自检后无法同时对工作树与 HEAD 成立），配 3 条闸门：理由 ≥20 字且必须含 owner · 登记表必须**恰为** `{'L0'}` · 传空登记表重算证明未盖住 L1~L8；变异塞 `"L3"` → 2 条 RED。<br>**零回归钉死**：L1/L3/L8 三块要求逐字节不变，由 `assert_untouched_blocks_are_healthy()` 独立断言（只校验「公式实参恰为本块 account_codes」这一不变量，不比对 description 措辞）。<br>**复盘查出 4 处真实缺陷**：`lCycleNoteSubtableContract.spec.ts` 4 条 FAIL 锁着旧值（L4 三处旧表名 + L7 列序）⇒ **诚实改写为新值并加反向断言「旧名不得复活」**，而非绕过；L2 label 归一化（模板是 `优先股\永续债利息`、底稿是 `优先股/永续债利息`，半角斜杠 → 反斜杠）+ 按模板行集 `filter`（listed 模板无「其他」行，原实现多推一行）。<br>🔴 **入库过程本身是一课**：数据修复无法从共享工作树 `git add` —— 三份数据文件混着并发 D/K 披露流的 **49 增/6 删/40 改**（prefill）、21 处（soe）、12 处（listed），JSON 无法文件级拆分（`git add -p` 对 1MB JSON 不可靠）⇒ 改为**在干净 worktree 上重放本 spec 的 4 个幂等脚本**，产出「远端基底 + 只有我的改动」，归因确认 prefill **1 增/2 删/6 改全部 L 循环、0 个非 L 块**后提交。中途一次判断被自己推翻：曾据一个「自己先跑过脚本的 worktree」的读数断言「并发 commit 把我的数据修复回退了」，改用 `663488b0..5ff15c02` **逐 commit 探测**后证明**从未回退、五个 commit 数据一直是原始破损态**（教训：判 HEAD 内容必须用 `git show <ref>:<path>`，不能用可能被自己污染的工作树）。另修 `fix_l_cycle_prefill_presets.py` 在 GBK 控制台打印 U+21D2 `⇒` 抛 `UnicodeEncodeError` 直接崩掉整个 `--check`（表现像「脚本坏了」而非「控制台编码不够」），stdlib 一行 `reconfigure(encoding="utf-8", errors="replace")` 收口。<br>**终态**：4 个幂等脚本 `--check` 全部 **0 欠账**（含此前长期报「2 项欠账」的 v1 —— 真相是它声明的目标态里 `八、53`/`五、48` guidance 带 markdown 粗体而盘上没有，每次都「修」一遍却从未入库）· 干净 checkout 复验 189 passed · CI 挂 2 个 job。<br>**遗留登记（非本 spec 作业面）**：L0 两处缺陷（sheet 名不实 + 病态区间）owner = `l0-confirmation-source-alignment` 待另立；`mutate_l_cycle_guards.py` 3 条 ANCHOR-MISS + 2 条 GREEN 待修锚点。 |
| ~~`workpaper-import-export-lifecycle-closure`~~ | **已归档** | → `_archive/05-business-features/`（历史行；归档状态以目录实扫为准）。底稿导入导出生命周期收口（**此前被表头误记为「无 tasks.md 的空壳」，2026-08-12 实扫纠正**） |
| ~~`frontend-excel-io-single-entry-convergence`~~ | **已归档** | → `_archive/06-engineering-governance/`（2026-08-14 收敛完成 46 → 0，commit `f049a11f`）。**登记的 4 处既有缺陷已处置：2 修 / 1 撤回误判 / 1 整链删除**（`batchExport.ts` 孤儿链「合并导出」用户不可达，用户裁决删）。动因是 `xlsx@0.18.5` 带两个永不会修的 CVE（SheetJS 已撤出 npm），25 处读上传文件各是独立攻击面。性质为**行为等价重构**，迁移默认姿势是三个显式关闭（`applyStyles`/`includeNoteRow` 两个默认 true 会给 42 个原本无样式的产物加三线表、并在表头前插行）。<br>**两处立项假设被实测推翻**：B5 不是换引擎批而是「入口收两个引擎」（换 SheetJS 要对齐五处语义差异且写不出冻结窗格）；B3 不能用 `parseFile` 而须另开低层薄封装。<br>**顺带修掉三个既有缺陷**：`parseFile` 列索引错位 · 样式模板写出非法 OOXML `vertical:'middle'` 致 openpyxl 打不开文件（影响 12 个走默认样式的调用点，后端 674 处 openpyxl 连带）· 本轮改造引入的括号不配平致 Vite 500（`get_diagnostics`/vitest/变异三层全绿，只有浏览器暴露 ⇒ 已固化成 `check_vite_transform.mjs` 守卫）。<br>**提交前发现的清单漏记（最贵一课）**：B2 那批 13 个 confirmation 文件只写在基线 `note` 的自然语言里、`files` 数组为空 ⇒ 按 files 精确 stage 的脚本漏掉它们（远端仍带裸 import，CI 必红）+ Vite 编译扫描只覆盖 33/46 + 进度失真。**此前所有守卫都在验「代码符不符合清单」，没有一条验「清单本身完不完整」** ⇒ 补 R6.7 / Property 38 + 2 条守卫 + 3 条变异（M18/M19/M20 全 RED）。同域次级坑两个：对账脚本不剥注释会漏检 `import(/* @vite-ignore */ 'exceljs')`；「数量相等 ≠ 集合相等」（曾出现基线 46 / HEAD 46 但各差一个元素）。<br>**终态**：守卫 8 文件 **119** 例全绿 · 变异 **18/18** 全 RED（静态自检 18/18）· Vite 编译 **46/46** · 三件套机器校验零 warning。剩 3 个 `[-]` 均在 tasks.md `## Notes` 写明阻塞原因：Task 2（迁移前快照窗口已关闭，事后补抓＝把错值当基线）· Task 16（变异 18/38 Property，缺口三类各有判据形态原因）· Task 18（B4 需多公司合并数据、C24-4 空态不渲染导出入口） |
| ~~`e1-variant-recalc-and-mutation-denominator-closure`~~ | **已归档** | → `_archive/08-disclosure-notes/`。**2026-08-15 新建**（承接 `e-cycle-…completion` 归档时登记未修的两项）。**A 组**修 E1-3 `multi` 口径抹零：`recalcRow` 的 multi 分支无条件由原币列派生（`useE1BankDetail.ts` L105~L119），而 `loadFromResponses` 对 `fxRate` 缺失回落 **1**、对 `openingFc` 等回落 **0**（L176~L179 不对称）⇒ 只有本位币列的行切到 multi 版后真实金额被 0 覆盖。<br>**立项新查三项超出原登记**：①影响面含**审计师手工录入的行**（不止种子行）②`USER_FIELDS`（L92~L98）同含本位币四列与原币五列 ⇒ `serializeRows` 把 0 落库、原值**不可恢复**，触发条件仅「切一次 variant + 改任一格 + 2 秒」；`syncCrossSheetTotals` 的 watch 带 `immediate:true` ⇒ E1-1 审定表 TB 核对基准同步归零（实测横幅「审定合计 0.00 ≠ TB 4467536.12」）③叶子口径 `buildBankSeedRows` 无条件给 `fxRate:1` + fc 全 0 ⇒ **aux 侧无银行账户数据的项目在 multi 版金额恒零，连 variant 都不用切**（改造前的存量缺陷，账户级取数只是把它改善为「先开 multi 即正确」）。<br>修复落在**消费侧**（三形态判定 `base-identity`/`foreign-pending`/`fc-authoritative`，判据用 `fxCurrency` 而非 `fxRate` —— 用 fxRate 会把「外币待录入」误判成「本位币恒等」从而臆造汇率 1，违反 Property 34），种子侧一行不动（AC 1.9 的 variant 字段集差异已被守卫锁死）。<br>**B 组**推广 `mutate_e_cycle_guards.py` 的**覆盖面分母**范式：平台 17 个变异脚本 / 9657 行，分母 **3/17** · 静态锚点自检 **1/17** · 冻结基线 **1/17**，仅 e-cycle 那个 11/11。收敛成 `backend/scripts/_mutation_kit/`（8 模块），`run_cli` 的 `guard_files` 设**必填**让「没有分母」在签名层面不可能。<br>🔴 **顺带修一个已归档 spec 的产物欠账**：7 个 `mutate_task*.py` 属已归档 `procedure-trimming-and-delegation-intelligence`(26/26)，归档 commit 只带了 `mutate_trim_decision_guards.py`，这 7 个至今 `??` 未入库。<br>在办 spec 的 3 个脚本（`k_cycle`/`i_cycle`/`ie_lifecycle`）**不迁只登记豁免**，豁免表带失效检测（spec 一归档即提示撤销）。 |

> 🔴 g7 与 e-cycle 双双归档后，上表**剩下的 5 个活行全部由并发会话推进**（tasks.md mtime
> 秒/分钟级刷新）。`x3-adjustment-entry-import-export` 已于 2026-08-16 全交付 **63/63** 归档
> → `_archive/05-business-features/`（复盘撕掉 5 处假绿后重做：15.2 挖出并修复 L6-3 刷新即崩、
> 8 条变异 `--run` 全 RED、全量收口跑前端 239 + 后端 537 passed；4 个 commit 落
> `work/2026-08-16-amount-input-migration-typing`）。
> 跨会话协作时不要并行推进同一 spec（memory 已实证并发会话会互相回退同一文件）。
> **`g7-column-alignment-and-extraction-closure`(24/24)** 与
> **`e-cycle-extraction-formula-and-disclosure-completion`(24/24)** 均已于 2026-08-15 归档（见下）。
> 🔴 **本日 5 个活行（含 2 个空壳）在 git 里全是 `??` 未跟踪** —— 2026-08-15 归档 e-cycle 时
> `git status` 实录：`i-cycle` / `k-cycle` / `l-cycle` / `x3` 四个**在办 spec 目录**连同两个空壳
> 目录一并未入库。含义是**它们一旦丢工作树即全部蒸发**，且 INDEX 里登记的进度数无法从 HEAD 复核。
> 已归档 spec 不受影响（`_archive/**` 已跟踪）。
> 🔴 **判 Active 数量一律行首锚定正则实扫 `.kiro/specs/*/tasks.md`，别信本表旧数** ——
> 2026-08-10 实扫发现表头写「Active 4」而真实是 6 个带 tasks.md 的活 spec
> （`i-cycle` / `k-cycle` / `l-cycle` 三个漏登记）。
> `f0`(144/144) / `parent-company`(18/18) / `report-config`(12/12) /
> `sampling-evaluation-and-governance-closure`(19/19) / `k0`(18/18) /
> **`sampling-compliance-closure`(25/25)** 已于 2026-08-08 归档（见 §二）；
> **`soe-listed-note-conversion-correctness`(19/19)** 已于 2026-08-09 归档。
> **`note-template-columns-and-legacy-snapshot-closure`(23/23)** 已于 2026-08-09 归档（见 §二）。
> **`h-cycle-extraction-formula-and-disclosure-completion`(18/18)** 已于 2026-08-10 归档（见 §二）。
> **`procedure-trimming-and-delegation-intelligence`(26/26)** 已于 2026-08-12 归档（见 §二）。

**2026-08-15 归档（3 个：2 → `08-disclosure-notes`、1 → `05-business-features`）**：

---

**其三**（后继于同域 `procedure-trimming-and-delegation-intelligence`(26/26)，归入 `_archive/05-business-features/`）：

`procedure-trim-report-line-account-resolution`(**16/16**) —— 裁剪判据的科目金额定位从「程序名 ↔ 科目名子串匹配」改为「程序 → 报表行 → 报表公式 → 金额」。

**立项缺陷已修复（浏览器实测）**：E 循环改造前 **0 条**金额类建议（程序名一律「货币资金 …」而 `trial_balance` 只有明细「银行存款」「其他货币资金」⇒ 单向子串匹配全落空 ⇒ 金额恒 `null`⇒ 重要性判据整体空转）→ 现 **4 条**「金额低于实际执行重要性」，金额 **8,607,977.04**，溯源含报表行编码 + 行名 + 公式原文。零漂移（基线工具 verify 差异 0 项 + 独立同口径交叉核实 6 域全一致）。

**净新增 = 2 后端模块 + 1 前端纯函数模块**：三段映射每段都委托既有真源（`four_table/*_cycle_specs.py` 的 `row_code` · `report_config.formula` · `ReportFormulaParser`），索引**零 `BS-*`/`IS-*`/`IMP-*` 字面量** + 与 11 个 per-cycle 声明逐字交叉锁死。

**design 未预见的实现判定 —— 两组准则字段分叉时宁缺勿造**：平台有 `applicable_standard_v2`（权威真源）与 `template_type`+`report_scope`（**报表页实际用的**，缺失时兜底 `soe_standalone`）两组，实测 32 个项目 24 未设 / 7 一致 / **1 分叉**（`0ec33ac9` 331 条程序，`v2=soe_standalone` 而 `template_type=listed`）⇒ 分叉时返 `standard_unset` + ERROR 日志、**不出数**（报表页必须出报表所以兜底，而裁剪判据是自动裁掉审计程序的依据，用说不清的准则算出的金额去裁程序风险高得多）。连带：`derive_applicable_standards` **永不为空**，故 R3.3 的「未设置」不能靠它判。

**浏览器实测暴露并已修的缺陷**：汇总闸按 `accountName` 去重，而报表行映射生效后该键退化成 `wp_code` ⇒ 4 条程序落同一报表行（同一笔 8,607,977.04）被算成 4 个科目 **34,431,908.16（虚高 4 倍）** ⇒ 超实际执行重要性 ⇒ **过度阻断批量确认**。改造前被数据掩盖（金额是 `null` 计 0，合计恒 0、闸门不亮）。修法 = 新增 `aggregateGateKey`（报表行 → 科目名 → 底稿编号退化）+ 5 条守卫含反向自检（旧键必复现虚高与误触）。

**归档复盘补齐三项**：①删死代码 `traceArgsOf`（零消费方）②新建**常驻** CI 接线守卫 `test_report_line_ci_wiring.py`(12 例) —— 原用一次性脚本校验致 **Property 22 无常驻判据**，将来重名 job 被 yaml 静默去重 / 门控 PATTERN 写坏致 job 恒跳过 / 引用未入库测试都不会被发现而 CI 一片绿；含内存内变异自检（不对共享热点 yml 做磁盘变异）③扫全部新增导出符号消费方 ⇒ 死代码 **0**、22 个 Property **全部**有守卫引用。

**终态**：后端 `procedure_trim` **419 passed**（新增 94 例）/ 前端 10 文件 **360 passed** / 变异 **17/17 RED**（每条命中的正是预期判据、还原 md5 一致、`.bak` 零残留）/ 真实库验收 **PASS**（36 项独立算术复核全一致，独立复核走「极简线性符号解析器 + 直接 SQL 聚合」与 `ReportFormulaParser` 实现路径完全不同）/ 准则变体 `soe_standalone` VERIFIED、`listed_*` 与 `soe_consolidated` **UNVERIFIABLE**（库中无该变体项目，不用构造数据冒充）。

🔴 **顺带修复上游 spec 的入库欠账（否则本 spec 的 CI job 在干净 checkout 下必挂）**：已 commit 的 `procedureTrimDecision.ts` import 的 `completenessExemption.ts`（连同 `b50Completeness.ts`）**在 HEAD 中不存在** —— 归属 `procedure-trimming-and-delegation-intelligence`(标记 26/26 但从未入库)，导致**既有的** `procedure-trim-intelligence-frontend` job 也已必挂。本轮连同各自配套测试一并入库（39 例全绿），CI 依赖闭包复查 **160 文件 / 0 未跟踪**。

**登记的既有问题（非本 spec 引入）**：`BS-055` 跨准则同码异义（listed「应付股利」/ soe「短期借款」，`m_cycle_specs.M1` 指向它 ⇒ 国企项目行名不符，但两变体 `formula` 均为 `None` ⇒ 返 `formula_unavailable` **不出数**，验收脚本分级 LOW）· J1/J2 声明的 `row_code` 与循环语义不符（`BS-051` 实为持有待售负债、`BS-069` 实为非流动负债合计且公式全 `ROW()`，索引如实跟随声明正是零字面量的设计目的）· `test_task23_zero_regression::test_linkage_module_is_new_not_a_rewrite` 恒红（判据 `_git_show(...) is None` 而该文件已进 HEAD 396 行，只读 HEAD 不依赖工作树 ⇒ 与本 spec 无关）。

**新登记的坑**：前端 vitest 里 `await import('字面量')` 被 Vite 在**转换期**解析，模块不存在 → 整文件 collection error + `Tests no tests`（零断言执行）⇒ 说明符存变量 + `/* @vite-ignore */` · `fs_append` 的内容会被并发会话的完整重写覆盖（实测 85 秒内被整段重写）⇒ 加挂后必须**立即**用不依赖行号的归因型判据复验 · PowerShell 的 `Measure-Object -Line` **不计空行**，据它切字节区间必错位 · 交叉核实自己会造假漂移（本轮两次：漏 `is_deleted=false` 过滤、快照键名写错）· 变异脚本运行期间**不能并行**跑同一组测试（会读到变异中间态而假红）。

---

**其二**（与前身 `e1-four-table-extraction-and-disclosure-alignment` / `e1-orphan-components-wiring`
同域，与同命名范式的 `h-cycle-extraction-formula-and-disclosure-completion` 同批）：

`e-cycle-extraction-formula-and-disclosure-completion`(**24/24**) —— E 类（E0/E1）取数 / 公式预设 /
附注披露收口，主交付 commit **`2ee7929e`**（2026-08-12）。交付内容见 §一 该行；本节只记**归档复盘的判据与教训**。

**归档不是看复选框，是十二维实证**（2026-08-15 复盘轮，零改代码）：产物 47 路径 untracked **0** ·
CI 7 个 E job 的 **37/37** 文件引用 exists+tracked（干净 checkout 可跑）· 后端 312 passed /
前端 294 passed（9 文件）· 变异**锚点自检 29/29 OK、0 MISS** · 3 个幂等 `--check` 全 0 欠账 ·
11 Req / **83 AC 零悬挂** · 41 Property 全被 tasks 引用 · design 提到的 16 个符号全在生产代码
可定位 · 三件套机器校验零诊断。

🔴 **本轮复盘沉淀的两条通用做法**：
①**变异锚点自检（`--check-anchors`）是「已归档 spec 是否还可复现」的最便宜判据** —— 只读、不改
生产代码、秒级完成，却能一次性证明「29 处生产代码结构未漂移 + 变异体系仍然有效」。相比之下
重跑全量变异要改包含并发在途改动的文件（本 spec 的 M09/M10/M29 锚在 `note_template_soe.json`，
而该文件当时正带并发 K 循环 +150/-98 未提交改动），风险收益不对称 ⇒ **复盘轮用锚点自检，
不重跑全量变异**。
②**工作树 dirty 文件必须逐个 diff 归因，不能按文件名猜归属** —— 本轮 4 个 dirty 文件里
`E1TabDisclosure.vue`（名字明确是 E 循环的文件）实际是**并发 K 循环**改的（引入 `rowScopeFailure`
共享件，把 fail-closed 提示从「哪张表」升级为「为什么」），`note_template_soe.json` 改的是少数
股东权益/合并范围表的动态列稳定 key（H7 范式）而非 E1 货币资金段 —— 靠 `fix_note_e1_monetary_fund_structure.py --check`
的 4 段全「已对齐」反证了 K 的改动没碰 E 的段。按文件名归属会把别人的在途成果误提交或误回退。

**该 spec 自身最值得复用的一条**：`mutate_e_cycle_guards.py` 把「变异全红」与「守卫全被反证」
拆成两个判据 —— 用 `SPEC_GUARD_FILES`（17 个守卫文件）作**覆盖面分母**，在 21 条变异全 RED 的
情况下仍报出 **7 个前端守卫文件从未被任何变异打红**，据此补了 M22~M29。新增守卫文件时若不同步
加变异，报告末尾会直接显示欠账。**这是 memory 假绿第①源「additive 注入即死代码」在守卫层的
对应防法**，建议后续 spec 的变异脚本一律照此带分母。

**两处遗留已在 tasks.md 登记**（未修，非本 spec 引入）：E1-3 multi 版 variant 切换抹零（见 §一）·
E1-10 交叉核对把科目码当账号比对 ⇒ 建议合并进存量口径回填 spec。

---

**其一**（与前身 `g7-four-table-extraction-and-disclosure-alignment` /
`g7-linkage-extraction-completion` 同域）：

`g7-column-alignment-and-extraction-closure`(**24/24**) —— G7 长期股权投资列结构对齐与取数闭合，
commit `83ccf630`（分支 `work/2026-08-12-g7-column-alignment-closure`，22 文件 / 16 个新文件）。
补上「源 xlsx ↔ 模板 seed ↔ 运行时载荷」三向锁死的**第三条边**（56 个偏差点 → 0），
并新增立项时不存在的**第四边：渲染层** —— 浏览器实测发现两级表头 **0/38 张从未渲染**
（模型里的 `group` 是 additive 死代码，任何 `.vue` 零引用），修复后 20 张真出两级表头。
契约覆盖面 **11 → 38 张**全部运行时表，并顺带修掉 15 处此前三条守卫**结构性看不见**的
标签列头原文偏差。
**修掉一个平台级假绿**：`_note_structure_kit` 的 `--check` 弱于 `--dry-run`（24 个幂等脚本共用）
—— 改坏模板一格，`--check` 从报 0 欠账变为报 2 欠账；此前该假绿让**所有幂等证空转**
（常规轮「0 变更 ⇒ 第二次写入 md5 不变」是恒真的，故补了从不对齐态出发的强化轮）。
**收口复盘追加修 1 项 fail-open**：两个披露 Tab 的 `syncToDisclosureNotes()` 把真同步与收尾
刷新塞进同一个 `try`，同步失败会被收尾的成功文案盖成「同步成功」⇒ 拆两段 try（真同步失败
`console.error` + `ElMessage.error` + **return**；收尾失败降级 `warning`），错误文案下沉共享
helper `g7DisclosureSyncFeedback.ts`，补守卫 5 例 + 变异 2 锚点。
**终态**：前端 G7 全域 49 文件 **887 passed** · 后端 G7 主域 **2297 passed**（2 例失败三层归因为
并发 K 循环在途）· 变异检验前端 **12/12 全 RED**（GREEN=0 / MISS=0 / WRONG=0）· `--list`
**15 锚点**静态自检通过 · CI 挂 `g7-column-alignment` + `g7-column-alignment-frontend` 两个 job。
**本轮沉淀的通用教训（已写入 memory `#conventions`）**：①`--list` 只打印不校验 ⇒ CI 里恒绿，
必须加「锚点命中恰好 1 次 + `replacement != anchor` + `expect_test` 可定位 + 无残留 `.bak`」；
②多 spec 混改同一 yml 的「只加不动」验收必须用**归因型判据**（变动是否落在我的字节区间内），
全局等值型在并发下必假红；③`stamp()` 写的 `section._aligned_at` 使任何「模板 JSON md5 逐字节
不变」判据必假红 ⇒ 收敛比对用剔时间戳的稳定 md5、两次写入一致仍用裸 md5；
④别跑全量 `backend/tests`（1522 文件、前台无中间输出会被误判卡死），按引用关系反查辐射面。
**三条登记在册但不在本 spec 半径的遗留**（未动，已写入 tasks.md 实录）：`account_mapping`
auto_fuzzy 备抵错映射（1525/1526/1527 全 → 1521）· H2 `('eng_mat','1604','1605')` 6 项目 +
H7 `('accum_dep','1621','1622')` 5 项目 · `fix_note_l_cycle_structure.py --check` 2 项 guidance 欠账。

**2026-08-12 归档（1 个，→ `05-business-features`，与前身 `procedure-applicability-trimming` /
`procedure-delegation-notification` 同分类）**：

`procedure-trimming-and-delegation-intelligence`(**26/26**) —— 程序裁剪三维判据（风险评估 →
重要性 → 数据存在性）+ 人员委派智能化。把裁剪从「单维（科目有无余额）」升级为九档短路的
决策内核（`procedureTrimDecision.decideTrim`）+ 汇总闸（`trimAggregateGate`）+ 完整性豁免
（`completenessExemption`，11 个循环各带 ≥20 字 rationale）+ 建议态/确认/驳回三态 +
理由码真源统一（`TrimReasonCode` 扩 4 值，canonical trim entry additive 扩 `reason_code?`）+
裁剪充分性复核视图 + 附注反向联动（复用 `disclosure_notes.is_empty`，不新建第二套不适用字段）+
委派建议分配算法（按风险降序 × 加权负载最小）。
**Task 26 浏览器实测收口（2026-08-12）**：只读部分 5 passed / 写库项两轮各 2 passed。
**核心链路在真实库首次完整跑通** —— 用 Task 14 的覆盖开关把 D 循环改判为完整性不敏感后，
D3 预收账款 13,656,018.02 < 实际执行重要性 26,104,487.00 ⇒ 档 8 产出 `below_materiality`，
逐条确认后落库 `suggestion_state={'reason_code':'below_materiality'}`（`jsonb_typeof=object`，
未踩「写成 JSON 字符串标量」那个坑）+ 含判据数值的 `skip_reason` 并列同事务；汇总闸真算出
「建议裁剪科目 1 个（已按科目去重），金额合计 13,656,018.02 元，低于实际执行重要性
26,104,487.00 元」。**顺带修掉一个真产品缺陷**：Task 14 的写入端点
`PUT /procedure-trim/completeness-scope` 在真实库上**恒 500** —— `CAST(:ts AS timestamptz)`
配 `now.isoformat()` 触发 asyncpg `DataError`（**UUID 与 timestamptz 的正确写法方向相反**：
UUID 是 `CAST + str`，timestamptz 是 `CAST + datetime 对象`）；而该模块 112 例守卫
（56 后端 + 56 前端）+ 14/14 变异全绿，因为写入 9 例全走替身而**替身不做参数编码** ⇒
补 3 条守卫（连库真写往返 INSERT/UPDATE/list/DELETE 末尾 rollback · 反向自检钉死驱动行为事实 ·
源码级），变异检验双双 RED。**实测 5 条失败全是判据缺陷无一产品缺陷**（按文案猜按钮 ——
真实是「保存覆盖」/「撤销覆盖」· `.el-message--success` 被前置步骤自己满足 ⇒ 改用网络请求作硬判据 ·
复核端点漏 cycle 段 · `locator.click()` 命中假阳性 ⇒ 改 `page.mouse.click` 真实输入事件 ·
交叉核实查询漏 `is_deleted` 过滤差点误报漂移）。数据按基线复原并经 postgres 只读交叉核实
（已裁剪 0 / `suggestion_state` 0 / `B50-T3-*` 0 行 / `row_tasks` 27 全部回到基线）。
**遗留议题已立后继 spec** `procedure-trim-report-line-account-resolution`（见 §一）。

**2026-08-10 归档（1 个，→ `08-disclosure-notes`，与前序 `h-cycle-four-table-extraction-and-account-mapping` /
`h-cycle-legacy-cleanup-and-platform-hygiene` 同分类）**：

`h-cycle-extraction-formula-and-disclosure-completion`(18/18) —— H 类（H1~H10）取数 / 公式 /
披露收口。**双族并存取数**（新族 `1651`/`1652` 使用权资产与旧族 `1641`/`1642` 在同一项目内互斥，
真源 `four_table/dual_family_codes.py` + 迁移 **V145** 改 `report_config` 公式为并取）+
`h_cycle_adjudication_prefill` 共享件（H1~H4 审定表段预填，四个 render 策略共用）+
H3 前端槽真源 `h3AccountScope.ts` + 金额控件登记 `hCycleAmountControlRegistry.ts` +
会计政策章 + 八、26 `text_sections`。真实库 **80 组合验收 0 违规**
（`verify_h_cycle_extraction_live.py`，9 项目 × 10 循环）。
**Task 18 浏览器实测 5/5 全过**（2026-08-10，实测项目 `2aa00f57` 重庆和平药房_2025 / soe）：
H8 审定表 TB 核对块出 `352,406,145.74` · H3 溯源面板四槽全渲染 · H1 溯源面板出数 +
预填按钮 enabled · 披露推送后附注「八、26 使用权资产」`last_sync_at` 由 NULL 前移且
`sub_table_data['使用权资产']` 25 行列结构未压扁 · 金额控件千分符生效。
**实测修正 tasks 原文三处**：H1 按钮真实文案是「从TB子科目预填」（非「从四表库带入未审数」，
后者宿主是 N1/N3/N4/N5·K1/K2·J1/J2·G8/G9·H2/H4）· H3 用 `WpFourTableSourcePanel`
而 H1/H2/H4/E1 用 `WpSemanticAccountSourcePanel`（DOM 与展开方式都不同）·
立项预设「三个底稿是空底稿」被推翻（实为已有 37 行 `checklist_responses`）。
**登记未修两项**：H8-1 四个金额列用裸 `el-input-number` 未传 `formatter`（EP 2.13.6 无该 prop，
A/B 对照实测确认千分符不生效，属存量替换待单独 spec）· `H8TabDisclosureSoe.syncToNotes()`
裸 `catch {}` 在 HTTP 全 200 时仍弹「同步附注失败」（fail-open 误报）。
实测后按基线**逐字节复原**并双重核实（脚本 verify `diff_count=0` + 独立 SQL 直查九项吻合），
复原后重跑验收脚本仍 0 违规。

**2026-08-08 归档（1 个，→ `05-business-features`，与 `voucher-sampling-*` /
`cutoff-test-*` / `voucher-check-sampling-integration` 同分类）**：

`sampling-evaluation-and-governance-closure`(19/19) —— 抽样评价与治理闭环
（`sampling-compliance-closure` 的后继）。四波：**Wave 1** 撤销回填同步软删两张投影表
+ 合规判据修正（特定项目占比不再用勾选数、MUS 样本量改比系统建议值）+ 覆盖率阈值
单一真源（底稿 > 项目 > 平台默认 0.60，显式标注"非准则数字"）· **Wave 2** CAS 1314
四条评价缺口（未检查样本二选一处置 / 偏差性质结构化复用 C 类口径 / 完整性核对阻断 +
≥10 字理由放行 / 分层层内评价灰度）· **Wave 3** 平台级 P0 —— `qc_rule_definitions`
**0 行**使 `_get_enabled_rule_codes` 返回空集 ⇒ **20 条 QC 规则全部静默不执行**，
门控语义改「禁用黑名单过滤」三态后真实库实测恢复 **20/20** 条；QC-12 判据重写为
不依赖已软弃用的 `SamplingConfig`；新增归档章节 `06-抽样记录汇总.txt` + 归档完整性
第 5 类（非阻断）· **Wave 4** 属性抽样接线控制测试 + 抽样引擎复核入口 + CI 两 job +
真实库只读验收（PASS=10 / FAIL=0 / SKIP=2）+ 浏览器实测。
**收口期修掉一个只有浏览器 + 独立算术复核才会暴露的真缺陷**：`alternative_performed`
的样本 `checkResult` 仍为空 ⇒ 被 `inferMisstatement` 的既有过滤整体排除 ⇒ 既不进
分子也不进分母，推断错报被**放大 2.26 倍**（真实库落库取证 3,412,422.05 vs 正确
1,511,272.73），不符 R3.3 且方向是虚高；修法 = 新增 `applyAlternativeTreatment` +
统一入口 `applyUncheckedDisposition`（留痕计数读原数组、逐位不变），
Property 28 守卫 8 例 + **变异检验 5/5 全 RED**。

**2026-08-05 空壳目录清理（2 个，Active 区不再有非 spec 目录）**：

`procedure-delegation-visibility-isolation` / `visibility-isolation-go-live-hardening` 两个目录只剩
`evidence/artifacts/`（无三件套、**未被 git 跟踪**），其 spec 文档早已完整归档在
`_archive/06-engineering-governance/`（86 个 tracked 文件）。逐文件哈希比对确认这批 evidence 是
**更早且已被取代的测量轮次**（canonical 是 6000 请求 / 64 并发，空壳里是 1500 / 48，项目 UUID 亦不同），
其中 6 个文件与两份归档副本都不同 ⇒ **不删除**，整体移入
`_archive/06-engineering-governance/{spec}/evidence/artifacts-superseded-run/`（零覆盖、移动前后哈希逐一相等）。
Archived 计数不变（未新增 spec，只是归位证据产物）。
> 🟡 `_archive/99-superseded/` 下另有这两个 spec 的**同名 evidence-only 目录**（24 个 tracked 文件，
> 其中 `visibility-isolation-go-live-hardening` 还嵌套了一层同名目录）—— 是更早一次未完成的归档搬移残留。
> 清理它需要删除 tracked 文件，留待确认。

**2026-08-05 归档（1 个，→ `05-business-features`）**：

`deliverable-lineage-wiring-and-writeback-closure`(25/25 + 40 个复选框全 `[x]`) —— 交付件溯源接线与回填闭环。
立项时的实证基线：`write_section_anchors` / `snapshot_on_confirm` / `_classify_change` 三者**生产零调用方**
⇒ 溯源/stale/刷新/回填整条链空转（前序 spec 22/22 全绿是**假绿**，测试自己合成带锚点的 docx）。
四波交付：**Wave 1** 锚点写入 + 章节状态落库 + 回填 rowcount 五桶 + 就地刷新 + 能力矩阵单一真源（真实链路验收 **12/12**，
真实项目写入 141 个锚点、`/section-states` 从全库 0 行变 141 行）· **Wave 2** 快照继承 + `doc_key` 去时间戳 +
真实编辑人（V142）+ 护栏接线（**实证席位从来没真正释放过**：占用用 `current_user.id`、释放用 `created_by`
且版本号取的是 OO 内部号，全靠 1h TTL 自愈）· **Wave 3** 报告正文段落级回填（真实链路验收 **18/18**，
发现 Word 模板模式下 `report_body_json` 只有 6 个元数据键、段落文字只在 docx 里 ⇒ 补 additive `sections`）·
**Wave 4** xlsx 差异告警（V143）+ 溯源可视化（版本链 `is_stale` 三态 + 三件套三列对照 + 列表行级溯源抽屉）。
**收尾修正推翻了自己上一轮的归因**：真实库那 22 处「Cell_Mapping 配置错位」实为**检测器自身缺陷** ——
资产负债表拆「主表 + 续表」而 JSON 两侧共用 `balance_sheet` 键且坐标重叠，按 `sheet_aliases` 取第一个匹配
sheet 会让续表 49 个 row_code 去主表取值；改为与 exporter 同源（逐 sheet 扫内联 `{{row:}}` 占位符 +
按真实 sheet 名取值）后 22→5 处（逐格核对确认真差异），另一真实报表变 `checked=452 / diffs=0` 完全一致。
真实库跑 detect 还揪出 naive/aware datetime 裸比较抛 `TypeError` 被 fail-open 吞成「无数据」的真 bug。
**遗留**：浏览器层肉眼实测（后端真实链路验收已 12/12 + 18/18 通过）· 尚未 commit。

**2026-08-04 归档（3 个，→ `11-confirmation-d0-module`）**：

`g0-confirmation-source-alignment`(23/23) —— G0 投资循环函证源模板对齐。逐格精读 10 张 sheet（全 visible）后
补齐 G0-1 下区四块（8 品种×8 指标矩阵「有就显示没有隐藏」+ 防死锁开关 / 样本选择 6 项 / 审计说明 5 段 / 审计结论）、
按循环解析跨表导航（删写死 `D0-*`）、G0A 补回 12 条 `program_category`（备选与 IPO 专项不再默认勾选）、
公式预设从「审定表口径 + `TB_SUM('1101~1511')`」改为 8 条 PLACEHOLDER、G0-6 三区块按源模板重排（删自造记账凭证列、
`support_doc` 拆成支持性文件 1/2 各三列）、9 条源模板缺陷显式登记并在 UI 逐条可追溯。
**顺带修掉两个真实数字/口径错误**：证券差异表三列方向全反（源 `M=J−G` 与表头 `③=①−②` 矛盾，平台照抄了缺陷方向 →
统一为账面 − 回函，两张差异表此前互相矛盾）· 该表组表头字面遗留 `差异（②−①)` 与派生方向自相矛盾（Task 23 浏览器实测抓出）。
**Task 23 实测 8 项 7 通过**，1 项受阻于平台级孤儿组件（`CrossWorkpaperNav.vue` 全仓零渲染宿主 →
Task 11 的修复正确但用户不可达；Property 13 只断言了链条上游有消费方，整条链仍是死的）。
遗留两条平台级议题已登记该 spec §Notes：孤儿导航组件接线（建议与 `e1-orphan-components-wiring` 合并）·
替代程序区块 `CheckBlock.vue` 可编辑金额列用 `el-input type="number"` 致千分符结构上不可能出现（七枢纽同款）。

`h0-confirmation-source-fidelity-and-linkage`(24/24) —— H0 固定资产循环函证源模板保真度与联动补齐。
逐格精读 9 张 sheet（**全 visible**）后修掉三个 P0（「账户/交易」下拉三处互不一致且无 H 类科目 /
H0-1 下区四块完全缺失 / H0-5 四段编号与源模板全部错位），并在真实库直跑与浏览器实测中挖出
**6 个额外缺陷**（其中 2 个是活的错数：H3 裸通名兜底把固定资产累计折旧扣进投资性房地产致账面金额为负；
H0 聚合忽略 `closing_direction` 把 contra 子科目加成正数）。

**2026-08-03 归档（4 个，→ `08-disclosure-notes`）**：
`h-cycle-four-table-extraction-and-account-mapping`(25/25) ·
`d4-four-table-extraction-and-disclosure-alignment`(33/33) ·
`n-cycle-note-template-and-disclosure-completion`(13/13) ·
**`semantic-account-resolver-full-rollout`(31/31)** —— 结论是「应立即迁移的策略 = 0 个」，
交付物是**三道守卫**而非批量迁移：定向裁决交叉锁死（未迁移清单 ⊆ 已登记裁决理由，
33 条逐条带实证）· 旧制编码数据触发守卫（旧制码一带非零余额即打红，把「该迁移了」
交给数据判断）· F2 展示元数据错码纠正。

新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）。

---

## 二、已归档 Spec（556 个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          3
├── 04-infra-architecture/            39
├── 05-business-features/            239
├── 06-engineering-governance/        14
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              81   ← 2026-08-15 实扫（本轮归档 g7-column-alignment-* +1）
├── 09-consolidation-phases/           5
├── 10-A~S-workpaper-all-cycles-complete/  31
├── 11-confirmation-d0-module/        17
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     7
```

### 最近归档（2026-08-15）

**→ 08-disclosure-notes（+2，本日该分类第 2 个：G7 长期股权投资 + I 循环收口）**

| Spec | 说明 |
|------|------|
| i-cycle-extraction-formula-and-disclosure-closure | I 类（I1 无形资产 / I2 开发支出 / I3 商誉 / I4 长期待摊 / I5 其他非流动资产 / I6 研发费用）取数、公式预设与披露附注收口（**26/26**，主交付 commit `e085d324` + 归档前复盘 Task 25）。<br>🔴 **归档前复盘先解掉一个阻断项：两个 CI job 在干净 checkout 下必红** —— Task 10 的数据产出（4 张表补 `columns`）从未入库、**7 个正式产物 `??` 未跟踪**且 4 个被 CI 直接引用。Task 21 的 CI 接线守卫用 `Path.exists()` 判**工作树**故结构上抓不到，已登记「应改判 `git ls-files --error-unmatch`（已入库）而不是「本机存在」」。<br>🔴 **复盘抓出 3 个真错：行维度三向从来没人比过** —— 原三向（Property 16）只比**列**、`_SRC_DYNAMIC_MARK_COUNT` 只锁**源侧**扩位数：① I1 上市「无形资产情况」减值准备减少段**丢了「（2）失效且终止确认的部分」并凭空多出第 4 个可扩位**（账面原值/累计摊销两层都有该行，只减值准备层没有 = 从 H1 复制漏改；`h1/h7/h8ListedDisclosureModel.ts` 同形态，已登记给 H 循环）② I1 国企同表 **48 行 / 10 个错类别**（缺「其他」、「矿产权」拆成「采矿权+探矿权」、「特许经营权」→「特许权」、首类别是「软件」）⇒ 新建项目附注开局即错类别 ③ `I1_LISTED_DEFAULT_CATEGORIES` 是**第二份类别真源**且 3 个 label 错，而**生产消费的正是这份错的**，Task 12 交付的 `resolveI1Categories()` 反倒**生产零消费方 = 死代码**。<br>**为什么全部逃过 38 张列契约 + 12 条扩位基线 + 14 条变异**：前端行模型与模板 rows 是**同一处错**（同批生成）⇒「模板 ↔ 载荷」自洽型判据两侧一起错、仍自洽。**只有拿源 xlsx 当第三边才抓得到**（与 G7「第四边 = 渲染层」同族的方法论）。<br>**守卫 +16**（后端 Property 43 七条 → 199 passed · 前端 Property 44/45 九条 → 24 passed），**免断言项 10 条逐条登记实证理由**（「源侧标记 ↔ 模板 expandable」实测**不是** 1:1，写成断言即锁死错值；第一版 4 条空话理由被自己的 ≥20 字理由闸打红）。**变异 14 → 19 条，新增 5/5 全 RED**。<br>**零回归归因型**（禁 stash / HEAD-swap）：后端辐射面 60 文件 AFTER 32 red / BEFORE 39 red ⇒ 新增 **0**、**顺带修好 7 条**，其中 `test_note_k_row_code_evidence::test_shared_table_manifest_has_no_drift` 是 **K 循环守卫本来红着被这处 soe 行修复带绿**（「修对了而不只是自洽」的独立印证）；前端 94 文件 / 3133 tests，5 个红文件在回退我的改动后失败数完全相同 ⇒ 全属并发会话域。<br>**入库归因型分区暂存**（`git hash-object -w` + `update-index`，不动工作树）：两个 `note_template_*.json` 只入 I 循环 5 个章节（另 33 个并发章节不带）· `prefill_formula_mapping.json` **在 HEAD 上重放本 spec 幂等脚本**得 desired（工作树该文件 394 个块跨全循环变动，一个不带）· `wp_code_overrides.json` 只入 `市场平均收益率2017: skip`。**入库前用「模拟干净 checkout」跑两个 job 的完整命令，汇总 rc=0** —— 这是本轮最该沉淀的做法：**验的必须是「即将提交的字节」，不是当前工作树**。<br>**另修三件套 10 处错基线**（含 requirements.md 两个重复 `## Glossary` 段、「6/6 全错」实为 11/12、「12 类」实为 11 类、「I3~I6 各 0 处扩位」漏了 I5 两版各 1 处、「`=#REF!` 15 格」实为 20 格、design 把两个**已存在**的 `fix_*` 脚本写成「新建」、`columns` 位置写错、`iCycleAccountScope` 不复用工厂的**有意偏离**未登记），新增 AC 5.8/5.9/6.5/7.7 与 Property 43/44/45 承接。<br>**如实登记**：Task 6 的 `diagnose_i_cycle_rowcode.py` 磁盘与 git 历史双查皆无（推测以 `_wip_*` 形态写、被 Task 24 清理删掉），不被 CI 引用且职能已被 `verify_i_cycle_live.py` 的 D1/D4 覆盖 ⇒ 按「功能已覆盖」结案，不为凑文件名重建空壳。 |
| g7-column-alignment-and-extraction-closure | G7 列结构对齐与取数闭合（**24/24**，commit `83ccf630`，分支 `work/2026-08-12-g7-column-alignment-closure`，22 文件 / 16 个新文件）。补上「源 xlsx ↔ 模板 seed ↔ 运行时载荷」三向锁死的**第三条边**（56 偏差 → 0），并新增立项时不存在的**第四边：渲染层** —— 浏览器实测发现两级表头 **0/38 张从未渲染**（模型的 `group` 是 additive 死代码，任何 `.vue` 零引用），修复后 20 张。契约覆盖面 **11 → 38 张**全部运行时表，顺带修掉 15 处三条守卫**结构性看不见**的标签列头原文偏差。<br>**修掉一个平台级假绿**：`_note_structure_kit` 的 `--check` 弱于 `--dry-run`（24 个幂等脚本共用）—— 改坏模板一格从报 0 欠账变为报 2 欠账；此前该假绿让所有幂等证空转（「0 变更 ⇒ 二次写入 md5 不变」恒真 ⇒ 补了从不对齐态出发的强化轮）。<br>**收口复盘追加修 1 项 fail-open**：两个披露 Tab 的 `syncToDisclosureNotes()` 把真同步与收尾刷新塞进同一 `try`，同步失败被收尾成功文案盖成「同步成功」⇒ 拆两段 try（真同步失败 `console.error` + `ElMessage.error` + **return**），文案下沉 helper `g7DisclosureSyncFeedback.ts`。<br>**终态**：前端 G7 全域 49 文件 **887 passed** · 后端 G7 主域 **2297 passed**（2 例失败三层归因为并发 K 循环在途）· 变异 **12/12 全 RED**（GREEN/MISS/WRONG 各 0）· `--list` **15 锚点**静态自检通过 · CI 挂 2 个 job。<br>**沉淀的通用教训 4 条**：`--list` 只打印不校验 ⇒ CI 恒绿（须加锚点命中恰好 1 次 + `replacement != anchor` + `expect_test` 可定位 + 无残留 `.bak`）· 多 spec 混改同一 yml 的「只加不动」验收须用**归因型判据**（全局等值型在并发下必假红）· `stamp()` 写的 `_aligned_at` 使「md5 逐字节不变」判据必假红 ⇒ 收敛比对剔时间戳、两次写入一致用裸 md5 · 别跑全量 `backend/tests`（1522 文件前台无输出会被误判卡死），按引用关系反查辐射面。<br>与同域 `g7-four-table-extraction-and-disclosure-alignment` / `g7-linkage-extraction-completion` 承接 |

### 归档（2026-08-14）

**→ 06-engineering-governance（+1，前端工程治理域第 4 个 spec）**

| Spec | 说明 |
|------|------|
| frontend-excel-io-single-entry-convergence | 前端 Excel 库调用收敛到单一入口（**15/18**，commit `f049a11f`）。**46 个生产文件 / 93 处裸 import → 0，`exempt[]` 为空、无一豁免**。动因：`xlsx@0.18.5` 是 SheetJS 在 npm 的最后一版（已撤出 npm 改 CDN 分发），带 CVE-2023-30533（原型污染）与 CVE-2024-22363（ReDoS），**两个修复版永远不会进 npm**，而项目有 25 处在读用户上传的 xlsx ⇒ 25 个独立攻击面。收敛后防护单点化。<br>性质是**行为等价重构**（产物逐格不变），迁移默认姿势是三个显式关闭 —— `applyStyles`/`includeNoteRow` 两个默认 true 会给 42 个原本无样式的文件加三线表并插行。<br>**顺带修 2 个既有缺陷**：样式模板写非法 OOXML `vertical:'middle'` 致 openpyxl 打不开产出文件 · `ConsolNoteTab.uniqueSheetName` 只 add 不 check（去重是死参数，撞名则整批导出失败）。<br>**删除 2 类零消费方代码**（用户裁决「没用就删」）：`batchExport.ts` + `BatchQueryResultGroup.vue` 整条孤儿链（「合并导出」用户不可达）连带 `headerStyle` 覆写通道 · `sheetMatcher` / `customInstructionSheet` 两项 API（各被后来补出的 `readWorkbookAoa` / 多 sheet 纯 AOA 覆盖，属设计冗余）。<br>🔴 **最贵一课在提交前才发现**：基线 `_progress[].files` 漏记 13 个 confirmation 文件（只写在 `note` 的自然语言里）⇒ 精确 stage 漏文件 + Vite 编译扫描只覆盖 33/46 + 进度失真。**此前全部守卫都在验「代码符不符合清单」，无一验「清单本身完不完整」** ⇒ 补 R6.7 / Property 38 + 2 守卫 + 3 变异。<br>终态：守卫 **119** 例全绿 · 变异 **18/18** RED · Vite 编译 **46/46** · 三件套零 warning。与同分类 `frontend-consistency-m1` / `dev-tooling-modernization` / `workpaper-maintainability-convergence` 同域 |

### 归档（2026-08-12）

**→ 05-business-features（+1，程序裁剪/委派域第 3 个 spec）**

| Spec | 说明 |
|------|------|
| procedure-trimming-and-delegation-intelligence | 程序裁剪三维判据 + 委派智能化（**26/26 全完成** + 浏览器实测 + 数据复原经 postgres 只读交叉核实）。详见 §一「2026-08-12 归档」段。要点：九档决策内核 + 汇总闸 + 完整性豁免 + 建议态三态 + 理由码真源统一 + 复核视图 + 附注反向联动；**真实库历史上第一次产生裁剪结果**（`procedure_instances` 此前 436 行全为 `execute`、0 条已裁剪 ⇒ 「裁剪→委派联动」逻辑正确但从未有数据流经过）；收口期修掉 Task 14 写入端点恒 500 的真产品缺陷（asyncpg timestamptz 参数编码，112 例守卫因替身不做参数编码而全绿）。与同分类前身 `procedure-applicability-trimming`、`procedure-delegation-notification` 同域；后继 spec = `procedure-trim-report-line-account-resolution` |

### 归档（2026-08-09）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| soe-listed-note-conversion-correctness | 国企↔上市附注转换正确性（**19/19 全完成**，守卫 549 passed / 0 failed）。修「生产 6 步里 3 步空操作 + v2 映射是孤儿」：`_map_disclosure_notes` 原先只 `SELECT count(*)` 一行不改却把该数报成 `mapped_notes` = **假成功反馈**；`_map_report_rows` / `_update_formula_references` 是 `return 0`。四处立项判断被实证推翻 —— ①跨变体 row_code 必须按 `(entity, scope)` **四象限**统计（按 entity 合并会虚构出「78 条一码两义」）②「同义两码」standalone **14** 条 / consolidated **13** 条（非 12），且 `EQ-030`/`EQ-033` 两 scope 目标码冲突 ⇒ 映射常量必须 `dict[scope, list]`③需求 3.8「两清单互斥」按字面**不成立**（14 条映射的 listed 目标码全部属「一码两义」，正因两侧异名才需要改写）→ 真不变量 = 「改写源不得落在该 scope 禁止清单里」④公式改写在 `report_config` 域内**零可改写对象**（该表无 `project_id` 列 = 纯模板表 / 全库 formula 对那批 row_code 引用 0 条 / `wp_formula` 0 行 / 附注 `binding_id` 是「章节号.行标签.列键」不含 row_code）⇒ 保留 `return 0` 但补原因码 `no_mapping_needed`。Task 10 裁决 = **删除 v2 不接线**（生产 Step 4 已调 `_map_disclosure_notes`、v2 零调用方且生产版严格更强），21 条断言迁移到生产测试 + 52 例移除守卫。Task 19 达成状态是**诚实输出「无法验收（缺授权）」**（`eligibility=NO_CANDIDATE` + rc=1，需求 10.7 明确允许）—— 8 个 live 项目里技术可切换 4 个、已授权 0 个，建议 `c8621493`（规模最小）。新建件：`note_conversion_row_codes.py` / `note_section_matcher.py`（5 对别名穷举 + 禁止匹配对 + 零相似度实现）/ `note_variant_matrix_null_audit.py`（35 条 null 三态裁决）/ `fix_variant_matrix_false_nulls.py`（三闸门：撞码 / 落点形态 / additive）/ `verify_note_conversion_live.py`；CI job `note-conversion-correctness`（jobs 136→137）。5 个生产文件收尾 md5 与开工基线逐字节一致 = 零净改动 |

### 归档（2026-08-08）

**→ 05-business-features（+1，抽样域第 5 个 spec）**

| Spec | 说明 |
|------|------|
| sampling-compliance-closure | 抽样/抽凭合规闭环（**25/25 全完成** + 浏览器实测 + 数据逐项复原）。四波：dataset 版本绑定（抽样查询原先只走 `get_active_filter`，序时账重导后同 seed 同参数得到不同样本且无提示 ⇒「seed 可复现」是假的）· 推断错报持久化 + A13 **`projected`** 通路（改造前 `misstatement_type` 硬编码 `factual`，PG enum 的 `judgmental`/`projected` 是死枚举 ⇒ CAS 1314 的核心输出进不了错报汇总）· 删 legacy `wp_sampling_engine`（金额口径 `debit+credit` 与 canonical 的 `GREATEST` 不同、分层权重写死、不落 log 不可撤销）+ V139/V140 迁移（**加唯一索引前必先查既有唯一约束** —— `uq_sampled_voucher_project_year_no` 全局唯一会让引擎登记撞它并被 fail-open 吞成 WARNING）· 78 宿主 methodology 收口（字段集判据按行模型语义分层：凭证明细型强制四要素 / 合规检查·计价测试型只要求样本可回溯，源模板实证 F2-33 只有源单据日期号、H4-5 只有入账凭证号，加「凭证日期」列属自造底稿列）。**用户裁决**：同一凭证被多底稿抽取必须弹窗人工确认（三出口 + 处置随回填留痕），不由配置项静默决定。**Task 24 收口修掉 4 个前端 dead output 缺陷**（`filled` 载荷缺 `batchId`/`datasetId` 致 bar 恒显「未绑定账套版本」· `wpCode` 是死 prop（78/78 宿主未传）致 `source_wp_code` 恒 null → 改 setup 顶层 `inject(WorkpaperRuntimeContextKey)` 传 getter · 回读态卡片被 `sampledVouchers.length > 0` 藏起来 · A13 描述批次号与样本量/种子不同源）+ 2 处后端修正（`cutoff_fill` 复用 `_normalize_evaluation` · `record_extraction_log` 两条幂等重放分支补回 `batch_id`）。新增 Property 22 + 守卫 46 例，**变异检验三轮 21/21 全 RED**，数据复原后独立只读查询逐项相符。与同分类 `sampling-evaluation-and-governance-closure`（其后继）、`voucher-sampling-engine`、`voucher-sampling-hardening`、`voucher-check-sampling-integration`、`cutoff-test-*` 同域 |

**→ 11-confirmation-d0-module（+2）**

| Spec | 说明 |
|------|------|
| k0-confirmation-source-alignment | K0 管理循环函证源模板对齐（18/18 全完成 + 浏览器实测 + 数据逐字复原）。**接手时三件套在工作树里被并发会话删掉**（`git checkout HEAD --` 恢复；恢复出的是 7/18 旧快照而磁盘产物远超它 ⇒ 「spec 文档被删导致进度记载整体回退」是新的一种假红成因）。**归档副本此前已被并发会话扫进 `d720d522`（无关 spec 的 commit）带进 HEAD，而 active 副本也还在 HEAD ⇒ 两份重复**；本轮按「以归档副本为基底、逐条施加增量」合并（保留并发会话两段实录，10 项结构性核验）后 `git rm` 掉 active 重复副本。**本轮唯一真缺口 = Property 22/23 无守卫**（design 的 Testing Strategy 表点名 `k0LowerZone.spec.ts` 而该文件不存在，Property 覆盖矩阵实扫「22 零引用、23 只被 H0 的同号 Property 偶然命中」）→ 新建 20 例守卫、**变异 6/6 全 RED + md5 逐字节还原**。另修三处三件套缺陷：悬挂引用（补 design 的 Property 24/25）· Testing Strategy 表路径漂移（`x0SummaryMatrix` 已随泛化内核撤回而不存在）· AC 11.1 无人引用。浏览器实测证实 29 叶子列六段分组 / 8 指标出数 / 账面金额自动取数 87,794,660.16（K1 BS-009 净额口径）/ 手工覆盖优先 / 下区键落 `checklist_responses`（**立项写的 `html_data` 是错的**）。新登记两个平台级缺口：保存后切走再切回回到 render-config 初始载荷（潜在数据丢失路径）· 详情面板不套用列剔除与 label 覆盖 |
| f0-confirmation-linkage-and-structural-enhancement | F0 存货循环函证联动增强（144/144 全完成）。矩阵自动聚合（三行取数 + 五派生比例 + 勾稽）+ F0-5/F0-6 供应商自动带入 + B50/A13 推送 + F0-7 邮箱域名可靠性 + F0-3 工号字段。Wave 7 九项返工其中三项修法与立项相反（舞弊迹象/矩阵取值/AI prompt 均按源模板忠实实现或撤回自造）；Task 20/21/22 浏览器实测于 2026-08-05/08-06 三轮补做全通（含 http 客户端形态错配、请求去重 abort、三循环键名各异三个只有浏览器能发现的缺陷）。与同分类 g0/h0/confirmation-orphan 同域 |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| parent-company-note-chapter-and-sourcing | 母公司附注章节结构与取数修复（18/18 全完成 + 已 push 8 个分层 commit）。判据真源 = `docs/模版/` 两份源 docx。修 5 类缺陷：soe 第 12 章标题误为「股份支付」+ slug 错、母公司 93 张表 columns/guidance/report_row_code 全缺、长期股权投资三表两级表头压扁、listed 表名首格泄漏且重名、母公司章 100% 无数据来源。核心件 `parent_company_note_sections.py`（母公司口径单一真源，按章节号逐字相等匹配）。收尾修 3 条守卫红（docstring 剥注释 / removed 键基线由 HEAD 名集推导 / 中间名留痕降级为条件断言），13/13 变异 RED |

**→ 04-infra-architecture（+1）**

| Spec | 说明 |
|------|------|
| report-config-account-code-integrity | `report_config` 科目码完整性（12/12 全完成）。全表对账 132 条 `TB()` 引用扫出 16 行错码（本 spec 修 V138 13 行 + V144 3 行），远超此前手工发现的 6 处。Task 7 挖出立项未见的第二写入路径 `ReportFormulaService.fill_all_formulas()`（按行名索引 + 只填 NULL 行 = 恰是 V138 置 NULL 那批 ⇒ 不修等于白做）+ 未完成重构残留副本 `fill_report_formulas.py`。修 6701/6702 互换 6 处（约 1.5 亿）。核心交付 = 平台级一致性守卫（此前零校验，错码可静默存在数年，先打红 13 行再改数据）+ CI job。V138/V144 均已应用真实库。撤 4 个已到期的 `trust_report_config=False`（零回归双证：40 组合仅 3 组变 resolved_from、码不变） |

**→ 05-business-features（+1）**

| Spec | 说明 |
|------|------|
| sampling-evaluation-and-governance-closure | 抽样评价与治理闭环（19/19 全完成 + 真实库只读验收 PASS=10/FAIL=0/SKIP=2 + 浏览器实测 + 数据逐位复原）。**Wave 3 是平台级 P0**：`qc_rule_definitions` **0 行** ⇒ `_get_enabled_rule_codes` 返回空集 ⇒ **20 条 QC 规则全部静默不执行**（非 except 分支、连 WARNING 都没有），门控语义改「禁用黑名单过滤」三态后真实库恢复 20/20。另修：撤销回填从不清两张投影表（撤销的凭证永久抽不到 + 项目级统计虚高）· 合规判据把「有没有全选」当准则风险 · 60% 覆盖率阈值写死在函数体 · CAS 1314 四条评价缺口（未检查样本处置 / 偏差性质 / 完整性阻断 / 分层层内评价）· 归档完整性完全不感知抽样。**收口期浏览器实测挖出并修掉一个数字级缺陷**：`alternative_performed` 样本被静默挤出比率估计基数、推断错报放大 2.26 倍（真实库落库取证 3,412,422.05 vs 正确 1,511,272.73），Property 28 + 变异 5/5 全 RED。**两项诚实登记未做浏览器实测**：分层明细（灰度默认关，开启需重启共享 dev server）与撤销后重复提示（会在真实批次留下不可逐字节复原的软删痕迹），均由守卫 + 只读脚本 SKIP 承担 |

### 归档（2026-08-07）

**→ 04-infra-architecture（+2）**

| Spec | 说明 |
|------|------|
| prefill-wp-prev-resolution-repair | `WP()`/`PREV()` 死链修复（17/17）。两个 resolver 读 `parsed_data['cells']`，该键真实库**零命中**（407 个非空 parsed_data 中 0 条）⇒ 337 条预设恒返 `None` 且 fail-soft 无告警。新建声明式真源 `prefill_anchor_map.py`（三元组键 `(wp_code, sheet, cell_ref)` → `AnchorSpec`，四种聚合 + **六态** `AnchorReadStatus`），取值改走 `checklist_responses(wp_id, item_id).remark`。**核心守卫 Property 4**：读前端 composable 源码抽 `serializeRows()` 持久化字段集与映射列键交叉锁死 ⇒ 「后端复刻前端派生列公式」这一双真源风险变成编译期可检测（D1-2 一族派生列因此进待对齐清单，宁缺勿造）。`PREV()` 改 **fail-closed** 恒返 `None`（`working_paper`/`wp_index` 都无 year 列，取本年值填「上年数」列属数字级错误，161 条里 118 条是「上年审定数」）。**落地时抓到 1 个 P0**：取值层 SQL 写 `checklist_responses.workpaper_id` 而真实列名是 `wp_id` ⇒ 被 `except Exception` 吞成 WARNING、8 条已对齐锚点全部仍返 None，而源码守卫/纯函数单测/characterization 三层全绿（characterization 恰好与「已修好」不可区分）⇒ 新增 **Property 17 真实执行守卫**。另修 `PL` 灰区（`WP('PL','利润表','净利润')` 目标是**报表**不是底稿，硬编码字母表 `"EFGHIJKLMN"` 结构上表达不了 ⇒ 改预设实时派生 + 独立登记表，Property 18）。实测 **6 HIT / 0 ERROR**，`624,025,343.06`（1260 行）经独立 SQL 交叉核对同值同行数；**10/10 变异 RED**；零回归双证（6 个未触碰 resolver 与 HEAD 逐字节相同 + 广域两侧失败集合逐条相同 126 条）。 |
| formula-management-runtime-closure | 公式管理运行层闭环（18/18 + 归档前双轮复核）。修六类实证缺陷：**48 格数字错**（`COLUMN_ALIASES` 缺 4 个发生额列名，两条求值路径静默回退期末余额 → 现 8→14 键 + 三态 helper `_resolve_tb_column`，未注册列名格数 48→**0**）· 用户公式与 Tier A **两套存储收敛**进 `wp_formula`（0 行 = 零迁移压力，GET 保留读兼容分支且守卫钉死）· `logic_check` 结果落库 `cross_check_results` · 删 **4 个同族孤儿**（`useFormulaStatus.ts` / `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` / `FormulaDependencyGraph.vue`，均 0 消费方 + 调后端零命中端点）· 底稿公式面板补 issue/hint/计算时间/中文类型标签 · 27 处硬编码 URL 收敛进 `apiPaths/formula.ts` + **平台级「前端公式 URL ⊆ 后端真实路由」守卫**。另修 3 处 spec 未记缺陷（`SUM_TB` 丢弃列名 / `_COLUMN_MAP` 把发生额映到无该列的 `TrialBalance` 静默返 0，24 个消费方 / TB 正则缺词边界误匹配 `SUM_TB` 后半段）。归档复核再修 2 处：**`test_wp_formula_layer_contract.py` 恒红零信号**（列清单只到 V100 而 V104 又加 3 列 → 判据改为扫全部 `V*.sql` 抽取，自动跟随迁移）· `draftRefresh` 漏进 `apiPaths` barrel（+ barrel 完整性守卫）。后端守卫 133 passed / 前端 60 passed / 变异 6/6 RED。与同分类 `formula-engine-unification`、`formula-runtime-convergence` 同族 |

### 归档（2026-08-05）

**→ 05-business-features（+1）**

| Spec | 说明 |
|------|------|
| deliverable-lineage-wiring-and-writeback-closure | 交付件溯源接线与回填闭环（25/25，四波全收口 + 两次真实链路验收 12/12、18/18）。与同分类的 `deliverable-lineage-and-writeback`（被它修的前序 spec）、`deliverable-lineage-content-control`、`audit-report-deliverable-center` 同域 |

### 归档（2026-08-03）

**→ 08-disclosure-notes（+3）**

| Spec | 说明 |
|------|------|
| h-cycle-four-table-extraction-and-account-mapping | H1~H10 语义科目定位收口（25/25 + 复盘 5 项 + 浏览器实测）：修 3 个「取错整个科目族」P0（H3 `1503/1504`→`1521/1525/1526/1527`、H8 `1901` 待处理财产损溢→`1641/1642/1643`、H9 `2205` 合同负债→`2601/2602`）；实测挖出 `parent_check` 揭示的 `trial_balance` 父子双算平台级缺陷 |
| d4-four-table-extraction-and-disclosure-alignment | D4 营业收入四表取数与披露/附注对齐（33/33） |
| n-cycle-note-template-and-disclosure-completion | N 循环附注模板与披露收口（13/13） |

### 归档（2026-08-01，第四批）

**→ 08-disclosure-notes（+14）**

| Spec | 说明 |
|------|------|
| f1-four-table-extraction-and-disclosure-alignment | F1 预付款项四表库取数链路根治+披露/附注收尾（28/28 全完成+实测） |
| f1-extraction-chain-and-disclosure-source-fidelity | F1 取数链路数据源忠实度（16/17，仅缺浏览器活测；实现已完成） |
| h3-investment-property-disclosure-alignment | H3 投资性房地产披露对齐（11/11 全完成+实测） |
| h5-oil-gas-disclosure-alignment | H5 油气资产披露对齐（8/8 全完成+实测） |
| h7-biological-assets-disclosure-rebuild | H7 生产性生物资产披露重建（12/12 全完成+浏览器实测） |
| h8-right-of-use-disclosure-alignment | H8 使用权资产披露对齐（7/7 全完成+实测） |
| h9-h10-remaining-disclosure-alignment | H9 租赁负债 + H10 资产处置损益披露对齐（9/9 全完成+实测） |
| k1-extraction-chain-and-note-alignment | K1 其他应收款取数级联第二轮收口（28/28 全完成+实测） |
| k1-four-table-extraction-and-disclosure-alignment | K1 四表库取数口径根治+披露/附注结构对齐（27/27 全完成+实测） |
| k2-four-table-extraction-and-dynamic-rows | K2 其他流动资产四表取数+动态行（13/13 全完成+实测） |
| n1-four-table-extraction-and-disclosure-alignment | N1 递延所得税资产四表取数+披露对齐（24/24 全完成+实测） |
| n2-disclosure-and-extraction-alignment | N2 应交税费披露与取数对齐（19/19 全完成+实测） |
| n2-vat-calc-source-alignment | N2 增值税计算源模板对齐（19/19 全完成+实测） |
| n345-four-table-extraction-alignment | N3/N4/N5 四表取数对齐（26/26 全完成+实测） |

**→ 99-superseded（+1）**

| Spec | 说明 |
|------|------|
| n2-source-alignment | 被 `n2-disclosure-and-extraction-alignment` 取代（仅含未落盘的 implementation-checklist） |

**清理空壳（2个）**

| Spec | 说明 |
|------|------|
| procedure-delegation-visibility-isolation | 早已归档（2026-07-18），残余 evidence 目录清除 |
| visibility-isolation-go-live-hardening | 残余 evidence 目录清除 |

### 2026-07-31 归档

**→ 08-disclosure-notes（+19，含并发会话完成的 spec）**

| Spec | 说明 |
|------|------|
| h2-construction-in-progress-disclosure-alignment | H2 在建工程披露结构对齐（7/7 全完成+实测）：两级表头重建 + 「项  目」→「工程物资」改名 + 10 表 columns/guidance + 契约守卫 + CI job + 浏览器实测通过 |
| d2-ar-disclosure-template-alignment | D2 应收账款上市披露三层对齐（31/31 全完成+实测+已提交） |
| d2-ar-disclosure-soe-alignment | D2 应收账款国企披露结构对齐（25/25 全完成） |
| f2-inventory-disclosure-template-alignment | F2 存货披露对齐（Sprint 1~8 全完成+已提交） |
| f1-prepayment-disclosure-template-alignment | F1 预付款项披露对齐（全完成+实测+待 commit） |
| disclosure-columns-coverage-rollout | 披露表 columns 覆盖推广（Task 1~16 全完成+已提交） |
| j1-disclosure-template-alignment | J1 应付职工薪酬披露对齐（61/61 全完成+待 commit） |
| k2-other-current-assets-disclosure-alignment | K2 其他流动资产披露对齐（22/22 全完成+实测） |
| n1-deferred-tax-disclosure-template-alignment | N1 递延所得税资产披露对齐（57/61 实现+实测完成） |
| n-cycle-tax-disclosure-alignment | N 循环税务类披露对齐（N2/N4/N5 全完成+实测） |
| d-cycle-remaining-disclosure-alignment | D3/D5/D6/D7 披露结构对齐（Task 1~9 全完成+实测） |
| k-cycle-disclosure-alignment | K1~K13 三批披露对齐（全完成+实测） |
| d1-notes-receivable-disclosure-alignment | D1 应收票据披露对齐（四阶段全完成+实测） |
| f-cycle-disclosure-parity | F 类披露复盘对齐（R1~R9 全完成） |
| applicable-standards-frontend-wiring | 准则前端全链接通（全完成+实测） |
| applicable-standards-runtime-and-sync-guard | 准则运行时守卫（全完成+实测） |

**→ 05-business-features（+2）**

| Spec | 说明 |
|------|------|
| f1-prepayment | F1 预付款项（含四表库自动取数补齐） |
| k2-other-current-assets | K2 其他流动资产 |

**→ 06-engineering-governance（+1，清理空壳）**

| Spec | 说明 |
|------|------|
| procedure-delegation-visibility-isolation | 服务端底稿可见性隔离（18/18，2026-07-18 已归档，空壳清理） |

### 2026-07-29 归档（12 个，详见 git log）

**→ 05-business-features（+9）**

| Spec | 说明 |
|------|------|
| advanced-query-consolidation | 高级查询模块合并收敛（12/12） |
| attachment-workpaper-linkage-convergence | 附件↔底稿联动收敛（23/23） |
| f2-adjudication-import-export | F2 审定表导入导出（9/9） |
| f2-detail-ledger-pull | F2 明细表序时账取数（11/11） |
| f2-four-table-extraction-refresh | F2 四表取数刷新（22/22） |
| hi-cycle-four-table-extraction | H/I 循环四表取数（14/14） |
| lmn-four-table-extraction | L/M/N 循环四表取数（12/12） |
| template-library-formula-preset-custom | 模板库公式预设（16/16） |
| work-hours-auto-collect-and-edit | 工时自动采集与编辑（18/18） |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| d-cycle-disclosure-note-enhancement | D3-D7 审定↔披露差异告警（13/13） |

**→ 09-consolidation-phases（+1）**

| Spec | 说明 |
|------|------|
| consol-disclosure-note-persistence | 合并附注 V2 按项目灰度（9/9） |

**→ 11-confirmation-d0-module（+4）**

| Spec | 说明 |
|------|------|
| confirmation-linkage-completion | 函证两价值孤儿正式做完（19/19） |
| h0-confirmation-source-fidelity-and-linkage | H0 固定资产循环函证源模板保真度与联动（24/24） |
| g0-confirmation-source-alignment | G0 投资循环函证源模板对齐与联动补齐（23/23） |
| confirmation-orphan-and-amount-format-closure | 函证域孤儿件与金额格式收口（13/13）：删 3 个 G0 零消费方 composable · `CrossWorkpaperNav.vue` 挂上首个渲染宿主（改造前全仓零宿主 = 用户不可达）· `BlockColumnDef.render:'amount'` + 七枢纽 76 个金额列标注 + 17 个非金额列登记 · 新增平台守卫「渲染宿主存在性」（组件基线 2 / 模块基线 23，只许缩短） |

---

## 三、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| 最高迁移 | `ls backend/migrations/V*.sql \| sort \| tail -1` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 四、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 归档移到 `_archive/{分类}/`，同步更新本文件
3. 分类：01地基 / 02循环 / 03打磨 / 04架构 / 05业务 / 06工程 / 07底稿瘦身 / 08附注 / 09合并 / 10全循环 / 11函证 / 12 2023-06-23批 / 13 2026-06-29批 / 99取代
4. **凭印象禁令**：完成度必须实证
5. 迁移系统 = `backend/migrations/V*.sql`（MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
