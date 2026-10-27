# 实施计划：凭证身份、底稿回写与预审/年审阶段（voucher-identity-writeback-and-audit-phase）

> 以 design.md 为准。每个任务可独立验收；标完成须有代码 + 测试证据 + 至少一条磁盘变异证明（原文件与 sha256 备份到 `tmp_voucher_identity/mutations/`，注入缺陷，确认对应测试红且红在预期处，逐字节还原并核对 sha256）。环境做不到的标 `[ ]*` 并写「代码已改但未实测」。
> 约束：PowerShell 用 `;` 不用 `&&`、用 `cwd` 不 `cd`；含中文或正则的脚本写成 `.py` 放 `tmp_voucher_identity/probes/`；行数用 Python `len(text.split("\n"))`；后端 `python -m pytest -p no:playwright`，hypothesis `max_examples=5`，PG 专有 SQL 加方言判断；前端 vitest + 单区域 tsconfig；浏览器实测用 chrome-devtools、关键点击前校验 `location.pathname`、写入型验收只用【测试】项目并走平台路径清理对账。宿主文件常被并发会话修改：每批在 `tmp_voucher_identity/verify_wt` 私有 worktree 动手前重读，提交前 `git diff --cached --name-only` 只含本批文件。

## 阶段 A：凭证身份

- [x] 1. 真实账测试向量与跨语言样例
  - 从真库只读导出固定夹具：四川物流 FY-0012、2025-01-07「0003」（FY 与 ZZ 两张）、一张 1 对多、一张红蓝混合、一张借贷双填（辽宁卫生）、一张超 200 行凭证的前 201 行；6 套账的凭证键计数与医疗器械银行存款整张凭证单位数（8,592）记入夹具头部
  - 跨语言样例 `voucher_identity_vectors.json`：输入分录 → 期望 vk / side / lfp
  - Files: `backend/tests/fixtures/voucher_identity_vectors.json`、`backend/tests/fixtures/voucher_real_ledger_vectors.json`；导出探针 `tmp_voucher_identity/probes/export_vectors.py`（交付后删）
  - Verify: `test_voucher_vectors_sane.py` 断言夹具非空、每张凭证借贷合计相等（双填凭证除外并标注）
  - 证据（2026-10-27）：`test_voucher_vectors_sane.py` 17 passed（7 张凭证各属一张凭证、6 张借贷相等、双填两行均为 X、各自特征、计数快照形状）；超 200 行凭证实际导出整张 202 行。变异 m01：FY-0012 一笔贷方 1680.00 → 1681.00 ⇒ `test_debit_equals_credit[fy0012_many_to_many]` 红，sha256 还原一致。顺带修 `consolidation_models.ConsolNoteTemplatePushLog.failures` 的 `'[]'::jsonb` 默认值（SQLite 建表即报错，基线 117 例 setup 阶段失败）+ 守卫 `test_orm_server_default_dialect_neutral.py`（变异 m00 红）

