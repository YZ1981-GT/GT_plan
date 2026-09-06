# OO ↔ HTML 双向回写 —— 5 人分工书

> 建立日期 2026-09-04 · 主做人 A · 有效期至五个 spec 全部收口
> 分工依据全部为**实测**，非估算。每条数字后附取证方式，改动前请先复算。

---

## 1. 目标与当前真实状态

### 目标

让**全量底稿**在 HTML 结构化视图与 OnlyOffice 之间双向回写，且：

- 跨 sheet 公式关联零损失（不只是"不改坏"，还要"联动正确"）
- 动态插行与删行都能联动回写
- 权威模板目录保持运行时只读，同时模板可编辑可版本化

### 当前真实状态（`workpaper_sync_entry_manifest.json` 的 `stats` 现读）

```
entry_count 186          （xlsx 179 / docx 7）
capability_counts:  single_onlyoffice 180 / single_html 5 / unreachable 1
                    ⇒ bidirectional 0

migration_state:    legacy_fake_bidirectional 141
                    parent_duplicate           43
                    adapter_candidate           1
                    unreachable_pending_delete  1
```

🔴 **现在 0 个入口是双向的**，141 个被 manifest 自己标为「假双向」（界面上像能双向，实际不能）。
这是本次全部工作的起点，也是判断"是否真做成了"的唯一分母。

### 五个 spec 的规模与进度

| spec | Requirement | Property | 任务 | 已完成 |
|---|---|---|---|---|
`workpaper-html-onlyoffice-bidirectional-writeback-closure` | 14 | 72 | 77 | 70（7 条 `[-]` 阻塞） |
`published-representation-production-path-and-lane-adjudication` | 12 | 35 | 43 | 1 |
`excel-structural-row-insertion-and-shift-aware-verification` | 12 | 31 | 27 | 0 |
`excel-template-override-layer-and-onlyoffice-template-editor` | 7 | 23 | 27 | 3 |
`excel-workbook-wide-row-change-propagation` | 9 | 31 | 27 | 0 |
**合计** | **54** | **192** | **201** | **74** |

五个 spec 的机器校验（`get_diagnostics`）与自洽性审计（悬空 AC / Validates 命中 / waves 自洽）
**均为 0 问题**，可以直接按 tasks.md 执行。

---

## 2. 分工总表

| 人 | 泳道 | 负责 spec / 任务 | 独占生产文件 | 能否立即开工 |
|---|---|---|---|---|
**A（主做）** | L1 首版发布 + 全局协调 + 裁决 | `published-representation…` 43 任务；主 spec Task 75 / 76；BP-19 方案 + BP-20 业务输入的对接（BP-18 无需裁决，见 §7） | `projection_lane_registry.py`、`projection_first_publication.py`、`opaque_entry_gate.py` | ✅ |
**B** | L2a 结构性插行 | `excel-structural-row-insertion…` 27 任务 | `excel_row_shift.py`、`adapters/excel.py`、`contracts.py`、`excel_materialize.py`、`excel_extract.py` | ✅ |
**C** | L2b 工作簿级行变更传播 | `excel-workbook-wide-row-change…` 27 任务 | `excel_workbook_row_change.py` | ⚠ Wave 0 可立即做；Wave 1+ 等 B |
**D** | L3 模板覆盖层 + OO 模板编辑 | `excel-template-override…` 27 任务 | `wp_template_finder.py`、`wp_template_override.py`、`wp_template_override_router.py`、`wp_onlyoffice_router.py`、`WpTemplateDetail.vue` + 前端测试 | ✅ |
**E** | L4 判据治理 + Word 域 | 主 spec Task 74、Task 71 判据侧；五个 spec 的变异脚本；Word Task 63 第二条 | `check_workpaper_writer_revision_gate.py`、`workpaper_writer_domain_overlay.json`、`backend/scripts/diagnose/mutate_*.py`、`adapters/word.py` | ✅ |

### 并行安全的实测依据

生产文件占用面交集只有**一处**：

```
B × C：backend/app/services/workpaper_sync/excel_extract.py
       backend/app/services/workpaper_sync/excel_materialize.py
       backend/app/services/workpaper_sync/excel_row_shift.py
```

D 的 6 个文件与 A / B / C / E **零交集**。A / B / D / E 四条泳道可完全并行。

🔴 **两处需要人为避让**（主 spec 无文件记号表，靠正文点名的模块推断，已登记在其
tasks.md 的「文件占用面与并行安全」小节）：

1. **主 spec Task 71 / 72 × D**：Task 71 点名 `get_sheet_onlyoffice_config` /
   `get_sheet_wopi_contents` / `get_whole_excel_grid`，都在 `wp_onlyoffice_router.py` 里，
   而该文件归 D。⇒ **Task 71 / 72 由 A 在 D 收口后接手**，E 不碰。
2. **主 spec Task 61 × A**：共 `check_task61_oo94_word_pilot_gate.py`。⇒ 该文件归 A。

---

## 3. 依赖顺序

```
第 0 步（A 做，全员等）  复选框对齐
   │
   ├───────────┬───────────┬───────────┬───────────┐
   ▼           ▼           ▼           ▼           ▼
  A: L1       B: L2a      C: L2b      D: L3       E: L4
 首版发布    结构性插行   Wave 0 实测  模板覆盖层   判据治理
   │           │           │           │           │
   │           └──────────▶│（B 的 Wave 4 完成后 C 接 Wave 1+）
   │                       │           │           │
   └───────────────────────┴───────────┴───────────┘
                           ▼
                  全量双向回写可用（bidirectional > 0）
```

🔴 **2026-09-04 实测更正（见 §11.2）**：下面这段原判断**方向是反的**，保留原文以便对照。
实测 `--apply` 后：D2 的首版发布**依赖 B 的 Wave 4 结构性插行接线**，H1 被 BP-21 的「……」
排版占位行挡住。⇒ **M2 是 M1 的前置**，B 的 Wave 4 是全局关键路径。

> ~~**为什么 A 的 L1 在关键路径上**：`bidirectional = 0` 是最根本的阻塞 —— 没有首版
> published representation，B / C / D 做完也没有可回写的对象。~~

L1 的第一个实质动作仍是把 `fix_projection_first_publication.py` 从 `--check` 推到 `--apply`
—— 已执行，结论见 §11.1（四个 entry 一个都发不出去，库里 0 新增行）。

**为什么 B 必须先于 C**：工作簿级计划把单 sheet 位移作为其受管 sheet 分量，且两者都改
`plan_managed_writes`。门已写进 C 的 spec（Task 101，现读 B 的 tasks.md 断言 Wave 4 的
Task 16 / 17 / 18 均为 `[x]`）。

---

## 4. 第 0 步：复选框对齐（A 做，全员等，约 1 轮）

三个 spec 的复选框与磁盘上实际存在的代码**不一致**，两个方向都有风险：

| spec | 复选框 | 磁盘实际 |
|---|---|---|
P | 1/43 | `projection_lane_registry.py`（含双向自检，import 期执行）、`projection_first_publication.py`、`backend/scripts/fix/fix_projection_first_publication.py`（`--check` 实测 H1 / D2 各 6/6 `ready_to_publish`）已存在 |
S | 0/27 | `excel_row_shift.py` 位移函数本体已写（分词扫描 + 4 条变异全 RED），但**生产零引用** —— 属死代码 |
T | 3/27 | `excel_sheet_visibility.py` 已交付并接线到 `wp_onlyoffice_router.py`，全模板库 314 份多 sheet 模板通过 |

不对齐会同时踩两个坑：把已交付的重做一遍，或把没接线的当已完成（假绿）。

**对齐判据**：现读代码的**生产引用关系**（该模块是否被 `backend/app/**` 引用），不是记忆，
也不是"文件存在"。`git status --porcelain` 空输出 = 未修改，用它区分自己的债与并发的债。

对齐完成后 A 在本文档 §9 追加一行变更记录，B / C / D / E 方可开工。

---

## 5. 各人任务书

### A（主做人）—— L1 首版发布 + 全局协调 + 裁决

**主线**：`published-representation-production-path-and-lane-adjudication`（43 任务 / 16 Wave）

已有基础（第 0 步对齐后确认实际完成度）：
- `projection_lane_registry.py`：L1~L5 五级裁决 + `assert_registry_covers_opaque_lanes()`
  import 期执行 + `assert_no_second_lane_decision_site()`。四条供给判据实测 b60/d2/h1 A=1、g7 A=0、**B 全 0 = BP-61-1**
- `projection_first_publication.py`：`resolve_plan` 五条准入 / `stage_instrumented_substrate`（零 DB） / `publish_first_generation`，6 个 error_code 两两不同
- `fix_projection_first_publication.py`：`--check` 六阶段全链已跑通

**下一个实质动作**：跑 `--apply`（P spec Wave 8~11），让 H1 / D2 真有 published representation。

真库写入的三个已知坑：
1. `engine.begin()` 内**一处失败全部回滚** ⇒ 必须逐 entry 独立事务
2. timestamptz 回写必须在 **Python 侧**转 `datetime`；SQL 层 `CAST(:x AS timestamptz)` 无效（驱动发送前就按目标类型编码）
3. 被 `^C` 中断的运行**可能已提交部分变更** ⇒ 判成败一律**查数据不看 exit code**

**兼任**：
- 主 spec Task 75 / 76（与 P spec 是同一份工作，以 P 为唯一执行面，完成后按其产出勾掉主 spec）
- 主 spec Task 61（共 `check_task61_oo94_word_pilot_gate.py`）
- 主 spec Task 71 / 72（**待 D 收口后**接手，因共 `wp_onlyoffice_router.py`）
- **BP-18 / BP-19 裁决**（见 §7）

**协调职责**：
- 冲突仲裁：任何人发现文件面与他人重叠，先停手报 A
- 生成器重跑的排期（见 §6 规则 3）
- 每个 lane 出门时的产物入库核查

---

### B —— L2a 结构性插行

**spec**：`excel-structural-row-insertion-and-shift-aware-verification`（27 任务 / 6 Wave）

**核心设计**：把「位移」从"必然是漂移"改成"**可以是一份被冻结的声明**"。验证器用
`plan.count` **声明值**归一化，不是观测值 —— 实测位移 ≠ 声明即判漂移。

**独占文件**：`excel_row_shift.py`（N1）、`adapters/excel.py`、`contracts.py`、
`excel_materialize.py`、`excel_extract.py`

**已有基础**：`excel_row_shift.py` 的位移函数本体已写好，含：
- `ROW_BEARING_STRUCTURES`（12 项）、`RowShiftPlan`、`ShiftReport`、`shared_formula_groups`、
  `shift_sheet_rows`（阶段 A~F）、`assert_shift_handlers_cover_structures`（AST `_handled` 标记）
- `_rewrite_formula_refs` 分词扫描（本模块**唯一** A1 改写入口），已处理四类误命中：
  跨 sheet 表名当坐标（实测全库 16,027 处）、跨 sheet 目标格误位移、带数字函数名（`LOG10`）、
  字符串字面量
- 4 条变异全 RED（短路前缀分支 / 摘 `!` 左边界 / 短路字面量 / 摘右边界断言）

🔴 **但它生产零引用** —— `plan_managed_writes` 里 `RowShiftPlan` / `shift_sheet_rows` /
`excel_row_shift` / `row_shift` 四个关键词**全部不出现**。所以 **Task 16 / 18（接线）是 B 的
最高优先级**，不是新写位移逻辑。

**最重要的两条顺序**：
1. **Wave 0 必须先做**（`_SHEET_STRUCTURE_BLOCKS` 先扩充到 10 项再动结构）—— 先补检查再动结构，
   否则"改了没人看"就是假绿。这一波实测已完成（4 → 6 coverage，806 passed）
2. **Task 16 的 6.2 步（算位移计划）必须排在 footer 两门之前** —— 两门要用位移后区间求值

**交接义务**：Wave 4（Task 16 / 17 / 18）完成时**主动通知 C**。C 的 Task 101 会现读你的
tasks.md 断言这三条为 `[x]`，但主动通知能省 C 一轮轮询。

**已知坑**：
- 位移阶段 A 必须**自底向上**重编号（自顶向下会让刚改过的行与原始行不可区分）
- 新插入行**必须带公式**（`formula` 模式走 `cached_value_only`，`_patch_sheet_xml` 对不存在的
  公式格抛「不得凭空造一个公式格」）
- 主格不复制、新行退化为独立公式（Req 4.8 主格永不换字面量）
- 残余 `RowSetDivergenceError` 分支**必须保留并强化**，不得为接线放宽
  （`mutate_task38_excel_materialize_guards.py` 的锚点依赖它）

---

### C —— L2b 工作簿级行变更传播

**spec**：`excel-workbook-wide-row-change-propagation`（27 任务 / 7 Wave）

**为什么需要它**（实测，非推断）：

| 事实 | 值 |
|---|---|
含跨 sheet 引用的 xlsx | **176 / 351** |
其中「被引用的 sheet 自身含动态行占位」 | 🔴 **137 份**（受影响 sheet **604 张**） |
K11 受管 sheet `审定表K11-1` 被引用 | 🔴 **2 张 sheet 的 114 处公式**，行号 7~25 共 19 个不同行 |
K11 受管区 | `A7:N25` ⇒ **被引用行号完全落在受管区内** |
最极端样本 | 「调整事项汇总表」被引用 **9,744 处**；「报表格式」被引用 **3,137 处** |

现状实现对跨 sheet 引用是**逐字不动**：保证不改坏，但不保证联动正确 —— 受管 sheet 插一行后
`'审定表K11-1'!F20` 仍指向 `F20`，而那笔数据已被推到 `F21` ⇒ **静默指向错行**。
静默错行比报错贵得多，审计取数看着仍然"有值"。

**Wave 0 可立即开工**（4 个 Open Gate 全是只读实测，零文件冲突）：

| Gate | 要测什么 | 为什么可能改设计 |
|---|---|---|
1 | `ManagedRegion` / projection 契约能覆盖 137 份里几份 | 覆盖不到的只能登记 `blocked`；若选启发式推断受管 sheet，**必须先答「推断错了被什么判据抓住」** —— 猜错受管 sheet 会把传播用到错的地方，比不传播更危险 |
2 | `definedNames` / `sqref` / `mergeCell@ref` / `hyperlink@ref` 四类载体的真实条数 | 为 0 的载体判据必须用真实模板 zip 级注入变体，不得手搓最小 xlsx（会在空集上恒真） |
3 | 9,744 处引用那份模板的传播耗时 | 超出可接受交互延迟就得异步化或登记 `blocked` |
4 | 「受管区内被引用的行」占受管区行数的比例 | 若绝大多数删行都命中悬空引用，fail-closed 等于**删行基本不可用** ⇒ 要改设计（如把被引用行标记为不可删） |

**Wave 1+ 的开工门**：Task 101 现读 B 的 tasks.md，断言 Wave 4（Task 16 / 17 / 18）均为 `[x]`。
未满足即报清单并阻断。判据落在**现读复选框**（行首锚定正则 `^\s*-\s\[([ x~-])\]\s+\d+\.`），
不是人工记忆。

**关键设计约束**：
- **加法不是翻转**：`_rewrite_formula_refs` 加 `propagate_sheets` 参数，默认空集时行为与现状
  **逐字相同**。Task 6 的零回归判据（全库 81,955 处引用输出不变）**必须先绿**才允许接传播
- **不新造 A1 改写入口**（Property 27 用 AST 锁死）
- 悬空引用 **fail-closed**：必须在**计划阶段**就发现并报出完整清单，不等写盘

---

### D —— L3 模板覆盖层 + OO 模板编辑

**spec**：`excel-template-override-layer-and-onlyoffice-template-editor`（27 任务 / 7 Wave）

**核心设计**：权威目录 `backend/wp_templates/` 保持字节冻结，编辑产物落在覆盖层，
`wp_template_finder` 增加一级优先解析。Requirement 9.9「运行时只读」约束的是一个**具体目录**，
编辑需要的是一个**解析结果**，二者可解耦。

**独占 6 个文件，与谁都不冲突** —— 最适合全程并行。

**已有基础**：
- `excel_sheet_visibility.py` 已交付并接线（zip 级只改 `xl/workbook.xml` 的 `state`/`activeTab`）。
  K11 九步真实切换序列实测 **11 项指标 0 漂移**，全模板库 **314 份多 sheet 模板全通过**
- OO 整本编辑界面**已端到端存在**：`GtWpRenderer.vue` L524-537 注入「完整Excel」合成页签，
  `whole_workbook=true` 时后端不加 actionLink、OO 打开整本显示全部 sheet tab

**Wave 0 三个 Gate 已裁决**（可直接进 Wave 1）：

| Gate | 裁决 | 依据 |
|---|---|---|
1 | `OVERRIDE_ROOT` = `backend/storage/template_overrides/` | `.gitignore` 已含 `backend/storage/`；`verify_backup.py` 的 `backup_storage.rglob("*")` 是 storage/ 全递归。**残留 Task 101**：只证明了备份*校验*脚本覆盖，执行备份的脚本未确认 |
2 | 作用域**复用既有 `TemplateLevel` 三档**（`firm_default` / `group_custom` / `project`），四层优先级 | 无 `Firm`/`Org`/`Tenant` 模型类，但该枚举已定义三档 ⇒ 原设计自造 `OverrideScope` 是重复造词 |
3 | **排除 xlsm**，浏览器内编辑集合 = xlsx 349 份 | 17 份 xlsm **17/17 全含 `vbaProject.bin`**，OO 保留性未取证 ⇒ 保守排除 |

**覆盖面口径**（不要误读 R7.2）：

| | 覆盖层解析 | 版本化/回滚 | 浏览器内编辑 |
|---|---|---|---|
xlsx（349） | ✅ | ✅ | ✅ OO 整本 |
docx / doc（109） | ✅ | ✅ | ❌ 上传替换 |
xlsm（17） | ✅ | ✅ | ❌ 待取证 |
xls（1） | ✅ | ✅ | ❌ 非 OOXML |

「可覆盖可回滚」= **476/476**，「可在浏览器里直接编辑」= **349/476**，其余 127 份走上传替换、
同样进版本表。AC 5.5：上传替换必须走与编辑**同一条** `stage_override` + 版本表路径。

**最重要的一条顺序**：Task 7 的零回归判据（覆盖层为空时对全部 476 条索引逐条比对三个入口的
返回值与 HEAD 版本）**必须先绿**，才允许做 Task 8 的 finder 接线 —— 先证明无回归再动既有解析器。

**避让义务**：`wp_onlyoffice_router.py` 归你。收口时通知 A，A 才接手主 spec Task 71 / 72。

**反面教材（绝不能重犯）**：
- **openpyxl 全量重写**：K11 实测 zip 部件 **37 → 19**（丢 7 个 `printerSettings*.bin` +
  6 个 `worksheets/_rels/*.rels` + `sharedStrings.xml` + `calcChain.xml` + 批注 + customXml）、
  共享公式主格 **12 → 0**、非空缓存值 **716 → 28**、样式索引 `s="94"` → `s="218"` 全表重排、
  中文表名被写成 `&#23457;` 数字实体
- **Univer 往返**：`xlsx → openpyxl → JSON → Univer → 再导出` 两次有损转换，快照模型没有
  printerSettings / VML 批注 / customXml 的概念。Requirement 7.3 明令排除

---

### E —— L4 判据治理 + Word 域

**主线一：主 spec Task 74** —— writer / version domain 归零

- 接手 Task 20 冻结的红基线里**七条**准则的归零：`unadjudicated_writer`（实测 **236 行**）、
  绕过统一 commit（**261 行**）等
- 做法只有两条：**逐 domain 裁决**（每行进 `workpaper_writer_domain_overlay.json` 的 reviewed
  overlay）+ 真实迁移
- **完成判据 = `check_workpaper_writer_revision_gate.py` 的 14 条准则全为零**（默认命令退出码 0），
  不是「上面七条为零」
- 🔴 **禁止四件事**：加豁免列、overlay 级 `allow_bypass`、缩小分母（收窄 `_APP_ROOT`、给
  `_is_production_source` 加业务目录排除）、把「已裁决 2 条」当成「七条已清零」
- 归零后同步更新 Task 20 正文冻结的那 14 个数字，并重跑
  `mutate_task20_writer_gate_guards.py`

**主线二：五个 spec 的变异检验脚本**

每个 spec 都有一条变异任务。集中由 E 写，好处是四态判读标准统一：

| 态 | 含义 |
|---|---|
RED | 打红了，且**正是预期那条测试** |
GREEN | 守卫缺陷（改了没红） |
ANCHOR-MISS | 脚本缺陷（锚点未命中或命中 >1；含 `\n` 跨行锚点在 CRLF 必 MISS） |
WRONG-TEST | 打红了但不是预期项（污染残留或锚点错行） |

🔴 只看退出码会把后三态误判成 RED。**后三态任一非零即不通过。**

🔴 **变异用例必须让被检验机制成为该用例的唯一保护**。已实测过一个反例：
`'明细表K11-2'!F29` 做变异用例**不敏感** —— 行号 11 小于 `insert_at=26`，位移是空操作；
且 `!` 在左边界黑名单里是第二道防线。换成行号落在插入点之后的用例才敏感。

**主线三：生成器 staleness 的统一责任**（见 §6 规则 3）

**主线四（待 A 裁决后接）**：Word 域 Task 63 第二条 bullet（`S33-REV` 已闭环部分）+
Task 61 的判据侧。第一条 bullet（9 个 B 子码）被 BP-18 阻塞。

**独占文件**：`check_workpaper_writer_revision_gate.py`、`workpaper_writer_domain_overlay.json`、
`backend/scripts/diagnose/mutate_*.py`、`adapters/word.py`

---

## 6. 协作规则（全员必守）

### 规则 1：文件独占

一个生产文件在任一时刻只有一个 owner。发现自己要改的文件在别人名下 —— **停手报 A**，
不要"就改一行"。本仓库已发生过并行改同一文件互相回退的事故。

判 owner：查本文档 §2 的表；表里没有的查各 spec tasks.md 的「文件记号」表；
主 spec 查其 tasks.md 的「文件占用面与并行安全」小节。

### 规则 2：改动前后都查 git 状态

```
git status --porcelain -- <path>
```

空输出 = 未修改。**这是区分「自己的债」与「并发会话的债」的唯一可靠方法。**

工作树长期不干净是常态（多人在途 + 数百 `tmp_*`）。判某 spec 是否真完成一律**工作树 + HEAD
双查**，防「从未提交」与「被回退」两类假红。

### 规则 3：生成器 staleness —— 只在收口时重跑

任何人改 `backend/app/**/*.py` 都会让 `workpaper_writer_inventory.json` 变 stale，
连带 `test_task20` / `test_task30` / `test_task44` 一批 freshness 判据打红。
**实测过一次：改 6 个文件连带 8 条判据红。**

规则：
- **中途不跑生成器**（多人并行时会互相覆盖）
- **每个 lane 收口时才跑**，跑完立即 `git diff --numstat` 确认 diff 规模合理
- 三个生成器：`generate_workpaper_writer_inventory.py`、
  `generate_workpaper_resolver_migration_matrix.py`、
  `generate_workpaper_task44_pilot_probe_registry.py`
- 排期由 A 协调；E 是兜底责任人

⚠ **拒绝整份重跑那些会带进他人在途状态的生成器**。已实测：`generate_task67_structural_pre_reconcile.py --write`
的 diff 是 600/464 行，且冒出并发会话带来的新漂移分类键 `scenario_profile_changed`×136 ——
那不是自己的改动。正解是用生成器**自己的**算法做外科式两字段更新（实测 diff 恰 2 行）。

### 规则 4：判据纪律

- **「字符存在」型判据不算判据。** 判据一律落在**行为 / 结构 / 真实执行 / DOM**
- 对生产源做「某符号是否真被用到」的判断前**必须先剥 Python docstring**
  （`_strip_comments` 不剥它）。已栽过一次：router 的 docstring 里记录了 openpyxl 那版的实测
  毁坏，判据于是恒红。可复用 `test_task54_l_cycle_migration.py` 的 `_strip_docstrings`
- **每写完守卫必做变异检验**；没打红 = 守卫有缺陷，不是代码没问题
- 所有判据必须带**分母断言**（476 条索引 / 351 份 xlsx / 176 份含跨 sheet / 137 份受影响 /
  604 张 sheet / K11 的 114 处引用 / 81,955 处引用 / 186 个 entry），防止在空集上恒真
- **fail-open 是最贵的一类缺陷**：`except Exception` 把「函数名拼错、列名拼错、传错客户端形态」
  全吞成 WARNING，表现为「本项目无此数据」，而静态检查与单测四层全绿。取值层守卫必须
  **真跑一次并把异常记 ERROR 态**

### 规则 5：spec 三件套的机器校验格式

- `requirements.md`：`# Requirements Document` / `## Introduction` / `## Requirements`（+ 推荐 `## Glossary`）；
  Requirement 用 `### Requirement N: 标题`（**半角冒号**，全角 `：` 不识别）；
  每条 Requirement 需 `**User Story:**` 与 `#### Acceptance Criteria`
- `design.md`：`## Overview` / `## Architecture` / `## Components and Interfaces` / `## Data Models`
  （+ 推荐 `## Correctness Properties` / `## Error Handling` / `## Testing Strategy`）；
  Property 用 `### Property N: 标题`（有冒号有标题）
- `tasks.md`：`# Implementation Plan:`；任务编号**必须纯整数**（`1b.` 不合法，用 `101.`）；
  `## Task Dependency Graph` 内含 waves JSON，每个 wave 要有 `wave` / `name` / `tasks` /
  `depends_on` / `rationale`
- ⚠ 正文换行的**行首**若恰为 `Property N ` 会被当成标题候选而报错，折行时避开
- ⚠ `get_diagnostics` 对刚改的文件**可能返回陈旧结果**；报错行号要用
  `python -c "open(p,encoding='utf-8').read()"` 直读磁盘核对

### 规则 6：环境与命令

- Python 一律 `python`（不是 `python3`）；命令分隔用 `;`（不用 `&&`）；固定目录用 `cwd` 参数（不用 `cd`）
- **别跑全量 `backend/tests`**（根目录 1522 个测试文件，前台跑数分钟无输出会被当卡死）⇒
  按**引用关系反查辐射面**（扫测试文件里对本次改动物的实际引用）
- pytest **一律从仓库根跑**（从 `backend/` 跑用相对路径的测试会 `FileNotFoundError` 假红）
- `-k "a or b"` 经 shell 会被拆成多个位置参数 ⇒ 用 `subprocess.run([...])` **不经 shell**，
  并加「passed < N 即中止」自检
- PowerShell 管道会把中文腌成乱码 ⇒ `Out-File -Encoding utf8` 写、`Get-Content -Encoding utf8` 读；
  脚本内落盘用 `Path.write_text(encoding="utf-8")`
- `python -c` 里含 `{}` / 引号易崩 ⇒ 写成 tmp 脚本文件
- importlib 加载含 `@dataclass` 的模块前必须 `sys.modules[spec.name] = mod`
- 定位受管 sheet 的 zip part **必须**用
  `app.services.excel_structure_fingerprint._parse_workbook_xml` + `_normalise_part`
  —— 手搓正则对 B60 / H1 / G7 三个模板**全部失败**（sheet 名含中文括号、属性顺序不保证）

### 规则 7：收口三件（每个 lane 出门必做）

1. 变异检验四态**全 RED**
2. 重跑受影响生成器（按规则 3）
3. 逐产物 `git status --porcelain -- <清单>`，见 `??` 即 add ——
   **「spec 全绿 ≠ 产物已入库」**。挂进 CI 的 job 在干净 checkout 下必须能跑
4. 清理自己的 `tmp_*` / `_wip_*` 诊断产物（按 mtime 判归属，并发会话在用的不动）

### 规则 8：临时产物

- `.gitignore` 已收 `tmp_*` 与 `_wip_*`
- 自己的产物自己清；判归属按**前缀 + mtime**，不按文件名里的任务号
  （曾出现 `E1TabDisclosure.vue` 名字是 E 循环的却是并发 K 循环改的）

---

## 7. 三条阻塞的实证裁决（2026-09-04 补，原「待裁决两条」已定性）

动手取证后结论与初判不同：**BP-18 根本不需要裁决**，而真正卡住 Word 域的是此前没被单列的 **BP-20**。

### BP-18 —— 不是选择题，是派生状态，会随 L1 自动解除

`registry.PENDING_ENGINE_ADAPTERS` 是一张「已交付 vs 仍未交付」的**双向登记表**，
其 `forbidden_paths` 含 `adapters/word.py` 与 `adapters/word`。它的解除条件在源码注释里
**已经硬编码写死**：

> Word tagged-SDT engine 的载体门是 F2-22/F2-23 的真实 OnlyOffice 9.4 pilot（Task 61）；
> 该门未过之前不得落地 Word adapter。

实测有 **13 个文件、40+ 处**引用它，其中 `test_task75_published_identity_observer.py` 与
`test_task77_word_entry_gate.py` 各自明写「**本任务无权翻 `PENDING_ENGINE_ADAPTERS` 里禁止
`adapters/word.py` 的那一行**」。这是被多方刻意锁死的门，单方面放开会打红一片。

真实解除链（现读复选框）：

```
Task 77 [x] 已完成
Task 75 [-] ┐
Task 76 [-] ┴→ Task 61 前置齐备 → Task 61 通过 → BP-18 自动解除 → Task 63 第一条可执行
```

而 Task 60 正文明写「BP-10 ~ BP-15 的**归零动作改由 Tasks 75–77 承接**」，
**Tasks 75 / 76 正是 A 的 L1 泳道**（= `published-representation` spec）。

**结论：BP-18 不需要任何人裁决，不要动那一行。** 它会随 L1 完成而解除。
E 的 Word 域任务排在 L1 之后，不是"等一个决定"，是"等一个前置完成"。

### BP-19 —— 推荐 **OPT-SPLIT**，理由是实物证据

两份权威模板实测：

| 文件 | 大小 | sha256(12) | `${token}` 数 |
|---|---|---|---|
`B/B2-3 …（就业务承接事项，**第一封**沟通函）.docx` | 22,705 B | `6dd3df4a5299` | **0** |
`B/B2-3 …（就业务承接事项，**第二封**沟通函）.docx` | 21,275 B | `365829d7d037` | **0** |

正文段落集合比对：**共有 17 条 / 仅第一封 20 条 / 仅第二封 5 条** ⇒ 不是同一文档的两个版本。

- **第一封**：15 条询问事项（管理层正直与诚信、重大会计与审计问题的意见分歧、商誉减值测试、
  同一控制下企业合并认定、第三方回款、会计政策与差错更正、股份支付、研发相关内控…）
- **第二封**：明写「**仅适用于上述编制说明第 7 项所述情形。发出时，将第一封沟通函的存印件附后**」
  ＋「截至本函件发出日止，我们尚未收到贵所的回复」＋「如在 20XX 年 X 月 X 日前仍未收到回复，
  我们将假设不存在专业方面的原因使我们拒绝接受该公司的委托」

而编制说明第 7 项写的是「如果未得到答复…项目组可以第二次致函前任注册会计师
（一般距第一封沟通函发出后两…）」。

⇒ **这是审计流程的两个阶段，不是一份文档的两个版本。**
`workpaper_sync_task63_subcode_adjudication.json` 里 OPT-PRIMARY 自己的 `cost` 就写着这句话 ——
它否定了 OPT-PRIMARY 自己的前提。

**为什么必须拆**：`why_it_blocks_contract_publication` 说得很准 —— per-entry contract 的
template slot 冻结**一份** `template_sha256`；一个 `wp_code` 对两份权威 docx 时，
「一个 entry 一份 template digest」这个前提结构性不成立。

**选 OPT-PRIMARY 的代价不可补救**：JSON 的 `unreachable_in_word_domain` 里那第二封函会永久
离线（只能离线填写后上传）。而第二封函恰恰是「前任会计师拒不回复」这一**异常路径的证据** ——
最需要留痕的场合退化成离线上传，审计证据链断一环。

**选 OPT-SPLIT 的代价可验证**：
- 新增 `wp_code` —— 牵动 `wp_index`、`wp_code_overrides.json`、前端注册
- Task 58 清册行数与 Requirement 7.7 的「9 个子码」数字需同步复核

两者都是机械的、可被判据锁死的工作。

**编码建议**：`B2-3-1` / `B2-3-2`。理由：「第一封 / 第二封」是**序号关系**而非变体关系，
平台已有三级子码先例（`B22A-4-4-1`）；不建议 `B2-3` / `B2-3B` 那种变体形态（`B60`/`B60B` 是
变体语义，会误导）。最终编码由业务方确认。

### BP-20 —— 真正的瓶颈，需要**底稿模板编制方**介入（不是代码工作）

🔴 两份 B2-3 的 `dollar_token_count` 均为 **0**，`w_tbl_count=1` / `w_tr_count=1` ——
**模板里没有任何 `${token}` 占位符**，无法建立字段身份。

JSON 明写：

> 在 **BP-20**（字段身份基础不合法）未解除前，**无论选哪个方案都发不出契约**。

这与 9 个 B 子码同源。Task 63 正文的解除条件是：

> 需底稿模板编制方为这 9 份引入 `${token}`，或逐份裁定每个 `××` 的业务含义。

**结论：BP-19 定 OPT-SPLIT 只解除「方案未定」这一层，实际发契约还要等模板编制方给占位符。**
这条不在工程团队能力范围内 —— 需要把「哪些 `××` 对应哪个业务字段」逐份问出来。
建议 A 单独起一份「Word 模板占位符补全清单」交业务方，9 个 B 子码 + B2-3 两封函共 11 份。

**清单已产出**（2026-09-04）：

- 交业务方填写：`docs/operations/word-template-placeholder-completion-list.md`
- 机器可读（业务填回后作落地依据）：`backend/data/word_template_placeholder_completion.json`
- 生成器（模板变动后重跑刷新）：`backend/scripts/gen/generate_word_placeholder_completion_list.py --apply`

生成器用**解析器本身**（`wp_docx_template_parser.parse_template`）抽取，保证清单里的位置与
生产代码实际看到的逐一对应，不手搓正则。现算结果：

```
载体 11 份（10 个 entry，B2-3 有两封函各一份）
  缺文件           1 份  S33-REV（裁决为 template_missing）
  解析出 0 个空     2 份  B40-1 / B40-2（与裁决 JSON 的 zero_structured_field_entries 一致）
待补全占位符      12 个
现有 ${token}      0 个  ← 与裁决 JSON 的 dollar_token_total = 0 交叉验证一致
```

