# Implementation Plan — adopt 真覆盖 + 刷新取数来源选择

## Overview

顺序即依赖：**先把 adopt 的行集语义补成真覆盖（阶段 0~4），再改弹窗（阶段 5~6）**。
这是用户裁决的顺序，不可颠倒 —— 弹窗上「以在线编辑侧为准，覆盖表单」这句承诺只有在
adopt 真能覆盖时才成立。

🔴 每个实现任务开始前**先重新现读**相关文件（有并发会话在改 `workpaper_sync` 域）。
🔴 判据禁写死 `.vue` 行号与任何计数；锚点用符号名 / 端点字面量 / 形态特征。
🔴 每条「结构性零」结论必配变异证明（同一扫描器在非空场景须命中非零）。
🔴 本 spec **不碰** `stale_deleted` / `shrink_sheet_rows` / `_shrink_managed_table_ref`
（那是 B 线 spec `workpaper-sync-row-deletion-multi-region-propagation`）。

## Tasks

- [ ] 1. 现算基线复算与行枚举器可用性普查
  - [ ] 1.1 复算 design「§ Overview」的八项现算值并回填 spec
    - 探针放 `backend/scripts/analyze/_aos_*.py`（`_` 前缀 = 用完即删）
    - 逐项复算：`all_store_item_ids` 定义数 / `merge_projection_into_store_rows` 定义数 /
      `iter_store_rows` 定义数 / `ROW_IDENTITY_STORE_KEY*` 赋值处与字面量取值分布 /
      `row_section_field=` 非空字面量处数 / 前端 `adopt-substrate` 引用数 /
      后端 `adopt-substrate` 测试引用数
    - 🔴 与 spec 记录不一致即**更新 spec** 并在本任务下记差异，不得默认沿用
    - 🔴 前端引用为 0 这条须配变异证明：同一扫描器对 `row-name-alignment` 须命中非零
    - _Requirements: 2.3, 4.5_
  - [ ] 1.2 普查每个 store item 的行枚举器可用性，产出两张显式清单
    - 逐 adapter 取 `all_store_item_ids()`，再按 `store_item_registry` 找 provider 模块，
      现读其是否暴露可用的 `iter_store_rows` 门面
    - 输出「可枚举」与「不可枚举（含原因）」两张清单；不可枚举清单即 Requirement 4.1 的跳过集合基线
    - 🔴 「读出为空」先排除解析失败：若某 provider 的 `iter_store_rows` 因 import 失败而取不到，
      须与「本来就没有」分开登记（两者处置不同）
    - _Requirements: 4.1, 4.3_

- [ ] 2. 真库判别 `changed_item_count` 报 0 的成因
  - 构造两组：(a) substrate 与 store 内容不同（应有变更）(b) 内容相同（应无变更）
  - 观测 `_snapshot_store` 的 after 快照是否看得到 `store_mirror` 的未提交写
  - 结论二选一并登记：「同事务可见性」还是「`applied<=0 and base` 跳过写库」
  - 🔴 必须真库（SQLite 内存库测不出这类事务可见性/数据分布问题）
  - _Requirements: 3.7_

- [ ] 3. 新建计划纯函数模块 `adopt_overwrite_plan.py`
  - [ ] 3.1 数据模型与稳定摘要
    - `ItemOverwriteDelta` / `OverwritePlan` / `OverwritePlan.digest`
    - digest 必须与清单元素顺序无关（排序后哈希），且对内容变化敏感
    - _Requirements: 1.7, 3.2, 3.3, 4.2_
  - [ ]* 3.2 属性测试：Overwrite_Plan 内部自洽
    - **Property 4: Overwrite_Plan 内部自洽**
    - **Validates: Requirements 1.7**
  - [ ]* 3.3 属性测试：plan_digest 顺序无关且内容敏感
    - **Property 6: plan_digest 顺序无关且内容敏感**
    - **Validates: Requirements 3.3**
  - [ ] 3.4 `RowReader` 适配层
    - 只做对 provider 既有 `iter_store_rows` 门面的薄适配；取不到即返回 None
      并由调用方记 `skipped_reason`
    - 🔴 **禁**自造 `row.get("rowId")` 兜底（行身份键现算多种取值）
    - _Requirements: 4.1, 4.4, 4.5_
  - [ ]* 3.5 属性测试：行身份识别与键名无关
    - **Property 10: 行身份识别与键名无关**
    - **Validates: Requirements 4.5**
  - [ ]* 3.6 属性测试：非法载荷一律 fail visible
    - **Property 9: 非法载荷一律 fail visible**
    - **Validates: Requirements 4.4**

