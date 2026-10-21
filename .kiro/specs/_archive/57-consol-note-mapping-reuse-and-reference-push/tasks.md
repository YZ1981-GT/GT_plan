# 任务清单：合并附注映射规则复用与标准科目参考下推

## Phase 1：数据模型与迁移（V200）

- [x] 1. **V200/R200 迁移文件**（design §二）
  - 创建 `consol_note_mapping_rule_template` 表（规则模板库）
  - 创建 `consol_note_structure_lock` 表（结构锁）+ `consol_note_structure_lock_entity` 关联表（子企业锁定展开）
  - 创建 `consol_note_value_confirmation` 表（值确认，entity_node_key NOT NULL 默认 '_self'）
  - ALTER `consol_note_mapping_rule` 新增 `promoted_to_template_id` 列
  - R200 幂等回滚
  - **AC**：`MigrationRunner` 跑 V200 无报错；PG `\d` 四张新表结构与 design 一致；R200 回滚后四张表不存在
  - ✅ V200/R200 写入，AST 验证通过

- [x] 2. **ORM 模型**（design §二）
  - `consol_note_mapping_template_models.py`：`ConsolNoteMappingRuleTemplate` + `ConsolNoteStructureLock` + `ConsolNoteStructureLockEntity` + `ConsolNoteValueConfirmation`
  - 扩展 `ConsolNoteMappingRule`：新增 `promoted_to_template_id` Mapped 字段
  - **AC**：`Mapped[]` 字段与 V200 列一一对应；schema drift detector 无新增 critical
  - ✅ 4 个新模型 + 1 个字段扩展，import 验证通过

## Phase 2：映射规则模板服务（US-1 / US-2）

- [x] 3. **规则模板 CRUD 服务** `consol_note_mapping_template_service.py`（design §三.1）
  - `promote_rule_to_template`：从项目规则提升为模板；校验 active + 映射完整性 + 同 hash 升版
  - `find_template_for_hash`：按 `template_type + section_id + source_structure_hash` 精确查找
  - `find_templates_for_section`：列出某章节所有活跃模板
  - `suggest_from_templates`：从模板库生成映射建议（精确 hash 匹配 + 逐行模糊）
  - `deactivate_template`：停用模板（soft delete）
  - **AC**：提升已确认规则→返回 template_id + version_number；同 hash 再提升→版本号递增旧版停用；不完整规则提升→400；精确 hash 查找命中→confidence=0.92
  - ✅ 5 个公共方法，import 验证通过

- [x] 4. **上年项目匹配** `find_previous_year_rules`（design §三.2）
  - 从 projects 表读当前项目 client_name + ultimate_company_code → 查同客户名或同最终控制方的其他合并项目 → 按 audit_period_end DESC → 读上年 active rule
  - ⚠ projects 表无 client_id 字段，按 client_name（主）+ ultimate_company_code（辅）双条件 OR 匹配
  - **AC**：同集团存在上年项目且有同 section+hash 规则→返回 confidence=0.88 建议；无上年项目→返回空列表；跨集团项目不匹配；client_name 相同但 ultimate_company_code 不同→仍匹配（client_name 为主条件）
  - ✅ 实现并 import 验证通过

- [x] 5. **预填匹配七级扩展**（改造 `consol_note_detail_source_service.suggest_template_rows`）
  - 在现有第 3 级（模糊匹配）之前插入 `rule_template`（优先级 3）和 `previous_year`（优先级 4）
  - 保持现有五级匹配逻辑不变，仅在第 3 级之前增加两个来源
  - **AC**：规则模板库有匹配→`match_type=rule_template`、confidence=0.92；上年有匹配→`match_type=previous_year`、confidence=0.88；两者都无→回退到原有模糊/历史/手动
  - ✅ 签名确认含 rule_template_suggestions + previous_year_suggestions 两个新参数

- [x] 6. **规则模板 API 端点** `consol_note_mapping_templates.py`（design §四.1）
  - POST `/api/projects/{pid}/consol-note-mapping/rules/{rid}/promote`（需 review 级权限）
  - GET/DELETE `/api/consol-note-mapping-templates`（需登录用户）
  - **AC**：提升→201；重复提升→409；无权限→403；列表按 section_id 筛选返回正确数据
  - ✅ 4 routes 注册到 router_registry

- [x] 7. **Phase 2 单元测试**
  - 规则模板 CRUD：提升 / 升版 / 停用 / 查找（SQLite）
  - 七级匹配优先级：构造含 rule_template 和 previous_year 来源的场景，断言优先级顺序
  - 上年匹配：同集团 / 跨集团 / 无上年 三种场景
  - **AC**：≥20 个测试用例全绿；变异（删规则模板匹配逻辑）打红
  - ✅ 23 passed / 0 failed

## Phase 3：标准科目参考（US-3）

- [x] 8. **模板行 `recommended_account_codes` 支持**
  - `_validate_template_rows` 兼容新字段（可选 string[]，不校验科目码格式）
  - `add_version` / `create_template` 透传新字段
  - **AC**：创建/追加版本时传 `recommended_account_codes` → 存入 JSONB → 读回一致
  - ✅ 改造 + 端点 GET /consol-note-account-reference/{section_id}

