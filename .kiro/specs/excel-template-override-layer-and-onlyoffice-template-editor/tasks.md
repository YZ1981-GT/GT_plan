# Implementation Plan: Excel 模板覆盖层与 OnlyOffice 模板编辑器

## Overview

25 个任务 / 7 个 Wave。核心顺序约束三条：

1. **Wave 0 三个 Open Gate 先裁决再写代码**（已全部裁决完毕）—— 落点、作用域层数、可编辑格式
   集合决定后续一切判据的形状。
2. **Task 7 的零回归判据必须先绿，才允许做 Task 8 的接线** —— 先证明改解析器不产生回归，
   再动既有解析器。
3. **Task 101必须在产生第一份覆盖文件之前完成** —— 否则覆盖层可能在备份/恢复时
   静默丢失。

## M0 复选框对齐（2026-09-04 · A · 5 泳道分工书第 0 步）

**结论：本 spec 复选框 3/27 与磁盘一致，无需改动。** 3 个 `[x]` 恰是 Wave 0 三个 Open Gate
的裁决，与本 spec 的生产交付面（N1 / N2 / N3 / M1 / M2 / M3 / T1~T5）零重叠 —— 那 11 个记号
的文件磁盘上**一个都不存在**，故 Wave 1 起全部为 `[ ]` 是对的。

对齐时另核两条，避免 D 误判：

* `backend/app/services/workpaper_sync/excel_sheet_visibility.py` **确实在磁盘**（415 行）且
  被 `backend/app/routers/wp_onlyoffice_router.py` 引用（AST import 扫描实测）。它是**前置交付**
  不是本 spec 任务 —— 本 spec 无任何任务要求重建它，Task 16 / Property 11 只"复用"。
  🔴 但它在 git 里是 `??` 未跟踪、`wp_onlyoffice_router.py` 是 `M` 未提交 ⇒ 这条"已接线"只
  活在工作树里。D 开工前建议先确认它没被并发会话回退。
* `excel_row_shift.py` 的 `_rewrite_formula_refs`（Notes 里点名要复用的第二项前置）同样在磁盘、
  同样 `??` 未跟踪，且**生产零引用**。Property 12 引用它做同源判据时不受影响（纯函数可直接调），
  但不要据此以为 S spec 已接线。

## Tasks

### 文件记号

| 记号 | 文件 | 性质 |
|---|---|---|
| N1 | `backend/app/services/wp_template_override.py` | 新增：常量 / 异常 / 解析 / 落盘 |
| N2 | `backend/migrations/V{next}__workpaper_template_override_version.sql` | 新增：版本表 + 部分唯一索引 |
| N3 | `backend/app/routers/wp_template_override_router.py` | 新增：解析 / 保存 / 回滚 / 删除 / OO 会话 |
| M1 | `backend/app/services/wp_template_finder.py` | 改：三个公开入口改薄封装 |
| M2 | `audit-platform/frontend/src/components/template-library/WpTemplateDetail.vue` | 改：编辑入口 + 来源/版本展示 |
| M3 | `backend/app/routers/wp_onlyoffice_router.py` | 改：模板编辑会话复用 `whole_workbook` |
| T1 | `backend/tests/workpaper_sync/test_template_override_resolution.py` | 新增：解析与零回归判据 |
| T2 | `backend/tests/workpaper_sync/test_template_override_write_gates.py` | 新增：越界 / 扩展名 / 版本 / 并发判据 |
| T3 | `backend/tests/workpaper_sync/test_template_override_lossless.py` | 新增：无损判据（跨 sheet / 部件 / 样式） |
| T4 | `audit-platform/frontend/src/components/template-library/__tests__/wpTemplateDetailOverride.spec.ts` | 新增：UI 形态判据 |
| T5 | `backend/scripts/diagnose/mutate_template_override_guards.py` | 新增：变异检验脚本 |

---

### Wave 0 —— 前置裁决（不写生产代码）

- [x] 1. 裁决 Open Gate 1：`OVERRIDE_ROOT` 的落点
  - 已裁决 `backend/storage/template_overrides/`。实测：`.gitignore` 含 `backend/storage/`；
    `verify_backup.py` 的 `backup_storage.rglob("*")` 是 `storage/` 全递归 ⇒ 新子目录自动覆盖；
    该目录已有 `projects`/`workpapers`/`attachments` 等具名子目录，布局惯例一致
  - 🔴 **残留**：只证明了备份**校验**脚本覆盖；执行备份的脚本尚未确认 → 见 Task 101
  - **Validates: Requirements 1.5**

- [x] 101. 收尾 Gate 1 残留：确认执行备份的脚本也覆盖 `storage/` 全递归
  - 判据：找到真正执行备份的脚本，证明其扫描面含 `OVERRIDE_ROOT`；不含则改扫描面
  - 不得留「覆盖层在恢复时静默丢失」
  - 🔴 **实测确认扫描面不含，已改**。执行备份的脚本 = `backend/scripts/ops/backup.py`。
    缺口根因是 **cwd 口径不一致**：两个脚本都相对 cwd 解析 `./storage`，而
    * 后端进程 cwd = `backend/`（`start-dev.bat`：`cd /d "%BACKEND_DIR%"`），
      `STORAGE_ROOT=./storage` ⇒ 运行时产物落 `backend/storage/`（实测 **2308 文件 /
      655 子目录**，最近写入当天）
    * 备份脚本用法是从仓库根跑 ⇒ 同一个 `./storage` 指向 `<repo>/storage`
      （实测 **281 文件**，最近写入 2026-09-01，早年从仓库根启动后端留下的陈旧目录）
    ⇒ 备份每天"成功"，备的却是错的目录，**差 2027 个文件**；`OVERRIDE_ROOT` 落在扫描面外
  - 🔴 同时修掉三处 fail-open，它们是这个缺口能长期无声存在的原因：
    ① `backup.py` 根不存在 → `skipped`，而 `main()` 只把 `failed` 计入失败 ⇒ 什么都没备也退出码 0
    ② `verify_backup.py` 备份里没有 storage 目录 → `passed: True`
    ③ 同上，`backup_files` 为空 → `passed: True`（空集恒真）
  - 产物：新增 `backend/scripts/_storage_roots.py`（根解析单一真源，两脚本共用；
    刻意不放 `backend/app/**` 以免触发生成器 freshness 判据连带打红）
  - 判据落在 `test_template_override_write_gates.py::TestTask101BackupCoversOverrideRoot`
    6 条：真调用根解析 + **反向自检**（旧口径必须**不**覆盖，否则该判据已恒真）+
    AST 可达性（`backup_storage` 真调用 `backup_scan_roots`，防 additive 死代码）+
    防回退（两脚本顶层不得再出现相对 cwd 的 `STORAGE_DIR`）+ 非 fail-open
  - ⚠ 副作用需运维知悉：备份体积从 281 → 2589 文件。这修复的缺陷**大于本 spec 范围**
    （2027 个运行时文件此前从未被备份，与覆盖层无关），已在分工书 §9 报 A
  - **Validates: Requirements 1.5**

