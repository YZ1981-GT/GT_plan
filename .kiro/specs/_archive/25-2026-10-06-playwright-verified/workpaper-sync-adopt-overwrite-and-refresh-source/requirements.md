# Requirements Document

adopt 真覆盖 + 刷新取数来源选择

## Introduction

上游 spec `workpaper-sync-managed-row-convergence` 已封板（materialize 真实链路转 200），
其末节把两项欠账转出为独立 spec。本 spec 承接 **A 线**：

> 「A 刷新取数来源选择：**第一个裁决点是 adopt 的 merge 语义要改成真覆盖**。」

因此本 spec 的顺序是**先裁 adopt 的行集语义，再定弹窗的选项集合** —— 不是反过来。
弹窗上「以在线编辑（OO）侧为准，覆盖表单」这句承诺，只有在 adopt 真的能覆盖时才成立；
否则按钮会骗用户。

### 🔴 上游结论已被现读 + 探针实证**推翻并细化**（本节是本 spec 的事实基线）

上游 `docs/operations/d4-bidirectional-writeback-inventory.md` §③ 与
`requirements.md` §更正 3 都写：

> `store_mirror` 的 merge 语义是「以 base（当前 store）行集为权威，只更新已有行、
> **不追加** base 没有的行」

**「不追加」这半句为假。** 本轮以离线探针真调 provider merge 纯函数
（`phase5_d4_revenue_detail.merge_projection_into_store_rows`，
与框架层引擎 `phase5_row_table_sheet.merge_projection_into_store_rows` 同形），
五例实测结果：

| 探针用例 | base | projection | 结果行集 | 结论 |
| --- | --- | --- | --- | --- |
| A 追加带名新行 | `[R1]` | R1(改值) + R2(product 非空) | `[R1, R2]` | **会追加** ⇒ 上游「不追加」为假 |
| B 变异对照：新行无名 | `[R1]` | R1(改值) + R2(只有 month_01) | `[R1]` | 幽灵行门剔除 ⇒ A/B 成对即**变异证明**（判据有区分力） |
| C 删除侧 | `[R1, R3]` | 只有 R1 | `[R1, R3]` | **永不删除** ⇒ 这才是「merge ≠ 覆盖」的真正内容 |
| D 空 base | `[]` | R1 + R2 | `[R1, R2]` | 与上游「空 base 下能产出完整行」一致 |
| E 已存在行清空 | `[R1]` | R1.product = `""` | `[R1]`（product 空） | 已存在行清空是合法编辑，不剔除 |

⇒ merge 的三态语义精确表述为：

- **更新**：命中身份的字段以 projection 为权威 ✅
- **追加**：projection 有 / base 无的身份**会追加**，但受**幽灵行门**约束
  （仅对本次新增的身份，若锚点业务名列为空则剔除）⚠️ 条件性
- **删除**：base 有 / projection 无的身份**永不删除** ❌

⇒ **「真覆盖」的唯一真实缺口是删除侧**（追加侧只差一个幽灵行门的口径裁决）。
这把改动面从「翻一整套合并策略」缩小成「补一个删除侧、且必须限定作用域」。

### 🔴 头号约束：`store_mirror` 是 OO 与 adopt 两条路径共用的同一份执行层

`store_mirror.py` 的模块 docstring 明写抽取目的就是消除第二真源；两个触发方：

| 触发方 | 调用点 | projection 来源 |
| --- | --- | --- |
| OO callback 落地 | `oo_to_html.OoToHtmlCoordinator._mirror_store_backed_if_needed`（薄转发） | 三路合并后的 **merged incoming** projection |
| adopt-substrate | `adopt_substrate_response.compute_adopt_substrate` | **published** substrate 的 extract |

OO 路径**依赖** base 权威语义：OO 会话期间 HTML 侧可能新增了尚未物化进 substrate 的行，
若删除侧对 OO 路径生效，这些行会被静默删掉。
⇒ 「把 merge 改成真覆盖」**不得**直接翻共用语义。落地形态由 design 裁定（ADR-AOS-001），
本文档只声明**结果约束**（Requirement 2）。