12 个占位符的语义已按上下文推断出建议名（业务方确认或改写）：

| 建议字段名 | 个数 | 出处 |
|---|---:|---|
`arbitration_commission` | 2 | B18-3-1 / B18-3-2 的「提交【××】仲裁委员会仲裁」 |
`fiscal_year_yy` | 4 | B2-1 #1、B2-6 #1/#2/#3 的「【20××】年度财务报表审计业务」 |
`sign_date_yy` | 6 | B2-1 #2、B2-11、B2-3 两封、B2-6 #4、B2-8 的签署日期 |

### 🔴 抽取过程中发现的第二类问题：单个 `×` **根本没被识别**

BP-20 描述的是「字段身份不稳定」。实测还有一类更硬的：

```
双 ×（××）被识别为占位符      12 个
单 ×（孤立的 ×）完全未被识别   12 个
```

12 个未识别的全部集中在签署日期：

```
【20××】年【×】月【×】日
     ↑↑        ↑     ↑
   被识别    看不见  看不见
```

`_LEGACY_PATTERNS` 只有 `(r"××", "placeholder_generic", "待填内容")` 一条 —— 单个 `×`
不匹配。后果是**双向回写启用后，审计师能在线填年份，但月和日永远填不了也存不下**。

BP-20 说的是"身份不稳定"，这个是"根本没有身份"。清单里已单列一节，建议整个日期
合并成一个 `${sign_date:签署日期}` 日期字段（程序会按日期控件渲染），不必拆成年/月/日三个。

### 关于 BP-19 与本清单的关系

裁决 JSON 的 `legacy_chinese_derived_total = 11`，而本清单现算 **12** —— 差的正是
**B2-3 第二封函的那 1 个**。JSON 只统计了 resolver 选中的第一封（见其
`unreachable_in_word_domain`）。本清单覆盖两封，是按 **OPT-SPLIT** 的口径准备的：
若最终采纳 OPT-SPLIT，两封函都需要命名；若采纳 OPT-PRIMARY，第二封那一行可划掉。

### 汇总：谁需要谁的确认

| 编号 | 性质 | 谁来解 | 卡住谁 |
|---|---|---|---|
BP-18 | **派生状态，无需裁决** | 随 A 的 L1（Tasks 75/76）完成自动解除 | Task 63 第一条 bullet |
BP-19 | **工程可决，推荐 OPT-SPLIT** | A 提方案，业务方确认编码 | Task 63 |
BP-20 | **需业务输入，代码无解** | 底稿模板编制方给 11 份模板的 `${token}` 或 `××` 语义 | Task 63、B2-3 双封函的契约发布 |

另注：主 spec 的 Task 75 / 76 / 74 曾从 `[x]` **退回 `[-]`**，理由写的是「假绿更正，非回退」。
说明这三条曾被判完成后又发现判据不实 ⇒ **剩余量比编号看起来大**，接手时先复算判据再动手。

## 8. 里程碑

| 里程碑 | 判据（可机械复算） | 责任人 |
|---|---|---|
M0 复选框对齐 | 三个 spec 的复选框与生产引用关系一致 | A |
M2 插行可用（🔴 **实测为 M1 前置**，见 §11.2） | `plan_managed_writes` 里出现 `row_shift`；D2 的 729 行能真实插入并通过 shift-aware 验证 | B |
BP-21 「……」排版占位行裁决（🔴 **新增，同为 M1 前置**，见 §11.3） | `resolve_managed_region` 派生 `last_row` 时剔除纯省略号行；H1 受管区 15 → 14 行；170 处 / 37 份模板的形态有统一处置 | A 提请 · B 落地 |
M1 首版落库 | `content_representation` 里有 H1 / D2 的 `projection` lane 记录；`capability_counts.bidirectional > 0` | A |
M3 传播可用 | K11 的 114 处跨 sheet 引用在插行后逐处正确；137 份可达性清册产出 | C |
M4 模板可编辑 | 476/476 可覆盖可回滚；349 份可浏览器内编辑；权威目录 476 份 sha256 逐份不变 | D |
M5 判据归零 | `check_workpaper_writer_revision_gate.py` 14 条准则全为零；五个 spec 变异全 RED | E |
**M6 全量双向** | manifest 的 `bidirectional` 计数达成目标；186 个 entry 各有能力态与验收态 | A 汇总 |

---

## 9. 变更记录

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-04 | 建立本分工书。五个 spec 机器校验与自洽性审计均 0 问题；文件占用面与三处碰撞点已实测登记 | A |
2026-09-04 | **L2a 泳道自证对齐（S spec）+ Wave 0/1 收口**。§4 要求的 M0 由 A 汇总；本行只登记 B 自己泳道的实测结果，不代 A 宣布全局 M0。详见下方 §9.1 | B |
2026-09-04 | **✅ M0 复选框对齐完成，B / C / D / E 可开工。** P `1/43 → 6/43`、S `0/27 → 6/27`、T `3/27` 核实无需改动。五个 spec 分母复算 43+27+27+27+77 = **201**，与 §1 表一致；`# Implementation Plan:` / `## Task Dependency Graph` / waves 五字段 / 纯整数任务号四项结构校验全过。详见 §10 | A |
2026-09-04 | 🔴 **L1 实测：四个 pilot entry 一个都发不出首版，且 §3 的关键路径判断方向是反的 —— M2 是 M1 的前置。** 详见 §11。同时修掉宿主 `--check` 的假绿（6 → 10 阶段、词表 6 → 11 格、删两处误导性兜底），`--check` 与 `--apply` 现在结算逐项相同 | A |
2026-09-04 | ✅ **M1 达成**：`projection_contract` lane published representation **0 → 1**（G7，10/10 全链，幂等已验）。解锁靠修掉四处「空集上恒真」的接线错误 + 消除 entry→wp_code 的第三份真源。详见 §12 | A |
2026-09-04 | 📄 **BP-21 已正式提请 B**，交接件 `docs/operations/bp-21-managed-region-typography-row-handoff.md`（自包含）。验收判据从「全库清册数」更正为「§B 逐 pilot 受管区扫描」—— 前者恒 170 不随修复变化，拿它当验收永远打红。判据现读 `resolve_managed_region` 真实返回值，落地前 **退出码 1 / 区内占位行 2 行（H1 A27、D2 A25）**，落地后应为 0。**A 不动 `excel_extract.py`**（B 独占，且 B 此刻正在 Wave 3 编辑该文件） | A |
2026-09-04 | **L2b Wave 0 收口（5/27）。** 四个 Open Gate 全部实测裁决（Task 1~4 `[x]`）；Task 101 就绪门交付（18 例绿 / 变异 **9-9 RED**），**判定门关闭**（上游 Wave 4 的 16/17/18 现读均 `[ ]`）。裁决改动三处设计 + 新增 5 条 AC / 5 条 Property。⚠ 向 A 报五件事（含 §10.3 那条正则的**二次修正**），详见 §11 | C |

---

## 10. M0 对齐结果（2026-09-04 · A）

对齐判据一律 **真实执行**，不是"文件存在"、不是记忆。

### 10.1 逐 spec 结果

| spec | 原 | 现 | 依据 |
|---|---|---|---|
P | 1/43 | **6/43** | `--check` 真跑，四个 entry 结算分布 `{ready_to_publish: 2, blocked_ooxml_gate: 1, blocked_missing_approved_bundle: 1}`；裁决层两条自检真跑 PASS |
S | 0/27 | **6/27** | 真实 K11 模板上真跑位移：`<row>` 37 → 39、`renumbered_cells=174`、6 组 si 索引全解出、纯函数成立 |
T | 3/27 | **3/27**（不动） | 3 个 `[x]` 恰是 Wave 0 三个 Gate 裁决；N1/N2/N3/M1/M2/M3/T1~T5 十一个记号的文件磁盘一个都不存在 |

**P 勾上**：1.3（双向锁 + 无第二真源，且 AST 确认 `assert_registry_covers_opaque_lanes()` 是模块级
表达式 ⇒ import 期真跑）· 2.1（供给四判据，G7 落"判据 A 不成立"并给出解除动作）· 4.1（五条准入，
四 entry 落四种结局）· 4.3（暂存 + 安全门，B60 以 `gate=external_relationships` 被拒）·
6.1（`--check` 六阶段 + 封闭词表 + `--json`）

**P 不勾**：4.5 / 6.3 —— 实现在磁盘但 **commit 腿从未执行**（`--check` 只跑到 loader+adapter），
A 跑完 `--apply` 后再勾。全部 `*` 测试子任务不勾：**F6~F9 四个测试文件磁盘不存在**（15 条）。

**S 勾上**：2（`_SHEET_STRUCTURE_BLOCKS` 6 → 10）· 4（清单 12 项 + 差集显式登记 + 覆盖断言真跑
PASS）· 5（三类非法取值三个互不相同 `error_code`；`ShiftReport` 8 字段）· 6 · 7 ·
8（si=1 主格 `H8` / `ref=H8:H25` / 17 成员）

**S 不勾**：Task 1（影响面 JSON 快照磁盘无产物）· Task 3（Wave 0 门无可复算证据）· 9~22
（`excel_extract` 三个 digest 函数**无 `row_shift` 参数**；`excel_materialize` / `contracts` /
`adapters/excel` 对 `row_shift` / `RowShiftPlan` / `carries_total_formula` **零 token**）

### 10.2 🔴 全员必读：五个"已交付"的生产文件在 git 里未跟踪

`git status --porcelain` 实测（**不是**看文件在不在）：

```
??  backend/app/services/workpaper_sync/excel_row_shift.py              ← S 的 N1（B 泳道地基）
??  backend/app/services/workpaper_sync/excel_sheet_visibility.py       ← T 的前置（D 泳道复用）
??  backend/app/services/workpaper_sync/projection_lane_registry.py     ← P 的 F1（A 泳道地基）
??  backend/app/services/workpaper_sync/projection_first_publication.py ← P 的 F2
??  backend/scripts/fix/fix_projection_first_publication.py             ← P 的 F3（唯一宿主）
??  backend/scripts/check/check_managed_region_typography_rows.py       ← BP-21 取证/验收
??  docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md ← 🔴 **本文档自己**
??  .kiro/specs/excel-structural-row-insertion-…/tasks.md               ← B 的 spec 目录
??  .kiro/specs/excel-template-override-layer-…/tasks.md                ← D 的 spec 目录
??  .kiro/specs/excel-workbook-wide-row-change-…/tasks.md               ← C 的 spec 目录
 M  backend/app/services/workpaper_sync/excel_extract.py                ← S 的 Wave 0 改动
 M  backend/app/routers/wp_onlyoffice_router.py                         ← sheet 可见性的接线
 M  .kiro/specs/published-representation-…/tasks.md                     ← A 的 spec
```

`git cat-file -e HEAD:<path>` 逐条复核：前五个 **HEAD 里不存在**。

🔴 **协调五个人的这份分工书自己也没入库**，B / C / D 三个 spec 目录同样是 `??`。
只有 A 的 spec 是 `M`（目录已跟踪）。⇒ 现在丢一次工作树，损失的不只是代码，
**还包括「谁负责什么、判据是什么、已经查清了哪些事实」这层信息本身**。

后果两条，与规则 7 第 3 项同源但更严重：

1. **丢工作树即三条泳道的地基同时蒸发** —— A 的 L1、B 的 Wave 1、D 复用的 sheet 可见性。
2. 任何挂进 `governance-checks.yml` 的 job 在干净 checkout 下**必挂**（文件不存在）。

**A 不代各泳道提交**：`excel_extract.py` 与 `wp_onlyoffice_router.py` 是 `M` 状态，一并提交会把
并发会话的在途改动扫进来 —— 那正是本仓库已发生过的事故形态。各泳道按规则 7 自己 `git add`
自己的产物清单。A 只负责在此登记并盯到入库。

### 10.3 对齐时顺手修正的一条判据缺陷

多处判据在用的复选框正则 `^\s*-\s\[([ x~-])\]\s+\d+\.` **漏掉 `- [ ]* 1.2` 形态**
（`]` 后紧跟 `*`）：P 少算 15 条、S 少算 5 条，报出来的分母是错的。正解：

```python
re.compile(r"^\s*-\s\[([ x~\-])\]\*?\s+\d+\.", re.M)
```

C 的 Task 101 要现读 B 的 tasks.md 断言 Wave 4 三条为 `[x]` —— **务必用修正后的正则**，
否则将来若写成 `[x]*` 形态会被漏读（当前 Task 16/17/18 是普通 `[ ]`，暂不受影响，别埋这个坑）。

<!-- 后续变更追加在此。 -->

---

## 10. E 泳道首份报告（2026-09-04）

> 全部数字为现读实测，附取证方式。三件需要 A / D 处理，见 §10.4。

### 10.1 已交付

**`backend/scripts/diagnose/mutate_task61_bootstrap_guards.py` 迁移到 `_mutation_kit`**
（`--run all` 实测 **11/11 RED**、覆盖面 **1/1**、退出码 0；`.mutbak` 残留 0；
三个被变异目标 `git status --porcelain` 空 = 完整复原；守卫基线仍 31 passed）。

迁移修掉**三个实缺陷**，都属「按退出码判定」这一形态的必然产物：

| # | 缺陷 | 后果 |
|---|---|---|
1 | 原 `run_all()` 判定只有 `"GREEN" if code == 0 else "RED"`，**四态里的 WRONG-TEST 分支根本不存在**（docstring 却声明四态；捕获的 `out` 从未使用） | 变异造成收集错误、或打红的是别的判据，一律记 RED |
2 | M04 的 `expect_test` 是**裸类名**（无 `::`），命中 `else str(_TEST)` 回退分支 ⇒ 实际跑整个守卫文件 | 判据强度与其余十条不同且无声，文件内任何失败都算 RED |
3 | 🔴 **M11 的 `want` 类名是错的** —— `test_a_lane_with_a_different_entry_id_scheme_is_rejected` 实际住在 `TestEvidenceLedgerIsRealAndComplete`，原写 `TestNoBypassAndNoBusinessRowWrites` | 迁移首跑当场判 WRONG-TEST 才暴露。原实现结构上不可能发现：变异确实打红了那条测试、退出码非零 ⇒ 记 RED |

缺陷 3 值得单列成规则：**WRONG-TEST 有第三种成因** —— 不只是「锚点错行」与「污染残留」，
还有「`want` 声明与守卫实际结构不符」。它也说明为什么判定必须走**失败名集合差集**：
按退出码判时，「判据写错」与「判据正确」在报告里逐字相同。建议补进 §6 规则 4。

**Task 74 标题去过期**：原写「236 未裁决与 261 绕过统一 commit」，而 `unadjudicated_writer`
现读已是 **0**。改为不携带易变计数的持久形态。改前核实整行唯一、全仓无守卫解析该标题；
改后 `git diff --numstat` 由 95/8 变 **96/9**（A 的在途改动完好，我恰 1 行）、复选框仍
70 `[x]` + 7 `[-]` = 77、`test_task20_writer_gate.py` 失败集逐条不变。
**Task 20 的 14 个冻结数字与 live gate 现算一致（646），未动。**

### 10.2 三条实测结论，修正分工书的三处判断

**① E 不是并行泳道，是终端泳道。** §3 的图把 E 与 A/B/D 并列为「可完全并行」，实测不成立：
五个 spec 的变异任务全部排在**最后一波**（P spec Wave 14 `depends_on: [13]`、S spec Task 20、
T spec Task 5+23、W spec Task 7+20+26），且 `backend/tests` 下**零个**测试文件引用
`projection_first_publication` / `projection_lane_registry` ⇒ P spec 守卫尚不存在。
变异脚本必须有守卫可打红，所以主线二在 B/C/D/A 交出守卫之前**一条都做不了**。
建议 §3 把 E 画在汇聚处，并明确「E 的产出速度由上游守卫交付速度决定」。

**② Task 74 的剩余量与 §5 的描述不同。** `unadjudicated_writer` 实测已 **236 → 0**
（§5 仍写「实测 236 行」）。默认命令现读退出码 1、**646** 条 blocking facts、14 条准则里 **6 条非零**：
`bypasses_unified_commit` 261 / `writer_without_characterization_test` 208 / `owns_direct_commit` 105 /
`non_canonical_resolver_only` 63 / `writes_legacy_version_field` 5 / `multi_resolver` 4。
其中 `multi_resolver` 归属 **Task 71**（不是 74），其 4 行全在 `wp_onlyoffice_router`；
`writes_legacy_version_field` 的 5 行里也有一行在该文件。**两者都在 D 名下的文件里** ⇒
Task 74 的完成判据（14 条全零）**结构性地要等 D 收口 + A 接手 Task 71**，
剩余 642 行是「逐 writer 迁 `ContentMutationService` + 逐行补 characterization test」，
adapter 供给在 Wave 5–7。**Task 74 不可能早于 M4 完成**，建议在 §8 里显式标出这条依赖。

**③ 共享 kit 采纳门是红的，且 12/20 不在 E 名下。** `governance-checks.yml:5279` 挂着
`test_mutation_kit_adoption.py`，`test_new_scripts_must_use_the_shared_kit` 实测失败、
**20 条违规**（现已 19，见 §10.1）。冻结名单 `_LEGACY_NOT_REQUIRED` 19 条 + `_FROZEN_SIZE=19`
**只许缩小、不接受新条目** ⇒ 唯一合规解是迁移，不能登记豁免。20 条全部入库于冻结日
2026-08-16 **之后**（门是对的，是真实欠账）：**E 名下 8 个 / 3653 行；其他 spec 12 个 / 3605 行**
（dsh_agent_panel 1056、advanced_query_scope_budget 680、mention_field 354、
frontend_reference_integrity 268、disclosure_notes 257、frontend_dangling_reference 207 等）。
⇒ **只修 E 的 8 个，CI 仍红。** 需要 A 跨 spec 排期。

### 10.3 但不建议现在批量迁移 —— 缺陷面已量化

先做了一遍只读审计再决定，结论与直觉相反：

- **`want` 声明可解析性：7/7 脚本已测量、196 条声明、0 条不可解析。**
  task61 的类名错是**孤例，不是系统性缺陷**。
- `mutate_task4_*` / `mutate_task7_*` **已有真差集四态**（`expected & set(failed)` → RED、
  有失败但不交 → WRONG-TEST、无失败 → GREEN）+ 基线全绿门 + `finally` 还原 + sha256 自证。
- `mutate_task71_chaos_*` 宿主按 `-rfE` 的 FAILED/ERROR nodeid 判四态（**不看退出码**），
  且有**逐变异 md5 复原校验 + 收尾再校验** —— 这一项**比 kit 更强**。
  它的两个真缺口是：判定用**绝对**失败集合而非 `current − baseline` 差集（守卫本身已红时
  任何变异都判 RED），以及无覆盖面分母。

⇒ 六个存量脚本的普遍缺口**只有覆盖面分母**。迁移是**合规任务，不是纠错任务**，
应按 lane 收口排期，不必抢工；抢工反而有丢掉 md5 自证等既有能力的风险（Property 26 等价性）。

**顺带两条门自身的假阳性**（判据缺陷，建议登记而非绕开）：
① `check/mutate_common.py` 是 harness **库**、按设计无 `run_cli`，却因文件名匹配 `mutate*.py` 进了分母；
② 合法复用他脚本 runner 的从属脚本（`mutate_task71_census_lock_guards.py` 刻意
`_host.run` / `_host.check_anchors` 不抄第二份）因未直接 import kit 被判违规 ——
而那正是门想鼓励的反重复行为。

### 10.4 🔴 需要处理的三件

**（一）D↔E 碰撞：D 在途重构 `wp_template_finder` 令 E 的 overlay 失效，1 个改动打红 9 条判据。**

D 正在改 `backend/app/services/wp_template_finder.py`（` M`，mtime 2026-09-04 16:58）：新增
`find_template_file_unresolved`(L118) / `find_all_template_files_unresolved`(L240) /
`find_template_file_any_unresolved`(L299)，把公开的 `find_all_template_files`(L401) /
`find_template_file_any`(L411) 改成薄委派。于是生成器的发现谓词不再把这两个公开函数判为
resolver，它们从 `rows` 掉出，**E 的 `workpaper_writer_domain_overlay.json` 里那两条裁决成了孤儿**，
`build_inventory` 直接抛 `WriterInventoryError: overlay adjudicates writers that no longer exist in source`。

爆炸半径（只算不写盘，遵守 §6 规则 3）：现源码 **317** 行 vs overlay **319** 条裁决；
孤儿**恰 2 条**，全在 D 的文件上；**新增未裁决 0 条**（`_unresolved` 变体未被判为 writer/resolver）；
删掉这 2 条后 `unadjudicated_writer` / `unadjudicated_resolver` **仍为 0** ⇒ 不会打掉 Task 74 唯一成果。

连带打红 **9 条**（实证：5 FAILED 全抛同一个 `WriterInventoryError`，4 ERROR 在 setup 期抛）：

```
test_task20_writer_gate.py        ::test_the_lane_is_part_of_the_freshness_contract          FAILED
                                  ::test_the_snapshot_category_is_exactly_the_snapshot_...   ERROR
                                  ::test_writers_that_also_snapshot_do_not_get_the_category  ERROR
                                  ::test_the_frozen_red_baseline_is_derived_from_the_live... ERROR
test_task74_domain_adjudication.py::test_adjudicating_clears_exactly_two_criteria            FAILED
test_workpaper_writer_inventory.py::test_stale_inventory_is_rejected_rather_than_evaluated   FAILED
                                  ::test_dropping_a_row_cannot_make_the_gate_greener         FAILED
                                  ::test_generator_refuses_an_unverifiable_retirement        FAILED ←
                                  ::test_inventory_on_disk_matches_the_ast                   ERROR
```

← 那条尤其值得注意：它**预期的错被孤儿错抢先掩盖**（`Regex pattern did not match`），
即这次碰撞不只让判据变红，还**遮住了另一条判据本该验证的东西**。

**HEAD 没有这个问题**，是纯工作树态：本会话**开头**跑 `check_workpaper_writer_revision_gate.py` 时
`assert_inventory_is_current` 通过、`rows=319` 与磁盘一致；现在源码只出 317 ⇒ D 的编辑发生在会话期间。

**E 不在移动目标上修。** 按 §6 规则 3 的同一逻辑（生成器只在收口重跑），overlay 重新对齐
也应在 **D 收口时**做：D 的函数集合还会动，若最终形态又把这两个判回 resolver，现在删了还得加回来。
修法已备好、恰 2 行：删 overlay 的 `app.services.wp_template_finder::find_all_template_files`
与 `::find_template_file_any` 两条裁决（L1255 / L1259 起）。**请 D 收口时通知 E，E 当轮执行并重跑生成器。**

顺带一条通用教训，建议补进 §6 规则 3：该规则现在只说「改 `backend/app/**` 会让 inventory 变 stale」，
实测形态更硬 —— **把公开函数改成薄委派会让它从发现谓词里消失，从而使他人 overlay 里的裁决成为孤儿、
生成器硬失败**。stale 是可重生成的，孤儿是要人裁决的。

**（二）请 A 排期跨 spec 的 kit 采纳迁移。** E 已交 1 个（20→19），E 名下还剩 7 个；
另 12 个属其他 spec，E 按 §6 规则 1 不碰。在这 12 个处理掉之前该 CI job 一直红。
建议：各 lane 收口时迁自己的，A 汇总；或单独立一份小 spec 收口，同时修 §10.3 的两条门假阳性。

**（三）BP-18 / Task 74 的依赖链请在 §8 里显式化。** §7 已把 BP-18 定性为「随 L1 自动解除」，
但里程碑表里 M5（判据归零，E）没有标出它依赖 M1（首版落库，A）与 M4（模板可编辑，D）。
按现读判据，`check_workpaper_writer_revision_gate.py` 的 14 条全零**不可能早于 M4**。

### 10.5 E 的下一步

在上游守卫到位之前，E 可继续做且零冲突的只有：
存量脚本按 §10.3 的排期迁 kit（自己名下 7 个）、以及 D 收口后当轮执行 §10.4（一）的 overlay 对齐。
Word 域（Task 63 第二条 / Task 61 判据侧）等 L1；BP-20 需业务方给 11 份模板的 `${token}`，代码无解。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-04 | E 泳道首份报告：交付 `mutate_task61_bootstrap_guards.py` 迁 kit（修 3 个实缺陷、11/11 RED）+ Task 74 标题去过期；报 D↔E overlay 孤儿碰撞（1 改动→9 条红）、kit 采纳门 CI 红（20→19，余 12 属他 spec）、E 实为终端泳道而非并行泳道 | E |

## 11. C 的 Wave 0 回报（2026-09-04 · L2b 工作簿级行变更传播）

进度 **5/28**（Task 1~4 `[x]`、Task 101 `[~]` 门已建成判定关闭；任务总数 27 → 28，
Wave 0 实测补入 Task 27，见 §11.7）。全部产物在 C 的独占面内，
未碰任何他人文件（`git status --porcelain` 逐条复核：`excel_extract.py` 的 `M` 与
`excel_row_shift.py` 的 `??` 都不是 C 改的）。

**产物清单**（规则 7 第 3 项：`??` 已登记待入库）

```
??  .kiro/specs/excel-workbook-wide-row-change-propagation/{requirements,design,tasks}.md
??  backend/tests/workpaper_sync/test_workbook_row_change_upstream_gate.py   ← T5，CI 可跑
```

机器校验：**10** Requirement / **61** AC / **38** Property（1..38 无空洞无重复）/ **28** 任务 /
waves 自洽 / **悬挂 AC 0 条**。

---

### 11.1 🔴 原登记的 8 个分母有 4 个复算不上

扫描口径复用生产分词器（`excel_row_shift._QUALIFIED_PREFIX_RE` / `_REF_TOKEN_RE` /
`_STRING_LITERAL_RE` / `_left_boundary_ok` / `_BARE_TOKEN_RE`）+
`excel_structure_fingerprint._parse_workbook_xml` / `_normalise_part`，**未手搓正则**。

| 分母 | 原登记 | C 复算 | 判读 |
|---|---:|---:|---|
| xlsx 总数 | 351 | **351** | ✅ |
| K11 受管 sheet 被引用处数 / 不同行数 | 114 / 19 | **114 / 19** | ✅ |
| A2-1「调整事项汇总表」 | 9,744 | **9,744** | ✅ |
| A3-1「报表格式」 | 3,137 | **3,137** | ✅ |
| 含跨 sheet 引用的 xlsx | 176 | **182** | ❌ |
| 跨 sheet 引用处数 | 81,955 | **144,154** | ❌ |
| 表名形如 A1 的引用处数 | 16,027 | **15,066** | ❌ |
| 受影响模板 / 受影响 sheet | 137 / 604 | **136** / 无一口径命中 604 | ❌ |

规律很清楚：**逐 sheet 指向具体对象的数字全对，库级聚合量全错** ⇒ 差异出在聚合口径，
不是扫描器。两条佐证：

1. 主 spec 的 design.md 写「**188 份**模板 81,955 处引用」，而本 spec requirements.md 写
   「**176 / 351**」—— 两处原本就互不一致；
2. requirements 把 `可改名` 列为占位标记，但它在全库 351 份 xlsx 里**命中 0 次**
   （只出现在 docx / md 侧）。只用原列六个标记算得 **101 份**；扩到 12 类标记才算得
   **136 ≈ 137** ⇒ 当初扫描用的标记集比文档写的宽。

C 已在自己 spec 的 design.md 建「分母断言」表（19 个分母 + 逐条口径定义 + 12 类占位标记
命中表），并在 tasks.md 明令**判据不得引用那五个数字**。
**其它泳道若也引用了这些数字，请一并复算。**

### 11.2 🔴 §10.3 那条正则还需二次修正（会让 C 的门永久关闭）

A 在 §10.3 给的修正 `re.compile(r"^\s*-\s\[([ x~\-])\]\*?\s+\d+\.", re.M)` —— `\*?` 完全正确，
C 已采纳（漏了它对上游少读 **5** 条）。但**编号只捕前导整数 `\d+` 仍有问题**：

上游的 `*` 子任务编号是 `2.1` / `5.1` / `6.1` / `8.1` / `10.1` 形态，`\d+\.` 只吃到前导整数
⇒ `- [ ]* 2.1` 被读成「任务 **2**」。实测后果：

```
只捕前导整数：27 条，重复 id = {2: 2, 5: 2, 6: 2, 8: 2, 10: 2}   ← 五组假重复
捕完整  id ：27 条 = 22 顶层 + 5 子任务，重复 id = 无
```

对 C 的门是致命的：门有一条「同 id 重复即 fail-closed」（防行首锚定失效），假重复会让它
**误触发并永久关闭**。正解是把编号捕成完整 id：

```python
_CHECKBOX_RE = re.compile(r"^\s*-\s\[([ x~\-])\]\*?\s+(\d+(?:\.\d+)*)\.?(?=\s|$)")
```

并且**用字符串 id** 而不是 int 做键 —— `"16"` 与 `"16.1"` 是两个不同任务。
C 的门已按此实现，并加了两条回归判据（`test_star_marked_subtasks_are_read_and_not_collapsed`
/ `test_whole_upstream_file_parses_to_expected_shape`）与两条变异（M6 漏 `\*?` / M7 只捕前导
整数），均 RED。**建议 A 把 §10.3 的推荐写法更新成上式** —— 各泳道若按原式做「重复检测」
类判据都会踩到。

另附一条给 E 的变异四态经验（建议并入 E 的统一标准）：Wave 0 踩到两类**无效变异用例**，
它们会被误判成「守卫缺陷」从而去改本来正确的守卫 ——

- **被收敛语义掩盖**：判据里「同编号保留最后一次」的收敛，让「行首锚定失效」这个变异结果
  不变 ⇒ 改成「收集全部出现次数 + 重复即 fail-closed」后变异才敏感；
- **被第二道防线挡住**：正则里的 `^` 与调用侧的 `.match` 互为冗余（`re.match` 自身锚定
  位置 0），单独改任一个都被另一个挡住 ⇒ 必须做**组合变异**；
- **分母断言的正确变异形态是把期望值改错**（证明它真被求值），不是删掉或放宽 ——
  后者只会让测试恒过、必判 GREEN 且毫无信息。

### 11.3 🔴 K11 是动机样本但不是可执行样本 —— 建议 A 定 L1 的排序

`DELIVERED_PER_ENTRY_CONTRACTS` 现读只有 **4 行**（b60 / d2 / g7 / h1），**K11 不在其中**。
而 `excel_extract.resolve_managed_region` 的唯一区域边界锚点是 **Excel Table displayName**，
全库 351 份 xlsx 里含 Excel Table 的只有 **1 份**（`C24` 的 `_2025__2`，与受管无关）——
Table 是 `excel_instrumentation` **注入**的，不是权威模板自带的。

⇒ 「受管 sheet 可知」的充要条件 = **该 entry 有已审核契约**，与模板长什么样无关。
Gate 1 因此裁决：**禁止启发式推断**（歧义度实测：每份受影响模板含占位标记的 sheet 张数
中位数 **4**、最多 **18**；猜错受管 sheet 产出的 xlsx 仍能打开、公式仍有值、只是值错了 ——
那正是本 spec 要消除的静默错行），其余一律 `blocked` + `no_projection_contract`。

这 4 个契约 entry 里**只有 D2 有真实跨 sheet 引用**：

| adapter | 受管 sheet | anchor | 宿主 | 被本工作簿其它 sheet 引用 |
|---|---|---|---|---|
| `b60.hour_budget` | `B60-1工时预算与控制表` | A5 | `B/B60-1 …xlsx` | **0 处** |
| `d2.receivable_detail` | `明细表D2-2` | A11 | `D/D2-1至D2-4 应收账款….xlsx` | 🔴 **52 处**（4 张引用侧，行 13/25/26） |
| `g7.soe_subsidiary_disclosure` | `附注披露信息（国企）` | A78 | `G/G7 长期股权投资.xlsx` | **0 处** |
| `h1.disposal_check` | `减少检查表H1-8` | A10 | `H/H1 固定资产.xlsx` | **0 处** |

C 已把首要判据载体由 K11 改为 **D2**，K11 降为结构判据载体（100% 阻断形态）。

**对 A 的建议**：L1 首版发布目标是 **H1 / D2**。按上表，**H1 无任何跨 sheet 引用（0 处）
而 D2 有 52 处** —— 若想让 L1 与 L2b 尽早联调，**D2 是唯一能同时验证「首版发布」与
「工作簿级传播」的 entry**；若只想先把 `bidirectional > 0` 跑通，H1 风险更低。
两条不冲突，只是排序上值得先定。

另附一条对全员有用的实测：🔴 **sheet 名不是全库唯一，禁止按 sheet 名定位宿主模板。**
`附注披露信息（国企）` 在 **39 份**模板里都存在，且被引用情况完全不同（G7 宿主 0 处，
`L/L5 长期应付款.xlsx` 里有 5 个被引用行）。C 已为此新增 AC 6.5 + Property 36。

### 11.4 🔴 Requirement 4.2 点名的四类载体结构性不存在

`conditionalFormatting@sqref` / `dataValidation@sqref` / `mergeCell@ref` / `hyperlink@ref`
的 OOXML 类型是 `ST_Sqref` / `ST_Ref`，语义上就是所在 worksheet 内的区间，**表达不了
sheet 前缀** —— 全库实测 `0/440`、`0/1223`、`0/37456`、`0/3950`，取值形态逐一印证
（`H7:M7 C7:F7 J7:J48` / `A1:R1` / `X3`，无一带 `!`）。

真载体是**另外三类 + definedNames**：

| 载体 | 总条数 | 含跨 sheet | 命中模板 | 样本 |
|---|---:|---:|---:|---|
| `hyperlink@location` | 3,764 | **3,480** | 158 | `底稿目录!A1` |
| workbook `definedNames` | 63,973 | **5,002** | 341 | `财务费用` → `Word附注!$B$2010` |
| `dataValidation/formula1\|2` | 1,094 | **8** | 4 | `Data!$B$2:$B$3` |
| `conditionalFormatting/formula` | 552 | **6** | 1 | `$F11=Data!$B$3` |

