# Task 73 evidence — source-backed entry profile 三字段收口

Task 1 的登记欠账：`editable` / `room_model` / `scenario_profile` 三个机器字段在
`backend/data/workpaper_sync_entry_manifest.json` 里**一个都不存在**，于是
`entry_profile.py` 的 RG-15/16/17 只能在手搓 fixture 上跑，对真实数据结构性不可达
（假绿第①源）。本目录是收口证据。

## 1. 命名裁决：`editability`（三值），不是布尔 `editable`

| 依据 | 结论 |
|---|---|
| V151 `working_paper_sync_test_run.editability VARCHAR(20) NOT NULL` + `ck_wpstr_editability` | 列名是 `editability`，域 = `editable/readonly/unreachable` |
| `entry_profile.PROFILE_KEYS` | `("editability", "room_model", "scenario_profile")` |
| design.md §sync_test_run 表 | `manifest_source_digest / editability / room_model / scenario_profile_digest` |
| Task 1 散文 / AC 12.12 | 用布尔 `editable` |

裁决：**磁盘上只保留 `editability`**（同时是 DB 列名与 Python 枚举名，且比布尔多带
`readonly` / `unreachable` 两个真实状态）；AC 12.12 需要的布尔由
`EntryProfile.editable` **单点派生**。守卫
`test_only_one_spelling_is_persisted` 断言 manifest / scenario_profile / 前端投影里
都不存在第二种拼写。

## 2. 三字段各自的独立事实来源（**不从 capability 派生**）

| 字段 | 独立可观测事实 | 落点 |
|---|---|---|
| `editability` | ① 宿主是否被任何生产源码引用（import 目标解析 + 模板标签用法，排除自动生成的 `*.d.ts`）② 宿主模板给挂载点传的 `readonly` 绑定形态（AST attribute 事实）③ canonical 组件自身 `readonly` prop 默认值 / `props.mode \|\| 'edit'` | `entry_source_facts.derive_editability` |
| `room_model` | ① 组件/宿主实际请求的 OO config 端点字面量（剥注释、禁跨行）② 该端点在后端**是否真有路由** ③ 路由 doc_key 表达式是否含用户成分 ④ 宿主是否存在客户端本地 doc_key 兜底 | `entry_source_facts.derive_room_model` |
| `scenario_profile` | 上述事实 + 挂载基数（`v-for` 动态 / 单例）+ room service 接线态 | `entry_source_facts.derive_entry_profile` |

`capability` 因此仍是**能真的失败**的交叉判据。反重言式有三道判据：

1. 推导函数**签名里没有** capability（`HostSourceFacts` / `ComponentSourceFacts` 不含业务裁决字段）；
2. `assert_derivation_ignores_business_adjudication()` 做 AST 传递闭包扫描，生成器在推导前无条件调用（生产消费方，不只是守卫在读）；
3. 行为判据：把 overlay 里每个 capability 都翻成另一个合法值重跑生成器（**实测 185 条 entry 的 capability 真的变了**），三字段 + provenance + `profile_source_digest` 必须逐字节不变（实测：全等）。

变异 **M01** 就是这条陷阱的实现（`entry.update({..., "room_model": "none" if capability == "single_html" else "shared"})`），必须打红。

## 3. digest 前后

| 项 | before | after |
|---|---|---|
| `manifest_digest` | `d2b1db62ad6b286a1b801f68acee8838cbb04e824296e0b91c83e311e0d4c8ea` | `67109bb81d4652e1cd32c28d2e5cf7eb4173b82504e4302a52fb4a3680c66a12` |
| `overlay_digest` | `39520b74572c9d68032291f230f66589a7c68268362a66b17a67cc98ebe98403` | `b5c6781cccf95794c18812c87b4b8ae0f1debc6104e0fa6a3ce409920a23d999` |
| `source_digest` | `b0fd31f177397d9cba4e17db485f789876b12371b5cc154e4bd55b4f9fc3443c` | **不变**（= overlay `approved_source_digest` = discovery `sourceDigest`） |
| `profile_source_digest` | 不存在 | `a75b8aa37c0e81c6e7b8180da76a4208123a8dfe98c6235a68c4247e3df6d18d` |
| `workpaper_sync_legacy_baseline.baseline_digest` | `d221f15c1b3cd659e31d66b8248cbd175b5b98837552fd8b8ef37437054181d7` | `9b0af9a61a91d0130329b2153ab912b94f2d1443727c728b7e31f5ee457df1bb`（只因内嵌 `manifest_digest` 变化重生成；其 `source_digest`、全部 flags/stats 不变） |

中途还有一次重生成（`7b5f87da…` → `67109bb8…`）：修掉 `strip_source_comments` 的
行数不守恒后，provenance 的 `#Lnn` 从整体左移 33 行纠正为真实行号（见第 7 节 M27）。

