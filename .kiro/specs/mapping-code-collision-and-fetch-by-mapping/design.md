# 设计：科目自动匹配编码撞号 + 税审取数一级科目只认映射 + 存量修复

## 1. 自动匹配（`mapping_service.auto_suggest` / `_match_single`）
- 新模块 `account_name_compat.py`：`name_key` 归一（取「\」最后一段、去「其中：」、全半角括号、帐 → 账、去空白）；`same_account` = 全等 / 一方包含另一方（≥ 2 字）/ 同义表同组；`SYNONYM_GROUPS` 手工维护（现金 / 库存现金、低值易耗品 / 周转材料、应付工资 / 应付职工薪酬、应交税金 / 应交税费、营业收入 / 主营业务收入 等）；`current_noncurrent_conflict`（一方带「非流动」另一方不带）。
- 新模块 `mapping_level1_match.py`（`mapping_service.py` HEAD 已 1014 行，新逻辑放这里）：编码归一（`strip_dot_zero` / `level1_code` / `normalize_code`）、标准一级科目名称索引（同名多码取 6xxx）、一级科目名 → 标准科目（全等再同义，不模糊）、客户一级科目上下文、`find_code_collisions`。
- `auto_suggest` 先配一级科目、再配明细：
  - 客户一级科目名：有一级科目行用该行名称（以「\」开头的旧导入名称不可信 ⇒ 不校验）；没有一级科目行时由同一一级码下全部明细推：每个明细取分隔符前一段（没有分隔符取全名），**只认能全等 / 同义对上标准一级科目的**，全部指向同一个标准一级科目才用。北京那份账明细叫「人工费用-工资」（第二级名）⇒ 对不上 ⇒ 不推、照常按 6601 认。
  - 按编码命中（完整码 → 前 4 位 → 一级码）后核对：客户一级科目名与标准一级科目名不兼容 ⇒ 撞号 ⇒ 明细跟随一级科目；一级科目本身按一级科目名找（全等 / 同义）；找不到不自动映射。
  - 编码认不出的明细跟随一级科目；一级科目只是**模糊**认出来的（`fuzzy_name`）明细不跟随；一级科目行存在但没配上 ⇒ 明细不按自己的名称猜。
  - 同义表先于名称模糊匹配（应付工资 → 应付职工薪酬，不走模糊到应付账款）；模糊匹配不跨流动 / 非流动（ABC餐饮 1302 其他流动资产曾配到 1519 其他非流动金融资产）。
  - 损益类旧编码对照、坏账准备二级（1231 系列）优先级不变。
- `auto_match` 跳过已有映射、`_get_unmapped_with_balance` 按剥「.0」后的编码比较。

## 2. 税审取数（`tax_workpaper_fetch.AccountBook.tops`）
- 名称在标准科目表：只取映射到该标准科目的客户科目；没有 ⇒ 空 + 原因「没有客户科目映射到标准科目「X」（码），请在底稿映射「客户科目 → 标准科目」补映射」。
- 不在标准科目表：只认客户一级科目（树根）名称全等 / 同义；不包含、不认明细。
- 规则执行器 `RuleResult.scope`（底稿映射页「规则指向但没取到」）用同一 `tops`，原 `loose` 参数删除。

## 3. 存量修复工具 `scripts/fix/rematch_account_mapping.py`
- `--mode rebuild`：客户科目表（编码, 名称）与有效余额表不一致才重建；自动映射按新规则逐条**原地**改 —— `account_mapping` 唯一索引 (project_id, original_account_code) 不排除已删行（PG 实测 `CREATE UNIQUE INDEX … (project_id, original_account_code)`），首版「删了再插」撞唯一约束，已改为同码原地更新 / 复活、新规则不再映射的停用、没有行的才插入。手工映射不动。
- `--mode collisions`（默认）：只改 `find_code_collisions` 列出的自动映射（标准科目码 = 本码 / 去分隔符完整码 / 前 4 位 / 一级码，且一级科目名不兼容）。
- 两种方式改完全量重算试算表（同 `POST /trial-balance/recalc`，含底稿过期标记收敛）；本年度已生成过报表的重新生成（同 `POST /reports/generate`）。
- `--apply` 必须给 `--backup`（`row_to_json` 原文：客户科目表、映射、试算表、报表）；`--restore` 按 id 还原客户科目表与映射并重算。

## 4. 真库执行（2026-11-03）
- 四川医药（`0e3ab724`）已于 11-03 11:59 UTC 被删除（回收站）；同一份账以「ABC餐饮有限公司_2025」（`90be32ec`，11:53 新建）重新导入 ⇒ 修复对象为 ABC餐饮，四川医药不动。
- ABC餐饮：客户科目表与有效余额表一致（新导入），不重建；两轮共改映射（见 tasks 验收摘要），留底 `backend/backups/rematch_account_mapping_abc_20261103_211043.json`、`…_214502.json`。
- 辽宁：撞号 6 条（1406.02 / 1407 / 4001.05 / 4101.01、第二轮 4001.01 / 4001.03），留底 `…_liaoning_20261103_210427.json`、`…_214502.json`。
- 北京GGGGGG激光科技：发现撞号 2 条（4001010000 实收资本 → 4001 生产成本、4101010000 盈余公积 → 4101 制造费用），**未授权、未改**。