- [x] 2. 凭证身份单一实现（需求 1）
  - 后端 `voucher_identity.py`（ADR-VK-01~04）：`VoucherKey`、`side_of`、`signed_amount`、`fingerprint_lines`、`voucher_key_sql`、`resolve_line_fps`
  - 前端 `utils/voucherIdentity.ts`：`voucherKeyString`、`sideOf`、`lineFingerprint`
  - Files: `backend/app/services/voucher_identity.py`、`audit-platform/frontend/src/utils/voucherIdentity.ts`、`backend/tests/test_voucher_identity.py`、`backend/tests/test_voucher_identity_real_ledger_pg.py`、`audit-platform/frontend/src/utils/__tests__/voucherIdentity.spec.ts`
  - Verify: 两边读同一样例逐字相等；pg_only 真库 6 套账凭证键计数、FY/ZZ-0003 两个键、`resolve_line_fps` 在回滚事务内复制一张凭证到新数据集后仍命中。变异：键去掉凭证字 → 「0003」用例红；指纹加回摘要 → 改摘要后命中用例红
  - 证据（2026-10-27）：后端 `test_voucher_identity.py` 66 passed（11 条行样例 + 1 条分组样例、真实凭证指纹唯一 / 改摘要不变 / 与顺序无关、SQLite 行值 IN / NOT IN、空凭证字匹配 NULL、重导后解析到新行、指定旧数据集解析到旧行）；真库 `test_voucher_identity_real_ledger_pg.py` 8 passed（6 套账 SQL 键计数 = Python 键计数，6 套账 0 个凭证键借贷不平，混凭证字三套按 (日期, 号) 少于按凭证键；FY/ZZ-0003 两张各自平衡；回滚事务内建数据集复制 FY-0012 并激活后指纹解析到新行），跑后核对真库无残留数据集与分录；前端 `voucherIdentity.spec.ts` 18 passed，单区域 tsc 0 错（同配置加类型错误探针报 2 个 TS2322，证明检查在跑）
  - 真库测试抓到的缺陷：`voucher_key_sql` 的空串写成绑定参数时，SELECT 与 GROUP BY 编成 `$1` / `$5` 两个表达式，PG 报 GroupingError（SQLite 不报）⇒ 改 `literal_column("''")` + 编译期断言 `test_voucher_key_sql_has_no_bind_params_for_pg_group_by`
  - 与 design §2 的偏离：函数名按 design（`signed_amount`、`voucher_key_sql`）；`voucher_key_sql` 含主体编码共四列（design 写三列漏了主体；真库 4 个 active 数据集一套账有两个主体编码）。前端另有 `describeLine` / `amountString` / `normText`；空白口径按 Python `str.strip()`（JS `trim()` 会去 BOM、不去 \x1c-\x1f，样例各一条）；舍入显式传 `ROUND_HALF_UP`（`ledgerDisplay.ts` / `useDecimalCalc.ts` 把全局 Decimal 改成银行家舍入）
  - 变异（均在私有 worktree，sha256 还原一致）：m02 `VoucherKey.of` 丢凭证字 ⇒ 22 红，含单元「0003」用例（两键相等）与真库 `test_fy_zz_0003`、三套混字账计数；m03 `voucher_key_sql` 丢凭证字 ⇒ 12 红，含分组计数 (3,3)≠(4,3) 与真库三套混字账计数；m04b 摘要并入指纹（不影响取行）⇒ 改摘要 8 例、SQLite 与真库重导用例红，未改摘要的解析用例保持绿；m05 前端舍入改 HALF_EVEN ⇒ 「负数五入远离零」等 2 红；m06 前端改用 `trim()` ⇒ 3 红