fail-closed 门未被削弱：加字段只改 `overlay_digest`（overlay 新增 `expected_profile`），
`source_digest` 与 `approved_source_digest` 的比对原样保留。

## 4. 生成事实（由生成器输出，勿复制进生产代码）

```
editability={'editable': 185, 'unreachable': 1}
room_model={'exclusive': 6, 'none': 1, 'shared': 179}
room_service_state=pending_room_service
scenario_profiles={
  'xlsx.editable.shared.single.pending_room_service.v1': 178,
  'docx.editable.exclusive.single.pending_room_service.v1': 5,
  'docx.editable.exclusive.dynamic.pending_room_service.v1': 1,
  'docx.editable.shared.single.pending_room_service.v1': 1,
  'xlsx.unreachable.none.single.pending_room_service.v1': 1,
}
```

doc_key provider 实扫（两条真实路由）：

| 端点 | doc_key 表达式 | 判定 | 探针 |
|---|---|---|---|
| `/api/workpapers/*/sheets/*/onlyoffice-config` | `_generate_doc_key(file_path, _sheet_wp_code)` → `hash(wp_code + st_mtime_ns)` | **含 mtime** | `behavioral`（真改一次 mtime 再比 key） |
| `/api/projects/*/working-papers/*/onlyoffice-config` | `f"wp-{wp_id}-{wp.file_version}-{'pf'\|'raw'}"` | 不含 mtime、不含用户 | `static_expression`（表达式内联在路由函数体，无法独立提取执行 —— 如实标注，不冒充实测） |

## 5. 「尚不可观测」的诚实表达

`rooms.derive_doc_key` / `RoomService`（Task 21）在 `workpaper_sync` 之外**零生产调用点**
（`room_service_wiring()` 实扫）。因此：

- `scenario_profile.room_service_state = "pending_room_service"`（机器可读，进 manifest digest 与前端投影）；
- `observe_room_facts()` 给 RG-17 的 `participant_lease` 恒为 `False`；
- 结果：**142 条独立可达 entry 全部 fail closed**，没有任何 entry 被手填成一个「看起来合理」的 room 事实。

Task 21 接线后 `room_service_wiring()` 非空 ⇒ `room_service_state` 自动翻转 ⇒
`manifest_digest` 变化 ⇒ 全部 evidence 自动 stale（design 的 stale policy）。

## 6. RG-15/16/17 现在真的跑在真实 manifest 上

`RegistryReport` 新增 `profile_drift` + `profile_drift_reasons`；`build_report(facts_observer=...)`
注入实测 descriptor/room 事实；唯一生产消费方 `check_workpaper_sync_closure.py` 传入
`entry_source_facts.observe_descriptor_facts / observe_room_facts`，并把
`registry_profile_drift` 登记进 `REGISTRY_ISSUE_KEYS`。

闭合门实测（`--expect-open-debt` 退出 0，默认命令退出 1 仍阻断）：

```
registry_missing_entry_profile: 0        ← 欠账已闭（此前 = 142）
registry_profile_drift: 142             ← RG-15/16/17 在真实数据上打红
total blocking facts: 836
```

逐条来源：

- **RG-15**：5 条 `capability=single_html` 的 entry 实测 `room_model=exclusive`（宿主真的挂着 OO 编辑器、doc_key 由客户端 `Date.now()` 兜底）⇒ Requirement 1.5 的「不可兑现的切换」被机器判据抓住；
- **RG-16**：176 条 entry 的宿主仍显示结构化 ↔ OO 模式切换，而裁决是 single_*；
- **RG-17**：两条不同分支同时被真实数据覆盖 —— xlsx sheet 端点走 **mtime 耦合**，`docx/wp-popup-docx-editor` 走 **缺 participant lease**。

**能红也能绿**：`test_drift_shrinks_to_the_rg15_layer_under_conformant_facts` 换一份合规
实测事实后，漂移集合必须缩到只剩 RG-15 那 5 条（否则「全红」就是不可证伪的常量）。

## 7. 变异检验：27/27 RED

- `mutation_report.json` —— 合并结果：`final_snapshot` 是修完全部缺陷 + manifest 重生成后
  **对同一棵工作树跑完 27 条**的一致快照（27/27 RED）；`diagnostic_runs` 保留首轮逐批原始
  判定，便于复核「GREEN 是怎么被归因掉的」。
- `mutation_final_{a,b,c}.json` —— 最终一致快照的三批原始输出。
- `mutation_report_batch{1,2,2b,3,4,5,6}.json` —— 诊断批次原始输出。
- 锚点自检 27/27 OK，0 MISS。

**首轮 5 条 GREEN + 1 条隐藏 ERROR 全部归因并修掉**，其中 3 条是脚本缺陷（无效变异）、
3 条是真实守卫缺陷（含 M27 那条后补的判据）：

