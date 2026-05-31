# Bug 修复：global-modules-cleanup（全局模块多源澄清 + 死文件清理 + 联动补全）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§一 地址库 + §五 底稿模板库 + §四 枚举字典 + §12.2 地址库澄清 + §21.3.2 模板联动 + §20.6 懒建表扫描）
> 工作流：Requirements-First（bugfix，多个独立小修打包）
> 定位：6 个小修打包成一个 spec（各自独立可分批，互不依赖）

## 一、背景

全局 7 模块盘点（六轮复盘）发现一批"非内核重构"的零散问题：地址库 V1/V2 命名混淆 + 33MB 死文件、底稿模板 JSON→registry 联动断裂、枚举字典陈旧注释、懒建表绕 D6。这些不值得各立 spec，打包成一个 cleanup spec 分批消除。

## 二、Bug 条件 C(X)（代码实证）

### C1：地址库 33MB 死文件进 git
- **实证**：`address_registry_l1_physical.json`（33.6MB）全仓代码 **0 处 import**（grep 仅 docs 提及）；scan 脚本只生成 l2/l3/resolved 不碰 L1
- **后果**：仓库最大单文件之一是死数据

### C2：地址库 V1/V2 命名混淆
- **实证**：V1（内存版 address_registry，公式编辑地址目录）与 V2（文件版 address_registry_v2，stale 影响依赖图）共用 "address-registry" 名字，但是**两个正交关注点**
- **后果**：开发者不知道该用哪个；§12.2 裁定"澄清非合并"

### C3：底稿模板 JSON→registry 无同步（联动断裂 §21.3.2）
- **实证**：scan 脚本生成 `gt_template_library.json` 后**不写** `wp_template_registry` 表（grep scan 脚本 0 命中 wp_template_registry）
- **后果**：JSON 更新后前端模板管理页（读 registry 表）可能过时

### C4：枚举字典陈旧注释
- **实证**：`system_dicts.py` 的 `_DICTS` docstring 写"与前端 statusMaps.ts 保持一致"，但 `statusMaps.ts` 实际不存在（已改名 `statusEnum.ts`）
- **后果**：误导后人以为要双维护

### C5：懒建表绕 D6（drift detector 盲区 §20.6）
- **实证**：`formula_audit_log.py` + `account_note_mapping.py` + `consol_cell_comments.py` 用 `CREATE TABLE IF NOT EXISTS` 懒建（grep 实证，非 migrations 目录）
- **后果**：绕开 D6 迁移，drift detector 盲区
- **注**：formula_audit_log 的懒建由 formula-engine-unification spec 收口，本 spec 处理 account_note_mapping + consol_cell_comments + 全仓扫描清单

## 三、修复条件（满足即修复）

- **F1**：`address_registry_l1_physical.json`（33MB）移出 git tracked（确认 0 引用后 git rm，构建需要则改 .gitignore + 文档注明生成命令）
- **F2**：V1/V2 两 router 文件头互标 `@see` 职责注释（V1=运行时地址目录/公式编辑，V2=静态依赖图/影响分析）；V2 router tag 向 linkage/dependency 靠拢
- **F3**：scan 脚本末尾加 `sync_registry_from_json()`（幂等 upsert wp_template_registry）
- **F4**：`_DICTS` docstring "statusMaps.ts" → "statusEnum.ts（fallback）"，明确 API 主源
- **F5**：account_note_mapping + consol_cell_comments 懒建表纳入 D6 迁移；全仓 `CREATE TABLE IF NOT EXISTS`（排除 migrations/tests）扫描产出清单

## 四、保留行为（修复不能破坏）

- 地址库 V1/V2 各自功能不变（仅命名/注释澄清，不合并、不改逻辑）
- 底稿模板 JSON 主源地位不变（registry 是派生）
- 枚举字典 API 主源 + statusEnum.ts fallback 设计不变（仅修注释）
- 删 L1 死文件前 `git log` 确认无近期更新 + grep 二次确认 0 引用
