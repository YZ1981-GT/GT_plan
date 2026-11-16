# 设计：Sheet 级 OnlyOffice 改走 Published Representation

## 1. 背景与当前事实

本 spec 承接 `workpaper-html-onlyoffice-bidirectional-writeback-closure` 任务 2.8 的实测，当前不直接修改生产代码。

2026-11-16 在当前工作树 / 共享 PG 上复核到以下事实：

| 事实 | 现算结果 | 证据路径 |
|---|---:|---|
| 旧式 sheet config / WOPI / callback | `wp_onlyoffice_router.py` 仍有完整实现 | `backend/app/routers/wp_onlyoffice_router.py` |
| 旧式前端调用面 | 78 处 / 29 个非测试文件 | `tmp_spec_consumers/probe_oo_callers.py` |
| room 协议宿主 | 25 个文件已出现 materialize / confirm / room 调用 | `frontend/src/components/workpaper/sync/` 与宿主文件 |
| manifest entry 总数 | 197 | `entry_profile.load_entry_manifest()` |
| manifest capability | bidirectional 111、pending 86 | `backend/data/workpaper_sync_manifest.json` 经 `entry_profile` 读取 |
| current representation 行 | 465 | `working_paper_content_representation` 共享库只读查询 |
| `xlsx-sheet/*` manifest entry | 0 | `onlyoffice_room_identity.sheet_entry_id()` 与 manifest 逐值对照 |
| K11 entry | `xlsx/gt-k11-asset-impairment-loss`，`mount_components=['GtOnlyOfficeSheet']`，`sync_editor_host_mounted=false` | manifest entry 现读 |
| room entry 派生 | `xlsx-sheet/{wp_code}/{sheet_slug}` / `__whole__` | `backend/app/services/onlyoffice_room_identity.py` |
| 旧式文件处理 | sheet 名猜子码、模板查找、复制 OO 缓存、隐藏/恢复 sheet | `wp_onlyoffice_router.py` 的 `_resolve_wp_file`、`_hide_non_target_sheets`、`_ensure_all_sheets_visible` |

### 1.1 已验证的错误迁移方向

本轮曾验证两条看似合理但不能采纳的方案：

1. **把所有旧式 composable 改成 readiness probe**：前端没有 `wpCode`，而服务端 `sheet_entry_id` 生成的 `xlsx-sheet/*` 在当前 manifest 中为 0；probe 只能恒定 fail-open 回旧式，迁移没有行为收益。
2. **把 `wp_generation_staging._source_paths` 的主文件查找改成 `resolve_wp_file(None, wp_code)`**：真实模板库上 9/9 路径相同，但 staging 测试使用系统临时目录 monkeypatch；`resolve_wp_file` 的 Property 42 路径边界会拒绝该目录，导致 snapshot digest 不随模板字节变化、来源变更保护失效。该改动已回退。

结论：本 spec 解决的是**打开对象与身份模型**，不是把旧函数名换成新函数名。

## 2. 目标与非目标

### 2.1 目标

- 为每个可迁移的 sheet / whole workbook 入口建立显式、可审核、可生成的 `SheetOpenBinding`。
- 让 binding 指向 manifest 中真实存在的 sync entry，且 entry 的 published representation、bundle、contract 与 target sheet 可验证。
- 让 room descriptor 在同一 immutable artifact 内表达 target sheet；单 sheet 不再通过隐藏 sheet 修改文件。
- 在 binding 逐入口达到 `migrated` 后停止签发旧式 URL，并为已签发旧 doc key 提供 drain / settlement。
- 保留 pending、single_onlyoffice、Word、custom 等不适用入口的真实行为和清晰文案。

### 2.2 非目标

- 不在本 spec 内重写 Excel provider、authority model、definition bundle 或 published representation 的生产链；缺供给的 entry 交给 owner lane。
- 不把 DOCX / Word carrier 改成 Excel sheet binding。
- 不把 custom 业务文件本体强行塞进普通 Excel published artifact。
- 不结算与本 spec 无关的旧 operation；冻结 contract 的读侧重建由 `frozen-contract-read-path-and-legacy-operation-settlement` 负责。
- 不把当前 `xlsx-sheet/*` 命名空间直接当成 manifest entry；必须先完成映射设计与生成物。

## 3. 目标架构

```text
sheet request (project, wp, sheet, whole)
              │
              ▼
SheetOpenBindingResolver  ──► SheetOpenBinding
              │                         │
              │                         ├─ entry_id (manifest exact match)
              │                         ├─ source_wp_code
              │                         ├─ target_sheet / whole scope
              │                         ├─ mapping status + evidence
              │                         └─ contract/bundle requirements
              ▼
EntryReadiness + current published representation
              │
       ┌──────┴────────┐
       │               │
   blocked/pending   migrated + ready
       │               │
   legacy independent  materialize → descriptor
   OO (explicit)       → target sheet in immutable artifact
```

### 3.1 SheetOpenBinding 数据结构

先以生成 JSON 为真源，不新增数据库表；只有当真实映射需要项目存量覆盖、CAS 或多人编辑后，才另立迁移设计。