### 🔴 第二个必须解决的已知局限：`changed_item_count` 不可信

上游 §更正 3 局限②登记「`changed_item_count` 不可信」，归因为「同事务快照读不到未提交写」。
而原 Requirement 1 的弹窗要靠 `dry_run` 给用户看差异摘要 ——
摘要不可信就等于拿假数字骗用户按确认。本 spec 把「摘要可信」立为独立需求
（Requirement 3），并要求**对账式判据**（摘要数 == 真实落库变更数）。

🔴 该归因本身**未经本轮实证**，存在第二个候选成因：`store_mirror` 的
「`applied <= 0 and base_rows` ⇒ 跳过写库」使得真的没有 UPDATE 发出。
两者处置不同（前者要改读取时机，后者说明报 0 是正确的），
⇒ Requirement 3.7 要求用真库判别，不得沿用未验证归因。

---

## Glossary

- **Adopt_Service**：`backend/app/services/workpaper_sync/adopt_substrate_response.py` 的
  `compute_adopt_substrate` 及其伴生纯函数，承载 adopt-substrate 端点的全部业务。
- **Adopt_Endpoint**：`POST {USER_SYNC_PREFIX}/adopt-substrate`（`wp_sync_router.py`），
  只做 guard 与状态码映射。
- **Store_Mirror**：`store_mirror.py`，把 Projection 镜像进 `checklist_responses` 的
  会话无关执行层；OO callback 与 Adopt_Service 共用。
- **OO_Callback_Path**：`oo_to_html.OoToHtmlCoordinator` 调 Store_Mirror 的那条链路。
- **Provider_Merge**：各 provider 暴露的 `merge_projection_into_*` 门面
  （现算：`merge_projection_into_store_rows` 定义 **36** 个，`all_store_item_ids`
  定义 **47** 个；🔴 两者均为现算值，禁写死 —— 交付时须重算）。
  🔴 `all_store_item_ids` 的 **47** 属**高度波动值**，分解 = 已跟踪 HEAD 树 43
  + 未跟踪新 provider 3 + 已跟踪文件未提交改动 1 = 47；口径 = AST 扫
  `backend/app/services/workpaper_sync/**.py` **全量**（含 `adapters/` 与 `pilot_*`）。
  🔴 旧记 **46** 已作废：它静默排除了 `pilot_d2_large_json.py`
  （「排除 pilot」或「只取 `phase5_*`」两种口径都恰得 46）；上游 spec 的 47
  在本口径下**可复现** ⇒ 不存在「上游记 47、本轮修正为 46」这回事，
  后续任务**不得**再把该值改回 46。
- **Overwrite_Plan**：一次 adopt 的**声明式计划**：逐 store item 的
  待追加 / 待删除 / 待更新行身份清单 + 计数 + 稳定指纹。
- **plan_digest**：Overwrite_Plan 的稳定 sha256 摘要，用于「用户确认的就是将执行的」绑定。
- **declared_table**：出现在 substrate projection 的 `row_keys` 键集合里的 table_key。
  🔴 「不在键集合里」与「在键集合里但值为空元组」是**两种不同语义**
  （前者不碰，后者清空），不得混用 —— 与 overlay 侧 `in` vs `get` 的既有裁决同源。