definedNames 的 5,002 条**必须按五类分解**（处置各不相同）：`builtin_self_scope` **2,457**
（Print_Area/Print_Titles 指向自己那张 sheet，插行后打印区域要跟着长 ⇒ 传播）·
`target_not_in_workbook` **1,991**（`'[4]2004'!#REF!` 外部残留 ⇒ 登记）· `user_self_scope`
**292**（传播）· `user_cross_sheet` **252**（🔴 R4.1 真正的对象）· `builtin_other_sheet` **10**。

另两条：`xl/pivot*/**` 全库 **0** 部件 ⇒ 原 R4.3 的 pivot 判据会在空集上恒真，必须用真实模板
zip 级注入变体；`xl/charts/**` 有 **8** 个部件 / 1 份模板，可用真实样本。

⚠ 实测踩坑一条：扫整个 `<dataValidation …>` 元素会把 `error=` 属性里的中文提示
（「请从G7-14名称列表…」）当成跨 sheet 引用 —— **只能扫 `<formula1>` / `<formula2>` 的内容**。

C 已据此改 R4.2 的语义（从「同样传播」改为「必须不被误传播 + 注入变体取证」）并新增
AC 4.5 / 4.6 / 4.7 + Property 32 / 33 / 34。

### 11.5 性能与删行两个 Gate 的裁决（无需 A 介入，登记备查）

**Gate 3 性能 —— 不异步化、不登记 blocked，阈值 2,000 ms。**
🔴 实测发现比登记更极端的样本：`C/C24 会计分录 - 细节测试.xlsx` 的 `2025假期清单` 被引用
**63,240 处** = 原登记最极端 9,744 的 **6.5 倍**。传播上界（读 zip + 全工作簿每个 `<f>` 过一遍
生产改写器 + zip 重打包）：C24 **1,158 ms** / A2-1 **201 ms** / A3-4 **181 ms** /
A3-1 **163 ms** / K11 **7 ms**。另测得耗时由**公式文本长度**主导而非条数
（A2-1 的 16,179 条只用 144 ms，C24 的 10,906 条用了 1,063 ms）⇒ 性能判据的自变量必须是
**引用处数**。

**Gate 4 删行 —— fail-closed 保留，但补第三态「不可删行」（新增 AC 3.8 / Property 35）。**
K11 受管区 `A7:N25` 共 19 行，被引用行落在区内 **19/19 = 100%** ⇒ 只有 fail-closed 抛错的话，
K11 这类底稿的删行功能表现为「**永远失败**」。全库代理统计 172 个组合中 **82 个（47.7%）**
的被引用行 span 内 100% 全被引用 —— 不是个别形态。⇒ 计划阶段前置产出 `undeletable_rows`，
让 HTML 侧在**发起删行之前**把这些行标成锁定（同一条 fail-closed 语义的可用形态，
**不替代**后端拦截）。对今天的 4 个契约 entry：D2 有 3 行不可删、其余三张 0 行
⇒ **删行不因本 Gate 阻塞**。

### 11.6 C 的下一步与阻塞

- **阻塞点**：Wave 1（Task 5 / 6 / 7）依赖 M0 ✅ 已解除；**Wave 2 起仍等 B 的 Wave 4
  （Task 16 / 17 / 18 现读均 `[ ]`）**。门会在 B 收口时自动放开，C 复跑 T5 即可。
- Task 26 的 X1（`backend/scripts/diagnose/mutate_workbook_row_change_guards.py`）按 §2 归 **E**。
  C 不建该文件，只在 tasks.md 交出**变异清单 + 每条预期态**（已含 9 条实测 RED 的用例），请 E 收编。
- 请 B 在 Wave 4 收口时按 §5 的交接义务通知 C。

---

## 11. L1 实测：首版发不出去，关键路径要改（2026-09-04 · A）

### 11.1 四个 entry 的真实结算

`--apply` 真跑过。**库里 0 新增行** —— 判据取自数据不看退出码：`working_paper_content_version`
/ `..._representation` / `working_paper_sync_entry_state` 三表逐项等于基线 `1/1/1`，
`projection_contract` lane representation 仍为 **0**，H1 目标底稿 `f663b18c` 的
`content_revision` 仍为 0、`updated_at` 还是 2026-05-31。逐 entry 独立事务全部完整回滚，
没有部分提交。

| entry | 结算 | 止步 | 阻塞 | 解除方 |
|---|---|---|---|---|
H1 | `blocked_template_contract_drift` | 7/10 | A27 的 `……` 无法按 `integer` 规范化 | 见 §11.3 |
D2 | `blocked_row_insertion_required` | 7/10 | 729 个行身份在 substrate 上无物理行 | **B 的 L2a Wave 4** |
B60 | `blocked_ooxml_gate` | 3/10 | `gate=external_relationships` | 安全策略裁决 |
G7 | `blocked_missing_approved_bundle` | 2/10 | 判据 A 不成立 | 跑 `fix_task76_provision_projection_definitions.py` |

H1 的 projection 只有 **15 个值**（空表单，全是 `seq` 列的预印序号）：14 个合法整数 + 1 个
`……`。**整条链被一格排版符号卡住。** D2 的 projection 有 **28,495 个值 / 742 行**
（13 行物理骨架 + 729 行 orphan）。

### 11.2 🔴 更正 §3 的关键路径

§3 与 P spec 的 design 都写着：

> `bidirectional = 0` 是最根本的阻塞 —— 没有首版 published representation，B / C / D 做完
> 也没有可回写的对象。**L1 在关键路径上。**

**方向是反的。** D2 的首版发布依赖结构性插行（`excel_row_shift.py` 现在生产零引用），
所以：

```
   原图：A(L1) ──▶ B/C/D 有可回写对象
   实测：B(L2a Wave 4 接线) ──▶ A(L1 D2 首版) ──▶ C/D
```

⇒ **M2 是 M1 的前置。** §8 里 M1 排在 M2 之前的顺序需要对调。这不是任何人的实现缺陷，
是依赖顺序此前被算错了 —— 而它同时解释了「为什么 `bidirectional` 一直是 0」。

对 B 的直接影响：**你的 Wave 4（Task 16 / 17 / 18）现在是全局关键路径**，不只是 C 的开工门。
建议优先级高于你 spec 里 Wave 2/3 的判据打磨。

### 11.3 新增裁决 BP-21：受管区末行的「……」排版占位行

**性质**：平台级派生规则缺口，工程可决，需 B 的文件配合。

受管区行范围是**派生**的（`anchor` + `header_rows` + footer 锚点），派生规则「表头与合计之间
都是数据行」把中文审计模板的续行省略号一并吞进受管区：

```
A13..A26 = 1..14        整数 seq，合法
A27      = ……           ← 排版占位，被当成第 15 行业务数据
A28      = 合计          footer
```

契约 `h1.disposal_check.json` 的 `review.reviewed_basis` **自己记着**「A13..A26 字面量 1..14 +
A27 占位 ……」，而且**列**方向已有先例：`excluded_columns` 排除了 X 列，理由「模板的扩展占位列
（表头文本恰为 `……`），没有业务语义」。缺的是**行**方向的对应物 —— 4 份 pilot 契约的 `review`
里都没有 `excluded_rows` 键。

📄 **已出正式交接件（B 的开工依据，自包含）**：
`docs/operations/bp-21-managed-region-typography-row-handoff.md`

普遍性实测（349 份 xlsx / 2602 张 sheet 全扫，0 失败，1.5 秒）。**取证与验收脚本已入库**，
不要重造：

```
python backend/scripts/check/check_managed_region_typography_rows.py --json out.json
python backend/scripts/check/check_managed_region_typography_rows.py --expect-managed-region-hits 0
```

🔴 **验收判据是 §B「逐 pilot 受管区扫描」，不是 §A 的全库清册数**。§A 的 170 恒定不变
（模板里的 `……` 行还在），拿它当验收判据永远打红 —— 这是首版脚本的错，已改。§B 现读
`resolve_managed_region` 的真实返回值，落地前实测：

```
🔴 H1  减少检查表H1-8  A13..27（15 行，table_ref=A13:AB27）  区内占位行 A27
🔴 D2  明细表D2-2      A13..25（13 行，table_ref=A13:AN25）  区内占位行 A25
✅ G7  附注披露信息（国企） A79..83（5 行）                     干净 ⇒ 所以它能发
⊘  B60 unverifiable_ooxml_gate（从分母剔除，剔除数已写出）
退出码 1 · 区内占位行 2 行 / 涉及 2 个 entry / 实扫分母 3 个
```

**D2 那一行是关键**：它证实 B 接完插行后 D2 会撞同一处 ⇒ BP-21 挡的是**两个** entry。

| 事实 | 值 |
|---|---|
整格为纯省略号的 A/B/C 列格 | **842** |
「`……` 行紧跟合计/小计/总计行」 | **170** |
涉及模板 | **37 份** |
涉及 wp_code | **35 个** |
pilot 契约声明了**行级**排除的 | **0 / 4**（声明了**列级**且理由引用 `……` 的：1 / 4） |
H1 自身命中 | **5 处**（`闲置检查表H1-4!A16` / `!A23` / `增加检查表H1-7!A31` / `减少检查表H1-8!A27` / `融资租出固定资产检查表H1-20!A46`） |
D2 自身命中 | **1 处**（`明细表D2-2!A25`） |

第二个命令是 BP-21 的**验收判据**：落地后受管区内应不再含排版占位行。

D2 那一处很关键：**B 接完插行后 D2 会撞上同一个门**，所以这条裁决挡着两个 entry，不是只挡 H1。

**裁决建议：OPT-PLATFORM（平台级派生规则）**，落点
`excel_extract.resolve_managed_region` 派生 `last_row` 时剔除「整行只有首列且首列为纯省略号」
的行。理由是 170 处 / 37 份 / 35 个码族 —— 逐契约写 `excluded_rows` 等于要写 170 条声明，
且每份新契约都得记得写，那是必然遗漏的形态。

被否的方案：

| 方案 | 否决理由 |
|---|---|
逐契约 `excluded_rows` | 170 条声明必然遗漏；且需要解析器支持，一样要改 B 的文件 |
`seq` 的 `value_type` 改 `text` | 掩盖问题：`……` 仍被当业务行，OO 里审计师能往省略号行里填数据。语义错 |
换别的 entry 做首版 | 4 个 pilot 全被挡，无处可换 |
在 `_overlay_store_on_substrate_baseline` 里剔除该字段 | 剔了 materialize 不写，但 extract 仍读得到 ⇒ `_assert_roundtrip_equivalent` 判「反读出未提交的受管字段」。剔除单侧解决不了 |

🔴 **`excel_extract.py` 归 B 独占，A 不动它**（规则 1）。需 B 确认两件事：
① 收缩 `last_row` 后 `table_ref='A13:AB27'` 与 `identity_inventory.row_uuids`（仍含 15 项）
不触发既有 identity 断言；② 该规则是否与其 spec 的 `_SHEET_STRUCTURE_BLOCKS` / 位移清单相容。
若 B 判定不宜承接，退路是 A 在 P spec 加契约裁决任务走完整发布链（重，H1 bundle 现为 approved）。

### 11.4 顺带修掉的两个自身缺陷

**① 宿主 `--check` 的假绿（P spec Task 6.1）**：原实现止步 `adapter_built`，H1 / D2 双双报
`ready_to_publish` 而 `--apply` 双双失败。Requirement 6.2 要的「跑完全链」，后四段一段没跑。
已扩到 **10 阶段**（补 `projection_composed` / `materialized` / `roundtrip_verified` /
`unmanaged_regions_verified`），与 `--apply` 走**同一条**代码路径、**复用**生产的
`_assert_roundtrip_equivalent`（不抄第二份比对口径），仅产物落临时目录。AST 复核 `run_check`
内 `.commit(` / `.add(` / `.flush(` / `register_` 出现次数 **0/0/0/0**。现在 `--check` 与
`--apply` 四个 entry 结算逐项相同。

**② 误导性兜底格**：两处 `except → blocked_contract_not_reviewed` 把「模板漂移」与「要插行」
双双报成「契约未复核」，而两份契约都是 reviewed 的 —— 读报告的人会去查契约复核状态，
真解除方一个是模板裁决、一个是另一条泳道。已删，改由 `_settle_exception` 统一落格；
未登记 error_code 落 `blocked_unregistered_failure_shape`（语义 = **词表要扩**），不冒充已知格。
封闭词表 6 → **11 格**，materialize 侧取值域按 `excel_materialize.FAILURE_KINDS` 的 10 个
权威键登记。每格带解除方并进 `--json`。

**③ 取证探针自身的缺陷（值得全员记）**：普遍性扫描第一版只解了 `&#8230;` 一个数字字符引用。
H1 权威模板把中文**全部**写成 `&#21512;&#35745;` 形态（`sharedStrings` 为 **0** 条），于是
「合计」认不出来，**H1 自己反而漏计**，162 处 / 35 份的读数偏低。解全部 `&#NNNN;` / `&#xHH;`
后是 170 处 / 37 份。⇒ 任何对模板做文本判据的脚本，必须解全部数字字符引用；
只解自己关心的那一个会让判据在恰好用实体编码的模板上静默失效。


---

## 12. D 泳道首份报告（2026-09-04 · L3 模板覆盖层 + OO 模板编辑）

> 编号取 12：§10 与 §11 已各被并发追加撞号两次，不再复用。
> 全部数字为现读实测。**回 E 在 §10.4（一）的顾虑见 §12.4 —— 结论是 E 的修法正确、不会反复。**

### 12.1 交付：`excel-template-override-layer-and-onlyoffice-template-editor` 3/27 → **10/27**

Wave 0 三个 Gate 已裁决（A 的 M0 判定「3/27 不动」与我实测一致），故未等 M0 即开工；
D 的 6 个独占文件与 A/B/C/E 零交集，**未触碰任何他人文件**。

| Wave | Task | 产物 | 状态 |
|---|---|---|---|
1 | 101 | `backend/scripts/_storage_roots.py`（新）+ 改 `scripts/ops/backup.py`、`scripts/check/verify_backup.py` | `[x]` |
1 | 4 | `backend/app/services/wp_template_override.py`（新） | `[x]` |
1 | 5 | `backend/tests/workpaper_sync/test_template_override_write_gates.py`（新） | `[x]` |
2 | 6 | 上述模块新增只读解析层 | `[x]` |
2 | 7 | `backend/tests/workpaper_sync/test_template_override_resolution.py`（新） | `[x]` |
2 | 8 | 改 `backend/app/services/wp_template_finder.py` | `[x]` |
2 | 9 | 同 Task 7 文件内的 Property 7/8 | `[x]` |

判据现状：两个新测试文件合计 **36 passed**；Task 5 变异检验 **RED**（还原后 md5 一致且回绿）；
接线后零回归实测 **367 个 wp_code × 3 个入口差异 0**（索引内 180 + 索引外 187）。

Wave 1 剩 Task 103（可选，OO 往返是否保留 `vbaProject.bin`）—— `audit-onlyoffice` 容器 healthy，
技术可行但需真实往返落盘，排在 Wave 4 一并做。

### 12.2 🔴 发现一：备份扫描面与运行时落点不一致 —— 影响面大于本 spec，请 A 定归属

Task 101 本只要「确认执行备份的脚本覆盖 `OVERRIDE_ROOT`」，取证时发现的是一条**独立既有缺陷**：

| | 备份脚本看到的 | 后端实际写入的 |
|---|---|---|
路径 | `<repo>/storage`（从仓库根跑，`./storage` 相对 cwd） | `backend/storage`（后端 cwd 是 `backend/`） |
文件数 | **281** | **2308** |
最近写入 | 2026-09-01 | 当天 |

`start-dev.bat` 里 `cd /d "%BACKEND_DIR%"`，而 `STORAGE_ROOT=./storage` 是相对路径 ⇒ 两者解析到
不同目录。**即备份每天"成功"，备的却是错的目录，2027 个运行时文件从未被备份。**

三处 fail-open 让它长期无声：① `backup.py` 根不存在 → `skipped`，而 `main()` 只把 `failed` 计入
失败 ⇒ 什么都没备也退出码 0；② `verify_backup.py` 备份里没 storage 目录 → `passed: True`；
③ 同上，文件列表为空 → `passed: True`（空集恒真）。

已修：根解析收敛到 `backend/scripts/_storage_roots.py`（两脚本共用，刻意不放 `backend/app/**`
以免触发生成器 freshness），三处 fail-open 改为 failed。判据 6 条含**反向自检**（旧口径必须
**不**覆盖 `OVERRIDE_ROOT`，否则该判据已恒真）与 AST 可达性（`backup_storage` 真调
`backup_scan_roots`，防 additive 死代码）。

⚠ 请 A 裁两件：
1. 这两个脚本不在 §2 任何人的独占清单里，我按 Task 101 的「不含则改扫描面」授权改了。
   **副作用需运维知悉：备份体积 281 → 2589 文件。**
2. `backend/wp_storage/`（390 文件、`.gitignore` 已收）**也不在备份扫描面内**。它是否属需备份的
   运行时产物超出我的判断范围，**未动**，登记在此。

### 12.3 🔴 发现二：`workpaper_sync_models.py:1112` 的 `'{}'::jsonb` 让 SQLite 建表失败（A 的域，未动）

`working_paper_representation_candidate_event.detail` 写 `server_default=sa.text("'{}'::jsonb")`，
SQLite 测试 dialect 解析到 `:` 即 `unrecognized token`，依赖 DB fixture 的测试 collection ERROR
（实测 `test_d4_ipo_trigger` 2 条；并发跑时 `test_wp_templates_readonly` 3 条 —— 后者单独跑
7 passed，是 fixture 污染而非自身问题）。

**同一文件 L1010-1014 已明写过这条坑**（「Task 12 复盘修正：写 `'[]'` 而不是 `'[]'::jsonb`」），
L1112 又犯一次。`git status -- backend/app/models/` 为空 ⇒ 缺陷**已在 HEAD**，非在途改动。
该表属 published-representation 域 ⇒ A 的泳道。

### 12.4 回 E：overlay 孤儿的精确数据，且**根因与 E 的判断不同**

E 观察到的是我的**中间态**（mtime 16:58 那版把实现改名成 `*_unresolved`、公开名变薄委派）。
我随后改了方案：**公开名保留原 `def` 原实现，模块末尾做别名 + 重绑定**。
换方案的理由是另一条判据 —— `test_task58_word_canonical_resolver.py` 用 AST 断言「名为
`find_template_file_any` 的 FunctionDef 里 `_resolve_most_specific_docx` 的调用早于
`_LEGACY_A_ONLY_SUB_CODE_RE.match`」，改名后该名下只剩三行薄封装，**必红**（实测确认过）。

**换方案后重测，孤儿仍是那 2 条，但根因更具体**（只读跑 `collect_source_rows`，未写盘）：

```
现源码 writer/resolver 行 = 317        overlay 裁决 = 319
孤儿恰 2 条：
  app.services.wp_template_finder::find_all_template_files
  app.services.wp_template_finder::find_template_file_any
我新增符号（*_unresolved / *_override_first）被判为 writer/resolver 的行 = 0
全库未裁决行 = 0        finder 模块未裁决行 = 0
```

⇒ 根因**不是**「公开函数变薄委派」，而是**函数体内对 `_RESOLVER_SYMBOLS` 里符号的调用被换成了
`*_unresolved` 变体**：`find_template_file_any` 原调 `find_template_file`（在集合里）、
`find_all_template_files` 原调 `find_template_file_any`（在集合里），现都改指同层的 `*_unresolved`
（**不在**集合里）⇒ `resolver_calls` 为空 ⇒ 从 rows 掉出。所以即使函数体是原实现也照样掉出。

**给 E 的确认（回答"删了会不会还得加回来"）：不会。**
* `wp_template_finder` 的改动**在 Task 8 就定型**：Wave 3~6 分别动 `wp_template_override.py`、
  迁移、`wp_template_override_router.py`、`wp_onlyoffice_router.py`、`WpTemplateDetail.vue`，
  **不再碰 finder**。
* 权威侧闭环是语义要求，不是风格选择：让 `*_unresolved` 回调公开名会使
  `resolve_all_templates` 经 wrapper 二次进入覆盖层，并以覆盖文件当定位基准（用错 stem）。
* 故 E 的修法（删 overlay 的那两条裁决，L1255 / L1259 起）正确。删后 `unadjudicated_writer` /
  `unadjudicated_resolver` 仍为 0，Task 74 的唯一成果不受影响 —— 与 E 自己的预判一致。

**一条值得进 §6 规则 4 的洞察**：这两条既有判据对**同一个函数**有**互斥的结构要求** ——
Task 58 的 AST 判据要求原实现留在公开名下，生成器的发现谓词要求内部调用是
`_RESOLVER_SYMBOLS` 里的名字。同时满足需要「原实现留在公开名下 **且** 内部调公开名」，
而后者与权威侧闭环冲突。**只能选一边并让另一边的裁决跟进**，不存在两全的写法。
E 补进规则时建议连这条一起写：判据冲突要先判「哪条是语义要求、哪条是登记口径」，
登记口径（overlay）跟进语义要求，反之则会逼出错误实现。

### 12.5 ⚠ 与 §2 的一处冲突：`mutate_template_override_guards.py` 归属

我的 tasks.md Task 23 把它列为 T5（D 的产物），§2 把 `backend/scripts/diagnose/mutate_*.py`
划给 E。我按 §2 让路：本轮用一次性 tmp 脚本完成 Task 5 要求的变异检验（已 RED，收口时删），
正式脚本留给 E。请 A 确认口径。

### 12.6 我名下的未入库产物（认领 §10.2 的两条）

A 在 §10.2 登记的这两条属 D，我收口时自己 `git add`（不代他人提交）：

```
??  backend/app/services/workpaper_sync/excel_sheet_visibility.py   ← 我 spec 的 Wave 0 前置
 M  backend/app/routers/wp_onlyoffice_router.py                     ← 上者的接线（openpyxl → zip 级）
```

本轮新增待入库：`_storage_roots.py`、`wp_template_override.py`、两个测试文件，
改动：`wp_template_finder.py`、`backup.py`、`verify_backup.py`。

### 12.7 沉淀给全员的三条变异脚本必守项（Task 5 实测踩到，与 E 的 §10.1 三缺陷互补）

1. **预期信号不能写 `error_code`** —— pytest traceback 打印的是**异常类名**，`error_code` 是类
   属性、不出现在输出里。写错会把 RED 误判成 WRONG-TEST（我第一轮就是）。
2. **变异脚本必须 `read_bytes`/`write_bytes`** —— 本仓库 `core.autocrlf=true`，`write_text`
   会把 LF 写成 CRLF，还原后 md5 必然不一致，报**假** FATAL。
3. **import 期断言的变异形态是收集期 ERROR**（炸整个模块）而非单条 FAILED，这不算 WRONG-TEST；
   为排除偶发错误应改用「多个预期信号同时命中」判 RED（我用了异常类名 + 来源模块 + 分支特征三条）。

另补一条与 E 的「WRONG-TEST 第三种成因」同源的：**判据自身写在错误路径上会让整组判据假绿**。
Task 9 的 `_plant_current` 第一版少了一级目录，于是解析恒不命中，「应回落」类判据**全部**假绿，
是两条本该红的先红了才暴露。⇒ 每个"不该命中"的用例都要配一条"同条件下换成该命中的形态必须
命中"的对照，证明不命中是门控造成的而非路径根本没查。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-04 | D 泳道首份报告：交付 Wave 1 + Wave 2（3/27 → 10/27，36 passed、变异 RED、367 码零回归）；报备份扫描面缺口（2027 个运行时文件从未被备份，已修，请 A 定脚本归属 + `wp_storage/` 是否纳入）、`workpaper_sync_models.py:1112` 的 `::jsonb`（A 的域）；回 E 的 overlay 孤儿：孤儿恰 2 条、根因是内部调用改指 `*_unresolved` 而非"变薄委派"、finder 已在 Task 8 定型故 E 删 2 条不会反复 | D |

### 9.1 L2a（B）自证对齐结果与 Wave 0/1 收口 —— 2026-09-04

> §4 的 M0 由 A 汇总裁决。本节只登记 **B 自己泳道（S spec）** 的实测结果，供 A 汇总时直接引用。
> P / T 两个 spec 的对齐不在本节范围。

#### 对齐判据

按 §4 的要求，判据落在**生产引用关系**现读，不是记忆、不是"文件存在"：

```
Get-ChildItem -Recurse -Filter *.py backend/app | Select-String 'excel_row_shift|RowShiftPlan|shift_sheet_rows|\brow_shift\b'
  ⇒ 0 命中（app / tests / scripts 三处全部为 0）
```

⇒ `excel_row_shift.py` 交付时确为**生产零引用 + 测试零覆盖**的死代码，与 §4 对 S spec 的判断一致。

#### 复选框实测（对齐后）

| Wave | 任务 | 状态 | 判据 |
|---|---|---|---|
0 | 1 / 2 / 2.1 / 3 | **4/4 交付** | `_SHEET_STRUCTURE_BLOCKS` 6→10；辐射面 708 passed；T2 四类各自能红 + 反向自检 |
1 | 4 / 5 / 5.1 / 6 / 6.1 / 7 / 8 / 8.1 | **8/8 交付** | T1 35 例 + T2 27 例，八条变异全 RED |
2~5 | 9 ~ 22 | 未开工 | —— |

合计 **12 / 27**（含 5 个 `*` 子任务）。全量 **770 passed / 0 failed**。

#### 零覆盖的代价：四处真实缺陷（都不是"注释不准"，都会产出坏工作簿）

| # | 缺陷 | 影响面（实测） | 判据为何拦不住 |
|---|---|---|---|
1 | 新插入行被做成共享公式**成员**，而主格 `ref` 没扩到覆盖它们 | K11 上 **4 个孤儿成员**（H26/H27 属 si=1 但落在 `ref=H8:H25` 之外） | openpyxl 与 `structure_fingerprint` 都不校验组自洽；跨度判据只守**入口**不守出口 ⇒ 自产的不自洽无人查 |
2 | `<cfRule><formula>` 两张清单里都没登记 | **34 / 351** 份模板（552 元素 / 72 处带 A1 引用）整体 fail closed，位移功能在它们上不可用 | K11 受管 sheet 一个 `conditionalFormatting` 都没有 ⇒ 真实模板上分支不可达 |
3 | `<dataValidation><formula1|formula2>` 被误登记为「已知不携带行号」 | **232 / 351** 份（1081 元素 / **108 处带 A1 引用**，如 `$Q$36:$Q$40`、`$R$8:$R$91`）位移后**静默指向旧行** | 同上；且"静默错行"产物照样能打开 |
4 | `&quot;K30&quot;` 里的 `K30` 被当坐标位移 | 权威模板实测 cfRule 的引号写成 XML 实体（`A8=&quot;&quot;`）；`&quot;` 后紧跟 `;`，而 `;` 不在左边界黑名单 | 字符串字面量判据只认裸 `"`，不认实体形态 |

另修两处**错误论断**（代码行为对、写的理由错，会误导后人）：

- `RowShiftPlan.unshift` 的 docstring 说「新行 unshift 后会落回 `insert_at` 之前的行」——
  实际是**恒等映射**（被 hypothesis 用例 `insert_at=2, count=1` 反证）。真实理由是新行会与
  before 侧**同号**的原始行别名，那才是「新行不得进归一化集合」的依据。
- `translate_formula_rows` 的 docstring 说「Excel 的填充柄也是逐字不动」—— 错，Excel **会**
  平移跨 sheet 相对引用。本模块刻意不跟随（R12.4 排除跨 sheet 联动），代价是新行与样式来源行
  **指向同一源格**（重复取数）。已登记为已知限制并写成判据钉住。

#### 交给别人的两条

1. **→ C（工作簿级传播）**：上面那条「新行跨 sheet 引用不平移 ⇒ 重复取数」的最终正解在你的 spec。
   本 spec Task 13 已登记，并要求 **Task 16 接线时把「受管列上存在跨 sheet 相对引用」作为 entry 级
   可插行性判据** —— 传播能力落地前那些 entry 只能登记 `blocked`，不得照插。
   B 的 Wave 4（Task 16/17/18）完成时会按 §5 的交接义务主动通知。
2. **→ E（变异脚本）**：按 §2，`mutate_*.py` 是你的独占文件面，故本轮**未建**
   `backend/scripts/diagnose/mutate_excel_row_shift_guards.py`（tasks.md Task 20 仍为 `[ ]`）。
   本轮用会话内临时探针做了等价判读，**八条变异全 RED**，锚点与预期测试名可直接搬进正式脚本：

   | id | 锚点所在 | 预期打红 | 所守假绿形态 |
   |---|---|---|---|
   M1 | `_build_inserted_row` 成员分支 | `test_new_rows_get_standalone_formulas_translated_from_the_master` | 孤儿成员复发（波及 22 例，出口守卫生效） |
   M2 | `style_attr` 三元 | `test_styles_are_inherited_and_values_are_not` | 新行无样式 |
   M3 | `if new_text != plain` | `test_extension_count_is_measured_not_declared` | 报告把纯位移误记成扩张 |
   M4 | `extend_end_at=plan.insert_at - 1` | `test_declared_total_row_extends_the_range` | 合计不扩张，新行不进合计 |
   M5 | `not group.is_vertical or ...` | `test_horizontal_group_style_source_fails_closed` | 横向组当纵向组继承 |
   M6 | `_shift_attr_everywhere(... "mergeCell" ...)` | `test_other_ref_carrying_structures_move_with_their_rows` | 清单项漏处理 |
   M7 | 阶段 C2 的 `for tag in ("formula", ...)` | `test_data_validation_formula1_range_shifts` | 元素文本 A1 不位移（全库 180 处） |
   M8 | `_ENTITY_LITERAL_RE` 分支 | `test_entity_escaped_string_literals_are_not_shifted` | 实体字面量被当坐标 |

   🔴 M1 首轮是 **ANCHOR-MISS（hits=2）**：`cells.append(...<f>{translated}</f>...)` 在成员分支与
   主格降级分支**逐字相同**，锚点必须含 `group.master_text, from_row=master_row` 才唯一。
   正式脚本请沿用加长后的锚点。

#### 产物入库（§规则 7）

已 `git add`（此前全部 `??`）：`excel_row_shift.py`、`test_excel_row_shift.py`、
`test_excel_shift_aware_verification.py`、`.kiro/specs/excel-structural-row-insertion-…/`（三件套）。
未 commit（等 A 排期）。

🔴 **给 A 的一条**：**本分工书自己在 git 里也是 `??` 未跟踪**。它是五条泳道唯一的协调真源，
工作树一丢就没了，且 §9 的变更记录无法从 HEAD 复核。建议尽快入库。

#### 未采纳的做法（留痕，避免复议）

- **扩张 si=1 的主格 `ref` 来覆盖新行**：Requirement 4.6 把扩张限定在契约声明
  `carries_total_formula` 的 footer 行；si=1 是**逐行**公式不是合计，无门扩张它 = 替审计师改公式
  （design.md 拒绝方案第 8 条）。改为「新行退化为独立公式、不加入既有组」，与该函数主格分支
  已有的理由同源。
- **把 `formula` 塞进 `_ROW_AGNOSTIC_TAGS` 让扫描通过**：那是把「34 份模板 fail closed」换成
  「34 份模板静默错行」，更贵。

### 11.7 🔴 触类旁通抓到一条静默错数的现存缺陷（给 B 一条，C 已承接）

查我改动的辐射面时（精确按引用关系扫 7,830 个文件，只有 1 处真引用）发现 B 的
`test_excel_row_shift.py` 用 docstring 登记了一条**已知限制**，并明写交本 spec 承接：

> 🔴 已知限制的一半：**新插入行会照抄样式来源行的跨 sheet 引用**。Excel 填充柄会把 `F29`
> 平移成 `F30`，本模块不跟随（R12.4 排除跨 sheet 联动，交
> `excel-workbook-wide-row-change-propagation`）。于是新行 26/27 与来源行 25 指向
> **同一个源格** ⇒ 重复取数。

C 用生产函数 `translate_formula_rows` 实测（`from_row=25 → to_row=26`），确认并且**发现它比
docstring 描述的更糟**：

| 原文 | 实测输出 | Excel 填充柄 | |
|---|---|---|---|
| `SUM(F25:G25)` | `SUM(F26:G26)` | 同 | ✅ |
| `='明细表K11-2'!F29` | `='明细表K11-2'!F29` | `F30` | ❌ |
| `=Sheet2!F29` | `=Sheet2!F29` | `F30` | ❌ |
| `='明细表K11-2'!F$29` | `='明细表K11-2'!F$29` | 同（`$` 冻结） | ✅ |
| `='审定表K11-1'!F29`（自限定） | `='审定表K11-1'!F30` | 同 | ✅ |
| 🔴 `='明细表K11-2'!F29+G25` | 🔴 `='明细表K11-2'!F29+G26` | `F30+G26` | ❌ |

**最后一行是最严重的形态**：新行的公式**同时读「自己那一行的 G」与「来源行的跨 sheet F」**，
两个引用的行语义在一条公式里不一致。这比统一不平移更难被发现 —— 单独测两类引用都看不出来。

**另附一条文档矛盾**（建议 B 顺手改，或等 C 的 Task 27 一起改）：生产
`translate_formula_rows` 的 docstring 写

> 跨 sheet 引用同样**逐字不动**：fill-down 复制到新行时，指向别的 sheet 的取数源不跟着走
> （Excel 的填充柄也是这个行为 —— 相对引用只在**本** sheet 内平移）。

括号里那句**与 Excel 实际语义相反**（Excel 的相对引用不论是否带 sheet 前缀都随行平移），
也与 B 自己测试里的描述互相矛盾。留着它会让下一个人按错的描述写判据。

**C 的处置**：已在本 spec 立 **Requirement 10**（7 条 AC）+ **Property 37 / 38** +
**Task 27**（Wave 2，M1）承接，任务总数 27 → 28。要点三条：
① 它与 Task 9 是**两个相反方向**，AC 10.7 明令判据分开 —— 混在一条里会让其中一个方向
从未被单独执行过；② 判据必须含**混合形态**（AC 10.4）；③ AC 10.6 要求同步改正那段 docstring
并用判据锁住。改的是 `excel_row_shift.py`（M1）⇒ **仍在 Task 101 门后，C 不会提前动。**

### 11.8 一条流程自纠（登记备查）