```json
{
  "schema_version": "sheet-open-binding:v1",
  "binding_id": "sha256:...",
  "entry_id": "xlsx/gt-k11-asset-impairment-loss",
  "source_wp_code": "K11",
  "document_scope": "single_sheet | whole_workbook",
  "target_sheet": "资产减值损失检查表K11",
  "sheet_key": "K11-1",
  "mapping_kind": "exact | provider | whole_workbook",
  "status": "pending | ready | migrated | draining | retired | out_of_scope",
  "manifest_entry_digest": "sha256:...",
  "contract_digest": "sha256:...",
  "bundle_digest": "sha256:...",
  "source_refs": ["file.py#Lx", "template.xlsx!Sheet1"],
  "owner": "lane/spec",
  "reason": null
}
```

约束：

- `entry_id` 必须逐值存在于当前 manifest，且 `effective_entry_id` 解析后仍在 manifest。
- `target_sheet` 是 artifact 内的 sheet 名，不是磁盘路径，不允许由请求期正则猜出。
- `whole_workbook` 是 document scope，不得把某个子码当整册 artifact。
- `provider` mapping 必须由 provider 提供稳定的 resolver identity 与测试样例；路由层只调用 resolver，不解析模板目录。
- 生成器输出需同时包含 `binding_id` 与输入 digest，避免映射文件被手工改后静默生效。

### 3.2 生成与读取

新增生成器（暂定 `backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py`）：

1. 读取 `workpaper_sync_manifest`、reviewed overlay、provider 的 `wp_match` / sheet declarations；
2. 读取目标 entry 的 document type、capability、mount 与 published supply 事实；
3. 对 exact / whole workbook 记录确定映射；对动态 sheet 只能记录 provider resolver，不写运行时正则；
4. 无法证明唯一映射时生成 `pending` 记录和 typed reason；不能生成一条看似成功的父级兜底；
5. 产出 `backend/data/workpaper_sync_sheet_open_bindings.json`，支持 `--check` 幂等。

运行时 `SheetOpenBindingResolver` 只读该生成物并校验 source digest。它不读 `wp_templates` 目录来猜结果，也不直接读取前端组件源码。

## 4. 服务端打开流程

### 4.1 entry-identity 端点的目标修正

当前已存在的 `GET /api/projects/{project_id}/workpapers/{wp_id}/sync/entry-identity` 不能继续直接调用 `sheet_entry_id()` 后拿结果去查 readiness，因为当前 manifest 没有 `xlsx-sheet/*` entry。

新实现应改为：

1. 项目 / 底稿权限与软删校验；
2. `SheetOpenBindingResolver.resolve(wp_id, sheet_name, whole_workbook)`；
3. binding 缺失 / 多义 / stale 时返回 200 的结构化 `pending` 或 409 typed reason，不能伪造 `xlsx-sheet/*` entry；
4. binding 成功后调用 `evaluate_entry_readiness`，返回 `entry_id`、`effective_entry_id`、`room_ready`、`allowed_modes`、`reason` 与 representation identity；
5. 只有 `migrated + runtime.ready` 才允许 room materialize。

### 4.2 Published artifact 读取

迁移后的 sheet 打开必须通过：

- `resolve_visible_current_representation_id(session, entry_id=...)`；
- `WorkpaperContentRepresentation` 的 published/current identity；
- `CanonicalArtifactRepository` / `ArtifactStorageLayout` 的 canonical path boundary；
- definition bundle、contract、adapter identity 的冻结校验。

迁移路径禁止：

- `find_template_file_any` 作为当前文件来源；
- `_resolve_wp_file` 复制 OO 缓存；
- `shutil.copy2` 生成本次编辑文件；
- `_hide_non_target_sheets` / `_ensure_all_sheets_visible` 改写 artifact；
- 从客户端传入 path、file name、doc key 作为信任身份。

### 4.3 Target sheet / whole workbook

Published artifact 必须保留完整 workbook 字节。单 sheet 视图通过 descriptor 的 target sheet / `actionLink` 定位；whole workbook 不传 target action，打开同一 artifact 的所有合法 sheet。两种视图必须使用同一个 representation generation，不得复制出两个文件名相同但内容不同的缓存。

如果某个 artifact 内没有声明的 target sheet：

- 不通过名称相似度兜底；
- 返回 `target_sheet_not_in_published_artifact`；
- binding 保持 pending，并记录 artifact digest、target sheet 与实际 sheet 列表摘要。

### 4.4 URL 与回调

`WorkpaperSyncEditorHost` 只消费 `EditorLaunchDescriptor`。descriptor 的 `document.url` / `callbackUrl` / room credentials 由 room 服务端按同一 room、generation、entry 签发。旧 `/wopi/contents` 与 legacy callback 只能服务 `pending` / `draining` binding，不得被 migrated binding 的新请求引用。

## 5. 前端改线策略

### 5.1 不把旧 composable 直接改成假 room

