# Tasks — 受管行双向收敛

> 顺序即依赖。P0（Task 1~9）解阻 D4 且零引擎改动；P1（Task 10~15）根治。
> 🔴 每个实现任务开始前**先重新确认相关文件状态**（有并发会话在改 workpaper_sync）。
> 🔴 判据以离线 harness 为主，HTTP 状态码为辅；每条"结构性零"结论必配变异证明。

## 阶段 0：前置确认（不写代码，先钉死假设）

- [ ] 1. 钉死 R1：adopt 后不会复现 `7→33` 写爆
  - 用 `d4_materialize_harness.py` 的 `rebased_world` 以**当前 gen165 字节**为 substrate，
    构造"store 认领 substrate 现有 33 行"的 projection，跑 materialize
  - 判据：materialize **不插行**（受管区已是 33 行）且产物 extract 后 `extra=0`
  - 🔴 若证伪（仍写爆或仍有 extra）：P0 不成立，直接转 P1（Task 10+），并在文档记录证伪
  - _Validates: Requirement 3.4, Design R1_

- [ ] 2. 确认弹窗差异摘要的数据来源（R4）
  - 现读 `compute_store_projection_response`：确认响应能否给出"未收缩的 baseline 行数"
  - 若不能：决定走 (a) 端点补只读字段 `baseline_row_count` 还是 (b) adopt dry-run
  - 判据：能明确回答"弹窗上那句『表单 N 行 ｜ 在线编辑侧 M 行』的 M 从哪来"
  - _Validates: Requirement 1.3, Design 4.2_

## 阶段 1：③ 反向收敛端点（P0 核心，零引擎改动）

- [ ] 3. 新增 `POST {USER_SYNC_PREFIX}/adopt-substrate` 端点（骨架 + 鉴权）
  - `wp_sync_router.py` 加路由，复用 `_guard(action="adopt_substrate")` 与 `_registration`
  - 🔴 **必在 `router_registry` 确认 wp_sync router 已注册**（本端点挂在既有 router 上，
    应自动生效，但需确认 `USER_SYNC_PREFIX` 前缀拼接正确）
  - 此步只返回 501/占位，不接业务，先让路由可达 + 鉴权链通
  - _Validates: Requirement 2.1, 2.2_

- [ ] 4. substrate 准入门（fail-closed，替代 coordinator 的 origin 门）
  - 校验 artifact 为 **published**（非 incoming / quarantined / 缺失）
  - 🔴 缺失/隔离 SHALL 拒绝并给可读原因，**不得降级成空 projection**（= 清空整表）
  - 变异反证：喂一个 incoming/缺失 artifact ⇒ 必须拒
  - _Validates: Requirement 2.5, Design 3.1_

- [ ] 5. 接 extract → merge → 落库主链
  - `adapter.extract(artifact, contract)` → projection
  - `base_by_item = {item: 现 store for item in provider.all_store_item_ids()}`
  - `provider.merge_projection_into_all_*_stores(projection=, base_by_item=)`
  - 逐 item upsert `checklist_responses`：service 只 flush，router 统一 commit
  - 🔴 不自造字段映射（第二真源禁令）—— 只调 provider 门面
  - _Validates: Requirement 2.3, 2.8_

- [ ] 6. 并发保护 + 可回滚 + 审计（替代 coordinator 的 fence）
  - `expected_revision` 与服务端不符 → 409
  - 覆盖前把被覆盖的 store 原值写入可追溯位置（复用既有 version/留痕，不新造表）
  - 审计日志记 entry / substrate sha256 / 影响 item 与行数
  - _Validates: Requirement 2.6, 2.7, 2.9_

- [ ] 7. 端到端解阻验证（离线 harness 主判据）
  - 对 D4 执行 adopt → 复跑 `store-projection` → 断言 `extra=0`（口径自证 common/missing）
  - 复跑 materialize → 断言 200 + descriptor
  - 🔴 D4 全 13 张受管 sheet 均能 extract（不得只验 D4-2）
  - _Validates: Requirement 3.1, 3.2, 3.3, 3.5_

