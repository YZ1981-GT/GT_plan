# Design Document

## Overview

本设计把「底稿导入导出全生命周期收口」拆成**五层**，每层的判据真源与守卫形态先定死，再谈实现顺序。

**立项需求文档的量化台账在本轮独立复算中被推翻 7 处**（连库直查 `working_paper` / `checklist_responses`、枚举真实 `app.routes`、扫 `create_cycle_import_export_router` 工厂调用、读 ACNR catalog）。逐条对照见 §核心事实修正。修正后的关键结论有两条方向性改变：

- **缺陷 A 的严重性被夸大，但性质更糟**：`checklist_responses` 不是「131 份 / 1,034,515 行有内容」，而是 **131 份有行 / 全库仅 695 行非空**（103.3 万行是 `conclusion` 与 `remark` **双 NULL** 的空骨架，单份 C24 底稿独占 1,033,230 行）。所以「把 checklist_responses 全量倾倒进导出」不仅会淹没有效内容，量级上根本不成立。真正的语义是：**非空行里 300 行是 JSON 数组、126 行是 JSON 对象、269 行是纯文本**，即录入数据是**以 JSON 载荷寄存在 `remark`/`conclusion` 文本列里的**（最长单行 181,056 字符）。导出要接的不是「行」，而是**每个 `item_id` 的 JSON 载荷**。
- **场景④不是「零端点」，而是「已建成一整套但前端没接」**：`backend/app/services/bulk_tab/` 有 **14 个模块 / 约 15.6 万字符**，`wp_bulk_router.py` 有 **11 个端点**（`preview-manifest` / `export-templates` / `export-data` / 两个 async / `export/{task_id}/download` / `import` / `import/async` / `import/{task_id}/result` / `import/rollback` / `progress/{task_id}`），带 `ZipAssembler`（sha256 + manifest.json + README）、`bulk_import_service`（拓扑序回传 + `conflict_resolver` + `snapshot_guard` + `workflow_gate`）、`bulk_async_runner`（进度上报）。四场景所需的骨架**基本齐备**，缺的是 UI 入口、归档时点接线与语义标注。

据此，本 spec 的设计主线从「重造」彻底转为**接线 + 止损 + 真源统一**：

```
止损（产物自证）→ 数据源接通（JSON 载荷而非行）→ 统一入口（复用 bulk_tab）
   → registry 真源换成 ACNR catalog → 断开模板库引用
```

### 核心事实修正（立项台账 → 本轮实证）

| # | 维度 | 立项需求文档 | 本轮实证（判据） | 对设计的影响 |
|---|---|---|---|---|
| 1 | `checklist_responses` 有内容底稿 | 131 份 / **1,034,515 行** | 131 份有行，**非空仅 695 行**；`conclusion`/`remark` 双 NULL 达 **1,033,715 行**；单份 C24 占 1,033,230 行 | R2.4 的「全量倾倒会淹没」判断方向对，但量级错；清单 sheet 必须按 **item_id 的 JSON 载荷**组织，不是按行 |
| 2 | 录入数据形态 | 「行含 `item_id` / 值 / 结论 / 备注」 | 非空 695 行里 **JSON 数组 300 / JSON 对象 126 / 纯文本 269**；`wp_ref` 全库 **0 条**非空；`max(len(remark))=181,056` | R2.2 的列定义（`item_id`/值/结论/备注）对纯文本行成立，对 JSON 载荷行**结构上不成立** ⇒ 需两态渲染 |
| 3 | 后端 `*_import_export.py` 模块数 | 102 个 / 87 个 wp_code | **99 个**（`backend/app/routers/wp_render_strategies/`），其中 **63 个零 `@router.` 装饰器**（走工厂），**62 个** `create_cycle_import_export_router(api_prefix=...)` 调用、prefix 全唯一 | 「87 个 wp_code」不是真源；真源是 **ACNR catalog** 的 `import_export.enabled` 段 |
| 4 | 三态端点规模 | 各 36 组 / 合计 314 个 | 真实 `app.routes` 共 **2288** 条，导入导出相关 **308** 条（`export-template` 106 / `export-data` 102 / `import-data` 100），按前缀分 **87 组**、其中 **81 组三态齐全** | registry 目标不是「87 个 wp_code」而是「**81 组齐全前缀**」，且须扣掉 `{wp_id}` / `{wp_code}` 这类**路径参数误计** |
| 5 | 孤儿 composable | 10 个（含 `useG13`/`useG14`） | **11 个**：`useG13`/`useG14` 确实零消费方，但**多出 `useF1ImportExport`**（F1 已在 registry 却是孤儿）；`useG13`/`useG14` 的现有 import 只出现在 **spec 测试文件**里 | R5.1 清单要改（10→11）；且暴露一条新缺陷模式：**registry 登记了 ≠ composable 被消费** |
| 6 | 场景④（归档导出） | 「11 个 archive 模块中零端点」 | archive 模块确为 11 个且确无底稿正文导出，但 **`bulk_tab` 有 14 模块 + `wp_bulk_router` 11 端点**完整覆盖模板/数据/回传/回滚/进度 | R3.6 从「新建」改为「**接线 + 归档时点门控**」 |
| 7 | `file_path` 指向模板库 | 1670 `template_fallback` / 120 份指向 `wp_templates` | 全库 2802 份：`file_path` **空 1564 份**、指向 `wp_templates/` **956 份**（其中 90 份确有 `checklist_responses` 行）；`A1x` 系列 6 条路径各被 **4 个项目**共享 | R6 的迁移面是 **956 份**（不是 120），空路径 1564 份属 R1 自证而非 R6 迁移 |