- [x] 3. 迁移 V{n}：挂凭登记表补凭证字与阶段（design §8 前半）
  - 现扫 MAX(V*.sql)+1 取号；`sampled_vouchers` 加 `voucher_type`、`phase` + 约束；重建手工侧与批次唯一索引；R{n} 回退；ORM 与 schema 同步
  - Files: `backend/migrations/V{n}__voucher_identity_sampled_vouchers.sql`、`R{n}__…sql`、`backend/app/models/workpaper_models.py`
  - Verify: `MigrationRunner(...).run_pending()` 落本地库；三层一致测试；同批次两张同号不同日凭证都能登记（N3）。变异：批次索引去掉 voucher_date → 该用例红
  - 证据（2026-10-27）：取号 **V210**（现扫：主树 V209 未入库属他会话；远端本分支已有 V206 / V207，`wt` worktree 另有 V206 / V207，attachment-security-baseline spec 记了 V208 / V209 ⇒ 206~209 都不能用；另见远端 V206 与 `wt` 的 V206 撞号，属他会话）。`V210__voucher_identity_sampled_vouchers.sql` / `R210__rollback_…sql`；先在回滚事务里演练 V210 → V210（幂等）→ R210 → V210，再用只含 V210 的临时目录跑 `MigrationRunner.run_pending()` 落本地库（executed ['210']，不顺带执行他会话未落库的迁移）。`test_sampled_vouchers_voucher_key.py` 17 passed（含 5 条 pg_only：同批次 FY-0003 / ZZ-0003 / 别日 0003 三张都登记、重复登记 0 行、换批次再登记 3 行；旧格式日志重复登记 0 行；手工侧同日同号不同凭证字分别挂、空凭证字与 NULL 同一张；阶段约束；本地库索引含新列），`test_sampling_registry_service.py` 等既有 84 例全过；迁移类守卫 worktree 前后对比失败集合相同（4 条预存：V/R 配对旧迁移缺 R、drift ledger V200 / V201、`gt_wp_type` 绑定）
  - 与 design §8 的偏离：①多加 `company_code`（凭证键含主体，design §8 漏了，同 §2）②两个索引名沿用旧名、批次索引谓词保持 `is_deleted = false`（ON CONFLICT 的 index_where 须与之一致；design 写的新名与 `AND batch_id IS NOT NULL` 作废）③批次索引的日期 / 主体 / 凭证字用 COALESCE 表达式列：旧格式回填日志只有凭证号，不折叠的话 NULL 互不相等、同批次可重复登记 ④`register_sampled_vouchers` 本任务就改成读 `filled_voucher_keys`（无则退回 `filled_voucher_nos`）并写阶段 —— 索引一换，ON CONFLICT 目标必须同时换，否则登记被 fail-open 吞成 WARNING 静默失败；新解析函数 `voucher_identity.parse_voucher_keys`
  - 变异（worktree，sha256 还原一致）：m07 V210 批次索引去掉日期表达式 ⇒ `test_batch_index_keys_on_voucher_key` 与 `test_conflict_target_columns_match_migration_index` 红；m08 登记退回只按号 ⇒ 单元用例与 pg_only N3 用例红

- [x] 4. 凭证穿透与下钻按凭证键（需求 2.1）
  - 两个服务方法与两个路由增 `voucher_type`；多凭证字歧义返回 409 `VOUCHER_KEY_AMBIGUOUS` + 候选；每行带 `side`、`line_fp`；改正 N4 注释
  - 前端：序时账凭证层带凭证字穿透、409 时弹候选选择；`useAttachedVouchers.fetchVoucherLines` 带凭证字
  - Files: `ledger_penetration_service.py`、`drilldown_service.py`、`routers/ledger_penetration.py`（净增 0 行）、`routers/drilldown.py`、`LedgerPenetration.vue`、`useAttachedVouchers.ts`
  - Verify: 端点级 TestClient：同日同号两凭证字 → 409 + 2 个候选；带凭证字 → 只返回本凭证分录。浏览器：四川物流【测试】副本上穿透「0003」出现候选。变异：去掉凭证字条件 → 合并分录用例红
  - 证据（2026-10-27）：歧义判定与候选、行补 `voucher_key` / `side` / `line_fp` 收在 `voucher_identity`（`VoucherKeyAmbiguous` 继承 HTTPException，全局处理器即出 409，路由不另写分支）；只给号跨日期也按 409 列候选（需求 2.1「不合并分录」，原先返回全年同号凭证合计）。`ledger_penetration.py` 1714 → 1711 行。后端 `test_voucher_key_penetration.py` 9 passed（服务层：日期 + 号两凭证字 409 且 2 个候选、带凭证字只回本凭证 3 行且指纹与 `fingerprint_lines` 一致、只给号列 3 个候选、空凭证字匹配 NULL、下钻同口径且 `is_balanced` 只算单张、候选上限 50 + truncated；端点级：两个路由 409 → 带凭证字 200、非项目成员 403）。前端 `voucherIdentity.spec.ts` 21 passed（含 409 读取与「字-号」称呼）、`pullSamplesForWorkpaper.spec.ts` 18 passed（回拉带凭证字且静默、空串照传、旧行不传、409 时占位样本列出候选并提示重新挂凭、不并入分录）；单区域 vue-tsc 与 HEAD 同口径对比：HEAD 10 个错、改后 5 个错且全是 HEAD 已有（扩 `Crumb` 类型顺带消掉 5 个旧错），新增 0
  - 浏览器（私有栈：worktree 后端 9981 跳过全部 worker 与启动重放 + 私有 Vite 3031 独立 cacheDir；共享 9980 未带 --reload、未重启）：🔴 四川物流 / 宜宾临港 / 那套辽宁卫生（37814426）项目已软删（`/api/projects/{id}` 404，页面打不开），改用未删除的辽宁卫生项目 d9295a0c（只读，库里 1,247 组同日同号混凭证字）：按 URL 恢复到「0004 / 2025-01-03」→ 候选 ZJGJ-0004（借 4,000,000.00）与 ZZ-0004（借 100,000.00），工具栏复制 / 抽中 / 挂凭按钮禁用；点 ZZ 的「查看」→ 只出 2241.12 与 2241.98.06 两行，标签与面包屑「ZZ-0004（2025-01-03）」；控制台唯一报错是浏览器记录的那次 409
  - 变异（worktree，sha256 还原一致）：m09 服务去掉凭证字条件 ⇒ 带凭证字只回本凭证、空凭证字、端点 200 三例红；m10 歧义判定恒放行 ⇒ 6 例红（服务、下钻、上限、两个端点）；m11 前端回拉不传凭证字 ⇒ 2 例红
  - 预存失败（HEAD 干净 worktree 复现，与本任务无关）：`test_ledger_penetration.py` 的 `test_entries_api` / `test_aux_entries_api` / `test_paginated_sums_match_full_aggregate`

