# Implementation Plan: 受管行删物理行的多区位移联动

## Overview

实现语言 **Python**（本 spec 全部落点都在既有 Python 模块内；前端零改动）。
顺序即依赖：阶段 0 先钉死两条未实证假设（design「§ 风险与未验证项」R1/R2），阶段 1 建声明生产者与位移载体，
阶段 2 逐条补位移联动，阶段 3 接线与门控，阶段 4 换守卫与验收。

🔴 每个实现任务开始前**先重新现读**相关函数（有并发会话在改 `excel_materialize.py`；
归档 README 教训 4 记载它曾在别的会话里被从 94 行 diff 改到 237 行）。
🔴 计数类判据一律**现算**，禁写死；判据禁写死行号，锚点用常量名 / 端点字面量 / 形态特征。
🔴 探针放 `backend/scripts/analyze/_bdelp_*.py` + 输出 `_bdelp_*.txt`，交付前清理（Task 24.1）。
🔴 含正则的核验一律写探针文件，禁 `python -c`；文件校验一律 Python 读 bytes + decode。

---

## Tasks

## 阶段 0：钉死假设

- [x] 1. 阶段 0 前置实证（不改生产代码）
  - [x] 1.1 复算 design「§ 现算基线」的 12 个基线量
    - 复算 B1（`plan_workbook_row_change_for_delete` 全仓命中）与 B2~B5（AST 口径的生产消费方数）
    - 复算 B8：🔴 **必须扫 `backend/storage/**`，不是 `backend/wp_templates/`**
      （同一扫描器在模板库上得 0 是扫错 population，不是结构性零）
    - 探针须显式统计并打印 `解析失败` 计数（本轮实测 28 份 `BadZipFile`，不统计会被当成「没有 `_GT_SYNC`」）
    - 配变异证明：合成双区 zip 上同一扫描器须命中 2
    - 判据：12 个量全部有现算值；与 design「§ 现算基线」不一致处**更正 design**（append 勘误节，不改历史结论）
    - _Validates: Design「§ 现算基线」_


  - [x] 1.2 实证 R1：受管 sheet 裸引用在删行后是否真的不平移
    - 探针构造受管 sheet 含裸 `SUM(B7:B25)` + 一处裸单格引用，跑 `shrink_sheet_rows(delete_at=20, count=1)`
    - 读回公式文本，判断行号是否变化（raw XML，禁 openpyxl 属性访问）
    - 🔴 若证伪（某处已在处理）⇒ Requirement 5 降级为「已有产物」并更正 design「§ 七条欠账逐条」A5 与「§ 风险与未验证项」R1
    - 同时勘误：`apply_workbook_row_change` docstring 表格声称「受管 sheet / delete / 裸引用：位移」
    - _Validates: Requirement 5（前提）, Design「§ 风险与未验证项」R1_


  - [x] 1.3 实证 R2：`unextend_total_formula` 是否需要删行对偶
    - 探针跑一次 `unmanaged_region_digest`（删行产物 vs 原产物），看 `managed_sheet_unmanaged_cells`
      是否因合计公式打红
    - 🔴 配变异证明：把合计行改成不带公式 ⇒ 该判据须仍绿（否则结论不可信）
    - 判据：能明确回答「删行侧需不需要 `unextend` 的对偶」，并写进 design「§ 风险与未验证项」R2
    - _Validates: Requirement 6.4, Design「§ 风险与未验证项」R2_


  - [x] 1.4 现算 R4：删行验收靶子是否还存在
    - 现算 D4 当前 `stale` 身份数（`_managed` 生产口径，禁自造裸差集）
    - 若为 0 ⇒ 验收改用合成 artifact + 显式构造 stale，并在 design「§ 风险与未验证项」R4 登记
    - _Validates: Design「§ 风险与未验证项」R4_

---

## 阶段 1：声明生产者与位移载体

- [x] 5. 新增位移载体 `RowDeletionShift`
  - [x] 5.1 实现载体本体（`excel_workbook_row_change.py`）
    - `deleted_rows`（升序去重、位移前口径）/ `region_first_row` / `region_last_row`
    - `shift(row) -> int | None`（被删行返回 `None`）/ `unshift(row) -> int` / `count` /
      `inserted_rows` 恒 `frozenset()`
    - 🔴 `frozen=True` + 走 `assert_no_mutation_surface`（与 `WorkbookRowChangePlan` 同一条纪律）
    - _Requirements: 1.12, 1.13, 6.1_

  - [x]* 5.2 属性测试：载体三条不变量
    - **Property 2：删行位移载体的三条不变量**
    - **Validates: Requirements 1.12, 1.13, 6.6**