- [ ] 4. 实现删除侧剪枝与计划计算
  - [ ] 4.1 `prune_undeclared_rows`：按声明身份集 + 分区剪枝
    - 作用域门：只处理 `table_key` 在 `row_keys` **键集合**里的表
    - 空值二分：不在键集合 ⇒ 不碰；在键集合但值为空元组 ⇒ 清空
    - 分区门：同一载荷承载多分区时只删本次声明分区的行
    - 返回 `(新载荷, 被删身份)`，纯函数、不碰 DB
    - _Requirements: 1.2, 1.3, 1.4_
  - [ ] 4.2 `compute_overwrite_plan`：聚合逐 item delta 与两侧行数
    - 逐 item 算 added / deleted / updated / ghost_dropped 四清单与计数
    - 不可枚举形态的 item 记 `skipped_reason` 并进 `skipped_items` 显式清单
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 3.1, 3.2, 4.1, 4.2_
  - [ ]* 4.3 属性测试：声明侧行集等式
    - **Property 1: 声明侧行集等式**
    - **Validates: Requirements 1.1, 1.3, 1.5**
  - [ ]* 4.4 属性测试：作用域外的行逐元素不变（参数化 table / 分区两维）
    - **Property 2: 作用域外的行逐元素不变**
    - **Validates: Requirements 1.2, 1.4**
  - [ ]* 4.5 属性测试：幽灵行门语义不变且被如实登记
    - **Property 3: 幽灵行门语义不变且被如实登记**
    - **Validates: Requirements 1.6**
  - [ ]* 4.6 属性测试：不可枚举形态载荷不被改动且被登记
    - **Property 8: 不可枚举形态的载荷不被改动且被登记**
    - **Validates: Requirements 4.1**
  - [ ]* 4.7 单测：`in` 与空元组的显式对照
    - 两例：table 不在 `row_keys` 键集合 ⇒ 行不变；在键集合但值为 `()` ⇒ 清空
    - 这是 prework 把 AC 1.3 降为边界后留的可读性锚点
    - _Requirements: 1.3_
  - [ ]* 4.8 守卫：跳过白名单无失效条目
    - 对跳过清单里每个 item 现读其 provider，断言确实取不到行枚举器
    - 反向变异：塞一个可枚举的 list-store item 进白名单 ⇒ 判据必须打红
    - _Requirements: 4.3_

- [ ] 5. Checkpoint — 纯函数层全绿
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. 接进 Adopt_Service（`adopt_substrate_response.py`）
  - [ ] 6.1 `dry_run` 改为返回完整 Overwrite_Plan
    - 取代现有 `_dry_run_summary` 的「只报 substrate 逐表行数」
    - dry_run 与真实执行**共用** `compute_overwrite_plan`，不得两套算法
    - _Requirements: 3.1, 3.2_
  - [ ] 6.2 `plan_digest` 校验与新 domain 错误类
    - 新增 `AdoptPlanDigestMismatchError` / `AdoptStorePayloadUnreadableError` /
      `AdoptPlanVerificationError`，`error_code` 命名与既有三个同风格
    - _Requirements: 3.4, 4.4_
  - [ ] 6.3 删除侧应用 + 提交前复读比对
    - 在 `mirror_projection_into_store(..., commit=False)` **之后**应用删除侧
      （🔴 顺序不可调换：前置清 base 会让幽灵行门全面生效，见 design ADR-AOS-001）
    - 写完在同事务复读，与 plan 不符即 rollback 并 fail visible
    - _Requirements: 1.1, 1.2, 3.5_
  - [ ] 6.4 `changed_item_count` 改由 plan 供出
    - 移除对「覆盖前后 remark 快照差集」的依赖
    - 源码锁：断言该字段不再取自 `_diff_snapshots`
    - _Requirements: 3.6_
  - [ ] 6.5 回滚快照与审计 details 扩展
    - `details` 追加 `rows_deleted_by_item` / `plan_digest` / `skipped_items`
    - `event_type` 沿用 `workpaper_sync_adopt_substrate`，**不**进 `EVENT_TYPE_SCHEMAS`
    - 业务写 / 回滚快照 / 审计三者同一事务
    - _Requirements: 1.8, 6.7, 6.9_
  - [ ]* 6.6 属性测试：应用计划后重算计划为空
    - **Property 7: 应用计划后重算计划为空（收敛）**
    - **Validates: Requirements 3.8**
  - [ ]* 6.7 属性测试：回滚快照可完整还原
    - **Property 11: 回滚快照可完整还原（round-trip）**
    - **Validates: Requirements 6.9**