- [x] 2. 裁决 Open Gate 2：作用域载体
  - 已裁决**复用 `TemplateLevel` 三档**（`firm_default` / `group_custom` / `project`），
    解析优先级四层 `project > group_custom > firm_default > authoritative`
  - 实测：`backend/app/models/**` 无 `Firm`/`Org`/`Organization`/`Tenant`/`Institution` 任何类，
    但 `template_library_models.TemplateLevel` 已定义这三档 ⇒ 原设计自造 `OverrideScope` 是重复造词
  - **Validates: Requirements 2.4**

- [x] 3. 裁决 Open Gate 3：xlsm 的宏
  - 已裁决**排除 xlsm**，可编辑集合 = xlsx 349 份
  - 实测：索引声明的 17 份 xlsm **17/17 全含 `vbaProject.bin`**；`audit-onlyoffice` 容器 healthy
    但 OO 往返保留性未取证 ⇒ 保守排除，与 docx 同等置灰
  - **Validates: Requirements 5.2**

- [-] 103. （可选，放开 xlsm 用）实测 OO 往返是否保留 `vbaProject.bin`
  - 真实 xlsm 上跑 OO 打开→保存，断言 `vbaProject.bin` 字节不变
  - 保留则把 xlsm 移进 `EDITABLE_FORMATS` 并把该断言固化为常驻判据；不保留则永久排除
  - **已取到一半证据，另一半有结构性障碍 ⇒ 维持保守排除，标 `[-]` 而不是 `[x]`。**
  - ✅ **已取证（conversion 路径）**：真跑 OO 的 `ConvertService.ashx` 做 xlsm → xlsm 往返，
    样本 `B30-2B 组成部分重要性水平（2021年6月）.xlsm`（51.1 KB）实测
    **`vbaProject.bin` 逐字节保留**（52224 字节、sha256 相同）、**zip 部件数 30 → 30 不变**、
    **printerSettings 2 → 2 保留**。已固化为常驻判据
    `TestTask103XlsmVbaSurvivesConversion`（3 条，OO 不可达时 skip）
  - ✅ **已取证（编辑保存路径，Playwright 真开编辑器）**：用 Playwright 打开真实 DocEditor、
    在空白格输入内容、触发 forcesave（`error=0`）、收到 `status=6` callback 落盘。
    样本同上 xlsm 实测 **`vbaProject.bin` 52224 字节、sha `abb2c4470223b7a1` 逐字节保留**。
    ⇒ 两条路径（conversion / 编辑保存）**都**不丢 VBA，"结论不能外推"这个顾虑已解除
  - 🔴 **但编辑保存路径有另一处真实损失：`printerSettings*.bin` 全丢**。K11（xlsx，7 sheet）实测：

    | 指标 | 编辑前 | 编辑保存后 | 判定 |
    |---|---:|---:|---|
    | zip 部件 | 37 | 27 | 少 10 |
    | `printerSettings*.bin` | 7 | **0** | 🔴 全丢 |
    | `worksheets/_rels` | 7 | 1 | 随 .bin 一起没了 |
    | `pageSetup` 元素 | 7 | **7** | ✅ 保留 |
    | 其中带 `r:id` | 7 | **0** | 指向 .bin 的引用被摘掉 |
    | 跨 sheet 引用（解字符实体后） | 291 | **291** | ✅ 无损 |
    | 非空缓存值 | 716 | 717 | +1 = 我输入的那格 |
    | 共享公式主格 | 13 | 11 | OO 把 2 组展开成独立公式（等价） |

    对照实验：**ConvertService 不丢**（部件 37→37、printerSettings 7→7、`r:id` 7→7）
    ⇒ 丢弃发生在 **DocEditor 的保存路径**，不是转换内核
  - 🔴 **裁决：不还原 printerSettings，改为实现 pageSetup 业务属性校验**（原先提的"搬回来"已否决）
    - 丢的 `.bin` 是 **DEVMODE** —— 绑定模板作者当年那台打印机的驱动私有结构。
      换台机器用 Excel 打开，本来就会 fallback 到本机默认打印机
    - **业务语义**（纸张 / 缩放 / 方向 / 页边距 / 页码起始 / 打印区域）在 OOXML 里存的是
      `<pageSetup>` 的**属性**，OO 把它们完整内联保留了 ⇒ 实测**真差异 0 项**
      （14 项差异全是 OO 显式写 `horizontalDpi`/`verticalDpi=600`，属设备能力不是业务设置）
    - 要搬回来必须给 `pageSetup` 加回 `r:id` + 重建 `worksheets/_rels` + 补 `[Content_Types]`
      —— 那是**内容级改写**，风险远大于"审计师换机器打印时用本机默认打印机"这点收益
  - ✅ **已实现（替代方案）**：`wp_template_override.diff_page_setup()` —— 保存时比对编辑前后的
    `pageSetup` 业务属性，结果挂在 `StagedOverride.page_setup_changes` 上、经
    `SaveResultOut.page_setup_changes` 回前端、callback 路径逐条记 WARNING
    - `PAGE_SETUP_MEANINGFUL_ATTRS`（11 项参与比对）vs `PAGE_SETUP_DEVICE_BOUND_ATTRS`
      （4 项刻意排除），两集合不相交由判据锁死
    - `PAGE_SETUP_DEFAULTS` 做默认值归一（**省略 ↔ 显式默认值等价**），
      `orientation` 的 `default ↔ portrait` 等价 —— 不归一则每次保存都报一堆假差异
    - 比对基线是**编辑起点**（`session.source_path`）而不是权威文件，否则第二次编辑会把
      第一次的合法改动重复报一遍
    - 🔴 **它不是门**：差异非空不阻止保存（用户真改纸张方向是合法编辑）。它是**观测手段** ——
      哪天 OO 换版本连业务属性一起改写，会立刻显性化，而不是等审计师打印时才发现
    - 比对抛错时**不** fail-open 成空 tuple，而是记一条 `<比对失败>` 变化 + WARNING 日志，
      否则"没比对"和"通过"长得一样
  - **判据**：`TestProperty20*` 四类共 **16 passed**（含真跑 OO ConvertService 的等价判据，
    OO 不可达时 skip；带两条分母断言防"缓存回吐原字节"式假绿）。
    **变异检验 10/10 全 RED**（删接线调用 / 基线换成权威文件 / 异常 fail-open /
    dpi 混进业务集合 / 去掉默认值归一 / 去掉 orientation 等价 / diff 恒返回空 /
    sheet 缺失不报 / router 不暴露字段 / `as_dict` 键漂移），每条命中的都是预期那条测试
  - ⇒ `EDITABLE_FORMATS` **仍保持** `frozenset({".xlsx"})`。VBA 保留性两条路径都已证实，
    但放开 xlsm 是**产品口径决策**（宏模板要不要让人在浏览器里改）而非技术阻塞，
    留给业务方裁决。判据 `test_xlsm_is_still_excluded_from_editable_formats` 锁住现状
    —— 不是多余：上面两条一绿，下一个读它的人很容易顺手把 xlsm 加进去
  - **本任务维持 `[-]`**：证据已齐（两条路径 + pageSetup 结论都落成常驻判据），
    但 `EDITABLE_FORMATS` 未改 ⇒ 任务标题说的"放开 xlsm 用"没有发生
  - 顺带锁死 Gate 3 的分母：`test_all_xlsm_templates_still_carry_vba` 断言 **17/17 全含宏**
    —— 那是"保守排除"的全部理由，若某天有一份不含宏了，排除口径就该复核
  - **Validates: Requirements 5.2**

