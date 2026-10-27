# D2 模板骨架槽位复用 + 双向回写提速 — Design

## §1 现状 grep 确认（动手前逐项核对）

| 事实 | 位置 | 对设计的影响 |
|---|---|---|
| orphan = projection 声明而 substrate 无物理行的身份；插入点 `max(row_identity_by_row)+1` | `excel_materialize.plan_managed_writes` 6.2 / `_plan_row_shift` | 复用在 6.2 之后、`_plan_row_shift` 之前消化 orphan；`_plan_row_shift` 只用 `len(orphan)`，不改 |
| 骨架身份永不当 stale（`is_template_skeleton_identity`） | 同上 6.2b | 复用行不会同时进收敛分支 |
| `_emit` 在 `projection.get(key) is None` 时直接返回 | 同上 `_emit` | 复用行要另补「清空」写入，否则模板示例文字留在格里 ⇒ roundtrip `extra`（身份已声明，不豁免） |
| roundtrip 只豁免「骨架身份 ∧ 未声明」的多出字段 | `content_mutation.assert_roundtrip_equivalent` | 不改；复用行由「写值或清空」保证无 extra |
| 身份保留门 `expected.row_uuids − observed ≠ ∅` 即抛 | `excel_extract.assert_identity_inventory_retained` | 同一次提交的 roundtrip extract 用的是 **base** 定义 ⇒ 必须显式豁免本次退役的骨架身份 |
| 物化后唯一的 extract-on-output 调用点 | `ContentMutationService._stage_cpu_segment_scoped` | 退役清单只在这里传入 extract |
| 新代际 adapter 的身份清册由观测器从新 artifact 现算，与 representation 冻结 digest 对账 | `published_identity_observer` / `target_bound_registration` | 提交后的读取天然不含退役身份，无需持久化退役清单 |
| 单趟物化在任一 binding 需插行时 decline | `materialize_projection_single_pass` | 「只复用不插行」会走单趟 ⇒ 两条路径都要带出退役清单 |
| 逐趟链式路径以主 binding 结果 `dataclasses.replace` | `adapters/excel.ExcelSyncAdapter.materialize` | 新字段随主 binding 结果自动流出 |
| provider 声明 → 框架解析的先例 | `oo_crash_neutralization.resolve_oo_crash_neutralization_fn` | 同款：provider 声明、框架经台账解析、声明了却取不到即 fail-closed |
| D2 模板骨架基线（R12 已有） | `pilot_d2_large_json.template_skeleton_baseline` / `template_skeleton_baseline.SkeletonBaseline` | 复用判「模板原样」直接用它，不另写判据 |
| `_archive/44` P1 等价论证依赖「全量物化不动骨架身份」 | `business_identity.py` | 复用只在有 orphan 时发生 ⇒ 此时 projection 必与基线不等、P1 不命中；对已物化产物再物化同一 projection 无 orphan ⇒ 不动点仍成立 |
| 契约字段会改契约 digest、迫使 bundle 重发布 | `backend/data/workpaper_sync_contracts/*.json` | 启用声明放 provider 模块常量，不进契约 |

## §2 槽位复用算法（纯函数，住 `skeleton_slot_reuse.py`）

```
candidates = { row: id | id 是骨架身份 ∧ baseline.carries_user_content(该行非受保护字段) 为假 }   # 物化前在 substrate 上算
last_declared = max(row | physical[row] ∈ wanted)，没有则 0
free = sorted(row ∈ candidates | row > last_declared ∧ candidates[row] ∉ wanted)
adopted = zip(orphan, free)                 # orphan 按声明序，槽位按行号升序
orphan' = orphan − adopted                  # 剩余照旧交给 _plan_row_shift
```