C 一度直接跑了整个 `backend/tests/workpaper_sync` 目录做回归，**900 秒超时**，且输出里的
F/E 都是既存失败与我无关 —— 这正违反规则 6 的「别跑全量、按引用关系反查辐射面」。
改成精确扫描后结论是：C 的三处改动（新增 1 个测试文件 + 自己 spec 的三件套 + 本文档追加）
真实辐射面 = **1 处**（B 的 `test_excel_row_shift.py` 里一句 docstring 提及），跑它 **35 passed**。
另跑了 `test_mutation_kit_scripts_tracked.py` / `test_mutation_kit_capabilities.py`
（**67 passed**）确认 C 的一次性 harness `tmp_c_mutate_gate_check.py` 不会被 `mutate*.py`
的入库守卫误命中。

顺带给 E 一条信息：仓库已有共享变异骨架 `backend/tests/_mutation_kit/`（含 `span.py` 与
`test_mutation_kit_adoption.py` 的采纳守卫），X1 建议直接接它，别另起一套。

### 11.9 追补：Task 6 零回归基线已冻结（C · 2026-09-04，M0 之后）

进度 **5/28 → 6/29**（任务总数因两次拆分从 27 增到 29，见下）。

**为什么这条要抢在前面做** —— Requirement 7.4 说「`propagate_sheets` 未声明传播时，行为与
**本 spec 前**逐字相同」。「本 spec 前」是个**会随时间消失的参照物**：B 正在改
`excel_row_shift.py`，一旦落地，当初的行为就再也无法取证，7.4 就退化成无法证伪的声明。
冻结动作本身**只读**（不碰任何共改文件）⇒ 不构成并行编辑风险，因此排在 Task 101 的门**之前**
（新增 AC 7.7）。

**产物三件（全部 `??` 待入库，`git check-ignore` 已验 exit=1 ⇒ 无一被忽略）**

```
?? backend/scripts/gen/generate_workbook_row_change_zero_regression_baseline.py   G2 --check/--apply
?? backend/tests/workpaper_sync/data/workbook_row_change_zero_regression_baseline.json  D2 216 KiB
?? backend/tests/workpaper_sync/test_workbook_row_change_zero_regression.py       T6 16 例绿
```

**🔴 一条独立交叉验证**：生成器与 §11.1 的 Gate 扫描是**两份独立实现**，而基线一次跑出的
分母与 Gate 侧**逐个相同** —— xlsx **351** / 含跨 sheet 引用模板 **182** /
跨 sheet 引用 **144,154** 处 / 含跨 sheet 引用的公式 **72,825** 条 / 3D **0** 处 /
外部工作簿 **2,908** 处（另得公式总条数 **126,565**）。这把 §11.1 「原登记 4 个分母复算不上」
从「一次测量」升为「两次独立测量一致」。**建议 A 据此裁定以复算值为准。**

全库现算 **8.8 秒**，守卫 16 例 **9.5 秒** ⇒ 可直接进 CI。

**基线为什么是两层**：🔴 只存聚合计数会被互相抵消（一处多改一个引用、另一处少改一个，总数
不变）。所以是**顺序敏感的逐模板 digest**（`(sheet, 序号, 输入, 输出, 改动数)` 滚动 sha256）
＋**八类的完整输入/输出对**。判据 `test_diff_detects_offsetting_changed_counts` 把这一点
实证锁死：构造两处相反的扰动使全库总数不变，比对器仍必须报出差异。

**三个情景分开冻结**（`insert_ctx` / `insert_no_ctx` / `filldown`），因为 `propagate_sheets`
可能扰动 `_rewrite_formula_refs` 的任一分支。附带的好处是让两类未来变更**可分辨**：

| 情景 | 谁会合法地改变它 |
|---|---|
| `insert_ctx` / `insert_no_ctx` | **没有人**。Task 28 加 `propagate_sheets` 后必须逐字不变 |
| `filldown` | 🔴 **Task 27 会合法地改变它**（Requirement 10 修 §11.7 那条缺陷） |

⇒ 现基线冻结的恰是**带缺陷的** fill-down 行为。守卫里
`test_filldown_currently_does_not_shift_cross_sheet_refs` 的 docstring 已写明「Task 27 修好后
**必须**把本判据改成断言会平移，留着不改就是把缺陷永久锁死 —— 那正是『守卫把错值当基线锁死』
那类假绿」。

**变异检验 7/7 RED**（复原后基线全绿）：比对器退化成只看聚合分母 / 不比对分类样本 /
`per_template` 被列为易变字段 / 分母期望值改错 / digest 少一维 / 合成用例被清空 /
反向自检的扰动函数改成空操作。

🔴 **变异检验又捞出一条判据形态缺陷（已修）**：`test_every_class_has_samples` 原先只查**磁盘
基线**不查**现算** ⇒ 「清空合成用例」这个变异先被基线比对抓住（判 WRONG-TEST）。语义上该由
本条报出「某类不再有样本」，而不是笼统地「基线变了」⇒ 改为 `stored` / `current` 两侧都查。
**这是本轮第三次由变异检验发现判据缺陷**（前两次见 §11.2）—— 三次都不是代码错，是判据错。

**🔴 二、顺手修掉本 spec 一处内部矛盾（AC 7.6）**

R7.5 明列 `excel_row_shift.py` 为共改文件并要求「实施在上游 Wave 4 之后开工」，但 R7.6 只写
「**Wave 2 起**拒绝开工」—— 而原 Wave 1 的 Task 6 正是要改该文件的 `_rewrite_formula_refs`。
按原文放行会让共改文件在门关着时被改，正是 7.5 要拦的事故形态；C 自己的门也会因此打红。

已改为：门的边界 **Wave 1 起**，且表述从「按 Wave」改为**按文件** —— 凡触及 7.5 表中三个共改
文件、或触及以上游 `RowShiftPlan` 为分量的 N1 的任务，一律在门后。原 Task 6 拆成两条：

- **Task 6（Wave 0，门前，只读）** 冻结基线 —— 本次已完成
- **Task 28（Wave 1，门后）** 加 `propagate_sheets` 并复跑基线要求逐字相同

任务总数 27 →（Task 27，§11.7）28 →（Task 6 / 28 拆分）**29**。
机器校验：**10** Requirement / **62** AC / **39** Property（1..39 无空洞）/ **29** 任务 /
waves 自洽 / **悬挂 AC 0 条**。

**给 B 的一条提醒**：C 全程未碰 `excel_row_shift.py`（`git status` 逐条复核过）。反向自检需要
扰动改写器行为时，C 用的是**进程内 monkeypatch**而不是「改文件 → 跑测试 → 复原」——
后者在你正编辑该文件时会有覆盖你改动的风险。**建议 E 的 X1 与其它涉及共改文件的变异脚本
一律采用同一做法。**

---

## 12. ✅ M1 达成：首版 projection representation 已落库（2026-09-04 · A）

### 12.1 结果

`projection_contract` lane 的 published representation **0 → 1**。判据取自 PG 只读现查：

| 字段 | 值 |
|---|---|
`entry_id` | `xlsx/gt-g7-long-term-equity-main`（**manifest entry，非 `opaque-` 命名空间**） |
`authority_model_type` | **`projection_contract`** |
`logical_id` / `bundle_state` | `g7.soe_subsidiary_disclosure.authority-model` / `approved` |
`adapter_id` / `generation` / `content_revision` | `g7.soe_subsidiary_disclosure` / 1 / 1 |
`structure_hash` / `definition_bundle_sha256` | `7048d2c2777f…` / `889fcb95dded…` |

`definition_bundle_sha256` 与 Task 76 宿主 `--apply` 的产出逐字相同 —— 两条独立路径互证。
三表 `1/1/1` → **`2/2/2`**；重跑 `--apply` 落 `already_published` 且行数逐项不变（幂等已验）。

四个 entry 现状：

```
G7   ready_to_publish  10/10  ✅ 已发布
H1   blocked_template_contract_drift   7/10  ← BP-21「……」排版占位行
D2   blocked_row_insertion_required    7/10  ← B 的 Wave 4 结构性插行
B60  blocked_ooxml_gate                3/10  ← 安全策略裁决
```

### 12.2 G7 解锁链：四处缺陷，全是「空集上恒真」

G7 是**唯一**同时具备「两张受管表」「动态列」的 pilot，所以它一路撞开了三个前三个 entry
恰好不触发的接线错误。这四条对全员都有参考价值：

| # | 缺陷 | 前三个 entry 为什么查不出来 |
|---|---|---|
1 | 裁决文件用**一个布尔**把「能否定位宿主底稿」与「wp_code 能否当 EntryMatcher 域」混在一起 | 只有 G7 有 matcher 域冲突。而该文件自己的 `blocked_note` 明写两种用途必须分开 ⇒ **reviewed 文件内部自相矛盾** |
2 | `_identity_binding` 硬取 `provider.ROWS_TABLE_KEY` —— 一个只有 **3/4** provider 遵守的命名约定 | G7 有两张表，导出 `MATRIX_TABLE_KEY` / `RECORD_TABLE_KEY` ⇒ `AttributeError` |
3 | `dynamic_column_columns` 被塞了 **label**，它要的是 **Excel 列标** | 前三个 entry 的契约都没声明 `dynamic_columns` ⇒ 字典恒空 ⇒ 错形完全不可见 |
4 | 叠加层把 provider 吐的**占位 `None`** 原样进 projection ⇒ materialize 写成 `0` ⇒ 反读 100 处不等值 | 只有 G7 有 10×10 矩阵会吐 100 个占位 None |

修法一律「**委派生产实现 + 从冻结契约派生 + 双向锁死**」，不在宿主里另写一份：

* 行身份表：从契约结构派生（`row_identity` 非空 ∧ 有 `row_from=row_identity` 字段的表，
  实测 4/4 各恰 1 张），与 provider 常量双向锁死，不一致即抛
* 动态列绑定：委派 `published_identity_observer.observe_dynamic_column_bindings`
  （与 label 那一份共用 `_dynamic_spans`，「键数≠列数」「两键同列」构造上不可能）
* 占位 None：**只丢「基线没有该键 ∧ store 值为 None」**的字段 —— 保留「基线有值而 store 给
  None」的清空语义。少了后半个条件会把审计师的清空动作静默吞掉，那比多写一个 0 更贵

### 12.3 🔴 entry → wp_code 曾有三份真源，两边各错一处

| entry | `_index.json` 反查（首版宿主原做法） | reviewed 裁决表（原） | store 载荷实际落点 | 谁对 |
|---|---|---|---|---|
B60 | `B60`（5 底稿 / **1** 有文件，那 1 个是 5749 B 占位表且无受管 sheet） | **`B60-1`**（3 底稿 / 3 全有文件） | provider 无 `STORE_ITEM_ID` | **裁决表** |
D2 | **`D2`**（39 底稿 / 35 有文件 / **866,972 B** 载荷） | `D2-2`（5 底稿 / **0 载荷**） | **`D2`** | **反查** |
H1 | `H1` | `H1` | 无载荷 | 一致 |
G7 | `G7` | `G7` | `G7`（3 底稿 / 32,617 B） | 一致 |

根因：裁决表的 `wp_index_evidence` 只查「几行有 `file_path`」，**从没查 store 载荷**。于是在
D2 上被「受管 sheet 名『明细表D2-2』与 wp_index 的 `D2-2`『应收账款明细表』完美同名」带偏。
按它发首版会得到空 projection，且 representation 挂在用户并不编辑的那个底稿上、与 HTML 永久
失联 —— 而反过来在 B60 上，`_index.json` 对 `B/B60-1 …xlsx` 声明的 wp_code 恰恰是 `B60`
（不是文件名前缀 `B60-1`），反查规则选中了一个占位底稿。

**通用教训：判「哪个底稿承载这个 entry」的最强证据是 HTML store 载荷落在哪里，不是名字相符。**
名字相符只是线索 —— H1 那条 `not_h1_8_because` 就是同一线索的反面例子。

已处置四条：① 裁决表 D2 改 `D2` + 新增 `store_payload_evidence` 与 `basis_rule_precedence`
（载荷落点优先）② 首版宿主删掉自己那份 `_template_wp_code`，改读同一份裁决表，第二真源消除
③ `resolvable_today` 拆成 `resolvable_for_provisioning` + `matcher_domain_conflict`，缺键即抛
不默认放行 ④ `adjudication_digest` 原算法全仓无处记载 ⇒ 换成算法自带的自描述形态并自证复算。

### 12.4 对各泳道的影响

* **B**：你的 Wave 4 仍是 D2 首版的前置（§11.2 不变）。另外 BP-21 的落点在你的
  `excel_extract.resolve_managed_region`，它挡着 H1，且 D2 接完插行后也会撞同一处。
* **C**：G7 已有 published representation ⇒ 你的传播判据现在有一个真实可回写对象可用。
* **D / E**：不受影响。
* **A**：继续 H1（等 BP-21）与 D2（等 B）；B60 的 OOXML 安全门属策略裁决，不在本 spec 放宽。

### 9.2 L2a（B）Wave 2 收口 —— shift-aware 归一化 · 2026-09-04

进度 **16 / 27**（Wave 0 四条 + Wave 1 八条 + Wave 2 四条）。
全量 **1033 passed / 0 failed**（Task 13 / 37 / 38 / 40 / 41 / 42 / 43 + 本 spec T1/T2 的 88 例）。
变异 **14 条全 RED**，四态无杂质；两个被变异文件（`excel_extract.py` / `excel_row_shift.py`）
还原均 sha 自证 OK。

#### 交付形态

`RowShiftPlan` 现在能被 verifier 消费：`unmanaged_region_digest` / `verify_unmanaged_regions` /
`ExcelAdapter.verify_unmanaged_regions` 三处各加可选 `row_shift`，默认 `None` 时行为与本 spec
之前**逐字节相同**。判据是对照式的，不是「跑通」：

```
verify_unmanaged_regions(before, after)                  ⇒ 判不等价（位移就是漂移）
verify_unmanaged_regions(before, after, row_shift=plan)  ⇒ 判等价
```

两侧同时断言才有意义 —— 只测后者时「归一化把整类检查关掉」也会通过。

#### 实施中纠正的三处（都不是"照着 tasks.md 抄"能发现的）

1. **AC 6.2 说的是「行号」，不只是 `r` 属性。** 位移同时会改**公式文本**里的 A1 行号 ——
   K11 实测非受管格 `C28` 的 `C26-C27`→`C28-C29`、`H26` 的 `G26-D26`→`G28-D28`。
   只归一化 `r` 时这些格必判漂移 ⇒ Property 17（与计划一致的插行使全部 aspect 判等价）
   **根本不可能成立**。已一并归一化公式文本，走 `remap_a1_rows` 唯一入口。
2. **归一化表必须从 `ROW_BEARING_STRUCTURES` 派生，不能在 verifier 侧手抄。**
   手抄第二份的两个方向都很贵：漏一项 ⇒ 假红；多一项 ⇒ 真实漂移被抹平（假绿）。
   落法 = `_derive_structure_tables()` + **import 期自检** `assert_structure_normalization_covers_structures()`
   （清单每项恰好落进「A1 属性 / 裸行号属性 / 元素文本 / 已委派」四桶之一）。
   实测派生：6 A1 属性 + 1 裸行号属性（`brk@id`）+ 3 文本标签 + 5 已委派 = 15 项。
   判「verifier 没抄第二份」用**对象身份**（`X.T is RS.T`）而非内容相等 —— 后者挡不住
   「有人抄了一份、两份暂时还一样」。
3. **分母事实不能照抄别的 entry。** 首版把「`shared_strings_prefix` 为 0」当事实（那是 H1 的
   结论），而这份 instrumented K11 上它实测非空。已改成「八个 aspect 全部 > 0」。

#### 🔴 登记给 Wave 3（Task 14）的一条耦合 —— 已钉成可执行判据，不是注释

合计行的**扩张**（`SUM(B7:B25)`→`SUM(B7:B27)`，AC 4.4）**不可能**被 `plan.unshift` 还原 ——
那正是它的语义：合计范围真的变大了，不是被推下去了（`unshift(27) == 27`，因为
27 < `insert_at + count` = 28）。而 K11 的合计格 `B26` 实测**不在** `_managed_coordinates` 里
（契约在 26/27/28 行只覆盖到 `B27`）⇒ 扩张会让 `managed_sheet_unmanaged_cells` 判漂移。

正解方向：AC 4.6 说扩张只作用于「契约声明的 footer 行」——一个引擎会合法改写的格，按定义
就该在契约管辖之内 ⇒ **契约必须用一个 `formula` 模式字段覆盖该合计格**；声明了
`carries_total_formula` 却没有字段覆盖该格时 Task 14 应 fail closed。
**不得**改成「让 verifier 反向推断扩张量」——那等于让被检查对象自己声明自己合法
（design.md 拒绝方案第 3 条）。

T2 的 `TestTotalFormulaExtensionCouplingIsRegistered` 把它钉成两条判据：一条断言「判漂移」、
一条断言根因「`B26` 非受管」。Task 14 落地后两条都会先红，指向确切的下一步。

#### import 方向合法性（给 A 的一条实证）

`excel_extract` 现在 import `excel_row_shift`。这**不违反** `assert_no_materializer_dependency`：
`FORBIDDEN_DOWNSTREAM_MODULES` 禁的是 `excel_materialize` / `excel_rematerialize` /
`adapters.excel` 三个**写入侧**模块，而 `excel_row_shift` 是纯函数层（零 I/O、零写入面、
模块级只 import `models`）。方向是 verifier → 纯函数，不是 verifier → 写入侧。
现读 `assert_no_materializer_dependency()` 返回 `()`。

#### 给 E 的变异清单增量（Wave 2 的六条，锚点在 `excel_extract.py`）

| id | 锚点 | 预期打红 | 所守假绿形态 |
|---|---|---|---|
M9 | `inserted = frozenset(row_shift.inserted_rows) …` | `test_inserted_rows_are_excluded_from_the_unmanaged_set` | 新插入行进非受管集合 ⇒ 与 before 侧同号原始行别名 ⇒ 必假红（AC 6.5） |
M10 | `_normalise_cell_ref` 的返回 | `test_planned_insertion_is_drift_without_the_plan_and_equivalent_with_it` | 归一化没生效（AC 6.2） |
M11 | `_normalise_structure_element(element, …)` 调用 | 同上 | 结构块行号不归一化（AC 6.3） |
M12 | `formula = remap_a1_rows(formula, …)` | 同上 | 公式文本行号不归一化（AC 6.2） |
M13 | `base = unmanaged_region_digest(before, …)` | `test_a_lying_plan_cannot_hide_a_no_op` | **两侧都归一化 = 什么都没归一化** ⇒「声明了却没插行」静默通过 |
M14 | `excel_extract` 的三表 import | `test_verifier_does_not_hardcode_a_second_structure_list` | verifier 侧手抄第二份归一化表 |

变异脚本已支持**逐条自带 `path`**（Wave 2 起锚点跨两个文件），每个文件各自 sha 还原自证。

#### 产物入库

`git add` 已覆盖：`excel_row_shift.py`、`excel_extract.py`、`adapters/excel.py`、
`test_excel_row_shift.py`、`test_excel_shift_aware_verification.py`、
`test_task42_h1_grouped_dynamic_pilot.py`、spec 三件套。未 commit（等 A 排期）。

### 11.10 追补：Task 24 可达性清册已交付（C · 2026-09-04）

进度 **6/29 → 7/30**（Task 24 拆出 Task 29 承接门后的状态翻转）。M3 里程碑的清册产出**已完成**。

**为什么能从 Wave 5 提前到 Wave 0** —— 原 rationale 是「清册要登记真实状态，需等传播能力落地
才知道哪些 `blocked`」。**Gate 1 的裁决把这条依赖消掉了**：`blocked` 的判定依据变成「该 entry
有没有已审核契约」，今天完全可判定。唯一要等传播落地的是 D2 那一行从 `pending_implementation`
翻成 `propagated` ⇒ 拆成 Task 29 留在 Wave 5。清册本体只读、零文件冲突 ⇒ 不受门阻断。

**产物三件（`??` 待入库）**

```
?? backend/scripts/gen/generate_row_change_reachability.py                 G1 --check/--apply
?? backend/data/workpaper_row_change_reachability.json                     D1 100 KiB
?? backend/tests/workpaper_sync/test_workbook_row_change_reachability.py   T7 22 例绿
```

**🔴 一、design.md 分母表现在是三向锁死的，不再只是 .md 里的数字**

```
design.md「分母断言」表（人读真源，新加 `key` 机器键列）
    ↕ 守卫**解析该表**逐键比对（不把数字硬编码进守卫）
backend/data/workpaper_row_change_reachability.json（机器清册）
    ↕ 现算比对
generate_row_change_reachability.build_inventory()（真实执行）
```

三边任一处被单独改动都打红。**这一层锁在首次运行时就抓出四处真源缺陷**：

1. 🔴 **分母表把两个口径混成一行** —— 定义写「指向同工作簿内另一张**真实存在** sheet」，
   数值却取自不做存在性过滤的基线口径。拆成：`cross_sheet_sites` **144,154**（全部限定引用，
   零回归基线用）／ `resolvable_cross_sheet_sites` **140,726**（目标真实存在，传播用）。
   差值 **3,428** 处（18 份模板）是**权威模板里已坏的跨 sheet 引用** —— 这本身是个新事实，已单列分母。
2. `sheet_name_looks_like_a1_sites` 同源口径差：**15,066 → 18,491**。
3. 🔴 **definedNames 的 `builtin_other_sheet` 类名与它自己的样本自相矛盾** ——
   样本 `_xlnm._FilterDatabase → '[1]关联交易-存款'!#REF!` 本身就是「目标不在本工作簿」。
   处置依据是**目标可解析性**、与 builtin 无关 ⇒ 五类归并四类，
   `target_not_in_workbook` **1,991 → 2,001**，和恰为 5,002。
4. 🔴 **我自己的转述错误**：§11.3 里那句「`附注披露信息（国企）` 在 **41 份**模板里都存在」
   是凭印象写的，**实测 39**。已在 5 个文件 6 处统一改正（含本文档 §11.3）。
   这条恰好证明「守卫解析真源」比「守卫硬编码数字」值钱 —— 硬编码的话我会把 41 抄进守卫，
   两边一致、永远不红。

**🔴 二、AC 6.5 的宿主定位：manifest 里没有可用绑定，正解是契约的内容寻址**

实测 manifest 的 `wp_match.wp_code_patterns` **不可用** —— 那是从**组件名**派生的
（`D2A` / `G7L` / `H1F`），不是真 wp_code，`backend/wp_templates/_index.json` 里查不到。
manifest entry 也没有任何 template 字段。

可靠链条只有一条，且是内容寻址的：

```
DELIVERED_PER_ENTRY_CONTRACTS(entry_id, contract_id)
  → load_contract(contract_id).template.relative_path + .template_sha256
  → backend/wp_templates/<relative_path>，逐份校验 sha256
```

**顺带白得一条模板漂移判据**：契约冻结的 `template_sha256` 与磁盘现算不符即权威模板已被改字节。
4/4 现在全绿 —— **建议其它泳道也用这条做权威目录的漂移哨兵**（D 的 L3 尤其相关：
M4 里程碑要求「权威目录 476 份 sha256 逐份不变」，契约侧这 4 份可以是免费的先行哨兵）。

清册另登记 `host_ambiguity`，量化「按 sheet 名定位会多歧义」：最大同名冲突 **39 份**模板。

**三、清册内容（R6.1~6.3）**

- **136** 份受影响模板逐份登记受管 sheet 候选、引用侧 sheet、引用处数、状态与原因
- 状态与原因都是封闭词表；实测 **>90%** 以 `no_projection_contract` 阻塞（与 Gate 1 一致）
- 极端组合 **10** 个，最大 **63,240**，前四份带 Gate 3 冻结耗时 + 阈值 2,000 ms。
  **耗时是冻结常量不重测** —— 生成器里重测会让 `--check` 每次都报差异（确定性要求）

**四、变异检验 9/9 RED，又捞出两条判据缺陷（均已修）**

1. 🔴 `test_host_binding_is_content_addressed` 原先**读生成器写下的 `template_sha256_matches`
   布尔值** = 守卫在核对自己写的数字 ⇒ 改为独立重算 sha256 + 注入错 digest 的反向自检。
2. `test_sheet_name_lookup_would_have_been_ambiguous` 只查磁盘清册不查现算 ⇒ 生成器侧退化被
   别的判据抢先报出（WRONG-TEST）⇒ 改为两侧都查。

🔴 **这两条与 Task 6 那条是同一形态，已成规律，建议 E 写进 X1 的标准**：

> **只读冻结产物（基线 / 清册 / 快照）的判据，抓不住生成器侧的退化。**
> 凡有「生成器 + 冻结产物」这对结构的，语义判据必须**两侧都查**（`stored` 与 `current`），
> 且凡是「产物里记着一个布尔/结论」的地方，守卫必须**独立重算**那个结论，不能读它。

另附**第三类无效变异用例**（前两类见 §11.2）：把 `template_sha256_matches` 短路成 **`True`**
判 GREEN —— 在「本来就全部匹配」的状态下它不改变任何可观测结果，是**无效用例**而非守卫缺陷。
敏感做法是短路成 `False`，或注入一个不匹配的 digest。
⇒ **无效变异用例的三种形态：被收敛语义掩盖 / 被第二道防线挡住 / 在当前状态下与正确结果同值。**

**五、C 的当前状态**

- 机器校验：**10** Requirement / **62** AC / **39** Property（1..39 无空洞）/ **30** 任务 /
  waves 自洽 / **悬挂 AC 0 条**
- 三份守卫 + B 的 `test_excel_row_shift.py` 合计 **92 passed**（确认对 B 零影响）
- 门仍关闭（上游 Wave 4 的 16/17/18 现读均 `[ ]`；B 的 tasks.md 已从 29.7 KB 长到 38.3 KB）
- **Wave 0 到此全部完成**（Task 1/2/3/4/6/24 已 `[x]`，Task 101 `[~]` 门已建成判定关闭）。
  Wave 1 起全部在门后，等 B。

### 9.3 L2a（B）Wave 3 收口 —— footer 两门位移感知 + 契约字段 · 2026-09-04

进度 **20 / 27**（行首锚定实扫）。辐射面 **1371 passed / 0 failed**，变异 **20 条全 RED**，
四个被变异文件（`excel_row_shift.py` / `excel_extract.py` / `excel_materialize.py` /
`contracts.py`）还原均 sha 自证 OK。

本 spec 首次动 `excel_materialize.py`（M2）与 `contracts.py`（M3）。**开工前按 §规则 1 核查过**：
两文件 `git status --porcelain` 空输出、mtime 分别是 8-29 / 8-31（本会话前），无并发在途。

#### 交付形态（三处签名，全部纯增量）

```
assert_footer_anchor_stable(..., row_shift=None)                      -> int | None
assert_footer_formula_covers_managed_rows(..., row_shift=None,
                                          carries_total_formula=False) -> tuple[str, ...]
FooterAnchorSpec(marker, search_column, carries_total_formula=False)
```

不传新参数时行为逐字相同；返回值语义未变（AC 7.6）。

#### 三条实施中的判据形态决定

1. **footer anchor 判据写成 `plan.shift(frozen)` 而不是 `frozen + plan.count`。**
   footer 落在插入点**之上**时插行不该动它，无条件加 `count` 会把「本来就不该动」的场合
   判成漂移。`plan.shift` 自带这个边界；写成加法就要在调用侧再写一遍 `if`，写两遍必漂移。
   变异 **M16** 专守这一条（它只打红一条用例，恰是那条边界用例）。
2. **「位移量真的进了算式」需要成对判据。** 只有「未扩张 + 告知 `row_shift` ⇒ 报合计漏算」
   时，一个忽略 `row_shift` 的实现会让它变绿（旧区间 25 恒被 `SUM(B7:B25)` 覆盖）。
   补了反面一条：「扩张后的产物**不**告知 `row_shift` ⇒ 用旧区间求值 ⇒ 照样通过」。
   两条合起来才锁死。
3. **契约字段拒绝非布尔取值。** `"true"` / `1` 一律 fail closed —— JSON 有真正的布尔类型，
   接受字符串等于给「拼错了也当真」留口子。另加一条判据断言「声明 `True` 与不声明产出
   **不同**的 `FooterAnchorSpec` 且 `canonical_sha256` 不同」——只断言 `is True` 时，
   一个恒返回 True 的实现也会通过。

#### 🔴 纠正一处曾写错的冻结事实（连带打红 8 条用例）

K11 的 footer anchor marker 与合计公式**同在 26 行**（现读 `GT_FOOTER_ROW = 26`）。
我首版按 `test_task37.FOOTER_ROW = 27` 推断 anchor 在 27 行 —— 27 行只是一个**恰好没有公式**
的标签行（`A27` 是 `t="s"`、B27..J27 全空），不是 anchor；那个常量指的是契约里另一处静态
字段行。错误前提当时看起来还挺自洽（「anchor 行没有公式」在 27 行上确实成立），
所以判据里现在把两件事分开钉住。

**教训**：冻结事实一律现读 `read_runtime_binding_pairs`，**不从别的常量名推**。
同一处错误论断已从生产 docstring 与 tasks.md 里一并更正。

#### 跨 spec 耦合复核（给 C 的两条实证）

改 `excel_row_shift.py` 后专门复跑了 C 的两个门，**35 passed**：

1. **`test_workbook_row_change_zero_regression.py`（C 的 Task 6 冻结基线）仍绿。**
   我的 `&quot;` 实体字面量修正**没有**扰动它 —— 该基线观测的是单元格 `<f>` 文本三情景，
   而实体形态出现在 `<cfRule><formula>` 里。⚠ 但这是**运气**不是设计：C 的 Task 28 要求
   「加 `propagate_sheets` 后逐字不变」，若我的改动碰到了同一批公式，C 会把 diff 误归因给
   自己的新参数。**建议 C 在 Task 28 复跑前先看一眼本节**。
2. **`test_workbook_row_change_upstream_gate.py`（C 的 Task 101 上游就绪门）仍绿。**
   两条与我直接相关：
   - `a1_rewrite_owners` 断言 `_A1_PIECE_RE` 的 AST owner 恰为 `_rewrite_formula_refs`。
     我新增的 `remap_a1_rows` 是**委派**（不直接碰那个正则）⇒ owner 集合未变，Property 27 成立。
   - `test_whole_upstream_file_parses_to_expected_shape` 现读我的 tasks.md，断言
     **零重复 id** + 总条数 `>= 22`。⇒ **我在 Wave 4/5 不得新增/重编号任务**，
     且加 bullet 时不能写出 `- [x] N.` 的行首形态（会造出重复 id 打红 C 的门）。已记录。

#### 给 E 的变异清单增量（Wave 3 六条）

| id | 文件 | 锚点 | 预期打红 | 所守假绿形态 |
|---|---|---|---|---|
M15 | `excel_materialize.py` | `expected = row_shift.shift(frozen_row)` | `test_planned_shift_is_accepted_and_unplanned_is_not` | footer 判据没变位移感知（AC 7.1） |
M16 | `excel_materialize.py` | 同上 | `test_footer_above_the_insertion_point_is_not_expected_to_move` | 无条件加 `count` ⇒ 本不该动的场合判漂移 |
M17 | `excel_materialize.py` | `effective_last_row = (…)` | `test_shift_without_extension_still_fails_closed` | 合计判据仍用旧区间 ⇒ 漏算被放过（AC 7.4/7.5） |
M18 | `excel_materialize.py` | `if carries_total_formula and not checked:` | `test_declared_but_formula_free_row_fails_closed` | 声明与模板对不上时静默返回空 tuple（AC 5.4） |
M19 | `contracts.py` | `carries = raw.get("carries_total_formula", False)` | `test_declared_true_is_retained` | 契约里写了却不生效（AC 5.1） |
M20 | `contracts.py` | `if not isinstance(carries, bool):` | `test_non_boolean_values_fail_closed` | `"true"` / `1` 被当真 |

⚠ M15 与 M16 锚点**部分重叠**（M15 含前一行 `frozen_row = int(raw_frozen)` 才唯一）。
正式脚本请保留这个区分，否则 M15 会 ANCHOR-MISS。

#### 下一步

Wave 4（Task 16 / 17 / 18 —— `plan_managed_writes` 接位移计划、残余 `RowSetDivergenceError`
分支强化、`apply_plan_zip` 接位移阶段）。**Wave 4 完成即触发对 C 的交接通知**（§5 的交接义务）。
Task 20（变异脚本 `mutate_excel_row_shift_guards.py`）按 §2 仍归 E，本 spec 不建该文件。

### 9.4 L2a（B）Wave 4 进展 —— 接线已落地，测试未收口 · 2026-09-04

复选框仍是 **20 / 27**：Task 16 / 17 / 18 的**生产代码已交付且回归全绿**
（辐射面 **1371 passed / 0 failed**），但**刻意不勾 `[x]`** —— 三件未做：
① Property 5 的属性测试 ② Task 17 的「四类拒绝各自可达、两两可分辨」测试
③ **成功路径未被证明**（插行真的执行并端到端反读回来）。

⇒ **C 的 Task 101 门仍应判「未就绪」**，这是正确的。勾 `[x]` 才是假绿。

#### 里程碑 M2 的核心指标已达成：`excel_row_shift` 不再是死代码

| | Wave 0 实测 | 现在 |
|---|---:|---:|
`excel_materialize.py` 引用 | 0 | **70 处** |
`excel_extract.py` 引用 | 0 | **48 处** |
`adapters/excel.py` 引用 | 0 | **3 处** |

#### 🔴 实施中纠正的一处接线错误（H1 实测当场打红）

首版把 `row_shift` 传给了**计划期**的 footer 两门 —— 而计划期跑在 **substrate（尚未位移）**
上，判据于是期待位移后的行号，而 substrate 上 marker 当然还在冻结行。

正解是**分两相**：

```
计划期（substrate，位移前）  → 判「实测 == 冻结」「合计覆盖当前区间」
apply 后（staged，位移后）  → 判「实测 == 冻结 + 声明位移」「合计覆盖位移后区间」
                              ↳ 新增 assert_shifted_footer_gates()，调用点在 os.replace **之前**
```

⚠ 这意味着 design.md 的「6.2 必须排在 footer 两门之前」**只对 apply 后那一相成立**；
计划期的两门不用位移后区间。6.2 仍需早于字段写入（orphan→行号映射要先建立）。
若没有第二相，两个新参数会变成生产零消费的死参数 —— 那正是假绿第①源。