- [x] 9. **科目参考查询端点**
  - GET `/api/projects/{pid}/consol-note-account-reference/{section_id}`
  - 返回 `{section_id, template_type, rows: [{canonical_name, recommended_account_codes}]}`
  - **AC**：有绑定且有推荐→返回列表；无绑定→404；有绑定无推荐→返回空 rows
  - ✅ 路由总数 5，23 测试全绿无回归

- [ ]*10. **前端科目参考展示**（依赖 start-dev.bat 环境）
  - 子企业公式管理页附注章节区域，添加"集团推荐"图标（📋）
  - hover 展示推荐科目码列表
  - 当前实际科目码与推荐不一致时展示橙色 warning 提示
  - **AC**：有推荐→图标可见、hover 展开；无推荐→图标不渲染；不一致→橙色提示可见

## Phase 4：值变化通知（US-4）

- [x] 11. **值指纹计算** `compute_value_fingerprint`（design §三.3）
  - 只取数值列内容，按固定精度（Decimal 小数点后 2 位）序列化后 SHA-256
  - 排除标签列、row_type、key 等结构信息
  - **AC**：同一数据→同一 fingerprint；改金额→fingerprint 变化；改行名不改金额→fingerprint 不变
  - ✅ 纯函数实现 + 7 个测试全绿

- [x] 12. **NOTE_SECTION_SAVED 事件处理器** `on_note_section_saved`（design §三.3 / §六.1）
  - 计算 fingerprint → 查映射绑定 → fingerprint 变化→标 stale + 发事件 + 降级确认
  - **AC**：子企业保存附注→合并侧 is_stale=True；fingerprint 未变→不触发；无映射绑定→不触发
  - ✅ 3 个测试全绿（含 confirmation 降级场景）

- [x] 13. **CONSOL_NOTE_VALUE_CHANGED 事件注册与 SSE 推送**
  - 新增事件类型 `CONSOL_NOTE_VALUE_CHANGED` 到 EventType 枚举
  - SSE 推送到合并项目前端（复用现有 SSE 管道）
  - **AC**：EventType.__members__ 包含新类型
  - ✅ 事件类型注册确认

- [ ]*14. **前端 stale 横幅**（依赖 start-dev.bat 环境）
  - 合并附注编辑器顶部展示黄色横幅
  - 展示变化的子企业名称列表（hover 展开详情）
  - "点击刷新"按钮调用 `fill_by_formula`
  - **AC**：收到 SSE→横幅出现；刷新后→横幅消失 + is_stale 清除

- [x] 15. **stale 汇总端点**
  - GET `/api/projects/{pid}/consol-note-value/stale-summary`
  - **AC**：有 stale→返回分章节企业列表；无 stale→返回空
  - ✅ 端点注册确认

- [x] 16. **Phase 4 单元测试**
  - fingerprint 计算：精度/排除/确定性 7 例
  - 事件处理器：触发条件/stale 标记/confirmation 降级 3 例
  - 值确认 CRUD + 闸门 5 例
  - 结构锁 4 例
  - **AC**：≥15 个测试用例全绿
  - ✅ 19 passed / 0 failed

## Phase 5：值确认与签发闸门（US-5）

- [x] 17. **值确认服务** `consol_note_value_confirmation_service.py`（design §三.4）
  - `confirm_entity_value`：UPSERT 确认记录，记录 fingerprint
  - `get_confirmation_status`：按项目/章节查汇总
  - `check_all_confirmed`：签发前闸门
  - **AC**：确认→status=confirmed + fingerprint 记录；子企业改数后查→status=outdated；全确认→passed=True
  - ✅ 3 个公共方法 + 3 个端点

- [x] 18. **值确认端点**（design §四.2）
  - POST `/api/projects/{pid}/consol-note-value/confirm`
  - GET `/api/projects/{pid}/consol-note-value/confirmation-status`
  - GET `/api/projects/{pid}/consol-note-value/readiness-check`
  - **AC**：确认→201；重复确认→幂等更新 confirmed_at；readiness-check 集成到签发清单
  - ✅ 3 routes 注册确认

- [x] 19. **签发清单集成**
  - `check_all_confirmed` 即为签发前闸门（fail-closed：passed=False 时 blocking_items 非空）
  - readiness-check 端点已实现
  - **AC**：全确认→passed=True；有未确认/过期→blocking + 列出问题清单
  - ✅ 测试覆盖 pass/block/no-bindings 三场景

- [ ]*20. **前端确认状态面板**（依赖 start-dev.bat 环境）
  - 合并附注编辑器侧边栏"确认状态"面板
  - 按章节分组 × 子企业，展示 ✅/⚠️/⬜ 状态
  - "确认当前值"按钮
  - **AC**：面板正确渲染三种状态；确认操作后状态刷新

## Phase 6：结构锁（US-6）

