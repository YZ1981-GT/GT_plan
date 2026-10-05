# 任务清单：合并附注节点隔离与共享上下文

> 需求：#[[file:.kiro/specs/consol-node-key-isolation-and-shared-context/requirements.md]] ·
> 设计：#[[file:.kiro/specs/consol-node-key-isolation-and-shared-context/design.md]]
> 顺序：附注身份与旧入口 → custom query → 普通报表 → 前端 → 端点/集成验证 → 浏览器验收。
> 规则：所有任务初始未完成；标 `[x]` 必须记录代码与通过测试证据。V177 已存在，不重复创建同一迁移。PBT `max_examples=5`。

- [x] 1. V177 契约与节点作用域基础
  - [x] 1.1 现读 V177、ORM、索引定义与 migration status，确认节点键和 NULL 行的唯一性/并发语义；若不满足，暂停并提出新迁移，不在本任务重复 DDL
  - [x] 1.2 在附注 service 建立共享 node scope 解析：项目权限、有效年度、树构建、精确 node_key 存在性、根 consol 判定；query 参数优先于 body
  - [x] 1.3 建统一节点行 loader/writer：精确节点行优先；只允许有效根 GET fallback 到同项目/年度/章节 NULL 行；无键旧调用只查 NULL
  - [x] 1.4 节点写入不修改 legacy 行；根首次写入从 legacy 建立节点专属行；处理唯一冲突并保持事务可用
  - [x] 1.5 真 ORM/SQLite 测试：双节点隔离、非法节点、年度/项目/章节范围、根回退、非根不回退、复制后 legacy 不变、无键 NULL 兼容
  - _需求：1.1~1.6；设计：§二~§三、P1~P4_

- [x] 2. 附注公式端点统一节点上下文
  - [x] 2.1 全仓 grep 旧端点调用方；保留兼容路径，但统一接入节点解析与共享行 loader/writer
  - [x] 2.2 `/refresh`、`/audit-all`、`/audit`、`/apply-formulas`、`/aggregate`、差额穿透与 `fill-by-formula` 复用一次共享视图上下文
  - [x] 2.3 删除这些路径中引用不存在 TB 列的 SQL；TB 直接读取限定真实 ORM/schema 字段；异常返回明确错误/逐项原因，不吞异常或伪造 0/模板成功
  - [x] 2.4 公式填入只写专属节点行，保留手工保护格，准确报告保留数量；保持对象/二维数组原形状
  - [x] 2.5 真 ORM/SQLite 测试：不同节点公式结果、手工格保护、失败响应、旧路由节点语义与事务回滚；真发 FastAPI 请求验证权限依赖
  - _需求：1.5、2.1~2.5；设计：§四、P2~P5_

- [x] 3. custom query 附注 cell 读写归属
  - [x] 3.1 `business_fetchers._dispatch` 将 filters 完整传到 module-cell resolver；将 `filters.node_key` 传入附注 fetcher
  - [x] 3.2 `_query_note_cells` 按 project/year/section 与精确 node_key 过滤；无 node_key 只查 NULL；加入稳定排序，不套用根 legacy fallback
  - [x] 3.3 扩展 note writeback 请求归属字段：project_id/year/section_id/node_key/record id/cell 定位与现有乐观锁字段；核查调用方并同步前端/API 类型
  - [x] 3.4 writer 在 `FOR UPDATE` 后复验所有归属字段、权限/状态与乐观锁；缺行/不匹配拒绝回滚，不 fallback 到 legacy
  - [x] 3.5 支持 dict 与二维数组行，保留行列及非目标 cell；对行列越界和不支持形状返回明确错误
  - [x] 3.6 真 SQLite/ORM writer 测试覆盖跨项目、跨年度、跨章节、跨节点伪造 ID、行不存在、乐观锁、对象/数组更新及独立事务复读；真发 HTTP 请求验证鉴权和响应
  - _需求：3.1~3.6；设计：§五、P6~P7_

- [x] 4. 普通合并报表按节点读时计算
  - [x] 4.1 `GET /api/consolidation/reports/{project_id}/{year}` 增可选 node_key；缺省选当前树根；显式键经当前项目/年度树精确验证，非法键/年度明确拒绝
  - [x] 4.2 复用 `load_view_context`、`node_measures`、`consol_report_values`，按 node_key 计算所选 report_type；不从项目级物化金额冒充非根金额
  - [x] 4.3 保留 `ConsolReportRow[]` 既有字段语义；本期/上期按同节点共享口径计算，缺节点/公式不支持给 null 与原因；股东权益表不由项目级 enrichment 覆盖节点金额
  - [x] 4.4 不写 `FinancialReport`、不改其唯一键和 generate/push 写入流程；报表 config 不存在时返回明确错误
  - [x] 4.5 真 ORM/SQLite 集团测试 + FastAPI 真请求：至少两个同企业不同角色节点、缺省根兼容、非法节点、全部报表字段契约、节点金额与同节点 trial/breakdown 逐行对拍、上期缺失原因、非根不读根物化值
  - _需求：4.1~4.5；设计：§六、P5、P8_