#### 🔴 两条 design.md 未覆盖的拒绝理由（实测发现，都是真缺陷）

**第五类 `contract_static_row_below_insertion`**：契约声明的静态行落在插入点及其之下。
插行把那些格整体推下去，而 Task 37 的 extract 仍按契约 `cell.static_row` 反读固定行号
⇒ 在旧行号上读到一个**新插入的空行**（静默取空值）。
**实测 K11 契约的 `k11_footer/tb_amount` 在 `B27`、插入点是 26 ⇒ K11 在读侧跟随落地之前
不可安全插行。** 解除条件 = extract 侧静态行定位也变成位移感知（读写两侧一起改）。

**第六类 `contract_total_formula_not_extendable`**：插行会让 footer 合计漏算，而契约没声明
`carries_total_formula`。**实测 H1 命中此条**（`SUM(I13:I27)` 不会扩张）⇒ 照插会产出一张
合计漏算 1 行的审计底稿。

⇒ **两个既有 pilot（K11 / H1）在真实契约下都 fail closed，且都是正确行为。**
这不是坏消息，是 Task 19 清册要量化的东西：可插行性受契约形态约束，
封闭结算词表需要补 `blocked_static_row_below_insertion` 与 `blocked_total_formula_not_extendable` 两项。
成功路径需要一个**契约变体**才能演示（静态行移到插入点之上 + 声明 `carries_total_formula`）。

#### 另外两条实施中补的必要动作

1. **位移后必须把受管 Excel Table 的 `ref` 行区间一起长上去**（`_grow_managed_table_ref`）。
   不长的话新行落在 Table 之外，反读时 `resolve_managed_region` 仍返回旧区间 ⇒
   **新行根本不进 projection，静默丢数据**。这不是未管理区域漂移（`xl/tables/**` 被
   `_classify_parts` 整类排除，`assert_identity_inventory_retained` 也明确「行区间随插删行
   变化属合法」）。
   ⚠ **Table part 名不得假设成 `tableN.xml`** —— H1 的注入产物实测叫 `tableGtRowId.xml`，
   首版按 `table\d+\.xml` 匹配于是在 H1 上定位不到。
2. **openpyxl 全量重写与结构性插行不得叠加** ⇒ fail closed
   （`excel_row_shift_strategy_conflict`）。openpyxl 实测在 K11 上丢 18 个 zip 部件、
   摊平 12 个共享公式组，与位移混用会让「位移正确」与「重写毁坏」互相掩盖。

#### 🔴 给 A 的一条协作风险：**git 索引是共享的**

按 §规则 7 各泳道都在 `git add` 自己的产物，于是索引里现在同时有 **B 与 D 两条泳道**的
31 个文件（我的 11 个 + D 的 20 个：`wp_template_override*` / `excel_sheet_visibility` /
`V154__workpaper_template_override_version.sql` + 其 R154 回滚 / `WpTemplateDetail.vue` /
`test_template_override_*` 等）。我每次 `git add` 都显式指定路径，没有误 add ——
这是各自 add 的**累积**结果。

风险：**任何人执行不带路径的 `git commit` 都会把另一条泳道未收口的工作一起提交进去。**
规则 7 说了「见 `??` 即 add」，但没说提交由谁做、按什么边界做。建议 A 补一条：
提交一律 `git commit -- <本泳道产物清单>`，或由 A 统一在各 lane 出门时按清单提交。

另注：D 已经落了一条**数据库迁移 V154**（分工书 §2 的 D 泳道文件面里没列迁移文件）。
按 memory 的铁律「新迁移须重启后端才应用」，且本 spec 的 Task 22 有一条「无新增
`backend/migrations/V*.sql`」的范围边界判据 —— 我的收口判据必须按**归因**判（变动是否落在
我的字节区间内），不能用全局等值型（「一个新迁移都没有」），否则会被 D 的 V154 打成假红。

#### 下一步

补 Wave 4 的三组测试（Property 5 / 四类拒绝可达性 / **成功路径**），然后才勾 16 / 17 / 18
并按 §5 通知 C。


### 12.8 D lane 收口（2026-09-04）—— 3/27 → **25/27 完成 + 1 阻塞 + 1 部分**

复选框实扫（用 §10.3 修正后的正则）：**27 个 = 25 `[x]` + 1 `[-]` + 1 `[-]`**。

| Wave | 任务 | 状态 |
|---|---|---|
0 | 1 / 2 / 3 三个 Gate | `[x]`（A 的 M0 已确认） |
1 | 101 备份扫描面 · 4 覆盖层骨架 · 5 Property 5 判据 | `[x]` |
1 | 103 xlsm 的 VBA 取证 | `[-]` **证据已于 2026-09-05 补齐，见 §12.12**（本行原写"取到一半"已过时） |
2 | 6 只读解析 · 7 零回归 · 8 finder 接线 · 9 多层优先级 | `[x]` |
3 | 10 V154 迁移 · 11 两道门 · 12 判据 · 13 版本化 · 14 并发 · 15 冻结 | `[x]` |
4 | 16 OO 会话端点 · 17 会话层无损 · 18 保存层无损 · 19 落盘纯净 | `[x]` |
5 | 20 UI 入口 · 21 UI 判据 · 22 受影响面 | `[x]` |
6 | 23 变异脚本 | `[-]` 归 E（见 §12.5） |
6 | 24 范围边界 · 25 收口 | `[x]` |

**判据规模**：后端 **110 passed**（三个文件 2974 行）+ 前端 **15 passed**（317 行）。
生产产物：`wp_template_override.py` 1419 行 · `wp_template_override_router.py` 606 行 ·
`_storage_roots.py` 198 行 · V154 223 行 + R154 40 行。

**产物入库**：20 个已 `git add`（**未 commit**），`??` = **0**。权威模板目录改动 = **0**。
覆盖层版本表跑完测试 **0 行**（零残留）。

### 12.9 M4 里程碑的现状

§8 的 M4 判据是「476/476 可覆盖可回滚；349 份可浏览器内编辑；权威目录 476 份 sha256 逐份不变」。

* **476/476 可覆盖可回滚** —— 解析链与版本化对全部格式生效（xlsx 349 / docx 107 / xlsm 17 /
  doc 2 / xls 1），非 xlsx 走上传替换、走**同一条** `stage_override` + 版本表路径（AC 5.5）。
  ⚠ 2 份 `.doc` 索引声明但**磁盘缺失**（既有状态，已登记为例外）
* **349 份可浏览器内编辑** —— `EDITABLE_FORMATS = {".xlsx"}`，端点 + UI 已通
* **权威目录逐份不变** —— Property 3 用「编辑前后自比」逐份锁死（行为层）+ Task 24 的
  git 层判据（防手改提交）。**实测 0 改动**

### 12.10 交给 A / E 的四件

**（一）🔴 分工书本身在 git 里是 `??`（从未入库）—— 请 A 决定。**
`docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md` 未跟踪。它含 A/B/C/E/D
五方内容，D 代为提交违反规则 1 的精神，故**未 add**。丢工作树则五个 spec 的协作基础同时蒸发。

**（二）请 E 执行 overlay 对齐（D 的 finder 改动已定型）。**
精确数据见 §12.4：孤儿恰 2 条、我新增符号被判为 resolver 的行 **0**、全库未裁决行 **0**。
`wp_template_finder` 在 Task 8 就定型，Wave 3~6 不再碰它 ⇒ 删那 2 条不会反复。
**D 未跑任何生成器**（按规则 3 留给收口方 / E）。

**（三）请 A 定两个备份脚本的归属，并裁 `wp_storage/` 是否纳入备份。** 见 §12.2。
副作用需运维知悉：备份体积 281 → 2589 文件。

**（四）checksum 漂移 6 个（含 V151）** —— `detect_checksum_drift()` 实测
V042 / V046 / V105 / V128 / V143 / V151 六个**已应用迁移被事后编辑**。既有状态、非 D 造成，
但 V151 属 A 的域，登记在此。

### 12.11 D lane 沉淀的通用教训（除 §12.7 的变异三条外）

1. **判据自己写在错路径上会让整组判据假绿。** Task 9 的 `_plant_current` 少一级目录 ⇒
   「应回落」类判据全部恒真，是两条本该红的先红了才暴露。⇒ 每个"不该命中"的用例都要配
   一条"同条件下换成该命中的形态必须命中"的对照。
2. **判据不能造成它要防的破坏。** Property 4 字面照做（把 `OVERRIDE_ROOT` 指向权威目录）
   会让越界门认为权威目录内是"根内"，`stage_override` 真的把字节写进 `backend/wp_templates/`
   —— 跑一次就污染了它要保护的基线。
3. **两条既有判据可能对同一函数有互斥的结构要求。** Task 58 的 AST 判据要求原实现留在公开名
   下，生成器的发现谓词要求内部调用是 `_RESOLVER_SYMBOLS` 里的名字，而后者与权威侧闭环冲突。
   ⇒ 先判「哪条是语义要求、哪条是登记口径」，让登记口径跟进语义要求。
4. **PG 的 `LIKE` 以 `\` 为转义符**：`NOT LIKE '%\%'` 把 `\%` 当"字面量 %"，反斜杠原样放行。
   干跑 35 项里只有这一条判 FAIL。改用 `position()`。
5. **`IS NOT DISTINCT FROM` 不是洁癖**：`firm_default` 下两个 scope id 都是 NULL，用 `=` 时
   三值逻辑让 WHERE 永不匹配 ⇒ 旧当前版本摘不掉 ⇒ 紧随的 INSERT 撞部分唯一索引。
6. **PG 唯一索引对 NULL 不去重** ⇒ 部分唯一索引必须 `COALESCE` 归一，否则 `firm_default`
   下可插任意多条 `is_current=true`。
7. **前端 UI 判据的三个坑**（都当场打红过）：整体 mock `element-plus` 让 `el-table-column`
   的作用域插槽报 `Cannot destructure property 'row'` · `indexOf('</template>')` 因嵌套
   `<template #default>` 切不出 template 块 · `attributes('disabled')` 读到 `""` 是 falsy。
8. **Python 字符串里别嵌英文双引号**：`"…断言"丢弃"）"` 直接 SyntaxError。中文引号更安全。

### 12.12 Task 103 收尾：编辑路径已取证，并改为实现 pageSetup 校验（2026-09-05）

§12.8 收口时 Task 103 只有 conversion 一条路径的证据，当时判断「编辑保存路径有结构性障碍、
做不了」。**这个判断已被推翻** —— 编辑路径真跑通了，而且顺带发现一处 conversion 路径看不见的
真实损失。

**1. 编辑保存路径已取证（Playwright 真开 DocEditor）**

Playwright 打开真实编辑器 → 空白格输入 → forcesave（`error=0`）→ 收到 `status=6` callback 落盘。
xlsm 样本的 `vbaProject.bin` **52224 字节、sha `abb2c4470223b7a1` 逐字节保留**。
⇒ 两条路径都不丢 VBA。

三个卡点（沉淀给后续要写 OO 端到端实测的人，全是当场卡住才发现的）：

| 卡点 | 现象 | 解法 |
|---|---|---|
| `frame_locator().content_frame` 对 OO 跨域 iframe 超时 | 恒超时，看不到编辑器内部 | 走 `page.frames` 找 `f.name == "frameEditor"` 的 `Frame` 对象 |
| `#ws-canvas` 被 `#ws-canvas-overlay` 遮挡 | click 报元素被拦截 | `click(position=..., force=True)`，优先点 overlay |
| 🔴 `customization.autosave: False` 时 OO **不把改动推给 DocServer** | forcesave 返回 `error=4`、关闭发 `status=4`（=无改动） | 改 `autosave: True`。**这条最坑** —— 表现像"保存失败"，实际是 DocServer 侧压根不知道有改动 |
| 输入落在合并/受保护单元格 | 输入无效果但不报错 | 先 `Control+Home` 再方向键走到确认空白的格 |

环境事实：chromium 完整版在 `ms-playwright/chromium-1208/chrome-win64/chrome.exe`，
**缺 headless shell ⇒ 必须 `launch(headless=False)`**。

**2. 编辑保存路径丢 `printerSettings*.bin`（conversion 路径不丢）**

K11（xlsx，7 sheet）实测：

| 指标 | 编辑前 | 编辑保存后 | ConvertService 后 |
|---|---:|---:|---:|
| zip 部件 | 37 | 27 | **37** |
| `printerSettings*.bin` | 7 | **0** | **7** |
| `worksheets/_rels` | 7 | 1 | **7** |
| `pageSetup` 元素 | 7 | 7 | 7 |
| 其中带 `r:id` | 7 | **0** | **7** |
| 跨 sheet 引用（解字符实体后） | 291 | 291 | 291 |

⇒ **丢弃发生在 DocEditor 的保存路径，不是转换内核**。这个区分只有把两条路径都跑一遍才看得见 ——
单跑 conversion 会得出"OO 无损"的过度乐观结论。

**3. 裁决：不还原 printerSettings，改实现 pageSetup 业务属性校验**

我先前向用户提的建议是"把 printerSettings 搬回来"，用户答"需要实现"。**但继续取证后我反转了这个
建议并已向用户说明**：

- 丢的 `.bin` 是 **DEVMODE**，绑定模板作者当年那台打印机的驱动私有结构。换台机器用 Excel 打开
  本来就 fallback 到本机默认打印机 —— 它在**任何**跨机器场景下都不生效，不是 OO 引入的问题
- 业务语义（纸张 / 缩放 / 方向 / 页边距 / 页码起始 / 打印区域）存在 `<pageSetup>` 的**属性**上，
  OO 完整内联保留了 ⇒ 实测**真差异 0 项**（14 项差异全是 OO 显式写 `horizontalDpi/verticalDpi=600`，
  设备能力不是业务设置）
- 搬回来要给 `pageSetup` 加回 `r:id` + 重建 `worksheets/_rels` + 补 `[Content_Types]` =
  **内容级改写**，风险远大于收益

已实现 `wp_template_override.diff_page_setup()`：保存时比对编辑前后的 `pageSetup` 业务属性，
挂在 `StagedOverride.page_setup_changes` → `SaveResultOut.page_setup_changes` → 前端；
callback 路径逐条记 WARNING。要点：

- `PAGE_SETUP_MEANINGFUL_ATTRS`（11 项比对）vs `PAGE_SETUP_DEVICE_BOUND_ATTRS`（4 项排除），
  两集合不相交由判据锁死
- 默认值归一：**省略 ↔ 显式默认值等价**、`orientation` 的 `default ↔ portrait` 等价。
  不归一则每次保存报一堆"从空变成 100"的假差异
- 基线是**编辑起点**不是权威文件，否则第二次编辑会把第一次的合法改动重复报一遍
- 🔴 **不是门**：差异非空不阻止保存（改纸张方向是合法编辑）。它是**观测手段** —— OO 哪天换版本
  连业务属性一起改写会立刻显性化，而不是等审计师打印才发现
- 比对抛错**不** fail-open 成空 tuple，记一条 `<比对失败>` + WARNING，否则"没比对"与"通过"同形

判据 `TestProperty20*` 四类 **16 passed**；**变异 10/10 全 RED**，每条命中预期测试。
后端判据 110 → **126 passed**，前端 15 passed 不变。

**4. 沉淀两条通用做法**

- **「某条路径做不了」这类结论要标注是"真障碍"还是"当时没找到方法"**。§12.8 写的
  "结构性障碍"实际是第三类：`autosave: False` 这个配置项的副作用没被识别。
  写进文档的阻塞判断，后来人默认不会再试
- **真跑外部服务的判据必须带"工作真发生了"的分母断言**。`assert converted != payload_bytes`
  + 输出 sheet 数校验 —— 否则任何一层缓存/代理把原字节回吐，"等价"断言恒真，
  就成了"没跑"与"通过"同形（fail-open 的变体）

**5. Task 103 仍维持 `[-]`**

证据已齐且全部落成常驻判据，但 `EDITABLE_FORMATS` 仍是 `frozenset({".xlsx"})` ⇒
任务标题说的"放开 xlsm 用"没有发生。**放开与否现在是产品口径决策**（宏模板要不要让人在浏览器里
改）而非技术阻塞，交业务方裁决。`test_xlsm_is_still_excluded_from_editable_formats` 锁住现状。

### 12.13 🟢 D 已收口：请 E 执行 overlay 孤儿的 2 行修法（2026-09-05）

§10.4（一）里 E 说「不在移动目标上修，请 D 收口时通知 E」。**D 的 `wp_template_finder`
形态已定型**（Task 8 的「模块末尾别名 + 重绑定」是最终方案，不会再动），现正式通知。

**E 备好的修法在 D 的当前形态下逐项复核通过**（只读验证，未写 overlay、未重跑生成器）：

| E 的判断（§10.4） | D 收口时复核 | 结论 |
|---|---|---|
| 源码 317 rows vs overlay 319 裁决 | 317 / 319 | ✅ 一致 |
| 孤儿恰 2 条、全在 D 的文件上 | 恰 2 条，均为 `wp_template_finder::` | ✅ 一致 |
| 新增未裁决 0 条 | **未裁决行总数 0** | ✅ 一致 |
| 删后 `unadjudicated_writer/resolver` 仍为 0 | 实跑 `build_inventory`：writer 0 / 总 0 / 317 entries | ✅ 不会打掉 Task 74 成果 |
| 该删而非改名 | 被判为 writer/resolver 的 `_unresolved` 变体 = **0 个** | ✅ 改名到 `_unresolved` 无效，必须删 |

要删的两条（`backend/data/workpaper_writer_domain_overlay.json`）：

```
app.services.wp_template_finder::find_all_template_files
app.services.wp_template_finder::find_template_file_any
```

**根因的精确形态**（比 §10.4 的描述再深一层，值得进 §6 规则 3）：
生成器的 `_RESOLVER_SYMBOLS` 里登记的是 `find_template_file` / `find_template_file_any`
这些**公开名**。Task 8 把三个公开函数内部的互相调用改成了 `*_unresolved` 变体（为了让权威侧
闭环、避免重新进入覆盖层），于是 `_collect_facts` 再也收不到 `resolver_calls`
⇒ `_classify` 返回 `None` ⇒ 三个函数**全部**掉出 `rows`。
overlay 只裁决了其中两个，所以只报两条孤儿。

⇒ **`_RESOLVER_SYMBOLS` 是一份按「公开函数名」写死的名单，任何「把公开入口改成薄委派 +
把真实现挪到私有名下」的重构都会让它失准。** 这类重构在本仓库还会发生（覆盖层、代理层都这个形状），
建议 E 顺手评估要不要把 `*_unresolved` 一族也登记进 `_RESOLVER_SYMBOLS`
—— 那样孤儿会变成"仍被发现"，不必删裁决。两种修法 D 都验证过可行，选哪个是 E 的域。

**归因证据（worktree 对照，非推断）**：在 `$TEMP` 开干净 HEAD worktree 跑同一批判据，
基线 8 failed / 7 errors；D 的工作树 20 failed / 10 errors。差集里**只有** task20 / task30 /
writer_inventory / task74 这 15 项是 D 引入的，全部指向同一个 `WriterInventoryError`。
其余 8 项两边同红（先前就坏，与 D 无关）。
⚠ 做差集时注意：同一用例在两边可能一边是 `FAILED` 一边是 `ERROR`（setup 期抛 vs 用例内抛），
按 `状态 + nodeid` 做差集会把它算成"新增"—— 我第一版脚本就这么误报了 7 项，按 nodeid 归一才对。

**D 侧不会再动这些文件**，E 可任意时点执行。执行后建议重跑：
`test_task20_writer_gate.py` / `test_task30_closure_gate.py` /
`test_workpaper_writer_inventory.py` / `test_task74_domain_adjudication.py`。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-04 | D lane 收口：3/27 → 25/27 + 1 阻塞（Task 23 归 E）+ 1 部分（Task 103）。后端 110 + 前端 15 判据全绿；20 个产物已 add、`??`=0；权威目录 0 改动、版本表 0 残留。四件事交 A/E：分工书本身未入库、E 的 overlay 对齐可执行、备份脚本归属 + `wp_storage/` 裁决、6 个 checksum 漂移 | D |
2026-09-05 | Task 103 收尾（§12.12）：编辑保存路径**已取证**（Playwright 真开 DocEditor，VBA 逐字节保留），推翻 §12.8「编辑路径有结构性障碍」的判断；发现编辑路径丢 `printerSettings*.bin`（7→0）而 conversion 不丢；**否决**「搬回 printerSettings」，改实现 `diff_page_setup` 业务属性校验（真差异 0 项）。后端判据 110 → **126 passed**，变异 10/10 全 RED。`EDITABLE_FORMATS` 未改 ⇒ Task 103 维持 `[-]`，放开 xlsm 转为产品口径决策 | D |

---

## 13. 2026-09-04 19:15 状态：B 的插行已接线，新阻塞点浮出（A 记）

### 13.1 B 的 Wave 3/4 已实质落地

`excel_row_shift.py` 从**生产零引用**（M0 对齐时的实测）变成 **19 处引用**：

```
excel_materialize.py   excel_row_shift 14 · RowShiftPlan 8 · shift_sheet_rows 4
                       row_shift 66 · carries_total_formula 18
adapters/excel.py      row_shift 5
excel_extract.py       row_shift 37 · RowShiftPlan 8
```

⇒ **M2「插行可用」的核心能力已在**（B 的复选框还停在 16–22 未勾，代码先落）。

D2 的首版阻塞随之**变形** —— 不再是「没有插行能力」，而是插行计划已算出来了：

```
[contract_total_formula_not_extendable]
需要插 729 行；但 footer 的合计区间覆盖不到位移后的末行 754，而契约**没有**声明
`footer_anchor.carries_total_formula` ⇒ 引擎无权扩张它。
照插会产出一张合计漏算 729 行的审计底稿。原始判据：footer 格 E26 的公式 'SUM(E13:E25)'
```

这个报错值得表扬：它没有「照插了再说」，而是把「会产出一张合计漏算 729 行的审计底稿」
这个业务后果直接写出来了。

### 13.2 新阻塞点：4/4 契约的 `carries_total_formula` 全为 `null`

B 的 spec Task 14 明写「**不**改任何既有契约 JSON（那会改 canonical digest）；改契约是后续
entry 迁移的事」⇒ **这一条归 A**（发布路径侧），已登记为 P spec 的 Open Gate 5。

裁决依据（实测 footer 行公式，非按常识推断）：

| entry | 受管区 | footer 行 | footer 公式条数 | 形态 | 区间末行 |
|---|---|---|---|---|---|
D2 | `A13:AN25` | 26 | **17** | `SUM(x13:x25)` | 25 = **受管区末行** |
H1 | `A13:AB27` | 28 | **7** | `SUM(x13:x27)` | 27 = **受管区末行** |
G7 | `A79:N83` | 85 | **0** | 无合计公式 | — |
B60 | — | — | 不可验（OOXML 门） | — | — |

⇒ 声明 `carries_total_formula: true` 是**如实描述模板事实**。而 **G7 一条合计公式都没有** ——
这正好解释了四个 entry 里为什么只有它发得出去，也说明 G7 首版的成功**没有**掩盖这条约束。

### 13.3 D2 首版的阻塞链是串联的两层

```
① BP-21：受管区末行 A25 是 `……` 排版占位行          → B（excel_extract.resolve_managed_region）
② carries_total_formula 未声明 ⇒ 合计区间无权扩张    → A（契约 + 完整发布链）
```

**不是二选一**：BP-21 收缩到 `A13..24` 后 footer 仍在 26、公式仍 `SUM(E13:E25)`；插 729 行后
新数据行到 753、`……` 推到 754、footer 推到 755，合计区间**仍**必须扩张。

### 13.4 里程碑现状

```
M0 复选框对齐      ✅ A
M2 插行可用        🟡 B 的核心能力已接线（19 处引用），复选框未勾、变异未跑
BP-21              ⏳ B 未接（resolve_managed_region digest 未变，验收退出码恒 1）
Open Gate 5        ⏳ A（改契约 + 走完整发布链；代价：D2 bundle 现为 approved db877e9dbc73）
M1 首版落库        🟡 1/4（G7 已发；H1 等 BP-21；D2 等 BP-21 + Open Gate 5；B60 卡安全策略）
```

---

## 14. Open Gate 5 只读预演结论（2026-09-04 · A）—— 只改 D2，不动 H1

### 14.1 判据形态：失败形态的移位

隔离单变量的对照 —— 直调纯函数 `plan_managed_writes`，definitions 仍取既有 frozen bundle，
只把它的 `contract` 入参换成内存打了补丁的那份。全程只读，库只 SELECT，产物落系统临时目录。

| entry | 目标底稿 | projection | as-is | patched |
|---|---|---|---|---|
**D2** | `ef7f88e3` / 490,291 B | 28,495 值 / **742 行** | `RowSetDivergence` **[contract_total_formula_not_extendable]** | **推进** → `EditableCellWrite` A25 = `……`（BP-21） |
**H1** | `f663b18c` / **0 B** | 15 值 / 15 行 | `EditableCellWrite` A27 = `……` | **逐字相同** |

**D2 需要 Open Gate 5，且与 BP-21 串联**（§13.3 判断被实测证实）。
**H1 今天不需要** —— store 0 字节 ⇒ 15 行 projection = 15 行物理 ⇒ 不插行 ⇒ footer 门走不到；
BP-21 收缩到 14 行后 baseline 同步变 14 行，仍不插行。

### 14.2 为什么「只改 D2」是更省的

改 H1 契约会作废它的 approved bundle（`05086f4021a6`）与 **4 份**冻结证据，**换不到任何推进**。
只改 D2 时受影响的冻结资产从 9 份降到 **5 份**（H1 的 3 份 + `task70_oo_scenario_refresh.json`
全部避开）。H1 的 footer 确实承载 7 条 `SUM(x13:x27)`，声明为 `true` 是如实的 —— 但**等它真有
数据需要插行时再改**，那时代价才换来真实推进。

### 14.3 实测代价（改 D2 一份）

* contract digest `bdd2f6494185…` → **`cb3beceb1dec…`**；patch 点**仅 1 处**
* `template_definition_sha256` / `instrumentation_definition_sha256` **不变**（模板字节没动）
* **双向锁**：`assert_contract_file_matches_source()` 要求磁盘 JSON 与
  `pilot_d2_large_json.build_contract_payload()` 现算 payload 逐字相等 ⇒ 必须同步改
  **provider 源码 + 跑生成器 `--apply`**。只改一边必打红。
  G7 的 provider 已有先例（显式写 `"carries_total_formula": False` + 理由注释）。
* **解析器无需改动**：`contracts.py` 已解析该键且对非布尔 fail-closed。
* **无旁路**：实测往 `review` 块加键 digest 同样变 ⇒ 不存在「放在不进 digest 的地方」的捷径。

### 14.4 已确认不必付的代价

**D2 / H1 都还没有 published representation**（`content_representation` 仅 2 行：1 opaque +
1 G7）⇒ **无需退役 representation、无需 pointer 迁移**。现在改比以后改便宜。
旧 bundle 不必删 —— Task 76 宿主按 canonical digest 幂等定位，新 digest 产出**新** bundle，
旧的留作历史（正是 S spec AC 5.5 要求的形态）。

### 14.5 预演撞到的一道门（它在正确工作，值得各泳道知道）

```
ExcelAdapterIdentityError [excel_adapter_contract_identity_mismatch]
传入 contract 的 canonical digest cb3beceb1dec… 与 adapter 冻结的 bdd2f6494185… 不一致
—— adapter 按 operation 冻结身份构造，不得跨 entry 复用
```

⇒ **adapter 构造时冻结契约 digest**。改契约后必须重走 definition/bundle 发布链才能生效，
没有「先试试看」的捷径。也因此预演必须直调 `plan_managed_writes`：
`adapter.materialize(contract=...)` 的那个入参**只用于身份断言**，真正生效的是
`definitions.contract`（来自 frozen bundle）—— 换它对行为零影响，容易误以为验过了。

### 14.6 里程碑现状

```
M0 复选框对齐   ✅ A
M2 插行可用     🟡 B 核心能力已接线（19 处引用），复选框未勾、变异未跑
BP-21           ⏳ B 未接（resolve_managed_region digest 未变，验收退出码恒 1）
Open Gate 5     🟡 A 预演完成、代价已量化；实施待人工确认（动已审契约）
M1 首版落库     🟡 1/4（G7 已发；H1 只等 BP-21；D2 等 BP-21 + Open Gate 5；B60 卡安全策略）
```

🔴 **H1 的解除条件已收窄为「只等 BP-21」** —— 这是本次预演最有价值的结论：原以为 H1 也要
付契约代价，实测不需要。BP-21 一落地 H1 立刻可发。

### 9.5 L2a（B）Wave 5 收口 —— spec 完成 26/27 + 1 交接 · 2026-09-04

复选框实扫 **26 完成 / 1 交接 / 总 27**。辐射面 **1454 passed / 2 skipped / 0 failed**
（两个 skip 都是**诚实标注**，不是绕过 —— 见下）。

#### Task 19（可插行清册）：词表从 7 格扩到 9 格

交付 `check_excel_row_insertion_readiness.py` + T3（21 例）。**4 个已发布契约的实测结论**：

| adapter | verdict |
|---|---|
`b60.hour_budget` | `insertion_safe` |
`g7.soe_subsidiary_disclosure` | `insertion_safe` |
`d2.receivable_detail` | `blocked_total_formula_not_extendable` |
`h1.disposal_check` | `blocked_total_formula_not_extendable` |

design.md 的词表只有 7 格，实测必须补两格（`blocked_static_row_below_insertion` /
`blocked_total_formula_not_extendable`）。**少这两格，清册会把「引擎明确拒绝」错报成
`insertion_safe`** —— 那是会让人以为可以上线的假绿。

🔴 **本脚本自己制造过一次这种假绿，值得记下**：首版手写了第二份 marker 定位（三载体
sharedString / inlineStr / str），结果在 **H1 / B60 / G7 上一个都找不到** —— 那三份模板
既没有 `sharedStrings.xml`，中文又以**数字字符引用**（`&#21512;&#35745;` = 合计）存在
inline `<t>` 里，而生产侧早有 `_decode_numeric_char_refs` 处理这一形态。找不到之后清册
走进「无 footer ⇒ 无合计漏算问题」那一支，**把 3 个 entry 全报成 `insertion_safe`**。

修法两条：改调生产的 `M._find_marker_row`；对「契约声明了 footer 却定位不到」**fail closed**。
T3 里 `test_marker_location_reuses_the_production_finder` 按**函数身份**钉住，
并反向断言脚本里不得再出现 `t="inlineStr"` 字样（第二份实现回来即红）。

⚠ 这是本 spec 第四次踩「手搓第二份实现」。前三次分别是：C 的 `r:id` 正则、
我的 footer 冻结行号误推、verifier 侧归一化表。**判据必须复用唯一入口。**

#### Task 21（真实可打开性）：不是 UNVERIFIABLE，是真验证

容器 `audit-onlyoffice` 实测 `onlyoffice-documentserver 9.4.0-129`，文档引擎
`FileConverter/bin/x2t` 版本 `9.4.0.129` —— 与 AC 11.5 要求的 9.4 一致。

🔴 **实测出 `x2t` 退出码的能力边界，并把它钉成判据**（不是写在注释里）：

| 损坏形态 | rc | 产物大小 |
|---|---:|---:|
原始模板（对照） | 0 | 130,367 |
删掉整个 `sheet4.xml` | 0 | 123,384 |
sheet part 换成垃圾字节 | 0 | 123,384 |
`workbook.xml` 换成垃圾 | 0 | **1,299** |
只砍 `</sheetData>` | 0 | 130,256 |
删掉 `[Content_Types].xml` | **89** | 0 |
根本不是 zip | **89** | 0 |

⇒ 退出码只对**容器级**损坏敏感。**所以判据是「rc=0 且产物 >= 对照的 80%」** ——
`workbook.xml` 坏时产物塌到 1.3 KB，正是量级判据抓住的形态。

**反向自检首轮打红，捞出真问题**：我原本用「砍 `</sheetData>`」当反向用例，实测 x2t 对它
返回 0 ⇒ 断言失败，暴露出「正面结论其实什么都没证明」。改用实测确认会被拒的两种容器级
损坏，并**另加一条判据把「sheet 级损坏被容忍」这个边界本身钉住** —— x2t 将来变严格时
它会红，提示更新能力表并加强结论。

**诚实表述**：本层证明「OnlyOffice 9.4 引擎能把产物当成完整工作簿解析出来」，
**不是**「编辑器里所见即所愿」。后者需人工在真实编辑器里看，本层不冒充它。

#### Task 20：归属冲突，按 §2 交接给 E

§2 把 `backend/scripts/diagnose/mutate_*.py` 判给 **E**，B 行文件面只有五个生产文件。
本 spec 的 tasks.md 把 N3 写成 B 的产物 —— 与 §2 冲突，**按 §2 执行**：
B 提供清单与预期态，E 写文件并统一四态判读标准。

交接件：`docs/operations/excel-row-insertion-mutation-handoff.md`。
清单**已实测验证 28 条全 RED**（不是六条 —— 随交付面增长到 28），基线 `137 passed`。

两条留给 E 的判读教训：
1. **`errors` 必须计入「红」** —— 变异写出语法错误时 pytest 报 `N error` 而非 `N failed`，
   只数 `failed` 会把「模块根本没跑起来」判成 GREEN（M28 首轮实测误判）。
2. **mutation 本身必须语法合法** —— 否则 WRONG-TEST 与 RED 分不开。

🔴 **变异检验捞出一处真缺陷（M28）**：它首轮 GREEN，暴露出「T4 只调
`apply_plan_zip_with_report`，从未走完整 `materialize_projection`」⇒
`assert_shifted_footer_gates` 的调用点**一次都没被执行**，两个新参数在生产链路上是
零消费的死参数。补 `TestMaterializeProjectionRunsTheWholeChain` 后转 RED。
**这正是我在 §9.4 里警告过的假绿第①源，被自己的变异脚本抓到。**

#### Task 22：归因型判据 + 两次自打红

结构缺席判据**全部按归因判**：仓库当前多泳道并行（索引里同时有 B 与 D 的产物，D 还落了
`V154` 迁移），全局等值型判据会被 D 的迁移打成假红。判据统一为「**在本 spec 声明的五个
交付文件里**，某类东西必须缺席」。