- **row_section**：多个分区共用同一个 store 载荷数组时的分区归属字段
  （引擎 `RowTableSheetSpec.row_section_field` / `row_section_value`）。
  🔴 真实分母是 **6 个 store item**（`phase5_g{1,3,4,5,6,9}_02_*`），**不是旧记的 7**：
  旧记「现算赋非空字面量 7 处 / 6 文件」已被证伪 —— 复现旧正则确实得**恰 7 处 / 6 文件
  且文件名逐个相同**（⇒ 差异归因于口径而非树变化），但那 7 处经 `tokenize` 判别
  **无一处是可执行代码**（5 处在 docstring / 散文字符串，2 处在 `#` 注释）
  ⇒ 非空**字面量**真值为 **0 处**。6 处真声明的 value 是 `ast.Name`
  （`ROW_SECTION_FIELD_G*`）**不是字面量** ⇒ 任何「只认字面量」的口径都会把全部真声明漏掉。
  这 6 个 item 的分区字段名**不统一**（共 5 种取值：`acctClass` / `agingCategory` /
  `maturityCategory`（g4 与 g6 共用）/ `sectionKey` / `section`）
  ⇒ 取值必须读 `RowTableSheetSpec.row_section_field`，**禁硬编码字段名**（含 `"section"`）。
  🔴 现算值，禁写死 —— 交付时须重算。
- **幽灵行门**：Provider_Merge 里「仅对本次新增身份、若锚点业务名列为空则剔除」的既有判据。
- **Refresh_Source_Dialog**：本 spec 新增的「刷新取数来源选择」弹窗。
- **Workpaper_Renderer**：`audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`。

---

## Requirements

### Requirement 1: adopt 的行集语义改为 substrate 权威覆盖

**User Story:** 作为审计助理，当我选择「以在线编辑侧为准，覆盖表单」时，我要表单的受管行集
真的变成在线编辑侧的行集，而不是只更新了几个字段、行还是原来那些。

#### Acceptance Criteria

1. WHEN Adopt_Service 以覆盖模式执行 AND substrate projection 声明了某 declared_table
   THEN THE Adopt_Service SHALL 使该 table 在 store 侧的受管行身份集合等于该 table 的
   `row_keys` 集合（集合相等，顺序不作要求）
2. WHERE table_key 未出现在 substrate projection 的 `row_keys` 键集合中，
   THE Adopt_Service SHALL 保持该 table 对应的 store 行原样不变
3. WHEN substrate projection 的 `row_keys` 含某 table_key AND 其值为空元组
   THEN THE Adopt_Service SHALL 把该 table 的受管行集清空
4. WHERE store item 的载荷由多个 row_section 共用，
   THE Adopt_Service SHALL 只对本次 projection 声明的分区执行删除侧，
   其它分区的行身份集合保持逐元素不变
5. THE Adopt_Service SHALL 追加 substrate 有而 store 无的行身份（覆盖语义的追加侧）
6. IF 本次新增的行身份在 store 侧锚点业务名列为空 THEN THE Adopt_Service SHALL 按既有
   幽灵行门剔除该行，并在响应中给出被剔除的身份清单
7. THE Adopt_Service SHALL 在响应中给出逐 item 的 `rows_added` / `rows_deleted` /
   `rows_updated` / `rows_ghost_dropped` 四个计数与对应身份清单
8. THE Adopt_Service SHALL 把删除侧的行身份清单写入审计日志 details（现有 event_type
   `workpaper_sync_adopt_substrate` 不变）

---

### Requirement 2: OO callback 路径的行集语义保持不变

**User Story:** 作为平台维护者，我要求「让 adopt 能删行」这件事不会让在线编辑的每次保存
变成全量覆盖，把用户在表单侧刚加的行静默删掉。

#### Acceptance Criteria

1. WHILE 镜像由 OO_Callback_Path 触发，THE Store_Mirror SHALL 保持 base 权威语义
   （不删除 projection 未声明的 store 行身份）
2. THE Store_Mirror SHALL 以「base 权威」为默认行为，使 OO_Callback_Path 的调用点无需
   传递任何新参数即得到与改动前一致的结果
3. THE Provider_Merge 的公开签名与返回形态 SHALL 保持不变（不得为本 spec 改动 36 个
   `merge_projection_into_store_rows` 定义的签名；🔴 36 为现算值，交付时重算）