- [x] 5. 抽样链路按凭证键与分录指纹（需求 2.2~2.4、2.6~2.7）
  - `enrich_voucher_context`（按凭证键、日期收窄）；整张凭证抽样单位按凭证键；`LedgerQueryFilters` 增 `exclude_voucher_keys` / `exclude_line_ids`；三处排除、截止测试排除、登记表、项目级排除、重复提示、概览、幂等键全部换口径；旧日志兼容并回 `legacy_exclusion`
  - 单一来源守卫 `test_voucher_identity_single_source.py`（AST，基线只许变短，交付时为空）
  - Files: `ledger_sampling_service.py`、`routers/voucher_sampling.py`、`routers/cutoff_sampling.py`、`sampling_registry_service.py`、对应测试
  - Verify: 医疗器械银行存款整张凭证单位数 = 8,592（pg_only）；预审批次按 lfp 排除后重导（回滚事务内复制成新数据集）仍排除；同号别月凭证不被排除。变异：排除改回凭证号 → 别月凭证用例红；守卫基线加回一条旧写法 → 守卫红
  - 证据（2026-10-27）：排除口径收在新模块 `voucher_sampling_exclusion.collect_exclusions`（取代路由里 4 个按号 / 按行 id 的辅助函数与截止测试的 `_get_extracted_voucher_nos`），两个路由经 `SamplingExclusions.filter_kwargs()` 同一映射交给 `LedgerQueryFilters`；登记表三个查询迁到 `sampled_voucher_queries.py`（登记服务已到行数上限，原处保留同名导出）。后端：新测试 `test_voucher_sampling_exclusion.py` 22 例（SQLite 真 ORM 行走生产路径：同日同号别凭证字与同号别月不被排除、重导后按指纹仍排除、旧日志行 id 重导后失效并标 legacy、只有凭证号的旧日志按号排除并标 legacy、撤销 / 别底稿 / 别类型不排除、整张凭证与截止测试按键、年审排除预审、项目级取登记表、跨底稿重复与概览按键、幂等键、两个路由映射、内存路径整张凭证按键）、`test_voucher_sampling_row_exclusion.py` 改写 26 例（原测试在测试里抄了一份排除逻辑，改为编译真实 `build_ledger_query`）、真库 `test_voucher_sampling_exclusion_pg.py` 5 例（医疗器械 1002 整张凭证单位 8,592、只按号 692；四川物流 FY-0012 预审分录按指纹排除，整套账 22,716 行复制成新数据集激活后排除新行；全年数十张「0003」只排 01-07 FY-0003，旧日志按号全排并标 legacy；FY-0012 凭证上下文 5 行与指纹、辅助明细账补全在真库无 WARNING；登记表三个查询按键），跑后核对真库无残留（数据集仍 c428ac95 active、回填日志 0、登记 0）；守卫 `test_voucher_identity_single_source.py` 5 例。worktree 跑「要提交的那棵树」抽凭 / 截止 / 凭证 36 个测试文件 568 passed、0 failed（含真库）。前端：样本带 `voucherKey` / `lineFp`，回填写 `filled_line_fps` / `filled_voucher_keys`（有一行缺指纹就整批不发指纹，后端退回按凭证键），跨底稿重复按凭证键剔除并写 `duplicate_voucher_keys`，旧记录 / 找不到的已抽分录提示，抽凭历史标「旧记录按凭证号排除」，截止测试回填带键与指纹；`voucherSamplingIdentityPayload.spec.ts` 7 例 + `voucherIdentity.spec.ts` 加 2 例，worktree 10 个相关 spec 221 passed；单区域 vue-tsc 0 错（同配置加探针报 2 个 TS2322，证明读到了改过的类型）
  - 浏览器（私有栈 9981 + 3031，未重启共享 9980）：医疗器械（5e193c68，未删除的真实项目，只读）E1「货币资金收支检查情况表E1-23」打开抽凭引擎 → 整张凭证、随机 6 张 → 总体 20,772 笔，6 张凭证 19 行，每行有凭证键与分录指纹且都在本凭证分录里，排除计数 0、`legacy_exclusion` false；点「确认填充」时页面里拦截全部写请求（改发到不存在的接口），拿到的回填载荷 19 个指纹与抽样结果逐个对上、6 个凭证键、阶段 final；配置弹窗两处说明已改成按凭证 / 分录；抽凭历史抽屉正常。核对真库：该底稿回填日志 0、登记 0、版本快照 0，当天 4 个编辑锁都已释放
  - 🔴 HEAD 本身打不开带程序表的循环宿主（与本任务无关，共享 3030 同样）：`GtAProgramConsole.vue`（40561d2c6）引用从未入库的 `useProgramOverrideTarget` / `useProgramRowControl`，`useProgramRowDelegate.ts`（3f7d857d2）引用不存在的 `useScopeExpansionRetry` 与 `ensureProgramRowTask`。私有 worktree 里临时加桩才完成上面的浏览器实测（清单 `tmp_voucher_identity/WT_STUBS.txt`，不入库）
  - 与 design §2 的偏离：①幂等键在分录指纹之外，没有指纹时用凭证键（截止测试按整张凭证回填，只按号会把 FY-0003 与 ZZ-0003 判成同一批而丢掉第二批）；旧日志（只有凭证号）派生的键与改造前逐字相同 ②行值 IN / NOT IN 单条语句上限 `MAX_KEYS_PER_STATEMENT = 7000` 个凭证键（每键 4 个绑定参数，asyncpg 上限 32,767），超过抛 ValueError 转 400 并说明原因，不拆多段（同一语句里拆段不解决上限） ③内存路径整张凭证单位按凭证键聚合，合成总体的 `voucher_no` 仍放号本身，系统抽样排序与两阶段路径同口径
  - 变异（worktree，sha256 还原一致）：m12 已抽排除改回按凭证号 ⇒ 6 红（整张凭证 / 截止测试别月凭证被连带排除、真库全年「0003」被排空等）；m13 `build_ledger_query` 换回 `voucher_no.notin_` ⇒ 守卫 2 红（新增违规 + 豁免失效），行为用例照绿（两种写法等价，只有守卫抓得到）；m14 分录行排除退回只认旧行 id ⇒ 9 红（含真库重导用例）；m15 内存路径整张凭证按号聚合 ⇒ 1 红（两张「0003」并成一个单位、抽中带出 4 行）；m16 前端跨底稿重复按号剔除 ⇒ 1 红；m17 前端缺指纹仍发部分指纹 ⇒ 1 红；m18 幂等键不认凭证键 ⇒ 1 红

