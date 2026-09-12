# Requirements Document

## Introduction

明细表可以从四表库（`tb_balance` / `tb_aux_balance` / `tb_ledger` / `tb_aux_balance` 辅助维度）一键取数，但**前端入口只在少数循环补齐**，其余底稿的明细表要么只能手工录几十上百行，要么只有"空表自动 seed"、用户改过数据后想重取无入口。本 spec 要做两件事：

1. **补齐入口**：逐一分析哪些明细表具备四表库取数能力但缺前端键，按统一范式补上。
2. **收敛实现**：现存 aux 取数有**两套**实现（F1/G7/K1/D1 的正确范式 vs D3/D5/D6/D7 的历史版本），后者违反四表库铁律。补入口的同时把历史版本迁到共享件，不允许再抄第 5 套。

### 基线：已有的 8 个后端 aux 取数端点（实扫 `wp_bound_entry_coverage.json`）

`POST /api/workpapers/{wp_id}/{d1|d3|d5|d6|d7|f1|g7|k1}/import-aux-balance`

前端调用方：`useD1DetailCustomer.ts` / `useD3ImportExport.ts` + `useD3Detail.ts` / `useD5Detail.ts` / `useD6Detail.ts` / `useD7Detail.ts` / `useF1Detail.ts` + `useF1DetailAutoSeed.ts` / `g7AuxExtraction.ts` + `G7TabDetail.vue` / `useK1DetailAutoSeed.ts`。

已有可见按钮「从余额表导入」的宿主（实扫 `.vue`）：`F1TabDetail` / `D7TabDetail` / `D6TabDetail` / `D3TabDetail` / `D5TabDetail` / `D2TabDetail` / `D1TabDetailCustomer` / `G7TabDetail`。**K1 只有 AutoSeed 无手动按钮** —— 空表自动 seed，用户动过数据后无法重取，属既有缺口样本。

### 🔴 红基线（必须先核实，不得照抄注释里的旧结论）

`_g7_long_term_equity_main_import_export.py:720` 与 `four_table/aux_aggregation.py` 的模块 docstring 都写着「禁止照 D3/D5/D6/D7 历史 aux 版本（其 SQL 引用不存在的列 `period_type`/`balance`，运行必 500）」。**本轮实扫结论：该理由已过期** —— `period_type` 在 `wp_render_strategies/**` 下**只出现在那句注释本身**；D3/D5/D7 的 SQL 实际用的是 `aux_name` / `opening_balance` / `closing_balance` / `account_code` / `is_deleted`，列都存在、不会 500。

历史版本的**真实**缺陷是（实读 `_d3_import_export.py:458` / `_d5_import_export.py:344` / `_d7_import_export.py:581` / `d_cycle_extraction/detail_aggregation.py:45`）：

- ① 裸写 `is_deleted = false`，**不走 `get_active_filter`** ⇒ 跨数据集版本双算（aux 冗余实测 2×）
- ② 直接 `GROUP BY aux_name`，**未先锁定单一 `aux_type`** ⇒ 同一科目挂多维度时金额双算
- ③ 科目码**硬编码**（`'2203%'` / `'1124%'` / `'2205%'` / `'1141%'`），不从报表映射解析
- ④ 把期初/期末全额塞进账龄首段（`agingPrior.within1 = prior_balance`）⇒ **伪造账龄分布**

⇒ 这四家全部 `get_active_filter` / `pick_aux_type` / `aux_aggregation` **零引用**（grep 实证）。

## Requirements

### Requirement 1: 缺口清单必须结构性推导

**User Story:** 作为审计师，我要知道到底还有哪些明细表能从四表库取数但没有按钮，而不是凭印象补几个。

#### Acceptance Criteria

1. WHEN 枚举候选底稿 THEN 必须从 `htmlRendererRegistry` + 后端 `RENDERER_DISPATCH` / render-config / `wp_code_overrides.json` 推导已挂载宿主集合，**禁止**用 grep 按钮文案或写死页面数量
2. WHEN 判定某明细表"具备四表库取数能力" THEN 判据必须是可核验的三元组：该 wp 的报表行能解析出科目码（`ReportLineAccountSpec` 或等效映射）+ 该科目在真库有对应四表数据 + 该明细表存在可承载的行结构（store item + 字段）
3. WHEN 产出清单 THEN 每条必须给 wp_code → 宿主组件 → store item_id → 现有入口（后端端点有/无、前端按钮有/无、AutoSeed 有/无）五列，并标注 gap 类型
4. WHEN 某底稿评估为"不适合取数" THEN 必须写明理由（如源模板无对应列、数据在序时账而非余额表），宁缺勿造，不得为凑数补入口
5. WHEN 清单落地 THEN 必须是可复核产物（JSON 或 md 表）并作为后续任务的唯一真源
6. WHEN 后续任务读取缺口清单 THEN 必须校验清单的 source digest 与当前 renderer registry / render-config 快照一致；不一致时必须阻塞实现，不得沿用过期清单

### Requirement 2: 红基线纠偏与历史实现迁移

**User Story:** 作为维护者，我不想每个新循环都从一句过期注释里继承错误理由，也不想平台同时跑两套四表库取数。

#### Acceptance Criteria

