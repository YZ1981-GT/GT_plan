# ACNR 目录贡献指南（双入口铁律）

> 适用范围：`backend/data/acnr/` 下的 ACNR（地址坐标名称注册中心）目录数据。
> 权威依据：spec `.kiro/specs/acnr/`（Requirement 18、20）与架构蓝图
> `docs/proposals/address-coordinate-name-registry-architecture.md`（v1.10）。
> 里程碑：本文档随 M0 创建（对应 R18.2）。

## 0. 一句话铁律

**ACNR 目录（`global_catalog.json`）只能通过两个入口写入：**

1. **生成器入口**：改 catalog 源数据 → 跑 `generate_catalog.py` 重新生成。
2. **overrides 入口**：在 `global_catalog.overrides.json` 打补丁（必须带 `reason` + `owner`，建议带 `expires_at`）。

**禁止第三套手写副本。** 任何绕过这两个入口、手工编辑 `global_catalog.json`
或在其他模块另起一份"地址表 / sheet 名映射 / 坐标清单"的做法，都会被 CI 阻断或在评审中打回。

平台历史上正因为**四套并行寻址体系**（五域 URI + `WP()` 公式、V1 运行时目录、
V2 静态语义图、索引命名空间）互不解析、各自维护副本而漂移失控。ACNR 的核心命题就是
**一格一 `addr_id`、四库共用一个 `resolve()`**。手写第四套副本 = 让漂移复活，绝对禁止。

---

## 1. 为什么是"双入口"

| 入口 | 面向场景 | 数据落点 | 是否入版本库 |
|------|----------|----------|--------------|
| **生成器** | 常规、批量、来自权威源（classification / I/E manifest / 坐标种子 / labels / render_registry）的变更 | 直接体现在重新生成的 `global_catalog.json` | ✅（生成产物 diff 可见） |
| **overrides** | 权威源暂时无法覆盖、需要人工临时修正的少量条目（项目模板差异、紧急补名等） | `global_catalog.overrides.json`，由生成器在合并阶段叠加 | ✅（补丁文件 diff 可见） |

两个入口的共同点：**产物始终是可 diff 的提交物**，CI 能对它做漂移校验与唯一性校验。
被禁止的"第三套"恰恰是那些**不可追溯、不经生成器、不经 CI 校验**的手写副本。

---

## 2. 入口一：生成器流程（首选）

### 2.1 权威源（生成器输入）

`generate_catalog.py` 只读以下 6 类输入源（**不自动扫描 71 个 I/E py**，见蓝图 §13.11 误操作清单）：

| 源 | 路径 / 来源 | 贡献内容 |
|----|-----------|----------|
| classification | `workpaper_sheet_classification`（DB/API） | 全量 `SheetCatalogEntry` 骨架（100% 覆盖） |
| I/E manifest | `backend/data/acnr/sources/{cycle}_cycle_ie_manifest.yaml` | `import_export` 段（首期先 D 循环） |
| 坐标种子 | `backend/data/*_address_registry_seed.json`（13 文件） | `CellCatalogEntry`（473 坐标） |
| 前端 labels | `audit-platform/.../{cycle}*SheetLabels.ts`（14 文件） | `sheet_name_aliases`（只 ingest，不反写） |
| render_registry | `workpaper_render_registry` | `component_type` + `upstream/downstream`（L4 第 6 边源） |
| overrides | `global_catalog.overrides.json` | 人工补丁（入口二，见 §3） |

> **权威源铁律（R-NAME / R20.2）**：`sheet_name` 冲突时，一律以
> `workpaper_sheet_classification` 为权威源。要改一个 sheet 的权威中文名，
> **改 classification**，不要在别处硬写。

### 2.2 操作步骤