## 阶段 2：① 刷新取数来源弹窗（P0 前端）

- [ ] 8. `GtWpRenderer.vue` 刷新取数改为来源选择弹窗
  - 「刷新取数」按钮改为先开弹窗；既有 `onRowNameAlignmentRefresh` 成为第一选项（实现不改）
  - 新增「以在线编辑（OO）侧为准，覆盖表单」→ 调 adopt-substrate（带二次确认 + 破坏性提示）
  - 「以表单为准，覆盖在线编辑」置灰并注明依赖 Requirement 4
  - 差异摘要按 Task 2 的结论取数
  - 🔴 全中文；未选择即关闭不执行任何取数
  - _Validates: Requirement 1.1, 1.2, 1.4, 1.5, 1.6_

- [ ] 9. Playwright 实测 P0 全链路
  - 在 D4 entry：点刷新取数 → 选「以 OO 侧为准」→ 确认 → adopt 成功 →
    再点在线编辑 → materialize 200 → 编辑器打开
  - 🔴 运行时实测（getDiagnostics/单测抓不到包装体解包、弹窗时序等运行时 bug）
  - _Validates: Requirement 3.2, Design 4.2_

## 阶段 3：② materialize 受管行收敛（P1 根治）

- [ ] 10. 公式格豁免（Requirement 5，先做——它是 5.2 清空方案的前提）
  - roundtrip 判据把"值来源为公式格"的字段纳入豁免，复用既有 protected 豁免机制
  - 🔴 仅限公式格；字面值格产生的 extra 不豁免
  - 变异反证：同一格公式→字面值 ⇒ 必须重新进 extra
  - _Validates: Requirement 5.1, 5.2, 5.3_

- [ ] 11. 收敛判据：与 overlay 对偶（store 声明的 table 才收缩）
  - 在 materialize 侧实现"store 声明了该 table → 收敛其受管区内 store 未列出的行；
    未声明 → 不碰"
  - 变异反证：store 不声明某 table ⇒ 断言该 table 行**未**被碰
  - _Validates: Requirement 4.1, 4.5_

- [ ] 12. 收敛动作：默认清空业务格（非删行）
  - 受管区内 store 未列出的行 → 清空**字面值**业务格，保留公式格
  - 🔴 不动行号、不触发悬空引用门
  - 判据：清空后该行不再进 extracted（依据实测"空业务格行不产字段"）
  - _Validates: Requirement 4.2, 4.3_

- [ ] 13. 删物理行路径（仅在需要压缩行数时，接 build_delete_plan）
  - 接 `resolve_deleted_row_keys` / `build_delete_plan`（现算签名见 requirements Req 4）
  - 🔴 先解决 R2：写探针钉死"某区间是否被公式引用"，**探针须带变异证明**
    （本轮的正则口径已被证失效，不可复用）
  - 悬空引用 → 沿用既有 fail-closed
  - _Validates: Requirement 4.4_

- [ ] 14. 全 entry 回归 + 变异反证
  - 按引用面定向跑（🔴 `backend/tests/workpaper_sync/` 整目录 >15 分钟超时，
    按符号反查测试文件）
  - 至少覆盖 D4 全 13 sheet + 一个 store-only 表（如 D4-10）+ 一个 baseline-only 表
  - _Validates: Requirement 3.5, 4.5, 5.3_

- [ ] 15. * 消费方接线的死代码守卫
  - 加 CI 守卫：`build_delete_plan` / `resolve_deleted_row_keys` 一旦被接进生产，
    必须有生产消费方（防"能力已建+测试全绿≠接线完整"再次发生）
  - 🔴 守卫源码断言"某函数有消费方"须用 AST 而非 grep（否则命中自己的注释/import）
  - _Validates: Requirement 4（防回归）_

## 遗留（不在本 spec 范围，另案）

- D4-10 占位骨架的 UX 取舍（收敛后无模板样式行）
- 谁整批替换 `D4-2-rows`（已排除 fallback 与 importFromLedger）
- `importFromLedger` 身份幂等性缺陷（`useD4RevenueDetail.ts:308`，改动属行为变更需产品裁决）