- [x] 6. 新增删行声明门面 `plan_workbook_row_change_for_delete`
  - [x] 6.1 抽出私有 `_scan_from_entries`（entries → 内存 zip → `_parse_workbook_xml` → `scan_reference_carriers`）
    - 🔴 insert 门面签名**逐字不变** —— B2 的 2 个生产调用方与 1 个测试调用方零改动
    - 判据：AST 断言两个门面都调这一个私有函数，模块内不存在第二份扫描逻辑
    - _Requirements: 1.4_

  - [x] 6.2 实现门面本体 + `RowDeletionChangeSet`
    - 返回 `RowDeletionChangeSet | None`；`None` = 零传播路径
    - 只暴露 `propagations`（鸭子兼容 verify），**不**声明 `at`/`count` 标量
    - 条目由 `build_propagation_entry(site, remap=shift.shift)` 构造（与 apply 同一改写入口）
    - _Requirements: 1.1, 1.5, 1.6_

  - [x]* 6.3 属性测试：零传播路径恒等
    - **Property 1：零传播路径恒等**
    - **Validates: Requirements 1.2, 1.3**

  - [x]* 6.4 属性测试：声明与载体同源
    - **Property 3：声明与载体同源**
    - **Validates: Requirements 1.1, 1.6**

- [x] 7. 门面内的 fail-closed：悬空引用与留痕键
  - [x] 7.1 逐极大连续段调 `find_dangling_sites`；坏点非空且未显式放行 ⇒ 抛 `DanglingReferenceError`
    - 🔴 **不得**传 `allow_ref_errors=True`（上游 §更正 4 明文）
    - 🔴 不整体调 `build_delete_plan` —— 那会顺带构造一个不成立的 `at`/`count` 计划
    - _Requirements: 1.7, 1.8_

  - [x] 7.2 调 `resolve_deleted_row_keys` 取留痕键并放进声明
    - 🔴 这使 `resolve_deleted_row_keys` 有第二个生产消费方（B4 的「0 生产入口」由此闭合）
    - _Requirements: 1.9, 1.10_

  - [x]* 7.3 属性测试：悬空引用一律计划期 fail-closed
    - **Property 5：悬空引用一律在计划期 fail-closed**
    - **Validates: Requirements 1.7, 1.8**

  - [x]* 7.4 属性测试：留痕键与被删行一一对应
    - **Property 6：留痕键与被删行一一对应**
    - **Validates: Requirements 1.9, 1.10**

- [x] 8. Checkpoint —— 确保所有测试通过；有疑问先问用户
  - 定向跑 `excel_workbook_row_change` 引用面（按符号反查，禁整目录）

---

## 阶段 2：七条位移联动逐条补齐

- [x] 9. A1 兄弟 Excel Table `ref` 收缩
  - [x] 9.1 新增 `_shrink_sibling_table_refs`（`excel_materialize.py`）并由 `_shrink_managed_table_ref` 末尾调用
    - 与 `_shift_sibling_table_refs` **共用同一个 `ref=` 匹配常量**，只换 remap
    - 🔴 兄弟表**首尾都要动**（与本表只缩末行相反）；用统一 `remap(row)`，不写两个 if
    - 走 `_sheet_table_parts`（worksheet rels）取清单，**不**扫 `xl/tables/*` 猜归属
    - 兄弟表完全在删除点之上 ⇒ 零改动且**不抛**（与插行侧同纪律）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

  - [x]* 9.2 属性测试：兄弟 `ref` 收缩
    - **Property 7：兄弟 Table `ref` 收缩**
    - **Validates: Requirements 2.1, 2.2, 2.4**

  - [x]* 9.3 属性测试：收缩后零身份 mint
    - **Property 8：收缩后零身份 mint**
    - **Validates: Requirement 2.5**

  - [x]* 9.4 覆盖面普查 + 变异反证
    - 参数化清单由 Task 1.1 的 B8 现算生成；断言「参数条数 == 现算组数」（**禁写死 18**）
    - 变异反证：进程内短路 `_shrink_sibling_table_refs` ⇒ Property 8 的断言打红
    - _Requirements: 2.7, 2.8_