🔴 **本文件被自己的判据打红两次，两次都是子串型判据的锅**：
1. `externalLink` —— 生产侧本来就有只读的部件分类表
   （`"external_link": re.compile(r"^xl/externalLinks/")`），那是**识别**外部链接用的，
   与「放宽许可」正好相反。改判**放宽动作**本身。
2. `os.getcwd()` —— 本条自己的 docstring 里写着这几个字（用来说明什么形态不行）。
   改判 **AST**：注释与文档字符串不是代码。

⇒ 同一教训两次：**判据要落在语义（AST / 行为）上，不落在字符出现。**

两个 skip 都是诚实标注：
* AC 11.6（`max_examples >= 100`）在本 spec 上**无载体** —— 本 spec 的属性测试形态是
  「实测 fixture + 参数化」，不用 hypothesis。判据仍在把关：一旦有人引入 `@settings` 就生效。
* 清册落盘产物未生成（`--json` 是可选动作）。

#### 给 C 的交接确认（§5 义务）

C 的 Task 101 上游就绪门实测**已打开**：
`test_workbook_row_change_upstream_gate.py` 现在报
`SKIPPED: 上游 Wave 4 已就绪，本反向判据不再适用（改由门后各任务自身判据接管）`。
⇒ **C 的 Wave 1 起全部任务可以开工。**

C 开工前请读 §9.3 的一条：我的 `&quot;` 实体字面量修正没扰动 C 的零回归基线，
但那是**运气不是设计** —— C 的 Task 28 要求「加 `propagate_sheets` 后逐字不变」，
若改动碰到同一批公式，C 会把 diff 误归因给自己的新参数。

#### 未完的两件（不影响本 spec 收口）

1. **Task 20 的文件本体**在 E 手上。
2. **D2 的 729 行 × 39 列是否撞 `SyncLimits` 预算**仍是 Open Gate ——
   清册的 `--rows`（取真实库行数）未实现，结构性结论不依赖库故可离线复现。

---

## 11. E 泳道第二份报告（2026-09-04，同日追加）

§10.3 说「批量迁移是合规任务、应排期不该抢工」。**排期前先做了可行性实测，结论更硬：
7 个剩余脚本今天一个都不能等价迁移。** 阻塞不在工作量，在共享件的表达能力。

### 11.1 两道闸门，逐个实测

**闸门一：守卫基线非绿 ⇒ 共享件直接 ABORT（退出 4）。**
kit 要求变异前基线全绿，否则差集判定不可信。实测 7 个脚本各自守卫文件的基线：

| 脚本 | 基线 | 判定 |
|---|---|---|
`mutate_task4_callback_contract_guards.py` | **37 passed** | ✔ 可完整验证 |
`mutate_task7_staged_artifact_boundary_guards.py` | **34 passed** | ✔ 可完整验证 |
`mutate_task70_oo_scenario_guards.py` | 4 failed / 83 passed | 🔴 只能验 `--check-anchors` |
`mutate_task71_census_lock_guards.py` | 4 failed / 210 passed | 🔴 同上 |
`mutate_task71_chaos_guards.py` | 4 failed / 205 passed | 🔴 同上 |
`mutate_task72_pre_delete_eligibility_guards.py` | 5 failed / 60 passed | 🔴 同上 |
`mutate_workpaper_writer_inventory_gates.py` | 3 failed / 34 passed / 1 error | 🔴 同上（即 §10.4（一）那条碰撞） |

5 个基线红里，反复出现的是 `TestReportIsFreshAndByteLocked::test_gate_check_passes` 与
`test_task67_structural_pre_reconcile.py` 的三条 —— 都是**新鲜度/字节锁**判据，
属并发在途改动的连带态（§6 规则 3 的形态），不是这些脚本自身的缺陷。

**闸门二：仅剩的两个基线绿脚本，用了共享件表达不了的两种语义。**

kit 的 `kind` 全集实测 = `replace` / `delete` / `insert` / `swap` / `move`，**无 `replace_all`**；
`want` 的 `ANY_RED("*")` 只是弱判据，**无法表达「期望 GREEN」**。而这两个脚本：

| | task4 | task7 |
|---|---|---|
`ALLOW_MULTI`（锚点多处命中、全量替换） | ID13（evidence 5 个承载行） | **3 条**（ID18 / 20 / 21） |
故意期望 GREEN 的负对照 | ID12「只加一条无害项，用于确认判据方向正确」 | L262「守卫按字段语义判据而非整文件 hash，无害新增不应误红」 |

**负对照不是可有可无的。** 它证明的是「判据不会把无害改动误报成违规」——
正是 §6 规则 4 要的反向自检。删掉它 = 少一条判据；把它翻成 RED = 改判据。
两者都违反 Property 26 的等价迁移要求。

顺带把可换算的部分也测清了，免得后来者重做：**task4 的 15 条里 12 条可机械换算**成
kit 的单行锚点（原锚点多是**无缩进子串**，补齐缩进后整行唯一即可）；ID3 / ID7 需
`scope` + `offset` 相对定位（实测 ID3 用 `"recovery_outcome": …` 唯一行 offset=+2、
ID7 用那条 `meaning` 唯一行 offset=+1 均可命中）。**只有 ID12 / ID13 无解。**

### 11.2 这与冻结名单里已有的裁决同族

`_LEGACY_NOT_REQUIRED` 里 `mutate_h_cycle_guards.py` 与 `mutate_trim_decision_guards.py`
的登记理由，写的正是同一件事：

> 「共享件架构限制：一条 Mutation 只有一个 side」…「非等价拆条（1条→2条，判定矩阵结构改变
> ⇒ 违反 Property 26）」…**「须单独立项扩展共享件后再迁」**

⇒ 「扩展共享件要单独立项」是**已有裁决**，不是我新提的口径。而冻结名单
**只许缩小、不接受新条目**，所以 task4 / task7 也不能靠登记豁免绕过。

### 11.3 量化：扩展 kit 能解锁多少（可直接作为立项依据）

全仓 39 个未采纳脚本（含并发新增），按「被哪种缺失能力卡住」分类实测：

```
未采纳总数              39
被缺失能力卡住           7（3653 行）
   需 replace_all        3
   需期望-GREEN 负对照    3
   需多侧合并判定         3   ← 已在冻结名单登记（h_cycle / trim_decision）
无上述阻塞               32（14653 行）
```

当前 CI 违规 20 条中：**17 条无表达能力阻塞**（其中多条另有「基线红」这道闸门），
**3 条被卡死** = `mutate_task4_*`、`mutate_task7_*`、`mutate_task71_chaos_*`。

**建议的立项范围（小而闭合，三件）**：
1. `kind` 增 `replace_all`（锚点多处命中并全量替换；命中数写进声明并在 `--check-anchors` 里核对，
   保留「命中数变化即 ANCHOR-MISS」的强度）
2. `want` 增显式**负对照**态（变异后应当无新增失败；GREEN 才是通过，非 RED 即失败），
   与现有 `ANY_RED` 弱判据区分开
3. 迁移 task4 / task7 / task71_chaos 并逐条验等价（判定矩阵逐条比对，Property 26）

**不建议**在没有这两种能力时硬迁 —— 那必然以「删掉负对照」或「削弱变异强度」为代价，
而这两件恰好是变异检验存在的理由。

### 11.4 顺带：并发实况两条（现读，非记忆）

**① P spec 的守卫已经存在了，§10.2① 那条结论已过期。** 会话中途新出现
`backend/scripts/diagnose/mutate_projection_first_publication_guards.py`（34,955 B，`??` 未跟踪，
自报 **P spec Task 10.1**），其引用的
`backend/tests/workpaper_sync/test_projection_first_publication.py` 与
`test_projection_lane_registry.py` 均已在盘。⇒ A 正在推进 P spec 的 Wave 14。
按 §6 规则 1，E 不碰该文件。**也就是说：E 的主线二不再是「无守卫可打红」，而是「等 A 收口」。**

**② 该新脚本已使违规数由 19 回到 20。** 它未采纳共享件（同族阻塞待查），
建议由 A 在 P spec 收口时一并处理，或纳入 §11.3 的立项。

### 11.5 E 现在还能推进的，只剩两件

- **等 D 收口** → 执行 §10.4（一）的 overlay 孤儿对齐（恰 2 行，修法已备好）
- **等 §11.3 立项** → 扩展 kit 后迁 task4 / task7 / task71_chaos

在此之前 E 没有可交付的**判据类**产物了 —— 硬做会以削弱判据为代价。
Word 域（Task 63 / Task 61 判据侧）仍等 L1；BP-20 仍等业务方给 11 份模板的 `${token}`。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-04 | E 第二份报告：实测 7 个剩余脚本**今天一个都不能等价迁移**（5 个基线红使 kit ABORT；仅剩两个基线绿的用了 kit 无法表达的 `replace_all` 与「期望 GREEN 负对照」）。量化扩展 kit 可解锁 3 条被卡死违规，给出小而闭合的立项范围。另记 P spec 守卫已就位、A 已在做其 Task 10.1 变异脚本 | E |

### 11.6 补记：§10.4（一）那条碰撞还暴露了门自己的一个缺陷（E 的文件，本轮**不改**）

复查孤儿是否仍在时发现：`check_workpaper_writer_revision_gate.py` 现在**崩在 traceback 上**，
而不是走它自己设计的 `[FAIL] … return 2` 路径。

根因是异常类型不匹配：门在 L347 只捕 `WriterGateError`（自己在 L62 定义的），
而它在 L107 调用的 `generator.build_inventory(...)` 抛的是**生成器模块的**
`WriterInventoryError` ⇒ 直接逃逸出 `try`。

后果：**不是 fail-open**（退出码仍非零，1 而非 2，仍然阻断），但操作者看到的是 traceback
而不是那句写好的诊断。门本身在「新鲜度 fail-closed」这一层是有效的 —— 它确实拒绝了
在 stale/不一致清册上出结论，只是拒绝得不体面。

**本轮不修**，理由与 §10.4（一）一致：该文件的守卫基线现在因 D 的在途改动而红
（`test_task20_writer_gate.py` 4 条 + `test_workpaper_writer_inventory.py` 4 条），
改了无法用绿基线验证 —— 那正是我建议别人不要做的事。
修法很小（把生成器异常一并捕获并归入 `[FAIL]`/退出 2），**并入 overlay 孤儿对齐那一轮一起做**，
届时能在恢复的绿基线上验证。

D 的 `wp_template_finder.py` 已从工作树态（` M`）转为已暂存（`M `），说明其改动趋于定形；
孤儿实测仍在（那两条裁决依旧无对应源码行）。**请 D 提交/收口后通知 E。**

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-04 | 补记 §11.6：writer gate 的 `except WriterGateError` 捕不到生成器的 `WriterInventoryError` ⇒ 门崩 traceback、退出码 1 而非 2（非 fail-open，仍阻断）。本轮不修，并入 overlay 对齐轮次以便在绿基线上验证 | E |

---

## 12. E 泳道第三份报告（2026-09-04，同日追加）

§11.5 说 E 只剩「等 D」「等立项」两件。**这条结论当场被 C 的进展推翻了** —— C 已交出
W spec 的上游就绪门守卫，而它的变异脚本正是 C 明确移交给 E 的活。已交付。

### 12.1 已交付：`mutate_workbook_row_change_upstream_gate_guards.py`（W spec 的 X1 部分）

**实测 6/6 RED、覆盖面 1/1、退出码 0**；被变异目标 `git status` 保持 `A `（无 `AM` ⇒ C 的
文件完整复原）；守卫基线复验仍 17 passed / 1 skipped；`.mutbak` 残留 0。

**交接依据**（W spec Task 26 正文原文）：

> ⚠ **X1 文件归 E**（分工书 §2：`backend/scripts/diagnose/mutate_*.py` 由 E 统一写，
> 四态判读标准统一）。C 的交付物是**变异清单 + 每条的预期态**，交 E 落成脚本

🔴 **为什么这件必须做**：C 在 Task 26 正文记了「已交付的 T5 变异清单（**6/6 RED**，可直接
并入 X1）」。但实测 W spec 目录下**只有三件套、无 evidence 目录**，全仓**无任何变异脚本引用
该门** ⇒ 那句「6/6 RED」当时**没有可复现产物**，而 Task 26 自己要求「CI job 在干净 checkout
下可跑」。C 的验证工作是真的，只是留在了会话里。现在它能被任何人一条命令复算。

**六条变异**（严格按 C 的清单，逐条对应）：

| # | 变异 | 打红的判据 |
|---|---|---|
M01 | 行首锚定**组合变异** | `test_checkbox_scan_is_line_anchored` |
M02 | `\]\*?` 去掉 `\*?` ⇒ `*` 子任务读不到、分母 27→22 | `test_star_marked_subtasks_are_read_and_not_collapsed` |
M03 | 重复编号不再 fail-closed | `test_duplicate_checkbox_is_fail_closed` |
M04 | `~`（进行中）当成就绪 | `test_gate_behaviour_on_synthetic_states` |
M05 | `propagate_sheets` 检测器短路 | `test_propagate_sheets_detector_fires_on_synthetic_violation` |
M06 | A1 owner 恒报唯一 ⇒ 掩盖第二入口 | `test_a1_owner_detector_fires_on_second_entrypoint` |

**M01 是这批里唯一需要设计的一条。** C 已实测警告：正则里的 `^` 与调用侧的 `.match`
**互为冗余**（`re.match` 自身锚定位置 0；`^` 无 MULTILINE 时也只匹配串首），单点变异必 GREEN
—— 这是 C 记录的「第二类无效变异用例」。解法是在**一行之内同时击穿两道**：把 `^\s*-\s`
换成 `.*-\s`，前导 `.*` 让 `.match` 的位置锚定一并失效。实测原正则 `{'16': [' ']}`、
变异后 `{'16': [' ', 'x']}`（正文叙述句里的 `- [x] 16.` 被当成真复选框）⇒ 判据敏感。

**M06 值得单记**：它证明了那条反向自检是承重的。把 owner 钉成恒为 `_rewrite_formula_refs`
之后，跑**真实源码**的 `test_single_a1_rewrite_entrypoint` **照样绿**（今天确实只有一个入口）
—— 只有「喂一份有第二入口的合成源」那条反向自检能抓到。Property 27 若少了它就是恒真重言式。

### 12.2 三条边界，E 没有越线

1. **不碰共改文件。** 六条变异全部落在守卫文件自身（它同时承载检测器与测试），与 B / C
   共改的 `excel_row_shift.py` / `excel_materialize.py` / `excel_extract.py` **零交集** ⇒
   不受 Task 101 门的约束（门约束的是改那三个文件的行为）。
2. **不勾复选框。** Task 26 在 Wave 6（`depends_on: [5]`），而 Wave 5 的 Task 25 / 29 现读均为
   `[ ]`、Task 101 自身为 `[~]` ⇒ **Task 26 未完成**。本文件只交付其中「判据已就位、基线已绿」
   的 Wave 0 门那部分；Task 26 的范围边界判据、产物入库核查与门后各 Wave 的变异，等 C 推进
   到位再补。**复选框由 C 或 A 裁决。**
3. **C 的文件原样归还** —— 逐变异 `finally` 还原 + md5 自证，收尾 `git status` 仍是干净的 `A `。

### 12.3 采纳门的账（现读）

违规数仍是 **20**，但构成变了：E 迁 task61（20→19）、A 新增 `mutate_projection_first_publication_guards.py`
（未采纳共享件，19→20）、E 这个新脚本走了共享件故**不计入**。
⇒ **若这两件没做，现在是 21。** A 那个脚本建议并入 §11.3 的立项一起处理。

### 12.4 一条方法论，建议补进 §6 规则 4

C 记录的两类无效变异用例（被收敛语义掩盖、被第二道防线挡住）**都有解，不必降级为「守卫缺陷」**：

* 被**收敛语义**掩盖 ⇒ 改判据的观测量（本例：从「最终取值」改成「全部出现次数」+ 重复即
  fail-closed），C 已经这么做了，所以 M01 今天是敏感的；
* 被**第二道防线**挡住 ⇒ 找一个能在**单点内同时击穿两道**的表达（本例 `.*` 前缀），
  而不是把两条变异拆开各判一次 GREEN。

把它们误判成「守卫缺陷」会去改本来正确的守卫 —— 那比不做变异更糟。

### 12.5 E 现在的待办（现读，比 §11.5 少一件）

- **等 D 收口** → overlay 孤儿对齐（恰 2 行）+ 顺手修 §11.6 的异常捕获缺陷。
  D 的 `wp_template_finder.py` 现读又退回 ` M`（未暂存）⇒ 仍在改，孤儿仍在。
- **等 §11.3 立项** → 扩展 kit 后迁 task4 / task7 / task71_chaos。
- **等 C 推进 W spec 到 Wave 5 完成** → 补齐 Task 26 的其余部分（范围边界判据 + 产物入库
  + 门后各 Wave 的变异清单落地）。
- Word 域仍等 L1；BP-20 仍等业务方给 11 份模板的 `${token}`。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-04 | E 第三份报告：交付 `mutate_workbook_row_change_upstream_gate_guards.py`（W spec X1 的 Wave 0 门部分，6/6 RED、覆盖面 1/1），把 C 记在 tasks.md 里的「6/6 RED」变成可在干净 checkout 复算的产物；M01 用 `.*` 前缀解决 C 记录的「第二道防线」无效用例；未勾 Task 26 复选框（Wave 5 未完成，留 C/A 裁决） | E |

### 11.11 追补：门已开、零回归已验证、Task 29 收口（C · 2026-09-05）

进度 **7/30 → 28/30**。⚠️ 其中 Task 5/7/8/9/10/11/12/13/27/28 由**并发会话**在门开后交付，
C 本轮做的是：**验证门的放行、验证零回归、收口 Task 29、并把两条「人工确认」固化成判据**。

**🔴 一、Task 6 抢在门前冻结基线的价值已兑现**

现读：上游 Wave 4 的 16/17/18 **全 `[x]`** ⇒ 门开；`excel_row_shift.py` 从 78,416 长到
**99,223** 字节；`propagate_sheets` **已进** `_rewrite_formula_refs` 签名。

而 Wave 0 冻结的零回归基线 `--check` **逐字相同**：
351 份 / 126,565 条公式 / 182 份含跨 sheet / 144,154 处引用 / 72,825 条 / 3D 0 / 外部 2,908。

**这是 AC 7.4 的独立证据，不是事后声明** —— 基线在该参数加入之前就已入库，git 里有时序。
若基线是事后补的，「与本 spec 前逐字相同」根本无从证伪。三个情景全部不变 ⇒ 加参数是纯增量。

Property 27 复核：`_A1_PIECE_RE` 的 AST owner 仍恰为 `{_rewrite_formula_refs}` ——
上游长了 20KB **没有**新造第二个 A1 改写入口。

门的反向判据按设计**自动 skip**（只在门关时适用）⇒ 17 passed / 1 skipped，不是漏跑。

**🔴 二、Task 24 的三向锁抓到一次真实的「真源改了、冻结产物没跟上」**

Task 13 落地后有人改了 G1 生成器（+26/-7：`REASONS` 加 `implemented`、D2 按 `demand` 翻转、
`affected_templates` 改为按 `in_contract` 分支），但**没重跑 `--apply`**
⇒ 守卫当场打红「`contracted_entries` 变了」。这正是三向锁要拦的形态。

C 的处置顺序刻意是**先验证再重冻结**（`propagated` 是声明、不是证据）：先跑 Task 8~13 的
**240 例全绿**确认传播能力真落地，才 `--apply`。diff 规模 **6 插 5 删**，逐条可解释。

**🔴 三、那次改动顺带修掉了 C 上轮的一处真缺陷**（对方注释里点明了）

C 上轮写的 `"blocked" if not in_contract else "blocked"` —— **两个分支完全相同**的三元。
它当时不影响结果（那时两类都该是 blocked），但把「这一维本该随契约分支」这件事藏了起来。

**这与 §11.10 抓到的「布尔值只读不重算」是同源形态**：看着在分支/在校验，实际从未生效。
建议 E 把这一类并入 X1 的标准形态清单：

> **恒等分支 / 只读结论**：`X if c else X`、`assert payload["ok"]`（`ok` 由被检查方自己写）、
> 只查冻结产物不查现算 —— 三者都是「代码结构上存在、语义上从未生效」。
> 判别法：**把那一维反过来，看有没有任何判据变红**。

**四、本轮新增两条判据：把「人工看 diff」固化成可复算的守卫**

1. `test_only_d2_flipped_to_propagated` —— 翻成 `propagated` 的 entry 集合**恰为** D2、
   D2 的 `propagation_demand_sites` **恰为 52**、受影响模板分布**恰为**
   `{(blocked, no_projection_contract): 135, (propagated, implemented): 1}`。
   🔴 判据形态刻意**按状态计数**而非「diff 只有 N 行」—— 后者依赖 git 工作树，
   在干净 checkout 上无从求值（那正是 §10.2 那类 CI 必挂的根因）。
2. `test_all_three_states_are_reachable` —— 三态**各自**被真实取到。
   🔴 本轮之前 `propagated` 是个**从未被使用**的状态值（词表里列着、清册里一条都没有），
   那时守卫只能验「词表没漂移」，验不到「这个状态真的可达」= 空集上恒真。

**五、C 的流程自纠（登记备查）**

C 一度在 `--apply` **之前**跑守卫，module-scope 的 `stored` fixture 缓存了旧清册
⇒ 报出 4 failed，其中包括「136 份全 propagated」这种不可能的分布，一度让我以为
`in_contract` 判定有 bug。查到底是我自己的操作顺序问题：单独重跑即 1 passed，
`--apply` 后全套 25 passed。

**教训（对全员有用）：改冻结产物的任务，必须先 `--apply` 再跑守卫** ——
否则 module-scope fixture 读到的是过期快照，报出的差异指向错误的根因。

**六、C 的当前状态**

- 进度 **28/30**。只剩 **Task 25**（真实 Excel/OnlyOffice 打开传播产物，需真实环境；
  取不到就标 UNVERIFIABLE，不用 fixture 冒充）与 **Task 26**（X1 变异脚本，按 §2 归 **E**）
- 机器校验：10 Requirement / 62 AC / 39 Property（1..39 无空洞）/ 30 任务 / **悬挂 AC 0 条**
- **336 passed / 1 skipped**（本 spec 10 个测试文件 + B 的 `test_excel_row_shift.py`，
  确认对 B 零影响）
- 本轮改动均为已入库文件的 `M`：清册 JSON（6 插 5 删）、清册守卫（+2 判据）、tasks.md

---

## 13. E 泳道第四份报告（2026-09-05）：W spec Task 26

按 §12.5 的待办推进 Task 26。**三项交付两项半**，Task 26 复选框已按实际状态置 `[~]`（不是 `[x]`）。

### 13.1 交付清单（全部实测）

| 产物 | 状态 |
|---|---|
`backend/scripts/diagnose/mutate_workbook_row_change_guards.py` | `--run all` **9/9 RED**、覆盖面 **2/2**、退出码 0 |
`backend/tests/workpaper_sync/test_workbook_row_change_scope_boundary.py` | **10 passed**（Requirement 9.1–9.6 逐条可执行化） |
`governance-checks.yml` 追加 job `workbook-row-change-scope-and-mutation-anchors` | YAML 已验（163 jobs / 4 steps），依赖文件全已跟踪 |
两个新产物 | 已 `git add` |

**文件名按记号表更正**：上一轮我建的是 `mutate_workbook_row_change_upstream_gate_guards.py`，
而 tasks.md 的文件记号表规定 X1 = **`mutate_workbook_row_change_guards.py`**。已改名归位。

**范围边界六条的落点**（判据一律落在可复算量上，不用「字符不存在」）：

| AC | 边界 | 落点 |
|---|---|---|
| 9.1 / 9.2 | 不做 reorder / 列变更 | `RowChangeKind` 成员恰 `{INSERT, DELETE}` + 计划无列方向字段 |
| 9.3 | 不放宽 OOXML 安全策略 | `workpaper_sync_limits.json` 三个开关（实测 `allow_external_relationships=False`） |
| 9.4 / 9.5 | 跨工作簿 / 图表 / 透视 | 三者 ∈ `UNPROPAGATED_REASONS` 且 ∉ `PROPAGATION_CARRIERS`，两词表不相交 |
| 9.6 | 不改 `backend/wp_templates/` | N1 的 AST 里无指向该目录的写入调用（双向变异：漏报 + 误报各一条） |

### 13.2 三条实测教训（都是我自己踩的，留档防复发）

**① 我的检测器首版漏掉「经变量传递」的写入 —— 被自己的反向自检当场打红。**
`Path('backend/wp_templates').write_bytes(...)` 认得出，但

```python
target = Path('backend/wp_templates')
(target / 'D2.xlsx').write_bytes(data)   # ← 漏掉
```

认不出（那次调用的子树里只有 `target`，没有目录字面量）。**而这恰是真实代码最可能的写法。**
补了变量绑定追踪（迭代到不动点，支持 `a = Path(...); b = a; b.write_bytes(...)`）后 10 passed。
反向自检的价值就在这里：它不是让判据更好看，是让判据在**我写错的时候**红。

**② 锚点必须按内容现查，不得沿用早先探测的行号。**
C 清单第 6 条我首版锚在 `assert row["propagation_demand_sites"] == 52, (`（探测时在 L305）。
实测判 **GREEN**。排查发现 C 在本会话期间**重写了 `test_workbook_row_change_reachability.py`**
（现 534 行），那行连同 `len(affected) == 136` 一并不存在，L305 现在是别的断言。

🔴 而 `--check-anchors` **报了 OK** —— 因为共享件拿「去行尾整行文本」在**当前**文件里查唯一命中，
我给的文本恰好与另一处同内容的行匹配上。**「锚点命中」与「命中我想要的那一处」是两件事。**
这也正是 GREEN 这一态的价值：按退出码判定会把「锚点漂移」记成 RED，永远发现不了。

**③ GREEN 的正确用法是补强判据，不是记账。**
首轮我编了一条「把词表判据的 `==` 降级成 `>=`」，并在 `why` 里写了「本条必须 GREEN 才是坏消息」
—— 这是**设计错误**：kit 语义里 GREEN 恒等于「守卫有缺陷」，无法表达「预期不红」。
而这条变异揭示的问题是真的：降级后真实枚举仍只有两个成员，**没有任何常规判据能观察到**。
正解是元判据 —— 已补 `test_boundary_equality_assertions_are_not_downgraded_to_subset`
（读自身 AST，断言那条 `assert` 的比较节点是 `ast.Eq` 而非 `GtE`），同一变异随即 **GREEN → RED**（现 M11）。

另一条首轮 GREEN（摘掉 `reason in UNPROPAGATED_REASONS`）归因为 **C 记录的「第二道防线」形态**：
紧随的 `not in PROPAGATION_CARRIERS` 与 `test_..._are_disjoint` 仍成立 ⇒ 不红。
该断言对**将来**词表变化仍有意义，故守卫侧保留，但不为它编一条注定 GREEN 的变异。

### 13.3 未完成的半项，以及为什么不硬做

**C 清单第 6 条「分母期望值改错」未入 X1。** 正确锚点是 C 新版里的
`assert with_demand == {"d2.receivable_detail": 52}, (`
（`test_d2_is_the_only_entry_with_propagation_demand`），但**该守卫文件当前基线是红的**：

```
清册 workpaper_row_change_reachability.json：D2 = propagated / implemented   （Task 29 已 [x]）
同文件 L440：assert row["state"] == "blocked" and row["reason"] == "pending_implementation"
⇒ AssertionError: 'propagated' == 'blocked'
```

这是 **C 的在途不一致**（清册为 `AM`、Task 29 刚从 `[ ]` 勾成 `[x]`，正在收口），不是我的债 ——
我的变异已全部还原，该文件 `git status` 是干净的 `A `。共享件在基线非绿时 ABORT，
且在移动目标上锚定必然再次漂移（教训②刚发生过）⇒ **留待 C 收口后由 E 补**，
届时把该守卫加进 `GUARD_FILES`，覆盖面 2/2 → 3/3。门后各 Wave（T2/T3/T4）的变异清单同理待交付。

### 13.4 边界：没有越线

- **不碰共改文件。** 九条变异全落在守卫文件自身，与 B/C 共改的
  `excel_row_shift.py` / `excel_materialize.py` / `excel_extract.py` 零交集 ⇒ 不受 Task 101 门约束。
- **C 的文件原样归还。** 逐变异 `finally` 还原 + md5 自证；收尾 `.mutbak` 残留 **0**，
  两个被变异文件均为干净 `A `。中途一次并发交叠留下 `.mutbak`，被 kit 起手门正确 ABORT 拦下
  （这正是它该有的行为），已 `--restore` 清零。
- **CI 只挂只读两步**（范围边界判据 + `--check-anchors`），不挂 `--run all` ——
  后者要改文件再还原，在 CI 上与并发 job 争用工作树，且需基线全绿。
- **改 tasks.md 前核对字节区间**：C 的在途 hunk 在 L164 / L916-943，Task 26 在 L955，不冲突。
  改后复选框仍 30 条，上游门守卫（它解析 tasks.md）复验 17 passed / 1 skipped。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-05 | E 第四份报告：W spec Task 26 交付三项中的两项半（X1 脚本 9/9 RED、范围边界判据 10 passed、CI job 追加、产物入库），按记号表把 X1 改名为 `mutate_workbook_row_change_guards.py`；Task 26 置 `[~]`。记三条教训：反向自检抓出我自己检测器漏「经变量传递」、锚点不得沿用旧行号（`--check-anchors` 会因同内容行误报 OK）、GREEN 应用于补强判据（据此补了元判据锁 `==` 不被降级）。第 6 条待 C 收口 reachability 守卫基线后补 | E |

### 11.12 追补：Task 25 收口，C 泳道 29/30（C · 2026-09-05）

只剩 **Task 26**（X1 变异脚本，按 §2 归 **E**）。机器校验：10 Requirement / 62 AC /
39 Property（1..39 无空洞）/ 30 任务 / **悬挂 AC 0 条**。

**产物**（🔴 新建的 T8 是 `??` 待入库）：

```
?? backend/tests/workpaper_sync/test_workbook_row_change_openability.py   T8  6 passed / 4 skipped
AM backend/tests/workpaper_sync/test_workbook_row_change_reachability.py  T7  修一条漏改
```

**🔴 一、AC 8.4 的「求值正确」实测出不可验边界 —— 并抓到一类新的假绿**

三层判据（仓库门 → openpyxl → OnlyOffice `x2t`）全部落地，第三层**在真实环境取到了证据**：
`'明细表D2-2'!AC26` 传播成 `AC28`，x2t 走 xlsx→bin→xlsx 后产物里是
`<f>&apos;明细表D2-2&apos;!AC28</f>` —— 真实引擎解析→序列化→写回，行号 28 完整保留。

**但 AC 8.4 要的是「可打开**且求值正确**」，而 x2t 不重算公式。** 实测：

```
往受管表目标格 '明细表D2-2'!AC28 写入 424242，再送 x2t 回转：
  目标格本体      → <c r="AC28"><v>424242</v></c>   （值被搬运保留）
  引用它的两个格  → <v>0</v>                        （**没有**变成 424242）
写标记前/后两次回转，引用格的 <v> 完全相同 ⇒ 未重算
```

⇒ 求值层登记 **UNVERIFIABLE**，结构层可验。两者差一个重算引擎。

🔴 **这是「用更权威的东西冒充」这一类假绿，建议 E 单独列入 X1 标准**：
AC 8.4 明令「不得用 fixture 冒充」，而这次的冒充候选**不是 fixture，是真实引擎** ——
x2t 返回 rc=0 且产物公式文本正确，极容易被写成「已用真实 OnlyOffice 验证求值通过」。
**fixture 冒充一眼假；真实引擎的成功看起来是最强证据，因此更危险。**
判别法：问「这个工具有没有能力回答我在问的问题」——x2t 是**转换器**不是**计算引擎**。

UNVERIFIABLE 不是只写个常量了事：有实验做反向自检，若哪天 x2t 开始重算会 `pytest.fail`
并指示把求值层升级成真判据 —— 升级必须是**有意**的决定。

**🔴 二、变异首轮只有 1/6 RED，逐条辨明后 6/6 —— 4 条无效用例 + 1 条真缺陷**

| 变异 | 首轮 | 根因 |
|---|---|---|
| M1 | GREEN | 改的是「放宽断言」，数据本就正确时放宽不改变结果 |
| M2 | GREEN | 🔴 对 zip 容器做 `bytes.replace` —— xlsx 里 XML 是 **DEFLATE 压缩**的，碰不到内容 |
| M3 | GREEN | 🔴 **真守卫缺陷**（见下） |
| M5 | WRONG-TEST | 判据其实红了，是我把 expected 写成 **fixture 名**而非测试名 |
| M6 | GREEN | 打的是「docker CLI 不存在」分支，而本机 CLI 存在（挂的是守护进程）⇒ **该行不可达** |

**M3 揭出的真守卫缺陷**：openpyxl 层原用**完整** `ref_before`（`'明细表D2-2'!AC26`）
做「不含传播前引用」检查。注入 `!AC28+0*AC26` 让前后坐标**并存**时抓不住 ——
注入的是**裸** `AC26`（无 sheet 前缀）。而「同一 sheet 的裸引用回退」恰是最可能的错法
（改写器少加一次前缀就退化成这样）。改比**坐标片段**后立刻打红。

🔴 **给 E 的第四类无效变异用例**（前三类见 §11.2 / §11.10）：
**变异打在当前环境不可达的分支上**（M6）。它与「恒等分支」是对偶 ——
前者代码可达但语义空转，后者语义有效但代码不可达，两者都判 GREEN 并被误读成守卫缺陷。
**判别法：变异前先确认那一行在本次运行里真的会被执行。**

**三、两条对全员有用的操作实测**

1. **x2t 必须走 `params.xml` 协议**。直接 `x2t in.xlsx out.bin` 报
   `Couldn't create temp folder` —— 那**不是权限问题**（实测 chown/chmod 全无效），
   是调用协议不对。误判成权限会让人一路改 owner 然后依然失败。
2. **skip 理由必须指向真实根因**。实测中途 Docker Desktop 挂了
   （`Docker Desktop is unable to start`），而原本的理由一律写成「容器里取不到 x2t」
   ⇒ 会让人去容器里找文件。已拆成「守护进程不可用」与「容器缺文件」两条独立理由。
   **skip 理由不精确 = 把人导向错误的排查方向**，与判据不精确同样有害。