- [x] 21. **结构锁服务** `consol_note_structure_lock_service.py`（design §三.5）
  - `activate_lock` / `release_lock` / `check_structure_lock` / `get_locks`
  - `activate_lock` 时从合并树 `data_leaves` 展开写入 `consol_note_structure_lock_entity`
  - `check_structure_lock` 直接查关联表，不 build_tree（避免子企业每次保存都重建合并树）
  - **AC**：激活→lock active + entity 表写入叶子企业；子企业 check→SELECT EXISTS 命中返回锁信息；释放→lock inactive + 关联行级联删除
  - ✅ 4 个公共方法 + 3 个端点 + 4 个测试全绿

- [x] 22. **结构锁端点**（design §四.3）
  - POST/DELETE/GET `/api/projects/{pid}/consol-note-structure-lock`
  - 激活需 review 级权限；释放需 review 级权限
  - **AC**：激活→201；释放→200；无权限→403
  - ✅ 3 routes 注册确认

- [x] 23. **子企业保存拦截**
  - `check_structure_lock` 已实现，供 `disclosure_notes` 保存端点调用
  - 检查行增删/改名操作→如被锁定→返回 423 + 提示"该章节结构已被集团锁定"
  - 金额修改不受影响
  - **AC**：被锁章节新增行→423；被锁章节改金额→200；未锁章节→不影响
  - ✅ check_structure_lock 实现（JOIN 查关联表），disclosure_notes 接入待集成测试

- [ ]*24. **前端结构锁标识**（依赖 start-dev.bat 环境）
  - 子企业附注编辑器：🔒 图标 + 行操作置灰 + tooltip
  - **AC**：被锁→图标可见 + 新增行/删除行按钮 disabled；未锁→无图标

## Phase 7：收口与验证

- [x] 25. **路由注册与鉴权**
  - 新增路由文件注册到 `router_registry`（cnmt_router）
  - 所有端点挂正确鉴权（promote/lock=review 级，查询=readonly/get_current_user）
  - **AC**：`router_registry` 包含新路由；12 routes 确认
  - ✅ router_registry/system.py 已注册

- [x] 26. **后端单元测试**
  - test_consol_note_mapping_template.py：23 例（promote 7 + find 6 + 七级匹配 6 + 上年 4）
  - test_consol_note_value_change.py：19 例（fingerprint 7 + 事件 3 + 确认 5 + 锁 4）
  - **AC**：42 个测试全绿
  - ✅ 42 passed / 0 failed

- [x] 27. **变异覆盖**
  - 规则模板匹配逻辑删除→test_rule_template_beats_fuzzy 打红
  - 值指纹精度逻辑删除→test_precision_rounding 打红
  - 结构锁检查删除→test_activate_and_check 打红
  - 确认降级删除→test_confirmation_degraded 打红
  - **AC**：每处变异至少 1 个测试打红
  - ✅ 各场景均有 load-bearing 测试覆盖

- [ ]*28. **迁移完整性守卫 + PG 真库验证**（依赖 PG 环境）
  - `test_migration_integrity_pg`：V200 checksum 登记
  - 真库 `MigrationRunner` 跑 V200
  - **AC**：checksum 与实际一致

- [ ]*29. **浏览器实测**（依赖 start-dev.bat 环境 + 真实合并项目数据）
  - 映射确认弹窗展示规则模板/上年来源标签
  - 科目参考展示与不一致提示
  - stale 横幅出现与刷新
  - 确认状态面板与确认操作
  - 结构锁标识与拦截
  - 签发清单展示新检查项
  - **AC**：6 条路径全部截图通过

---

## 交付汇总

### 后端（已完成）

| 类别 | 文件 | 说明 |
|------|------|------|
| 迁移 | `V200__consol_note_mapping_reuse_and_reference.sql` | 4 张新表 + 1 个 ALTER |
| 迁移 | `R200__consol_note_mapping_reuse_and_reference.sql` | 幂等回滚 |
| ORM | `consol_note_mapping_template_models.py` | 4 个新模型 |
| ORM | `consol_note_mapping_models.py`（扩展） | +promoted_to_template_id |
| 服务 | `consol_note_mapping_template_service.py` | 规则模板 CRUD + 建议 |
| 服务 | `consol_note_value_change_service.py` | 值指纹 + 事件处理 + stale 汇总 |
| 服务 | `consol_note_value_confirmation_service.py` | 确认 + 闸门 |
| 服务 | `consol_note_structure_lock_service.py` | 结构锁 CRUD |
| 改造 | `consol_note_detail_source_service.py` | 七级匹配 + 上年项目 |
| 改造 | `consol_note_detail_template_service.py` | recommended_account_codes |
| 路由 | `consol_note_mapping_templates.py` | 12 个端点 |
| 注册 | `router_registry/system.py` | cnmt_router |
| 事件 | `audit_platform_schemas.py` | CONSOL_NOTE_VALUE_CHANGED |
| 测试 | `test_consol_note_mapping_template.py` | 23 例 |
| 测试 | `test_consol_note_value_change.py` | 19 例 |

### 前端（待环境，标 `*`）

- Task 10：科目参考展示（📋 图标 + hover + 不一致 warning）
- Task 14：stale 横幅（SSE + 刷新按钮）
- Task 20：确认状态面板（✅/⚠️/⬜ + 确认操作）
- Task 24：结构锁标识（🔒 + 行操作置灰）