- [x] 10. A2 `_GT_SYNC` runtime binding 的删行重冻结
  - [x] 10.1 把 `_refresh_gt_sync_runtime_binding` 的 `plan.row_shift` 依赖改成位移载体协议
    - insert 传 `RowShiftPlan`、delete 传 `RowDeletionShift`；insert 分支行为**逐字不变**
    - `_grow_range_string` 按载体方向分流出收缩语义，**不抄第二份**
    - 7 个被重写键逐个给删行语义（design「§ 七条欠账逐条」A2 的对照表）
    - 🔴 `same_sheet_tids` 推导**复用现有那一段**（worksheet rels → 兄弟 `displayName` → 平行清册）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 10.2 属性测试：重冻结三条不变量
    - **Property 9：runtime binding 重冻结的三条不变量**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5**

  - [x]* 10.3 端到端 + 变异反证：连跑两趟
    - 第一趟删行、第二趟物化同一 entry ⇒ 计划期 footer 门通过
    - 变异反证：去掉 per-template footer 键重冻结 ⇒ 第二趟必抛 `FooterAnchorDriftError`
    - _Requirements: 3.6, 3.7_

- [x] 11. A3 + A4 definedName 与跨 sheet 公式：接上声明即生效
  - [x] 11.1 让删行分支把声明喂给 `_apply_workbook_propagation`
    - 🔴 **不改** `_apply_workbook_propagation` 的替换算法（含 `&apos;` 四候选形态），只喂声明
    - _Requirements: 4.1, 4.2_

  - [x]* 11.2 属性测试：按声明位移的三类形态
    - **Property 10：按声明位移的三类形态**
    - **Validates: Requirements 4.1, 4.5, 4.6, 4.7**

  - [x]* 11.3 属性测试：传播对账 fail-closed
    - **Property 11：传播对账 fail-closed**
    - **Validates: Requirements 4.3, 4.4**

  - [x]* 11.4 变异反证：声明里移除 `xl/workbook.xml` 条目 ⇒ verify 判 `adapter_unmanaged_region_drift`
    - _Requirements: 4.8_

- [x] 12. A5 受管 sheet 自身裸引用平移（含合计区间收缩）
  - [x] 12.1 apply 阶段 0 在 `shrink_sheet_rows` 之后追加裸引用平移
    - 走 `excel_row_shift.remap_a1_rows`（既有唯一入口），**不新写**行号改写器
    - 🔴 **不复用** `shift_sheet_rows`（上游明文：造新行+下移的语义会互相干扰边界）
    - 合计区间按契约 `carries_total_formula` 收缩；未声明则不改写该 footer 任何公式
    - 🔴 若 Task 1.2 证伪本项 ⇒ 本任务改为「登记已有产物 + 补判据」，不写新代码
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x]* 12.2 属性测试：受管 sheet 裸引用平移
    - **Property 12：受管 sheet 裸引用平移**
    - **Validates: Requirement 5.1**

  - [x]* 12.3 属性测试：合计区间收缩受契约门控
    - **Property 13：合计区间收缩受契约声明门控**
    - **Validates: Requirements 5.4, 5.5**

  - [x]* 12.4 属性测试 + 变异反证：合计区间不覆盖 footer 行
    - **Property 14：合计区间不得覆盖 footer 自身**
    - 变异反证：跳过平移 ⇒ 本属性打红
    - **Validates: Requirements 5.6, 5.7**

- [x] 13. A6 verify 侧归一化载体接线
  - [x] 13.1 让 `verify_unmanaged_regions` 的归一化入参接受 `RowDeletionShift`
    - 鸭子兼容即够（`unshift` / `inserted_rows`）；只给 **after** 侧
    - 按 Task 1.3 的结论决定是否需要 `unextend_total_formula` 的删行对偶
    - _Requirements: 6.1, 6.3, 6.4_

  - [x]* 13.2 属性测试：归一化等价且不被弱化
    - **Property 15：验证归一化等价且不被弱化**
    - **Validates: Requirements 6.2, 6.4, 6.7**

  - [x]* 13.3 变异反证 + 空集显式断言
    - 不传载体（`row_shift=None`）⇒ Property 15 的等价断言打红
    - 在 verify 入参处显式断言 `inserted_rows == frozenset()`（复用 Property 2，不重复实现）
    - _Requirements: 6.5, 6.6_