---

### Wave 1 —— 覆盖层骨架（零 DB、零写入）

- [x] 4. N1：常量、异常、根目录互斥断言
  - `OVERRIDE_ROOT` 单一常量；6 个异常类，`error_code` 两两不同
  - `assert_override_root_disjoint_from_authoritative()`：祖先 / 后代 / 相等三种情形均抛
  - import 期执行该断言（照 `projection_lane_registry` 的范式，让接线错误在 import 就暴露）
  - 已交付 `backend/app/services/wp_template_override.py`：`AUTHORITATIVE_ROOT` /
    `OVERRIDE_ROOT` / `EDITABLE_FORMATS`（仅 `.xlsx`，Gate 3）/ `SCOPE_PRIORITY`
    （复用 `TemplateLevel` 三档，Gate 2）+ 6 个异常 + 两条 import 期断言
  - 刻意**不** import `wp_template_finder`（Wave 2 起 finder 反向调用本模块会成环），
    `AUTHORITATIVE_ROOT` 自行推导，两处一致性由判据锁死而非约定
  - `_is_within` 用 `relative_to` 而非字符串前缀 —— `wp_templates_backup` 不是
    `wp_templates` 的后代，前缀比较会误判（已有正例判据）
  - **Validates: Requirements 1.5**

- [x] 5. T2：Property 5 判据 + 变异
  - 三种情形各一例；互不包含时通过
  - 变异：把 `OVERRIDE_ROOT` 改成 `TEMPLATES_DIR / "x"` 必须打红
  - 已交付 `test_template_override_write_gates.py`，**20 passed**。除三种失守情形外另有：
    互不包含通过（证明不是恒抛）、字符串前缀 lookalike 通过、**import 期行为判据**
    （把常量改坏后 `exec_module` 必抛，比"顶层有一行调用"的 AST 判据更硬）、
    error_code 6 个两两不同、`AUTHORITATIVE_ROOT == finder.TEMPLATES_DIR`、
    索引 476 条 + 格式分布 `xlsx349/docx107/xlsm17/doc2/xls1` 双向锁死
  - 变异检验 **RED**（三信号全命中：异常类名 / 来源模块 / "落在权威模板目录"分支），
    还原后 md5 一致且回绿
  - 🔴 变异过程踩到两个**脚本自身**的坑，已沉淀为后续变异脚本的必守项：
    ① 预期信号写 `error_code` 会误判 WRONG-TEST —— pytest traceback 打印的是**异常类名**，
      error_code 是类属性不出现在输出里
    ② 变异脚本必须 `read_bytes`/`write_bytes` —— 本仓库 `core.autocrlf=true`，
      `write_text` 会把 LF 写成 CRLF，还原后 md5 必然不一致，报假 FATAL
    ③ import 期断言的变异形态是**收集期 ERROR**（炸整个模块）而非单条 FAILED，
      这不算 WRONG-TEST；为排除偶发错误改用"三信号同时命中"判 RED
  - ⚠ 正式的 `mutate_template_override_guards.py`（Task 23 / T5）归 **E**
    （分工书 §2：E 独占 `backend/scripts/diagnose/mutate_*.py`），本轮用一次性 tmp 脚本
    完成检验，收口时删除；与 §2 的冲突已在 §9 报 A
  - **Validates: Requirements 1.5**

---

### Wave 2 —— 只读解析 + 零回归证明

- [x] 6. N1：`TemplateResolution` 与 `resolve_template` / `resolve_all_templates`
  - 覆盖层为空时行为等价于现有 finder；带 `origin` / `version_id` / `sha256`
  - 解析判据是「该作用域有当前版本且其文件存在」，不是「文件存在」
  - 🔴 **实现裁决（design.md 的空白，落地时必须定）："当前版本"由文件系统布局承载，
    解析路径不查 DB。** 理由：design 的 `resolve_template` 签名是同步的、无 session，
    而 finder 三个公开入口也是同步的（被 `wp_template_init_service` 等同步调用），
    Requirement 2.3 要求签名不变 ⇒ 解析**不能** await async session。布局：
    `OVERRIDE_ROOT/{scope_seg}/{wp_code}/{authoritative_stem}/current{ext}`。
    DB 版本表（Wave 3）承载元数据与并发唯一性，是审计记录；`current{ext}` 是它的
    同步可读投影。两处状态的一致性由 Wave 3 的 Property 16~19 断言，且写两侧必须收在
    同一函数里 —— **不接受**「解析读文件、写入读 DB」各读一侧的形态
  - 🔴 **必须按 `authoritative_stem` 再分一级目录**（第一版漏了，是真缺陷）：一个 wp_code
    可对多份权威文件（`D2-1至D2-4 …xlsx` 等），`find_template_file` 取主文件而
    `find_all_template_files` 取全部。只按 wp_code 定位时，覆盖主文件后两个入口会返回
    **不同**的文件。定位收敛到唯一入口 `override_dir_for()`
  - `sha256` 做成**惰性 property**（按 `(path, mtime_ns, size)` 缓存）而非 eager 字段：
    `find_template_file` 在生成底稿时被频繁调用，权威目录最大 xlsx 近 900 KB，
    eager 摘要等于给每次模板查找加一次全文件读
  - **Validates: Requirements 2.1, 2.2**

- [x] 7. T1：Property 6 零回归判据（**接线前必须先绿**）
  - 对 `_index.json` 全部 476 条逐条比对三个入口的返回值与 HEAD 版本
  - 分母断言：条数 == 476，且 xlsx 349 / docx 107 / xlsm 17 / doc 2 / xls 1
  - 已交付 `test_template_override_resolution.py`（**36 passed**，含 T2 合并跑）。判据形态是
    `git show HEAD:…wp_template_finder.py` **真把 HEAD 跑起来**逐条 `==`，不是比对人工誊抄的
    期望清单。加载后必须修正它按 `__file__` 推导的 `BACKEND_DIR`/`TEMPLATES_DIR`
    （tmp 目录会算错 ⇒ 读不到索引 ⇒ 三个入口齐返 None ⇒ 判据在空集上恒真）
  - 🔴 **补了一个覆盖面盲区**：`_index.json` 的 `wp_code` 值域只有 **180** 个，而生产大量
    使用**索引外**的码 —— 程序表码（`D4`→`D4A`）、拆出的主码（`D2-1`→`D2`）、G7 试点
    `G7L`/`G7E`、自定义 `ZZT26A`、双封函 `B2-3`、零载体 `S33-REV`。这批码走的正是回退分支
    最密集的路径（前缀回退 / A 子码严格分支 / 范围式命名回退），只测索引内等于放过它们。
    现按机械规则派生 **187** 个一并比对（不手工誊抄清单，清单会随索引过时），
    并加反向自检「这批码在 HEAD 下必须有一部分真能解析出模板」防 `None == None` 恒真
  - 接线后复跑：索引内 180 + 索引外 187 = **367 个 wp_code × 3 个入口，差异 0**
  - **Validates: Requirements 2.3**