- [x] 5. 前端树节点共享上下文
  - [x] 5.1 `ConsolidationIndex.vue` 将 `{code,name,nodeKey}` 单一上下文传给报表加载器和 `ConsolNoteTab`；实体类型要求 nodeKey
  - [x] 5.2 报表请求经 `GET /api/consolidation/reports/{project_id}/{year}` 显式发送 nodeKey；附注所有节点级读取/写入/公式/审核/刷新/聚合/穿透请求传当前 nodeKey；独立穿透选择以当前节点初始化
  - [x] 5.3 报表和附注缓存键包含 project/year/nodeKey/report-or-template 维度；刷新仅清除对应节点缓存
  - [x] 5.4 加请求上下文与递增序号保护，切项目/年度/nodeKey 后旧响应不得提交；不能只依赖缓存或取消请求
  - [x] 5.5 API/组件测试覆盖透传、同企业同角色身份区分、缓存分区与局部清理、请求乱序、差额穿透独立选择；用户可见错误中文
  - _需求：4.5、5.1~5.5；设计：§七、P9_

- [~] 6. 端到端回归与契约收口
  - [x] 6.1 定向运行合并附注公式、合并报表视图、module-cell resolver、snapshot writer 与相关端点测试；将预存失败与本 spec 新增失败分开记录
    - 证据：定向后端回归 **346 passed, 136 warnings, 65.39s**；按运行结果收口，本轮定向回归未报告失败。
  - [x] 6.2 真 FastAPI 请求覆盖成功/拒绝、权限依赖、响应 envelope、旧 body node_key 与 query 优先级；不得以 service-only 测试替代
    - 证据：真实 FastAPI HTTP 回归 **69 passed, 53 warnings, 49.01s**，覆盖真实请求成功/拒绝及端点依赖链；另有前端 Vitest **52 passed**、目标 ESLint **0 errors / 4 warnings**、Core 单区域 `vue-tsc` 通过。
  - [x] 6.3 审查全量 SQL 对 `consol_note_data` 的查询/更新，确认不存在绕过作用域 helper 的附注节点读写；节点金额无第二套 company_code 算法
    - 证据：已完成全仓访问核对；节点查询按 `project_id/year/section_id/node_key` 限定，旧调用只匹配 `node_key IS NULL`。唯一裸 `UPDATE` 位于 `snapshot_writer_modules.write_note_cell`：先按记录 ID 锁行，再逐项复验 `project_id/year/section_id/node_key`，随后执行乐观锁检查；HTTP 路由另执行项目编辑权限校验。`_mark_notes_stale` 只按 `project_id/year` 标记 `is_stale`，登记为合法的项目/年度级例外。普通报表当前节点金额经 `load_view_context`、`node_measures`、`consol_report_values` 计算；`company_code` 仅出现在旧上期物化兼容、展示等路径，不作为节点金额算法或节点身份。
  - [~] 6.4 执行定向 lint/type/test；前端类型检查使用本仓可运行的单区域配置并用 TS2322 变异证明目标文件实际纳入检查
    - 证据：Core 单区域 `vue-tsc` 通过；在其纳入的 `consolCacheKeys.ts` 临时注入 `const mutation: number = 'TS2322'` 后，检查实际报告 TS2322；删除变异后再次运行 Core `vue-tsc` 通过。限制：Scope 配置在 4GB、6GB 堆下均 OOM，因此全量 Scope 类型检查未完成，不能记为通过。环境/既有阻塞：`GET /api/report-config/types?scope=consolidated` 返回 422。
  - [~] 6.5 Playwright 真浏览器：切换两个树节点、普通报表重载、附注保存后重读、快速切换制造响应乱序、确认数据互不串用；环境不可运行则保持未完成并记录阻塞
    - 浏览器证据：通过真实点击和真实网络请求完成树节点切换、普通报表刷新、附注保存/reload/节点切换；普通报表乱序实验中，母公司请求先发并延迟约 12 秒，本部请求后发且先完成，最终 UI 保持本部节点并显示 129 行报表；无 `requestfailed`。限制：未提供附注请求自身延迟/乱序的 Playwright 证据，因此本项保留部分完成。运行时记录：存在 Vue directive warning；历史运行曾出现 `resetWorksheetData` ReferenceError 与 401，作为既有运行时限制如实保留，不据此声称本轮浏览器流失败或通过相关未覆盖场景。
  - [x] 6.6 按需求 1~6 与设计 P1~P9 逐项复核覆盖，检查三件套链接、端点名/字段名、所有任务证据完整；未实际验证的任务不打勾
    - 证据：已逐项核对需求 1–6、设计 P1–P9、三件套交叉引用、端点名/字段名与任务证据闭合；Scope OOM、422 及未实测的附注请求乱序仍明确保留为未完成/限制，没有据静态检查或非浏览器证据标绿。
  - _需求：6.1~6.5；设计：§八~§十_