- 「只在最后一个已声明行之后」保证不把新行排到已有业务数据上方（store 行序不被打乱）。存量底稿（数据在 25~524、骨架在 13~24）因此**不会**被引擎就地改形，走 §5 刷新。
- candidates 用零参可调用对象延迟计算：没有 orphan 时不读模板、不遍历 substrate 投影。
- 复用行的写入：UUID 列写 store 身份；`_emit` 照常写 projection 有的字段；projection 没有的非受保护字段若格内有值则写 `blank`（与收敛清空同一写入形态）；受保护格不动。

## §3 退役身份的流转

`MaterializePlan.retired_row_identities`（非空时才进 `as_dict`）→ `MaterializeResult.retired_row_identities`（默认 `()`）
→ `_stage_cpu_segment_scoped` 仅在非空时以关键字传 `adapter.extract(..., retired_row_identities=...)`
→ `ExcelSyncAdapter.extract` 只给主 binding → `extract_projection` → `assert_identity_inventory_retained`：
豁免集 = 传入集 ∩ 骨架身份形态（非骨架身份传进来也照样判丢失）。

## §4 启用声明

provider 模块常量 `SKELETON_SLOT_REUSE_TABLE_KEYS`（本 spec 只给 D2-2 `receivable_detail_rows`）+ 既有 `template_skeleton_baseline()`。
框架按 `contract.contract_id` 经 `DELIVERED_PER_ENTRY_CONTRACTS` 取 provider 模块；声明了表却没有可调用的基线函数 ⇒ 抛
`SkeletonSlotReuseDeclarationError`（不静默退回不复用）。D2-3 两区的骨架行带「其中：」标签行，属版式内容，本 spec 不启用。

## §5 存量底稿刷新工具

`backend/scripts/fix/republish_entry_from_template.py --wp-id <id> [--entry-id …] --check|--apply`：
按底稿取 current representation（`working_paper_sync_entry_state`），`resolve_rehash_plan` → `stage_instrumented_substrate`
→ `publish_first_generation`（store 全部 item 由 provider `all_store_item_ids()` 给出）→ commit。
`--check` 报告当前代际、受管表首个业务行行号、store 字节数、是否有未结束的在线编辑房间；有房间时拒绝 `--apply`。

## §6 OO→HTML 回写可见（R4）

先实测：OO 改格后点「结构化视图」，看网络是否有 `POST …/forcesave`。只见 `…/leave` 即坐实「`dirty` 已被 OO 状态事件复位 ⇒
`leaveWithoutSaving()`」；修法是会话内出现过编辑就走保存路径（CS 回 `no_changes` 视为干净关闭）。实测正常则不改前端。

## §7 提速（R5，`_archive/44` P4 的落地）

- `parse_cache` 新键：`contract_id + contract.canonical_sha256 + adapter 提取口径摘要 + artifact sha`，只认 `ExcelSyncAdapter` 精确类型。
- `extract_three_way`：base 走缓存；current 与 base 同 sha 直接复用对象（journal 照记）；incoming 不缓存。
- 提交成功后把 roundtrip `extracted` 按发布 artifact sha 写入缓存（失败路径不写）。
- 守卫：命中与冷提取逐字段相同；同 contract_id 不同 canonical 内容键不同。实施前后各测一次真实耗时，收益不足则如实记录。

## §8 拒绝方案

- D2 专用 openpyxl 直写脚本：丢 x14 数据验证、footer 冻结键失配、绕开 revision / room / 历史，且不覆盖其余 entry。
- `substrate_prepare_fn` 预处理钩子：复用路径会绕过它，且会在 substrate 上伪造身份。
- 就地改 artifact：artifact 内容身份列不可变（DB 约束），representation sha 必须等于 artifact sha。
- 删除骨架行：删插共存不支持（6.8b 降级）、触发身份保留门、违背「删行逐表 opt-in」铁律。
- 引擎自动搬移存量数据行到骨架槽位：属行重排，现有判据（行序 / 位移声明）不覆盖；一次性数据修复用 §5 工具。

## §9 测试