- [x] 8. M1：三个公开入口改薄封装
  - `find_template_file` / `find_all_template_files` / `find_template_file_any` 内部走 `resolve_template`
  - 新增带来源的入口供新代码用；旧入口签名与返回类型不变
  - 🔴 **不能把实现改名成 `*_unresolved`** —— 试过，被一条既有判据打红：
    `test_task58_word_canonical_resolver.py::test_finder_no_longer_uses_a_only_regex_for_sub_code_decision`
    用 **AST** 断言「名为 `find_template_file_any` 的 FunctionDef 里，对
    `_resolve_most_specific_docx` 的调用早于 `_LEGACY_A_ONLY_SUB_CODE_RE.match`」，锁的是
    「统一 Word resolver 没成死代码」。改名后该名字下的函数体只剩三行薄封装 ⇒ 必红。
    ⇒ 改用**模块末尾别名 + 重绑定**：`def` 保留原名原实现（AST 判据绿），末尾把
    `*_unresolved` 指向原函数、把公开名重绑定为 `functools.wraps` 包的 wrapper
    （`__wrapped__` 让 `inspect.signature` 仍报 `(wp_code)`，Requirement 2.3 也不破）
  - 旧签名只解析到 `firm_default` 层（拿不到 project/group id），这是**有意的**：
    加参数会波及全库约 50 个调用点。项目级覆盖走
    `wp_template_override.resolve_template(wp_code, project_id=…, group_id=…)`
  - 🔴 **补了零回归的反向自检**（`TestOverrideLayerIsActuallyWired`）：若重绑定失效，
    三个入口仍是纯权威实现 ⇒ Property 6 照样全绿而覆盖层是**死代码**（假绿第①源）。
    故加两条正向判据：结构上 `__wrapped__` 在位，行为上种一份 firm 级覆盖后公开入口
    必须返回它、而 `*_unresolved` 必须仍返回权威文件
  - 已确认**不给 E 的 Task 74 增红**：`generate_workpaper_writer_inventory._RESOLVER_SYMBOLS`
    是精确集合（`leaf in` 判断），含 `find_template_file` / `find_template_file_any`
    但不含 `*_unresolved`；且公开名的 `def` 未改名，原有 resolver_call 记录形态不变
  - **Validates: Requirements 2.1, 2.3**

- [x] 9. T1：Property 7 / 8 多层优先级与逐层回落
  - 三层同时命中取项目级；逐层撤掉依次回落，每步断言 `origin` 与 `sha256`
  - 四层同时命中取 `project`；逐层撤掉断言 `override:project` → `override:group_custom`
    → `override:firm_default` → `authoritative`，每步比对 `origin` 与现算 `sha256`
  - 另加：缺 scope id 时该层不参与（不会拿到别的项目的覆盖）、跨扩展名 current 不被解析
  - 🔴 **测试 helper 的布局必须与 `override_dir_for` 一致**：第一版 `_plant_current` 少了
    `authoritative.stem` 一级，于是解析恒不命中，「应回落」类判据**全部假绿**（两条本该
    红的先红了才暴露出来）。现在 helper 里写明这条，并给每个"不该命中"的用例配一条
    "同条件下换成该命中的形态必须命中"的对照，证明不命中是门控造成的而非路径根本没查
  - **Validates: Requirements 2.4, 2.5**

---

### Wave 3 —— 写入门与版本化