## 5. 实施中的调整
- 首版从明细名推一级科目名只取分隔符前一段：北京 10 位编码、无一级科目行的账套里第二级名「人工费用」被当成一级科目 ⇒ 13 个费用明细判撞号、配不上（预览发现，未落库）⇒ 改为「推出的名称必须对上标准一级科目且一致」。
- 首版撞号清单只看本码 / 一级码 ⇒ 漏辽宁 4001.01 → 400101 ⇒ 加去分隔符完整码与前 4 位。
- 首版明细一律跟随一级科目 ⇒ ABC 1302 的模糊错配被放大到 3 个明细 ⇒ 模糊父级不跟随 + 模糊不跨流动 / 非流动。
- `test_legacy_pl_crosswalk::test_auto_suggest_new_standard_chart_unchanged` 原断言 `5001 生产成本 → 5001`（标准表 5001 = 主营业务收入，即同码不同义）改为 → 4001 生产成本、5403 机械作业 → 4403。

## 6. 范围外（只登记）
- （第二批已处理）北京撞号 2 条、辽宁有余额未映射 5 个、ABC 待摊费用 / 其他流动资产，见 §8。
- ABC餐饮账套本身末级余额合计 −19,469,933.96（借贷不平，导入数据问题），资产负债表不平与映射无关。
- `test_mapping_service.py` 两例（`test_prefix_match` / `test_suggestions_have_required_fields`）断言 `match_method == "prefix"`，HEAD 上 1001 先命中 `exact_code` 同样红（干净副本放 HEAD 版 `mapping_service.py` 复现）。
- （第二批已修）`test_dataset_import_platform::test_import_queue_memory_lock_does_not_block_db_lock` 红：本机 Redis `import_lock:active_set` 残留 3 个项目，见 §8.3。
- `test_lazy_import_resolvability` 两例红：`ai_content.py`（`app.services.consol_lock_service`）、`consol_note_template_push_service.py`（`app.models.disclosure_note_models`）、`note_section_pairing.py`（`resolve_alias_counterparts`）三处函数内导入目标不存在；三个文件本 spec 未改、HEAD 原文即含这些导入。

## 7. 验证
- 回归（税审底稿 / 公式引擎 / 鉴证报告 / 映射 / 旧制度对照 / 报表行映射 / 数据集导入 / 可见范围 / 鉴权基线 / 函数全局名棘轮 / 延迟导入）：295 passed，5 failed 均为 §6 登记的预存问题。
- 行数门：`mapping_service.py` 1091 行超门（1035 × 1.05 = 1086）⇒ 编码段 + 一级科目段搬到 `mapping_level1_match.code_and_level1_step`，降到 1057 行；搬移前后三个项目预览结果一致（ABC 0 变化、辽宁 0 撞号、北京 2 撞号）。
- 隔离副本磁盘变异（每条改一处、跑 5 个测试文件、逐字节恢复 + sha256 校验）：第一轮 18 条 12 打红；补 4 例后第二轮 24 条 23 打红（存活 1：明细推出的一级科目不要求一致）；补 1 例后第三轮 24 条全部打红、无害对照存活。
- 浏览器实测（ABC餐饮，写请求全部拦截）：「科目 → 底稿」1501 固定资产 → 1601 并进 3-03-01、3101 实收资本 → 3001 并进 3-07-13（两家股东 2100 万 / 900 万取到）、短期借款表提示「没有客户科目映射到标准科目「短期借款」（2001）」；「客户科目 → 标准科目」94.1% 已映射、有余额未映射 6 个（1301 及 5 个明细）；控制台 0 错误。

## 8. 第二批（用户 2026-11-03「按照你的建议来决定 4 件事」）

### 8.1 映射数据（工具 `rematch_account_mapping.py` 加 `--mode unmapped` / `--set`）
| 项目 | 改动 | 资产负债表 |
|---|---|---|
| 北京GGGGGG激光科技 | 撞号 2 条：4001010000 实收资本 → 3001、4101010000 盈余公积 → 3101 | 所有者权益 64,698,747.49 → 115,035,058.07（实收资本 5,000 万原被当生产成本） |
| 辽宁 | 未映射 7 条自动匹配：1651.02 → 1641 使用权资产、2651.01 / .99 → 2601 租赁负债、4104.03 / .04 / .05 → 3201 利润分配、1452 低值易耗品 → 1411 | 资产 − 负债和所有者权益：123,363,926.13 → −3,016,608.00 |
| ABC餐饮 | 手工 16 条：待摊费用及 10 个明细 → 1123 预付账款；待抵扣进项税额、其他流动资产及 3 个明细 → 2221 应交税费 | 预付款项 0 → 902,452.99；应交税费 9,348,855.60 → 6,819,527.77；差额 −22,913,055.20 → −19,481,274.38（≈ 账套本身末级余额合计 −19,469,933.96） |

