# Design —— Excel 模板覆盖层与 OnlyOffice 模板编辑器

## Overview

**把「编辑模板」从"改那份权威文件"改成"在权威文件之上叠一层可版本化的覆盖"。**

权威目录 `backend/wp_templates/` 保持字节冻结；编辑产生的新 xlsx 落在覆盖层；`wp_template_finder`
增加一级优先解析。于是「运行时只读」（Requirement 9.9）与「模板可编辑」不再互斥 —— 前者约束的是
一个**具体目录**，后者需要的是一个**解析结果**，二者可以解耦。

编辑器本体不新造：复用已交付并实测无损的 OnlyOffice 整本模式（`whole_workbook=true` +
`excel_sheet_visibility` 的 zip 级可见性）。

## Architecture

### 分层与解析链

```
调用方（wp_template_init_service / wp_onlyoffice_router / 各 render 策略）
        │
        │ find_template_file / find_all_template_files / find_template_file_any
        ▼
wp_template_finder（改为薄封装，签名与返回类型不变）
        │
        │ resolve_template(wp_code, project_id=, group_id=)
        ▼
wp_template_override.resolve_template
        │
        ├─ 1. project        覆盖层当前版本？   → override:project
        ├─ 2. group_custom   覆盖层当前版本？   → override:group_custom
        ├─ 3. firm_default   覆盖层当前版本？   → override:firm_default
        └─ 4. 回落            wp_templates/     → authoritative
```

写入侧完全独立，且只能落在覆盖层：

```
OO 编辑会话 ── callback 落盘 ──▶ stage_override（越界门 + 扩展名门 + 格式门）
                                        │
                                        ├─▶ backend/storage/template_overrides/...
                                        └─▶ workpaper_template_override_version（新版本 + is_current 转移）
```

### 为什么解析层是正确的接缝

`wp_template_finder` 实测形态支持这一点：

* 纯文件系统，`session` / `db` / `WpTemplate` 各 0 次引用 ⇒ 不必先做数据层改造。
* 唯一根常量 `TEMPLATES_DIR`（L19）⇒ 覆盖层只需在它之前插一层查找。
* 三个公开入口 `find_template_file` / `find_all_template_files` / `find_template_file_any`
  ⇒ 接缝收敛，不必逐个调用方改。

而 `wp_template.file_path` 存的是路径不是内容 ⇒ 版本表也只存路径 + sha256，与既有形态一致。

---

## 明确拒绝的方案

1. **直接写 `backend/wp_templates/`。** 违反 Requirement 9.9；且实测有多个 spec 的守卫逐份比对
   476 条索引的 size/digest（如 `test_authoritative_template_digests_recompute`），改一个字节就
   打红一片。更重要的是语义：那是「所有项目所有底稿的生成基线」，不该由单个用户就地改。

2. **把模板内容搬进 DB（bytea）。** `wp_template.file_path` / `template_library.file_path` 现存
   形态都是路径；搬进 DB 要改两张表的语义（违反 Requirement 7.5），且 351 份 xlsx 里最大的
   近 900 KB，OO 每次打开都要从 DB 取再落临时文件，反而多一跳。

3. **用 Univer 做模板编辑器。** Univer 路径是 `xlsx → openpyxl → JSON → Univer → 再导出 xlsx`
   两次有损转换；其快照模型没有 printerSettings / VML 批注 / customXml 的概念。这正是本 spec
   前置修复所消除的那类毁坏（K11 实测部件 37→19、共享公式主格 12→0、非空缓存值 716→28、
   中文表名被写成 `&#23457;` 数字实体），不能按更大的口径重开。

4. **用 openpyxl 落盘覆盖层文件。** 同 3 的理由；`excel_materialize.select_write_strategy` 早已
   判定生产上 351 个模板没有一个能通过 openpyxl 这道门。

5. **覆盖层只做单层（事务所级）。** 项目间需求不同是常态；只给一层会逼人去改事务所级，
   影响面反而更大。故做「项目 > 事务所 > 权威」三层。

6. **解析只返回 `Path`。** 那样调用方无法回答「这份底稿用的是谁的模板」。必须带来源标记
   （Requirement 2.2）。

7. **保存即就地覆盖上一份覆盖文件。** 无法回滚、无法复核改了什么。必须版本化（Requirement 4）。

8. **回溯改写已生成底稿。** 已生成底稿是审计证据，模板变更不得倒灌（Requirement 7.4）。

9. **按 mtime 判覆盖层是否更新。** mtime 在拷贝/同步中不可靠；一律用 sha256。