- [x] 6. 挂凭按凭证键并记阶段（需求 2.5）
  - `/ledger/sample-voucher` 收凭证字、阶段（缺省取项目阶段，任务 8 前取 final）；列表返回凭证字与阶段；回拉按凭证键
  - Files: `routers/ledger_penetration.py`（净增 ≤ 0 行，必要时把挂凭三端点整体移到任务 14 的新路由并保持原 URL）、`useAttachedVouchers.ts`
  - Verify: 同日同号两凭证字分别挂同一底稿得到两条记录；回拉只取各自分录。变异：去重键去掉凭证字 → 用例红
  - 证据（2026-10-27）：挂凭三端点整体移到新路由 `routers/voucher_links.py`（URL 不变，在 `router_registry/system.py` 注册；`ledger_penetration.py` 1711 → 1512 行）。服务端按当前账套 `single_voucher_lines` 解析凭证键：同日同号多张凭证且没给凭证字 ⇒ 409 `VOUCHER_KEY_AMBIGUOUS` + 候选，账套里没有这张凭证 ⇒ 404 `VOUCHER_NOT_FOUND`（不登记未经校验的键）；去重条件与 V210 手工侧唯一索引是同一组 COALESCE 表达式，复活已删行时未删行优先；`phase` 只收 preliminary / final（其他 422），缺省 final。后端：`test_voucher_links.py` 11 例（同日同号两凭证字各一条且回拉各取各的、缺凭证字 409 且不落库、唯一号由账套补全、找不到 404、同底稿重复挂幂等并复活、两张底稿与别月各自成条、手工侧不碰引擎行、旧行不改写、阶段记录 / 缺省 / 校验、只读成员 403 与非成员 403、真实应用里三条路由各注册一次）；真库 `test_voucher_links_pg.py` 1 例（回滚事务内四川物流 FY / ZZ-0003 各挂一条、无凭证字 409、重复挂幂等，回拉 FY 2 行 / ZZ 3 行；跑后真库 sampled_vouchers 0）；`test_sampled_voucher_scope_and_date.py` 里读源码的去重用例改由上面的行为用例取代；单一来源守卫 EQ 规则细化（按号比较须同函数同时引用公司、日期、凭证字，或调 `single_voucher_lines`），基线清空、`_BASELINE_MAX = 0`。worktree 46 passed、5 skipped；守卫与相关回归 333 passed、8 failed，8 例均为预存（lazy import 引用并发会话未入库的模块、`coverage_ledger_drift_guard`、`test_ledger_penetration` 已知 3 例）。前端：`attachVoucher` 带凭证字、主体、阶段（`_silent`）+ `attachFailureReason`；挂凭弹窗逐张收集失败原因，标签显示「日期 字-号」；序时账凭证层去重键含凭证字，「抽中本凭证」改走 `attachVoucher`；回拉样本带 `voucherKey` / `lineFp`；`attachVoucherIdentity.spec.ts` 5 例，相关 spec 46 passed；单区域 vue-tsc 4 个错误均为预存（HEAD 同样报）
  - 浏览器（私有栈 9981 + 3031，辽宁卫生 d9295a0c 真实项目只读，页面里拦截全部写请求）：凭证层打开 2025-01-03「0004」⇒ 弹候选，选 ZZ；挂凭弹窗标签「2025-01-03 ZZ-0004」，选 A10 底稿点「挂入底稿（1 张）」，拦到的载荷带 `voucher_type: "ZZ"`、日期与科目；被拦截的请求返回 404，界面提示「1 张凭证没挂上：2025-01-03 ZZ-0004：当前账套里没有这张凭证（可能账套已重导）」，失败原因路径走通；「抽中本凭证」载荷同样带 `voucher_type: "ZZ"`。核对真库 sampled_vouchers 0、当天编辑锁全部已释放
  - 与任务描述的偏离：①凭证键由服务端按账套解析，不登记前端给的未校验键（歧义 409、找不到 404）②V210 前的旧行（无凭证字 / 主体）不改写，挂同一凭证时新建带凭证字的一行，旧行回拉时 409 提示重新挂凭 ③阶段缺省 final，任务 8 改取项目阶段
  - 变异（worktree，sha256 还原一致）：m19 去重条件去掉凭证字 ⇒ 3 红（SQLite 两凭证字用例、真库用例、守卫）；m20 解析不认凭证字 ⇒ 7 红；m21 前端挂凭不发凭证字 ⇒ 2 红；m22 回拉丢凭证键与指纹 ⇒ 1 红

