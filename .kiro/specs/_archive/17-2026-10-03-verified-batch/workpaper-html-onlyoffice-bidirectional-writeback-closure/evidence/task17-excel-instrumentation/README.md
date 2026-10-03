# Task 17 证据：Excel instrumentation definition 与 non-current upgrade candidate 生成器

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` / Wave 1 Task 17
Requirements: 2.1, 2.3, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.19, 9.1, 9.8, 9.9, 9.10, 14.16
Properties: **P28** / **P66** / **P67** / **P71**

## 1. 本任务交付了什么

| 产物 | 角色 |
|---|---|
| `backend/app/services/workpaper_sync/excel_instrumentation.py` | 载体裁决门 + canonical payload + zip 级注入 + 等价/反读 + candidate-only 门面 + 编排器 |
| `backend/app/services/excel_metadata_sheet_policy.py` | 隐藏 metadata sheet 的业务排除名单（**单一真源**，sheet 名只从 Task 5 的 `GT_SYNC_SHEET_NAME` import） |
| `backend/app/services/xlsx_read_adapter.py`（改） | `list_sheet_names` 排除 `_GT_SYNC`（六处业务枚举的共同入口） |
| `backend/app/services/xlsx_to_univer.py`（改） | Univer 快照排除 `_GT_SYNC`（否则编辑器标签栏多一张无法解释的表） |
| `backend/data/onlyoffice_excel_instrumentation_gate.json` | Task 5 `stale_policy.invalidate_on` 四项的机器可比对 digest 基线（Tier A 运行时 / Tier B 仓库上下文） |
| `backend/tests/workpaper_sync/test_task17_excel_instrumentation.py` | 纯域守卫（真实权威模板 K11 + C24） |
| `backend/tests/workpaper_sync/test_task17_excel_instrumentation_pg.py` | 真实 PostgreSQL 守卫（否定式承诺） |
| `backend/scripts/diagnose/mutate_task17_excel_instrumentation_guards.py` | 42 条变异检验 |

发布 DAG 只走到第二段 + candidate 登记：

```
template definition ──► instrumentation definition ──► non-current candidate
（权威源 backend/wp_templates/）（只单向引用 template digest）（state=awaiting_contract）
```

## 2. 依据的 Task 5 实证裁决（P66）

单一真源 `backend/data/onlyoffice_excel_identity_carrier_contract.json`，逐条 `probe_verdict` 实读：

| 载体 | 裁决 | 用不用 |
|---|---|---|
| `hidden_sheet` / `defined_name` / `excel_table` / `hidden_uuid_column` | `passed` | 全部采用 |

| 锚点 | 裁决 | 用不用 |
|---|---|---|
| `defined_name_ref` / `excel_table_sheet_association` | `passed` | 采用 |
| `sheet_id` / `sheet_display_name` | **`failed`** | 禁用，且**结构上不可达** |

`sheet_id` 被证伪的实测后果（findings.md §3）：OO 9.4.0-129 **每次保存**把 `sheetId` 按 tab
顺序重编号为 `1..N`，15/15 个回传 artifact 全部如此，第一个失败的操作只是「打开→改一格→
forcesave」。因此生产反读 `read_back_identity()` **只传** `expected_table` + `uuid_column_letter`，
让 `identity_inventory()` 的 `sheet_resolution_candidates` 只剩 `table_sheet` 一项 —— 这是结构
性不可达，而不是「代码里记得别传」。守卫直接断言该集合等于 `{"table_sheet"}`（M23 falsify）。

OO build 字面量的溯源链是三处互锁，不在测试里抄字符串：

```
gate 基线 tier_a_runtime.onlyoffice_build
  == 契约 evidence.onlyoffice_build              （"9.4.0-129"）
  ⊂ Task 5 oo_build.json 的 dpkg 行             （"ii onlyoffice-documentserver 9.4.0-129 amd64 …"）