ABC 的判断依据：本平台国企单体资产负债表「其他流动资产」（BS-026）没有取数公式，映射到任何科目都不进报表；「预付款项」取 1123、「应交税费」取 2221。待摊费用按新准则衔接通常转入预付账款 / 其他流动资产，取能进报表的预付账款；待抵扣 / 待认证 / 留抵进项税额、预缴所得税属应交税费的借方明细，归 2221（列报上应重分类到其他流动资产，本平台报表无该公式，在应交税费内抵减）。手工映射（`manual`）不会被自动匹配 / 重做改动。

留底：`backend/backups/rematch_account_mapping_{abc_manual,liaoning_unmapped,beijing}_20261103_224521.json`。

### 8.2 发现但未改：试算表把「贷方科目的借方余额」存成正数
`trial_balance_service.recalc_unadjusted` 对资产负债权益类贷方科目 `closing = abs(closing)`（同文件损益类兜底一处同样写法）。贷方科目实为借方余额时（累计亏损、应交税费留抵、负债的借方余额）方向反了：
- 北京 3201 利润分配：余额表 4104030000 期末借方 63,884,011.49（累计亏损），试算表存 +63,884,011.49 ⇒ 报表「未分配利润」列成正 6,388 万，所有者权益多 1.28 亿；北京资产负债表差额 −137,567,519.04 主要来自这里（另约 976 万是本年亏损未结转）。北京余额表末级合计为 0，账本身是平的。
- 北京 2221 应交税费 56,820.50、辽宁 2602 未确认融资费用 621,327.29、辽宁 320101 提取法定盈余公积 1,508,304.00 同类。
- 5 个有账项目共 4 个科目。修法：贷方科目 `closing = −signed`（保留符号）；影响全平台试算表 / 报表 / 底稿取数 / 附注推送，需另立 spec 并全量回归，未擅改。

### 8.3 导入锁（`import_queue_service.py` + 测试基座）
- 根因：全部导入流程都调同步 `release_lock`，它只清内存；`release_lock_async`（清 Redis）全仓无调用方。锁键 30 分钟才过期（期间同一项目重新导入报「另一 worker 持有锁」），活跃集合没有过期时间、成员永久累积，满 3 个后所有导入报「系统繁忙」。
- 本机残留 3 个都不是真实项目（`projects` 表查无、无进行中批次）：测试里 `acquire_lock` 直连 `.env` 的真 Redis（`ImportQueueService._get_redis` 直接调 `app.core.redis.get_redis`，测试基座虽导入 fakeredis 却未用）。
- 修：`release_lock` 在事件循环里另起任务（持有引用）先移出集合、再删锁键；`_redis_check_global_concurrency(db, current_project_id)` 满额时清残留（本项目自己的旧成员 / 无锁键且无进行中批次），返回减去后的数；测试基座 autouse 让导入队列用每例独享的 `FakeRedis(server=FakeServer())`。
- 用例（新文件 `tests/test_import_queue_active_set.py`，原 `test_dataset_import_platform.py` HEAD 已 782 行、放不下）：残留成员清掉后放行、有锁键 / 有进行中批次的保留；成员都在用时仍「系统繁忙」；本项目旧成员不挡重新导入；`release_lock` 清掉锁键与集合成员。
- 行数门：`import_queue_service.py` HEAD 已 932 行且未登记（任何改动都被拒），本批 +39 行，按惯例登记白名单 971 行并写明拆分方向。
- 本机残留已用同一判断清掉（集合 3 → 0）。

- 隔离副本磁盘变异 9 条全部打红（满额不清残留 / 本项目旧成员不算残留 / 有锁键也清 / 有进行中批次也清 / 清完不减计数 / 释放不清 Redis / 只删锁键 / 取锁不传 db / 测试不隔离真 Redis），无害对照存活。「测试不隔离真 Redis」那条变异确实往真 Redis 写了 3 个测试项目（1 个带锁键），已按「非真实项目且无进行中批次」清掉，集合与锁键均为空。

### 8.4 回归
- 140 passed（导入锁新用例、`test_dataset_import_platform` 含原来红的 `test_import_queue_memory_lock_does_not_block_db_lock`、`test_import_distributed_lock`、`ledger_import/test_global_concurrency_limit`、`integration/test_activate_rollback_mutex`、映射撞号、旧制度对照、税审取数）；跑完真 Redis 导入集合与锁键仍为空（测试不再写真 Redis）。
- `test_import_engine.py` 18 例、`test_data_lifecycle_router.py` 2 例红：`_create_test_project` 的 `BasicInfoSchema` 缺 `company_code` / `short_name`（2026-10-29 `254fec365` 改为必填），在建项目这步就失败，与本 spec 无关（两文件本 spec 未改）。