- 纯函数：候选（模板原样 / 用户填过 / 未知骨架）、复用（全空模板 3 行 / 20 行 / 部分已占 / 存量布局不复用 / projection 声明了骨架行）。
- 真链路（新 instrument 的 D2 模板）：物化 → 首个业务行 = 13、剩余插在 24 之后、roundtrip 等值、未管理区域等价、保留门豁免只覆盖退役集；未启用表逐字节不变。
- 变异：去掉豁免 ⇒ 保留门红；去掉清空 ⇒ roundtrip extra 红；去掉「最后已声明行之后」⇒ 存量布局用例红。

## §10 实施记录（2026-10-23）

### R1~R3

- 证据：`test_skeleton_slot_reuse.py` 17 例 + 磁盘变异 4/4；34 个相关文件 HEAD 对比零新增失败（59 条共同预存）；golden digest 242 不变；行数门过。
- 重药安徽 D2 刷新：gen 11→12、rev 17→18、首个业务行 25→13。浏览器：B13 = 万春街道新苑社区卫生服务一站，A512 = 500，A513 = ……，A514 = 合计，E514 = `=SUM(E13:E513)`。
- 和平药房两份 D2 待用户确认后再刷新。

### R4 实测抓到的 4 处平台缺陷（均已修）

| 缺陷 | 修法 | 守卫 |
|---|---|---|
| OO 的 `onDocumentStateChange(false)` 把 dirty 复位 ⇒ 回表单只发 leave、编辑丢失，下次打开弹「备份副本」 | 桥 `notifyDirty` 只认 true；命令受理 / CS `no_changes` / 会话结束才清零（一处改动覆盖全部宿主） | `sessionEditsStickyDirty.spec.ts` 4 例 + 变异 3/3；同目录 17 条失败与 HEAD 一致 |
| 回调下载地址 `localhost` 解析到 `::1`，`[::1]:8080` 报 WinError 10013 ⇒ 10-21 起 status 2/6 回调全部被拒 | `callback_download._open_first_reachable`：只在连接失败时、只在已校验的地址间回退（不重新解析，SSRF 口径不变） | `test_callback_download_address_fallback.py` 4 例 |
| 落盘前拒收不结算 ⇒ forcesave 请求永久 frozen ⇒ leave 409 | `callback_reject_settlement`：只对 forcesave，shell → rejected、request → terminal（文档服务不重发） | task22 PG 用例 + 变异 2/2 |
| `verify_unmanaged_regions` before-digest 缓存键缺区域（预存，真链路 3→20 行顺序复现） | 键加 `table_ref@uuid_column` 与扫描行 | 真链路用例 |

### R6 重开在线编辑

- 根因：OO→HTML 应用（merged == incoming）推进 room 快照、同代不换 doc_key；participant 的确认行不可变、停在打开时那版。leave 只要没落地（在途请求 409 / 网络 / 关标签页），lease 4 小时内被复用 ⇒ 确认新基线撞「不得用不同基线二次确认」。
- 修法：`confirmation_rebase.is_rebase_onto_room_baseline` —— 新 descriptor 的 (representation, content version, projection) 等于 room 快照且 revision 严格前移 ⇒ 旧确认 `invalidated_at`，插入新确认；其余仍 409。
- 守卫：`test_reconfirm_on_advanced_baseline_pg.py` 6 例；变异 5/5（恒 False / 恒 True / 去 revision 前移 / 去 projection 比对 / 不作废旧确认）；room / confirm / materialize / oo_to_html 13 个 PG 套件 661 例，6 红均为 task28 缺 `ONLYOFFICE_JWT_SECRET`，HEAD 同红。
- 浏览器：rev 19、rev 20 两次「leave 未落地后重开」都在 8 s 内进入编辑且是最新内容（C13 先为 SLOT-C13-T4，回退后为空），无备份副本弹窗；无改动回表单只发 leave（200，4.5 s）。
- 测试编辑已回退：store 500 行，与测试前只差 row1 `companyCode` `''` → `None`（R17 OO 清空写显式 null，语义等价）。