```

## 3. visible-equivalence 是真比对（R 6.17）

在**两份真实权威模板**上跑，不用手搓最小 xlsx（那六个 aspect 全是空集 ⇒ `equivalent==True` 恒真）：

* **K11**（`K/K11 资产减值损失.xlsx`）：7 sheet / ≥300 公式 / ≥40 merge，结构主线；
* **C24**（`C/C24 会计分录 - 细节测试.xlsx`）：全平台 351 个模板里**唯一**含 `xl/charts/` 的一个
  （8 chart / 3 drawing / 1 media），受保护部件这一格只能由它回答，且逐部件 digest 字节未变。

六个 aspect（可见 sheet / 业务值 / 公式 / 样式 / merge / 受保护部件）逐项 `True`，白名单只有四样
（隐藏 `_GT_SYNC` / `GT_` defined names / 受管 sheet 上一列隐藏 UUID / `headerRowCount=0` 的
Table 部件）。非空集自证由 `test_the_aspects_are_not_vacuously_equal` 承担；负对照由
`test_equivalence_is_falsifiable`（真改一个可见业务单元格）承担。

**不用字节口径**：Task 5 控制组已证 OO 往返本身会重映射 487 处填充色、替换字体、压平长公式
（不带 instrumentation 也一样），按 protected-part 字节 digest 判等会让每次 OO 保存都误判成结构
漂移。本模块的等价判定只发生在「注入前 vs 注入后」这一对**都没过 OO**的字节上。

隐藏 metadata sheet 的业务排除调用**生产函数本体**（`list_sheet_names` / `xlsx_to_univer_data`），
不是断言「代码里有 exclude 调用」；并有负对照锁住范围不得越界收进离线导入自有的 `_meta_`。

权威模板只读：跑完全部注入后重算 `backend/wp_templates/` 两份模板 sha256，与 Task 5 记录的
`dc0e5434…` / `b70229f4…` 逐字比对（R 9.9）。PG 侧同样在开工/收工各采一次。

## 4. non-current 承诺的判据（P67 / R 6.18 / 9.10）

否定式承诺**全部**由不经过被测代码返回值的判据兜住：

1. **`xmin` 逐行相等** —— `working_paper` / content_version / representation / entry_state 四张表
   的行版本事务 id 在 upgrader 跑完前后逐行相等，证明一行都没被 UPDATE。这条来自 PostgreSQL
   自身，「outcome 里的比较逻辑被改坏」不会让它假绿。
2. **全 schema uuid 列反向清扫** —— 分母是 `information_schema` 里**全部** uuid 列（实测 > 50 列），
   逐列查是否等于 candidate id / staged artifact id，允许命中位置写成白名单。未来新增表自动纳入分母。
3. **`set(ResolutionIntent)` 全枚举** —— 十个意图逐个断言 `assert_candidate_not_consumable` 恒抛，
   并且走 `resolve()` 真实路径再验一遍（前者是显式禁令 API，后者能发现「有人把 candidate 校验从
   `resolve()` 里摘掉」）。
4. **definition/bundle 按 delta 判** —— baseline 播种本身要发布一个 approved bundle，绝对计数无意义；
   判据是增量恰为 `template +1 / instrumentation +1 / contract +0 / authority_model +0 / bundle +0`。
5. **`CandidateOnlyRepository` 门面** —— representation / pointer / finalize 三个方法 + Task 15
   `REVISION_DOMAIN_WRITE_METHODS` 全集在 candidate 生成路径上不可达（取并集而非手抄清单）。
   禁令做成门面而不是「本模块没写那段代码」，就是为了让它可 falsify（M30~M33）。
6. `target_contract_definition_id` / `target_definition_bundle_id` 恒 `None`，`state` 恒
   `awaiting_contract`，`finalize` 被 Task 12 的 `assert_candidate_finalizable` 以「缺 contract」拒绝。

## 5. 变异检验：42 条，全 RED

| 文件 | 报告 |
|---|---|
| `mutation_report.json` | 全量 42 条一次跑完（M01~M42） |
| `mutation_report_m29_retry.json` | M29 修掉守卫缺陷后的复跑 |

冻结基线：`test_task17_excel_instrumentation.py` **98 passed** + `test_task17_excel_instrumentation_pg.py`
**34 passed** = **132 passed**，失败名集合空集。

判定分布（`RED` = 守卫有效 / `GREEN` = 守卫缺陷 / `WRONG-TEST` = 打红了但不是预期项 /
`ANCHOR-MISS` = 脚本缺陷）：

* 锚点自检 **42/42 OK，0 MISS**，且核验只读性（目标文件 sha256 全未变）；
* 首轮 **41 RED + 1 WRONG-TEST(M29)**；修掉 M29 暴露的守卫缺陷后复跑 **M29 → RED**；
* 合计 **42 RED / 0 GREEN / 0 WRONG-TEST / 0 ANCHOR-MISS**；
* 覆盖面 **2/2** 个登记守卫文件各被至少一条变异打红；
* 每条变异退出上下文后 sha256 逐条还原自证（`还原=True` 全部 42 条）。

落点分布：载体裁决门与 stale 门 10 条（M01~M10）· canonical payload 与发布 DAG 5 条（M11~M15）·
真实注入与可见等价 7 条（M16~M22）· identity 反读 3 条（M23~M25）· 业务 sheet 排除 4 条（M26~M29）·
candidate 非当前性 10 条（M30~M39）· 真库落库形态 3 条（M40~M42）。

## 6. 变异检验找出并已修的三个守卫缺陷

变异检验的价值不是给已有守卫盖章，而是找缺口。本轮找出三个，逐个补了**只违反它自己**的场景：

### 6.1 `assert_carrier_allowed` 的 raise 完全没有守卫（P66 的核心）

Property 66 的后半句是「任一缺失阻断 engine gate」，而这条门改成 `pass` 后**全绿**。原因：
既有守卫只改逐条 `probe_verdict`，被 `_assert_gate_matches_verdicts` 的集合相等判据拦在 `load()`
里 ⇒ `assert_carrier_allowed` 永远走不到（顺序遮蔽，与 `assert_candidate_finalizable` 的陷阱同源）。

补 `test_a_consistently_retracted_carrier_blocks_the_engine_gate`（4 个 carrier 逐个参数化）：把
`probe_verdict` 与 `gate_for_downstream_tasks.allowed_carriers` **一致地**改成「该载体已被证伪」，
于是 `load()` 合法通过、allowed 集合真的少一个，注入与 payload 两条独立入口各自必须拒绝并点名。
→ M05 现在 RED。

### 6.2 `assert_evidence_fresh` 的 digest 漂移分支没有守卫（P71）

既有守卫只走「evidence 文件不存在」那条；把内容 digest 比对删掉不会变红。Property 71 要求的是
「evidence 任一变化即失效」，缺文件与内容漂移是两条独立分支。

补 `test_tier_b_digest_drift_makes_the_gate_stale`。→ M09 现在 RED。

### 6.3 `test_exclusion_preserves_order` 是空转判据（M29 首轮 WRONG-TEST）

原用例传 `["a", _GT_SYNC, "b", "c"]`，过滤结果 `["a","b","c"]` 恰好**已是排序态** ⇒ 把
`return [...]` 改成 `sorted(...)` 它照旧全绿。首轮 M29 判 WRONG-TEST（真正打红的是两条走真实
模板的用例，而这条专职判据空转）。

改成逆序输入 `["c", _GT_SYNC, "b", "a"]` + 一组中文表名。→ M29 复跑 RED。
教训可复用：**顺序判据的输入必须与排序结果不同，否则判据不可 falsify。**

## 7. 修掉的两个真实接线错误（前一次中断留下的）

PG 守卫首跑 `8 failed`，两条都是真错，不是环境问题：

1. `snap["resolver"]["current"]` 取 `current.definition_bundle_id` —— bundle 身份挂在
   `CanonicalResolution.bundle`（Task 12 的 `DefinitionBundleSnapshot`）上，不是平铺字段 ⇒
   `AttributeError` 被 `_collect()` 记进 `snap["errors"]`，采集在此中断，后续
   `resolver.current` / `finalize_gate` / `forbidden_surface` / `source_sha_after` 四段全部没采到，
   连带 7 条用例 KeyError。**这不是 fail-open**：`test_no_harness_errors` 专门断言 `errors == []`，
   所以它如实打红了；修正为 `current.bundle.bundle_id` 并补记 `bundle_sha256`。
2. `assert gate["onlyoffice_build"].startswith("onlyoffice-documentserver 9.4.0")` —— 这个格式
   **不存在**于任何真源：gate 基线与契约记的都是 `"9.4.0-129"`，带包名的那串只出现在 dpkg 原始行里。
   改成三处互锁（见 §2），不再抄字面量。

## 8. 无效变异的三个陷阱（清单刻意避开，写下来免得下一轮重踩）

1. **删掉只在坏输入上生效的防御 = 行为不变**。删 `validate_instrumentation_payload(payload)`
   调用在合法 payload 上全绿，而这不是守卫缺陷。→ 改成**注入坏输入**（M11 往 payload 插一个
   `definition_bundle_sha256` 反向引用），让那条调用真正被逼着报错。
2. **契约里全 `passed` 的枚举做「去掉过滤器」变异是空操作**。四个 carrier 全 `passed`，
   `passed_carriers` 推导式去掉 `== "passed"` 后集合不变；anchors 侧两个是 `failed`，
   去掉过滤器集合真的变 ⇒ 这条检验只能在 anchors 侧做（M03）。
3. **`list_sheet_names` 有 calamine / openpyxl 两条分支**。本机 `python_calamine` 已安装 ⇒
   生产实际走 calamine 那条；只改 openpyxl 兜底分支会假 GREEN。故 M26 落在 calamine 分支上。

## 9. 本任务**没有**做的事（都是刻意的）

* 不创建 published/current representation、不切 entry pointer、不进 resolver/room/download/
  evidence、不递增 `content_revision`（六条各有实测判据，见 §4）；
* 不伪造 per-entry contract / authority model / definition bundle —— 由 Task 36 与 Tasks 40–57
  发布 approved child 后调用 `RepresentationService.finalize_candidate()`；
* 不依赖 Task 6、不实现 Word SDT（Excel/Word lane 保持解耦）；
* custom / user-upload 默认不 instrumentation；
* 不修改 `backend/wp_templates/` 本体（`instrument_workbook_bytes` 只吃 bytes 只吐 bytes，
  结构上碰不到模板文件；两侧还各有一次 sha256 收工核对）；
* 不读取、修改、暂存或带入 `backend/data/amount_input_migration_status.json`。

## 10. 未能验证 / 留给后续的部分

* **真实 OO 9.4 往返**不在本任务重跑：Task 17 只按 Task 5 已固化的裁决建生成器，
  identity 经真实 OO 往返的实证归 Task 5（`evidence/task5-oo94-excel-identity/`），
  逐 entry 的真实 OO gate 归 Tasks 40–45。本任务的 P66 落点是「只采用 passed 载体 + 结构上
  不可达被证伪锚点」，不是「重新证明载体能活过 OO」。
* **`finalize_candidate()` 成功路径**不在本任务：缺 approved contract/bundle 时它必须拒绝，
  这一半已验；成功一半要等 Task 36 发布 approved child。
* **`test_v151_schema_contract.py` 有 3 条既存红**（`trg_wpso_duplicate_link` 在测试建的 scratch
  schema 里不存在 ⇒ P18 / P64 的若干违规数据未被拒绝）。可复现、与 Task 17 无关：V151 迁移文件
  里该触发器出现 2 次但没被建出来，属 Task 9/10 的 schema 落地问题，本任务未改动它。