> 🔴 上表每条都可复算：#1/#2/#7 = `mcp_postgres` 只读直查；#3 = 扫 `wp_render_strategies/` 源码 AST；#4 = `app.routes` 枚举后按倒数第二段分组；#5 = 按 **import 路径**（非符号名）反查消费方；#6 = 目录实扫 + router 装饰器枚举。

## Architecture

### 五层与依赖

```
L1 产物自证（止损层，不依赖任何其他层）
   ├─ resolve_wp_file verdict 自证（R1.1 / 1.3 / 1.7）
   ├─ export-xlsx 空 html_data 自证（R1.2 / 1.8）
   └─ _未导出清单 覆盖 template_fallback（R1.4 / 1.5 / 1.6）
        ↓ 独立可交付，先上线
L2 导出数据源接通（依赖 L1 的自证文案真源）
   ├─ checklist_responses JSON 载荷读取（R2.1 / 2.2）
   ├─ 附加 sheet 而非改写模板单元格（R2.3 / 2.5 / 2.6）
   └─ 上限截断 + 来源标注（R2.7 / 2.8）
        ↓
L3 四场景统一入口（复用 bulk_tab，不新造）
   ├─ 三态端点语义标注（R3.1 / 3.2 / 3.3 / 3.4）
   ├─ 模板↔数据错用校验（R3.5）
   ├─ 归档时点门控（R3.6 / 3.8）
   └─ UI 四场景语义可辨（R3.7）
        ↓
L4 registry 真源换血（ACNR catalog 单一真源）
   ├─ CYCLE_IMPORT_EXPORT 从 catalog 派生（R4.1 / 4.3）
   ├─ apiPrefix 双向锁死（R4.2 / 4.4 / 4.5）
   ├─ 既有 10 key 零回归（R4.6）
   ├─ 显式登记表（R4.7）
   └─ 11 个孤儿处置（R5 全部）
        ↓
L5 断开模板库引用（破坏性迁移，最后做）
   ├─ 首写前复制到项目存储（R6.1 / 6.6）
   ├─ wp_templates 只读守卫（R6.2）
   └─ 幂等 + 可回滚 + 逐条隔离（R6.3~6.5 / 6.7 / 6.8）
        ↓
L6 守卫 / CI / 验收（R7 全部）
```

**关键依赖**：

- **L1 必须早于 L2**：自证文案的单一真源（`VERDICT_LABELS`）要先扩出「结构化录入未写入 xlsx」这一档（R1.8），L2 才有地方挂「已接通但本份无录入」的区分。
- **L4 必须早于 L5**：迁移会改 `file_path`，而 registry 守卫要用「迁移前的 verdict 分布」作对照基线（R6.7）。顺序颠倒会让基线本身漂移。
- **L3 依赖 L2**：场景③要标注「哪些列来自四表取数、哪些可编辑」（R3.3），这个列级元数据由 L2 的载荷读取层产出。
- **L5 是唯一破坏性层**，须显式确认参数（R6.8），且放在全部守卫就位之后。

### 判据真源表

| 维度 | 真源 | 读取方式 | 禁止 |
|---|---|---|---|
| 自证文案 | `wp_file_resolver.VERDICT_LABELS` | import | 调用方硬写中文字面量（R1.3） |
| verdict 取值域 | `wp_file_resolver.WP_FILE_VERDICTS` | import | 字面量 `'template_fallback'` 散落 |
| 自证行布局 | `export_engine._build_failure_fallback_workbook` 范式（第 1 行原因 / 第 2 行空 / 第 3 行起数据） | 复用同一 helper | 各写一份行号 |
| 录入数据 | `checklist_responses.(conclusion, remark)` 按 `(wp_id, item_id)` | 读**两列**并按 JSON/文本两态解析 | 只读一列；假定是结构化行 |
| I/E 路由元数据 | **ACNR catalog** 的 `import_export` 段（`api_prefix` / `item_id` / `storage_field` / `import_order` / `depends_on_sheets`） | `acnr.catalog.list_sheets(import_export_only=True)` | 从 `*_import_export.py` 动态提取（ACNR 铁律 R18.6/R-ROUTE 已明令禁止） |
| 真实端点集合 | `app.routes`（运行期） | 启动 app 后枚举 + 按倒数第二段分组 | 数源码里的 `@router.` 装饰器（63 个模块零装饰器，会漏 2/3） |
| sheet 键 | catalog 的 `sheet_code`；G0 另有 `_SHEET_NAME_MAP` 键 | 读 catalog / 读后端 map 键集 | 凭 wp_code 推断（`G0-3S` 反例） |
| 批量四场景骨架 | `bulk_tab/`（`manifest_builder` / `bulk_export_service` / `bulk_import_service` / `zip_handler`）+ `wp_bulk_router` | 复用 | 新写第二套 |
| 孤儿判定 | **import 路径**（非符号名），且须递归到「有渲染宿主」 | 扫 `.vue`/`.ts` 的 import 语句 | 符号名 grep（只产生假阴性，R5.5） |
| 模板库只读 | `backend/wp_templates/` | 迁移前后哈希比对 | 只查代码不查磁盘 |

### 为什么 registry 真源必须换成 ACNR catalog

立项需求文档把目标写成「registry 覆盖后端已有 `*_import_export.py` 的全部 wp_code」（R4.1），本轮实证显示这个判据**结构上做不到**：