---

# 🔴 实施进度与任务更正（2026-09-28，以本节为准）

> requirements.md 末节「方向裁决与需求更正」是本节的依据。原任务表保留备查（append-only）。

## 已交付（阶段 0/1 + 一项独立重构）

- [x] 1. 钉死 R1：adopt 后不会复现 `7→33` 写爆
  - harness 实测：base=gen165(33行) + projection=自反读 ⇒ materialize **1 趟不插行**、
    产物字节与输入完全一致、`common=1311 / extra=0 / missing=0`
  - 变异组：projection 删掉 `d4r-mtl69x8j-1h71mrw`(18 字段) ⇒ **恰 18 个 extra**
    （首版变异组用 `dataclass.__dict__` 赋值无效，自查后改为删字段对照）
  - _Validates: Requirement 3.4（该 Req 后因 §更正 3 作废，但本实测结论仍有效）_

- [x] 2. 确认弹窗差异摘要 M 值来源
  - `compute_store_projection_response` 的 `row_count` 是 **overlay 之后**的行数
    （旧行已按 store 权威丢弃）⇒ 拿不到未收缩的 baseline 行数
  - 裁决：走 adopt 的 `dry_run`（只 extract 不落库，返回 `substrate_row_count` +
    `substrate_rows_by_table`），不给 store-projection 加旁路字段
  - _Validates: Requirement 1.3_

- [x] 3~6. `adopt-substrate` 端点全套（**降级为运维工具**，见 §更正 3）
  - 新建 `adopt_substrate_response.py`：published 准入 fail-closed（不得空覆盖）/
    `expected_revision` 并发锁 / extract→mirror→落库 / dry_run / 覆盖前留存原值 + 审计
  - `wp_sync_router.py` 挂 `POST …/adopt-substrate`；`adopt_substrate` 登记进 `_WRITE_ACTIONS`
    （未登记则 `_action_authorizer` 恒 403）
  - 3 处 task28 守卫跟随更新（handler 分母 `+4`→`+5`、slashed 路由 suffixes 表加一行）
  - 回归：test_task28 全量 **101 passed**
  - _Validates: Requirement 2.1~2.9_

- [x] **X（计划外但必需）. `store_mirror` 抽取 —— 消除第二真源**
  - 把 `OoToHtmlCoordinator` 的三个 `_mirror_*` 私有方法（472 行）搬成会话无关模块
    `store_mirror.py`；`oo_to_html.py` 改薄转发（3686→3233 行），行为逐字节等价
  - 抽取前现算确认依赖面：只用 `self._session` + `state.frozen.{adapter_id,project_id,wp_id}`
  - 🔴 修掉两个真缺陷：①缺模块级 `import json`（搬移后 `NameError` ⇒ adopt 首调 500）
    ②6 处逐 item commit 破坏原子性（adopt 中途失败留部分写入，实测 store 137→154）
    ⇒ 三函数加 `commit: bool = True`（默认不变），adopt 传 `False` 并统一 commit + 异常回滚；
    审计留痕移到 commit 前入同一事务
  - 2 个守卫跟随迁移扫描目标 + 各加「OO 侧转发未被误删」断言
  - 回归：直接面 35 passed / 扩展面 192 passed / commit 参数化后 167 passed

- [x] 10. 公式格豁免 —— **作废，无需实现**
  - 实证豁免本已存在且生效：73 个公式字段逐 key 验证全部被 `_managed()` 剔除
  - 原前提是裸差集口径误判造成的假命题（见 §更正 1/2）
  - 🔴 **不得**为它改动 roundtrip 判据（改了是弱化）

## 未实现（C 主线，D4 的 500 仍未解除）

- [ ] 11. 收敛判据：与 overlay 严格对偶
  - 落点：`excel_materialize.plan_managed_writes`（L1625），紧接 6.2 orphan 插行之后
  - 该处已有全部变量：`physical`（substrate row→identity）/ `row_of_identity` /
    `wanted`（store 声明的行）/ `orphan`（已有的插行方向）
  - 新增反向：`stale = [row for row, ident in physical.items() if ident not in wanted]`
  - 🔴 仅当 `table_key ∈ projection.row_keys` 才收敛；未声明一律不碰（少做而非多做）
  - 变异反证：store 不声明某 table ⇒ 断言该 table 行**未**被删
  - _Validates: Requirement 4.1, 4.5_