- [x] 14. A7 apply 后 footer 两门的删行分支
  - [x] 14.1 `assert_shifted_footer_gates` 的门改为「两个位移载体都空才 return」
    - 预期行号 = 冻结值 − 声明的被删行数；合计覆盖用删行后的受管末行求值
    - 🔴 调用点仍在 `os.replace` **之前** ⇒ 门不过即零产物
    - _Requirements: 7.1, 7.2, 7.4_

  - [x]* 14.2 属性测试：footer 两门的算术与零产物
    - **Property 16：footer 两门的算术与零产物**
    - **Validates: Requirements 7.2, 7.3, 7.4**

  - [x]* 14.3 防空转断言
    - 用返回值（具体行号，非 `None`）断言该门真的执行过，**不用**「没有抛错」
    - _Requirements: 7.5_

- [x] 15. Checkpoint —— 确保所有测试通过；有疑问先问用户
  - 定向跑 `excel_materialize` / `excel_extract` 引用面；记录 passed 数与零回归结论

---

## 阶段 3：启用受控（契约门控 + 分流 + 零回归冻结）

- [x] 16. 契约字段 `row_convergence`
  - [x] 16.1 `contracts.py` 加 `RowConvergenceMode` 枚举与 `TableSpec.row_convergence`（默认 `clear`）
    - `_parse_table` 用 `raw.get(...)` 取值；现读已确认该函数**不拒绝未知键** ⇒ 纯增量
    - 加一条 CS 规则：声明 `delete` 必须同时有 `row_identity` 与 `delete_policy`
      （编号取现算的下一个可用值，**禁写死**）
    - _Requirements: 8.1, 8.2, 8.3_

  - [x]* 16.2 属性测试：契约门控的默认与分流
    - **Property 17：契约门控的默认与分流**
    - **Validates: Requirements 8.1, 8.2, 8.4**

  - [x]* 16.3 属性测试：开启删行必须同时具备行身份与删除策略
    - **Property 18：开启删行必须同时具备行身份与删除策略**
    - **Validates: Requirement 8.3**

  - [x]* 16.4 覆盖面普查：全部既有契约解析后均为 `clear`
    - 分母现算（**禁写死**），并断言「遍历文件数 == 现算分母」
    - _Requirements: 8.5_

- [x] 17. 6.8b 分流改造（clear / delete / 降级）
  - [x] 17.1 按 design「§ 删与插共存」4.2 的判定树重写 6.8b 的分流
    - 顺序：容量归零 → 契约未开启 → orphan 非空（共存）→ 才走 `stale_deleted`
    - 共存 ⇒ 走清空 + 写入可观测的降级原因（进 `MaterializePlan.as_dict()`）
    - 🔴 **不**在删行前口径重算 `insert_at`
    - 🔴 apply 期原 `[convergence_delete_with_insert_unsupported]` 拦截**保留**为纵深防御
    - 产删行计划时同时挂上 `row_deletion` 与 `deletion_change` 两个字段
    - _Requirements: 1.11, 8.4, 9.1, 9.2, 9.3, 9.4_

  - [x]* 17.2 属性测试：删行计划必带两份声明
    - **Property 4：删行计划必带两份声明**
    - **Validates: Requirement 1.11**

  - [x]* 17.3 属性测试：共存降级为清空且原因可读
    - **Property 19：共存降级为清空且原因可读**
    - **Validates: Requirements 9.1, 9.2, 9.5, 9.6**

- [x] 18. `stale_cleared` 路径逐字节零回归的三层判据
  - [x] 18.1 冻结字节基线
    - 用同一份 substrate + 同一份 projection，在本 spec 落地**前**跑一次 `apply_plan_zip_with_report`，
      把产物 sha256 冻结进 `backend/tests/workpaper_sync/data/`
    - 🔴 必须在改 6.8b **之前**取基线（改完就再也取不到「本 spec 之前」）
    - _Requirements: 8.6_

  - [x] 18.2 路径层 AST 断言：删行计划的产出被 `row_convergence` 门控
    - 取赋值语句的祖先条件链，不用字符串 grep（否则命中注释/文档串）
    - _Requirements: 8.7_

  - [x]* 18.3 变异反证：门控改恒真 ⇒ 18.1 的字节基线打红
    - 🔴 只有它打红才证明第 18.1 层真的在观测字节；不打红说明基线挂错了对象
    - _Requirements: 8.8_

