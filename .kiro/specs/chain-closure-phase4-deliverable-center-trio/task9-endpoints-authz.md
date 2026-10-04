# Task 9：readiness / 生成 / 重试 / 下载端点与权限

状态：**已通过 SQLite + TestClient 真请求**（含三组变异证明 red→green）。真 PG / Playwright 属 Task 13/15。

需求：1.6, 3.5, 5.1, 5.6, 7.4

## 一、设计决策：新建专用 trio 路由，不改既有 word_export 端点

design §4.4 要求正式三件套的 HTTP 边界带**项目级**鉴权（readiness/状态/下载=readonly，
生成/重试=edit）。既有 `word_export.py` 的 `/full-deliverables`、`/jobs/{job_id}`、
`/jobs/{job_id}/retry`、`/{task_id}/download` 仅 `Depends(get_current_user)`（只验登录，
无项目级隔离）。

两种做法权衡：

- **A（否决）**：在 `word_export.py` 原地把 `get_current_user` 换成 `require_project_access`。
  风险：这些端点有既有前端调用方，直接收紧权限可能打断在用流程；且「对齐」动作本身
  不干净（铁律㉗①：不以「对齐既有端点」正当化缺陷，更不应反向把既有端点连带改坏）。
- **B（采纳）**：新建专用路由 `backend/app/routers/deliverable_trio.py`，前缀
  `/api/projects/{project_id}/deliverables/trio`，每个端点从一开始就带正确的
  `require_project_access`。既有 word_export 登录态端点原样保留（兼容），正式 trio 走新端点。

采纳 B。清晰的项目级鉴权 + 不破坏既有调用方。

## 二、交付内容

| 文件 | 改动 |
|---|---|
| `backend/app/routers/deliverable_trio.py` | 新建；6 个端点（见下） |
| `backend/app/router_registry/report.py` | 注册 `deliverable_trio_router`（FastAPI 不热加载 router，必须显式注册） |
| `backend/app/services/export_job_service.py` | 新增 `get_job_item(item_id)`（下载端点按主键取 item，再经 job 校验归属） |
| `backend/tests/test_phase4_trio_endpoints_authz.py` | 新建；15 个 TestClient 真请求测试 + AST 变异守卫 |

### 端点清单

| 方法 路径（省略前缀） | 权限 | 边界 |
|---|---|---|
| `GET /readiness?year=` | readonly | 只读；blocked 返回中文阻断项（需求 1.6），不 200+空文件 |
| `POST ` (= `/trio`) | **edit** | 先 readiness 复查，blocked→409；ready 才 `executor.run` + **router commit** |
| `GET /jobs/{job_id}` | readonly | `job.project_id==project_id` 校验，错项目 403 |
| `GET /jobs/{job_id}/attempts` | readonly | append-only 历史；错项目 403 |
| `POST /jobs/{job_id}/retry` | **edit** | 属主校验；`SnapshotMismatchError`→409（需求 5.1/5.5）；**router commit** |
| `GET /items/{item_id}/download` | readonly | item→job 属主校验 + 下载前 `verify_file_fingerprint`（需求 3.5） |

### 关键实现约束

- **铁律㉗（路径参数 ≠ 隔离）**：`ExportJob` 带 `project_id`，`ExportJobItem` 不带 →
  job 端点按 `job.project_id` 真比对；download 先 `get_job_item` 再 `get_job(item.job_id)`
  比对 `job.project_id`。路径里的 `project_id` 只用于鉴权依赖，归属靠数据层查询。
- **403 零写入**：写端点 `db` 走 `Depends(get_db)`，`current_user` 走
  `Depends(require_project_access("edit"))`；鉴权在依赖解析阶段失败即 403，端点体不执行，
  `commit` 只在业务成功后由 router 调用。测试断言 403 后 `ExportJob` 计数为 0。
- **service 只 flush / router commit**：`create_trio` 与 `retry_trio_job` 由 router 统一
  `commit`；readiness / 状态 / 下载只读不 commit。
- **下载 fail-closed**：`verify_file_fingerprint` 失败时 `missing_file`→404、其余（空文件 /
  哈希不符 / 路径逃逸）→409，均**不**返回文件。

## 三、测试与变异证明

### 修复后绿（15 passed）

```
tests/test_phase4_trio_endpoints_authz.py ...............  [15 passed]
```

覆盖：readiness ready/blocked/非成员403/只读放行；创建 403 零写入 + 非成员 403；
job 属主错项目 403 / 同项目 200；重试快照冲突 409 / 只读成员 403；
下载 缺失文件 404 / 篡改哈希 409 / 合法文件 200 流式 / 错项目 403 / 非成员 403；
AST 守卫断言 6 个端点真的声明 `require_project_access` 且 level 符合读写语义。

同批回归（无本阶段引入红）：`test_phase4_readiness_gates` + `test_phase4_trio_retry_reexecute`
+ `test_phase4_trio_attempt_history` → **47 passed**。

### 变异证明（去鉴权 / 错项目 / 跳过指纹 必须红）

鉴权测试用**真 SQLite + 真 `ProjectUser` 行**，override 的是内层 `get_db`/`get_current_user`，
让真实 `assert_project_permission` 跑起来（铁律㉕：直接 override 依赖工厂会静默失效全 401）。

| 变异 | 期望 | 实测（red） |
|---|---|---|
| readiness 的 `require_project_access("readonly")` 改回 `get_current_user`（只验登录） | 非成员应 403 | `test_readiness_non_member_403`：`assert 200 == 403` 失败；AST 守卫 `get_trio_readiness 未声明 require_project_access 依赖` 失败 |
| job / download 的 `job.project_id != project_id` 归属校验短路为恒假 | 跨项目应 403 | `test_get_job_wrong_project_403` 与 `test_download_wrong_project_403`：`assert 200 == 403` 失败 |
| download 跳过 `verify_file_fingerprint` | 篡改应 409、缺失应 404 | 篡改文件 `assert 200 == 409` 失败；缺失文件 starlette `RuntimeError: File ... does not exist`（即「返回缺失文件冒充交付」的真实故障） |

三组变异全部确认 red，随后逐一还原，复跑 15 passed。

### 铁律㉖（AST 而非文本匹配）

`test_all_trio_endpoints_declare_project_authz` 用 `ast.parse` 解析端点函数参数默认值里
`Depends(require_project_access("<level>"))` 的 Call 节点，读出每个端点真实声明的权限级别。
docstring 里写「权限：readonly」不产生 Call 节点 → 天然排除，不会被注释骗过。谁删掉或改弱
某端点的鉴权依赖，该断言立即变红。

## 四、未覆盖 / 后续

- 真 PG 临时 schema（迁移/约束/锁/行级）→ Task 13。
- Playwright 一键出具/下载失败中文提示 → Task 15（写库需用户授权）。
- `create_trio` 的「ready→真实执行 executor.run 落三文件」在 SQLite 下依赖导出器与
  模板，本任务只验鉴权/readiness门/commit边界与 403 零写入；完整三件套生成的真实落盘链
  由 Task 12（SQLite 全链回归）与 Task 13（PG）覆盖。