- [ ] 7. OO 路径隔离判据（J1~J5）
  - [ ] 7.1 源码锁与基线双条件
    - J1：`oo_to_html` 三个 `_mirror_*` 转发方法不出现 prune 相关符号
    - J2：`store_mirror.mirror_projection_into_store` 函数体内本 spec 符号命中为零
      + 会话基线 sha256（🔴 工作树可能被并发会话改动，单靠 `git diff == 0` 不是判据）
    - J5：prune 调用点全仓恰 1 处且在 adopt 链上（逐条判注释 vs 代码）
    - _Requirements: 2.2, 2.5_
  - [ ]* 7.2 属性测试：模式二分（含变异反证）
    - **Property 5: 模式二分（OO 不被连带改变）**
    - **Validates: Requirements 2.1, 2.4**
  - [ ] 7.3 OO 既有引用面回归
    - 按符号反查测试文件定向跑（🔴 `backend/tests/workpaper_sync/` 整目录 >15 分钟超时）
    - 至少覆盖 OO callback 镜像直接面 + `store_item_registry` + D4 mirror 形态守卫
    - _Requirements: 2.6_
  - [ ] 7.4 反向判据：路由清单守卫不应变化
    - 本 spec 不新增路由 ⇒ `test_task28_sync_router.py` 的 handler 分母 / 路由清单 /
      slashed suffixes 三处**不应**改动；若需改动即说明误加了路由，应打红
    - _Requirements: 2.3_

- [ ] 8. 端点级测试（🔴 TestClient 真发 HTTP，不是只测 service）
  - [ ] 8.1 五个状态码分支各一例
    - 401 未认证 / 403 `workflow_locked` / 409 revision 不符 /
      409 无已发布 substrate / 422 无 approved contract
    - 🔴 409 无已发布 substrate 这例必须**同时**断言「状态码」与「store 行数未变」——
      只看状态码不足以排除空覆盖
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [ ] 8.2 `plan_digest` 不符 ⇒ 409
    - 先取 dry_run 的 digest，再改动 store 使 digest 过期，然后带旧 digest 执行
    - _Requirements: 3.4_
  - [ ] 8.3 测试注入形态的自我约束
    - override 内层 `get_db` / `get_current_user`（稳定函数对象），
      🔴 **禁**以依赖工厂对象作 `dependency_overrides` 键（会静默失效致全部 401）
    - 沿用既有 pg 测试的「一次 `asyncio.run` 采集 + 异常记录不穿透 +
      `test_no_phase_crashed_during_collection`」做法
    - 源码锁：断言本测试文件真的经 ASGI 发请求
    - _Requirements: 6.6_
  - [ ] 8.4 原子性注入测试
    - 三个注入点（business 写后 / 删除侧后 / 审计前）各一例，断言库内零残留
    - 覆盖多 item 场景（上游实测过 137→154 的部分写入事故形态）
    - _Requirements: 6.7, 6.8_
  - [ ] 8.5 真库对账：dry_run 摘要 == 实际落库变更
    - 同一 substrate 与同一 store 版本下，dry_run 的 added / deleted / updated 三清单与
      真实执行后实际落库的三清单**逐元素相等**
    - 🔴 必须真库（口径类判据 SQLite 测不出数据分布问题）
    - _Requirements: 3.8_

- [ ] 9. Checkpoint — 后端全链路全绿
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. 前端：`RefreshSourceDialog` 组件
  - [ ] 10.1 组件骨架与三项内容
    - 恰 2 个可执行来源 + 恰 1 个说明项，每项一句影响范围说明
    - 打开即请求 dry_run，渲染「表单 N 行 ｜ 在线编辑侧 M 行」与增 / 删 / 改条数
    - 数字**全部**取自响应字段，前端不自行重算
    - 🔴 现读同文件的 HTTP 客户端用法后保持一致（`http.*` 需 `.data`，`api.*` 已解构）
    - _Requirements: 5.2, 5.3_
  - [ ] 10.2 破坏性二次确认与请求体
    - 「覆盖表单」二次确认，文案明示破坏性与将删除的行数
    - 确认请求携带 `plan_digest` 与 `expected_revision`
    - 409 digest 不符 ⇒ 提示两侧已变化并重取 dry_run
    - _Requirements: 5.5, 5.6_
  - [ ] 10.3 禁用态与说明项
    - dry_run 返回 `adopt_substrate_not_published` / `adopt_contract_required` ⇒
      「覆盖表单」禁用 + 就地显示原因
    - 说明项「以表单为准，同步到在线编辑」不可选，文案指引点「在线编辑」按钮，且不发任何请求
    - _Requirements: 5.7, 5.9_
  - [ ] 10.4 成功后的重载与提示
    - 成功后 `reload()` 并提示**实际**增删条数（取自响应，不复用 dry_run 的数）
    - _Requirements: 5.10_