- [x] 19. Property 28 冻结基线看门狗
  - [x] 19.1 加文件级 sha256 断言
    - 断言 `workbook_row_change_zero_regression_baseline.json` 的 sha256 == 交付时现算值
    - 失败文案须写明「若是**有意**重生成：改这里的期望值并在提交说明里逐处论证合法性」
    - _Requirements: 10.3, 10.4_

  - [x] 19.2 冻结被观测对象
    - 对 `_rewrite_formula_refs` / `translate_formula_rows` / `_scenario_kwargs` / `SCENARIOS`
      四个符号的源码文本取 sha256 并断言与交付值相等
    - 断言 `SCENARIOS` 仍是三元组（不得加删行情景）
    - AST 断言删行侧的反向映射通过**实参**传入（`remap` 不是函数内部常量）
    - 🔴 **执行纪律（无自动判据）**：若实施中发现必须改 `_rewrite_formula_refs`，**停下**，
      按范围变更处理（先按该守卫 docstring 记载的七条机械核验逐条取证，再显式重新冻结，
      并在提交说明里论证每一处 diff 的合法性）。**不得**在实施中顺手 `--apply` 重生成。
    - _Requirements: 10.1, 10.2, 10.5, 10.6_

- [x] 20. Checkpoint —— 确保所有测试通过；有疑问先问用户

---

## 阶段 4：G2 症状复现、守卫替换与验收

- [x] 21. G2 症状链的沿链复现测试
  - [x] 21.1 合成双区固件 + 四环逐环断言
    - 固件：一张 sheet、两个 GT_* Table（main / other，各带 uuid 列）、`delete_policy=tombstone` 契约
    - 四环：兄弟 `ref` 值 → 区间尾行 UUID 是否为空 → `scan.minted_by_row` → `extra`（生产口径）
    - 🔴 `extra` 一律用生产的受管字段过滤口径复算，**禁自造裸差集**（上游踩过三次）
    - 🔴 用**进程内** `monkeypatch` 制造「修复前」态，不改磁盘生产文件
      （归档 README 教训 6：变异 harness 自身会假绿）
    - 判据：修复前四环**全红**、修复后四环全绿
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 22. 上游反向守卫替换为正向判据
  - [x] 22.1 改 `test_managed_row_convergence.py`
    - 移除 `"stale_deleted = tuple(sorted(stale_rows))" not in src` 这条反向断言
    - **同一次提交**加三条正向断言：① 删行计划必带两份声明 ② 必落在契约门控内
      ③ apply 依次经过 A1~A5 五个动作（用**实测计数**断言，不用「没有抛错」）
    - 🔴 保留既有的「清空仍是默认分支」断言 —— 实施期**先现读确认**它在新分流下仍成立
    - 🔴 **不加**「`shrink_sheet_rows` 必须有生产消费方」这类守卫：现算它已有 2 个生产消费方 ⇒ 恒真空转；
      改为现算消费方数并断言 > 0，在文案里登记「因此不加原始形态的死代码守卫」
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 23. 全引用面回归 + 真实数据验收
  - [x] 23.1 定向回归
    - 按符号反查跑：`excel_workbook_row_change` / `excel_materialize` / `excel_extract` /
      `contracts` / `test_managed_row_convergence` / `test_workbook_row_change_zero_regression` /
      `test_sibling_table_ref_row_shift` / `test_multi_sheet_workbook_change_merge` 八个引用面
    - 🔴 见红先 `git stash` 回滚本轮改动复跑，确认是本轮引入还是预存失败（不把别人的红算到自己头上）
    - _Requirements: 6.7, 8.6_

  - [x] 23.2 真实链路验收（按 Task 1.4 的结论选靶子）
    - 给一张表开 `row_convergence=delete`，构造一个真的 stale 行，点「在线编辑」
    - 四条判据：① materialize 200 ② 被删行真的没了（行数 −N）③ 兄弟区身份全在、零 mint
      ④ 下一趟物化不抛 `FooterAnchorDriftError`
    - 🔴 **实测后清理数据复原**；🔴 若环境不可达，如实标 `[ ]*` 并写「代码已改但未实测」
    - ✅ **已验收（`test_row_deletion_realchain_acceptance.py`，6 passed）**：靶子按 Task 1.4
      结论改用权威模板现场 instrument 的 D4-1 双区（live 靶子已消失，见 design E.5）。
      四条判据全绿，走的是**完整** `materialize_projection`（含落盘 / identity 保留门 /
      footer 两门 / 未管理区域比对），不是只跑 `plan` + `apply`。产物落在 pytest tmp 目录
      ⇒ 无需清理数据。
    - 🔴 **未覆盖**：HTTP「点在线编辑」那一跳（需 `start-dev.bat` 起 9980 + 3030 + OnlyOffice）。
      判据④「下一趟物化不抛 `FooterAnchorDriftError`」覆盖了那一跳最常见的故障形态
      （第一次删成功、第二次点开 500），但离线四条全绿**不等于**端到端已验收 ——
      该范围声明由 `test_http_hop_is_not_covered_here` 承载为显式判据（见 design E.9）。
    - _Requirements: 3.6, 7.1_