- [ ] 12+13（合并）. 收敛动作：删 stale 物理行
  - 接 `build_delete_plan` / `resolve_deleted_row_keys`（签名见 requirements Req 4）
  - stale 行按 `(sheet, 连续区间)` 分组，每组一个 plan，**从下往上删**
  - 悬空引用由引擎 `find_dangling_sites` 自动 fail-closed，**不传** `allow_ref_errors=True`
  - 🔴 原「清空业务格 + 保留公式格」方案随 §更正 4 作废
  - _Validates: Requirement 4.2, 4.3, 4.4（按更正后的新 AC 1~4）_

- [ ] 14. 全 entry 回归 + 变异反证
  - 按引用面定向跑（`backend/tests/workpaper_sync/` 整目录 >15 分钟超时，按符号反查）
  - 至少覆盖 D4 全 13 受管 sheet + store-only 表（D4-10）+ baseline-only 表
  - _Validates: Requirement 4.5_

- [ ] 15. * 消费方接线的死代码守卫
  - `build_delete_plan` / `resolve_deleted_row_keys` 接进生产后必须有生产消费方
  - 🔴 断言用 AST 而非 grep（否则命中自己的注释/import）
  - 仅当 Task 12+13 完成后才需要

- [ ] 16. 验收：extra→0 且 materialize 200
  - 靶子 = 当前 live 的 **77** 个 extra（模板占位 49 / 双重身份 24 / L2 污染 4）
  - 判据用 `_managed` 生产口径复算，离线 harness 为主、HTTP 为辅
  - _Validates: Requirement 3.1~3.3（借用其判据形态），§更正 5_

## 收尾状态

- 探针与临时产物：✅ 全清（18 个 `_d4p_*.py` + 6 个临时产物）
- 文档：✅ inventory 第九轮 ①~⑧ 已登记
- live 污染：保留作 C 的回归靶子（§更正 5 已裁决）
- git：未提交（工作树有大量并发会话改动，**禁 `git add -A`**）

---

# 🔴 C 主线实施进度（2026-09-28 第十轮，以本节为准）

## 已交付

- [x] 11. 收敛判据：与 overlay 严格对偶
  - `excel_materialize.plan_managed_writes` 新增 **6.2b**：
    `stale_rows = {row: ident for row, ident in physical if ident not in wanted}`
  - 🔴 仅当 `dynamic_table.table_key in projection.row_keys` 才收敛（用 `in` 而非 `get`：
    「store 没声明这张表」与「声明了且为空」语义不同，混用会误收敛 store 没管的表）
  - 🔴 **排除模板骨架行**（实测教训）：`is_template_skeleton_identity` 过滤
    `GTROW-{template}-{4位}`（非 MINTED）。首版没排除 ⇒
    `test_d4_1_materialize_extract_realchain` **4 红**
    （`IdentityRetentionError: 丢失 3 个 row identity, 首个 GTROW-D41MAIN-0009`）
  - 变异反证：`test_convergence_is_dual_to_overlay`（源码锁 `in projection.row_keys`
    与 `is_template_skeleton_identity` 两处判据形态）
  - _Validates: Requirement 4.1, 4.5_

- [x] 12+13. 收敛动作：**按受管区容量分级**（非纯删行，见 requirements 更正 6）
  - **6.8b** 分流：`survivors = [row for row in physical if row not in stale_rows]`
    - `survivors` 非空 → `stale_deleted`（删物理行）
    - `survivors` 为空 → `stale_cleared`（清空 editable 字面值格，保留身份载体 + 公式格）
  - **apply 阶段 0**（排在位移之前）：按**降序**逐行 `shrink_sheet_rows(delete_at=row, count=1)`
    + `_shrink_managed_table_ref` 对称收缩 Table ref
  - 🔴 删行与插行**互斥**：同时非空即 `RowSetDivergenceError`
    （`convergence_delete_with_insert_unsupported`）—— 不静默凑一个可能错位的 `insert_at`
  - 🔴 `shrink_sheet_rows` 的**首个生产接线点**（此前生产零消费方），闭合
    「能力已建 ≠ 接线完整」
  - `MaterializePlan` 加 `stale_deleted` / `stale_cleared`（默认 `()`，既有构造点零影响）
  - _Validates: Requirement 4.2~4.4 + 更正 6 AC 5~8_