### R5 实测与结论

- 安静环境一次保存（`[sync-timing] oo_to_html_apply`）：共 16.4 s = base 提取 1.77 + current 0.91 + incoming 1.91 + 合并 1.83 + CPU 段 9.46 + 其余 0.5。
- 三方提取合计 4.6 s，base/current 去重最多省 0.9 s（约 5%）；主耗时在 CPU 段（物化 + 反读 + 未管理区域校验）。按 §7 末句「收益不足如实记录」未实施，CPU 段拆分另立 spec。
- 已知限制：apply 进程中途被杀（实测是并发会话反复触发热重载）时，平台没有重驱机制，靠文档服务重发回调续跑（这次 operation 108 s，apply 本体 25.8 s）；重发前用户等待，超 180 s 前端提示「重试回写」。

### 勘误（2026-10-23 下午，随 `workpaper-sync-save-path-cpu-hotspots` 的 179 文件对比发现）

上文「34 个相关文件 HEAD 对比零新增失败」的范围太窄。扩到 179 个相关文件（含 store 直通与删行归一化的 PG / 单测）后，本 spec 的改动多出 3 条失败，均已修复并加守卫：

| 失败 | 根因 | 修法 |
|---|---|---|
| `test_store_materialize_pg` 两例（首版后同 store 再开，复用判「内容变了」、指纹直通不命中） | 复用的骨架行里，store 没给值的公式格保留了模板缓存的 `<v>0</v>`，反读成该行的值；首版记下的 projection 没有这个键 | 新写入形态 `cached_value_cleared`：保留 `<f>`、去掉 `<v>`，与新插入行的公式格同形；守卫 `test_adopted_rows_keep_formulas_but_drop_the_template_cached_values`，变异 2/2 |
| `test_row_deletion_verify_normalisation` 缓存键用例 | 本 spec 给 before-digest 键追加的两段排在塌陷集合之后，用例按末段断言塌陷集合 | 两段挪到塌陷集合之前（内容不变，只换顺序） |

真实影响：重药安徽 / 和平药房的 store 行都带公式列的值（HTML 侧已算好），走的是写缓存值分支，所以浏览器实测没有暴露；store 不带公式列值的底稿（新增空行、导入）会受影响。

### 和平药房刷新（2026-10-23 下午）

- 2024 D2（`1cf770c2…`）此前从未发布在线编辑版本（`--check` 报 blocked、store 756 行、0 个骨架身份）。浏览器打开即走首次发布（17.9 s），按新模板物化：B13 = 中国联合网络通信有限公司重庆市分公司（store 第 1 行），A768 = 756，A770 = 合计，E770 = `=SUM(E13:E769)`；store 摘要 `5357e611…` 前后不变。
- 2025 D2（`ef7f88e3…`）：`--apply` 后 gen 8→9、rev 51，但首个业务行仍是 25。store 741 行的末尾 12 行（第 730~741 行）带骨架身份 `GTROW-D22-0013..0024`，只有模板示例文字（单项计提 / 组合1~4 / 组合X / 客户类型组合 / 非关联方），没有客户名和金额 —— 槽位被这 12 行「占着」，真实业务行排在其后。store 摘要 `dad04d88…` 前后不变。删除这 12 行要用户确认，删后再跑一次 `--apply`。
- 同项目 D3-det-rows、D5-2-rows、D6-2-rows（12/12）、H1-8-rows 的 store 也只有骨架身份行（本 spec 范围外，只记录）。

### R5 转交

提速改由 `workpaper-sync-save-path-cpu-hotspots` 实施：根因是逐格编译正则 + 三处逐键扫模板 + 重复提取 + 事件循环阻塞（不是 CPU 段本身不可压缩）。结果：离线 CPU 链 14.07 → 6.69 s，浏览器保存回表单 20.5 → 13.0 s，见该 spec design §8。
