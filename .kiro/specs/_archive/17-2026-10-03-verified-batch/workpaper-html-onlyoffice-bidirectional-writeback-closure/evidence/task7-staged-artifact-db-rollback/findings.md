# Task 7 实证：Windows staged artifact publish、DB rollback 与 orphan GC 边界

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 7
Requirements 2.4 / 3.4 / 5.9 / 9.6 / 9.7 / 14.6 · Property 5 / 9 / 42

**这是 Wave 0 探针，不是实现。** Task 9（迁移）与 Task 11（CanonicalArtifactRepository /
RetentionPolicyService）尚未开工，本目录只提供「平台边界行为」的可复算实证，供 Task 9/11/15 引用。
本任务未新增正式迁移、未写业务表、未改生产代码。

## 采集环境

| 项 | 值 |
|---|---|
| run_id | `20260824T163552Z-ded0a7` |
| 平台 | Windows-10-10.0.19045-SP0 / Python 3.12.8 |
| 项目卷 / 临时卷 | `D:` / `C:`（跨卷用例的前置条件成立） |
| PostgreSQL | 16.14（Debian）· database `audit_platform` |
| scratch schema | `tmp_task7_probe_2e922c226dc4`（跑完 `DROP SCHEMA CASCADE`，复核 remaining=0） |
| 探针 | `backend/scripts/diagnose/probe_task7_staged_artifact_boundaries.py all` |
| 用例 | fs1–fs8 + db1–db6，`probe_status = ok`，逐 case `status = ok`，harness_errors = 0 |
| 只读种子 | `backend/wp_templates/A/A31 审计标识一览表.xlsx`（只复制，未修改模板库） |

## 一、Windows 文件系统实证

### fs1 流式 staging + fsync

- 分块流式写入，边写边算 sha256；`streaming_sha256 == reread_sha256 == seed_sha256`。
- `os.fsync(fd)` 对**文件**可用。
- 🔴 **目录 fsync 在 Windows 不可用**：`os.open(dir, O_RDONLY)` 直接
  `PermissionError errno=13`（连 fsync 都到不了，失败发生在 `open` 阶段）。
  ⇒ POSIX 惯用的「rename 后 fsync 父目录」无法照搬，rename 的元数据持久性依赖 NTFS 日志。
  **实现不得声称做了目录 fsync。**
- staging 位于项目同卷（`D:`），staging identity（`artifact_stage_id`）不依赖 operation。

### fs2 content-addressed publish 幂等

- 目标名 `{generation:09d}-{sha256[:12]}{ext}`。同内容两次 publish → **同目标名、同目标 sha256**。
- 异内容 → 不同目标名，且第一个 published artifact 未被覆盖。
- 🔴 幂等尺度是 **(目标路径, 目标 sha256)**，不是文件身份：重复 publish 后 NTFS
  `st_ino`（file index）**会变**（本轮 1125899907582099 → 1125899907582105）。
  **实现不得用 st_ino / file index 判幂等。**
- publish 后 staging 文件消失（`os.replace` 语义）。

### fs3 `os.replace` 同卷原子性

双判据，且都设观测量下限（观测不足直接 ERROR，不允许把「没看」当「没有」）：

| 判据 | 观测数 | 结果 |
|---|---|---|
| size 采样（`os.stat`，不长期持句柄） | 5315 | 只见 524288 / 786432 两种完整大小；中间大小 **0** 个；missing **0** |
| content 采样（`FILE_SHARE_READ\|WRITE\|DELETE` 短开短读） | 968 | 全部是完整旧/新内容；撕裂读 **0**；missing **0** |

⇒ 同卷 `os.replace` 对并发读者表现为原子替换。

附带观测：content 段有 **122 次** `os.replace` 因并发句柄被拒后重试成功
（`replace_retry_count`）—— 这与 fs5 的结论一致，见下。

### fs4 `os.replace` 跨卷

- `C:` staging → `D:` 目标：**失败**，`OSError errno=18 (EXDEV) / winerror=17
  (ERROR_NOT_SAME_DEVICE)`，`系统无法将文件移到不同的磁盘驱动器。`