1. **99 个模块里 63 个零 `@router.` 装饰器** —— 它们的端点由 `create_cycle_import_export_router(tag=, api_prefix=, specs=)` 在导入期生成。想从源码「数出」它们的 sheet 键，必须解析工厂调用的 `specs` 字典字面量，而这些字典分散在各模块顶部的 `_Kx_x_HEADERS` / `_Kx_x_KEYS` 常量里 —— 这正是 memory 记的「grep 式守卫」反模式。
2. **catalog 与后端工厂 prefix 双向都有缺口**：catalog 独有 30 个前缀（`d1`~`d7` / `f0`~`f3` / `g0` / `g4-*` / `g6-*` / `g7-*` / `g8` / `h0` / `h10` / `k0`），后端工厂独有 32 个（`h5` / `h7` / `h9` / `i1`~`i6` / `l1`~`l8` / `m1`~`m10` / `n1`~`n5`）。**两侧都不是全集**。
3. **ACNR 已被 `bulk_tab` 全链采信**：`manifest_builder.build_manifest` → `wp_bulk_tab_export.list_export_sheets` → `acnr.manifest.list_import_export` → `acnr.catalog.list_sheets`，且 catalog 不可用时**抛 `AcnrCatalogUnavailableError` 而非静默降级**。前端 registry 若不同源，等于平台内并存两套 I/E 目录。

**设计结论**：`CYCLE_IMPORT_EXPORT` 不再手写，改为**构建期从 ACNR catalog 生成**（或运行期拉取 + 构建期守卫锁死）。后端工厂独有的 32 个前缀属 **catalog 缺口**，是本 spec 要补的 catalog 数据，而不是让前端去抄第二份清单。这条同时把 R4.2/4.3/4.4/4.5 四条 AC 从「两份字面量互相比对」降级成「一份真源 + 一条派生守卫」。

## Components and Interfaces

### C1 自证层共享件（L1）

新建 `backend/app/services/wp_export/self_evidence.py`，把散落的自证逻辑收成单一出口：

```python
#: 自证档位 —— 扩展 verdict 之外的两档「已就绪但内容未落 xlsx」
SelfEvidenceKind = Literal[
    "verdict",              # 来自 resolve_wp_file 的四档
    "html_data_absent",     # verdict=file 但 html_data 缺 sheet 键
    "entry_not_in_xlsx",    # verdict=file + html_data 空 + checklist 有行（R1.8）
]

def build_self_evidence_banner(
    *,
    kind: SelfEvidenceKind,
    verdict: str | None = None,
    detail: str = "",
) -> str:
    """产出自证首行文案。文案只取 VERDICT_LABELS + 本模块 _KIND_LABELS，
    调用方一律不得硬写中文（R1.3）。"""

def stamp_self_evidence(ws, banner: str) -> None:
    """按 `_build_failure_fallback_workbook` 既定范式落盘：
    第 1 行 banner（加粗标红）/ 第 2 行留空 / 第 3 行起数据（R1.7）。"""
```

**关键约束**：`verdict == 'file'` 且 `html_data` 非空时**不得调用**（R1.6 禁给正常导出加噪声）—— 判据放在调用方的一个纯函数 `needs_self_evidence(...) -> SelfEvidenceKind | None`，便于守卫直测。

### C2 录入载荷读取层（L2）

新建 `backend/app/services/wp_export/entry_payload_reader.py`。**它不是「读行」，而是「读 item_id 的载荷并判形态」**：