```powershell
# 1) 修改对应的权威源
#    - 改 sheet 名 / 分类 → 改 classification（DB）
#    - 改 import/export 路由 → 改 backend/data/acnr/sources/{cycle}_cycle_ie_manifest.yaml
#    - 加坐标 → 改对应 *_address_registry_seed.json
#    - 加别名 → 改前端 *SheetLabels.ts

# 2) 重新生成 catalog（确定性：同输入 → 字节一致输出）
python backend/scripts/acnr/generate_catalog.py

# 3) 检查产物 diff
rtk git diff backend/data/acnr/global_catalog.json
rtk git diff backend/data/acnr/catalog_report.json

# 4) 提交源改动 + 生成产物（两者必须同一次提交，否则 CI drift 报红）
```

### 2.3 生成产物

| 产物 | 说明 |
|------|------|
| `backend/data/acnr/global_catalog.json` | L1 catalog 主产物（含 `registry_version`） |
| `backend/data/acnr/shards/catalog_{cycle}.json` | 按循环分片（可选，懒加载） |
| `backend/data/acnr/catalog_report.json` | 冲突 / 缺口 / 未登记别名报告——**每次生成后必看** |

### 2.4 合并规则要点

- classification + I/E manifest + 坐标种子 + labels 别名 → 合并为
  `SheetCatalogEntry` 与 `CellCatalogEntry` 两类条目。
- `skip_reason` 非空的 sheet：写入对应条目，并**完全阻止本次 bulk manifest 生成**
  （不是仅跳过该 sheet，R1.4）。
- 别名一对多冲突（一个别名映射多个 sheet_code）：CI 在合并前标为缺口并
  **阻断该别名进入 catalog**；阻断优先于缺口标记（R3.3–R3.5）。

---

## 3. 入口二：overrides 补丁

当权威源暂时无法覆盖、又需要人工临时修正少量条目时，走 `global_catalog.overrides.json`。

### 3.1 必填字段

每条补丁**必须**注明来源与责任人，避免"永久临时补丁"：

```yaml
# global_catalog.overrides.json（示意，JSON 形态）
project_id: "..."            # 若为项目级 overlay
addr_id: "D2/D2-2"
overrides:
  sheet_name_alias_add: ["现场临时叫法"]
reason: "项目模板差异，classification 尚未同步"   # 必填：为什么需要补丁
owner: "zhangsan"                                  # 必填：谁负责，将来谁来清理
expires_at: "2026-12-31"                           # 建议：到期复核，防永久滞留
```

| 字段 | 是否必填 | 作用 |
|------|----------|------|
| `reason` | ✅ 必填 | 记录补丁存在的理由，供评审与将来清理判断 |
| `owner` | ✅ 必填 | 责任人；补丁不是"匿名后门" |
| `expires_at` | ⚠️ 强烈建议 | 到期复核；临时补丁应回流到生成器权威源后删除 |

### 3.2 overrides 的定位

- overrides 是**临时/例外通道**，不是常规通道。能改权威源就改权威源。
- 补丁最终应"回流"：当 classification / manifest / seed 补齐后，删除对应 override。
- overrides 同样是可 diff 的提交物，同样受 `check-addr-id-unique` 等 CI 守卫约束。

---

## 4. 禁止事项（第三套副本铁律）

以下行为**一律禁止**，会被 CI 阻断或评审打回：

1. ❌ **手工编辑 `global_catalog.json`**。它是生成产物，只能由 `generate_catalog.py` 写。
   手改会立即触发 `check-acnr-catalog-drift`（生成器重跑后 diff 不为空 → 阻断 PR）。
2. ❌ **在其他模块另建"地址表 / sheet 名映射 / 坐标清单"副本**。所有消费者
   （公式管理库 / 高级查询库 / 索引库 / 附注库）必须经 `resolve()` / `/api/acnr/*`
   读取，不得各自维护本地映射。
3. ❌ **新增 `[A-I]\d` / `[A-S]\d` 标准码判定的重复正则副本**。标准码判定唯一常量为
   `grammar_v1.json` 的 `STANDARD_WP_CODE_RE`，由 `wp_render_config.py` 与
   `wp_index_resolve.py` 共同 import（`check-standard-wp-code-re-single` grep-ban 守卫）。