## 阶段 B：项目审计阶段与回写契约

- [ ] 7. 多借多贷精确配对（需求 3）
  - `voucher_pairing.pair_voucher`（design §3），接入 `enrich_voucher_context` 与凭证穿透响应
  - Files: `backend/app/services/voucher_pairing.py`、`backend/tests/test_voucher_pairing.py`
  - Verify: FY-0012 两笔付款配到应付职工薪酬、管理费用配到贷方应付职工薪酬；等额多解 → multi；201 行 → large；性质测试金额守恒与顺序无关。变异：去掉唯一解判断 → 多解用例红；去掉第 6 步校验 → 冲突用例红

- [ ] 8. 项目审计阶段与预审截止日（需求 6.1、6.2、6.5）
  - 迁移 V{n+1}：`projects` 两列（design §8 后半，`interim_survival_checks` 表一并建）；ORM / schema / 项目详情与更新接口；角色判定（经理、合伙人含签字合伙人、admin）与审计日志
  - 前端 `useProjectAuditPhase`；项目设置「年度准则」页「审计阶段」区块
  - `voucher-extract` 的 `phase` 改 Literal，缺省取项目阶段，非法 422
  - Files: 迁移两文件、`models/core.py`、`schemas/core.py`、项目路由、`ProjectSettingsCenter.vue`、`composables/useProjectAuditPhase.ts`
  - Verify: 端点表驱动测试（经理 / 合伙人可改、审计员 403、非法值 422）；浏览器改阶段后刷新读回。变异：放开审计员 → 403 用例红