- [x] 24. 收尾

  - [x] 24.1 清理探针 + 更正 design + 登记 INDEX
    - 删除全部 `backend/scripts/analyze/_bdelp_*.py` 与 `_bdelp_*.txt`
    - 把 Task 1.1~1.4 的四条实证结论 append 进 design「§ 风险与未验证项」（**不改历史结论，只追加勘误节**）
    - 更新 `.kiro/specs/INDEX.md` 的进度（🔴 纯 CRLF：`read_bytes().decode('utf-8')` + `write_bytes()`；
    表格第三格内禁裸 pipe；校验「每行恰 4 个未转义 pipe」）
    - _Validates: Design「§ 风险与未验证项」, 「§ 现算基线」_

- [x] 25. Final checkpoint —— 确保所有测试通过；有疑问先问用户

---

## Notes

- 标 `*` 的子任务是测试类，可为更快的 MVP 跳过；但本平台默认**全部做完**（用户明确要求
  `run-all-tasks` 时 `*` 也要做，除非显式说跳过）。
- 属性测试一律 `hypothesis` + `max_examples=5`（**禁默认 100**），docstring 首行写
  `Feature: workpaper-sync-row-deletion-multi-region-propagation, Property {N}: {标题}`。
- Windows：用 `python` 非 `python3`；多命令用 `;` 不用 `&&`；固定目录用 `cwd` 不用 `cd`；
  venv 在仓库根 `.venv`（backend cwd 用 `..\.venv\Scripts\python.exe`）。
- 写中文禁 PowerShell `-replace` / `Set-Content`（乱码），用文件写入工具或 `python read_text/write_text`。
- `fsWrite` ≥100 行会截断 ⇒ 分批小块写。
- **明确不碰**：`store_mirror.py` · `adopt_substrate_response.py` · `GtWpRenderer.vue`（A 线范围）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["5.1", "18.1"] },
    { "id": 2, "tasks": ["5.2", "6.1"] },
    { "id": 3, "tasks": ["6.2", "16.1"] },
    { "id": 4, "tasks": ["6.3", "6.4", "7.1", "16.2", "16.3", "16.4"] },
    { "id": 5, "tasks": ["7.2", "7.3", "7.4", "9.1", "10.1"] },
    { "id": 6, "tasks": ["9.2", "9.3", "9.4", "10.2", "10.3", "12.1"] },
    { "id": 7, "tasks": ["12.2", "12.3", "12.4", "13.1", "17.1"] },
    { "id": 8, "tasks": ["11.1", "13.2", "13.3", "17.2", "17.3", "18.2"] },
    { "id": 9, "tasks": ["11.2", "11.3", "11.4", "14.1", "18.3", "19.1", "19.2"] },
    { "id": 10, "tasks": ["14.2", "14.3", "21.1", "22.1"] },
    { "id": 11, "tasks": ["23.1", "23.2"] },
    { "id": 12, "tasks": ["24.1"] }
  ]
}
```