**四、修掉我自己上轮的一处判据缺陷**

`test_d2_is_the_only_entry_with_propagation_demand` 硬写了 D2 是 `blocked`，
Task 29 合法翻转成 `propagated` 后本条漏改而打红 —— 那是**判据与「会随进度变的事实」耦合**。
已改为只断言「有需求 ⇒ 落在两个合法态之一」，「恰好是哪一态」由
`test_only_d2_flipped_to_propagated` 单独钉死。

**五、🔴 上报一条与我无关的既存失败（不碰他人文件）**

```
FAILED test_workbook_row_change_delete.py::TestProperty35UndeletableRows
       ::test_d2_region_is_13_to_25_not_11_to_25
  AssertionError: formula_mask ('Q13:Q24', 'S13:S24', 'AB13:AB24') 未印证数据区 13..25
```

单独跑也失败；`git status` 确认该文件我从未改过（`A` 状态、非我暂存）。
看形态是 D2 受管区边界的判据与契约 `formula_mask` 的实际取值不一致
（mask 到 24 而区间断言到 25）。**请该文件的作者复核** —— 这类「差一行」的边界
恰恰是本 spec 最该拦的东西，不宜放着。

---

## 14. E 泳道第五份报告（2026-09-05）：Task 26 收口 + Task 74 数字刷新

### 14.1 W spec Task 26 已完成，该 spec 现 **30/30 全绿**

§13.3 登记的「未完成的半项」已补齐。C 于 09-05 收口 `test_workbook_row_change_reachability.py`
（把 `blocked/pending_implementation` 改为接受 `propagated/implemented`）后基线转绿，
E 当轮补入 C 清单第 6 条：

```
X1 --run all      → 10/10 RED、覆盖面 3/3、退出码 0
三守卫基线复验     → 49 passed / 1 skipped
锚点自检          → 10/10 OK，0 MISS
.mutbak 残留      → 0
```

**C 清单六条全部落地**：M01 行首锚定组合变异 / M03 重复编号 fail-closed / M04 `~` 当就绪 /
M05 `propagate_sheets` 检测器短路 / M06 A1 owner 掩盖第二入口 / **M07 分母期望值改错**。
另加四条：M02（去掉 `\*?` ⇒ `*` 子任务读不到、分母 27→22）、M08 + M10（模板写入检测器**双向**）、
M11（元判据：词表断言的 `==` 不得降级成 `>=`）。

收尾把改名前的旧文件从索引移除（`git rm --cached mutate_workbook_row_change_upstream_gate_guards.py`，
此前状态是 `AD`：索引有、磁盘无）。两个产物现为干净 `A `。

### 14.2 Task 74 的数字已刷新，并证实 §10.4（一）的判断成立

**overlay 孤儿已自愈，E 未改 overlay 一个字节。**
09-04 我判断「那是 D 覆盖层接线的在途中间态，不在移动目标上改 overlay」，
09-05 复查证实：`wp_template_finder.py` 的 12 个顶层函数**一个没删**，D 只是**新增**了
`_find_template_file_override_first` / `_find_all_template_files_override_first` /
`_find_template_file_any_override_first` 三个（HEAD 12 → 现 15）。孤儿消失，
当时连带打红的 **9 条判据全绿**（`test_task20_writer_gate` + `test_task74_domain_adjudication`
+ `test_workpaper_writer_inventory` 合计 **81 passed / 0 failed**）。

⇒ **教训入账**：生产源重构期间 overlay 出现的「孤儿」可能只是瞬时态。
先复查再裁决；当时若按第一反应删掉那两条裁决，D 定形后还得加回来。

**但债增加了 12 条**，且两条都归 Task 74：

| 准则 | 09-04 | 现读 | 差 |
|---|---:|---:|---:|
`bypasses_unified_commit` | 261 | **264** | +3 |
`non_canonical_resolver_only` | 63 | **72** | +9 |
合计 | 646 | **658** | +12 |

归因：那三个新增函数使 `wp_template_finder` 被判为 non-canonical resolver 的行由 2 增至 5。

**Task 20 正文已被并发会话同步为 264/72/658，而 Task 74 正文仍是 261/63/646/642 —— 文档内部
不一致。** Task 74 是 E 的任务，已按现读实测更新（待迁 642 → **654** 行），并留档瞬时故障那一段。
改后三守卫复验仍 **81 passed / 0 failed** ⇒ 文档与门现算一致。

### 14.3 E 的待办（现读）

- **overlay 孤儿对齐：已无需做**（自愈，见 §14.2）。§11.6 记的 writer gate 异常捕获缺陷
  （`except WriterGateError` 捕不到生成器的 `WriterInventoryError`）现在基线已绿、可安全修，
  但它属**门的健壮性**而非判据正确性（非 fail-open，仍阻断），优先级低于下面两项。
- **等 §11.3 立项** → 扩展 kit（`replace_all` + 负对照态）后迁 task4 / task7 / task71_chaos。
- **W spec 门后各 Wave（T2/T3/T4）的变异清单** → 等 C 交付后落地（不阻塞 Task 26）。
- Word 域仍等 L1；BP-20 仍等业务方给 11 份模板的 `${token}`。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-05 | E 第五份报告：W spec Task 26 收口（10/10 RED、覆盖面 3/3、锚点 10/10），该 spec 达 **30/30**；旧名文件从索引移除。证实 09-04「不在移动目标上改 overlay」的判断成立 —— 孤儿系 D 覆盖层接线的瞬时态，已自愈且 9 条判据全绿，E 未动 overlay。同步 Task 74 过期数字（646→658、待迁 642→654，归因 D 新增三个 `*_override_first` 函数），消除与 Task 20 正文的不一致 | E |

### 11.13 追补：Task 25 在真实环境收口，并抓出一条 D2 末行的裁决冲突（C · 2026-09-05）

Docker 恢复后补跑，**W spec 我这侧全部收口**；E 的 Task 26 已到 30/30。
本节三件事：Task 25 的真实环境证据、一条真守卫缺陷、一条**给 A/B 的裁决冲突**。

**一、Task 25 从「4 条 UNVERIFIABLE」变成真实环境全绿。**

| 阶段 | 环境 | 基线 | 变异 |
|---|---|---:|---:|
| 首轮 | Docker 中途挂掉 | 6 passed / **4 skipped** | 6/6 RED（**仅覆盖前两层**） |
| 复跑 | 容器 healthy | **10 passed / 0 skipped** | **8/8 RED**（注入式，覆盖第三层与求值层） |

我这侧四个守卫合跑 **67 passed / 1 skipped**，那条 skip 是门开后按设计自动失效的反向判据。

三条真实环境结论（都在**守卫内部**复算，不再是一次性探针）：引擎 `9.4.0.129`；
`'明细表D2-2'!AC26 → AC28` 经 x2t 回转后行号逐字保留（引擎把单引号写成 `&apos;`
⇒ 只能比坐标片段）；**x2t 不重算公式** —— 往目标格写 `424242`，目标格本体变
`<v>424242</v>` 而引用它的两格仍 `<v>0</v>`。第三条现在是守卫跑出来的，
所以 AC 8.4 求值层的 UNVERIFIABLE **有可复算的实验做反向自检**，不是只信一个常量。

**二、🔴 I6 抓出一条真守卫缺陷（已修）。** 引擎版本判据原写 `detail.startswith("9.4")`，
注入伪造串 `"9.4-FAKE"` 直接通过。真实风险不是有人伪造，是**引擎升到 `9.40`**
——`"9.40".startswith("9.4")` 恒真 ⇒ 大版本换代被静默放过，届时上面三条实测结论
（identity 载体、`&apos;` 实体、不重算）**同时失效却无人知晓**。已改为解析版本号
**按点分段**比对，且版本串形态非法时直接判失败（拿不到可比对的号不得算通过）。

**三、给 E 的第五类无效变异用例 —— 「保护对象在基线里是 skip 状态」。**
前四类都是「变异本身无效」，这一类不同：**变异有效，但没有观察者**。首轮 Docker 挂掉时
第三层与求值层 4 条判据全 skip，对它们做任何变异都恒 GREEN，极易被误读成守卫缺陷
而去改本来正确的守卫。通则：**变异覆盖面 = 基线里真正 run 起来的那些测试**；基线含
skip 时结论必须标注覆盖范围，环境恢复后**补跑**，并把基线 skip 数打进报告首行。

附一条自纠：第二组变异我**首跑又写成「放宽断言」型**（`assert X` → `pass`），7/8 判 GREEN
——根因正是我自己在 §11.12 已登记过的第三类（当前状态下与正确结果同值）。
改成全注入式后立刻 7/8 RED。**同一类错跨轮复现，说明它不是笔误而是思维默认路径**，
所以值得把「有效变异必须让**被检查对象**变错，而不是让**检查**变松」写成硬规则。

**四、🔴 给 A/B：D2 受管区末行 24 与 25 两套口径并存，当前有一条测试红着。**

现读失败（**非我的文件，我从未改过**，单独跑也红）：

```
FAILED test_workbook_row_change_delete.py::TestProperty35UndeletableRows
       ::test_d2_region_is_13_to_25_not_11_to_25
  AssertionError: formula_mask ('Q13:Q24','S13:S24','AB13:AB24') 未印证数据区 13..25
```

一开始看像 mask 写漏一行，**其实是裁决冲突**。`d2.receivable_detail.json` 的
`footer_anchor.note` 明写着：

> 区间末行 25 是 BP-21 的排版占位行，合计公式覆盖它属超集 ⇒ 对受管区末行 **24** 仍然成立

即契约**有意**把受管区定为 `13..24`（12 行）；而删行判据仍是 `D2_REGION=(13,25)` +
`d2_region_rows=13`，并要求 mask 印证到 25。

源 xlsx 只读实测（`明细表D2-2`，openpyxl）为两边各留了依据，所以不能靠"看哪个顺眼"定：

- A13..A24 = 序号 `1..12`；**A25 = `……`**；A26 = `合计` ⇒ 支持「25 是占位行、末行 24」
- 但 **Q25/S25/AB25 物理上都有逐行公式**（`Q25 = =E25+O25-P25`），
  且合计是 `=SUM(Q13:Q25)` ⇒ 支持「25 在数据区内」

**风险不在这条红测试，在两套口径的缝隙**：契约认为第 25 行不受管（不该被传播），
判据认为它是数据区末行（应可删并收缩区间）。删/插第 25 行时两侧行为不一致，
正是会产出「能打开、有值、值错」的静默错数。建议 A 就 BP-21 补一句
**「占位行是否计入受管区」**的显式裁决，然后单侧对齐（改判据分母或改 mask，二选一）。
我不动这两个文件：契约属上游，delete 判据是并发会话在写。

**五、机器校验（现读）**：10 Requirement / 62 AC / 39 Property（1..39 无空洞）/
30 任务全勾 / **悬挂 AC 0 / 幽灵引用 0 / 整条零实现的 Requirement 无**。

**六、⚠ 产物入库待授权**：`test_workbook_row_change_openability.py` 仍 `??` 未跟踪。
按「spec 全绿 ≠ 产物已入库」，它一挂 CI 在干净 checkout 下必挂。等用户授权后 `git add`。

| 日期 | 变更 | 人 |
|---|---|---|
2026-09-05 | C 收口：Task 25 在真实环境从 6 passed/4 skipped 变 **10 passed/0 skipped**，补跑第二组变异 **8/8 RED**（首轮那 4 条 skip 判据的首次真实覆盖）。修真守卫缺陷 I6（`startswith("9.4")` 被 `9.4-FAKE` 骗过 ⇒ 改按点分段比对）。登记第五类无效变异用例「保护对象在基线里是 skip 状态」+ 通则「变异覆盖面 = 基线里真跑起来的测试」。🔴 抓出 D2 受管区末行 **24（契约 BP-21）vs 25（删行判据）** 的裁决冲突并附源 xlsx 双向证据，请 A 补显式裁决 | C |

---

## 15. A 泳道第三份报告（2026-09-05）：Task 76 收口 + 三条新裁决 + 两处生成器 staleness

### 15.1 本轮变更记录（A）

| 变更 | 判据 |
|---|---|
| ✅ **主 spec Task 76 由 `[-]` 转 `[x]`** | 四表全有真实行 + `--apply` 幂等重跑 `created_total=0`、四表 before == after |
| 🔴 **BP-24 裁决并落地**：两个宿主的目标底稿解析规则不同源 | 新建生产模块，两宿主 `TARGET_ORDER_SQL` `is` 同一对象；变异 4/4 RED |
| 🔴 **BP-25 裁决**：B60 的「剔除死外链」路径**不存在** | 全库 351 份 → 162 份含 externalLinks → **162/162 真引用**，死元数据 **0** |
| 🔴 **BP-23 的测试替身回归已修并升级成见证** | 变异删掉 `row_shift=` ⇒ 恰打红新增那一条，且只有那一条 |
| 主 spec Task 75 阻塞点换环（仍 `[-]`） | 供给已解除；新绑定约束是 spec 自己规定的**顺序**（Task 36 finalize 在前） |
| 主 spec Task 71 / 72 保持 `[-]`，`multi_resolver` 实测 **4** | 结构性下游于 186 entry 迁移，不是这 4 个函数的缺陷 |
| ⚠ 登记两处**生成器 staleness**，按 §6 规则 3 排在收口 | manifest 生成器与 Task 66 清册生成器现在都 FAIL，根因都是并发泳道改了前端 |

### 15.2 ✅ Task 76 收口：candidate 表 0 → 1，且是受控 attach 入口的**第一次生产调用**

Task 76 的自述验收判据点名四表都要有真实行，此前两表未兑现。现全部兑现：

| 表 | 此前 | 现在 |
|---|---|---|
| `working_paper_sync_definition_artifact` | 14 | **23** |
| `working_paper_sync_definition_bundle` | 5 | **9** |
| `working_paper_representation_upgrade_candidate` | **0** | **1**（`state=ready`） |
| `working_paper_content_representation` | 1（opaque lane） | **4**（其中 3 行是 projection 链的 G7 / H1 / D2） |

解锁靠**补上一个从来没有生产入口的环节**。Task 17 的 `ExcelInstrumentationUpgrader`
一直只被测试调用 —— 而 `ProjectionDefinitionProvisioner._settle_representation_stage`
在「已有 current representation 但绑的不是本次 approved bundle」时返回 `blocked`，理由原文就写着
「②已有 representation 时，纯 definitions 升级须先由 Task 17 的 instrumentation upgrader
登记 non-current candidate」。两边都在位、中间那一步没有宿主 ⇒ 典型的假绿第①源。

新建 **`backend/scripts/fix/fix_excel_instrumentation_upgrade_candidate.py`**（十阶段 + 7 格封闭
结算词表）。H1 实测：candidate `cfcb99ab…` 以 `awaiting_contract`、三个 target 全 `None` 登记，
随后 `fix_task76_provision_projection_definitions.py --apply` 经
`CandidateDefinitionAttachService.attach()` 绑上 approved contract `064b11a66d37` +
bundle `b2284d1fd77d`，`awaiting_contract → ready`；append-only 审计在位
（candidate_event seq 1 `contract_bundle_attached`）。四个 entry 的 entry pointer /
`representation_generation` / representation 行数 / `content_revision` **逐值不变**，
`finalized_*` 仍 `NULL`（finalize 属 Task 36，本宿主不越线）。

### 15.3 落地时纠正的三处判断（都不是「照着 tasks.md 抄」能发现的）

1. **不能拿当前已发布 artifact 再 instrument 一次**：`instrument_workbook_bytes` 自己就拒
   （「源 artifact 已含 instrumentation 部件 —— 重复注入会产生第二套 identity；存量
   instrumented artifact 应走 definition 升级」）⇒ candidate 字节 = **权威模板按新 spec 重新
   instrument**；`rollback_source_sha256` 取**当前已发布 artifact** 的 digest。两个不同输入，
   upgrader 的 API 本就分开，混用会把回滚 digest 写成假的。
2. **不能调 `upgrader.publish_definitions()`**：它内部用非幂等 `DefinitionPublisher`，对已
   approved 的同 digest 直接撞 `uq_wpsda_kind_sha256`（实测 template `ef2e9042958a`）。
   更要紧的是**正确性** —— candidate 声明的 template/instrumentation 必须**正是目标 bundle 的
   typed slot 引用的那两条**，否则 finalize 会绑上一个「slot 指向 A、candidate 声明 B」的
   bundle：两边各自自洽，合起来不一致。改用
   `publish_pilot_definitions(ReusingDefinitionPublisher)` 的返回值。
3. **路径解析必须走 `artifacts.resolve_relative_path()`**：`CanonicalArtifactRepository`
   **没有** `storage_root` 属性（在 `.layout` 上），自己拼路径会绕过 `assert_within_root` 的
   越界判定。

另加一道 fail-closed 门：🔴 **store 载荷非空即拒**（`blocked_store_payload_not_empty`）。
候选字节来自模板 ⇒ 不含业务数据，对 store 已有数据的 entry 直接升级会**丢数据**；那条路必须
重投影（`materialize` + `ContentMutationService`），属 Task 36。H1 的 `H1-8-rows` 全库 0 行，
故该门今天不挡任何需要升级的 entry —— 写它是为了不让下一个人在有数据的 entry 上误用。

### 15.4 实测抓出的两处**幂等**缺陷（预演与真跑不一致那一类）

1. **我自己的新宿主**：`_pending_candidate` 原来只查 `state='awaiting_contract'`。Task 76 的
   attach 把状态推到 `ready` 之后，本宿主重跑会**再登记一个** candidate。口径改成「未 finalize
   且非 rejected」，新增结算 `candidate_already_ready`。
2. **Task 76 宿主的 `--check` 比 `--apply` 少一条分支**：
   `preview_representation_settlement` 漏掉生产 `_settle_representation_stage` 的第二条分支
   （`_candidate_bound_to` → `reused_candidate`）⇒ attach 完 `--check` 仍报 `blocked`，而
   `--apply` 会给 `reused_candidate`。**同一库状态、两个结论**，正是「预演选 A 真发选 B 而报告
   读起来完全正常」那类缺陷。已补齐，判据取
   `target_definition_bundle_id == bundle_id AND finalized_representation_id IS NULL`
   —— **不拿 `state == 'ready'` 当代理**（那会把「ready 但绑的是别的 bundle」误判成复用）。

> 沉淀给全员一条：**凡是「`--check` 预演 + `--apply` 真跑」的宿主，分支数必须逐条对应生产结算
> 函数**。少一条分支不会让任何测试变红（两边各自都自洽），只会在真实库状态走到那条分支时
> 让报告说谎。判据形态：拿生产函数的分支清单当分母，而不是拿预演函数自己的取值域。

### 15.5 🔴 BP-24（新裁决）：两个宿主的目标底稿解析规则不同源 —— 已收敛

两个宿主读**同一张**裁决表（`workpaper_sync_entry_wp_code_adjudication.json`），却各写一份全序：

| 宿主 | 原 `TARGET_ORDER_SQL` |
|---|---|
| `fix_projection_first_publication.py` | `(has_store_payload DESC), wi.wp_code, wp.created_at, wp.id` |
| `fix_task76_provision_projection_definitions.py` | `wi.wp_code, wp.created_at, wp.id` |

真库实测 4 个 pilot 里**分歧 2 个**：D2 的首版发布落在 `ef7f88e3`（project `2aa00f57`，
store 490,291 B），而 Task 76 解析到 `1e171c06`（project `df5b8403`，store 空）⇒ Task 76 的
`--check` 对**已发布**的 D2 报 `settlement=blocked` / `current_representation_id=null`；
B60 同样分歧。G7 / H1 恰好一致 —— **恰好，不是设计使然**。

危害不止读数不准：`--apply` 若照旧执行，candidate / representation 会建在**另一条底稿**上，
于是「Task 76 四表有真实行」与「首版已发布」各自成立却指向不同的 wp —— 两个判据分别在两个
异集上为真，是最难发现的一类假绿。

**修法**：新建 `backend/app/services/workpaper_sync/projection_target_resolution.py`
（裁决表读取 + 全序 + SQL 三者的唯一实现），两宿主删掉自留的那份、改成转引。
`has_store_payload DESC` 那一项的理由（否则 D2 首版发出去是**空 projection**）写在模块顶部。

**守卫改造 —— 这一段值得所有泳道看**：实现搬走后，`test_projection_first_publication.py` 里
4 条原判据**当场打红**，而它们打红的方式恰好演示了三种判据缺陷：

* `test_resolve_target_selects_at_most_one_row` 在一个只剩一行 `return` 的函数里找 `LIMIT 1`
  ⇒ **判据留在了不含实现的文件上**（改看生产模块）。
* `test_missing_provisioning_key_fails_closed` 报 `DID NOT RAISE` ⇒ monkeypatch 打在宿主的
  **转引常量**上不起作用。这条「打红」其实是**正确性的证明**（宿主真的不再自读了）⇒ patch 改打
  真源，并**反向**加一条「patch 宿主的转引常量必须**无效**」。
* `test_host_does_not_read_filename_heuristics` 的反向自检（「必须有被禁名字在原文里有、剥完
  就没有」）失效了两次：①宿主正文不再讨论幻影码 ⇒ **分母为空**，自检在空集上判定；②生产模块把
  幻影码写进了 `raise` 的**错误文案**（正当，且 strip 本就不该剥它）⇒ **误报**。
  改成**合成输入**双向钉死（剥 docstring 里的名字 / 不剥代码里的字符串），与行文无关。

新增 `test_both_hosts_share_one_order_clause_object`：判据是 **`is` 同一性**而不是字符串相等
（字符串相等允许两边各写一份恰好一样的字面量，那种形态下任何一边被改都不打红）+ 全序必含
`store.remark` + 两宿主都不得有含 `wp.created_at` 的字面量。**变异 4/4 RED**。

> 🔴 变异设计自纠：第 4 条我首版写成「给宿主加 `if _WP_CODE_ADJUDICATION.is_file()` 短路」，
> 判定 **GREEN**。原因是测试里 patch 过去的那个文件**确实存在** ⇒ 行为不变。改成「宿主自己再读
> 一份裁决表」的一行式才 RED。**变异体必须真的重现要防的那个病灶形态**，不是随便改一处。

### 15.6 🔴 BP-25（新裁决）：B60 的 `blocked_ooxml_gate` 维持不放行 —— 「剔除死外链」这条路不存在

B60 的首版发布恒落 `blocked_ooxml_gate`（`gate=external_relationships`，命中
`xl/externalLinks/_rels/externalLink1.xml.rels`）。此前提过一条看起来很省的解除路径：
**「那些外部链接是死元数据，剔掉即可」**。用生产分词器
`excel_row_shift.iter_qualified_references` 全库普查后，该路径被证伪：

| 事实 | 数 |
|---|---|
| 权威模板总数（`backend/wp_templates/**/*.xlsx`） | **351** |
| 含 `xl/externalLinks/` 部件 | **162** |
| 其中含 `_rels` | 162 |
| **真引用**外部工作簿（`[N]Sheet!A1` 形态 ≥ 1 处） | **162 / 162** |
| 死元数据（有部件、0 处引用） | **0** |
| 外部引用总处数 | **14,146**（`definedName` 10,263 + `formula` 3,883） |

B60 自己的两处外链来自两个隐藏 defined name
（`<definedName name="本循环科目" hidden="1">[1]索引!$D$15:$D$76</definedName>`），
Target 指向 `file:///D:\Documents and Settings\Administrator\桌面\to－内部控制组\…\国贸_2005_随便.xls`。

**裁决（A）**：
1. **不放宽** `allow_external_relationships=True` —— 那是削弱一条全局安全控制，且影响面是
   162/351 = **46%** 的模板库，不是 B60 一份。
2. **不剔除外链** —— 死元数据 0 份，剔掉就是静默改掉审计底稿的取数。
3B60 因此**维持 blocked**，归口为**模板编制方 remediation**（模板出厂时带着指向个人 D:/E: 盘
   工作簿的链接），**不是工程项**。这与 §7 的 BP-20 同族。
4. 这条同时**限定 M6 的可达范围**：162/351 份模板受此影响，全量双向若要求 OOXML 安全门全过，
   必须先有模板侧的链接清理，那是一项独立立项。

判据已落成可机械复算 + CI：
`backend/scripts/check/check_template_external_links.py --expect-dead-metadata 0`，
并挂进 `governance-checks.yml` 的新 job `b60-external-link-census`（只读，纯 zipfile + 生产分词器）。
判据形态是**归因型**：只断言「死元数据模板数 == 0」。哪天模板编制方真清理过链接、出现了死元数据，
本门会打红 = 提醒**重新裁决**，而不是让旧结论默默继续成立。

> 为什么普查必须用生产分词器而不是 grep `[1]`：`[` 在公式里还出现在结构化引用
> （`Table1[列名]`）和字符串字面量里。`iter_qualified_references` 与生产改写器
> `_rewrite_formula_refs` 共用同一批原语（跳字符串字面量 / 实体形态 / 左边界判定），四类误命中
> 防线自动继承。自己 grep 会同时产生假命中和漏命中（`&quot;` 实体形态）。

### 15.7 Task 75 的阻塞点换了一环：不再是「供给」，而是 spec 自己规定的**顺序**

Task 75 仍 `[-]`，但上一轮记的根因（「四个 entry 都没有 current published representation」）
**已解除**。`check_task44_oo94_excel_pilot_gate.py` 现读四个 pilot **仍全部**：

```
capability_enabled=False / adapter_registered=False / observer=available
result_distribution {'failed': 28, 'passed': 5, 'unverifiable': 140}
error_code_distribution {'pilot_not_admitted': 136, 'upstream_gap': 28, 'scenario_kind_unrepresentable': 4}
```

新的绑定约束是**顺序**，且它由 spec 自己写死：四个 provider 的
`assert_manifest_capability_enabled()` docstring 与 Tasks 46–57 的启用前置都写明
「经 **Task 36** 校验动态 identity / visible equivalence 并 finalize 其 candidate 为
published representation **之后**才允许注册 adapter / 接宿主 / 标 bidirectional」。

现有三条 published representation 走的是 P spec 的**首版发布**路径
（`ContentMutationService.commit`），**不是** Task 36 的 `ExcelEntryFinalizeGate`
⇒ 严格按 spec，今天没有任何一个 entry 可以标 `bidirectional`；而
`attach_pilot_adapters()` 的第一道门就是 `manifest_capability_enabled()`，capability 不翻则
`adapter_registered` 在结构上不可能为 True。

**H1 现在有了 `state=ready` 的 candidate，它是第一个可被 Task 36 处理的 entry。**
解锁顺序因此是：**Task 36 finalize → overlay 裁决 capability → 重生成 manifest → adapter 注册
→ Task 75 第五条 bullet 的请求路径实跑**。M1 的第二半（`capability_counts.bidirectional > 0`）
挂在这条链上，**不是**改 overlay 就能拿到。

> 🔴 顺便更正 §8 里 M1 判据的读法：M1 写的是「`content_representation` 里有 H1 / D2 的
> projection lane 记录」**且**「`capability_counts.bidirectional > 0`」。前半已达成（G7/H1/D2
> 三条），后半的前置是 Task 36 —— 所以 **M1 目前是「前半达成、后半有明确前置」而不是「3/4」**。
> 我此前用「3/4」描述过 M1，那是把 M1 当成「四个 pilot 各发一版」在数，与判据原文不符，在此更正。

### 15.8 Task 71 / 72 保持 `[-]`：`multi_resolver` 实测 4，且它结构性下游于 186 entry 迁移

`check_workpaper_writer_revision_gate.py` 现读（`rows=327 writers=272 resolvers=80 retired=3`）：

```
multi_resolver: 4 [wp_onlyoffice_router::get_sheet_onlyoffice_config,
                   wp_onlyoffice_router::get_sheet_wopi_contents,
                   wp_onlyoffice_router::get_whole_excel_grid,
                   wp_onlyoffice_router::post_sheet_onlyoffice_callback]
unadjudicated_writer: 0 | unadjudicated_resolver: 0
keeps_legacy_write_path_beside_unified_commit: 0 | after_save_still_increments_revision: 0
representation_upgrade_increments_business_revision: 0
total blocking facts: 658
```

Task 71 要求这 4 行「改为只经 published representation + approved 非空 bundle 的 substrate
取数」后计数归零。这 4 条路由服务的是**全部** xlsx 底稿，而今天有 published representation 的
只有 **3 / 186** 个 entry ⇒ 无条件切换会让其余 183 个 entry 直接取不到 substrate。
所以 `multi_resolver=0` 结构性下游于 Tasks 46–57 + 61–64 的逐 entry 迁移，
**不是这 4 个函数自身的缺陷**，今天也没有能让它归零的中间形态。E 的 M5「判据归零」同理受此约束。

### 15.9 ⚠ 两处**生成器 staleness**：都 FAIL，都排在收口，都**不是**代码缺陷（§6 规则 3）

**（一）manifest 生成器** —— `generate_workpaper_sync_manifest.py --check` 直接 FAIL：
overlay 的 `approved_source_digest` 已 stale（approved `b0fd31f1…` vs current `d9fddb64…`）。
只读量化后确认是**机械** staleness 而非语义变更：

* 挂载 **277 → 277**，新增 77 / 消失 77，落在**同一批文件、同一 component**
  ⇒ 只是 `mountId`（内容 / span 哈希）位移，**清册形态未变**（0 个新增文件、0 个消失文件）。
* 变动集中在 **42 个 host Vue**（D / F / G / H 循环 + `WorkpaperWordEditor.vue`），每个 2 或 4 条。
* 四个 pilot 宿主里**只有 `GtD2AccountsReceivable.vue`** 在内；
  `GtG7LongTermEquityMain.vue` / `GtH1FixedAssets.vue` / `GtB60Bundle.vue` 未变。

⇒ 重新 approve 是**机械动作**（形态同一性已核），但按 §6 规则 3 应在**收口时一次做完** ——
并发会话仍在改前端，早改早 stale。**在此之前任何人跑该生成器都会 FAIL，这是预期状态，不要当缺陷修。**

**（二）Task 66 清册生成器** —— `generate_task66_legacy_deletion_plan.py --check` 直接 FAIL：
「三边锁其中一边变了（磁盘 `943ea32b7b99` vs 现算 `b3bbc29234b5`）」。
`test_task66_legacy_deletion_plan.py` 的 **9 条失败是同一个根因**（清册 vs 磁盘现状漂移），
不是 9 个缺陷。逐条对应：

| 失败 | 性质 |
|---|---|
| `useG7LonTerDualMode.ts` 清册里的路径已不在磁盘上 | 清册漂移 |
| `usePilotBridgeAdapter.ts` 生产消费方清单与 import 图现算不符 | 清册漂移 |
| `createDualMode.ts` rollback target 的 plan commit 不是当前 HEAD | 清册漂移 |
| `paragraph_index_fallback:wp_onlyoffice_router.py` 登记的最后调用点 `#L1690` 找不到 needle | 行号漂移（实际已到 **L1696**，snippet 逐字仍在） |
| 「对照组前提变了：替代面已入库 —— 请同步解除 BP-66-2」 | 🔴 **语义结论，需裁决** |

**裁决（A）：现在不重跑 `--write`**，三条理由：
1. Task 66 正文逐字写着「不改生产文件，避免在 Task 70 前改变 source commit 使 evidence stale」。
   重跑会把 `plan_commit` 绑到当前 HEAD，而工作树**脏**（并发多会话在途）⇒ rollback blob 与工作树
   不符，**回滚能力反而变假** —— 比清册过期更糟。
2. 其中一条（BP-66-2 的对照组前提已变、替代面已入库）是**语义**结论，需要裁决而不是重跑；
   重跑会把它静默吸收掉。
3. 与（一）同族，应在收口时**一次**做完。

**给 D / E 的一条**：`paragraph_index_fallback` 那项的 `owner.replacement_owner_task=61` /
`deletion_owner_task=72`，行号漂移是 `wp_onlyoffice_router.py` 被编辑造成的（该文件现归 A）。
清册重跑时它会自动修正，**不要**单独手改 JSON 里的 `line`（手改会让三边锁的 digest 更不一致）。

### 15.10 🔴 给 C 的两条（请 C 确认）

**（一）`test_workbook_row_change_delete.py:187` 需 C 更新** —— 现失败：

```
formula_mask ('Q13:Q24', 'S13:S24', 'AB13:AB24') 未印证数据区 13..25
```

根因是 BP-21 **解耦了两件事**：`formula_mask`（逐行公式列的只读区域）跟的是**受管区末行**，
而数据区/DV 区间/footer `SUM` 跟的是**物理模板末行**。此前二者相邻，那只是因为末行的排版占位行
（整格 `……`）被误算成了业务行。C 的判据把 `formula_mask` 当「数据区」的代理，现在不成立了。
**我不代改 C 的文件**；建议判据改成显式读 provider 的 `TEMPLATE_PHYSICAL_LAST_ROW`
（物理事实）与 `LAST_DATA_ROW`（受管事实）两个常量，而不是从 `formula_mask` 反推。

**（二）C 的工作簿级传播**已经**接进生产 materialize** —— 这与两个既有前提矛盾，请 C 复核：

BP-23 修生产接线时顺带取证：`excel_materialize` 真的在调
`plan_workbook_row_change_for_insert`，跨 sheet 引用确实在被正确改写。D2 首版实测（插 729 行）：
不传 `row_shift` ⇒ 未管理区域漂移项 238 → 632；只传 `row_shift` 不传 `propagation` ⇒ 引用侧
**3 张 sheet** 的跨 sheet 公式仍判漂移（`'明细表D2-2'!$AI$25` → `$AI$754`）。三个声明都喂上之后
全部通过验证。

⇒ 这与 **B 的 R12.4「排除跨 sheet 联动」** 和 **C spec 的「现状逐字不动」** 两个前提都矛盾：
跨 sheet 联动不但没被排除，而且已经是 D2 首版能发出去的**必要条件**。请 C 与 B 各自复核自己
spec 里那条前提的措辞是否需要更正（这不影响已交付的代码，只影响 spec 正文的自洽性）。

### 15.11 既存失败清单（现读，**均与本轮无关**，登记以免被反复归因）

