# 设计文档：global-modules-cleanup（全局模块多源澄清 + 死文件清理 + 联动补全）

> Bug 条件：#[[file:.kiro/specs/global-modules-cleanup/bugfix.md]]
> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§一/§五/§四/§12.2/§21.3.2/§20.6）
> 工作流：Requirements-First（bugfix）

## 一、概述

6 个独立小修打包：地址库 33MB 死文件清理（F1）+ V1/V2 命名澄清（F2）+ 底稿模板 JSON→registry 联动（F3）+ 枚举字典陈旧注释（F4）+ 懒建表纳入 D6（F5）。各自独立、互不依赖、可分批 commit。原则：**该单源单源（无重复，仅澄清边界）、该联动联动（JSON→registry 单向派生）、死代码该删就删（小心验证 0 引用）**。

## 二、修复方案

### F1：清 33MB 死文件（删，小心验证）

```bash
# 删前三重验证（删除铁律）
grep -rn "address_registry_l1_physical" backend/ audit-platform/   # 确认 0 代码引用
git log --oneline -- backend/data/address_registry_l1_physical.json   # 确认无近期更新（真实路径 backend/data/）
# 确认 scan 脚本不生成 L1（只生成 l2/l3/resolved）
git rm --cached backend/data/address_registry_l1_physical.json   # 移出 tracked
# 若构建期需要 → .gitignore 加 + 文档注明生成命令；若纯死数据 → 直接 git rm
```
> 同步评估 `unified_dependency_graph.json`(11.9MB) 是否运行时加载（linkage_graph_builder 生成，确认消费方后决定保留/移出）。

### F2：V1/V2 命名澄清（不合并）

- V1 `address_registry.py` + `routers/address_registry.py` 文件头加：`@see address_registry_v2 — 本模块=运行时动态地址目录（公式编辑用）`
- V2 `routers/address_registry_v2.py` 文件头加：`@see address_registry — 本模块=静态依赖图（stale 影响分析用，linkage_graph 离线产物）`
- V2 router tag 从 "address-registry" 改 "linkage-analysis"（前端不动，两套 store 本就分离）

### F3：底稿模板 JSON→registry 联动（单向派生）

scan 脚本（`_scan_workpaper_templates.py` 或正式 scan 工具）末尾追加：

```python
async def sync_registry_from_json(db: AsyncSession):
    """JSON 生成后幂等 upsert wp_template_registry（JSON 是权威源，registry 是派生）。"""
    library = json.loads(Path("backend/data/gt_template_library.json").read_bytes())  # utf-8-sig
    for tpl in library["templates"]:
        await db.execute(
            insert(WpTemplateRegistry).values(wp_code=tpl["code"], wp_name=tpl["name"],
                cycle=tpl["cycle_prefix"], ...)
            .on_conflict_do_update(index_elements=["wp_code"], set_={...}))
    await db.commit()
```
> 权威源=JSON（scan 生成），派生=registry 表（单向，安全）。

### F4：枚举字典陈旧注释

`system_dicts.py` `_DICTS` docstring："与前端 statusMaps.ts 保持一致" → "与前端 `constants/statusEnum.ts`（dictStore 加载失败时的 fallback）保持一致；API `/api/system/dicts` 为运行时主源"。

### F5：懒建表纳入 D6

- `account_note_mapping.py` + `consol_cell_comments.py` 的 `CREATE TABLE IF NOT EXISTS` 懒建 → 改为 V0XX 迁移（+ R0XX 回滚），删 ensure_table 懒建调用
- 全仓 `grep "CREATE TABLE IF NOT EXISTS"`（排除 migrations/tests）产出懒建表清单（一次性扫描，文档记录）
> formula_audit_log 的懒建由 formula-engine-unification spec 处理，本 spec 不重复。

## 三、验证策略

- F1：删后 app import OK（无 import 该文件）+ 仓库瘦身 33MB
- F2：纯注释/tag 改动，零功能影响（getDiagnostics 0）
- F3：scan 后 registry 表行数 == JSON templates 数（幂等重跑 skip）
- F4：纯注释改动
- F5：迁移幂等（CREATE/ALTER IF NOT EXISTS）+ drift detector 不再报这两表盲区

## 四、正确性属性

- **H1 死文件无引用**：删 L1 后全仓 grep 0 引用 + app import OK
- **H2 registry 同步**：sync_registry_from_json 后 registry 行数 == JSON templates 数（幂等）
- **H3 命名澄清零回归**：V1/V2 功能不变（仅注释/tag）
- **H4 懒建表入 D6**：account_note_mapping + consol_cell_comments 迁移幂等 + 三层一致