10. **用「文件存在」当解析判据。** 必须是「该作用域有当前版本且其文件存在」；只看文件存在会把
    已回滚/已删除的残留文件当成有效覆盖。

11. **允许跨扩展名覆盖。** 用 xlsx 覆盖 docx 会让下游 componentType 分发错位，直接拒绝
    （Requirement 2.6）。

12. **把 docx 一起做。** docx 的编辑器、落盘、结构判据是另一套（`word_template_filler`、
    段落索引），混做会让两边判据都不清楚。范围切掉（Requirement 7.2）。

---

## Components and Interfaces

```python
# backend/app/services/wp_template_override.py（新建）

#: 裁决见 Gate 1。`backend/storage/` 已在 .gitignore 内且备份校验面是它的全递归。
OVERRIDE_ROOT: Final[Path] = BACKEND_DIR / "storage" / "template_overrides"

#: 裁决见 Gate 3。17/17 份 xlsm 含 vbaProject.bin 且 OO 保留性未取证 ⇒ 暂只开 xlsx。
EDITABLE_FORMATS: Final[frozenset[str]] = frozenset({".xlsx"})

class TemplateOverrideError(SyncDomainError): ...
class OverrideRootEscapeError(TemplateOverrideError): ...       # 写入目标越界
class OverrideExtensionMismatchError(TemplateOverrideError): ...# 跨扩展名覆盖
class OverrideFormatNotEditableError(TemplateOverrideError): ...# docx/doc/xls/xlsm
class OverrideScopeUnknownError(TemplateOverrideError): ...
class OverrideCurrentVersionAmbiguousError(TemplateOverrideError): ...

# 🔴 作用域**复用** template_library_models.TemplateLevel（裁决见 Gate 2）：
#    firm_default / group_custom / project。不新造 OverrideScope 枚举 ——
#    平台无独立事务所实体，而这三档已是模板库的既有词汇。
#: 解析优先级，靠前者胜。
SCOPE_PRIORITY: Final[tuple[TemplateLevel, ...]] = (
    TemplateLevel.project,
    TemplateLevel.group_custom,
    TemplateLevel.firm_default,
)

@dataclass(frozen=True)
class TemplateResolution:
    """解析结果 —— 路径 + 来源，供 Requirement 2.2。"""
    path: Path
    origin: str                   # "authoritative" | "override:project"
                                  # | "override:group_custom" | "override:firm_default"
    wp_code: str
    version_id: str | None        # 覆盖层才有
    sha256: str

def resolve_template(
    wp_code: str, *, project_id: UUID | None = None, group_id: UUID | None = None
) -> TemplateResolution | None
def resolve_all_templates(
    wp_code: str, *, project_id: UUID | None = None, group_id: UUID | None = None
) -> list[TemplateResolution]
def assert_override_root_disjoint_from_authoritative() -> None
def stage_override(...) -> Path       # 只在覆盖层内落盘，越界即抛
```

`wp_template_finder` 的三个公开入口改为薄封装，内部调 `resolve_template` 并取 `.path`
（保证 Requirement 2.3 零回归），同时新增带来源的入口供新代码用。

## Data Models

### 版本表（新迁移）

```sql
-- workpaper_template_override_version
wp_code            text     not null
scope              text     not null   -- 'firm_default' | 'group_custom' | 'project'
                                       -- 取值复用 template_level_enum（Gate 2）
project_id         uuid     null       -- scope='project' 时非空
group_id           uuid     null       -- scope='group_custom' 时非空
file_relpath       text     not null   -- 相对 OVERRIDE_ROOT
sha256             char(64) not null
is_current         boolean  not null default false
parent_version_id  uuid     null
created_by         uuid     null
created_at         timestamptz not null default now()
-- 唯一性：同 (wp_code, scope, project_id, group_id) 下 is_current 至多一条
```

`is_current` 的唯一性用**部分唯一索引**而不是应用层检查 —— Requirement 4.4 要求在并发下成立，
应用层检查在并发下必失效。三档作用域的 NULL 语义不同（`project` 用 `project_id`、
`group_custom` 用 `group_id`、`firm_default` 两者皆 NULL），Postgres 的唯一索引对 NULL 不去重，
故需按作用域分别建三条部分唯一索引，或用 `COALESCE(..., '00000000-...'::uuid)` 归一后建一条。
**选后者**：一条索引比三条更难漏，且 `WHERE is_current` 条件只写一次。

---

## Error Handling

一条禁令一个异常类型一个 `error_code`，全部继承 `SyncDomainError`，`error_code` 两两不同：