当前 22 个 composable 没有 `wpCode`，且现有 room manifest 没有 `xlsx-sheet/*` entry。它们不能简单调用 readiness 后显示 room。新 spec 的前端改线顺序是：

1. binding endpoint 返回真实 `entry_id` 后，统一 `onlyOfficeEntryConfig` / readiness helper 改读 binding；
2. migrated binding 由 `WorkpaperSyncEditorHost` 挂载 descriptor；
3. pending binding 明确显示「独立在线编辑（不同步）」并保留旧式 fallback；
4. legacy composable 逐个删旧端点调用，守卫按 binding 状态允许的调用面检查。

### 5.2 组件边界

- `GtOnlyOfficeSheet` 只作为 pending / single_onlyoffice / custom / out_of_scope 的兼容组件。
- `WorkpaperSyncEditorHost` 只承载 published artifact + room descriptor。
- `onlyOfficeEntryConfig.ts` 只做 binding/readiness 预检，不做 materialize；materialize、confirm、forcesave 继续由 `useWorkpaperSyncBridge` 负责。
- 迁移过程中不得同时渲染两个编辑器；旧组件 unmount 与新宿主 mount 必须由同一状态机控制。

## 6. Legacy Drain 与删除

### 6.1 分阶段状态

`pending → ready → migrated → draining → retired`。每次晋级保存 binding digest、representation generation、browser evidence id 与操作者。

- `pending`：映射或供给未完成，允许独立 OO，但文案不得声称双向。
- `ready`：映射和供给已就绪，先在候选环境跑 required scenarios。
- `migrated`：新请求只签 room descriptor，不再签旧 URL。
- `draining`：已签出的旧 doc key 在 TTL / grace 窗口内可以完成；不产生新旧 key。
- `retired`：旧 config / WOPI / direct callback 对该 binding 返回 typed 410/409，不再写文件。

### 6.2 回滚

全局 `ONLYOFFICE_LEGACY_URL_ISSUE` 只能作为紧急总开关，不能替代 binding 状态。回滚只允许把尚未 retired 的 binding 从 `migrated` 退到 `draining` / `pending`，并记录原因；已经 retired 的旧 callback 不得通过开关重新启用无绑定 direct-write。

## 7. 验证设计

### 7.1 静态与生成物

- manifest / binding / route / host 闭合检查；
- `--check` 幂等；
- migrated binding 的生产路径不出现 old config / WOPI / direct-write 调用；
- `entry_id`、target sheet、document scope 逐值双向对账。

### 7.2 后端

- binding resolver：唯一、缺失、多义、stale、跨项目、target sheet 缺失；
- current representation：published / candidate / missing / digest drift；
- room descriptor：target sheet、whole workbook、room/generation/doc key 一致；
- legacy drain：旧 token TTL、旧 callback 不越权、不写错误 artifact；
- PG：只读路径、权限、representation 选择与审计回执。

### 7.3 前端与浏览器

至少覆盖：

1. 普通单 sheet：HTML → descriptor → target sheet → forcesave → HTML 回读；
2. whole workbook：所有 sheet 可见、目标 sheet 不丢、切回 HTML 后数据一致；
3. 聚合包 source sheet：映射到独立 entry，不回退父级模板；
4. pending / single_onlyoffice / custom：旧入口仍能用，但文案是独立在线编辑且没有双向成功态；
5. migrated 入口：网络中不再出现 old `onlyoffice-config` / `wopi/contents` / legacy callback；
6. drain：已打开旧编辑器能在窗口内完成，窗口后新请求被拒并给中文原因。

## 8. 风险与裁决点

| 风险 | 处理 |
|---|---|
| 一个 sheet 既可映射父 entry 又可映射子 entry | manifest 生成阶段报 ambiguity，不在请求期猜 |
| Published artifact 的 sheet 名和 UI 名不同 | binding 显式保存 `target_sheet`，不按相似度匹配 |
| 旧式模板副本含业务未发布修改 | 迁移前逐 entry snapshot / hash；migrated 只读 published artifact |
| custom 文件没有 published representation | 保持 out_of_scope / single_onlyoffice，另立 custom lane |
| 旧 operation 冻结旧 contract | 交给 `frozen-contract-read-path-and-legacy-operation-settlement`，本 spec 不重组历史 operation |
| 全局 78 处旧调用一次性切换风险 | binding 逐入口 rollout + drain + metrics，禁止大爆炸替换 |

## 9. 完成门

只有以下条件全部成立才允许归档：

- binding 生成物可重算、无未解释 ambiguity；
- 至少一个普通 sheet、一个 whole workbook、一个聚合 source sheet 真浏览器闭环通过；
- migrated binding 的旧 URL 新签发数为 0，drain 后 direct-write 为 0；
- current published artifact 与 HTML / API 回读逐值一致；
- 变异守卫证明删除映射、candidate 冒充 current、恢复 template copy、绕过 target sheet、legacy callback 放行都会打红；
- clean checkout 三件套、生成器、路由注册、后端 / 前端测试均通过；
- 更新 umbrella 2.8 的余项状态，并在 INDEX 登记后再归档本 spec。