- 失败后源文件仍在、目标不存在（无半成功态）。
- 唯一跨卷 fallback `shutil.move` 能成功但是 **copy 语义**：32 MiB 文件的三次移动中，
  size 采样都观测到**目标路径以 0 字节可见**（`incomplete_sizes = [0]`）后才变为完整大小。
  受缓冲写入影响未逐级看到中间大小，故契约只声明「不完整即可见」这一点。

⇒ **staging 目录必须与 publish 目录同卷**：跨卷根本没有原子原语，退化方案会让目标路径在内容
完整前就出现在 publish 命名空间里。

### fs5 文件占用（六种 share 模式全测）

| 被占用方 | share 模式 | `os.replace` 结果 |
|---|---|---|
| 目标 | `none` | `PermissionError errno=13 winerror=5` |
| 目标 | `read` | 同上 |
| 目标 | `read_write` | 同上 |
| 目标 | `read_delete` | 同上 |
| 目标 | `read_write_delete` | 同上 |
| 目标 | `delete_only` | 同上 |
| 源 | `read_write` | `PermissionError errno=13 winerror=32`（ERROR_SHARING_VIOLATION） |

🔴 **结论一（反直觉，必须记住）**：Windows 上**任何** share 模式（包含 `FILE_SHARE_DELETE`）
持有目标句柄，都会让 `os.replace` 报 **WinError 5**。`os.replace` 落到
`MoveFileExW(..., MOVEFILE_REPLACE_EXISTING)`，其替换路径不接受目标上存在任何句柄。
⇒ 「让读者用 share-delete 打开」**不是**可行缓解，别在 Task 11 里写这种方案。
（首轮探针只测了一种 share 模式，得出「share-delete 可以」的错误预期，后补成六模式矩阵才纠正。）

🔴 **结论二（架构性）**：目标名**不预先存在**时，即使另一进程正持有**旧 current artifact**，
publish 依旧成功（`fresh_target_while_old_current_held`：`raised=false`、新目标已建、旧 current 完好）。
⇒ content-addressed 不可变发布天然绕开占用问题；current 切换交给 **DB pointer**，
不要覆盖固定路径。所有失败都保留旧内容（六个目标用例的 `target_is_old_content` 全为 true，
`target_is_new_content` 全为 false）。

**诊断码映射**（Requirement 9.7「SHALL 可诊断」）：

| 情形 | exc | errno | winerror | 语义码 |
|---|---|---|---|---|
| 目标被占用 | PermissionError | 13 | 5 | `FILE_IN_USE` |
| 源被占用 | PermissionError | 13 | 32 | `FILE_IN_USE` |
| 跨卷 rename | OSError | 18 | 17 | `CROSS_VOLUME_RENAME` |

目标占用与源占用错误码不同，可分开诊断。杀毒扫描持句柄属同一失败模式与同一诊断码
（未单独注入，见「未覆盖项」）。

### fs6 进程中断

用子进程 + `TerminateProcess` 实测，**判成败只查磁盘状态，不看退出码**（被 kill 的子进程
退出码恒为 1，与写成功/失败无关）。

| 注入点 | 残留 | 是否可能被误当 published |
|---|---|---|
| 写 staging 途中 kill | `artifact.tmp` 存在、**1310720 / 4194304 字节**（部分）、hash ≠ 完整 hash | 否 |
| staging 完成、publish 前 kill | `artifact.tmp` 完整且 hash 有效 | 否 |

三重理由（都有实测支撑）：

1. 残留只在 `.staging/{wp_id}/{artifact_stage_id}/artifact.tmp`，`.versions` 命名空间扫描
   不含任何 `.staging` 路径；
2. publish 目标名由内容 sha256 决定，半成品 hash 与声明 hash 不符 ⇒ publish gate 直接拒绝；
3. resolver 只解析 `.versions` 下、由 DB pointer 指向的 published artifact（db2/db3 佐证）。

第二种残留归类为 `orphan_candidate_invisible_to_resolver`，走 reconciliation + GC。

### fs7 路径安全（Property 42）

8 类逃逸全部被 `os.path.realpath` + 根归属判定拒绝，`inside_ok` 被接受：