1. WHEN 核实历史端点 THEN 必须实测确认 D3/D5/D6/D7 端点当前是否真会 500（跑真库或读 SQL 列 vs schema），并把结论写进 spec evidence
2. WHEN 确认「`period_type`/`balance` 必 500」理由已过期 THEN 必须修正 `aux_aggregation.py` docstring 与 G7/K1/D1 注释里的该表述，改为真实缺陷（①②③④），不得留错误理由继续繁殖
3. WHEN 迁移历史端点 THEN D3/D5/D6/D7 必须改为复用 `four_table.aux_aggregation.aggregate_aux_by_name`（含 `get_active_filter` + `pick_aux_type`），删除各自的裸 SQL
4. WHEN 迁移后 THEN 科目码必须从报表映射解析（保留硬编码仅作显式兜底且必须注明来源），不得继续裸硬编码
5. WHEN 迁移触及账龄字段 THEN 不得把余额全额塞进账龄首段；无账龄来源时该字段留空并在返回 message 中提示需人工填账龄
6. WHEN 迁移完成 THEN `get_active_filter` / `pick_aux_type` 在这四个文件中必须可 grep 到真实调用（不是注释），且旧裸 SQL 零残留

### Requirement 3: 统一取数范式（禁止第 5 套）

**User Story:** 作为维护者，新增入口时我要有一条唯一正确的路，不用去猜照哪家抄。

#### Acceptance Criteria

1. WHEN 新增或改造任一 aux 取数端点 THEN 必须复用 `four_table.aux_aggregation`（或有充分理由时扩展它），**禁止**新写第 5 份归集 SQL
2. WHEN 归集逻辑不足以覆盖新场景 THEN 必须**扩展共享件**并同步既有消费者，不得在端点内分叉
3. WHEN 端点返回行 THEN 只写**录入列**，派生列（合计/审定/账龄合计等）留给前端 recalc，不得双写
4. WHEN 写入 store THEN 默认 merge 语义：已有行按业务键不覆盖，只追加新单位；覆盖必须由显式参数（如 `overwrite=true`）驱动并在 UI 上二次确认
5. WHEN 端点涉及 `tb_aux_balance` THEN 三条铁律必须全部落地：active dataset 过滤 / 单一 `aux_type` 锁定 / 科目前缀匹配（非精确等值）

### Requirement 4: 前端入口一致性

**User Story:** 作为审计师，每张明细表的取数按钮应该长得一样、行为一样。

#### Acceptance Criteria

1. WHEN 补前端入口 THEN 位置与文案沿用既有范式（明细表 toolbar 的「从余额表导入」，与 `+ 添加行` 同排），宿主已有「导入导出 ▾」下拉时并入该下拉，不得再造第三种摆法
2. WHEN 只读态（`isReadonly`）THEN 入口必须禁用
3. WHEN 取数进行中 THEN 必须有 loading 态，且禁止重复提交
4. WHEN 取数返回 0 行 THEN 必须给出可辨别原因的中文提示（未找到该科目辅助余额 / 该科目未按维度挂账 / 数据集未激活），不得只说"导入 0 行"
5. WHEN 底稿已有 AutoSeed（如 K1/F1）THEN 仍必须提供手动入口，二者语义区分：AutoSeed 仅空表触发、手动入口可在非空表上按 merge 语义追加
6. WHEN 入口触发成功 THEN 必须刷新受影响的级联（明细 → 审定表 → 附注读同一 store 的路径），不得只改本 Tab 内存态

### Requirement 5: 不伪造、不静默（fail-open 治理）

**User Story:** 作为质控复核人，我要能区分"真的没有这笔数"和"取数代码接错了被吞掉"。

#### Acceptance Criteria

1. WHEN 共享件 `aggregate_aux_by_name` 捕获异常 THEN 不得只 fail-open 返回空：必须以 ERROR 级别记录异常（含科目前缀 / project / year），使"接线错误"与"真无数据"在日志上可分辨
2. WHEN 端点返回 0 行 THEN 响应必须携带可区分的原因码（无候选 `aux_type` / 无匹配科目 / 无 active dataset / 异常），前端按原因码给不同提示
3. WHEN 某字段无四表来源 THEN 必须留空，不得用 0、上期值或把总额塞进首段账龄伪装成已取数
4. WHEN 取数结果写库 THEN 必须可追溯来源（至少能判断某行是取数产生还是手工录入）

### Requirement 6: 守卫、变异检验与真栈实测

**User Story:** 作为维护者，我要证据证明这些入口真的接上了，而不是又一批死代码。

#### Acceptance Criteria

1. WHEN 新增/改造端点 THEN 必须有守卫测试断言三条铁律真实生效（active filter 生效 / 单一 `aux_type` / 前缀匹配），且断言的是**行为**（SQL 结果或调用轨迹）而非"函数存在"
2. WHEN 编写守卫 THEN 必须做变异检验并四态判定（RED / GREEN=守卫缺陷 / ANCHOR-MISS / WRONG-TEST）；锚点至少含：去掉 active filter · 去掉 `aux_type` 锁定 · 把 merge 改成 overwrite
3. WHEN 补前端入口 THEN 必须有 vitest 断言按钮存在且 disabled 受 `isReadonly` 控制、点击真调对应端点（不是只 mock 通过）
4. WHEN 全部交付 THEN 必须至少一次浏览器真栈实测：某张此前无入口的明细表，点新按钮后行数从 0 变为账套真实户数，且金额与只读 SQL 快照逐字对齐
5. WHEN 迁移历史端点 THEN 必须实测迁移前后金额差异并解释（若原来双算，迁移后金额下降是**预期**修正，须在证据里写明倍数）