| 异常 | error_code | 触发条件 | 为什么不能降级 |
|---|---|---|---|
| `OverrideRootEscapeError` | `template_override_root_escape` | 写入目标 `resolve()` 后不以 `OVERRIDE_ROOT` 为前缀 | 降级就等于允许写权威目录，Requirement 1.1 直接失守 |
| `OverrideExtensionMismatchError` | `template_override_extension_mismatch` | 覆盖文件扩展名与权威文件不一致 | 用 xlsx 覆盖 docx 会让下游 componentType 分发错位 |
| `OverrideFormatNotEditableError` | `template_override_format_not_editable` | 目标格式不在 `EDITABLE_FORMATS` | xlsm 含宏且 OO 保留性未取证，放过去等于赌 |
| `OverrideScopeUnknownError` | `template_override_scope_unknown` | `scope` 不在 `TemplateLevel` 三档内 | 未知作用域会让解析优先级无定义 |
| `OverrideCurrentVersionAmbiguousError` | `template_override_current_version_ambiguous` | 同作用域查出 >1 条 `is_current` | 索引应已挡住；查出来说明索引缺失或被绕过，必须响亮失败 |

🔴 **不设 fail-open 分支。** 解析失败时不得"静默回落到权威文件" —— 那会把「覆盖文件损坏」
伪装成「本来就没有覆盖」，审计师看到的是旧模板却以为是新的。解析层只在**确实没有当前版本**时
回落；文件存在但读不出、sha256 不符、版本行自相矛盾三种情形一律抛。

`stage_override` 的落盘用「临时文件 + `os.replace`」：任何一步抛错，覆盖层原有文件完好无损。

## Testing Strategy

四层判据，每层都要能独立打红：

1. **结构性判据（零 DB、零写入）** —— `assert_override_root_disjoint_from_authoritative`、
   AST 扫描写入目标位。这类判据在 import 期或单测里跑，秒级。
2. **解析等价判据** —— 覆盖层为空时对全部 476 条索引逐条比对三个入口的返回值与 HEAD 版本。
   **这条必须在接线（Task 8）之前先绿**，否则等于先改后证。
3. **无损判据** —— 在含跨 sheet 引用的真实模板上取证，比对 zip 部件字节、跨 sheet 引用去重集合、
   共享公式主格数、非空缓存值数、`printerSettings` / `worksheets/_rels` 部件数、样式索引序列。
   复用已交付的 `_assert_only_workbook_part_changed`。
4. **变异检验** —— 每条结构性判据改一字看是否打红，四态判定
   （RED / GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷 / WRONG-TEST=打红了但不是预期项）。

分母断言贯穿全部判据：476 条索引、349 份 xlsx、17 份 xlsm、跨 sheet 引用数 > 0 —— 防止判据
在空集上恒真。

并发判据（Property 18）必须用**两个真实连接**同时写，验证靠部分唯一索引而不是应用层检查；
应用层检查在并发下必失效，用单连接测不出来。

## Correctness Properties

### Property 1: 覆盖层写入不得越界
覆盖层的任何写入函数，其目标路径 `resolve()` 后必须以 `OVERRIDE_ROOT` 为前缀；否则抛
`OverrideRootEscapeError`。用 `..` 穿越、绝对路径、符号链接三种形态各构造一例。

**Validates: Requirements 1.1**

### Property 2: 写入目标位不出现权威目录
对 `wp_template_override.py` 全部函数做 AST 扫描：不存在任何一处把 `TEMPLATES_DIR`（或其
`/` 拼接结果）传给 `write_bytes` / `write_text` / `open(..., 'w')` / `shutil.copy*` 的目标位。

**Validates: Requirements 1.2**

### Property 3: 权威目录 476 份逐份冻结
一次完整编辑保存后，`backend/wp_templates/` 下 476 个文件的 (size, sha256) 与 `_index.json` 声明
逐份相同。

**Validates: Requirements 1.3**

### Property 4: 冻结判据的变异必须打红
把 `OVERRIDE_ROOT` 临时改为 `TEMPLATES_DIR` 时，Property 3 的判据必须打红；且打红的
恰是 Property 3 那条测试而不是别的（变异四态里的 WRONG-TEST 也算失败）。

**Validates: Requirements 1.4**

### Property 5: 覆盖层根与权威目录互不包含
`assert_override_root_disjoint_from_authoritative()` 在 `OVERRIDE_ROOT` 是 `TEMPLATES_DIR`
的祖先、后代、或相等三种情形下均抛错；互不包含时通过。

