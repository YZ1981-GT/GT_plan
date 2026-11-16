# 设计：批量建项与合并企业树导入收口

## 1. 目标、复用边界与取舍

现有 `batch_project_service.py` 已超过 800 行，本次不继续堆叠。保留其公开兼容函数，新增模块承载模板协议、持久计划和执行编排：

- `batch_project_workbook.py`：列协议、模板、受限 XLSX 解析、错误工作簿。
- `batch_project_plan.py`：规范行、DB 预取、动作分类、库存覆盖预览、请求摘要。
- `batch_project_execution.py`：计划持久化、幂等、锁/CAS、创建/更新/成员/链接编排。
- `batch_project_service.py`：向后兼容转发和旧 service API。

`group_forest` / `consol_group_tree` 继续是树算法真源，`project_wizard_service` 继续是单项目字段校验真源，`group_links.apply_group_values` 与 counterpart 规则继续是集团字段写入真源。不得在前端重建树或在批量模块复制关系算法。

### 1.1 关键取舍

| 议题 | 采用 | 不采用 |
|---|---|---|
| 计划真源 | PostgreSQL 持久计划，JSONB 保存规范行和回执 | 进程内 map、仅 Redis、把 500 行塞进签名 token |
| 执行语义 | 预校验后整批原子 | 行异常后全局 rollback 再继续；默认静默部分成功 |
| 上传次数 | 上传一次，确认只发 plan id + idempotency key | 同一文件二次上传与二次解析 |
| 更新范围 | 仅三码关系字段，基线摘要 CAS | 通过 Excel 批量覆盖任意项目基本信息 |
| 合并导出 | 服务端从根项目推导成员 | 客户端提交“我认为属于这棵树”的 ID 清单 |
| 性能 | 500 行同步、批量预取、一次 flush/commit | 未量化即上后台队列或新增依赖 |
| 用户成员 | manager 创建者挂经理；admin/partner 仍按显式模板字段 | 给 admin/partner 伪造经理委派 |

## 2. 数据模型与迁移

新增 `ProjectBatchImportPlan`（独立模型文件，避免继续扩大 `core.py`）：

- `id UUID` 主键；`actor_user_id` FK users。
- `mode`：project/consolidation；`status`：validated/applying/applied/failed/expired。
- `file_name`、`file_sha256`、`template_version`、`request_hash`、`idempotency_key`。
- `rows JSONB`：规范行、Excel 行号、动作、目标项目、目标基线摘要。
- `tree_preview JSONB`、`summary JSONB`、`warnings JSONB`、`receipt JSONB`、`public_error`。
- `expires_at/applied_at/created_at/updated_at`。
- unique `(actor_user_id,idempotency_key)`，幂等键非空时生效；状态与 mode CHECK；按 actor/status/expiry 建索引。

V/R 迁移动态使用当前最高版本之后的编号。V 使用 `IF NOT EXISTS`，但同名对象结构不一致须 fail-closed；R 仅删除本次对象。ORM、迁移和 service 三层逐字段一致。

计划有效期默认 30 分钟。规范行不保存原始文件字节；错误工作簿由规范行和错误生成。过期计划可读回摘要但不能执行。

## 3. Excel 协议

### 3.1 列

前 10 列保持兼容：客户名称、USCC、简称、年度、项目类型、准则、报表类型、parent、ultimate、relation。

追加三列：

1. `操作类型(action)`：新建/更新集团关系/跳过；空值按有无项目 ID 推导。
2. `项目ID(project_id)`：现有项目导出时填写，新建行留空。
3. `关系基线摘要(base_hash)`：服务端导出，更新时用于识别导出后的关系变化。

旧 9/10 列可导入，返回“旧模板，建议下载新版”的 warning。新版通过隐藏 `_GT_META` sheet 保存版本、生成时间、mode 和可选 root id；用户可见表头仍是权威，不依赖公式缓存。

### 3.2 模板与解析

“数据”sheet 只有表头和空白输入行；四行示例放“填写示例”sheet。枚举选项放隐藏 `_GT_OPTIONS` sheet，以命名区域给 D/E/F/J/K 列下拉。表头冻结、筛选、必填色和批注统一生成。

上传边界：路由流式读取至固定上限；检查 ZIP/XLSX 签名、压缩成员数和解压后总大小；工作簿最多 501 个数据行、13 列。解析通过 `anyio.to_thread.run_sync` 执行。新版表头必须逐列相同；旧模板按已登记前缀兼容，不回退到任意 active sheet。

年度解析只接受 int、形如 `2025` 的字符串或值等于整数的 Excel 数字；`2025.1` 拒绝。

## 4. 两阶段 API

- `GET /api/projects/batch-template?mode=project|consolidation`
- `POST /api/projects/batch-validate?mode=...`：multipart 文件 + 可选批次默认值，创建 validated 计划。
- `POST /api/projects/batch-apply`：JSON `{validation_id,idempotency_key}`，执行或重放。
- `GET /api/projects/batch-imports/{validation_id}`：返回本人计划状态/原回执。
- `POST /api/projects/batch-export`：保留选中项目导出，先做全集合 readonly 鉴权。
- `GET /api/projects/{project_id}/group-import-template`：从合并根导出树内项目。
- `GET /api/projects/batch-imports/{validation_id}/errors.xlsx`：下载错误行与原因。

旧 `POST /batch-import` 保留兼容：先做完整 DB 感知校验，格式/业务错误行跳过，写入行各用 SAVEPOINT，保证部分成功回执与真实落库一致；生产前端只走 validate/apply 的整批原子路径。
## 5. 预校验与动作规划

