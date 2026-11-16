# 任务：Sheet 级 OnlyOffice 改走 Published Representation

> **状态：9/34（2026-11-16，Phase 0.1~0.3、1.1~1.2、2.1~2.4 已完成；产品代码仍未迁移已就绪 binding）**
>
> 本 spec 必须在现状事实冻结后再改生产代码。所有 `[ ]` 都是必做任务；外部依赖不能标绿，必须写明 owner、证据和下一步。

## Phase 0：事实冻结与范围裁决

- [x] 0.1 固化旧式调用面：现算 backend 三个旧端点、前端 78 个调用 / 29 个文件，按 host、composable、Word、custom、single_onlyoffice 分组。
  - 产物：`evidence/legacy-sheet-onlyoffice-callers.json`（raw string mentions 81/30，去掉本 spec 新增唯一 helper 与共享声明后的 direct call baseline 78/29）。
  - _R: 4, 5, 6_
- [x] 0.2 固化 manifest / entry / representation 事实：现算 manifest entry、capability、`xlsx-sheet/*` 命名空间、current representation、mount host 与 room host。
  - 产物：`evidence/entry-and-representation-baseline.json`；共享 PG 行数只作 snapshot，不是永久门槛。
  - _R: 1, 2, 8_
- [x] 0.3 逐入口列出 sheet→entry 候选映射，分为 `exact` / `provider` / `whole_workbook` / `ambiguous` / `out_of_scope`。
  - 不得把当前 `sheet_entry_id()` 生成的 `xlsx-sheet/*` 直接当作已存在 entry。
  - 产物：`evidence/sheet-binding-adjudication.json`；首批候选为 K11 provider mapping 与 D4 aggregate source-sheet mapping，custom/Word 明确 out_of_scope。
  - _R: 1, 5_
- [ ] 0.4 完成五角色范围复核：合伙人确认打开对象与业务含义，项目经理确认 rollout，质控确认不伪造双向，审计助理确认界面文案，EQCR 确认历史 operation / artifact 审计边界。
  - _R: 5, 6, 10_

## Phase 1：SheetOpenBinding 真源与生成器

- [x] 1.1 定义 `sheet-open-binding:v1` JSON schema 与封闭枚举：scope、mapping_kind、status、reason、source_refs、digest。
  - 守卫拒绝缺 entry、缺 source digest、重复 binding、未知 status 与裸正则；`test_sheet_open_bindings.py` 现算覆盖。
  - _R: 1, 8_
- [x] 1.2 实现 `generate_workpaper_sync_sheet_open_bindings.py`：从 manifest、reviewed overlay、provider `wp_match` / sheet declarations 生成 binding。
  - 提供 `--apply` / `--check`；内容不变重跑零 diff；当前生成 197 条 binding，全部保持 `pending` 或 `out_of_scope`，不伪造迁移完成。
  - _R: 1, 8_
- [ ] 1.3 为 exact / provider / whole workbook 分别建立正向与反向 fixture；provider resolver 必须有稳定 resolver identity。
  - _R: 1, 9_
- [ ] 1.4 把 ambiguous / no target / no entry / stale digest 作为显式 pending reason，不得生成父级兜底映射。
  - _R: 1, 5_
- [ ] 1.5 生成 `backend/data/workpaper_sync_sheet_open_bindings.json` 与 source manifest，加入 clean checkout 入库守卫。
  - _R: 1, 8, 10_

## Phase 2：服务端解析与 Published Artifact 读取

- [x] 2.1 重构 `/sync/entry-identity`：由 `SheetOpenBindingResolver` 返回真实 manifest `entry_id`，删除对不存在的 `xlsx-sheet/*` entry 的直接假设。
  - 兼容旧响应字段，但新字段必须含 mapping status、target sheet、representation identity；route 级测试覆盖 pending provider mapping 不伪造 entry。
  - _R: 1, 3_
- [x] 2.2 把 sheet readiness 接到 binding 后的 effective entry；缺 mapping 时返回 200 pending 或 typed 409，不能把 EntryReadinessNotFound 当成 room ready。
  - `SheetOpenBindingResolver` 在 entry 缺失、provider 未审核、exact 多义时均返回 pending；端点测试证明不会生成 `xlsx-sheet/*` 虚假身份。
  - _R: 1, 3, 7_