4. 变异反证：THE Test_Suite SHALL 用同一组 `(base, projection)` 分别以两种模式执行，
   断言删除侧结果**不同**（相同即判据失效）
5. 源码锁：THE Test_Suite SHALL 断言 `oo_to_html` 对 Store_Mirror 的转发调用点未传覆盖模式
   参数，使有人「顺手统一」两侧时打红
6. THE Test_Suite SHALL 对 OO_Callback_Path 的既有引用面回归，断言零行为变化

---

### Requirement 3: dry_run 的差异摘要必须与真实落库变更逐项相等

**User Story:** 作为审计助理，弹窗上告诉我「将删除 12 行」，我按确认后就应该正好删 12 行；
我不接受一个和实际不一样的数字。

#### Acceptance Criteria

1. THE Adopt_Service SHALL 由**同一个**纯函数计算 Overwrite_Plan，dry_run 与真实执行
   共用该函数（不得两套算法）
2. WHEN `dry_run=True` THEN THE Adopt_Service SHALL 返回 Overwrite_Plan 的完整内容：
   逐 item 的待追加 / 待删除 / 待更新身份清单、四个计数、两侧行数
3. THE Adopt_Service SHALL 为 Overwrite_Plan 产出与元素顺序无关的稳定 `plan_digest`
4. WHEN `dry_run=False` AND 客户端回传了 `plan_digest` AND 服务端重算值与之不符
   THEN THE Adopt_Endpoint SHALL 拒绝执行并返回 409 与可读原因
5. WHEN 真实执行完成写入 AND 提交之前 THEN THE Adopt_Service SHALL 复读本次写入结果并与
   Overwrite_Plan 比对，不一致即回滚整个事务并 fail visible
6. THE Adopt_Service SHALL 使响应的 `changed_item_count` 取自 Overwrite_Plan，
   不取自覆盖前后的 remark 快照差集
7. THE Test_Suite SHALL 用真实 PostgreSQL 判别「快照 diff 报 0」的成因属于
   「同事务可见性」还是「无变化跳过写库」，并把结论登记进本 spec 的实施记录
8. THE Test_Suite SHALL 用真实 PostgreSQL 做对账：同一 substrate 与同一 store 版本下，
   dry_run 报出的三个身份清单与真实执行后实际落库的三个身份清单逐元素相等

---

### Requirement 4: 不可覆盖形态必须显式登记，不得静默部分覆盖

**User Story:** 作为平台维护者，我要求「覆盖」这件事对做不到的 store item 明确说做不到，
而不是悄悄只覆盖一部分，让「覆盖不完整」从一条已知局限变成另一条已知局限。

#### Acceptance Criteria

1. WHERE store item 的载荷不是可按行身份枚举的行数组（dict 形态 store、纯文本固定项等），
   THE Adopt_Service SHALL 对该 item 跳过删除侧，并在响应中逐条列出被跳过的 item 与原因
2. THE Adopt_Service SHALL 在响应中以显式清单（而非仅总数）表达跳过集合
3. THE Test_Suite SHALL 校验跳过清单里的每个 item 确实仍属不可枚举形态
   （白名单无失效条目）
4. IF store item 的载荷解析失败（非合法 JSON / 非数组） THEN THE Adopt_Service SHALL
   fail visible 并给出该 item 的 item_id，不得当成零行处理
5. THE Adopt_Service SHALL 不依赖任何硬编码的行身份键名（现算行身份键字面量 **7** 种取值：
   `rowId` / `id` / `rowKey` / `key` / `month` / `metricName` / `rowUuid`；
   🔴 现算值，禁写死，交付时重算）

---

### Requirement 5: 刷新取数必须让用户显式选择来源（原 Requirement 1 重裁决）

**User Story:** 作为审计助理，表单与在线编辑两侧不一致时，我要明确指定「以哪一侧为准」，
而不是由系统隐式决定。

#### 现状（现读确认，不是推测）