- [x] E3（新增，替代原 Task 10）. roundtrip 的模板骨架豁免
  - `content_mutation._assert_roundtrip_equivalent` 算出 extra 后过滤：
    **①是模板骨架 ∧ ②store 未声明该行** ⇒ 豁免
  - ②保证不弱化 fail-closed：store 声明了却缺字段仍报；非骨架孤儿仍报
  - `contracts.is_template_skeleton_identity` 是收敛判据与本豁免的**单一真源**
  - 实测：D4 的 extra **77 → 0**，真实链路确认不再报 `extra`
  - _Validates: Requirement 5（按 E3 重定义）_

- [x] 守卫. `test_managed_row_convergence.py`（新，22 tests）
  - A 组：骨架身份域划分（含 `MINTED_ROW_IDENTITY_PREFIX` 绑定断言）
  - B 组：豁免是合取 —— 2 条变异反证（声明了仍报 / 非骨架仍报）+ **源码锁**
    （防有人「简化」掉 `identity not in declared` 后变异反证仍绿）
  - C 组：收敛与 overlay 对偶 + 分级 + plan 字段默认值
  - 回归：相关面 **238 passed**，新守卫 **22 passed**

## 🔴 未解决：500 仍未解除，卡在第五层根因（既有缺陷，非本 spec 引入）

真实链路（UI 点「在线编辑」→ D4-3）现报 **`missing`**（不再是 `extra`）：

```
staged representation 反读后缺少受管字段
adjudication_main_rows/xsheet-other-g5d43680692/{current_unadjusted,label,prior_unadjusted}
```

离线实证：`row_keys` 两侧都正确归 `adjudication_other_rows`，但**端点 `values` 里同一行
有两套 key 前缀**（`adjudication_main_rows/…` ＋ `adjudication_other_rows/…`），
而 provider 纯 store 投影只有后者。
⇒ `main_rows/` 前缀**由 overlay 引入** = **substrate extract 把 D4-1 同 sheet 双区的
other 区身份按主表 `table_key` 产出了字段 key**。materialize 在 main 受管区找不到该身份的
物理行 ⇒ 没写入 ⇒ 反读缺失。

⇒ 这是 **D4-1 双区 extract 的 table 归属缺陷**，影响面推测涵盖所有同 sheet 多受管区底稿
（D4-1 / D4-9 / D4-20 / D4-34 / D4-36 等），**需独立排查**（不在本 spec 范围）。

## ✅ 第十一轮：F1 + G2 + G3 收口，materialize **已转 200**（真实链路验收通过）

上一节的第五层根因（other 区身份按主表 `table_key` 产 key）本轮用 **F1** 修掉后，
又暴露并修完两层。完整七层链与实证见
`docs/operations/d4-bidirectional-writeback-inventory.md` 第十一轮。

### F1（第五层）：overlay 逐 table 判据

`projection_first_publication.overlay_store_on_baseline_projection` 增加
`owner_tables` + `_table_segment_agrees`，与 `final_row_id_set` **合取** ——
只有「该身份确实属于这张表的段」时才保留其 key。修完 `missing` 归零。

### G2（第六层）裁决：**删物理行降级为「清空业务格」**

删行牵动整套行号位移联动，而插行路径为此已有专门处理
（`_shift_sibling_table_refs` 兄弟 Table ref / footer 重冻结 /
`_apply_workbook_propagation` definedName 与跨 sheet 公式）。
实测：只补了自己那个 Table ref 的收缩就让 other 区出现 uuid 空行 ⇒
`_scan_row_identities` 按 tombstone **重新 mint** `GTROW-MINTED-*` ⇒ 又一轮 `extra`。