- [x] 2.3 新增 published artifact reader：通过 current representation id、bundle、contract 与 canonical artifact layout 读取文件，禁止模板 copy / hidden-sheet mutation。
  - 实现 `services/workpaper_sync/sheet_published_artifact.py`：`current pointer → representation/artifact row → canonical visibility/path → sha256/size → OOXML target sheet` 五步固定顺序，任一步失败即抛 typed error，**不回退模板**。
  - 接线 `/sync/entry-identity`：只有 `ready` / `migrated` binding 才读 artifact（`pending` 走不通，防未审核入口被当可开）。
  - 守卫 4 例（reader）+ 4 例（endpoint，含 pending 不读 / ready 读 / target_sheet 传参）；变异 M1 门控恒假、M2 门控恒真、M3 去 target_sheet 传参**全部精确打红**。
  - 🔴 M2 首轮存活：pending 用例原先只断言「不抛」，而端点 `except Exception` 把断言吞成 pending ⇒ 改为**记录调用并断言为空**。这是「断言必须落在观测到的副作用上」的又一实例。
  - _R: 2, 7_
- [x] 2.4 descriptor 增加 target sheet / document scope 的冻结字段；单 sheet 使用 actionLink，whole workbook 保持完整 artifact 视图。
  - 实现 `services/workpaper_sync/descriptor_view_identity.py`（封闭域 + 归一化 + 组合约束）；`EditorLaunchDescriptor` 增 `target_sheet` / `document_scope` 两字段并纳入 `DESCRIPTOR_REQUIRED_FIELDS`；route 与 store service 均把 `resolve_launch_target_sheet` 的结果冻结进 `MaterializeRequest`。
  - 21 例守卫（`test_sheet_descriptor_view_identity.py`）：构造期封闭域 7 例、归一化 4 例、route/service 装配 AST 7 例、阴性对照 3 例。
  - 变异 11/11 全精确打红（含 `M1` 去 target、`M2` scope 字面量、`M3` 整册带 target、`M4` 枚举加宽、`M5a/M5b` 两处 route scope、`M6` store 丢 scope、`M7` 不转发 target、`M8` 归一化忽略 scope、`M9` 用原始 request 值、`M10` 去封闭域校验），零假红。
  - 🔴 首轮 5/6 存活：初版判据只查**字段存在性**（`target_sheet=None` 也能构造成功）⇒ 补「构造点实参表达式」与「被调方收到什么」两层 AST 判据才承重。这是「字段存在 ≠ 值正确」「测了被调函数一层，测不到调用方传没传参」的第三、第四层。
  - 🔴 顺带修 task 2.1 遗留的真回归：前端契约生成器只认 `USER_SYNC_PREFIX`，把兄弟前缀上的 `entry-identity` 判成「缺 scope 段」而整体 `raise` ⇒ 改为认**全部显式 scope 前缀**并投影 `prefixKind` / `WP_SYNC_SIBLING_PREFIX_TEMPLATE`；`task28` 的 6 条守卫同步（等价鉴权判据 `authorize_wp_read` 而非放宽白名单）。
  - 行数门：抽出 `descriptor_view_identity.py` 后 `materialize_coordinator` 3508 / `wp_sync_router` 3638 / `test_task28` 1957 全部回到门内（未抬白名单）。
  - _R: 3, 8_
- [ ] 2.5 为 target sheet 缺失、candidate、bundle drift、artifact missing、artifact digest drift 建 typed error 与中文原因。
  - _R: 2, 3, 7_
- [ ] 2.6 为 migrated binding 停止签发旧 config / WOPI / callback；pending / out_of_scope 保留独立在线编辑并在响应标明不同步。
  - _R: 4, 6_

## Phase 3：前端宿主切换

- [ ] 3.1 把 `onlyOfficeEntryConfig.ts` 改为读取真实 binding，不再把 `xlsx-sheet/*` 作为 entry 身份；保留 readiness / legacy fallback 的明确三态。
  - _R: 1, 4, 6_
- [ ] 3.2 为 `WorkpaperSyncEditorHost` 增加 target sheet / whole workbook descriptor 接线；不得在业务 composable 自己调 materialize 或拼 callback URL。
  - _R: 3, 4_
- [ ] 3.3 迁移一个普通 single-sheet canary，从 `GtOnlyOfficeSheet` 切到 room host；记录 old URL、descriptor、target sheet 与 HTML 回读证据。
  - _R: 3, 9, 10_
- [ ] 3.4 迁移一个 whole-workbook canary；验证所有 sheet 可见、target sheet 正确、切回 HTML 不丢写。
  - _R: 3, 9_
- [ ] 3.5 迁移一个聚合 source sheet；验证映射到子 entry，不回退父级模板。
  - _R: 1, 3, 9_
- [ ] 3.6 更新 pending / single_onlyoffice / custom / Word 的前端文案与入口门控；不得显示“双向回写”假状态。
  - _R: 4, 5, 6_