4. ❌ **手改生成的 `*SheetLabels.ts`**（M2 起生成物，`check-sheet-labels-generated` 守卫）。
5. ❌ **消费者自拼 `wp_code + sheet + cell` 字符串或自拼 jump_route**。
   一律通过 `addr_id` / URI 引用，跳转用 `resolve()` 返回的 `jump_route`（五层引用铁律 R7）。
6. ❌ **修改已存在的 `addr_id`**。改 addr_id 属破坏性变更，须新 addr + 迁移映射表；
   sheet 改名走 `sheet_name_aliases`，删坐标标 `deprecated:true` 并保留至少一版
   `registry_version`（R19）。

---

## 5. CI 守卫（自动把关）

双入口铁律由以下 CI 守卫强制执行（蓝图 §13.5）：

| 守卫 | 检测内容 | 启用里程碑 | 需求 |
|------|----------|-----------|------|
| `check-acnr-catalog-drift` | 生成器产出与已提交 `global_catalog.json` 一致（不一致阻断 PR） | M0 | R18.3 |
| `check-addr-id-unique` | 全局 `addr_id` 无重复（含 overrides 叠加后） | M0 | R18.4、R24.4 |
| `check-ie-catalog-sync` | `*_cycle_ie_manifest.yaml` 与 catalog `import_export` 段一致（先 D 循环） | M0 | R18.5 |
| `check-standard-wp-code-re-single` | grep-ban：阻断新增 `[A-I]\d` / `[A-S]\d` 副本 | M0 | R12.3 |
| `check-ccr-resolve` | 每条 CCR source 可 resolve 或标 `semantic_only` | M1 报告 / M3 blocking | R17 |
| `check-sheet-labels-generated` | 禁止新增手改 `*SheetLabels.ts` | M2 | R18 |

### drift 检查本质

```
generate_catalog.py && git diff --exit-code global_catalog.json
```

只要你手改了 `global_catalog.json`（或改了源却忘了重跑生成器），CI 重跑生成器后
`git diff` 非空即阻断 PR。这就是"手写副本无处遁形"的机制保证。

---

## 6. I/E 路由铁律（R-ROUTE / R18.6）

导入导出（bulk manifest）路由**只认 catalog 的 `api_prefix` + `item_id`**，
不认任何硬编码路径。要改一个 sheet 的导入导出路由，改
`{cycle}_cycle_ie_manifest.yaml` 后重跑生成器，不要在 py 里另写。

---

## 7. 提交自查清单

提 PR 前逐项确认：

- [ ] 变更走的是**生成器**还是 **overrides**？（不能是手改 `global_catalog.json`）
- [ ] 若走生成器：源改动与重新生成的 `global_catalog.json` 在**同一次提交**里。
- [ ] 若走 overrides：`reason` + `owner` 已填，`expires_at` 已考虑。
- [ ] 看过 `catalog_report.json`，无未处理的冲突/缺口/未登记别名。
- [ ] 没有新增第三套地址副本、没有新增 `[A-S]\d` 重复正则、没有手拼 jump_route。
- [ ] 没有修改已存在的 `addr_id`（改名走 aliases，删除走 deprecated）。
- [ ] 本地 `check-acnr-catalog-drift` / `check-addr-id-unique` 通过。

---

## 8. 规则冻结引用（M0，R20）

双入口铁律对应冻结规则 **R-ENTRY**（只许生成器或 overrides 入口）。相关冻结规则：

- **R-URI**：五域 URI 语法不变。
- **R-ADDR**：addr_id 格式与不可变政策。
- **R-WP**：`WP()` 2 参与 3 参并存互转。
- **R-NAME**：sheet_name 权威源 = classification。
- **R-ROUTE**：I/E 路由只认 `api_prefix` + `item_id`。
- **R-ENTRY**：只许生成器或 overrides 入口（本文档）。

以上规则于 M0 冻结并归档决议，后续实现以此为统一依据。