`traversal_relative` / `traversal_nested` / `traversal_posix_style` / `absolute_outside` /
`unc_path`（`\\127.0.0.1\C$\...`）/ `cross_project_absolute` / `cross_project_traversal` /
`symlink_escape`

- 软链接越界**真建了链接**（`os.symlink`，本机管理员权限），realpath 解析到
  `C:\Users\Administrator\AppData\Local\Temp\tmp_task7_probe_escape_*\artifact.xlsx` ⇒ 拒绝。
  仅字符串前缀比较无法拦住这一类。
- 跨项目复用：同一相对路径在两个 project 根下解析到不同绝对路径，归属判定只能靠 realpath，
  不能靠 `relative_path` 字符串唯一性。
- 扩展名伪装：非 ZIP 的 `.xlsx` 被 magic bytes（`PK\x03\x04`）拒绝；xlsx 字节改名 `.docx`
  被 zip 内部件识别为 xlsx（`xl/workbook.xml`）。扩展名不作类型依据。

### fs8 校验门注入（Property 9）

三个注入点各自在**第一个对应 gate** 处失败（`zip_structure` / `ooxml_parts` /
`roundtrip_equivalence`），三者均：

- `published = false`
- `current_sha_unchanged = true`
- `pointer_unchanged = true`（generation/revision/artifact_sha256 三元组不变）
- `versions_namespace_unchanged = true`
- 只在 `.staging` 留下 residue

## 二、DB rollback / orphan / GC 实证

结构在 scratch schema 内等价复现（`working_paper_artifact` / `working_paper_content_version` /
`working_paper_content_representation` / `working_paper_sync_entry_state` /
`working_paper_artifact_gc_audit` + 一个「representation 必须引用 published canonical artifact」触发器）。
`db_sql_log.json` 记录全部 135 条语句，守卫结构化提取写目标逐条校验 scratch 限定。

### db2 publish 后 DB rollback（Property 5 核心）

两种失败注入都做：Python 异常（模拟 outbox 写入失败）与真实约束冲突
（`uq_wpcv_revision`，pgcode 23505）。两例结论完全一致：

| 断言 | 实测 |
|---|---|
| entry pointer generation | 仍为 1（旧 representation） |
| 新 artifact row 数 | 0 |
| 五张表行数 | 与 baseline 完全相同 |
| resolver 返回 | 只有旧 published artifact |
| **磁盘上的新文件** | **仍存在，sha256 与 publish 时一致** |

🔴 **这就是「文件系统与 PostgreSQL 不是同一事务」的正证据**：DB `ROLLBACK` 不回滚已 publish
的文件。唯一正确语义 = 失败只留下**对 resolver 不可见的 orphan**。

### db6 反向证据

只提交 pointer、不 publish 文件 ⇒ commit 成功、resolver 返回一行、而
`relative_path` 在磁盘上**不存在**。
⇒ 「pointer 指向缺失 artifact」的半成功态在物理上完全可能，**发布顺序必须是
publish-then-commit**；顺序反了没有任何机制能救。

### db3 candidate / incoming / orphan 永不可解析

三例插入 representation 全被触发器拒绝，pgcode 均为 `23514`（check_violation）：

| artifact | kind / state | 结果 |
|---|---|---|
| upgrade candidate | `upgrade_candidate` / `candidate` | 拒绝 |
| durable incoming | `incoming` / `durable` | 拒绝 |
| orphan canonical | `canonical` / `orphan` | 拒绝 |

⇒ Task 9 的迁移应带同形状的 CHECK/trigger；Task 11 的 service validator 与之双层锁死。

### db4 orphan reconciliation（两种形态都覆盖）

- **磁盘有文件、DB 无 row**（rollback 时 artifact row 一起没了）→ reconciliation 扫描
  `.versions` 后**登记**为 `state='orphan'`（2 个）；
- **DB 有 published row、无 representation 引用**（artifact row 先单独提交、pointer 事务失败）→
  **标记**为 orphan（1 个）。

三条 orphan 都带 `orphaned_at`；reconciliation 后 resolver 仍只返回旧 published artifact。

### db5 RetentionPolicy / GC（`workpaper-sync-retention:v1`）