| 文件 | 失败数 | 机制 | 归属建议 |
|---|---|---|---|
| `test_wopi_working_paper_qc_review.py` | 15 | ①底稿列表接口已改**分页信封**（`{items,page,page_size,stats,…}`）而测试仍 `assert len(items)==2` ②`test_put_file_rejects_a_non_ooxml_payload`：SQLite fixture 没 provision opaque bundle ⇒ Task 65 的 opaque 门**先于** ZIP magic 触发 ③三条 `404==200` 路由 | 非 sync 域（②在 sync 域但要改的是别的文件的 fixture 完整性）。已核 `git status`：本轮未碰 `wopi_service.py` / QC / review / working_paper 路由；D 的 `router_registry/workpaper.py` 改动纯 additive ⇒ 也不是 D |
| `test_task50_h_cycle_migration.py` | 1 | 前端 `useH4Recoverable.ts#L313→L314` 行号漂移 | 位置化清册漂移，同族于 §15.9 |
| `test_task66_legacy_deletion_plan.py` | 9 | 见 §15.9（一个根因） | 收口时随清册重跑 |
| `test_workbook_row_change_delete.py` | 1 | 见 §15.10（一） | C |

本轮**唯一**由 A 引起的回归是 `test_task15_content_mutation.py` 的 2 条，已修并升级成 BP-23 的
见证（`_NOT_PASSED` 哨兵 —— **不能用 `None` 当「没传」**，因为无插行时 materialize 声明的就是
`None`，拿 None 判会让接线一旦被回退仍报绿）。现 82 passed，变异 RED。

辐射面复跑口径：按**引用关系反查**而非跑全量（`backend/tests` 根下 1522 个测试文件）。
本轮口径 = `workpaper_sync/**` 内命中改动物 token 的全部文件 + 域外只取命中
`content_mutation` / `ContentMutationService` / `MaterializeResult` 的，共 **63 个非 pg 文件**，
结果 **58 绿 / 5 红 / 收集为 0 = 0**。

### 15.12 A 名下的产物入库（§规则 7）

本轮新增的**生产**产物三件，此前均 `??` 未跟踪，已随本轮 add：

| 文件 | 用途 |
|---|---|
| `backend/app/services/workpaper_sync/excel_typography_rows.py` | BP-21 平台级门的单一真源 |
| `backend/app/services/workpaper_sync/projection_target_resolution.py` | BP-24 的目标解析单一真源 |
| `backend/scripts/fix/fix_excel_instrumentation_upgrade_candidate.py` | Task 17 upgrader 的生产宿主 |
| `backend/scripts/check/check_template_external_links.py` | BP-25 的普查判据（已挂 CI） |

> 🔴 重申 §10.2 那条：**「spec 全绿」≠「产物已入库」**。挂进 `governance-checks.yml` 的 job 在
> 干净 checkout 下必挂（文件不存在），且工作树一丢全部蒸发。每个 lane 收口必查
> `git status --porcelain -- <产物清单>`，见到 `??` 即登记待 add。

### 15.13 A 的下一步（现读，按依赖排序）

1. **Task 36 的 `ExcelEntryFinalizeGate` 跑 H1** —— 唯一能推进 M1 后半的动作。输入已就位
   （candidate `cfcb99ab…` `state=ready`，五条 finalize 前置里 approved contract / bundle /
   visible-equivalence digest / rollback digest 四条已有真值）。
2. finalize 成功后：overlay 裁决 H1 的 `capability=bidirectional` + `adapter_id` →
   重生成 manifest（与 §15.9（一）的 digest 重新 approve **合并成一次**）→ adapter 注册 →
   Task 75 第五条 bullet 的请求路径实跑（render-config / materialize / extract 各一次）。
3. 收口时**一次性**重跑两个生成器（manifest + Task 66 清册），并同时裁决 BP-66-2。
   前提是并发泳道停止改前端 —— 请 C / D / E 在自己收口后回报一声。
4. D2 / G7 走同一条链（它们的 bundle 已是最新，无需 candidate；直接等 Task 36 对首版
   representation 的处置口径）。B60 维持 blocked（§15.6）。

**给全员的一条**：在 1 完成之前，`capability_counts.bidirectional` 恒为 0、四个 pilot 的
`adapter_registered` 恒为 False、Task 44 gate 恒非零退出 —— 这些都是**预期状态**，
不要当缺陷去修，也不要为了让它们变绿而放宽任何一道门。

---

## 16. 前端实测复核（2026-09-06）：双向回写在界面上 0 个 entry 可用 + BP-26 新裁决

> 本节全部结论来自**浏览器真实操作 + 真库现查**，不是代码推断。三个 pilot 各撞到一种不同的
> 阻断形态，值得各泳道都看一眼 —— 它们都不是任何人的实现缺陷，但有两条此前无人登记。

### 16.1 现读证据：双向回写确实 0 个 entry 接入

| 判据 | 现读值 |
|---|---|
| manifest `stats.capability_counts` | `{single_html: 5, single_onlyoffice: 180, unreachable: 1}` ⇒ **`bidirectional` 键不存在 = 0** |
| `legacy_fake_bidirectional_count` | **141**（与 §1 起点一致，未变） |
| `working_paper_content_representation` | **4 行**：1 opaque + G7 + H1 + D2（三条 projection lane 全部 `generation=1`） |
| `working_paper_representation_upgrade_candidate` | 1 行 `state=ready`（H1） |
| 三个已发布 pilot 的 manifest 条目 | `capability=single_onlyoffice` / `adapter_id=null` / `migration_state=legacy_fake_bidirectional` |
| 前端 `workpaperEntrySyncNotice.ts` | `SYNC_ADAPTER_REGISTERED_ENTRY_IDS = []`，UI 常显「两侧数据未互通」 |

⇒ §15.13 那句「在 Task 36 完成之前 `bidirectional` 恒为 0，这是预期状态」**经界面复核成立**。
平台在 UI 上是**诚实**的：AC 1.4 要求的「可操作原因」真的常显给审计师了
（「结构化视图的录入保存在系统数据库，在线编辑改的是项目存储里的另一份 Excel 文件」）。

🔴 **但补一条 §15.13 没点明的事实**：`ExcelEntryFinalizeGate` 在
`backend/scripts/fix/` 下**没有任何生产宿主** —— 全仓唯一提及它的 fix 脚本是
`fix_excel_instrumentation_upgrade_candidate.py` 里一句 docstring（「finalize 归 Task 36，
不在本宿主内」）。对照 Word 域早已有
`fix_task77_finalize_word_entry_representation.py`（36,688 B）在调
`WordEntryFinalizeGate.finalize_candidate`。
⇒ §15.13 第 1 步「Task 36 的 gate 跑 H1」目前**没有可跑的东西**，要先建宿主。
这与 §15.2 记录的 Task 17 upgrader「实现+测试齐备、生产零宿主」是同一形态。

### 16.2 三个 pilot 的界面可达性：三种不同的阻断

| entry | 目标底稿 | HTML 侧 | 「完整Excel」→ OO |
|---|---|---|---|
| **G7** | `354e060f`（重庆和平药房_2025） | ✅ 正常（带 `Excel A6:M199` 坐标溯源 chip） | 🔴 **打不开**：`errorCode -82 打开文件时发生错误` |
| **H1** | `f663b18c`（首汽租车_2025） | 🔴 **整页 404**「项目已删除」 | 不可达 |
| **D2** | `ef7f88e3`（重庆和平药房_2025） | ✅ 正常（729 行客户明细） | ✅ 正常（11 sheet 全在，含注入的 `GT_Custom`） |

**G7 的 -82 有确切根因**（容器 `audit-onlyoffice` 日志同刻记录，非猜测）：

```
docId wpsync-290640fe72401046d176a023-g1
changesError: TypeError: Cannot read properties of undefined (reading 'tocBool')
  at cIF.Calculate (sdkjs/cell/sdk-all.js:358829)
  at DependencyGraph.calcTree ...
isDocumentLoadComplete: false
```

`cIF` 是 `IF()` 的求值类、`tocBool` 是参数转布尔 ⇒ **G7 整册里有一个 `IF()` 的参数在 OO 侧解析
为 undefined，把依赖图计算打断在文档加载完成之前**。容器 healthy（3 小时）、sdk 已加载 ⇒
**不是「OnlyOffice 不可用」，是这一份文档的内容让 OO 崩了**。定位到具体是哪个 `IF()` 需要
逐 sheet 二分，尚未做。

### 16.3 🔴 BP-26（新裁决，已落地）：目标底稿解析漏了「项目软删除」这一层

**H1 的 404 不是环境脏数据，是解析规则的缺陷。** `resolve_projection_target` 的 `WHERE`
原本只有 `wp.is_deleted = false` —— 只看底稿自己删没删，不看**所在项目**删没删。实测：

* H1 全序第一名 `f663b18c` 属项目 `df5b8403`「首汽租车_2025」，`projects.is_deleted = true`；
* 首版 published representation 已经发在它上面（09-05 落库）；
* 前端 `GET /api/workpapers/{id}/render-config` 对它返回 **404「项目已删除」**。

⇒ 「DB 里 published representation 存在」与「双向回写在界面上可用」在**两个异集**上各自为真。
与 BP-24 同族但更隐蔽：BP-24 是两个宿主选到**不同**底稿（一比就发现），这条是两个宿主选到
**同一条**、只是那条对用户不可达，**任何只查库的判据都恒绿**。

**为什么一路预演都没撞上**（这部分决定了判据必须怎么写）：

* `has_store_payload DESC` **偶然**替 D2 挡住了 —— D2 在活项目那条上有 490,291 B 载荷；
* H1 的 `H1-8-rows` 全库 0 行载荷（裁决表自己记着 `max_payload_bytes: 0`）⇒ 全序退化成
  `wi.wp_code, wp.created_at, wp.id`，而**已删除的测试项目往往创建得最早** ⇒ 稳定排第一；
* 裁决表的取证口径漏了同一层：H1 那条 `wp_index_evidence` 写「5 行未删除、5 行有 file_path」，
  统计的是 `working_paper.is_deleted`，**从未涉及所属项目**。

**已落地（只收窄候选集，不放宽任何门）**

| 文件 | 改动 |
|---|---|
| `projection_target_resolution.py` | 新增 `TARGET_VISIBILITY_SQL`（`wp` / `p` / `wi` 三层 `is_deleted`）+ SQL `JOIN projects` + 新增 `count_candidates_hidden_by_visibility()` |
| `fix_projection_first_publication.py` | 新增 `_no_target_diagnosis()`；两处「裁决码族下没有存活底稿」改为**区分**「一条都没有」与「有 N 条但全不可见」 |
| `test_projection_first_publication_pg.py` | stub DDL 补 `projects.is_deleted` / `wp_index.is_deleted`（缺列会连带打红 Property 24 落库侧，属夹具不全） |
| **新建** `test_projection_target_visibility.py` | **13 passed**（6 结构 + 5 真 PG 行为 + 2 诊断），独立 schema、一次 `asyncio.run` 采集 |

**效果是外科式的**（同一条生产 SQL、仅替换可见性子句做对照）：

```
B60  afb9201a → 不变      D2  ef7f88e3 → 不变（被 store 载荷项挡住），但 35 条候选被排除
G7   354e060f → 不变      H1  f663b18c(已删项目) → c71b7c54(重庆和平药房_2025，活)
```

**变异检验 7/7 RED**，零未命中，三个被变异文件 md5 还原自证 OK，收尾基线全绿。
清单可直接搬进 E 的正式脚本（`mutate_*.py` 按 §2 归 E，本轮用一次性 tmp 脚本，已删）：

| id | 目标 | 锚点要点 | 预期打红 |
|---|---|---|---|
| M01 | 常量摘掉 `p.is_deleted` | —— | 三层判据 + 选中可见行 + 隐藏计数 + 无目标 |
| M02 | 常量摘掉 `wi.is_deleted` | —— | 三层判据 + 隐藏计数 |
| M03 | 删 `JOIN projects` | 🔴 必须加长到含下一行 `LEFT JOIN checklist_responses`（该串在文件里出现 **2** 次） | JOIN 结构判据 |
| M04 | 隐藏计数忘 `NOT (...)` | —— | 取反判据 + 计数 + 诊断数字 |
| M05 | 宿主不再调计数函数 | —— | 死代码判据 + 诊断 |
| M06 | 诊断退回含糊文案 | —— | 诊断判据 |
| M07 | 让不可见候选**不再**按全序胜出 | 打在守卫自己的夹具上 | 分母判据（证明用例对本机制敏感） |

**变异检验当场抓出我自己两个判据缺陷**（值得进 §6 规则 4）：

1. 🔴 **子串判据被 `wp.` 里的 `p` 骗过**：`"wp.is_deleted = false"` 本身就**包含**子串
   `"p.is_deleted = false"` ⇒ 首版写 `"p.is_deleted = false" in clause` 时 M01 照样通过。
   改成按 ` AND ` **拆成合取项集合**精确比对 + 断言恰 3 项。
   通则：**SQL 别名做子串判定必踩前缀包含**，一律拆词或按边界判。
2. `_strip_docstrings` 把 docstring 整段清空 ⇒ 「类体/函数体只有 docstring」的情形变成空体，
   `ast.parse` 报 `IndentationError`，**5 条结构判据全部在「解析失败」上打红**。
   正解：首行留一个保持原缩进的空串字面量 `""`，其余行清空（行数不变，行号仍可对齐）。

**归因（外科式，非推断）**：把我改过的三个文件临时换回 **git 索引版本**（= 我编辑前的内容）后
重跑，5 条既有失败**仍全红** ⇒ 本轮引入 **0** 条。逐文件 md5 还原自证 OK。
既有 5 条分别是：`test_projection_lane_regression_gate.py` 2 条（冻结读数 2 vs 真库 4，
是 09-05 发布 H1/D2 后登记未更新）、`test_task76_wp_code_adjudication.py` 1 条
（monkeypatch 打在宿主转引常量上无效 —— **正是 §15.5 记过的形态，那处还没修**）、
`test_projection_first_publication_pg.py` 2 条（BP-21 落地后 error_code 变空，判据未同步）。

### 16.4 双向回写的核心实测（D2，唯一三项都可用的 entry）

在**受管 sheet 的受管区** `'明细表D2-2'!AC14`（受管区 `A13:AN25` 内）写入 `424242`，
Ctrl+S 触发 forcesave（config 实测 `forcesave: True` / `mode: edit`）：

| 观测点 | 保存前 | 保存后 |
|---|---:|---:|
| `working_paper.updated_at` | 2026-06-08 | **2026-09-05 17:42**（callback 真到达） |
| `working_paper.file_version` | 1 | **2** |
| `working_paper.content_revision` | 1 | **1** |
| `working_paper_content_version` | 1 | **1** |
| `working_paper_content_representation` | 1 | **1** |
| `working_paper_content_application` | 0 | **0** |
| `checklist_responses.D2-detail-rows` | 490,291 B | **490,291 B** |
| HTML 侧搜索 `424242` | —— | **搜不到** |

⇒ **OO 保存走的是 legacy 文件路径（`file_version++`），完全没有经过统一 commit
（`content_revision` 不变）**，`legacy_fake_bidirectional` 的字面含义被逐项证实。
`file_version` 与 `content_revision` 的分叉正是主 spec 的核心命题，这里是它的运行态实证。

**OO 保存产物体检**（zip 级，对照权威模板）：

| 指标 | 权威模板 | OO 保存后 |
|---|---:|---:|
| 大小 | 123,162 | 95,737 |
| zip 部件 | 48 | **31** |
| `printerSettings*.bin` | 11 | **0** |
| `xl/worksheets/_rels/` | 11 | **2** |
| `calcChain.xml` | 有 | **无** |
| sheet 数 / openpyxl 可打开 | 11 / ✅ | 11 / ✅ |

⇒ 产物**是有效 xlsx**（zip 完整、openpyxl 能开、11 sheet 与 `GT_Custom` 全在、写入的
`424242` 落盘 5 处）。部件丢失与 D 泳道在 K11 上的实测同形（§12.12：编辑保存路径丢
`printerSettings`，conversion 路径不丢），**已被 D 裁决为不还原**、改做 `diff_page_setup`
业务属性校验 ⇒ 本节不重复提议。测试写入已清除（marker 5 → 0）。

### 16.5 🔴 新登记（未修）：保存后再次打开会降级到**权威模板**，而横幅说的是「OnlyOffice 暂不可用」

保存后第二次打开 D2 的「完整Excel」：**超过 45 秒未 ready** ⇒
`GtOnlyOfficeSheet` 的 `readyTimeout` 触发 `document-ready-timeout`，前端降级。
第三次打开：**READY at 3 秒**。容器日志无任何 D2 错误 ⇒ 这是 **DocServer 对新 doc key
的一次性转换开销**（保存后 `document.key` 变了，且产物**丢了 `calcChain.xml`**，
OO 必须重建整个依赖图；D2 有 729 行明细）。

三条各自独立的缺陷，按危害排序：

1. 🔴 **降级目标是「整册 Excel **模板**」而不是当前底稿**（`GtWpRenderer.vue` 的
   `loadWholeExcelGrid`）。实测 G7 降级后显示的是 `G7 长期股权投资.xlsx` 模板里的
   G7A 程序表、D2 降级后显示 `D2-1至D2-4 …（Leap-常规程序）.xlsx` ——
   **审计师看到的是模板内容，不是自己刚编辑的数据**。横幅只写「已从整册 Excel 模板拉取
   只读网格展示」，没说「你的编辑不在这里面」。审计场景下这属于会致错的呈现。
2. **文案「OnlyOffice 暂不可用」与事实不符**：容器 healthy、sdk 已加载、DocEditor 已实例化。
   真实成因有三种且解除动作完全不同 —— ①文档让 OO 崩了（G7 的 `-82`/`tocBool`）
   ②首次转换未在阈值内完成（D2）③服务真的不可用。统一成一句会把排查引向容器与网络。
   这与 §6 规则 4 反对的「fail-open 把不同根因吞成一句」同族。
3. **45 秒阈值低于真实首次转换耗时**。要么提高阈值 + 显示「首次打开需要转换，请稍候」，
   要么先探 conversion 状态再决定是否降级。**不建议**把阈值一调了事：真正的问题是
   降级后展示的东西是错的（第 1 条）。

**建议归属**：`GtWpRenderer.vue` / `GtOnlyOfficeSheet.vue` 不在 §2 任何人的独占清单里
（D 的清单只到 `WpTemplateDetail.vue`）。请 A 裁定，或并入 §15.13 第 2 步
（adapter 注册后本来要改这两个宿主的显示逻辑）。

### 16.6 移交与待办

| # | 事项 | 状态 | 建议归属 |
|---|---|---|---|
| 1 | BP-26 代码修复 + 13 条判据 + 7/7 RED 变异 | ✅ 已完成 | —— |
| 2 | 🔴 H1 的 published representation 仍挂在**已删项目**的 `f663b18c` 上；修复后解析指向 `c71b7c54`（活） | **待裁决**：退役旧 representation / 迁 pointer / 还是恢复项目。§14.4 那句「D2/H1 都还没有 published representation ⇒ 无需退役」**已过期** | **A** |
| 3 | `ExcelEntryFinalizeGate` 缺生产宿主 | 未做（§15.13 第 1 步的前置） | **A** |
| 4 | G7 整册里让 OO 崩的那个 `IF()` | 已定位到函数级（`cIF.Calculate`/`tocBool`），未定位到具体单元格 | **A**（G7 是 §16.1 三条已发布 representation 之一） |
| 5 | 降级展示模板 + 文案失真 + 45s 阈值（§16.5 三条） | 未修 | 待 A 定（前端宿主无 owner） |
| 6 | BP-26 变异清单落成正式 `mutate_*.py` | 清单已备（§16.3 表），tmp 脚本已删 | **E** |
| 7 | §15.5 记过的「monkeypatch 打在转引常量上无效」在 `test_task76_wp_code_adjudication.py` 里**还没修** | 现读仍 `DID NOT RAISE` | **A** |

**产物入库状态**（§规则 7）：本轮改动 3 个已跟踪文件（`AM`）+ **新建 1 个测试文件仍 `??`**
（`backend/tests/workpaper_sync/test_projection_target_visibility.py`）。按「spec 全绿 ≠ 产物已入库」，
它一挂 CI 在干净 checkout 下必挂 ⇒ **待授权后 `git add`**。本轮未 commit、未跑任何生成器。

| 日期 | 变更 | 人 |
|---|---|---|
| 2026-09-06 | 前端实测复核：确认界面上 **0 个 entry 双向可用**（manifest `bidirectional` 键不存在、UI 常显「两侧数据未互通」），并在 D2 上逐项实证 OO 保存只动 `file_version`（1→2）不动 `content_revision`、HTML store 490,291 B 一字未变。🔴 新裁决 **BP-26**：目标解析漏 `projects.is_deleted` ⇒ H1 的 representation 发在前端 404 的底稿上；已修（三层可见性 + 诊断区分 + 13 判据 + 7/7 RED 变异，归因证明本轮引入 0 条失败）。另登记 G7 的 `-82`/`tocBool` 根因、`ExcelEntryFinalizeGate` 缺生产宿主、以及降级展示**模板**+文案失真+45s 阈值三条前端缺陷 | 实测复核 |

---

## 17. 真实数据验证：双向回写阻塞链已挖到底（2026-09-06）

> 承 §16。本节把「为什么 `bidirectional` 恒为 0」从「Task 36 没做」这个笼统结论，
> 挖到**四个各自独立、逐个可复现**的技术病灶，其中三个已修并有守卫，第四个是设计裁决。
> 全部结论来自真库执行 + 生产函数现调，不是代码推断。

### 17.1 ✅ BP-26 的直接成果：H1 首版发到了真实活项目上

BP-26（§16.3）修好后，`fix_projection_first_publication.py --check` 的 H1 结算从
`blocked_template_contract_drift 7/10` 变成 **`ready_to_publish` 全链 10/10**：

```
xlsx/gt-h1-fixed-assets   state=ready_to_publish
  裁决码族=['H1'] 选中=H1 wp_id=c71b7c54 store=0B      ← 活项目（重庆和平药房连锁_2025）
  stages 已执行 10/10
  projection {'value_count': 14, 'row_keys': {'disposal_check_rows': 14}}
```

🔴 **14 而不是 15** —— 少的正是 BP-21 剔除的 A27「……」排版占位行。
⇒ **BP-26 与 BP-21 是合起来才解锁 H1 的**：BP-21 让受管区末行干净，BP-26 让目标落在
用户看得见的底稿上。任一未修，H1 都发不出去。

`--apply` 已执行，判据取自数据不看退出码：

| 观测 | 值 |
|---|---|
| `content_representation` | 4 → **5** 行（真实活项目上现有 **3** 条：G7 / D2 / **H1 新增**） |
| H1 新记录 | rep `0897fcd1` / version `3ed6862a` / gen 1 / artifact `9a3cb615791b` |
| 前端复核 | `c71b7c54` 底稿**正常打开**（「重庆和平药房连锁有限责任公司_2025」，页签齐全，**不再 404**） |

### 17.2 🔴 BP-27（已修）：adapter 取 representation 不看可见性，多实例还不确定

四个 pilot 的 `attach_pilot_adapters()` 各写了一份**逐字相同**（md5 `2256d0b778f0`）的查询，
三个问题叠在一起：

1. `working_paper_sync_entry_state` 主键是 **`(wp_id, entry_id)`** ⇒ 同 entry 多实例合法，
   而查询只按 `entry_id` 过滤；
2. 无 `ORDER BY` 就取 `.first()` ⇒ 取哪条不确定；
3. 不看项目软删除。

H1 实测三条全中：BP-26 修好后在活项目发了新首版，而旧的已删项目那条 entry_state **仍在**
⇒ 同一 entry 两行。**这一条在生产请求路径上**（`wp_sync_router` 的
`_attach_pilot_adapters` / `_apply_durable_incoming`），比宿主脚本更要紧 ——
错了就是审计师的请求静默绑到看不见的底稿。

**已修**：收敛为 `projection_target_resolution.resolve_visible_current_representation_id()`，
复用 `TARGET_VISIBILITY_SQL`（可见性只有一处定义）+ 新增
`VISIBLE_REPRESENTATION_ORDER_SQL` 全序常量。真库验证：

```
H1  候选 2 条：976b04f6(f663b18c 首汽租车_2025 已删, created 05-31) ← 全序第一名，被正确跳过
                0897fcd1(c71b7c54 重庆和平药房连锁_2025 可见, created 06-08) ← 选中
D2 / G7  各 1 条可见 ⇒ 选中     B60  0 条 ⇒ 返回 None（adapter 不注册，fail visible）
```

🔴 **敏感性成立**：不可见那条按全序本该胜出（created 更早），所以这个用例真的在检验过滤。

### 17.3 🔴 BP-29（已修）：artifact 根两派并存，读写永远错层

**这一条是双向回写此前最硬的隐形阻塞，而它只能靠「在 capability 启用态下真跑一次」才暴露。**

做法：注入一份内存 manifest（只把 pilot 的 `capability`/`adapter_id` 改成启用态，其余逐字
不动），然后真调生产的 `attach_pilot_adapters()`。三个 pilot 的 capability 门**全部放行**，
但组装时抛：

```
ArtifactPublishError: published artifact 指针指向的文件不存在:
  storage/2aa00f57-…/.versions/c71b7c54-…/representations/…/000000001-9a3cb615791b.xlsx
```

根因：artifact 的 `relative_path` **自带 `storage/` 前缀** ⇒ 根必须是 `BACKEND_ROOT`
（= `backend/`）。全平台两派：

| 根 | 处数 | 谁 |
|---|---:|---|
| `BACKEND_ROOT` ✅ | **10** | `wp_sync_router` ×3（**生产请求路径**）· `content_mutation` · `materialize_coordinator` · `writer_migration` · Task 65/76/77 宿主 |
| `storage_root()` ❌ | 2 | 两个首版发布宿主（`fix_projection_first_publication` / `fix_excel_instrumentation_upgrade_candidate`） |

磁盘分布是决定性证据：`backend/storage/<proj>/…` 有 **142** 个 representations 目录，
双层 `backend/storage/storage/…` 只有 **4** 个 / 27 个文件，全是这三个 pilot。

**已修**：两个宿主 `storage_root()` → `BACKEND_ROOT`；27 个错位文件已迁到正确位置并删除双层
源目录（迁移前后逐 digest 核对）。⚠ 我一度把 4 个 pilot 反向改成 `storage_root()`（BP-28），
被 142:4 的分布证伪后已回退 —— **留档提醒：定「哪个根是对的」要看磁盘分布 + 生产请求路径用
哪个，不能只看报错指向谁**。

🔴 **为什么这个错根能潜伏这么久**：`assert_manifest_capability_enabled()` 恒抛 ⇒
门之后的整段接线代码**从未被执行过** = 死代码。这是假绿第①源的一个新形态：
**不是「加了没人用」，而是「门恒关，门后全部代码等于没写」**。判据建议：
凡有「顺序门 + 门后长链」结构的，必须有一条在**注入放行**下真跑门后全链的判据。

### 17.4 🔴 BP-30（未修，需裁决）：`structure_hash` 一列存了两种不可比的语义

BP-29 修完后 artifact 能读到了，adapter 组装推进到最后一步，抛：

```
ObservedIdentityDriftError: 重算 structure_hash 1340ff20f9a4… 与 representation
冻结的 c573174d3906… 不一致 —— 受管结构已漂移（Requirement 6.10 / Property 28）
```

H1 是刚发布、artifact 刚写的，不可能真漂移。实证复算（三个 pilot 全部 `True`）：

```
冻结 structure_hash  == normalized_structure_hash(整份 xlsx 字节)   ✅ True
冻结 artifact_sha256 == sha256(整份文件)                            ✅ True
```

而 adapter 接线时调的是
`published_identity_observer.recompute_structure_hash(*, contract, observed_structure)`
—— 按**契约 + 受管结构坐标**算 canonical digest。

⇒ **同一列被两条路径赋予两种语义**：
* 写入方（首版发布 ← `excel_materialize` ← `ContentMutationService.commit`）：**文件字节摘要**
* 读取方（adapter 接线的观测器 / `ExcelEntryFinalizeGate`）：**受管结构坐标摘要**

这正是 §15.7 那句「首版发布路径不是 Task 36 的 gate ⇒ 今天没有 entry 可以标 bidirectional」
的**确切技术根因**（此前只说了路径不同，没说清为什么路径不同就不行）。

**两条修法，都需要裁决（不是接线能解决的）**：

| 方案 | 内容 | 代价 |
|---|---|---|
| A | 首版发布路径改用与 gate 同构的 `structure_hash` 公式 | 改 P spec 的产出语义；已发布 3 条 representation 的冻结值全部作废 |
| B | 建 Excel 域 finalize 宿主（Word 域已有 `fix_task77_…` 可参照），走 Task 36 重新发布 | 需先裁决现有 3 条 representation 如何退役 / 迁 pointer |

⚠ 顺带更正 §16.1 的一处：三个 pilot 现读均为 `already_current`
（`fix_excel_instrumentation_upgrade_candidate.py --check`：current representation 已绑定
期望 approved bundle，幂等无需升级）⇒ **Task 36 的「definitions 升级」在它们上无事可做**，
真正缺的是「用 gate 的公式重算并冻结 structure_hash」这一步。

### 17.5 平台脏数据盘点（只读，未删 —— 请裁决）

| 类别 | 数量 | 内容 |
|---|---:|---|
| 活项目（**全部保留**） | **8** | 全是真实客户名。数据最丰的是 `2aa00f57` 重庆和平药房连锁_2025（324 底稿 / 156 store 行，G7+D2+H1 三个 pilot 都在这里） |
| 合成测试项目 `proj_xxxxxxxx` | 34 | 8/1~8/14 创建、已软删 |
| 命名测试项目 | 7 | `sign-passthrough-test` / `dq-balance-test` / `formula-eval-v2-test` / `sign-migrate-test` / `B2-test` / `dedup-test` + 一条 0 底稿的「重药控股安徽_2025」重名 |
| 🔴 已软删的**真实**项目 | 1 | `df5b8403`「首汽租车_2025」（63 底稿、1 条旧 H1 representation）—— **需单独裁决**，不与测试数据同批处理 |

**物理删除的真实成本（实测，不是估算）**：那 34 个合成项目在 **173 个引用 `projects` 的子表**
里占 **2,119,556 行** —— 主要是 `tb_aux_ledger` 133 万 + `tb_ledger` 69.7 万 +
`tb_aux_balance` 8.6 万（它们是**导入测试**残留，不是空项目）。

**两个硬约束**：
1. 平台**没有**「项目彻底删除」能力 —— `DataLifecycleService.purge_project_data()` 只清四表
   账套数据（且有 `retention_until` 硬校验），不删项目/底稿；
2. 外键里 **~29 张 RESTRICT**，其中 `working_paper_sync_scope_index` 受 V151 触发器
   `wpsync_forbid_scope_index_delete` 保护（**tombstone 永不物理删除**）⇒ 涉及它的项目行
   在设计上**删不掉**。

⇒ 建议分两步、且都需要你点头：**①** 用 `purge_project_data` 清那 34 个合成项目的四表数据
（释放 211 万行，走平台自带入口、风险可控）；**②** projects 行与其余子表按拓扑序清理需要
单独写幂等脚本 + dry-run，且对受 RESTRICT 保护的项目只能维持软删。
「首汽租车_2025」单独裁决。本轮**一行都没删**。

### 17.6 本轮改动与产物

| 文件 | 改动 |
|---|---|
| `projection_target_resolution.py` | BP-26 三层可见性 + 隐藏计数（§16.3）· **BP-27** 新增 `resolve_visible_current_representation_id()` + `VISIBLE_REPRESENTATION_ORDER_SQL` |
| `pilot_h1_grouped_dynamic.py` / `pilot_d2_large_json.py` / `pilot_g7_two_level_dynamic.py` / `pilot_simple_checklist.py` | BP-27 改调共享解析器（各 1 处）· BP-29 artifact 根保持 `_BACKEND_ROOT` 并写明理由（各 2 处） |
| `fix_projection_first_publication.py` | BP-26 诊断区分（§16.3）· **BP-29** `storage_root()` → `BACKEND_ROOT` |
| `fix_excel_instrumentation_upgrade_candidate.py` | BP-29 同上 |
| `test_projection_target_visibility.py` | 13 → **18** 判据（+BP-27 三条 / +BP-29 两条含分母断言） |
| `test_projection_first_publication_pg.py` | stub DDL 补两列（§16.3） |

**验证**：判据 18 passed · 变异 **4/4 RED**（零未命中、md5 还原 OK、收尾基线全绿）·
辐射面 **840 passed / 0 failed / 0 errors**（Tasks 40~44 pilot 四件套 + 首版发布 + 定义
provisioner + lane registry + 本判据）。

**实施中被自己的判据/测试抓到三次，都已修**：
1. `session.execute(stmt, params)` 传两个位置参数 ⇒ Tasks 40~43 的 `_StubSession` 只收一个
   ⇒ **67 个用例集体 TypeError**。改用 `.bindparams()`，不去改四份测试替身；
2. `.first()` 取 Row 属性 ⇒ stub 的 result 直接返回标量 ⇒ `'UUID' object has no attribute
   'rid'`。改回 `.scalars().first()`（与被替换的原实现同形）；
3. 新函数写死 `ORDER BY wp.created_at, wp.id` ⇒ 被既有判据
   `test_check_and_apply_share_the_same_order_clause` 抓住（它禁止排序键字面量）。
   提成命名常量 + f-string 插值后自然转绿 —— **判据红得正确，不该改判据**。

| 日期 | 变更 | 人 |
|---|---|---|
| 2026-09-06 | 真实数据验证：H1 首版发到活项目 `c71b7c54`（BP-26 + BP-21 合并解锁，projection 14 值），前端复核不再 404。把「bidirectional=0」挖到四个病灶：**BP-27**（adapter 取 representation 不看可见性、多实例不确定，在生产请求路径上）与 **BP-29**（artifact 根两派并存 142:4，读写永远错层）已修 + 5 条判据 + 4/4 RED 变异 + 840 passed 回归；**BP-30**（`structure_hash` 一列存「文件字节摘要」与「受管结构坐标摘要」两种不可比语义）已定性，需裁决 A/B 两方案。另交脏数据盘点：34 个合成项目占 211 万行子表数据，平台无「项目彻底删除」能力且 ~29 张 RESTRICT（含 V151 tombstone 保护）⇒ 分两步且待裁决，本轮未删 | 实测复核 |