## 新增任务：合并工作底稿、公式运行时与动态股比

> 以下任务承接既有 1~6，不改变既有附注节点隔离任务的证据状态。所有新增任务初始未完成；只有代码、定向测试和运行时证据齐全后才能标 `[x]`。

- [ ] 7. 第一批修复：父页年度、页签隔离与工作底稿错误状态
  - [ ] 7.1 `ConsolidationIndex.vue` 将父页有效 `projectId/year` 显式传入 `ConsolWorksheetTabs`；子组件删除 route/query 和当前日期年度猜测
  - [ ] 7.2 工作底稿加载、保存、上年提取、G7 预览/导入和公式重载统一消费父页年度；页面年度变化时清理或标记旧年度数据
  - [ ] 7.3 API 层区分成功空数据、非 2xx/网络失败和响应解析失败；组件显示中文 empty/error 状态，不能 catch 后返回 `{}` 伪装空表
  - [ ] 7.4 保持工作底稿当前项目/年度级作用域，不追加伪 `node_key`；左树切换仍只更新报表/附注节点上下文，右侧页签切换不改左树节点
  - [ ] 7.5 修正总分汇总提示条件，覆盖根节点、母公司节点和单户节点；补前端 API/组件测试
  - _需求：7.1~7.6；设计：§十一、ADR-CNSC-006~007、P10_

- [ ] 8. `consol_worksheet` 公式 Runtime 真实读写
  - [ ] 8.1 扩展 `CanonicalFormulaTarget`、scope/domain 映射和公式 locator，明确 project/year/sheet/row/cell 身份
  - [ ] 8.2 实现 `ConsolWorksheetDomainReader`：批量读取项目/年度表，支持对象行/二维数组，区分 miss 与数据库/解析 error
  - [ ] 8.3 实现 `ConsolWorksheetMutationAdapter`：真实 JSON 更新、updated_at/CAS 检查、事务失败回滚、restore 和审计 source formula/run 身份
  - [ ] 8.4 接入 coordinator 的 reader/adapter 和公式执行结果；fresh read 可见，不能只修改前端 `formulaResults` 或内存 dict
  - [ ] 8.5 为长投、关联往来、关联交易增加可编辑 source scope/binding，按精确 node_key 和子树读取既有报表/附注/底稿域
  - [ ] 8.6 补真实持久化/CAS/错误区分测试；如现有 schema 不足以可靠 CAS，提出独立 V/R 迁移而不是伪造版本
  - _需求：8.1~8.6；设计：§十二、ADR-CNSC-008、P11_

- [ ] 9. 动态股比事件和正式抵销建议链路
  - [ ] 9.1 设计并实现 1~N 事件 DTO/ORM/迁移/API，包含稳定 ID、日期、序号、前后比例、来源、状态和计算版本
  - [ ] 9.2 将 G7-10 等来源行规范化为事件并幂等 upsert；保留来源行 identity，重复导入不得生成重复事件
  - [ ] 9.3 将 `ShareChangeSheet` 从固定 `1 | 2 | 3` 投影改为事件集合驱动；动态生成第二次、第三次及第四次以上列/行并显示校验错误
  - [ ] 9.4 实现期间净资产追溯、比例变化、权益法模拟、资本公积/投资收益/NCI 影响；与长投/关联交易公式 source scope 对接
  - [ ] 9.5 生成带 project/year/node/event IDs 和计算版本的抵销建议；draft 不入账，确认并 approved 后才进入现有 elimination recalc/push
  - [ ] 9.6 补 1/2/3/4 次事件、日期/序号排序、三次追溯、重复 G7 导入和 draft/approved 链路测试
  - _需求：9.1~9.8；设计：§十三、ADR-CNSC-009~010、P12~P13_

- [ ] 10. 扩展端到端验证与任务收口
  - [ ] 10.1 定向运行既有节点隔离/报表/附注测试，并分离并发工作树预存失败与本轮新增失败
  - [ ] 10.2 运行工作底稿 API/组件、公式 Runtime、动态股比和抵销链路测试；失败状态不得以静态检查替代
  - [ ] 10.3 使用单区域前端 tsconfig 做类型检查，并用 TS2322 变异证明目标文件确实被纳入检查；后端按 Windows 规则运行 `python -m pytest`
  - [ ] 10.4 Playwright 验收根节点、母公司节点、单户节点：父页有效年度请求、空/错状态、右侧页签不改左树、报表/附注节点联动及 1/2/3 次股比显示
  - [ ] 10.5 对照需求 1~10、P1~P13、ADR 和任务证据逐项复核；仅已实际验证的任务标 `[x]`
  - _需求：10.1~10.5；设计：§十四~§十五_