- [ ] 9. 共享回填函数与引擎改造（需求 4.1~4.6、4.8、6.3）
  - `voucherCheckFill.ts`（design §4）、`VoucherRowMetaTag.vue`、`VoucherPairingCell.vue`、全局 `.gt-row-locked` 样式
  - 引擎：样本带 vk / lfp / pairing / 批次号；emit `undo-request`；删视图条与 `existingSamples`；日志写 `filled_line_fps` / `filled_voucher_keys`；阶段从项目读并显示
  - Files: `composables/shared/voucherCheckFill.ts`、两个新组件、`GtVoucherSamplingEngine.vue`、`useVoucherSampling.ts`、`useSamplingPhase.ts`、`expandMultiAccountVouchers.ts`（改为转调或删除，删前 grep 调用方）
  - 任务 5 留下的引擎侧遗留：预览「人工增补凭证」（`SamplingPreviewDialog.handleAppendSearch`）只按凭证号去重，同号别日 / 别凭证字会被当成已有行；`useCutoffAutoSampling.applyFillMode` 与引擎 `applyFillMode` 的合并去重仍按凭证号（F6），改由共享回填函数按分录指纹去重
  - Verify: `voucherCheckFill.spec.ts`：追加去重、替换只动本阶段抽凭行、已填行确认、旧行触碰迁移、撤销确认与取消、年审预审行 `guardPersist` 写回；引擎行数不超限。变异：追加去掉去重 → 重复导入用例红；替换不限阶段 → 预审行被删用例红

- [ ] 10. 宿主接入一：D、E 循环（需求 4.7、6.4）
  - D1~D7、D4 检查、E1 两个 tab：回填改调共享函数、解析套 `withRowMeta`、表格加行样式与标签列、删字面量 phase；D2 去掉 append → replace 映射；挂凭导入改幂等
  - 接入守卫 `voucherCheckFillAdoption.spec.ts` 建立冻结清单（全部未接入宿主），本批完成后删去对应项
  - Verify: 每个宿主的回填单测（抽凭两次、挂凭导入两次不重复）；浏览器抽查 D2、E1。变异：清单加回 D2 → 守卫红