- [ ] 3.7 宿主闭包守卫：迁移 binding 的所有旧 `onlyoffice-config` 调用为 0；未迁移调用逐条存在 ledger、owner 与 reason。
  - _R: 4, 6, 10_

## Phase 4：Legacy Drain 与旧路径删除

- [ ] 4.1 将全局 legacy 开关收敛为 binding 级状态机：pending → ready → migrated → draining → retired。
  - _R: 6, 8_
- [ ] 4.2 新增旧 doc key / callback drain ledger：记录签发时间、TTL、binding、entry、generation、终结状态。
  - _R: 6, 7, 8_
- [ ] 4.3 migrated binding 的新请求不得签旧 URL；draining 只接受已签发且 scope / token / generation 全匹配的 callback。
  - _R: 6, 7_
- [ ] 4.4 旧 direct-write 分支按 binding 逐个删除；删除前守卫要求旧签发数、callback in-flight、drain timeout 连续为 0。
  - _R: 2, 6, 10_
- [ ] 4.5 删除无调用方的 `GtOnlyOfficeSheet` 兼容代码前，完成 grep 0 调用、测试全绿、独立提交与回滚标签；single/custom/Word 豁免必须有真实条件断言。
  - _R: 4, 5, 6_

## Phase 5：测试与真实验收

- [ ] 5.1 后端 unit / contract：mapping 唯一性、scope、target sheet、current representation、candidate 拒绝、path boundary、typed error。
  - _R: 1, 2, 7_
- [ ] 5.2 后端 PG：真实 `WorkpaperContentRepresentation`、bundle、artifact 读取与项目隔离；只读验证先独立事务，写入验收只用【测试】项目并可恢复。
  - _R: 2, 7, 9_
- [ ] 5.3 前端 unit / AST：唯一 URL、唯一 binding resolver、migrated 旧调用为 0、pending 文案与模式集合封闭。
  - _R: 1, 4, 6, 10_
- [ ] 5.4 变异：删 mapping、伪造 parent fallback、candidate 冒充 current、恢复 template copy、去掉 target sheet、绕过 legacy token、让 old callback 无条件写入均必须 RED；阴性对照 GREEN。
  - _R: 1, 2, 3, 6, 10_
- [ ] 5.5 Playwright：普通 sheet / whole workbook / 聚合 source sheet / pending fallback / drain 五条 required scenarios；记录网络、console、页面错误、数据快照与 artifact identity。
  - _R: 3, 4, 6, 9, 10_
- [ ] 5.6 clean checkout：生成物 `--check`、后端测试、前端定向测试、构建、路由注册、行数门与 git tracked 交付物检查。
  - _R: 8, 10_
- [ ] 5.7 更新 umbrella 2.8 的余项状态、INDEX、memory 与归档证据；只有完成门满足后归档本 spec。
  - _R: 10

## 依赖图

```text
0.1~0.4
   │
   ▼
1.1~1.5  ─────► 2.1~2.6
                    │
                    ▼
                 3.1~3.7
                    │
                    ▼
                 4.1~4.5
                    │
                    ▼
                 5.1~5.7
```

## 当前明确不做的事

- 不在本 spec 中修 `wp_generation_staging._source_paths` 的 `multi_resolver`：它依赖 staging 是否应受 Property 42 canonical path boundary 约束，需单独裁决；当前错误替换已回退，原有 4 行 writer debt 保持真实。
- 不把当前 78 个旧式调用按文件机械替换；只有 binding 成为 `migrated` 后才允许迁移，pending 继续标独立在线编辑。
- 不修改当前工作树中其它会话的 frozen contract、OO template parity、published identity observer 等脏文件；本 spec 的任务按 clean candidate tree 执行。


## Umbrella 交接边界（2026-11-16）

本 spec 是 `workpaper-html-onlyoffice-bidirectional-writeback-closure` 2.8 中「sheet 级旧入口与 published artifact 打开语义」的后续承接者。它不把原 umbrella 的未完成项自动标绿：

- 本 spec 承接：SheetOpenBinding、真实 manifest entry、published artifact、target sheet / whole workbook、前端宿主切换、legacy drain 与相应 sheet 级浏览器场景。
- 本 spec 不单独宣称完成 umbrella 6.3 的全部 entry required scenarios；全量 bidirectional entry 的 operation / evidence 账本仍需后续 owner 按原 umbrella 口径闭合。
- 本 spec 不单独宣称完成 umbrella 7.5；五角色最终复核、clean-checkout 总验与最终归档必须在本 spec 及相关 residual owner 的证据齐备后执行。
- 原 umbrella 的 `_source_paths` resolver debt 仍保持真实，需先裁决 staging 是否应纳入 Property 42 canonical path boundary，不因本 spec 的 sheet 映射而自动关闭。