1. 解析和规范化全部非空行；同批重复键为 `(company_code,audit_year,report_scope)`。
2. 一条查询取全部同键现有项目，一条查询取 parent/ultimate 涉及的同年度项目；不逐行查唯一性。
3. 行动作：
   - 无 project_id 且键不存在：create。
   - 无 project_id 且键已存在：unchanged/skip，并明确显示“系统已存在”；不能伪装成成功创建。
   - 有 project_id、action=更新集团关系：目标必须与导出身份、代码、年度、口径一致，只比较集团字段。
   - action=跳过：skip。
   - 其他冲突：error。
4. 对更新目标逐项目检查 edit；导出和查看计划检查 readonly。全局创建动作只允许 admin/partner/manager。
5. 以库存项目为底，将 create/update 投影为轻量 Project-like 覆盖层，再调用 `build_forest`。循环诊断、重复项目、缺失更新目标和构树异常进入 blocking errors。
6. 自动根计划按 `(ultimate,year)` 生成，明确进入 summary 和预览；已有根只复用。自动根属性优先取同组显式 consolidated 行，其次取组内共同准则/类型；冲突要求用户补显式根。
7. 对每个 update 保存目标集团字段规范 JSON 的 SHA-256。apply 时 `SELECT ... FOR UPDATE` 后重算，变化即 409 stale。

`request_hash` 对 `{mode, defaults, canonical rows}` 采用 UTF-8、排序键、紧凑 JSON SHA-256，不含文件名和生成时间。

## 6. 原子执行

路由先原子领取计划：同 actor、validated、未过期才能切 applying；applied 返回原 receipt，applying 返回 409“正在执行”。领取和业务执行使用同一事务，失败回滚后以独立短事务把计划记 failed；业务项目、成员和关系全部为零部分写。

创建阶段不再先调用一次 `check_uniqueness` 再让 `create_project` 重查。新增受控内部入口接收已锁定/已批量验证标志，但仍执行 Pydantic、USCC、集团字段规范化，并依赖数据库唯一索引兜底。所有 Project 先 add，统一 flush。

manager 操作者在任何业务写前解析唯一 active staff。每个新建普通项目和新建自动根调用 `AssignmentService.save_assignments` 写经理委派；复用根不碰团队。若 500 行实测被逐项目通知拖慢，再在 AssignmentService 内新增等价批量入口，不在批量模块手写 ProjectUser。

更新阶段调用扩展后的集团关系服务：显式接受 parent、ultimate、relation，写单户/合并 counterpart，支持 `sync_links=False`。全部动作结束后按年度各调用一次 `sync_group_links`。审计日志在 SAVEPOINT 内批量写；主业务失败必须回滚，审计失败按现有策略留 warning。

成功回执写入计划并与业务事务同 commit。客户端响应丢失后 GET 或重复 apply 读取同一 receipt。

## 7. 权限

- template/validate/apply/legacy import：`require_role([admin,partner,manager])`。
- 计划状态和错误文件：仅 actor；admin 不越过计划归属，避免读取上传数据。
- 选中项目导出：输入集合去重、空集合 422、全部存在且 readable；一项无权整体 403。
- 合并树导出：根项目 readonly，且必须为 consolidated；遍历得到的每个项目再次验证可读，不泄露隐藏成员。
- 更新关系：每个目标和 counterpart 必须 edit；归档项目沿用 423。

普通单项目创建权限超出本 spec，不顺手收紧；本次只保证两个批量入口一致。

## 8. 前端

`BatchImportDialog` 新增：

```ts
mode?: 'project' | 'consolidation'
rootProjectId?: string | null
```

默认 project，保持 Projects/MiddleProjectList 无改动；ConsolidationHub 传 consolidation。合并模式显示“导出当前集团树”，仅在选定根时启用；未选根时仍可下载新建模板。

弹窗改 `80vh` flex：header 与 footer 固定，中间滚动。步骤为“取得模板 → 上传校验 → 确认执行 → 查看结果”。树按 `default-expanded-keys` 只开前两层，异常/改动节点带标签；顶部 summary 卡片固定。

校验后保存 validation_id；apply 发送 UUID 幂等键。网络异常先 GET 状态；applied 显示原回执，validated 可重试，applying 短轮询。未成功不清文件和预览。成功发出 `{receipt}`，调用方同时刷新列表和树；合并入口可跳转首个 created/auto root。

错误统一从平台响应信封提取中文 `detail/message`，请求带 `_silent` 防止全局拦截器重复 toast。错误 Excel 用 `downloadFile`。

## 9. 验证与降级

- SQLite：解析、模板、动作分类、原子失败、幂等回执、成员与多年度根。
- PostgreSQL：迁移/R、唯一并发、计划领取、JSONB/CAS、全事务回滚。
- TestClient：角色矩阵、混合授权 ID、计划归属、归档项目、响应信封。
- 前端：project/consolidation 两模式、上传一次、固定 footer、错误保留、结果恢复。
- Playwright：【测试】集团导出 → 改 parent → validate diff → apply → 刷新树 → 再导入幂等；最后恢复原关系并删除新建测试项目。
- 性能：固定 500 行，记录 parse/plan/apply/refresh 分段；若 AssignmentService 是主要瓶颈，保留正确实现并如实登记下一步，不绕过成员链。

降级：数据库迁移尚未应用时新端点返回中文 503，旧模板下载仍可用；不得退回进程内计划或重新启用二次上传。