**拒绝 G1**（逐处补齐兄弟 ref）：每补一处暴露下一处，远超「修 500」的范围。

⇒ `shrink_sheet_rows` / `_shrink_managed_table_ref` / `MaterializePlan.stale_deleted`
**保留但刻意不启用**，并加**反向守卫**断言「收敛不得产出删行计划」。
这使原 Task 13（删物理行路径）**转为独立 spec 的前置**，本 spec 内不实施。

### 🔴 G3（第七层）根因：「清空」≠「写空文本」

`_cell_xml` 对 `CellWriteKind.inline_text` 的 `None` 与 `""` 都渲染成
`<is><t xml:space="preserve"></t></is>` —— 一个**存在且值为空串**的格，
extract 反读得 `""` ⇒ **仍算有值** ⇒ 仍产 key ⇒ `extra` 消不掉。
amount 字段「恰好」好了是巧合（`_render_number("")` 落成 `<v></v>`，openpyxl 读回 `None`）。

⇒ 这解释了 extra **精确地 7 → 1**：main 表 7 字段中 6 个 amount 消失、1 个 text 残留。

**修法**：新增 `CellWriteKind.blank`（渲染 `<c r=".." s=".."/>`，无 `t`/`<v>`/`<is>`，
保留样式 `s=`），收敛清空对**所有** value_type 统一用它。
先例同型：`boolean_literal` 对 `None` 也落真空格而非 `<v>0</v>`（BP-22）。

### 验收实证（真实链路，非离线）

点 D4-3「在线编辑」→ `POST …/materialize` **200 OK**，`generation` 165→**166**、
`replayed: false`、OnlyOffice iframe 加载、页面 0 errors。
新 substrate `000000166-d7d15bc324af.xlsx` 四条判据全过：

1. `W22 = 'xsheet-other-g5d43680692'` **身份保留**（否则重新 mint）
2. `A22~H22` 七格**全空**（`label` 从 `g5d43680692` 变空 ⇒ 收敛真实执行，非「没报错」）
3. `E22/I22` 公式**完好**（`=SUM(B22:D22)` / `=SUM(F22:H22)`）
4. other 区 `X25~X36` 身份全在 ⇒ **无 uuid 空行**，第六层不复发

### 回归

`test_managed_row_convergence.py` **26 passed**（新增 2 条：blank 源码锁 +
渲染形态断言含**变异反证** `inline_text(None)` 仍产空串格 ⇒ 证明判据有区分力）。
相关面 **230 passed 零回归**（task38 / d4_1_realchain / task15_pg /
single_pass / static_region）。

## 待办（本 spec 内）

- [x] 14. 全 entry 回归 + 变异反证 —— 230 + 26 passed
- [x] 16. 验收：materialize 转 200 —— 真实链路已通过（四条判据实证）
- [ ] 15* 死代码守卫 —— 🔴 **前提已反转**：G2 决定 `shrink_sheet_rows`
      **刻意不接线**，故不能加「必须有生产消费方」的守卫（那会与 G2 冲突）。
      当前守的是**反向**判据（收敛不得产出删行计划）。本条转入删行 spec。
- [ ] 13* 删物理行路径 —— 转独立 spec（需先补齐多区位移联动，见 G2）

---

# 🔴 收尾裁决（2026-09-28，本 spec 封板，以本节为准）

## 结论

后端主线已交付并通过**真实链路**验收：D4 点「在线编辑」→ `POST …/materialize`
**200 OK**，`generation` 165→**166**（四条判据实证见 §第十一轮）。

本 spec 就此封板。唯一真实欠账 Task 8 / Task 9 经用户裁决**转独立 spec**，
不在本 spec 内实施。

## 转出理由（原任务表第 8、9 项）