```python
@dataclass(frozen=True)
class EntryPayload:
    item_id: str
    shape: Literal["json_array", "json_object", "plain_text", "blank"]
    rows: list[dict] | None      # json_array 解析结果
    obj: dict | None             # json_object 解析结果
    text: str | None             # plain_text 原文
    source_field: Literal["conclusion", "remark"]
    raw_len: int

async def read_entry_payloads(
    db, wp_id, *, row_limit: int = ...,
) -> tuple[list[EntryPayload], int]:
    """返回 (载荷列表, 被截断条数)。

    · 双列都读：`conclusion` 与 `remark` 各自可能承载 JSON（实测两者都在用）
    · 全空行剔除（R2.4）—— 实测 1,033,715 / 1,034,515 行双 NULL
    · 形态判定：strip 后首字符 `[` → 试 json_array；`{` → 试 json_object；
      解析失败降级 plain_text（不抛，不静默丢）
    · 上限保护（R2.7）：按**总字符数**与**条数**双阈值，实测单行可达 181,056 字符
    """
```

**清单 sheet 渲染两态**（R2.2 与实测形态的冲突解法）：

| 载荷形态 | 渲染 | 理由 |
|---|---|---|
| `json_array`（300 行） | 每个 `item_id` 一个区块，首行 `item_id` + 来源列名，其下按数组元素的键集展开成表 | 这是真正的「结构化录入」，列名取载荷自身的键，不硬写 |
| `json_object`（126 行） | `item_id` + 键值两列纵向列出 | 对象无天然行概念 |
| `plain_text`（269 行） | `item_id` / 值 / 来源列 三列 | 与 R2.2 的原始设想一致 |

R2.2 要求的列含 `item_id` / 值 / 结论 / 备注 —— **「结论/备注」在实测里是同一份载荷的两个候选存放列，不是两个业务字段**。设计上改为标注 `source_field`（`conclusion` 或 `remark`），并在 sheet 内写明该列语义（R2.8 的「数据来源」即由此列承担）。这处偏离 AC 字面，须在 tasks 里显式登记裁决。

### C3 四场景统一入口（L3）

**不新建后端能力**，只做三件事：

1. **语义标注层**：新建 `backend/app/services/bulk_tab/scenario_registry.py`，把四场景与既有端点绑定成声明式表（单一真源，前端读它渲染 UI，不各写一份中文）：

```python
@dataclass(frozen=True)
class ScenarioSpec:
    key: Literal["blank_template", "fill_back", "refresh_edit", "archive_export"]
    label: str                  # 中文场景名
    产物说明: str                # UI 直接展示，禁前端硬写
    适用时点: str
    endpoint: str               # 复用既有 wp_bulk_router 路径
    mode: Literal["template", "data"] | None
    direction: Literal["export", "import"]
    archived_allowed: bool      # R3.8：归档态是否可用
```

2. **模板↔数据错用校验**（R3.5）：ZIP 内 `manifest.json` 已有 `mode` 字段（`manifest_builder` 实测写入 `mode: template|data`）。导入侧读 `mode` 并与目标场景比对，不符则返可读错误。这是**零新增存储**的做法 —— manifest 已经带了这个字段，此前只是没人校验。
3. **归档态门控**（R3.8）：接既有 `bulk_tab/workflow_gate.py`（已存在，7809 字符），在导入路径加归档态判据；导出路径不加。

**场景③的列级标注**（R3.3）由 L2 的载荷读取层配合 ACNR catalog 的 `formula_ref` 产出：来自四表取数的列在 catalog 里有 `formula_ref`，可编辑列没有。这是**已有元数据的复用**，不新增声明。

### C4 registry 派生与守卫（L4）

- 新建 `audit-platform/frontend/src/components/workpaper/shared/cycleImportExportRegistry.generated.ts` —— 由脚本从 ACNR catalog 生成（含 `apiPrefix` / `sheets[]` / `itemId` / `storageField`）。
- `cycleImportExportRegistry.ts` 保留为**门面**：`CYCLE_IMPORT_EXPORT = { ...generated, ...MANUAL_OVERRIDES }`，其中 `MANUAL_OVERRIDES` 只放 catalog 表达不了的（如 G0 的 `G0-3S` 传输键）。既有 10 key 的行为由 characterization 守卫钉死逐字节不变（R4.6）。
- 新建 `EXEMPT_IE_PREFIXES` 显式登记表（R4.7）：每条含 `prefix` / `reason` / `evidence` / `stale_check`。
- 守卫 `cycleImportExportRegistry.spec.ts` 扩为**三向**：catalog ↔ generated ↔ 真实 `app.routes` 快照。

### C5 孤儿处置（L4 / R5）

11 个孤儿按**三类**处置，判据是「后端端点是否仍被别的入口覆盖」：

| 孤儿 | 后端 prefix 状态 | 建议处置 | 理由 |
|---|---|---|---|
| `useF1ImportExport` | `f1` 在 registry **且**有 3 态端点 | **接线或删** | F1 已在 registry ⇒ 下拉能用 ⇒ 该 composable 是重复实现，倾向删 |
| `useG13ImportExport` / `useG14ImportExport` | `g13`/`g14` 三态齐全，且 `G13TabDetail.vue` / `G14TabDetail.vue` **已挂 `CycleImportExportDropdown`** | **删** | 能力已由 dropdown 覆盖，composable 是并存的第二条路 |
| `useH5` / `useH7` / `useK12` / `useK5` / `useL4` / `useK1Writeoff` | 后端工厂有 prefix，但 **catalog 缺** | **接线**（补 catalog + 挂 dropdown） | 这些是真缺口：后端能力存在但用户不可达 |
| `useK0` / `useL0` | `k0` 在 catalog（2 sheet）；`l0` 三态齐全但 catalog 缺 | **接线** | 函证模块跨循环共享（memory 铁律），须走 D0 共享组件 |

**递归判据**（R5.6）：孤儿基线守卫要判「有渲染宿主」，而非「被 import」。`useG13`/`useG14` 当前唯一 import 方是 **spec 测试文件** —— 这正是「被 import 但仍是孤儿」的活样本，守卫必须把 `__tests__/`、`*.spec.ts` 排除在「消费方」之外，否则基线永远清不掉。

### C6 模板库解引用迁移（L5）

新建 `backend/scripts/fix/fix_wp_template_deref.py`：

```
--check    统计现状（预期：956 份指向 wp_templates，其中 90 份有 checklist 行）
--dry-run  逐条打印将复制到的目标路径 + 冲突检测
--apply --confirm-destructive   实际执行
--rollback <ledger.json>        按台账回滚
```

- **复制目标**：`storage/projects/{project_id}/workpapers/{wp_code}_{wp_id前8}.xlsx`（每项目独立副本，满足 R6.6 的「4 个项目共享同一路径 ⇒ 各得独立副本」）。
- **台账**（R6.3）：`{wp_id, old_path, new_path, sha256_before, sha256_after, ts}` 落 JSON，回滚只按台账反写 `file_path`，**不删新文件**（避免回滚本身造成数据丢失）。
- **幂等**（R6.4）：`file_path` 已不指向 `wp_templates/` 即跳过；二次执行零变更。
- **逐条隔离**（R6.5）：单条异常记入 `failed[]` 继续，末尾汇总。
- **verdict 分布对照**（R6.7）：迁移前后各跑一次 `resolve_wp_file` 全量统计并 diff。
- **只读断言**（R6.2）：迁移前后对 `backend/wp_templates/` 递归取 `(相对路径, size, sha256)` 快照，逐条相等。

**空 `file_path` 的 1564 份不在本迁移范围** —— 它们没有可复制的源，属 R1 自证层（`verdict='empty'`）的作业面。这条边界必须写进登记表，否则下轮会有人把 1564 份也算成「迁移遗漏」。

## Data Models

### 探针 SQL（守卫与验收脚本共用口径）

```sql
-- 两套存储的交集（缺陷 A 的判据）
WITH cr AS (
  SELECT wp_id,
         COUNT(*) AS rows_all,
         COUNT(*) FILTER (
           WHERE COALESCE(NULLIF(TRIM(conclusion), ''), NULLIF(TRIM(remark), '')) IS NOT NULL
         ) AS rows_nonblank
  FROM checklist_responses GROUP BY wp_id
),
hd AS (
  SELECT id AS wp_id
  FROM working_paper
  WHERE is_deleted = false
    AND parsed_data ? 'html_data'
    AND parsed_data->'html_data' <> '{}'::jsonb
)
SELECT
  (SELECT COUNT(*) FROM cr WHERE rows_nonblank > 0)                        AS cr_nonblank_wps,
  (SELECT COUNT(*) FROM hd)                                                AS html_wps,
  (SELECT COUNT(*) FROM cr JOIN hd USING (wp_id) WHERE cr.rows_nonblank>0) AS both;

-- 载荷形态分布（决定清单 sheet 的两态渲染）
SELECT
  COUNT(*) AS nonblank,
  COUNT(*) FILTER (WHERE LEFT(TRIM(COALESCE(NULLIF(TRIM(remark),''),conclusion)),1) = '[') AS json_array,
  COUNT(*) FILTER (WHERE LEFT(TRIM(COALESCE(NULLIF(TRIM(remark),''),conclusion)),1) = '{') AS json_object
FROM checklist_responses
WHERE COALESCE(NULLIF(TRIM(conclusion),''), NULLIF(TRIM(remark),'')) IS NOT NULL;

-- 模板库引用与跨项目共享（缺陷 B 的判据）
SELECT file_path,
       COUNT(DISTINCT project_id) AS projects,
       COUNT(*) AS wps
FROM working_paper
WHERE is_deleted = false AND file_path LIKE '%wp_templates%'
GROUP BY file_path HAVING COUNT(DISTINCT project_id) > 1
ORDER BY projects DESC;
```

### 端点分组口径（守卫必须照抄，否则数字对不上）

```python
# 真实端点只能从运行期 app.routes 取（63 个模块零 @router. 装饰器）
# 分组键 = path 倒数第二段；必须剔除路径参数段，否则 {wp_id}/{wp_code} 会被当成前缀
_PARAM_SEG = re.compile(r"^\{.*\}$")

def group_ie_routes(app) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for r in app.routes:
        path = getattr(r, "path", "")
        segs = path.strip("/").split("/")
        if not segs or segs[-1] not in ("export-template", "export-data", "import-data"):
            continue
        if len(segs) < 2:
            continue
        prefix = segs[-2]
        if _PARAM_SEG.match(prefix):      # 🔴 R4 的「87 组」里含 {wp_id} 等误计
            continue
        out.setdefault(prefix, set()).add(segs[-1])
    return out
```

## Correctness Properties

### Property 1: verdict 非 file 时产物含自证文案

`resolve_wp_file` 返回 `verdict != 'file'` 时，单份下载与批量打包的产物内必须含「本份为空白模板」字样及 `VERDICT_LABELS[verdict]` 的中文原因。

**Validates: Requirements 1.1**

### Property 2: export-xlsx 空 html_data 自证

`html_data` 为空或缺对应 sheet 键时，产物首行含「录入内容未包含」及可操作提示。

**Validates: Requirements 1.2**

### Property 3: 自证文案单一真源

自证文案只取 `VERDICT_LABELS` 与 `self_evidence._KIND_LABELS`；扫全部调用方源码，不得出现硬写的中文自证字面量。反向自检：在调用方插一句硬写文案必须打红。

**Validates: Requirements 1.3**

### Property 4: 清单覆盖 template_fallback

`_未导出清单.txt` 必须列出 `verdict == 'template_fallback'` 的底稿。反向自检：改回「仅 empty/missing」必须打红。

**Validates: Requirements 1.4**

### Property 5: 清单按 verdict 分组且每档有处置建议

清单按 verdict 分组，且每个出现的档位都有对应处置建议行；建议文案条数 ≥ 出现档位数。

**Validates: Requirements 1.5**

### Property 6: 正常导出零噪声

全部底稿 `verdict == 'file'` 且 `html_data` 非空时，产物不含任何自证文案。判据用纯函数 `needs_self_evidence(...) is None`，并配「正常态替身必返 None」的无条件自检。

**Validates: Requirements 1.6**

### Property 7: 自证行不占数据区首行

自证落盘复用 `stamp_self_evidence`：第 1 行 banner、第 2 行空、第 3 行起数据。断言数据首格行号恒为 3。

**Validates: Requirements 1.7**

### Property 8: 「文件已就绪但录入未写入 xlsx」独立成档

`verdict == 'file'` 且 `html_data` 空且 `checklist_responses` 有非空行时，自证 kind 为 `entry_not_in_xlsx`，文案与 `html_data_absent` 逐字不同。反向自检：两档文案相同必须打红。

**Validates: Requirements 1.8**

### Property 9: 导出数据源含 checklist_responses

导出路径除 `html_data` 外必须真实读取 `checklist_responses`。判据为**真实执行**：造一份只有 `checklist_responses` 无 `html_data` 的底稿，产物必须含其内容。禁止只断言「代码里出现了表名」。

**Validates: Requirements 2.1**

### Property 10: 清单 sheet 按载荷形态两态渲染

`json_array` 载荷展开成表（列名取载荷键集）、`json_object` 纵向键值、`plain_text` 三列。每态各一例断言；`source_field` 必须落进 sheet。

**Validates: Requirements 2.2, 2.8**

### Property 11: 不改写模板既有 sheet 单元格

清单 sheet 为**追加**。断言：导出前后模板既有 sheet 的全部单元格值逐格相等。反向自检：故意写一格必须打红。

**Validates: Requirements 2.3**

### Property 12: 全空行不进清单

`conclusion` 与 `remark` 双空的行不进清单。真实库口径自检：1,033,715 行双 NULL 必须全部被剔除，清单行数不受它们影响。

**Validates: Requirements 2.4**

### Property 13: 清单 sheet 名不冲突

清单 sheet 名不与模板既有 sheet 名冲突；冲突时按后缀递增且断言最终名唯一。

**Validates: Requirements 2.5**

### Property 14: 无录入则无清单 sheet

`checklist_responses` 无非空行时产物不含清单 sheet。

**Validates: Requirements 2.6**

### Property 15: 上限截断且标注

清单行数与总字符数双阈值；超限截断并在 sheet 内标注被截断条数。真实库自检：C24 那份 1,033,230 行必须触发截断且不 OOM。

**Validates: Requirements 2.7**

### Property 16: 四场景复用既有三态端点

`scenario_registry` 的每个 `endpoint` 必须存在于真实 `app.routes`；且不得新增 per-cycle 端点（端点总数与基线相比只许持平或按登记增加）。

**Validates: Requirements 3.1**

### Property 17: 场景①产物不含项目数据

`export-template` 产物不含任何 `checklist_responses` / `html_data` 内容。反向自检：让它误走 data 分支必须打红。

**Validates: Requirements 3.2**

### Property 18: 场景③标注四表取数列与可编辑列

`export-data` 产物含列级标注，来源为 catalog 的 `formula_ref` 有无。断言标注列数 = catalog 中该 sheet 有 `formula_ref` 的 cell 数。

**Validates: Requirements 3.3**

### Property 19: 场景②③同一 import-data 端点

两场景回传路径解析到同一端点（按 `scenario_registry` 断言 endpoint 相等）。

**Validates: Requirements 3.4**

### Property 20: 模板↔数据错用可读报错

ZIP `manifest.json` 的 `mode` 与目标场景不符时返可读错误，且**不写入任何数据**。反向自检：撤掉校验必须让错位数据落库（守卫据此打红）。

**Validates: Requirements 3.5**

### Property 21: 场景④归档前后两时点可执行

归档前与归档后各执行一次批量导出均成功；产物含 `manifest.json` + sha256。

**Validates: Requirements 3.6**

### Property 22: UI 四场景语义可辨

前端渲染的四个入口各有「产物内容」与「适用时点」说明，文案取 `scenario_registry` 单一真源。反向自检：前端硬写中文说明必须打红。

**Validates: Requirements 3.7**

### Property 23: 归档态拒导入准导出

归档态下导入端点返可读拒绝原因；导出端点仍 200。

**Validates: Requirements 3.8**

### Property 24: registry 覆盖 catalog 全部启用条目

`CYCLE_IMPORT_EXPORT`（generated + overrides）覆盖 catalog 中 `import_export.enabled` 的全部 prefix；差集为空或全部落在 `EXEMPT_IE_PREFIXES`。

**Validates: Requirements 4.1**

### Property 25: apiPrefix 三向锁死

catalog ↔ generated registry ↔ 真实 `app.routes` 三向一致。分组口径照抄 §Data Models 的 `group_ie_routes`（含剔除路径参数段）。

**Validates: Requirements 4.2, 4.5**

### Property 26: sheets 取后端真源不推断

`sheets[]` 逐个存在于 catalog 的 `sheet_code` 或后端 `_SHEET_NAME_MAP` 键集。反向自检：把 `G0-3S` 改成 `G0-4` 必须打红。

**Validates: Requirements 4.3**

### Property 27: 后端新增未登记即打红

catalog 或工厂新增 prefix 而 registry 未登记 ⇒ 守卫红。反向自检：注入一个假 prefix 必须打红。

**Validates: Requirements 4.4**

### Property 28: 既有 10 key 零回归

`f1/f2/f2-val/f2-spe/f2-st/f3/f4/f5/g0/h0` 十个 key 的 `apiPrefix` 与 `sheets[]` 逐字节与基线相同（characterization）。

**Validates: Requirements 4.6**

### Property 29: 无法登记者进显式表

`EXEMPT_IE_PREFIXES` 每条含 `reason` + `evidence`；条目数有上限且只许下调。

**Validates: Requirements 4.7**

### Property 30: 11 个孤儿逐个处置

11 个孤儿（含立项漏记的 `useF1ImportExport`）逐个落到「接线 / 删除 / 豁免」之一，无未表态者。

**Validates: Requirements 5.1**

### Property 31: 接线者有真实渲染宿主

判「接线」成立的判据是**有渲染宿主**，且宿主不得是 `__tests__/` 或 `*.spec.ts`。反向自检：只加一个 spec 文件的 import 不得让基线缩短。

**Validates: Requirements 5.2, 5.6**

### Property 32: 删除者的后端端点仍有覆盖

判「删除」成立须证明该 prefix 的端点仍被 dropdown 或别的入口覆盖，或端点亦一并移除。

**Validates: Requirements 5.3**

### Property 33: 豁免者配 stale 检测

豁免条目一旦出现真消费方即打红。

**Validates: Requirements 5.4**

### Property 34: 孤儿判定按 import 路径

判据用 import 路径而非符号名。反向自检：仅改符号名不改路径，判定结果不得变化。

**Validates: Requirements 5.5**

### Property 35: 孤儿基线只许下调

基线条目数写死上限（11），只许减不许增。

**Validates: Requirements 5.7**

### Property 36: 模板库引用首写前复制

`file_path` 指向 `wp_templates/` 的底稿在首次写入前完成复制，写入落到项目独立路径。

**Validates: Requirements 6.1**

### Property 37: wp_templates 永不被写入

迁移前后 `backend/wp_templates/` 的 `(相对路径, size, sha256)` 快照逐条相等。反向自检：故意写一个字节必须打红。

**Validates: Requirements 6.2**

### Property 38: 迁移可回滚

台账含 `old_path`/`new_path`；`--rollback` 后 `file_path` 逐条还原，且不删新文件。

**Validates: Requirements 6.3**

### Property 39: 迁移幂等

二次 `--apply` 零变更（受影响行数为 0）。

**Validates: Requirements 6.4**

### Property 40: 逐条隔离失败

注入单条失败（如目标目录不可写）后其余条目仍成功，失败条进 `failed[]`。

**Validates: Requirements 6.5**

### Property 41: 多项目共享路径各得独立副本

实测 6 条路径各被 4 个项目共享 ⇒ 迁移后这 6 条产出 24 个互不相同的 `new_path`。

**Validates: Requirements 6.6**

### Property 42: verdict 分布变化被记录并核对

迁移前后 `resolve_wp_file` 全量 verdict 分布 diff 落台账；`template_fallback` 应减少、`file` 应增加，且总数守恒。

**Validates: Requirements 6.7**

### Property 43: 迁移须显式确认参数

无 `--confirm-destructive` 时拒绝执行并 exit 非 0。

**Validates: Requirements 6.8**

### Property 44: 守卫覆盖五类不变量

守卫集合覆盖「产物自证 / 数据源接通 / registry 三向锁死 / 孤儿基线 / 模板库只读」五类，逐类至少一个守卫文件。

**Validates: Requirements 7.1**

### Property 45: 每条判据可被变异打红

变异脚本对每条判据各有一个变异；覆盖率 = 变异数 / 判据数，缺口显式登记。

**Validates: Requirements 7.2**

### Property 46: 变异四态判定

按「失败测试名集合差集」判 RED / GREEN / ANCHOR-MISS / WRONG-TEST 四态，不看退出码；锚点命中数必须为 1；`\n` 跨行锚点在 CRLF 下须先归一。

**Validates: Requirements 7.3**

### Property 47: 真实库四场景各一次往返

验收脚本在真实库跑四场景各一次往返；每次记录产物条目数、sha256、落库行数。

**Validates: Requirements 7.4**

### Property 48: 无合法对象时诚实输出

真实库无合法验收对象时输出「无法验收」+ 非零退出，不用 fixture 冒充。

**Validates: Requirements 7.5**

### Property 49: 浏览器实测且数据复原

浏览器实测四场景入口；实测前抓基线（全文 + md5），测后逐字节复原 + 独立只读核实。

**Validates: Requirements 7.6**

### Property 50: 零回归用前后对照

用「当前态 → 施加改动 → 对照」判零回归，禁 HEAD-swap。

**Validates: Requirements 7.7**

### Property 51: CI 挂载全部守卫

`governance-checks.yml` 新增 job 覆盖本 spec 全部守卫；`yaml.safe_load` 可解析且无重名 job。

**Validates: Requirements 7.8**

### Property 52: 立项台账修正被固化

本轮推翻的 7 处台账（§核心事实修正）在守卫中逐条固化为可复算断言：`checklist_responses` 非空行数量级 · 双 NULL 行占比 · 载荷三形态分布 · 后端模块数与零装饰器模块数 · 真实三态端点分组数（剔除路径参数后）· 孤儿数 11 含 `useF1ImportExport` · `wp_templates` 引用份数 956 与共享路径 6 条。

反向自检：把任一断言改回立项旧数必须打红。

**Validates: Requirements 7.1, 7.4**

## Error Handling

| 场景 | 处理 | 理由 |
|---|---|---|
| `resolve_wp_file` 返 `empty`/`missing` | 产物仍生成，但带自证 banner | 空目录比空白模板更难排查（既有 `download_pack` 判断保留） |
| `html_data` 缺 sheet 键 | 自证 kind = `html_data_absent`，不抛 | fail-visible 而非 fail-silent |
| `checklist_responses` JSON 解析失败 | 降级 `plain_text` 并**记 WARNING** | 实测 269 行本就是纯文本，不能当异常；但要留痕以便发现真损坏 |
| 载荷超上限 | 截断 + sheet 内标注条数 | 实测单行 181,056 字符、单份 103 万行，不设限必 OOM |
| ACNR catalog 不可用 | 抛 `AcnrCatalogUnavailableError` | 复用既有铁律，绝不静默退回分散 JSON |
| ZIP `manifest.json` 缺失 | 抛 `ZipManifestMissing`（既有） | 无 manifest 无法判 mode ⇒ 无法防错用 |
| `mode` 与场景不符 | 拒绝导入 + 可读错误，零写入 | R3.5 明令不得静默写入错位数据 |
| 归档态导入 | 拒绝 + 原因；导出不拦 | R3.8 |
| 迁移单条失败 | 记 `failed[]` 继续 | R6.5 逐条隔离 |
| 迁移无 `--confirm-destructive` | 拒绝执行 | R6.8 |
| 迁移目标路径已存在且哈希不同 | 记冲突、跳过该条 | 防覆盖已有项目文件 |
| 验收无合法对象 | 输出「无法验收」+ 非零退出 | R7.5 禁 fixture 冒充 |

## Testing Strategy

| 层 | 文件 | 形态 |
|---|---|---|
| L1 | `backend/tests/services/test_wp_export_self_evidence.py` | 纯函数 `needs_self_evidence` 四态 + `stamp_self_evidence` 行号 + 文案真源扫描 |
| L1 | `backend/tests/services/test_wp_download_manifest.py` | 清单分组 / `template_fallback` 覆盖 / 处置建议条数 |
| L2 | `backend/tests/services/test_entry_payload_reader.py` | 三形态解析 + 双列读取 + 空行剔除 + 双阈值截断 |
| L2 | `backend/tests/services/test_export_entry_sheet.py` | **真实执行**：只有 checklist 无 html_data 的底稿产物含内容；模板既有 sheet 逐格不变 |
| L3 | `backend/tests/services/test_scenario_registry.py` | endpoint ⊆ 真实 `app.routes` + 四场景语义齐备 + `archived_allowed` 三态 |
| L3 | `backend/tests/services/test_bulk_mode_mismatch.py` | manifest `mode` 错用拒绝 + 零写入 |
| L4 | `backend/tests/test_ie_route_inventory.py` | **运行期 `app.routes`** 分组（照抄 `group_ie_routes`）+ 三向锁死 + 台账数字固化 |
| L4 前端 | `components/workpaper/shared/__tests__/cycleImportExportRegistry.spec.ts`（扩展） | catalog ↔ generated ↔ routes 快照三向 + 既有 10 key characterization |
| L4 前端 | `components/workpaper/__tests__/ieOrphanBaseline.spec.ts` | 孤儿按 **import 路径** + 排除 `__tests__`/`*.spec.ts` + 基线只许下调 |
| L5 | `backend/tests/scripts/test_wp_template_deref.py` | 幂等 / 回滚 / 逐条隔离 / 共享路径独立副本 / `--confirm-destructive` 门控 |
| L5 | `backend/tests/test_wp_templates_readonly.py` | `wp_templates/` 快照逐条相等 + 故意改一字节必红 |
| L6 | `backend/scripts/diagnose/verify_ie_lifecycle_live.py` | **只读 + 四场景往返**；无对象时诚实输出「无法验收」 |
| L6 | `backend/scripts/diagnose/mutate_ie_lifecycle_guards.py` | 变异四态判定 / 锚点命中数 = 1 / md5 还原 / `--restore` |

**守卫设计约束**（来自平台既有教训，逐条对应 memory 铁律）：

- **端点清单一律运行期取** —— 63 个模块零 `@router.` 装饰器，源码扫描会漏 2/3。且分组必须剔除 `{wp_id}` 这类路径参数段，否则会把它算成一个「前缀」（立项的「87 组」即含此误计）。
- **「数据源已接通」必须真跑** —— 只断言源码里出现 `checklist_responses` 字符串属 grep 式守卫；须造一份只有 checklist 无 html_data 的底稿，产物必须含其内容（memory：additive 注入即死代码是假绿三源之一）。
- **孤儿守卫排除测试文件** —— `useG13`/`useG14` 当前唯一 import 方是 spec 文件，若把它算消费方，基线永远清不掉。
- **连库守卫用一次 `asyncio.run` 取全部快照** —— 每测试各自 async 会污染共享连接池。
- **载荷读取的上限自检要用真实量级** —— 用 1000 行替身测不出 103 万行的问题；替身须按实测量级构造或直接连库跑那一份。
- **`stripComments()` + 反向自检** —— 文案真源扫描要先剥注释（docstring 里的示例文案会冒充硬写），并配「剥注释确实生效」的自检。
- **变异锚点先归一 CRLF** —— 本仓库文件为 CRLF，含 `\n` 的跨行锚点必 ANCHOR-MISS。
- **全量扫描做 `(path, mtime_ns, size)` memoization** —— 键必须含 mtime，否则变异检验假绿。

## Notes

### 与并发 spec 的边界

| spec | 交集 | 处置 |
|---|---|---|
| `k-cycle-…-closure`（5/25 在跑） | `useK5`/`useK12`/`useK1Writeoff` 三个孤儿属 K 循环 | 孤儿处置前查该 spec mtime；接线改动只碰 composable 与宿主，不碰 `k_cycle_specs.py` |
| `l-cycle-…`（3/26） | `useL4`/`useL0` 两个孤儿 | 同上 |
| `h-cycle-…`（已归档） | `useH5`/`useH7` 两个孤儿 | 无活动会话，可直接处置 |
| `g7-column-alignment-…`（4/24） | ACNR catalog 的 `g7-*` 三前缀 | 只读 catalog 不改；若需补 catalog 数据，先协调 |
| `procedure-trimming-…`（15/26） | 无 | 不碰 |

### 五条已知不做

1. **模板单元格回填** —— 需 per-cycle 地址映射，`structure.json` 全库 0 个、`item_id` 形态 211 种（立项已裁决，本设计沿用「附加 sheet」）。
2. **空 `file_path` 的 1564 份补文件** —— 无可复制源，属 R1 自证层作业面，不进 R6 迁移。
3. **`wp_templates/` 参考副本与权威副本的差异对齐** —— memory 已记两处不一致（G4/G5/G6），属另一半径。
4. **catalog 补齐后端工厂独有的 32 个前缀的完整 sheet 元数据** —— 本 spec 只补 `import_export` 段（`api_prefix`/`item_id`/`storage_field`），`formula_ref` 等 cell 级元数据留待各循环 spec。
5. **`checklist_responses` 的 103 万行空骨架清理** —— 是数据治理议题（单份 C24 占 99.9%），删除属破坏性操作且与本 spec 目标无关，只在验收脚本里登记其存在。

### 待用户裁决（不阻塞 L1~L3）

1. **孤儿 `useF1ImportExport` / `useG13` / `useG14` 是删还是接** —— 三者的 prefix 都已有 dropdown 覆盖，倾向删（能力不丢，减一条并存路径）。若倾向保留则需说明与 dropdown 的分工。
2. **R2.2 的「结论 / 备注」列语义偏离** —— 实测二者是同一载荷的两个候选存放列（非两个业务字段），设计改为标注 `source_field`。需确认这个偏离可接受。
3. **场景④的归档后导出是否需水印** —— `archive_manifest_service` 已有 `watermark` 概念，归档后导出的底稿包是否套用同一水印。