- [ ] 11. 宿主接入二：F 循环与 G 循环（同任务 10 的三处改动）
  - F1、F2 四个 tab、F3、F4、F5；G1 两个、G2、G4、G5、G6、G7 两个、G8、G9、G10、G11、G12（G5 改用独立的本期 / 期后字段）
  - Verify: 同任务 10；浏览器抽查 F3、G9

- [ ] 12. 宿主接入三：H、I 循环
  - H1 两个、H2 两个、H3、H4 两个、H5 两个、H6、H8、H10；I1 两个、I2 七个、I3、I4、I5、I6 三个；H1 等内联拼接改用 `prepareSamples(..., 'join')`
  - Verify: 同任务 10；浏览器抽查 H1、I2

- [ ] 13. 宿主接入四：J、K、M、N 循环与在线编辑往返（需求 4.1、4.7、6.4）
  - J1、K1、K2、K3 三个（修 K3 空操作）、K4、K5 两个、K7、K8 四个、K9、K10、K12、K13、M1、M2、N2（J1 / K1 / M1 / M2 改用独立字段）
  - 带在线编辑的凭证检查 sheet 逐 provider 验证 `_gt` 往返（N1），丢失的在合并处透传非受管键
  - 接入守卫冻结清单清空
  - Verify: 同任务 10；每个 provider 一例往返测试；浏览器抽查 K3、K8。变异：某 provider 合并时丢弃 `_gt` → 往返用例红

- [ ] 14. 一张凭证挂多张底稿与已挂标识（需求 5）
  - 新路由 `routers/voucher_links.py`（批量挂凭、已挂查询）并在 `router_registry` 注册；挂凭弹窗多选、失败明细；序时账明细层与凭证层标签；改过期注释
  - Verify: 端点表驱动（edit / readonly / 越权 403、单次 500 键上限）；浏览器把 FY-0012 挂到应付职工薪酬与货币资金两张底稿，各自导入只出现本科目分录、金额与凭证对平。变异：批量接口去掉 SAVEPOINT → 单条失败致整批回滚用例红

## 阶段 C：年审口径、合并评价与存续核对

- [ ] 15. 年审抽样口径弹窗与排除（需求 7.1~7.4）
  - 新路由 `routers/sampling_phase.py`：`phase-context`；`voucher-extract` 增 `final_population_mode`（年审且有预审时必填）、口径 a 日期窗口、口径 b 排除清单；口径写入批次留痕，历史显示
  - `FinalPopulationModeDialog.vue`，缺省上次口径、首次 b
  - Verify: `test_sampling_phase_pg.py`：a 的框只含剩余期间；b 的框扣除预审分录且重导后仍扣除；缺口径 422。浏览器弹窗两选项。变异：口径 b 不扣手工挂凭 → 用例红

- [ ] 16. 两阶段合并评价（需求 7.5、7.6）
  - 评价增 `sample_error_total`、`combined`；`phase-evaluation` 按 ADR-VK-10 计算；引擎评价面板显示全年合并；抽样记录结论投影
  - Verify: 两公式各一组固定数；预审缺 `sample_error_total` 时不给结果；旧记录输出逐字节不变。变异：口径 b 改加预审推断 → 用例红

- [ ] 17. 预审样本存续核对（需求 8）
  - `POST /sampling/interim-survival` 与确认接口、`interim_survival_checks` upsert；宿主横幅、行状态标签、逐行确认；`voucher-coverage` 返回未确认数
  - Verify: `test_interim_survival_pg.py` 在回滚事务内造四种状态各一例；浏览器横幅与确认。变异：删第 3 步 → 重编号被判已删除，用例红

- [ ] 18. 验收与收尾（需求 9）
  - 【测试】项目浏览器全流程（需求 9.3），清理对账
  - 变异记录汇总表；和平药房抽凭接口耗时对比（design §10）；干净 worktree 跑「要提交的那棵树」的本 spec 测试与相关回归，失败集合与 HEAD 逐条对比
  - INDEX.md 登记、memory 更新；临时目录清理