- `GtWpRenderer.vue` 的「刷新取数」按钮仍直接绑 `onRowNameAlignmentRefresh`
  （处理函数同文件内，走 `POST /api/workpapers/{wpId}/row-name-alignment` 后 `reload()`），
  方向是**上游业务数据 → store**，既不读 substrate 也不读 OO ⇒ 不改行集
- 前端全仓对 `adopt-substrate` 的引用现算为 **0**
  （变异证明：同一扫描器对 `row-name-alignment` 在同文件命中非零 ⇒ 扫描口径有效）

#### 选项集合的重裁决（与原文差异须显式声明）

| 原 Requirement 1 选项 | 本 spec 裁决 |
| --- | --- |
| 从上游业务数据取数 | ✅ 沿用，成为第一个可执行选项（实现不改） |
| 以在线编辑（OO）侧为准，覆盖表单 | ⚠️ 变形：语义由 Requirement 1 兑现后才成为可执行选项 |
| 以表单为准，覆盖在线编辑〔原置灰〕 | 🔁 反转：该方向已由 materialize 受管行收敛真实实现，不再是「暂不可用」，改为**说明项 + 指引**，不新增执行入口 |

#### Acceptance Criteria

1. WHEN 用户点击「刷新取数」 THEN THE Workpaper_Renderer SHALL 打开 Refresh_Source_Dialog，
   不直接执行取数
2. THE Refresh_Source_Dialog SHALL 提供恰 2 个可执行来源
   （「从上游业务数据取数」「以在线编辑侧为准，覆盖表单」）与恰 1 个说明项
   （「以表单为准，同步到在线编辑」），每项附一句说明其影响范围
3. THE Refresh_Source_Dialog SHALL 展示两侧行数差异摘要与将发生的增删条数，
   数据取自 Adopt_Service 的 dry_run 响应
4. WHEN 用户关闭 Refresh_Source_Dialog 而未选择来源 THEN THE Workpaper_Renderer SHALL
   不执行任何取数请求
5. WHEN 用户选择「以在线编辑侧为准，覆盖表单」 THEN THE Refresh_Source_Dialog SHALL 要求
   二次确认，并在确认文案中明示这是破坏性操作与将删除的行数
6. WHEN 用户在二次确认中点确认 THEN THE Workpaper_Renderer SHALL 携带 dry_run 返回的
   `plan_digest` 与 `expected_revision` 发起真实执行请求
7. WHERE 本 entry 未注册 sync 或无已发布 substrate，THE Refresh_Source_Dialog SHALL
   禁用「覆盖表单」选项并就地说明原因
8. THE Refresh_Source_Dialog 的全部用户可见文本 SHALL 为中文
   （技术术语 OO / Excel / JSON 可保留英文）
9. THE 说明项「以表单为准，同步到在线编辑」SHALL 指引用户使用既有「在线编辑」按钮，
   且 SHALL 不触发 materialize 请求
10. WHEN 真实执行返回成功 THEN THE Workpaper_Renderer SHALL 重载底稿数据并提示实际增删条数

---

### Requirement 6: 端点级鉴权与并发 / 回滚保护复核

**User Story:** 作为平台维护者，我要求这个破坏性端点的鉴权、并发锁、可回滚三道保护是
**真发 HTTP 请求**验过的，不是只测了 service 纯函数。

#### 现状（现读确认）

- `Adopt_Endpoint` 经 `Depends(_services)`，而 `_services` 依赖 `get_db` 与
  `get_current_user`（router docstring 明写后者是**唯一** 401 产生点）
- `adopt_substrate` 已登记进 `_WRITE_ACTIONS`（未登记则 `_action_authorizer` 恒 403）
- 后端对 `adopt-substrate` 的既有测试引用现算 **4 处 / 3 文件**，其中经 `tokenize`
  判注释后**可执行代码仅 1 处**（`test_task28_sync_router.py` 里「路由清单 / handler 分母」
  守卫内的路由清单字面量 `("POST", "/adopt-substrate")`）；其余 3 处**全是注释**
  （`test_task28_sync_router.py` 1 处 + `test_d2_store_value_equivalence.py` 1 处
  + `test_d4_mirror_shape_invariants.py` 1 处）
  ⇒ **无任何端点级行为测试**（这是本 spec 必须补的）。🔴 现算值，禁写死 —— 交付时须重算