- [x] 10. N2：迁移 —— 版本表 + 部分唯一索引
  - 表见 design.md；`is_current` 唯一性用**部分唯一索引**承载
  - `IF NOT EXISTS` 幂等；配 `R{n}__` 回滚脚本
  - 已交付 `V154__workpaper_template_override_version.sql` + `R154__rollback_…sql`
    （实扫迁移号：153 个 V 文件、最大 V153、schema_version 已应用 153 ⇒ V154 无撞号）
  - 🔴 表加了一列 `authoritative_stem`：覆盖粒度是 **(wp_code, 权威文件 stem)** 而非 wp_code
    （理由同 Task 6），否则 D2 这类多文件底稿覆盖主文件后两个入口返回不同文件
  - 部分唯一索引用 `COALESCE(project_id/group_id, 全零UUID)` 归一后建**一条**：
    PG 唯一索引对 NULL **不去重**，直接放 id 列会让 `firm_default` 下可插任意多条
    `is_current=true`。**已实测**：干跑里「firm_default 第二条 is_current=true」被拒
  - 另加三个触发器：不可变列（除 `is_current`）、**禁止物理删除**（Requirement 4.3
    的 DB 层兜底）、父版本不得跨作用域
  - 干跑验证（事务内执行 → 35 项断言 → ROLLBACK → 复核表不存在）：**35 项全通过、零残留**。
    抓到一个真缺陷：`file_relpath NOT LIKE '%\%'` 里 `\` 是 PG 的 **LIKE 转义符**，
    `\%` 被解释成「字面量 %」⇒ 反斜杠原样放行。改用 `position('\' in …) = 0`
  - 已通过 `MigrationRunner.run_pending()` 正规路径应用（`executed=['154']`、
    7 索引、3 触发器、schema_version → 154）。应用前实测「未应用集合恰是 V154」，
    避免连带应用他人在途迁移
  - **Validates: Requirements 4.1, 4.4**

- [x] 11. N1：`stage_override` 与两道门
  - 越界门（Property 1）：`..` 穿越 / 绝对路径 / 符号链接三形态
  - 扩展名门（Property 9）
  - 越界门收敛到 `assert_target_within_override_root()`：`resolve()` 同时解掉 `..` 与
    符号链接，故三形态由**同一条**检查覆盖；**返回 resolve 后的路径**且落盘必须用返回值
    （用原始路径写盘则这道门只是装饰，已有判据断言返回值）
  - 纵深防御 `_assert_no_path_injection`：`wp_code` / stem 必须是**名字**不是路径。
    含 `/` 的 wp_code 虽 resolve 后仍在根内（不越界），却会造出目录层级让两个 wp_code
    写到同一位置；且 `base / "/abs"` 在 pathlib 里会**丢弃 base**，必须在拼路径前拒绝
  - 🔴 **扩展名门第一版是死代码**：`extension = authoritative.suffix` 再拿它和
    `authoritative` 比 ⇒ 恒真。真实场景是**上传替换**时用户传了别的格式，故新增
    `source_extension` 参数（来自上传文件名）。门要有意义，被比较的两侧必须来自不同来源
  - 格式门 `require_editable_format` 只作用于浏览器内编辑；上传替换必须放行 docx/xlsm
    （Requirement 7.2 覆盖面表：476/476 可覆盖）。两条路径共用 `stage_override` = AC 5.5
  - 落盘拆成 `stage_override`（写 `versions/`）+ `activate_staged_override`（切 current）
    两步，因为「落盘」与「生效」必须能分开失败 —— 见下条写入顺序裁决
  - 🔴 **写入顺序裁决（两处状态不可能原子，必须定序）**：**先提交 DB，再切 current**。
    DB 成功而 current 失败 ⇒ 有台账未生效，可被一致性检查**幂等补切**；反序失败 ⇒
    **已生效无台账**，审计师看到改过的模板而系统说不出来源，且无法自动修。
    宁可「改了但没生效」，不要「生效了但说不出来源」
  - **Validates: Requirements 1.1, 2.6**

- [x] 12. T2：Property 1 / 2 / 9 判据
  - Property 2 是 AST 扫描：写入目标位不出现 `TEMPLATES_DIR`
  - 扫四类写入形态：方法调用的接收者（`write_bytes`/`mkdir`/`unlink`…）、
    `os.replace` 第二参、`shutil.copy*`/`move` 第二参、`open(..., 'w')` 第一参
  - 🔴 配**反向自检**（喂一个合成违规，扫描器必须抓到 1 条）+ **分母断言**
    （本模块至少 4 处写入调用），否则「0 offenders」可能只是扫描器什么都没看
  - Property 9 含大小写用例（`.XLSX` 覆盖 `.xlsx` 放行但落盘用权威写法，
    否则文件系统上会出现两个 current）
  - 另加 stage/activate 分离判据：stage 后解析仍是 `authoritative`、activate 后才生效且
    **幂等**（一致性检查要能安全补切）、deactivate 后回落且 `versions/` 历史保留、
    无 `.staging` 残留
  - **Validates: Requirements 1.1, 1.2, 2.6**

- [x] 13. N1 + N3：版本写入 / 回滚 / 删除
  - 保存产生新版本并接 `parent_version_id`；回滚只改 `is_current` 不删行；删除后回落
  - 交付 `record_override_version` / `promote_override_version` / `clear_current_override`
    / `list_override_versions`（async 接 session，**不 import 任何 DB 引擎** ⇒ 解析层仍零 DB）
  - 🔴 **`IS NOT DISTINCT FROM` 而不是 `=`**：`firm_default` 下 `project_id` /
    `group_id` 都是 NULL，用 `=` 时三值逻辑让 WHERE 永不匹配 ⇒ 旧当前版本摘不掉 ⇒
    紧随的 INSERT 撞部分唯一索引。已有专门判据 `test_firm_default_demote_works_despite_null_ids`
  - N3（router）留到 Wave 4 与 OO 编辑会话端点一起做，避免两次改同一文件
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.5**

- [x] 14. T2：Property 16 / 17 / 18 / 19 判据
  - Property 18 必须真并发（两个连接同时写），验证靠索引而非应用层检查
  - 全部用例事务内跑 + 结束回滚 ⇒ **零残留**（实测跑完库里 0 行）。这不是洁癖：
    V154 禁止物理删除，一旦提交测试数据就**清不掉**
  - 🔴 Property 18 第一版用 `SET LOCAL lock_timeout` + `get_raw_connection()` 直接发语句，
    整轮测试 **10 分钟超时** —— 绕过 SQLAlchemy 事务后 `SET LOCAL` 落在别的事务里、
    对本次 INSERT 无效，conn_b 无限等待。改用 `asyncio.wait_for` 在**客户端**掐断：
    conn_b 超时 = 它确实在等 conn_a = 索引在起作用。应用层「先 SELECT 再 INSERT」
    **不会**阻塞，故这条判据能区分二者
  - 配**正向对照** `test_different_key_does_not_block`：不同 key 不该阻塞。没有它，
    超时可能来自连接池耗尽/表锁/网络，「阻塞」就不再是「索引生效」的证据
  - 🔴 另抓到一个真缺陷：解析用 `glob("current.*")`，而 activate 在同目录写
    `current.version` ⇒ glob 拿到两个文件、判「多个当前版本」抛
    `OverrideCurrentVersionAmbiguousError` ⇒ **一激活就再也解析不出来**。
    修法收成单一真源 `CURRENT_VERSION_MARKER_SUFFIX` + `CURRENT_METADATA_SUFFIXES`，
    并加**双向锁死**判据（真跑一次 activate，扫目录里每个非模板文件的后缀都必须已登记）
  - 实测语义登记：**模板库里不存在的 wp_code（自定义底稿如 `ZZT26A`）不能有模板覆盖** ——
    `resolve_template` 取不到权威文件时直接返回 None 且不查覆盖层（"覆盖"必须有被覆盖对象）。
    第一版判据用随机 wp_code 当场红在这里
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [x] 15. T1：Property 3 / 4 权威目录冻结判据
  - 476 份 (size, sha256) 逐份比对 `_index.json`
  - Property 4 变异：`OVERRIDE_ROOT` 指向 `TEMPLATES_DIR` 时必须打红，且打红的正是 Property 3 那条
  - 🔴 **`_index.json` 不声明 sha256**（只有 `size_kb`），而既有 digest 基线是**按循环切片**的
    （各 `test_task5X_*_cycle_migration.py` 的 `manifest_slice`），没有全量 476 份基线。
    造一份全量基线会成为第二真源、且任何 lane 合法更新模板都要来改它 ⇒ 改用
    **编辑前后自比**：真跑一次 stage → activate → deactivate，前后 (size, sha256) 逐份比对。
    这更贴合 Property 3 的原文（"一次完整编辑保存后逐份不变"）且不受并发改模板影响
  - 🔴 **Property 4 有安全陷阱：判据本身不能造成它要防的破坏。** 字面照做
    （monkeypatch `OVERRIDE_ROOT` 指向权威目录）会让越界门认为权威目录内是"根内"，
    `stage_override` **真的把字节写进 backend/wp_templates/** —— 跑一次就污染了它要保护的
    基线。故 Property 4 落在三重上，都不真写：① 互斥断言三形态 ② 越界门拒绝权威目录路径
    ③ 变异脚本在受控环境改源码跑（Task 23，归 E）
  - ⚠ **既有缺陷登记（非本 spec 造成，已报 A）**：索引 `size_kb` 与磁盘**普遍不符** ——
    451 份一致 / **23 份漂移** / 2 份缺失。22 份磁盘更小、1 份更大；最极端
    `H\H3 投资性房地产.xlsx` 索引 712.3KB 而磁盘仅 142.7KB（**-80%**）；按类别 A4/B10/G4/H5。
    xlsx 缩 80% 与 openpyxl 全量重写的已知毁坏形态吻合，但 A17-1 / B60 系列是 **docx**、
    不经 openpyxl ⇒ 不能一概而论。判据改为锁死这个**分布**（漂移变多 = 有人改了权威模板，
    变少 = 有人重算了索引），不让漂移面继续扩大
  - **Validates: Requirements 1.3, 1.4**

---

### Wave 4 —— OO 编辑会话与无损判据

- [x] 16. M3 + N3：模板编辑会话端点
  - 复用 `whole_workbook=true` 语义与 `excel_sheet_visibility` 的 zip 级可见性
  - 落盘路径不经 openpyxl / Univer / exceljs
  - 服务层（N1）：`prepare_template_edit_session` / `commit_template_edit_session` /
    `save_session_manifest` / `load_session_manifest` / `discard_template_edit_session`
  - router（N3）：`wp_template_override_router.py`，**8 个端点**已由
    `router_registry/workpaper.py` 的「模板管理」组注册（实测 8/8 挂上，既有 template
    端点未被挤掉）。⚠ 注册改动落在 `router_registry/workpaper.py`（不在 §2 任何人名下），
    是「只加不动」的两行，已报 A
  - 🔴 **会话要一份工作副本**：显示全部 sheet 需要改 `xl/workbook.xml`，而权威模板不许被写
    ⇒ 先复制到覆盖层编辑区，只对副本改可见性
  - 🔴 **保存时必须把 workbook.xml 还原成源模板的样子**：否则权威模板刻意隐藏的 sheet
    会在覆盖版本里变可见 —— 用户没要求过的语义漂移。为此在
    `excel_sheet_visibility` 新增 `plan_restore_workbook_part`（additive）：
    sheet 名序列未变时**整体换回**源 workbook.xml（`activeTab`/`firstSheet`/`definedNames`
    一并精确还原，比逐属性还原可靠）；序列变了则按**名字**匹配还原可见性（增删 sheet
    会让索引全部错位）
  - 🔴 **`TemplateEditSession` 必须同时记 `source_path` 与 `authoritative_path`**：
    已有覆盖时解析结果是 `current.xlsx`，拿它的 stem 定位会让第二次保存落到
    `{wp_code}/current/` 而不是 `{wp_code}/{权威stem}/` —— 目录对不上，解析再也找不到。
    专门有一条判据 `test_second_edit_round_still_uses_authoritative_stem` 覆盖这个场景
  - 🔴 **会话元数据落盘、不用进程内字典**：OO 的 callback 是另一个请求，多 worker 下会落到
    别的进程，进程内状态随机丢失 ⇒ 表现为"保存时报会话不存在"。判据用「重新从磁盘加载」
    证明它不依赖内存，并断言会话不存在时**抛**而不是当作新会话
  - 🔴 **口径修正：覆盖层必须跟 `find_template_file_any` 同口径，不是 `find_template_file`。**
    后者只认 xlsx/xlsm，而它对 `B2-1` 这类 docx 子码会回退到父级 XLSX ⇒ docx 模板永远
    解析成 xlsx、格式门永远放行、"docx 置灰"根本测不出来（第一版判据就因此永久 skip）。
    更要紧的是 `_any` 才是下游 `wp_template_init_service` 真正用的入口 ——
    口径不一致会让「覆盖的那份」和「生成底稿用的那份」是两个文件
  - 机对机端点（`contents` / `callback`）**不声明** `get_current_user` / `require_role`
    （声明了会恒 401，且失败点在 OO 内部很难查）；管理端点必须有 `require_role`。
    两侧都有判据落在**函数签名的真实依赖声明**上，不是注释
  - **Validates: Requirements 3.1, 3.6**

- [x] 17. T3：Property 10 / 11 无损判据（会话层）
  - config 不含 `actionLink`、全部 sheet 可见
  - 会话建立前后除 `xl/workbook.xml` 外部件字节相同（复用 `_assert_only_workbook_part_changed`）
  - 已交付 `test_template_override_lossless.py`。Property 11 直接用
    `excel_sheet_visibility.assert_only_workbook_part_changed`（为此给那个私有函数加了公开
    别名，避免跨模块用私有符号，也避免各写一份逐部件比对）
  - Property 10 的 config 半边用**真调路由处理函数**（不经 HTTP 栈也不经依赖注入）：
    `require_role([...])` 每次调用返回新闭包，拿不到可作 `dependency_overrides` key 的稳定
    对象；直接调函数反而更硬 —— 测的是真实返回值
  - 另加：权威文件 sha256 不因建会话而变、工作副本在覆盖层内、session_id 路径注入被拒、
    discard 幂等
  - **Validates: Requirements 3.1, 3.2**

- [x] 18. T3：Property 12 / 13 / 14 无损判据（保存层）
  - 「打开 → 不改 → 保存」后跨 sheet 引用去重集合逐项相同
  - 共享公式主格 / 非空缓存值 / printerSettings / worksheets/_rels / 样式索引五项不变
  - 模板选取须断言其跨 sheet 引用数 > 0
  - 🔴 **取证模板选 K11，理由是实物证据**：它的现读指标与 design.md 记录的
    **openpyxl 全量重写毁坏样本逐项吻合** —— 它就是那次毁坏的原始样本。
    zip 部件 **37**（毁坏后 19）· 共享公式主格 **13**（毁坏后 0）· 非空缓存值 **716**
    （毁坏后 28）· printerSettings **7**（毁坏后 0）· worksheets/_rels **7**（毁坏后 1）·
    跨 sheet 引用去重 **201** · sheet **7** · 样式索引 **1742**。八项全部锁成基线 ⇒
    若本 spec 的落盘路径重新引入那类毁坏，数字会立刻掉下来
  - 空保存后实测：跨 sheet 引用 201 个逐项相同、五项指标逐项不变、**样式索引序列**逐项相同、
    `workbook.xml` 内容回到源模板、除 `workbook.xml` 外**逐部件字节相同**
    （不断言整文件 sha256 —— workbook.xml 的压缩字节可能因重新 deflate 而不同）
  - **Validates: Requirements 3.3, 3.4, 3.5**

- [x] 19. T3：Property 15 落盘路径纯净性（AST 可达性）
  - 从落盘入口出发做调用图可达性，不出现 openpyxl / Univer / exceljs 符号
  - 判据是可达性不是字符串存在
  - 🔴 **必须先剥 docstring**：本模块的 docstring 里大量叙述性提到 `openpyxl`
    （反面教材记录），不剥就会把叙述当成真实引用 ⇒ 判据恒红
    （`test_task54_l_cycle_migration.py` 已在这里栽过一次）。专门有一条判据
    `test_docstring_stripping_is_required_not_optional` 把这件事本身锁死 ——
    将来若有人去掉剥离逻辑，那条会说明为什么不能去
  - 🔴 **模块集合必须闭合**：只扫一个文件的话「0 offenders」只说明"我扫的那个干净"。
    加了 `test_write_path_reaches_only_the_two_scanned_modules`：从四个落盘入口的函数体里
    收集跨模块 import，断言只有 `excel_sheet_visibility`（已扫）与 `wp_template_finder`
    （纯文件系统路径解析，无 xlsx 读写）两个 —— 出现第三个就必须要么纳入扫描、
    要么它不该在落盘路径上
  - 另配反向自检（喂合成 openpyxl import 必须被抓）+ 分母断言（四个入口函数真实存在）
  - **Validates: Requirements 3.6, 3.7**

---

### Wave 5 —— UI 与影响面

- [x] 20. M2：`WpTemplateDetail.vue` 编辑入口 + 上传替换入口 + 来源/版本展示
  - **浏览器内编辑**入口仅 xlsx 可用（349 份，依 Wave 0 Task 3 裁决）；docx / doc / xls / xlsm
    置灰并说明原因（不是只是不可点）
  - **上传替换入口**：对置灰的 127 份提供，使它们同样能产生覆盖版本（Requirement 7.2 的覆盖面表）
  - 🔴 上传替换必须走与浏览器内编辑**同一条** `stage_override` + 版本表路径（AC 5.5），
    不得另开一条绕过越界门与扩展名门的通道 —— 判据落在调用链可达性（AST）而非「界面上有这个按钮」
  - 来源与版本号取自后端字段；彩色 tag 全中文
  - 已交付「模板来源与编辑」卡片（挂在既有基本信息卡之后，不新建平行页面）：
    当前来源彩色 tag + 覆盖版本短 id + 在线编辑（按后端 `editable_in_browser` 门控）+
    上传替换（始终可用）+ 版本历史 drawer（含回滚与删除覆盖）+ OO 整本编辑弹窗
  - 置灰原因文案由**后端**下发（`not_editable_reason`），四种格式各一句具体理由，
    并附「可用上传替换产生覆盖版本，同样进版本表、同样可回滚」
  - API 路径加在 `apiPaths/workpaper.ts` 的 `templateLibraryMgmt` 对象里而不是新开导出对象
    —— 后者要同步改 `apiPaths/index.ts` 的**三处** re-export 列表，那是并发会话都在改的文件
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [x] 21. T4：Property 20 / 21 UI 形态判据
  - 遍历 + 门控 + 嵌套三要素；前端不含据文件名推断来源的逻辑
  - 已交付 `wpTemplateDetailOverride.spec.ts`，**15 passed**。两层判据：真 mount 的渲染形态
    （四种置灰格式各一条 `it.each`，断言 disabled + **原因文本逐字命中**）+ 源码结构
    （Property 21 的「不含第二份优先级规则」只能这么验，mount 测不出来）
  - Property 21 用一个**前端不可能自己拼出来的** `origin_label`（`事务所覆盖·后端下发标记#7`）
    做 fixture —— 断言能命中它就证明来源确实来自后端
  - 🔴 踩到三个测试自身的坑，都已沉淀成注释：
    ① **整体 mock `element-plus` 会让 mount 全挂**（`el-table-column` 的作用域插槽拿不到组件
      定义，报 `Cannot destructure property 'row'`）⇒ 改用 `importOriginal` 只换
      `ElMessage`/`ElMessageBox`，其余保留真实实现并 `plugins: [ElementPlus]`
    ② **`indexOf('</template>')` 切不出 template 块**：组件里有嵌套的
      `<template #default="{ row }">`，第一个 `</template>` 在文件中段 ⇒ 后半个 template 全丢，
      「file input 存在」这类判据在被截断的字符串上恒假。改切到 `<script` 为止
    ③ **`attributes('disabled')` 判不出禁用**：element-plus 的 `el-button` 渲染成
      `disabled=""`，空字符串是 **falsy** ⇒ 四条置灰判据在按钮确实禁用时全红。
      改读真实 DOM 属性 `(el as HTMLButtonElement).disabled`
  - **Validates: Requirements 5.1, 5.2, 5.3**

- [x] 22. N3 + T1：Property 22 / 23 受影响面与不倒灌
  - 保存响应含按项目分组的既有底稿数，与直接查库现算相等
  - 抽样既有 `working_paper` 文件 sha256 不变
  - 🔴 **`working_paper` 没有 `wp_code` 列**（它在 `wp_index`），必须 JOIN。少了这个 JOIN
    结果恒空 ⇒ 报告说"不影响任何底稿"而实际影响了几百份 —— 这是最糟的形态。
    判据用**另一种写法**现算同一个数字交叉验证，并先探一个真有底稿的 wp_code
    （否则在空集上恒真）
  - 响应加 `retroactive_rewrite: false` 字段而不是只在注释里说：调用方看到
    `affected_workpapers` 有几百份时第一反应会是「系统是不是要把它们都改一遍」，
    这个字段是那个问题的答案。配 AST 判据断言 upload 端点**真的**调了统计函数
    （字段声明了却没人填 = 恒空的受影响面）
  - OO callback 的响应格式是固定的 `{"error": N}`，塞不进受影响面 ⇒ 记 log；
    统计失败只记 WARNING，不让已成功的保存变成 error
  - ⚠ 判据落在 T2（`test_template_override_write_gates.py`）而非 tasks.md 记号里的 T1 ——
    受影响面需要真库 session，T2 已有 `pg_session` fixture，不必再搭一套
  - **Validates: Requirements 6.1, 6.2, 6.3**

---

### Wave 6 —— 变异检验与收口

- [-] 23. T5：变异检验脚本
  - 逐条改一字看是否打红；四态判定（RED / GREEN / ANCHOR-MISS / WRONG-TEST）
  - 锚点跨行时注意 CRLF
  - 🔴 **阻塞原因（不是未做，是让路）**：5-lane 分工书 §2 把
    `backend/scripts/diagnose/mutate_*.py` 划给 **E**（判据治理泳道），而本 spec 的文件记号表
    把它列为 T5。按分工书规则 1「文件在别人名下就停手」，D 不建这个文件。
  - D 已完成的替代动作：Task 5 要求的那次变异检验用一次性 tmp 脚本真跑过，结论
    **RED**（三信号全命中、还原后 md5 一致、还原后回绿），脚本已按规则 8 清理。
  - **移交给 E 的三条实测必守项**（已写进分工书 §12.7）：
    ① 预期信号写 `error_code` 会误判 WRONG-TEST —— pytest traceback 打印的是**异常类名**
    ② 变异脚本必须 `read_bytes`/`write_bytes` —— `core.autocrlf=true` 下 `write_text`
      会把 LF 写成 CRLF，还原后 md5 必然不一致，报**假** FATAL
    ③ import 期断言的变异形态是**收集期 ERROR**（炸整个模块）而非单条 FAILED，
      不算 WRONG-TEST；应改用「多个预期信号同时命中」判 RED
  - 可变异的结构性判据清单（供 E 取用）：Property 5 三形态 · Property 2 的 AST 扫描器 ·
    Property 15 的 docstring 剥离 · `CURRENT_METADATA_SUFFIXES` 的双向锁死 ·
    K11 八项基线 · V154 的部分唯一索引 COALESCE
  - **Validates: Requirements 1.4**

- [x] 24. 范围边界判据
  - 断言本 spec 未改 `backend/wp_templates/` 任何字节、未引入 Univer、未回溯改写底稿、
    未改 `wp_template` / `template_library` 已有列语义
  - 已交付 7 条（`TestTask24ScopeBoundary`）：权威目录 git 层零改动（与 Property 3 的行为层
    互补 —— 行为判据管运行时，git 判据管「有人手动改了模板还提交了」）· 前端不 import
    xlsx 解析库 · V154 不 ALTER/DROP/UPDATE 既有四张表 · V154 additive-only ·
    回滚脚本存在且说明了覆盖层物理文件的处置 · `.gitignore` 已收 `backend/storage/`
  - 🔴 **判据自己先红了一次，抓到我自己犯的「字符串存在型判据」**：初版扫全文找
    `univer`，命中的是既有 CSS 类 `.gt-wpd-comp--univer`（Univer 是平台的一个
    **componentType 取值**，那是底稿渲染配色，与覆盖层无关）。改为落在
    **import 语句的模块路径**上，并配反向自检（喂合成 `@univerjs/core` + `xlsx` import
    必须被抓，而 CSS 里的同名字样必须**不**被抓）
  - 回滚脚本那条不是形式检查：`resolve_template` 的判据是**文件系统**（`current{ext}`
    是否存在），不查版本表 ⇒ 回滚 DB **不会**让解析回落权威目录，覆盖仍然生效、
    只是失去版本元数据。脚本不写清这点，运维会以为 DROP 表就撤销了覆盖
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6**

- [x] 25. 收口：产物入库核查
  - 对全部新增/改动文件跑 `git status --porcelain -- <清单>`，见 `??` 即 add
  - 挂进 CI 的 job 必须在干净 checkout 下可跑
  - 实测 **11 个 `??` + 7 个 `M`**，已按分工书 §10.2「各泳道自己 add 自己的产物清单」
    全部 `git add`（**不 commit**）。其中包括本 spec 的**三件套目录本身**（此前从未入库）
  - 🔴 **分工书 `docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md`
    也是 `??`（从未入库）—— 未 add，报 A。** 它是 A 建的共享文件，含 A/B/C/E 四方内容，
    代为提交违反规则 1 的精神。丢工作树则五个 spec 的协作基础同时蒸发
  - 两个共享文件（`router_registry/workpaper.py` 4 插 1 删 / `apiPaths/workpaper.ts`
    17 插 0 删）已逐行 diff 归因，**只有我的改动**，可安全 add
  - CI 覆盖已核实：`ci.yml` 的 `python -m pytest backend/tests/`（排除 integration/e2e）
    与 `npx vitest run` 都会收集本 spec 的四个判据文件，**无需新增 CI job**
  - ⚠ **登记一个不假绿的事实**：DB 判据（Property 16/17/18/19/22/23）在 CI 主 job 里会
    **skip**（那里没有 PostgreSQL），`-m pg_only` 那个 job 又不跑迁移、库里没有 V154 的表。
    故这组判据的实际执行环境是**有库的本地/预发布**。刻意**不**加 `pg_only` marker ——
    加了会让人以为 CI 在跑它们。本地实测：6 组全绿、跑完库里 0 行（零残留）
  - 已清理自己的 46 个 `tmp_d_*` 诊断产物（1 个被超时 pytest 进程占用，会话结束后可删）；
    根目录另有 23 个 `tmp_*` 属并发会话，未动
  - **Validates: Requirements 7.1**

---

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 0,
      "name": "前置裁决",
      "tasks": [1, 2, 3],
      "depends_on": [],
      "rationale": "三个 Open Gate 的裁决决定 OVERRIDE_ROOT 落点、作用域层数、可编辑格式集合；先裁决再写代码，避免写完再返工。已全部裁决：落点 backend/storage/template_overrides/、复用 TemplateLevel 四层优先级、可编辑集合仅 xlsx（xlsm 17/17 含宏且 OO 保留性未取证故排除）"
    },
    {
      "wave": 1,
      "name": "覆盖层骨架与裁决残留",
      "tasks": [101, 103, 4, 5],
      "depends_on": [0],
      "rationale": "常量与互斥断言零 DB 零写入，是后续一切写入门的地基；import 期断言让接线错误立刻暴露。同波并入两条裁决残留：Task 101确认执行备份的脚本覆盖 OVERRIDE_ROOT，否则覆盖层在恢复时静默丢失，必须在产生第一份覆盖文件前完成；Task 103可选，取到 OO 保留 vbaProject.bin 的证据后才允许放开 xlsm"
    },
    {
      "wave": 2,
      "name": "只读解析与零回归证明",
      "tasks": [6, 7, 8, 9],
      "depends_on": [1],
      "rationale": "Task 7 的零回归判据必须先绿再做 Task 8 的接线 —— 先证明无回归再动既有解析器"
    },
    {
      "wave": 3,
      "name": "写入门与版本化",
      "tasks": [10, 11, 12, 13, 14, 15],
      "depends_on": [2],
      "rationale": "解析已可信后才允许产生覆盖文件；越界门与扩展名门先于版本写入，权威目录冻结判据压在最后一道"
    },
    {
      "wave": 4,
      "name": "OO 编辑会话与无损判据",
      "tasks": [16, 17, 18, 19],
      "depends_on": [3],
      "rationale": "编辑会话要写覆盖层，故依赖 Wave 3；无损判据分会话层与保存层两段，落盘路径纯净性用 AST 可达性"
    },
    {
      "wave": 5,
      "name": "UI 与影响面",
      "tasks": [20, 21, 22],
      "depends_on": [4],
      "rationale": "UI 需要后端下发的来源/版本字段，故依赖 Wave 4 的端点"
    },
    {
      "wave": 6,
      "name": "变异检验与收口",
      "tasks": [23, 24, 25],
      "depends_on": [5],
      "rationale": "变异检验要在全部判据到位后做；收口核查产物入库，防「spec 全绿 ≠ 产物已入库」"
    }
  ]
}
```

## Notes

### 与前置交付的关系

本 spec 依赖两项**已交付并实测**的能力，不要重复实现：

* `backend/app/services/workpaper_sync/excel_sheet_visibility.py` —— zip 级 sheet 可见性
  （只改 `xl/workbook.xml`）+ `_assert_only_workbook_part_changed` 逐部件字节自检。
  K11 九步真实切换序列实测 **11 项指标 0 漂移**；全模板库 **314 份多 sheet 模板全通过**。
  Property 11 直接复用该自检函数。
* `backend/app/services/workpaper_sync/excel_row_shift.py` 的 `_rewrite_formula_refs` ——
  公式行号改写的唯一入口，已处理四类误命中（跨 sheet 表名当 A1 引用、跨 sheet 目标格被误位移、
  带数字函数名如 `LOG10`、字符串字面量）。本 spec 不改它，但 Property 12 的跨 sheet 引用
  不变性与它同源。

### 反面教材（本 spec 要避开的两类已实证毁坏）

* **openpyxl 全量重写**：K11 实测 zip 部件 37→19、共享公式主格 12→0、非空缓存值 716→28、
  样式索引 94→218 全表重排、中文表名被写成 `&#23457;` 数字实体。
  `excel_materialize.select_write_strategy` 早已判定 351 个模板没有一个能通过 openpyxl 这道门。
* **Univer 往返**：`xlsx → openpyxl → JSON → Univer → 再导出` 两次有损转换，快照模型没有
  printerSettings / VML 批注 / customXml 的概念。Requirement 7.3 明令排除。

### 判据纪律

* 「字符存在」型判据不算判据。`_strip_comments` 不剥 Python docstring —— 对生产源做「某符号
  是否真被用到」的判断前必须先剥 docstring，否则 docstring 里叙述性提到的符号名会被当成真实引用
  （已在 `test_task54_l_cycle_migration.py` 栽过一次，那里现已有 `_strip_docstrings` 可复用）。
* 每条结构性判据写完必做变异检验，没打红 = 守卫有缺陷，不是代码没问题。
* 变异用例本身要敏感：被检验的机制必须是该用例的**唯一**保护。若另有第二道防线也挡住同一
  用例，变异不会打红，会被误判成守卫缺陷。

### 收口

* 每个 Wave 结束跑 `git status --porcelain -- <本 Wave 产物清单>`，见 `??` 即 add。
  「spec 全绿 ≠ 产物已入库」—— 挂进 CI 的 job 在干净 checkout 下必须能跑。
* 改动 `backend/app/**/*.py` 后必须重跑受影响的生成器（`generate_workpaper_writer_inventory.py`
  等），否则一批 freshness 判据会连带打红。归因方法：`git status --porcelain` 空输出 = 未修改，
  用它区分自己的债与并发会话的债。
