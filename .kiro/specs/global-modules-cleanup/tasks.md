# 实施计划：global-modules-cleanup（全局模块多源澄清 + 死文件清理 + 联动补全）

> Bug 条件：#[[file:.kiro/specs/global-modules-cleanup/bugfix.md]]
> 设计：#[[file:.kiro/specs/global-modules-cleanup/design.md]]
> 工作流：Requirements-First（bugfix）| 6 个独立小修可分批 commit
> 铁律：删死文件前 grep 0 引用 + git log 确认无近期更新；懒建表入 D6 三层一致

## F1 — 清 33MB 死文件（~0.5 天）

- [ ] 1. 三重验证后删 L1 物理文件
  - grep 确认 `address_registry_l1_physical` 全仓 0 代码引用（仅 docs）
  - git log 确认无近期更新 + 确认 scan 脚本不生成 L1
  - git rm（纯死数据）或 .gitignore + 文档注明生成命令（构建期需要）
  - 删后 app import OK + 仓库瘦身验证
  - _Bug 条件: C1_ _属性: H1_

- [ ] 2. 评估 unified_dependency_graph.json(11.9MB)
  - grep linkage_graph_builder 消费方，确认运行时是否加载
  - 死数据则同 L1 处理，运行时用则保留
  - _Bug 条件: C1_ _属性: H1_

## F2 — V1/V2 命名澄清（~0.5 小时）

- [ ] 3. 两 router 文件头互标 @see + V2 tag 改名
  - V1 address_registry 标"运行时动态地址目录（公式编辑用）"
  - V2 address_registry_v2 标"静态依赖图（stale 影响分析，linkage_graph 离线产物）"
  - V2 router tag "address-registry" → "linkage-analysis"
  - _Bug 条件: C2_ _属性: H3_

## F3 — 底稿模板 JSON→registry 联动（~0.5 天）

- [ ] 4. scan 脚本加 sync_registry_from_json
  - scan 末尾幂等 upsert wp_template_registry（on_conflict_do_update）
  - JSON utf-8-sig 读 + 字段映射（code/name/cycle_prefix）
  - _Bug 条件: C3_ _属性: H2_

- [ ] 5. F3 验证
  - scan 后 registry 行数 == JSON templates 数；幂等重跑 skip
  - _Bug 条件: C3_ _属性: H2_

## F4 — 枚举字典陈旧注释（~0.5 小时）

- [ ] 6. 修 _DICTS docstring
  - "statusMaps.ts" → "statusEnum.ts（fallback）"；明确 API 为运行时主源
  - _Bug 条件: C4_

## F5 — 懒建表纳入 D6（~0.5 天）

- [ ] 7. 全仓懒建表扫描清单
  - grep `CREATE TABLE IF NOT EXISTS`（排除 migrations/tests）产出清单
  - 文档记录（formula_audit_log 归 formula-engine spec，本 spec 处理其余）
  - _Bug 条件: C5_ _属性: H4_

- [ ] 8. account_note_mapping + consol_cell_comments 入 D6
  - 两表 CREATE TABLE IF NOT EXISTS 懒建 → V0XX 迁移（+R0XX 回滚，IF NOT EXISTS 幂等）
  - 删 ensure_table 懒建调用
  - ORM 三层一致校验
  - _Bug 条件: C5_ _属性: H4_

- [ ] 9. F5 验证
  - 迁移幂等（重跑 skip）+ drift detector 不再报这两表盲区
  - _Bug 条件: C5_ _属性: H4_

## 收尾

- [ ] 10. 集成验证 + 收尾
  - 全部修复后 app import OK + 既有测试零回归
  - 更新 INDEX.md + memory；各小修分批 commit（git status 确认无其他 staged）
  - _Bug 条件: C1, C2, C3, C4, C5_ _属性: H1, H2, H3, H4_