1. **按钮承诺的语义端点给不了**：Task 8 弹窗的核心选项「以在线编辑（OO）侧为准，
   覆盖表单」调的是 `adopt-substrate`，而 §更正 3 已把该端点**降级为运维工具**
   并登记其局限 —— `merge ≠ 覆盖`：以 base（当前 store）行集为权威，
   **只更新已有行、不追加 base 没有的行**。⇒ 照 Requirement 1 原文实现，
   按钮承诺的语义该端点给不了。

2. **原解阻用途已消失**：弹窗原本的解阻用途是「materialize 500 时打不开在线编辑」
   的出路，而第十一轮 materialize 已转 200 ⇒ 该用途随之消失。

3. **选项集合需重新裁决**：Requirement 1 本身（刷新取数不应隐式决定数据源）
   仍有独立价值，且其第三个选项「以表单为准，覆盖在线编辑」现已由 materialize
   收敛**真实实现** ⇒ 选项集合需重新裁决，不宜照原文照搬。

现状实证：`audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`
**第 144 行**仍是 `@click="onRowNameAlignmentRefresh"` 直接触发，
来源选择弹窗**未实现**。

## 🔴 原任务表未勾条目的对照登记（禁重跑）

顶部原任务表的 `[ ]` 是 append-only 保留备查，**不代表欠账**。下表给出逐条承接，
run-all 类编排**不得**据顶部 `[ ]` 重新执行。

| 原任务表条目 | 承接处 | 处置 |
| --- | --- | --- |
| 2. 确认弹窗差异摘要的数据来源（R4） | §实施进度 `[x] 2` | 已交付（裁决走 adopt 的 dry_run） |
| 3~6. adopt-substrate 端点 | §实施进度 `[x] 3~6` | 已交付（降级为运维工具） |
| 7. 端到端解阻验证 | §更正 3 | 作废（Requirement 3 不可达，adopt 非解阻路径） |
| 8. 刷新取数来源选择弹窗 | 本节 | **转独立 spec** |
| 9. Playwright 实测 P0 全链路 | 本节 | **转独立 spec**（依赖 Task 8） |
| 10. 公式格豁免 | §更正 1 | 作废（豁免本已存在且生效，改它是弱化）；替代物是 §第十轮 `[x] E3` 模板骨架豁免 |
| 11. 收敛判据：与 overlay 对偶 | §第十轮 `[x] 11` | 已交付 |
| 12. 收敛动作：默认清空业务格 | §第十轮 `[x] 12+13` ＋ §第十一轮 G2/G3 | 已交付（最终确为清空，但清空须用 `CellWriteKind.blank` 真空格而非写空串） |
| 13. 删物理行路径 | §第十一轮 G2 | 转独立 spec（`shrink_sheet_rows` / `_shrink_managed_table_ref` / `MaterializePlan.stale_deleted` 保留但刻意不启用，需先补齐多区位移联动） |
| 14. 全 entry 回归 + 变异反证 | §第十一轮 `[x] 14` | 已交付（230 + 26 passed） |
| 15. * 消费方接线的死代码守卫 | §第十一轮 `15*` | 转独立 spec（前提已反转：G2 决定不接线，故不能加「必须有生产消费方」的守卫；当前守的是反向判据「收敛不得产出删行计划」） |
| 第九轮 12+13（合并）. 删 stale 物理行 | §第十轮 `[x] 12+13` | 被分级方案取代 |
| 第九轮 16. 验收：extra→0 且 materialize 200 | §第十一轮 `[x] 16` | 已交付（extra 77→0，materialize 200） |

## 转出 spec 的建议范围

- **A：`刷新取数来源选择`**（Requirement 1 重裁决 ＋ Task 8 / 9）
  - 第一个裁决点：adopt 的 `merge` 语义要不要改成**真覆盖**。先裁这条，
    再定弹窗的选项集合。

- **B：`受管行删物理行的多区位移联动`**（Task 13 ＋ 15）
  - 前置欠账：兄弟 Table ref 收缩 / footer 重冻结 / definedName 与跨 sheet 公式传播。
  - 缺其一就会让 other 区出现 uuid 空行、并被 `_scan_row_identities` 重新 mint 身份，
    触发新一轮 `extra`（§第十一轮 G2 实测）。