| id | 首轮 | 归因 | 处理 |
|---|---|---|---|
| M09 | GREEN | **无效变异**：模板标签边对当前数据行为不变（185 宿主里 tag-only = 0，57 both / 127 import-only） | 改打 load-bearing 的 import 边；标签边另用合成索引判据锁住能力，并断言 tag-only 仍为 0（一旦出现就要求把 M09 改回去） |
| M10 | GREEN | **无效变异**：`if candidate.is_file()` → `if True` 时 `'./GtX.vue'` 的第一个候选本来就是正确路径 | 改成解析恒失败（`return None`） |
| M12 | GREEN(`1 error in 1.09s`) | **脚本缺陷**：`new` 写成 4 空格缩进 ⇒ IndentationError ⇒ pytest 只有 error 没有 failure，四态判定按「新增失败集合为空」判 GREEN（实为 **ERROR 态**） | 缩进对齐锚点（12 空格）；这条是「只看退出码/失败集合会把 ERROR 误判成 GREEN」的实例 |
| M13 | GREEN | **守卫缺陷**：`_assert_comment_stripping` 的探针把端点写在注释里但**没加引号**，而 `_ENDPOINT_RE` 只认引号内字面量 ⇒ 剥不剥注释都是 1 hit | 探针改成带引号的注释端点；另加真实反例判据（b60 宿主注释） |
| M14 | GREEN | 正则允许跨行的**行为**后果被 `startswith("/")` 过滤器挡住（吞出来的串以 `>` 开头） | 改用针对正则本身的判据 `test_endpoint_regex_never_spans_lines`；并在脚本里写明那个过滤器是纵深防御、单独删它行为不变 |
| M18 | GREEN | **守卫缺陷**：`pytest.raises(match="editability")` 被「过期复核值」这条消息顶上来满足了（任何写错的复核值同时也是过期值） | 判据改 match `"source facts derive"`（不符这条判据自己的措辞） |
| M27 | 首轮**没有这条变异** | **守卫缺陷**：provenance 判据只断言「文件存在 + 行号 ≥ 1」，而 `strip_source_comments` 的 `^\s*//` 把空行吃掉导致全部 `#Lnn` 左移 33 行 —— 判据照样绿 | 修生产代码（`^([ \t]*)//` + 行数守恒自检），判据升级为「那一行必须真的含该事实」，并补 M27 锁死 |

## 8. 复现命令（仓库根）

```powershell
python backend/scripts/gen/generate_workpaper_sync_manifest.py --check
python backend/scripts/gen/generate_workpaper_sync_legacy_baseline.py --check
python backend/scripts/check/check_workpaper_sync_closure.py --expect-open-debt
rtk python -m pytest backend/tests/workpaper_sync/test_task73_entry_profile_manifest.py `
  backend/tests/test_workpaper_sync_manifest_contract.py `
  backend/tests/test_workpaper_sync_legacy_baseline.py `
  backend/tests/workpaper_sync/test_task13_contract_registry.py `
  backend/tests/workpaper_sync/test_task21_room_service.py -q -p no:randomly
python backend/scripts/diagnose/mutate_task73_entry_profile_manifest_guards.py --check-anchors
python backend/scripts/diagnose/mutate_task73_entry_profile_manifest_guards.py --run all --out <report>
```

前端：

```powershell
rtk npx vitest run src/components/workpaper/sync/__tests__/workpaperSyncManifest.spec.ts `
  src/components/workpaper/sync/__tests__/workpaperSyncLegacyBaseline.spec.ts
```

## 9. 未闭合 / 交给下游

- **Task 21**：room service 接线（doc_key 去 mtime + participant lease）。在那之前 RG-17 对全部 entry 必红，这是**有意驻留**，不是待修 bug。
- **Task 25/31**：真实 `EditorLaunchDescriptor`。当前 RG-16 用的 descriptor 事实是「宿主实际 offer 了哪些视图」（Task 2 红基线的 `ui_characterization.mode_switch_visible`），descriptor 端点落地后应换成真实 descriptor。
- **本次实测顺带发现的生产缺陷**（未修，不在本任务范围）：`WorkpaperWordEditor.vue#L969` 请求 `/api/workpapers/{wpId}/onlyoffice-config`，而后端只有 `/api/projects/*/working-papers/*/onlyoffice-config` 与 `/api/workpapers/*/sheets/*/onlyoffice-config` —— **该端点没有后端路由**，`#L974` 的 `Date.now()` 兜底因此是实际生效路径（doc_key 每次打开都变）。已作为 `room_model=exclusive` 的机器事实记进 manifest（`client_local_doc_key_fallback` + `frontend_endpoint_without_backend_route` 同时进 `scenario_profile.doc_key_defects`）。
- **Task 67**：按最终源码重新生成并逐 entry 复核 manifest/profile。