#### Acceptance Criteria

1. WHEN 请求未携带有效身份 THEN THE Adopt_Endpoint SHALL 返回 401
2. WHILE entry 处于 `workflow_locked`，THE Adopt_Endpoint SHALL 拒绝该请求并返回 403
3. WHEN `expected_revision` 与服务端当前 `content_revision` 不符 THEN THE Adopt_Endpoint
   SHALL 返回 409 与可读原因
4. IF 本 entry 无已发布 substrate（缺 representation 指针或文件缺失） THEN THE
   Adopt_Endpoint SHALL 返回 409 并保持 store 原样（不得以空内容覆盖）
5. IF 本 entry 的 registration 无 approved contract THEN THE Adopt_Endpoint SHALL 返回 422
6. THE Test_Suite SHALL 以真发 HTTP 请求的方式覆盖上述五个状态码分支，
   并 SHALL 通过替换内层 `get_db` / `get_current_user` 依赖实现，
   不得直接以依赖工厂对象作 override 键
7. WHEN 覆盖发生 THEN THE Adopt_Service SHALL 在同一事务内写入业务变更、回滚快照与
   hash-chain 审计（三者要么一起成功要么一起回滚）
8. THE Adopt_Service SHALL 使多个 store item 的写入在单个事务内完成
9. THE 回滚快照 SHALL 足以恢复被覆盖 item 的原始载荷（含被删除的行）

---

### Requirement 7: 真实链路实测

**User Story:** 作为使用者，我要的是在浏览器里点下去真的对，不是单测绿。

#### Acceptance Criteria

1. WHEN 在真实前后端环境打开一个已注册 sync 且有已发布 substrate 的 entry 并点击
   「刷新取数」 THEN Refresh_Source_Dialog SHALL 出现并显示两侧行数与增删条数
2. WHEN 选择「以在线编辑侧为准，覆盖表单」并完成二次确认 THEN 请求 SHALL 返回成功，
   且刷新后表单受管行集与 dry_run 摘要预告的一致
3. WHILE 上述流程进行，浏览器控制台 SHALL 无 error 级输出
4. IF 真实环境不可用 THEN 本需求的任务 SHALL 如实标记为未实测，不得标为完成

---

## 非目标（明确排除）

1. **不碰受管行删物理行的多区位移联动** —— 那是并行的 B 线 spec
   `workpaper-sync-row-deletion-multi-region-propagation`。本 spec **不改**
   `stale_deleted` / `shrink_sheet_rows` / `_shrink_managed_table_ref`，
   也不改 materialize 侧收敛的任何行为
2. **不改 Provider_Merge 的公开签名**（Requirement 2.3）
3. **不新增「不打开在线编辑就 materialize」的入口**（Requirement 5.9）
4. **不清理 live 测试污染** —— 上游 §更正 5 已裁决保留为回归靶子
5. **不弱化 roundtrip fail-closed 判据**，不动模板骨架豁免
6. **不改 `importFromLedger` 的身份幂等性缺陷**（上游遗留③，属行为变更需产品裁决）

## 遗留待裁决（记录，不在本 spec 实施）

1. dict 形态 store item 的删除侧支持（Requirement 4.1 现为跳过 + 登记）——
   需 provider 侧提供「rows 路径声明」或 `prune` 门面，改动面涉及多个 provider
2. 是否给「以表单为准，同步到在线编辑」一个独立执行入口（当前为说明项 + 指引）
3. adopt 的批量版本（多底稿一次覆盖）——「批量刷新」弹窗是否纳入本来源选择