**Validates: Requirements 1.5**

### Property 6: 覆盖层为空时解析零回归
覆盖层为空时，对全部 476 条索引逐条调用三个公开入口，返回值与 HEAD 版本逐份相同。

**Validates: Requirements 2.3**

### Property 7: 四层同时命中取项目级
同一 `wp_code` 在项目层与事务所层同时有当前版本时，`resolve_template(wp_code, project_id=...)`
返回项目层，`origin == "override:project"`。

**Validates: Requirements 2.4**

### Property 8: 逐层撤掉依次回落
自项目层逐层撤掉当前版本，解析依次回落为 `override:firm` → `authoritative`，每一步的
`origin` 与 `sha256` 都被断言。

**Validates: Requirements 2.5**

### Property 9: 跨扩展名覆盖被拒
覆盖文件扩展名与权威文件不一致时 `stage_override` 抛 `OverrideExtensionMismatchError`；
`.xlsx` 覆盖 `.xlsx`、`.xlsm` 覆盖 `.xlsm` 通过。

**Validates: Requirements 2.6**

### Property 10: 编辑会话是整本模式
模板编辑会话的 OO config 中 `whole_workbook` 为真：响应里不含 `actionLink`，且解析出的文件
全部 sheet 可见。

**Validates: Requirements 3.1**

### Property 11: 会话建立前后仅 workbook.xml 变
编辑会话建立前后，模板文件除 `xl/workbook.xml` 外全部 zip 部件字节相同。

**Validates: Requirements 3.2**

### Property 12: 空保存后跨 sheet 引用集合不变
在含跨 sheet 引用的真实模板上做一次「打开 → 不改任何内容 → 保存」，跨 sheet 引用去重集合
逐项相同。

**Validates: Requirements 3.3**

### Property 13: 空保存后五项结构指标不变
同一场景下，共享公式主格数、非空缓存值数、`printerSettings` 部件数、`worksheets/_rels`
部件数、样式索引序列五项逐项不变。

**Validates: Requirements 3.4**

### Property 14: 取证模板的跨 sheet 引用数非零
判据 12/13 所用模板的跨 sheet 引用数 > 0，且该数值在测试里被断言（防止挑到空集上恒真）。

**Validates: Requirements 3.5**

### Property 15: 落盘路径不含有损中间层
模板落盘路径的调用链（AST 可达性）里不出现 `openpyxl.load_workbook` / `Workbook.save` /
Univer / exceljs 相关符号。

**Validates: Requirements 3.6, 3.7**

### Property 16: 每次保存产生接父版本的新版本
每次保存后版本表新增一行，且 `parent_version_id` 指向保存前的当前版本（首版为 NULL）。

**Validates: Requirements 4.1**

### Property 17: 回滚取历史版本且不删行
把某历史版本置为当前后，解析返回该历史版本的文件（sha256 相等），且版本行数不减。

**Validates: Requirements 4.2, 4.3**

### Property 18: 并发下当前版本恰一条
并发对同一 `(wp_code, scope, project_id)` 发起两次保存，DB 里 `is_current=true` 的行恰为 1
（靠部分唯一索引，不靠应用层检查）。

**Validates: Requirements 4.4**

### Property 19: 删除覆盖后回落到权威文件
删除覆盖后解析回落到权威文件，且返回的 sha256 与 `backend/wp_templates/` 下该文件现算 sha256
相等。

**Validates: Requirements 4.5**

### Property 20: 编辑入口按格式门控
`WpTemplateDetail.vue` 里存在编辑入口，且该入口对 `format in {xlsx, xlsm}` 可用、对
`{docx, doc, xls}` 置灰；判据落在渲染形态（遍历 + 门控 + 嵌套三要素）而非字符串存在。

**Validates: Requirements 5.1, 5.2**

### Property 21: 来源与版本号取自后端
界面显示的来源与版本号取自后端下发字段，前端不含任何据文件名/路径推断来源的逻辑。

**Validates: Requirements 5.3**

### Property 22: 受影响面与现算相等
保存覆盖的响应含受影响面：该 `wp_code` 下按项目分组的既有底稿数量，且该数字与直接查库现算相等。

**Validates: Requirements 6.1**

### Property 23: 既有底稿不被倒灌
保存覆盖后，抽样既有 `working_paper` 文件的 sha256 不变。

**Validates: Requirements 6.2, 6.3**

---

## Rollout