| 阶段 | 判定 | 文件 |
|---|---|---|
| grace 未到，dry-run | 全 `retain` / `grace_not_elapsed` | 全在 |
| grace 已过，dry-run | 出现 `delete` 判定 | **全在**（dry-run 永不删） |
| grace 已过，apply，二次确认无引用 | `delete` / `grace_elapsed_and_unreferenced` | 已删 |
| grace 已过，apply，二次确认**发现引用重现** | `retain` / `reference_found_on_recheck` | **保留** |
| `legal_hold_canonical` | `retain` / `legal_hold` | 保留 |

- 每个判定都写审计行，`dry_run` 真假分别留痕。
- 无策略时 `retain` + 告警（`no_policy_retain_and_alert`），不确定即保留。
- GC 全程不影响 resolver 结果。

## 三、Task 7 的四个直接结论

1. **staging 目录必须与 publish 目录同卷** —— 是。跨卷 `os.replace` 报 WinError 17，
   唯一 fallback 会让目标在内容完整前可见（fs4）。
2. **被占用的文件能否原子替换** —— 不能，且**任何 share 模式都不能**（含 FILE_SHARE_DELETE），
   一律 WinError 5；源被占用是 WinError 32。旧内容始终完好（fs5）。
3. **半成品能否被误当 published** —— 不能。命名空间隔离 + 内容寻址 hash gate + resolver
   只认 DB pointer，三重独立理由都有实测（fs6 + db2/db3）。
4. **文件系统与 PostgreSQL 是否同一事务** —— **不是同一事务**，且不得如此宣称。db2 证明 DB
   rollback 不回滚文件，db6 证明 DB commit 不创造文件。

## 四、未覆盖项（明确登记，不标成功）

| 项 | 状态 | 阻塞点 | 替代证据 |
|---|---|---|---|
| `os.replace` 自身被中断的半成品 | 未独立注入 | 单次 `MoveFileExW` 元数据调用，用户态无法注入中断点 | fs3 的 5315 次 size 采样 + 968 次 content 采样均未见中间态 |
| 杀毒软件扫描导致的 rename 冲突 | 未注入 | 无法在本机确定性触发 AV 扫描窗口 | fs5 已证明任意进程持句柄即产生 WinError 5，AV 属同一失败模式与同一诊断码 |
| 生产 `CanonicalArtifactRepository` / `RetentionPolicyService` 行为 | 超出 Wave 0 | Task 11 未开工 | 本任务只固化其必须满足的平台边界 |

## 五、守卫与变异检验

- 契约：`backend/data/workpaper_staged_artifact_boundary_contract.json`（`schema_version: 1`）
- 守卫：`backend/tests/test_workpaper_staged_artifact_boundary_contract.py`（34 例全绿）
- 变异 runner：`backend/scripts/diagnose/mutate_task7_staged_artifact_boundary_guards.py`
- 变异结果：`mutation_report.json` —— 23 条变异，**RED 22 / GREEN 1（对照项）/ ANCHOR-MISS 0 /
  WRONG-TEST 0**，还原后基线回到全绿。

变异检验抓出的**真实守卫缺陷**（已修）：第 21 条变异把写目标改成 `public.working_paper_artifact`
但保留 scratch schema 名，首轮 **GREEN** —— 因为守卫原来只做「语句里出现 scratch schema 名」的
子串检查。已改为结构化提取写目标（`INSERT INTO` / `UPDATE ... SET` / `CREATE TABLE` /
`CREATE INDEX ... ON` / `CREATE TRIGGER ... ON` / `ALTER TABLE` / … 逐个要求 scratch 限定），
复测 RED。这条同时也是给 Task 9/11 的提醒：**「未写业务表」不能靠字符串包含判定。**

## 六、文件清单

| 文件 | 内容 |
|---|---|
| `run_meta.json` | 采集环境、`probe_status`、逐 case 状态、布局元数据 |
| `fs_observations.json` | fs1–fs8 原始观测 |
| `db_observations.json` | db1–db6 原始观测 |
| `db_sql_log.json` | scratch schema 名 + 全部 135 条 SQL（未写业务表的可复算证据） |
| `mutation_report.json` | 22 条变异的四态结果 |
| `findings.md` | 本文件 |