- [ ] 11. 前端：接线 `GtWpRenderer.vue`
  - 「刷新取数」按钮 `@click` 由 `onRowNameAlignmentRefresh` 改为打开弹窗的处理器
  - 既有 `onRowNameAlignmentRefresh` **函数体一字不改**，成为第一个选项的处理器
  - 🔴 锚点用符号名，不写死行号
  - _Requirements: 5.1, 5.4_

- [ ] 12. 前端测试
  - [ ]* 12.1 交互路径组件测试
    - 点「刷新取数」⇒ 弹窗可见且**未**发出 `row-name-alignment` 请求
    - 未选择直接关闭 ⇒ 零请求
    - 选第一项 ⇒ 走既有取数；选覆盖项 ⇒ 出二次确认
    - 点说明项 ⇒ 零请求（不触发 materialize）
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10_
  - [ ]* 12.2 属性测试：前端摘要与计划逐值相等
    - **Property 12: 前端摘要与计划逐值相等**
    - **Validates: Requirements 5.3**
  - [ ] 12.3 中文文案守卫
    - 扫组件模板与文案常量，断言用户可见文本无未豁免英文
    - 豁免词（OO / Excel / JSON 等）逐条白名单，并配「白名单无失效条目」检查
    - _Requirements: 5.8_

- [ ] 13. 真实链路实测（Playwright）
  - 打开一个已注册 sync 且有已发布 substrate 的 entry → 点「刷新取数」→ 弹窗显示两侧行数与
    增删条数 → 选「以在线编辑侧为准，覆盖表单」→ 二次确认 → 成功 →
    刷新后表单受管行集与摘要预告一致；控制台 0 error
  - 🔴 环境不可用时**如实**标未实测（用「代码已改但未实测」措辞），不得标完成
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 14. 收尾
  - [ ] 14.1 探针清理
    - 删除全部 `backend/scripts/analyze/_aos_*.py` 与其临时产物
  - [ ] 14.2 判据引用闭合性自查
    - 脚本化检查：每条 AC（Requirement X.Y）与每条 Property 至少被本文件引用一次
    - 🔴 正则须处理 `_Requirements: 1.1, 1.3_` 这类尾部下划线形态
      （`\b` 在 `1_` 处不匹配，须用 `(?![0-9])`）
    - _Requirements: 7.4_
  - [ ] 14.3 更新 `.kiro/specs/INDEX.md` 的完成度与本轮教训
    - 🔴 INDEX.md 是纯 CRLF ⇒ `read_bytes().decode('utf-8')` + `write_bytes()`；
      表格第三格内禁裸 pipe；校验「每行恰 4 个未转义 pipe」
    - _Requirements: 7.4_

- [ ] 15. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标 `*` 的子任务是测试类，可为 MVP 跳过；但本 spec 的 `*` 子任务里含**全部 12 条 property**
  与变异反证 —— 平台铁律要求 run-all 时 `*` 也必须做完，除非用户明确说跳过
- 顶层任务不带 `*`
- 阶段 0（Task 1~2）不改生产代码，只现算与判别，其结论会回填 spec
- 🔴 Task 6.3 的「merge 之后再删」顺序是 ADR-AOS-001 的核心，不可调换
- 🔴 Task 7 的整组是「不破坏 OO 路径」的唯一保障，不得因为「adopt 测试全绿」而跳过

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2"] },
    { "id": 1, "tasks": ["3.1", "3.4"] },
    { "id": 2, "tasks": ["3.2", "3.3", "3.5", "3.6", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.7"] },
    { "id": 4, "tasks": ["4.3", "4.4", "4.5", "4.6", "4.8"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["6.3"] },
    { "id": 7, "tasks": ["6.4", "6.5"] },
    { "id": 8, "tasks": ["6.6", "6.7", "7.1", "7.2"] },
    { "id": 9, "tasks": ["7.3", "7.4", "8.1", "8.2"] },
    { "id": 10, "tasks": ["8.3", "8.4", "8.5"] },
    { "id": 11, "tasks": ["10.1"] },
    { "id": 12, "tasks": ["10.2", "10.3", "10.4"] },
    { "id": 13, "tasks": ["11"] },
    { "id": 14, "tasks": ["12.1", "12.2", "12.3"] },
    { "id": 15, "tasks": ["13"] },
    { "id": 16, "tasks": ["14.1", "14.2", "14.3"] }
  ]
}
```