1. 建 `wp_template_override.py`：常量 + 异常 + `assert_override_root_disjoint_from_authoritative`（零 DB、零写入）。
2. 迁移：`workpaper_template_override_version` 表 + 部分唯一索引（幂等 `IF NOT EXISTS`）。
3. `resolve_template` / `resolve_all_templates`（只读解析，先不接 finder）。
4. Property 6 零回归判据：覆盖层为空时 476 条逐条比对 —— **先证明无回归再接线**。
5. `wp_template_finder` 三个入口改薄封装。
6. `stage_override` + 越界/扩展名两道门（Property 1/2/5/9）。
7. 版本写入 + 回滚 + 删除（Property 16/17/18/19）。
8. OO 模板编辑会话端点（复用 `whole_workbook` + `excel_sheet_visibility`）。
9. Property 11/12/13/14 无损判据 —— 在真实含跨 sheet 引用模板上取证。
10. `WpTemplateDetail.vue` 入口 + 来源/版本展示（Property 20/21）。
11. 受影响面 + 不倒灌判据（Property 22/23）。
12. 变异检验：Property 4 及全部结构性判据逐条改一字看是否打红。

## Open Gates —— 已裁决（2026-09-03 实测）

### Gate 1：`OVERRIDE_ROOT` 放哪 —— 裁决 `backend/storage/template_overrides/`

实测依据：

* `.gitignore` 已含 `backend/storage/`、`backend/wp_storage/`、`storage/` 三行 ⇒ 覆盖层文件不入 git，
  与 `working_paper.file_path` 指向的运行时产物同等对待，不会污染仓库。
* `backend/scripts/check/verify_backup.py`：`STORAGE_DIR = Path("storage")`、
  `backup_storage = backup_path / "storage"`、`backup_files = list(backup_storage.rglob("*"))`
  ⇒ 备份校验面是 `storage/` 的**全递归**，新增子目录自动被覆盖，无需改扫描面。
* `backend/storage/` 现有一级子目录含 `projects` / `workpapers` / `attachments` / `deliverables`
  / `ledger_uploads` / `preview` / `qc_annual_reports` 等具名目录 + 数百个项目 UUID 目录
  ⇒ 增设一个具名子目录符合既有布局惯例。

**残留待办（Wave 0 Task 1 收尾）**：上面只证明了「备份**校验**脚本」覆盖 `storage/` 全递归；
还需确认「真正执行备份的脚本」同样覆盖。若不覆盖，覆盖层会在恢复时静默丢失 —— 这是
Requirement 1.5 之外的一条独立风险，必须在 Wave 1 之前落实。

### Gate 2：作用域载体 —— 裁决复用既有 `TemplateLevel` 三档，不新造词汇

实测依据：

* `backend/app/models/**` 全扫，**无** `Firm` / `Org` / `Organization` / `Tenant` / `Institution`
  任何模型类 ⇒ 平台没有独立的"事务所"实体。
* 但 `template_library_models.TemplateLevel` **已经定义了三档**：

  ```python
  firm_default = "firm_default"   # 事务所默认
  group_custom = "group_custom"   # 集团定制
  project      = "project"        # 项目级
  ```

⇒ 原设计里自造的 `OverrideScope.FIRM` / `PROJECT` 是重复造词。**改为直接复用 `TemplateLevel`**，
解析优先级 `project > group_custom > firm_default > authoritative`（四层）。`group_custom` 需要
`group_id`，与 `TemplateLibraryItem.group_id` 同源。

对 Requirement 2.4 的影响：作用域从两层变四层，Property 7/8 的判据须覆盖四层同时命中与逐层回落。

### Gate 3：xlsm 的宏 —— 裁决**暂时排除 xlsm**，可编辑集合 = xlsx 349 份

实测依据：

* 索引声明的 **17 份 xlsm 全部（17/17）含 `vbaProject.bin`** ⇒ 不存在"反正没宏，丢了也无所谓"的侥幸。
* `audit-onlyoffice` 容器 healthy 在跑，但**我没有取到 OO 往返后 `vbaProject.bin` 是否存活的证据**。

⇒ 在没有证据前把 17 份含宏文件放进可编辑集合，等于赌 OO 保留 VBA。保守裁决：**xlsm 与 docx
同等置灰**，可编辑集合仅 `xlsx`（349 份）。

放开条件（可另起一条小任务）：在真实 xlsm 上跑一次 OO 打开→保存，断言 `vbaProject.bin` 字节不变。
证据到位后再把 xlsm 移进可编辑集合，并把该断言固化为常驻判据。

对 Requirement 5.2 的影响：置灰集合由 `{docx, doc, xls}` 扩为 `{docx, doc, xls, xlsm}`。
