---
inclusion: manual
---

# 编码与 UI 规范

需要了解项目编码规范、UI 偏好、命名约定时用 `#conventions` 引用此文件。

## UI 视觉规范（致同品牌）

- 主色 #4b2d77（紫色），设计 Token 在 gt-design-tokens.css
- 样式层级：gt-tokens → global.css → gt-page-components.css → gt-polish.css
- 按钮圆角 8px，表格行间距 10px，边框 0.5px 半透明
- 进度条流动光泽动画，标签降低饱和度
- 页面切换 Transition 过渡动画（gt-page mode=out-in）
- 页面横幅统一紫色渐变（网格纹理+径向光晕）
- 按钮三种模式：实心渐变+白字、plain 浅色+深色字、text 透明+纯文字
- 弹窗遮罩：半透明白色 rgba(255,255,255,0.6) + backdrop-filter: blur(2px)
- el-dialog 必须加 append-to-body（三栏布局 overflow:hidden 会截断）
- 输入框 focus：只保留 1px 浅紫色边框，去掉双层阴影和浏览器 outline
- 危险操作按钮用 text 模式纯文字，删除图标默认灰色 hover 变红
- 全局字号 15px（--gt-font-size-base）

## 表格规范

- 所有 el-table 必须 border + resizable（支持拖拽列宽）
- 报表表头冻结：el-table 用 max-height，矩阵表格用 thead sticky
- 行高约 0.7cm（26px），单元格 padding 2px 6px，字号 12px
- 选中行浅蓝 #e8f4fd，hover 行 #f5f8fc
- 金额单位：数据库以"元"存储，前端 displayPrefs Store 控制显示（元/万元/千元），顶栏"Aa"面板切换
- 金额格式化：统一用 formatters.ts 的 fmtAmount/fmtAmountUnit，禁止各组件自定义 fmt 函数
- 条件格式：负数红色(.gt-amount--negative) + 变动超阈值黄色(.gt-amount--highlight)，displayPrefs.amountClass() 返回 CSS 类
- 表格字号：通过 `:style="{ fontSize: displayPrefs.fontConfig.tableFont }"` 绑定，4档预设（11/12/13/14px）
- 单元格选中样式：统一使用 CellContextMenu.vue 全局 gt-ucell--selected（淡紫色半透明背景+边缘边框），禁止各模块自定义 scoped 选中样式
- 单选时加 gt-ucell--single-selected（outline + 右下角填充柄小方块，Excel 风格）
- 拖拽框选：setupTableDrag(tableRef, getCellVal) 一行代码启用，拖拽期间 body 加 .gt-dragging 禁止文本选中
- 复制按钮命名：工具栏"复制整表"（复制整个表格）vs 右键菜单"复制选中区域(N格)"/"复制值"（复制选中单元格）
- 搜索栏位置：必须在表格上方（横幅/提示区下方），致同品牌紫色渐变背景
- Ctrl+F：各组件内 document.addEventListener('keydown') + e.preventDefault() 拦截浏览器默认搜索
- 项目列建议 fixed，金额列建议 sortable

## 附注编辑器规范

- 目录树 indent 10px，子节点 padding 2px
- 章节标题不显示序号前缀（只显示科目名称）
- 正文段落间距 10px、字号 13px、行高 1.8、首行缩进 2em
- 单元格三种模式：auto（自动提数）→ manual（手动编辑）→ locked（锁定）
- TipTap 富文本编辑器用于叙述文字区域
- 空表格处理：只有"报表项目主要注释"（第五章/第八章）下的科目表格需要数据行和合计行；会计政策/关联交易/前期差错等章节的表格是描述型，不需要填充数据行

## 报表规范

- 横幅必须显示：单位名称 + 年度 + 模板类型（国企/上市）+ 口径（合并/单体），全部下拉可切换
- 审核按钮只执行 logic_check + reasonability 公式（auto_calc 不参与）
- 报表行次严格参照致同 Excel 模板，不能自己编造
- 无数据时显示预设模板结构（行次+项目名称），金额列为空

## 后端编码规范

- asyncpg 时区规则：所有与 PG TIMESTAMP WITHOUT TIME ZONE 列比较的 datetime 必须用 `datetime.utcnow()`（naive），不能用 `datetime.now(timezone.utc)`（aware）
- UTF-8 BOM 防御：读取 JSON/HTML 文件统一用 `utf-8-sig` 编码
- SoftDeleteMixin：所有软删除调用 `soft_delete()` 方法
- 路由认证：所有端点必须有 `Depends(get_current_user)` 或 `require_project_access`
- 事件发布用 `asyncio.create_task`（非阻塞），失败只记日志不阻断
- LLM 调用统一 temperature=0.3 + max_tokens=2000 + 超时 30s + 失败不阻断手动操作
- consolidation_models server_default：PG 枚举列用 `server_default="xxx"` 纯字符串

## 前端编码规范

- 禁止直接 import http 拼 URL，必须通过 apiProxy.ts 或 commonApi.ts
- 数据解包：http.ts 响应拦截器已自动解包 ApiResponse，前端用 `const { data } = await http.get(url)`
- SSE 统一封装：sse.ts（createSSE 自动重连 + fetchSSE 流式 POST）
- tsconfig 不支持 Map 迭代，用 Record 代替
- 大文件上传用原生 fetch 绕过 http.ts 拦截器（去重/重试/解包冲突）
- webkitdirectory 上传文件名含路径，后端用 `Path(file.filename).name` 只取纯文件名

## Word 导出排版规范

- 字体：仿宋_GB2312 + Arial Narrow（数字）
- 页边距：3/3.18/3.2/2.54cm
- 表格：上下 1 磅边框无左右（三线表）
- 高风险标红，页脚页码
- 千分位格式，0 显示 '-'

## 命名约定

- 路由路径：新代码统一用 working-papers（带连字符），旧代码 workpapers 保持不变（breaking change 不改）
- 报表标准：applicable_standard = soe_consolidated / soe_standalone / listed_consolidated / listed_standalone
- 底稿编码体系：B(风险评估)/C(控制测试)/D-N(实质性程序)/A(完成阶段)/S(特定项目)
- 附注章节编号：国企版 14 章（一~十四），上市版 17 章（一~十七）

## 用户交互偏好

- 删除操作必须 ElMessageBox 二次确认
- 空状态：全宽简洁（图标+一句话+一个按钮），不要啰嗦步骤说明
- 项目子页面返回按钮跳转 /projects（不是首页 /）
- 导航按角色裁剪（审计员 6 项，管理层多看看板/委派，admin 额外看用户管理）
- 空壳页面（<50 行）标记 developing 灰色不可点击
- 功能收敛：停止加新功能，核心 6-8 个页面做到极致


## 后端踩坑与规范（2026-05-10 补充）

### uvicorn --reload 本机实测不生效（2026-07-30）

9980 端口上同时跑着 `.venv\Scripts\python.exe` 与系统 `Python312\python.exe` 两个 uvicorn
（均带 `--reload --reload-dir app`）。实测改 `app/routers/*.py`、新增 `app/services/*.py`
后端点**仍返回旧代码结果**，`os.utime` 触摸文件也无效。需要 live 验证后端改动时**先重启后端**。

配套坑：**空结果可能是 token 过期的 401 假阴性** —— 浏览器里用 `fetch` + `?.` 链式取值会把
`{"code":401}` 吞成 `[]`，看起来像"我的代码把数据搞没了"。判定前必须先看 HTTP status。

### get_note_detail 投影块内禁止从 ORM 对象取属性

`getattr(note, "source_template")` 在异步会话下可能触发 `MissingGreenlet`，
而该块外层是 `except Exception` 兜底 → 异常被吞掉后**连 `_tables` 都不会被赋值**，
表现为「附注表格全部消失」。一律用已 `model_validate` 的 `detail` 取值。

### 附注 `guidance` 只在 seed 路径生效 → 需读时回填

`tables[].guidance`（附注 TAB 编制提示）只经 `disclosure_engine._carry_seed_table_guidance`
在生成时写入。`_source=workpaper` 的记录读取时走 `note_sub_table_projector.project_sub_tables`
投影，投影只认推来的 `sub_table_data` + `_sub_table_columns`，**模板 guidance 完全不参与**
（同步载荷里也没有 guidance，它是模板侧指引而非业务数据）→ 项目一旦点过「同步到附注」，
TAB 提示就永久变空。解法 = `backend/app/services/note_table_guidance.py` 读时按
`(source_template, section_number, 表名)` 回填：不写库、表名对不上就跳过、已有非空不覆盖，
因此零回归（此前是空，最坏还是空）。已接在 `get_note_detail` 投影之后。

### uvicorn --reload 路由树不可变限制

给已注册 router 追加新 `@router.get(...)` 端点后，`--reload` 只能重新 import 代码，无法重建 FastAPI app 的路由树，新端点访问返回 404。修复必须整进程重启（Ctrl+C + 重跑 start-dev.bat）。反之对现有端点函数体的改动 --reload 可以正常热加载。

### uvicorn --reload 僵尸端口

reloader 进程崩溃/中断后，LISTEN 在 9980 的子进程 PID 在 `Get-Process` / `tasklist` 都查不到但 `Get-NetTCPConnection` 仍显示 LISTEN。无法通过 Stop-Process 杀掉，必须在 start-dev.bat 的 cmd 窗口 Ctrl+C 或整窗口关闭重开。

### 重复 activate 导致数据叠加

同一 `project_id + year` 多次导入**不会覆盖**，而是每次创建新 dataset 并 activate，旧 dataset 只标 `superseded` 但数据行仍 `is_deleted=false`。结果 tb_balance COUNT = 单次导入行数 × N。验证数据正确性前必须先清理所有历史 dataset（DELETE ledger_datasets 级联）。

### 清理项目账表数据的 SQL 外键顺序

```sql
-- 1. 先取消活跃 jobs（job_status_enum 值单 L: canceled，非 cancelled）
UPDATE import_jobs SET status = 'canceled'
  WHERE project_id = :pid
    AND status IN ('queued','running','validating','writing','activating','pending');

-- 2. 四表数据（无外键约束直接删）
DELETE FROM tb_balance      WHERE project_id = :pid AND year = :yr;
DELETE FROM tb_aux_balance  WHERE project_id = :pid AND year = :yr;
DELETE FROM tb_ledger       WHERE project_id = :pid AND year = :yr;
DELETE FROM tb_aux_ledger   WHERE project_id = :pid AND year = :yr;

-- 3. activation_records → ledger_datasets（外键顺序）
DELETE FROM activation_records
  WHERE dataset_id IN (SELECT id FROM ledger_datasets WHERE project_id = :pid AND year = :yr);
DELETE FROM ledger_datasets WHERE project_id = :pid AND year = :yr;
```

### 测试 fake user role 必须是 `.value` 对象

`backend/app/deps.py:161` 的 `require_project_access` 用 `current_user.role.value == "admin"` 做权限判断，测试里 `override_get_current_user` 的 fake user **不能**直接写 `role = "admin"` 字符串，会报 `'str' object has no attribute 'value'`。

正确模式：
```python
class _FakeUser:
    id = FAKE_USER_ID
    class _Role:
        value = "admin"
    role = _Role()
```

## 前端踩坑与规范（2026-05-10 补充）

### el-table 树形（多层嵌套）最佳实践

三层渲染（父 > 分组 > 明细）关键点：
- `row-key` 用独立 `_rowKey` 字段，分段式：`acc:${company}:${code}` / `acc:...:grp:${type}` / `acc:...:grp:...:aux:${aux_code}`
- `:tree-props="{ children: 'children', hasChildren: 'has_children' }"` 后端必须同时返回 `children` 数组和 `has_children` 布尔
- 每个节点用 `_nodeType` 字段区分类型（`'account' | 'group' | 'aux'`）
- 展开全部需要**递归**：`toggleRowExpansion(row, true)` + 遍历 children 再调自己，否则只展开第一层
- 多层过滤：parent 命中保留整组，任一 group.aux_type 或 child.aux_code/name 命中也要保留父节点
- 行样式：通过 row-class-name 返回 `_nodeType` 对应 CSS class

### PowerShell 批量修改中文文件铁律

**禁止**用 PowerShell 的 `Get-Content -Raw | -replace | Set-Content` 对含中文的文件做批量修改——默认用 UTF-16 解码 UTF-8 3 字节中文会截断成 2 字节（第 3 字节被吞），产生 `\xef\xbf\xbd` replacement char。

正确做法：**必须用 Python `open(path, 'rb')` 字节级读写**，`content.replace(b'old', b'new')`；或用 IDE 的 strReplace 工具。


## UX 异步流程五铁律（2026-05-10 Sprint 8 UX 精修 v2 沉淀）

### 1. 异常状态检测 ≠ 强制跳转

用户点击入口打开对话框时若检测到后端异常状态（如已有进行中的作业），**不要自动切换视图打断用户**。正确做法：弹 `ElMessageBox` 三选一给用户选择权：
- 查看进度 / 继续原操作
- 取消旧作业并新建
- 稍后（什么都不做）

### 2. 顶栏跳转 vs 用户主动开——两个入口要区分

同一个对话框可能从两个路径打开，处理逻辑不同：
- **顶栏跳转回来**：用户目的明确是"看进度"→ 静默恢复，不弹框
- **主动点入口**：用户想开新流程 → 需弹框提示已有作业

实现：入口函数加 `{ autoRecoverActiveJob?: boolean }` 参数，分别走 `recoverActiveImportJobSilent` / `checkActiveJobBeforeUpload`。

### 3. dialog 关闭流程统一

处于"进行中"状态时（如 importing step）**不应禁用 × 和 Esc**——用户找不到关闭入口会很焦虑。
正确做法：
- 放开 `show-close` / `close-on-press-escape`
- 加 `:before-close` 钩子识别状态，importing 时关闭 = "放后台继续"（走相同 toast + 保留 jobId 逻辑）

### 4. 异步弹窗时序

dialog 关闭动画（~300ms）期间**不要立即弹另一个 MessageBox**，两个 dialog DOM 叠加视觉不佳。
使用 `setTimeout(() => ElMessageBox.confirm(...), 300)` 延迟等动画完成。

### 5. canceled ≠ failed（后端异常处理）

Worker 层 `except Exception as exc` 捕获到 `ImportJobCanceled`（继承自 RuntimeError）也算异常。必须：
```python
is_canceled = isinstance(exc, ImportJobCanceled)
if is_canceled:
    error_msg = "导入已取消"
    target_status = JobStatus.canceled
else:
    error_msg = _humanize_import_error(exc)
    target_status = JobStatus.failed
```
transition 到对应状态；不能一刀切 failed。

这五条适用于所有"长流程 + 可后台继续"的 UX（导入/导出/PDF 生成/批量操作等）。


## 修复必须实测验收（2026-05-10 用户规约）

用户明确要求：**修复后必须亲自测试验收，不能改错了或改了没效果**。

### 适用场景强制要求

| 修改类型 | 最低验收要求 |
|---------|------------|
| 错误映射 / 类型判断函数（如 `_humanize_import_error`）| 新增/更新 unit test 覆盖所有分支，必须实际跑 `pytest` |
| 新建 HTTP 端点 / 修改现有端点 | 实际 curl 或跑对应 test_client 测试，不能只看代码 |
| 引用外部模型字段（ORM / TypedDict / API schema）| grep 确认字段名+类型，不能凭印象；尽量加 fixture 构造测试 |
| 多个 router 挂载同一 URL 路径 | grep 同路径所有实现，确认哪个先注册拦截；必要时删死代码 |
| 新增 TypeScript 类型断言或 cast | 跑 vue-tsc 验证；类型塌陷（如交叉类型变 never）必须用 any 断言 + 注释说明 |
| 任何 async 流程的 try/except/finally 分支 | 构造真实异常跑一次，验证错误路径被正确捕获 |

### 本轮实战踩过的 5 个静态 review 漏洞

1. `msg.lower().contains('ForeignKeyViolation')` 对 asyncpg 异常失效——类名不在 msg 里
2. 凭印象写 `job.upload_token` 实际字段不存在
3. 两个 router 挂同 URL，先注册的拦截导致后者变死代码
4. `ImportArtifact(manifest={})` 字段名错，实际是 `file_manifest`
5. Element Plus MessageBoxData 交叉类型 TS 塌陷为 `never`

### 推荐工作流

```
1. 修改代码 → 2. grep 相关字段/类名 → 3. getDiagnostics 看 TS/Python 编译
4. 构造 1-2 个关键场景手动测（python -c / curl）→ 5. 加对应 unit/integration 测试
6. 跑全量回归（pytest + vue-tsc） → 7. 真实数据 smoke（e2e_yg4001_smoke.py 或相当）
```
第 4-7 步任一步失败都算修复未完成。


## 账表四表查询规约（B' 视图重构，2026-05-10）

**参考**：ADR-002、`backend/app/services/dataset_query.py`

### 强制规则
1. **Tb* 四表查询必须走 `get_active_filter`**（TbBalance/TbLedger/TbAuxBalance/TbAuxLedger）
2. **禁止直接写 `TbX.is_deleted == False`**（或 `sa.false()`）—— CI `backend-lint` job 卡点防回归
3. **raw SQL 禁止 `WHERE is_deleted = false`**，改为 `EXISTS (SELECT 1 FROM ledger_datasets d WHERE d.id = tb_x.dataset_id AND d.status = 'active')`

### 标准用法
```python
from app.services.dataset_query import get_active_filter

# 方法 A：where 条件列表
result = await db.execute(
    sa.select(TbLedger).where(
        await get_active_filter(db, TbLedger.__table__, project_id, year),
        TbLedger.account_code == code,  # 业务过滤
    )
)

# 方法 B：year 已知且复用多次 → 先查 active_id 再用同步版本
active_id = await DatasetService.get_active_dataset_id(db, project_id, year)
filter_expr = get_filter_with_dataset_id(TbLedger.__table__, project_id, year, active_id)
# 多次复用 filter_expr 避免 N+1
```

### year=None 场景（Template B）
```python
from app.models.dataset_models import LedgerDataset, DatasetStatus

active_ds_subq = (
    sa.select(LedgerDataset.id).where(
        LedgerDataset.project_id == project_id,
        LedgerDataset.status == DatasetStatus.active,
    )
)
conditions = [
    TbLedger.project_id == project_id,
    TbLedger.dataset_id.in_(active_ds_subq),
    TbLedger.is_deleted == sa.false(),  # 兜底保险
]
```

### 允许清单（year=None 兜底，CI baseline=6）
- `wp_chat_service.py:generate_ledger_analysis`
- `sampling_enhanced_service.py:analyze_aging`
- `report_trace_service.py:trace_section`
- `ocr_service_v2.py:match_with_ledger`
- `routers/report_trace.py:aux_summary`（2 处，aux_balance + balance）

### 写入规约
- pipeline 新写入统一 `is_deleted=False`（staged 隔离靠 `dataset.status=staged`）
- 回收站 / archive / restore 仍用 `is_deleted=true`（软删语义保留，独立于 B' 可见性）

### raw SQL 迁移模板
```sql
-- 改前
SELECT ... FROM tb_ledger
WHERE project_id = :pid AND year = :yr AND is_deleted = false

-- 改后
SELECT ... FROM tb_ledger l
WHERE l.project_id = :pid AND l.year = :yr
  AND EXISTS (
    SELECT 1 FROM ledger_datasets d
    WHERE d.id = l.dataset_id AND d.status = 'active'
  )
```

### 迁移脚本编号规则（V*.sql / R*.sql）

- 目录：`backend/migrations/`
- 前进脚本：`V{NNN}__{description}.sql`（如 V005__enable_rls.sql）
- 回滚脚本：`R{NNN}__{rollback_description}.sql`（如 R005__disable_rls.sql）
- 编号规则：**实施时动态确定 max+1**，禁止在 spec 起草阶段硬编码编号（因为并行 spec 可能冲突）
- 确定方法：`ls backend/migrations/V*.sql | sort | tail -1` 取最大编号 +1
- 每个 V*.sql 必须有配套 R*.sql 回滚脚本
- 回滚脚本必须使用 `IF EXISTS` / `DO $$` 块保证幂等性
- R001 是 no-op（基线回滚太危险，仅文档记录）
- 当前已落地：V001~V006 / R001~R006


## Spec 目标设定规约（2026-05-11 沉淀）

- 性能目标必须基于实测基线设定，不能凭直觉
- 设定前先跑一次真实样本拿基线数据（如 YG2101 128MB → pipeline ~660s）
- 目标分两层：架构收益目标（如 activate <1s）+ 端到端目标（如 total <Xs）
- 端到端目标受 IO/网络/PG 物理限制，不能无限压缩
- 目标超标时区分"架构问题"和"物理限制"：前者必须修，后者记录为已知限制
- 示例：YG2101 activate 从 127s→<1s 是架构收益；total 660s 是 PG COPY 物理限制（~5000 rows/s）


## Subagent 调用约束（spec 工作流，三轮复盘 2026-05-16 沉淀）

每次 invokeSubAgent 的 prompt 必须包含以下 5 类边界子句，避免 subagent 自作主张越权：

1. **范围锁定**：明确列出"本任务做什么"和"本任务不做什么"。如果发现 spec 范围扩张需求（如测试期望反推 production 加权限守卫），**只报告不实施**——由 orchestrator 决定是否在新任务里处理。

2. **Bug 处理边界**：如发现 production bug 阻碍当前任务推进：
   - **必须独立报告**（在返回值的 "production_bugs_found" 字段列出）
   - **不在当前 commit 修复**（避免 git log 看不到独立事件 + 测试改动与 bug 修复混淆）
   - 由 orchestrator 决定是否在新任务里修

3. **状态变更可审计**：TD 项 / UAT 状态 / spec 章节措辞变更必须附 commit-style note：日期 / 触发任务编号 / 测试结果摘要。禁止单方面声明"已重新完成"而无审计痕迹。

4. **实测 delta 验证**（V3 复盘 2026-05-28 沉淀）：批量治理任务必须前置 baseline grep + 后置实测验证：
   - 任务起始：跑 baseline grep（如 `grep "align=right" | wc -l = 109`）
   - 任务结束：再跑同 grep（如得 92），输出 "X→Y" 实数 + 用户阈值对照（"目标 ≤ X%"）
   - 禁止只汇报"已完成 N 视图"，必须给出**全局命中数变化**和**完成度百分比**
   - 反例：subagent 报"Top 3 视图已接入示范"但未提"baseline 109→92 仍距目标 60% 远"

5. **结构化返回**：禁止大段总结，强制返回 JSON-style 字段：
   ```
   {
     "files_created": [...],
     "files_modified": [...],
     "tests_run": "X passed / Y failed",
     "vue_tsc_status": "exit 0 / errors",
     "production_bugs_found": [...],   // 不修，仅列出
     "scope_expansion_requests": [...], // 测试中发现的 spec 扩张需求
     "td_status_changes": [...],       // 含 commit-style note
     "delta_measurements": {           // V3 沉淀新字段
       "baseline_metric": "align=right cols",
       "before": 109,
       "after": 92,
       "target": 22,
       "completion_ratio": "16%"
     }
   }
   ```

**反例**（template-library-coordination 三轮复盘踩坑）：
- subagent 给 `gt_coding.py` mutation 端点加 `require_role` 守卫（任务只要求"核实端点存在性"，是范围扩张）
- subagent 修复 `gt_coding_service.delete_custom_coding` 的 `soft_delete()` bug 与测试改动混在同一 commit
- subagent 划掉 tasks.md 的 TD 项 + 改 UAT-9 措辞，无审计痕迹

**反例**（V3 Sprint 4 12.4.1 console.log 治理）：
- subagent 报"Top 28 处已替换（8 文件）"，未提 ESLint 实际违规仅 3 处（"74 处"是 grep 总数包括合法 warn/error）
- 导致用户问"完成了吗"我答"渐进治理中"，实际严格违规已经 0 但 spec 标 [~]
- 用§4 实测 delta 验证可避免：subagent 必须给 `npx eslint --rule '{"no-console": "error"}' src/` 输出 = 0 violation

## PBT 反模式识别清单（三轮复盘 2026-05-16 沉淀）

很多 hypothesis 测试不是真 property-based，而是"参数化用例"。评审 PBT 时用 3 问清单：

1. **输入 strategy 是否故意包含违反约束的 case？** — 真 PBT 会 fuzz 出"非法输入"让 production 拒绝；反模式是 strategy 已强制满足约束，测试永真
2. **测试是否会因 production 代码修改而失败？** — 真 PBT 改算法会触发反例；反模式是 reimplement 算法 + 喂同一算法 + 断言一致（同义反复）
3. **算法实现和测试断言是否独立来源？** — 真 PBT 用独立简化版作 oracle；反模式是直接调 production 函数自己当 oracle

**已知反模式样本**（template-library-coordination）：
- `test_property_3_cycle_sort_order`：先 `sorted(groups, key=...)` 再断言已排序 — 永真命题
- `test_property_2_template_list_field_presence`：strategy 强制生成必有字段的 dict，测试不可能失败
- `test_property_5/12/13`：reimplement 算法 + 喂给同一算法 + 断言一致 — 同义反复

**PBT 分级 max_examples 规约**：
- P0 关键 Property（authz / readonly / 边界条件）：50-100
- 可选探索类：5（MVP 速度优先）
- 不允许 P0 关键 Property 用 `max_examples=5` 充数

## Spec 工作流规范（2026-05-18 从 memory 迁入精简版）

### Spec 三档分类
- **档 1 直接修**（不写 spec）：单文件/单端点/配置类，工时 ≤ 0.5 天
- **档 2 小型 spec**（仅 README）：根因不清晰/多文件协调，工时 0.5-2 天
- **档 3 完整三件套**（requirements + design + tasks）：跨视图/跨服务，工时 ≥ 1 周
- 判断铁律：spec 起草本身 ≥ 0.5 天 + 复盘 + 评审；范围清晰+单文件 → 不该走三件套

### Spec 起草铁律
- design.md 必须"代码锚定"：每个修改点列文件+行号/函数名，字段/枚举/端点 grep 核对
- tasks.md 只放编码任务；手动验证放 UAT 验收清单
- Sprint 粒度 ≤ 10 任务，强制回归测试+UAT 才进下一 Sprint
- 创建时强制"假设清单 grep 核验"5 项：ORM 字段 / seed JSON / 路由编号 / 前端文件 / DB 表列
- 创建阶段禁止动 production 代码（代码骨架放独立区块加注释"非实施"）
- tasks.md 末尾固定"已知缺口与技术债"章节（P0/P1/P2 + 触发条件 + 后续 spec）
- 三件套顶部各加 `## 变更记录` 表格（版本号+日期+摘要+触发原因）

### Spec 实施铁律
- 实施前预检：grep 所有目标文件核对是否已预先实施，已存在直接验证后标 [x]
- 标 [x] 前必须跑 pytest 验证（"代码文件存在" ≠ "功能可用"）
- 跨文件字段/枚举假设必须 grep 核对（凭印象写 = runtime 失败）
- 测试 fixture 复用邻居文件的 `db_session` 模板（conftest.py 不提供 db_session）

### Spec 三件套质量铁律（2026-05-28 V3 复盘沉淀）

**①「3 分钟可行性探测」铁律**：requirements.md 每条 Req 起草前必须做最小可行性证据，写到 design.md 对应章节。具体动作三选一：
- grep 实测命中数（如"console.log 74 处"实际 ESLint 违规仅 3 处，差 25 倍）
- 跑 5 行 SDK 原型（如 el-table-v2 是否原生支持行选择/列宽拖拽，结论：全部不支持）
- 读 1 段官方文档/类型定义（如 el-tag type='' 在 v2 已废弃必须 'primary'）
- 没探测就估工时 = 工时严重失真（实操中观察到 5x-25x 偏差）

**②「baseline 总数 vs 违规数」严格区分铁律**：requirements.md 实测基线必须区分两类数字，禁止混用：
- **总数**（grep 物理出现次数）：用于度量代码规模、覆盖面广度
- **违规数**（ESLint/ruff/policy 实际报错数）：用于度量治理目标
- 任务描述写"74 处 → 0"易引发"做了几十处都不到目标"的错觉，写"3 处违规 → 0"才是治理终点

**③「TS 类型预演」铁律**：design.md 涉及第三方 SDK / 跨组件 props 时必须写 5-10 行 TypeScript 类型签名片段，不能只写文字。本轮血泪：
- el-table-v2 `rowEventHandlers` 是对象不是函数（两种签名差异隐藏在 .d.ts 里）
- `sortBy` prop 类型用 string literal 'asc' 必须 cast 或 import enum
- `Array.at()` 需 ES2022 lib（tsconfig 升级才能用）
- 缺类型预演 = 实施时大量临时返工

**④「[~] 状态语义」严格铁律**：tasks.md 里禁止把"渐进治理"和"等真实环境"混用 `[~]`，必须语义化拆分：
- `[partial]` = 已落实主路径，剩缘 case（不阻塞父任务关闭计算）
- `[blocked-env]` = 等真实环境（playwright / dev server / 真合伙人，不阻塞 merge）
- `[ ]` = 真未做（阻塞父任务关闭）
- `[ ]*` = 可选（独立 Sprint 处理）
- 用户/Code Review 问"完成了吗"时，`[partial]` 答"主路径完成"、`[blocked-env]` 答"代码完成待真实环境"、`[ ]` 答"未做"，避免"完成了但又没完成"的模糊表述

**⑤「真环境 UAT 拆独立 spec」铁律**：起草阶段把这类任务反向决策：
- 静态可验证（vitest/pytest/grep/getDiagnostics） = 留在主 spec
- 必须 dev server 跑 = 拆 `{spec}-uat` 独立 spec（**不阻塞主 spec 关闭**）
- 必须真合伙人/真大数据 = 拆 `{spec}-acceptance` 独立 spec
- 否则父任务永远 `[ ]`，INDEX.md 视觉假象"主 spec 未完成"

**⑥「gaps.md 反向记录」铁律**：本轮多次"以为完成实际未完成"的根因 = memory.md 只记我做了什么，缺反向记录。每次 `[x]` 标记前必须问 3 个反向问题：
- 我跳过了什么 case？（如 12.4.1 跳过了 `console.warn/error` 治理）
- 我妥协了什么质量？（如 12.1 WorkpaperEditor 2625→2555 仅 -70 行，远未到目标 ≤1000）
- 我留了什么债？（如 14 个 vitest 失败转入下个 spec）
- 答案写入 spec 目录下 `gaps.md`（与 requirements.md 平级）；spec 关闭时 gaps.md 自然成为下个 spec 的 input

**⑦「CI 双卡点」立即兜底铁律**：本轮发现 vue-tsc 86 + vitest 14/29 都是长期未发现的债，根因 = CI 没卡点。立即必须建：
- frontend-ci: `npx vue-tsc --noEmit` errors > 0 → red
- frontend-ci: `npx vitest run` failed > 0 → red（不允许"基线已知失败"豁免，每个失败强制 .skip + GitHub issue）
- backend-ci 已做到，frontend 必须立即追上

- 集成测试 docstring 强制 `# Validates: Property X` 反向映射
- spec 不硬编码数字：task/Property/验收标准必须运行时表达式，narrative 允许快照值

### Subagent 调用约束（扩展版）
- 单次任务 ≤ 4 件事，超过强制拆批次
- prompt 强制返回结构化 JSON（files_created / files_modified / vue_tsc_status / pytest_count）
- orchestrator 不预读 subagent 即将创建的目标文件
- 越权三类风险：范围扩张 / bug 修复混入测试 commit / 状态变更单方面声明
- 工时压缩比 > 5× 必须暂停 review（可能是 grep 不全而非高效）
- 大批量 search-replace 后必须 grep 多种相关属性变体复核（不信 subagent 自报值）
- "已实施"三步验证：端点存在 ✓ + 至少 1 处真实调用方 ✓ + UI 触发路径明确 ✓

### UAT 规约
- 状态枚举：`✓ pass` / `○ pending-uat` / `⚠ partial` / `✗ fail`
- spec 完成时建 `.kiro/uat-pending/{spec_id}.md` 触发清单
- TD 只列未解决项；已落地的迁到 spec 末尾"实施记录"

### 跨 Spec 协调
- A spec 依赖 B spec 产出时，A 启动条件核验列出 B 完成度 + fallback 策略
- 跨 spec 共享文件依赖方向必须双向声明
- `.kiro/specs/INDEX.md` 不删除，新 spec 必须登记，每月一审

### CI Baseline 规约
- `.github/workflows/baselines.json` 字段格式：`{property}-{format}-{scope}`
- 占位值由 Sprint 0 实测填入，design 显式标注
- 属性级前缀（`border-color-prop-hex-vue-files`）替代泛化命名

### 批量替换通用模式
- 100+ 文件用 Python 脚本（正则 + skip allow-* 注释 + 字节级 read/write 绕 PowerShell GBK）
- dry-run → 补映射表 → 二轮 dry-run → apply → grep 多变体复核 → 修订 baseline
- 脚本用完即删（不进 git）

### 占位 Spec README 模板（17 章）
一为什么做 / 二真实结构 / 三总控台拆解 / 四审定表公式拓扑 / 五优化方向 / 六范围边界 / 七启动条件 / 八UAT清单 / 九技术债 / 十风险缓解 / 十一差异说明 / 十二启动建议 / 十三工时估算 / 十四范围边界做不做 / 十五风险与缓解 / 十六修订记录 / 十七后续启动建议


## §测试与 PBT 铁律（2026-05 沉淀）

### PBT 设计
- **避免恒真断言（tautology）**：测 `(p and X<C) or (not p and X>=C)` 当 `p := X<C` 时是恒真断言，毫无业务价值；正确做法用业务不变量（恒等点/边界内/边界外/对称性/单调性）+ parametrize 显式边界用例覆盖
- **PBT 量化精度**：被测函数若内部 quantize 到 N 位小数，property 用极小 delta 会因量化损失等值，严格单调性会失败；正确做法 = ①property 改为非严格（`>=`，量化容忍）+ ②独立 property 在更"原始"字段（如 amount_change，未量化或量化损失更小）上验证严格单调
- **PBT 阈值边界严格不等式陷阱**：源码用 `if rate < -THRESHOLD` 严格不等式时，恰好 ±THRESHOLD 整点归 normal 而非 anomaly；parametrize 边界用例必须仔细对照源码不等号严格性（≤/< 区别）
- **VR 三角勾稽 PBT 模板**：避免恒真断言用 drift ∈ [-2,2] 区间生成 closing = expected + drift，业务不变量 `passes ↔ |drift| < tolerance`；boundary 用 parametrize 显式覆盖临界点（drift=0/±0.99/±1.0/±1.5）；金额用 `st.floats(0, 1e9)` + 后转 Decimal 避免极端值异常
- **PBT 策略选择**：用 `st.floats` + 后转 Decimal 验证（hypothesis 对 float shrinking 成熟 + 生成快 10x），不要直接用 `st.decimals`（慢且 shrinking 不成熟）
- **PBT 已注册 vs 未注册 prefix 必须分开测**：`_ensure_ipo_loaded` 对未注册 prefix 返回降级 errors 而非 []；用 `st.text().filter(lambda s: s.upper() not in REGISTERED)` 拆出独立 property 验证降级行为
- **optional PBT task 跳过必须注明**：spec 起草时把 PBT 列为 `[ ]*` 但实施时跳过，形成"显式列出但隐式跳过"的偏差；跳过决策（实施/等价 case 覆盖/性价比不足）须在 spec 末尾"已知缺口"段落留一句话注明
- **🔴 fast-check `fc.float({ noNaN: true })` 仍会生成 ±Infinity（金额域必须显式给上下界）**：2026-07-30 实测 seed `1139061718` 命中 `calcChangeRate(-Infinity, 0)` → `Infinity / -Infinity` = NaN → `toBeCloseTo(NaN)` 必失败；同形状还有 `calcSubtotal([+Inf, -Inf])`、`calcNetValue(Inf, Inf)`。**这类红是生成器越界而非公式缺陷，但随机 seed 让它成为定时炸弹**（D1 两个 spec 文件潜伏至今才炸）。规矩：①金额类生成器统一 `{ min: -1e9, max: 1e9, noNaN: true }`（抽成文件级 `AMOUNT` 常量）②若必须无界，则在 predicate 里 `Number.isFinite(v) ? v : 0` 归一（G10/G11/H10 已是此写法，故一直安全）③配套把 `parseNum` 类入口从 `isNaN(n)` 改为 `Number.isFinite(n)` —— `parseFloat('Infinity')` / `parseFloat('1e400')` 都能过 `isNaN` 检查，漏进公式会让整表变 NaN

### pytest 输出与运行
- **pytest 输出捕获铁律**：①PowerShell `2>&1 | Tee-Object` 在长时输出 + 并发情况下会出现"文件被锁"+ 静默丢失输出；正确方法 = `cmd /c "python -m pytest ... > _log 2>&1"` 然后 `Get-Content _log -Tail N` 分两步 ②本仓库未装 `pytest-timeout` 插件（`--timeout=60` 报错 unrecognized arguments）③测试代码用 `Path("backend/data")` 相对路径时必须从仓库根 cwd 跑（不能在 backend/ cwd 跑）

### 跨 spec ref_id 铁律
- **跨 spec 引擎复用 term 参数标准模式**（H→I 落地）：H-F11 折旧引擎 `_calc_*(*, term: Literal['depreciation','amortization'] = 'depreciation')` 默认值保持向后兼容；I-F2 摊销引擎调用时显式传 `term='amortization'`；schedule 输出字段名按 term 切换；写回时直接读取 `s["amortization"]` 不需手动改名兼容
- **跨 spec ref_id 区间过滤铁律**：单边 `int(...) >= N` 过滤会被后续 spec 新条目污染；正确做法 = 双重过滤 `(N_lo <= ref_id <= N_hi) AND cycle_membership(source_wp.startswith(L) OR target_wp.startswith(L))`；test_cross_spec_ref_id_ranges.py 含 SingleSidedFilterDetection 自动扫描全仓 cross_wp_refs tests 检测违规；闭区间已对齐：F 176-210 / H 211-242 / I 243-266
- **CWR severity 三级语义**：blocking = 阻断签字 / warning = stale 标记 + 提示用户 / info = 仅披露引用不影响流程；新增 CWR 时 info 占比应 < 25%
- **CWR blocking 比例由业务性质决定**：N 循环 blocking 占比 42% (5/12) 显著高于 M 循环 7% (1/15)，因 N→报表/N→税金内部联动错误均阻断签字；不应套用统一 blocking 阈值

## §守卫判据形态铁律（全局等值型 → 归因型，2026-08-15 guard-assertion-attribution-refactor 沉淀）

**核心口径**：全量扫描型守卫（跨循环/跨 spec 扫某集合再断言其规模的守卫），判据只许用 A/B/C 形态，**禁用 D/E**。

| 级别 | 形态 | 并发安全 | 举例 |
|---|---|---|---|
| A（目标态） | 违规清单为空 `expect(bad).toEqual([])` | ✅ 新增自动纳管、他人修好不红 | `unexpected = actual − allowlist` 必为 `[]` |
| B（可用） | 地板 `toBeGreaterThanOrEqual` / 天花板 `toBeLessThanOrEqual` | ✅ 只防空转与扩张 | `BUILDER_FLOOR=12`（实测 109，留大余量） |
| C（可用） | 包含式重点项 `toContain` / `assert x in inventory` | ✅ 结构错才红 | 「外币货币性项目必在可扫描清单」 |
| D（禁用） | 全局等值 `expect(集合.length).toBe(硬编码)` | ❌ 任何 spec 动真源必红 | `expect(tables.length).toBe(29)` |
| E（禁用） | 跨文件抠源码数字再等值 | ❌ 双向锁死，改一处必红另一处 | 正则从别的守卫源码抠 `.toBe(6)` 再断言 |

- **代价实证**（本 spec 立项事件）：2026-08-12 K 循环给共享表补段首码，真源 23/6/29 → 24/8/32，导致 **3 个 blocking CI job 挂 + 7 条断言红 + 6 条仍有效的归因断言被连坐（同 `it` 内等值断言先炸、后续拿不到反馈）+ 约 15 分钟归因成本**，且成本落在与该变更无关的人身上。等值断言还**掩盖了一个数据丢失级真红达 3 天**（k1/k3NoteSectionMap 推共享表未声明 `_row_scope`）。
- **规模型断言的正确写法**：新建全量扫描守卫时，规模量一律 **地板（形态 B）+ 命名常量 + 注释记「当前实测 N」**，**禁止** `toBe(<实测值>)`。地板要显著低于实测、留大余量（12 ≪ 109），使任何合法缩减都不假红；规模增长时无需上调地板。
- **两个硬编码常能被一个结构不变式替代且判据更强**：如 `counts.listed + counts.soe === tables.length` 校验真源自洽 —— 任何 spec 改真源都不打红它，但生成器算错分组会。优先找不变式，而非锁两个快照数字。
- **等值不得污染归因**：一个 `it` 内含「规模型」+「归因型」两类断言时必须拆成两个 `it`（规模型先、归因型独立）；多个具名对象的归因一律收集违规清单后单次 `toEqual([])`，禁止 `for` 循环内逐个 `expect`（首个失败即中止，后续对象无反馈）。
- **登记表按语义拆分、不混装**：「永久豁免」（有依据、不该有链路）与「真实缺口」（待补）必须分表，否则「缺口应为 0」这个可收敛目标不可表达。天花板判据只许缩不许扩，**缩小时必须同步下调天花板**（留余量 = 偷偷放宽成可回弹）。
- **跨文件锚定落在行为事实、不落在对方写法**：需要感知「别的守卫是否仍把某对象登记为 X」时，先 `stripComments` 再判**去注释后的真实登记**（`includes('对象名')`），不要正则抠对方的常量名/断言写法/具体数字（墓碑注释会让含注释正则同时假红+假绿）。
- **改完守卫必做变异检验**（见 `backend/scripts/check/mutate_guard_attribution.py` 范式）：人为制造真实违规，四态判定 RED/GREEN/ANCHOR-MISS/WRONG-TEST，只有 RED 且命中预期测试名才算判据仍有效；没打红 = 守卫有缺陷，不是代码没问题。
- **单循环内的硬计数可留**：作用域限于单一循环、真源不被本循环外其它 active spec 触及的硬计数（如 `g7NoteSubtableContract` 的 27/2/11/3）判 `keep`，但须补一行注释「作用域限于 X 循环，故硬计数安全」。判「必须改」的唯一标准 = 该断言的真源被本 spec 之外的其它 active spec 拥有或触及。

## §UAT 标注铁律

- **形式合规但用户不可达 UAT 标注**：UAT 标 ✓ 必须验证"用户在 UI 层实际能触达功能"，不能仅基于"组件文件存在 + 后端单测全绿"；前端 Dialog 类组件必须**同时**满足：①组件创建 ②WorkpaperEditor 集成（toolbar 按钮 / 右键菜单 / sheet 顶部入口）③vitest 覆盖 buildBody/formatRate/flag 映射；缺任一项应标 ⚠ partial 而非 ✓
- **UAT 分级铁律**：标 ✓ pass 必须"功能在用户层可用"，stub/占位实现一律标 ⚠ stub，部分实现标 ⚠ partial；不要一律 ✓ 误导上线决策
- **程序化 UAT 验收方法**：写一次性脚本 `_uat_check.py` 跑量化指标（sheet 数 / cells / cross_wp_ref 数 / VR 规则数 / 4-arg AUX 校验等）+ 复用已有 pytest/vitest 断言 + 代码锚定核验，按 N 项验收一次输出全部 ✓/⚠/✗ 分级；脚本用完即删；比手动 UAT 快 10x，但仅适用于"可量化"指标
- **UAT 数量指标语义**——总数 vs 新增段：spec UAT "≥ N 条"类指标默认是"总条目数"（含基线 + 新增）；闭区间过滤仅用于"新增段"度量，绝对不能替代总数核验
- **UAT P 列优先级标注**：F spec 缺失（仅备注 P0 #1/#2/#3），H spec v1.2 升级为表格 P 列；P0 项数 = 关键架构改动数 × 2~3
- **真实 UAT 验收暴露价值铁律**（partner-dashboard 实战）：单元测试 100% + memory 记录"20/20 tasks ✅"不等于"用户层可用"；类似"组件已建但没在视图中接进来" / "状态没持久化导致 reload 后逻辑失效"等 bug 只能用 playwright 真实数据 UAT 暴露

## §sub-agent 协作铁律

- **sub-agent 沙箱伪绿铁律**：sub-agent 报告"task 完成 + N/N 测试全绿"必须在主 agent 跑一次原仓库测试做真实验证；防御机制 = ①每个子代理 task 完成后主 agent 执行 `python -c "import; getattr"` 锚定核验关键符号 ②sub-agent 报告"全绿"后主 agent 重跑相关测试文件 ③大 spec 完成后做"伪绿系统性盘点"
- **sub-agent overload 直接执行降级**：sub-agent 反复 high load 时不要重试浪费 turn，直接在主 agent 执行 task；批量委托建议每批 4-5 task，单 task 不值得委托
- **sub-agent 高负载降级硬规则**：sub-agent 报 "high load" 时**只重试 1 次**，第二次失败立刻在 main agent 直接执行（保持进度），不要反复重试浪费 turn

## §spec 工作流铁律

- **二轮复盘"形式 vs 实质"自查铁律**：Sprint 4 P0/P1/P2 修复完成后必须再做"形式合规但本质未到位"自查；典型隐患：①stub 标志硬编码 ②CWR severity 偏松 ③LLM summary 文案模板写死（无变量插值）④隐式覆盖（PBT 跳过的"等价覆盖"未形式化证明）
- **复盘"形式 vs 实质"原则**：spec 完成后必须做"复盘 → 找出形式合规但本质未到位 → 列 P0/P1/P2 修复轮 → 修完再标 ✓"循环
- **复盘核验"先实测再修复"铁律**：复盘怀疑某项不达标时必须先 grep 现状 + 跑核验脚本实测，再决定是否写补丁脚本；I3-2/I2-6/I1-10+I1-11 prefill 复盘前以为各 4/0/10 cells，实测发现 Sprint 2 实施时已 9/4/14 cells 全部超原始目标，UAT 表过时未更新形成 partial 假象
- **partial 项必须独立追踪铁律**：spec 完成后 ⚠ partial 项必须升级到 INDEX.md 或独立 backlog 入 P0/P1/P2 队列，不能仅以"task 5.x 已完成 + 已知限制 X"形式埋在 spec 文档内
- **spec 父任务标 `[ ]` 但子任务全 `[x]` 不视为未完成**：spec-task-execution 子代理只标更新子任务勾选，父任务标记常被忽略；判定 spec 完成度应基于"叶子任务全 `[x]`"而非父任务标记
- **memory 中"转季度迭代/延后/未覆盖"表述定期实测核验**：早期复盘记录"剩余 N 项延后"在后续 spec 实施完成后会变成假象；问"还有什么剩余"前必须 grep tasks.md 实测每项当前状态
- **task 标 [x] 铁律**：只有跑过 pytest/vitest 且全绿才能标 [x]；"假设复用已有逻辑 = 0 改动"不等于验证通过
- **大 spec 拆分铁律**：把异质度极大的 N 项功能塞进单 spec 会导致 30/30 标 ✓ 假象 + 复盘工作量 = N × 单 spec 复盘；判定信号：spec 内 ADR 数 ≥ 6 且彼此无依赖时一定要拆
- **router_registry 注册必须验证铁律**：新建 router 必须有对应 `test_router_registered_in_*` 测试 + 主 agent 跑通验证 §N 字符串
- **xfail reason 写"XXX doesn't exist - production code bug"= 根因修复信号**（2026-05-31）：不是绕开——先验证真实定义（枚举大小写/字段是否存在，`python -c "getattr(Enum,'X','MISSING')"`，不信测试与代码哪个对），修根因后去 xfail 让其真实通过，不留假绿
- **merge 跨阶段签名变更必 grep 全部调用方铁律**（2026-05-31 实证，两次咬人）：merge 带入相邻阶段的 sync↔async 改 / 删公开方法时，必须全仓 grep 调用点同步改+跑 import 冒烟——单阶段 mock 测试全绿不代表跨阶段不断裂（实例：Phase1 改 async 令 Phase2 cascade 静默失败 / Phase1 删 _execute_formula 令 Phase2 测试全红）
- **多阶段 spec 并行开发盲区 = 无全链路集成测试**（2026-05-31）：各阶段单元/PBT 充分但都 mock 掉相邻阶段，接口契约无守门 → merge 时签名漂移咬人；下游阶段应基于上游真实代码而非"上游待做"假设开发；"先行止血"stopgap 代码（顶上游未做）应明确标"临时，上游来了要删"并连带删其测试
- **复盘必跑全套测试不信文档自述**（2026-05-31）：声称"全绿"前实际跑套件——本轮正是跑 147 consol 套件抓到 merge 后 7 个失效测试；"全绿"含金量受数据限制时必诚实标明（如合并模块全合成/mock 数据，真实数据正确性 0 验证 ≠ 可生产）

## §migration / SQL 铁律

- **migration_runner SQL 限制**：使用 SQLAlchemy text() 执行，不支持 `DO $$...$$` PL/pgSQL 块（`$$` 被解析为绑定参数）；所有迁移必须用纯 SQL 语句（ALTER TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS / ALTER TYPE ADD VALUE IF NOT EXISTS）
- **迁移文件位置**：必须放 `backend/migrations/`（migration_runner 读取此目录），从 alembic/versions/ 写后必须复制
- **模型字段无迁移补救**：当 task 仅在 ORM 模型加 JSONB 字段但未配套 V0XX 迁移时，SQLAlchemy server-side `Mapped` 默认值不会触发 ALTER TABLE；必须手动补迁移

## §通用代码模式

- **变量名与 FastAPI Query 参数名冲突陷阱**：函数签名 `sheets: str | None = Query(None)` 后函数体内不能再用 `sheets: dict = {}`（参数会立即被覆盖丢失），必须重命名内部变量；同款适用所有"参数名 = 短变量名"场景（rows / cols / data 等）
- **xlsx-js-style CJS/ESM 互操作**：`await import('xlsx-js-style')` 在不同环境返回 `{utils, writeFile, ...}` 或 `{default: 实际模块}`；用 helper `_loadXlsxStyle()` 优先取 `mod.utils` 顶层、否则解 `mod.default.utils`
- **LibreOffice 路径 fallback 铁律**：Windows winget 安装的 LibreOffice 默认不加 PATH（`C:\Program Files\LibreOffice\program\soffice.exe`）；任何依赖外部命令行工具的服务必须 4 路径 fallback：①shutil.which ②env 变量显式覆盖 ③Windows 默认 ④macOS Homebrew Cask ⑤Linux 包管理器路径
- **EventBus.broadcast_raw 模式**：进程内事件总线轻量级广播 API（不走完整 publish dispatch / 不入 debounce / 仅写 Redis Stream + log）；适用于不需要 EventPayload schema 的场景
- **API 写回联动模式**：后端 endpoint 加 `apply_to_sheet: str | None`，写入 `working_paper.parsed_data.{namespace}[sheet]={method/applied_at/data}`；前端弹窗加 `targetSheet` prop + 「采纳并写回」按钮 + emit `applied` 事件
- **配置驱动型 stub 测试模式**：用 `monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False/True)` 切换两态，验证 endpoint 响应字段 `is_llm_stub` 同步切换 + summary 文案条件分支正确
- **WorkingPaper 模型 wp_code 在 WpIndex 上不在主表**：按 wp_code 查询底稿必须 `select(WorkingPaper).join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id).where(WpIndex.wp_code == wp_code)`
- **build_reasoning_chain 公共构造器模式**：`app.services.llm_service.build_reasoning_chain(reasoning, references, data_sources, is_llm_stub, base_confidence)` 返回 4-tuple；is_llm_stub=True → confidence 强制 0.0 / False → clamp(base_confidence, 0.0, 1.0)；6 个 stub endpoint 共用此 helper 防文案漂移
- **stub 标志铁律**：API 返回字段如 `is_llm_stub` 不能写死 True/False，应由 `settings.WP_AI_SERVICE_ENABLED` 类配置驱动

## §K 循环 sheet 分类与正则陷阱

- **K 循环 sheet 分类优先级**：10 类规则中"费用明细" priority=3 前置于"明细表" priority=4，专门匹配 `^明细表K[89]-`（K8-2/K9-2 销售/管理费用月度明细）；"往来款检查" priority=6 仅匹配 K1-/K3- 含业务关键词
- **正则 negative lookbehind 防误命中**：sheet 名 `会计提示` 的"计提"二字会被通用"计提"规则误命中检查表，用 `(?<!会)计提` 排除前缀为"会"的情况
- **附注披露 5 种括号变体**：`附注披露信息(上市公司)` / `(国企)` / `（上市公司）` / `（国企）` / `（国有企业）` 5 种全角/半角括号 + 双称呼组合
- **真实 sheet 名末尾空格陷阱**：openpyxl 读 J1 模板发现 `审定表J1-1 ` 末尾带空格，prefill cell 的 `sheet` 字段必须包含真实空格；spec 起草时 sheet 名核对必须用 `repr(name)` 输出避免肉眼漏看

## §Frontend UI 路由与导航

- **首页快捷区盘点铁律**：新功能上线后 Dashboard.vue `quickActions` 数组必须同步追加快捷入口；判定信号：所有"全局功能"（无 :projectId 前缀的路由）必须同时出现在①Dashboard quickActions ②ThreeColumnLayout FALLBACK_NAV 或 sidebar tools 簇；缺一不可
- **路由可达性核验铁律**：vue-router 子路由 `path: 'xxx'`（无前导 `/`）在父路由 `path: '/'` 下最终 URL 是 `/xxx` 是合法的；防御脚本 = grep ThreeColumnLayout 所有 `path: '/xxx'` + `@click="router.push('/xxx')"` 集合，与 router/index.ts 全部 `path: '...'` 集合做差集
- **node 跳转 routeMap 实施前必须 grep router 验证**：图省事猜路由 name 可能整片失效，必须 ① grep router/index.ts 验证 name 存在 ② grep 路由 path 验证是否需要 projectId 参数 ③ 区分"模块名"与"实际是底稿 wp_code"


## §可复用架构模式（2026-05-22 沉淀）

### DT-3 方案 B：DB-backed 重构的混合替代方案

枚举字典/配置项类需求要支持"在线修改"但不能完整 DB 化（value 与代码引用绑定）时：
- value 字段（与代码 enum 绑定）锁定，POST/DELETE on `/items` 仍返 405
- 仅"展示属性"（label/color/desc）允许 DB 覆盖：新建 `*_overrides` 表 PK=(key, value) 仅存 `*_override` 字段（NULL=用代码默认）
- GET 端点合并代码默认 + DB 覆盖（覆盖优先）
- PUT 端点 admin only，校验 (dict_key, value) 必须存在于代码 _DICTS（防新增）
- DELETE `/items/{value}/override` 子路径清除覆盖恢复默认（独立路径与"删除 value"区分）

### S-3 v2：声明式 JOIN 白名单

高级查询构建器/DSL 类要支持 JOIN 但不能接受任意 ON 条件时：
- 预登记 `JOIN_WHITELIST: dict[base_table, dict[target_table, {on: [(left_col, right_col), ...]}]]`
- DSL 仅接受 `joins: [{table: str, type: 'inner'|'left'}]`，不接 ON 表达式
- 字段引用双段语法 `table.field`，校验 table 必须 ∈ (base ∪ joins)
- 单段语法（如 `audited_amount`）默认从 base_table 解析（向后兼容）
- 新增 JOIN 关系走代码 PR 而非用户输入

### DSL 类型 coerce（query_builder 实战）

DSL endpoint 接受 user JSON 时，filter value 必须按列类型 coerce 否则 SQLAlchemy 报奇怪错误：
- `_coerce_value(col, value)` helper：用 `col.type.python_type` 决定目标类型
- UUID 列 + str value → `uuid.UUID(value)`，非法字符串返 400 INVALID_UUID（避免 SQLAlchemy 抛 `'str' object has no attribute 'hex'`）
- Decimal/Date/DateTime/Bool 同款，str 输入按 ISO 8601 / Python 标准转换
- in/between 操作符的 list 内每元素都要 coerce
- like/not_like 不 coerce（强制字符串语义）
- is_null/is_not_null 忽略 value

### 版本管理双契约模式（AT-3 实战）

attachments / KnowledgeDocument 类版本链 service 同时支持两种调用契约：
- 契约 A：`(attachment_id, version_id)` — 通过实例 id 反查链 + 跨链拒绝校验（version_id 必须与 attachment_id 同 chain key）
- 契约 B：`(project_id/folder_id, name, target_version)` — 显式定位
- list_versions 同款双契约（仅传 attachment_id 反查 vs 显式 project_id+name）
- chain key = (project_id, reference_id, reference_type, file_name) 或 (folder_id, name)
- 旧版本不真删（is_deleted=false 保留），rollback 创建 version=N+1 + previous_version_id 指向当前最新
- 测试必须两种契约都覆盖（部分前端代码用 A，部分用 B）

### service 层"DB+ORM+service"三层一致校验

子代理或人工实施"加字段/加方法"类任务时，必须 grep 三层是否一致：
- ①DB 迁移文件（V0XX.sql 或 alembic version 文件）
- ②ORM 模型 `Mapped[]` 字段
- ③service 方法（含 list/rollback/get 等）

任一层缺失即伪绿。AT-3 实战中 V014 迁移已写但 Attachment 模型 + service 都没补，pytest 设施齐备反而掩盖缺陷（fixture create_all 自动建表）。

### service 层禁止裸 SQL 操作 ORM 未声明列（ADR-CONSOL-002，2026-05-31）

- **规约**：service 层禁止用裸 SQL（`text("UPDATE/SELECT ... consol_lock ...")`）操作未在 ORM `Mapped[]` 声明的列
- **根因**：`schema_drift_detector` 只对比 ORM `Base.metadata` vs DB；裸 SQL 操作的列两边都看不到 = 自动化安全网盲区
- **后果**：列不存在时 UPDATE 静默失败 / SELECT 抛异常被 try/except 吞掉 → 功能"假成功"
- **正确做法**：所有字段必须先在 ORM 模型声明 `Mapped[]`，service 通过 ORM `select(Model.field)` / `setattr(obj, field, value)` 操作
- **审查方法**：`grep "UPDATE \w+ SET" backend/app/services/` + `grep "text(" backend/app/services/consol*` 定期扫描
- **适用范围**：所有 service（不限 consol），尤其新增字段时必须同步三层（DB 迁移 + ORM + service）

## §PG / 运维操作铁律（2026-05-23 ledger-import-view-refactor 9.8/9.9/9.10 沉淀）

### PG SET 命令不支持 prepared statement 绑定参数

`SET LOCAL app.current_project_id = :pid` 会被 PG 拒绝。必须用 `SELECT set_config('app.current_project_id', :pid, true)` 函数等价；session 级（`is_local=false`）/ tx 级（`is_local=true`）由第三参数控制。set_rls_context 等场景一律走 set_config。

### PG superuser 永远 bypass RLS

dev 用 postgres 直连测不到 RLS 隔离效果（PG 永远 bypass superuser）。生产部署必须用独立 app role（无 SUPERUSER 无 BYPASSRLS）。canary 验证脚本里要 grep `current_user` 确认非 superuser，否则 RLS POLICY 等于没启用。

### CONCURRENTLY 不能在事务内（含 SQLAlchemy AUTOCOMMIT）

SQLAlchemy async `engine.connect()` + `execution_options(isolation_level="AUTOCOMMIT")` 仍走连接池事务包装，DROP/REINDEX INDEX CONCURRENTLY 会阻塞。正解：
- 用 `asyncpg.connect(dsn)` raw connection（asyncpg 默认 autocommit）
- 加 `SET lock_timeout = '60s'` 防止被 idle-in-transaction 卡死
- DSN 转换：`postgresql+asyncpg://...` → `postgresql://...`

### CONCURRENTLY 失败留 _ccnew 残骸

被 cancel/timeout 的 REINDEX/CREATE INDEX CONCURRENTLY 会留 `_ccnew*` 或 `_ccold*` 同名 invalid index，再次 REINDEX 会拒绝重建。脚本必须先清理：
```sql
SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
WHERE NOT i.indisvalid AND (c.relname LIKE 'idx_%_ccnew%' OR c.relname LIKE 'idx_%_ccold%');
-- 对每行 DROP INDEX CONCURRENTLY IF EXISTS xxx_ccnew
```

### CONCURRENTLY 卡住调试套路

①`pg_stat_activity` 查 active 会话（query 是否仍是 REINDEX/DROP）+ `idle in transaction`（最常见 blocker，xact_start 老旧）
②`pg_locks` 看目标表 `ShareUpdateExclusiveLock granted=False`（被等待的锁请求）
③`pg_cancel_backend(pid)` 软取消 active / `pg_terminate_backend(pid)` 硬终止 idle-in-tx
④清完后查 `pg_index WHERE NOT indisvalid` 找 _ccnew 残骸先 DROP 再重试

### PowerShell `Out-File` 文件锁

powershell 进程异常退出但仍持有 log 文件句柄时，`Get-Content / Remove-Item` 都拒绝。正解：
- `Get-Process powershell | Where-Object { $_.Id -ne $PID } | Stop-Process -Force` 先释放
- 用 `cmd /c "python xxx.py > log 2>&1"` 替代 PowerShell 的 `2>&1 | Out-File`
- `Set-Content -Encoding UTF8` + `-join` 字符串数组会吞 ⚠️ 📌 → 等字符；写中文/emoji 文件用 `fsWrite` / `strReplace` / `fsAppend` 工具或 `python -c` 替代

## §批量入库脚本规范（2026-05-23 ledger-import 9.2 沉淀）

可复用工具：`backend/scripts/batch_import_real_samples.py`，绕过前端 UI / Worker 队列直调 ledger_import 管线（detect→identify→parse→convert→write→trial_balance 派生），支持 `--skip-large/--only/--dry-run`。

### 设计要点

- **幂等设计**：项目按 client_name 复用；trial_balance 先 DELETE 同 (project_id, year) 再 INSERT
- **raw SQL 创建项目**：避免 ORM 加载顺序问题
- **通用 helper 可独立复用**：`_insert_balance` / `_insert_aux_balance` / `_insert_trial_balance` 可挪到 demo seed / E2E fixture

### 踩坑清单

- `projects` 表 5 个 NOT NULL 字段无 default：`version` / `consol_level` / `is_deleted` / `scenario` / `has_foreign_currency` 必须显式给值
- `created_by` FK 到 users 表，硬编码 UUID 不存在；必须 `SELECT id FROM users WHERE username='admin'` 先查
- `AccountCategory` 枚举只有 5 值（asset/liability/equity/revenue/expense）无 cost
- `trial_balance` 有 unique (project_id, year, company_code, standard_account_code) 约束，幂等需先 DELETE 同 (project_id, year)

### 直接调 service 优于 Playwright UI

单家完整入库走前端 UI 含 30+ 步骤 + 大文件 detect 数分钟，agent turn 易超时。用 Python 调用同款 service 管线（detect/identify/parse/convert/insert）效果完全等价但快 10x，最后用 Playwright 仅做"前端可见性"验证。


## §跨模块 source 命名空间规约（2026-05-24 advanced-query-enhancements-p1p2 沉淀）

### Source URI 格式（5 命名空间）

- `workpaper:{wp_code}|{sheet_name}|{cell_range}` — 底稿 cell 级查询（高级查询 SheetCellRangePicker）
- **`wp://{wp_code}/{cell}`** — 公式引擎 WP 域单元格引用（`wp_formula` 持久化；**勿用** `wp://{wp_code}#{cell}` 作新数据，仅 `uri_to_formula_ref` 兼容旧 `#`）
- `report:{report_type}|{cell_range}` — 报表虚拟 sheet（A=row_code, B=row_name, C=current_period_amount, D=prior_period_amount, E=formula）
- `note:{section_id}|{cell_range}` — 附注虚拟 sheet（A=code, B=name, C=year_end, D=year_begin, E=formula）
- `adj:{adjustment_type}|{cell_range}` — 调整分录虚拟 sheet（A=entry_no, B=account_code, C=account_name, D=debit_amount, E=credit_amount, F=description）
- `tb:{aux_dim}|{cell_range}` — 试算表虚拟 sheet（A=account_code, B=account_name, C=opening_balance, D=debit_amount, E=credit_amount, F=closing_balance, G=audited_amount）

判定 = 任何新增模块 cell 查询必须遵循 `{module}:{qualifier}|{cell_range}` 格式，`|` 分隔避免与命名空间 `:` 冲突。

### 模板联动事件总线契约

- 正向（模板→查询）：`eventBus.emit('open-custom-query', { tab: 'basic', source: string, project_id?: string })`
- 反向（查询→模板）：`GET /api/custom-query/address-resolve?uri=...` → `router.push(route_path, route_query)`
- 树 reveal：监听 `open-custom-query` 事件后自动展开 ancestorKeys + scroll-into-view

### 跨 sheet 公式解析 regex

正确 pattern（避免灾难性回溯）：
```
(?:'([^']+)'|([A-Za-z\u4e00-\u9fff][\w\u4e00-\u9fff]*))!([A-Z]{1,3}\d{1,7})
```
- Group 1 = 带引号 sheet 名（含空格/中文）
- Group 2 = 不带引号 sheet 名（必须以字母/中文开头）
- Group 3 = cell 引用
- 禁止使用 `[^'!]+` 类字符类（PowerShell 转义 + 回溯风险）


## §UI 视觉偏好补充（从 memory 下沉 2026-05-26）

### GtToolbar slot 契约

- GtToolbar 提供 `#left` / `#right` / `#center` 三个 slot
- Tab 栏右侧工具按钮通过 `#right` slot 注入，不独占行
- 简单 CRUD 页面不用 GtPageHeader 紫渐变横幅，直接 GtToolbar compact 模式

### 全屏三件套

- `useFullscreen(containerRef)` 返回 `{ isFullscreen, toggle, exit }`
- 全屏容器加 `.gt-fullscreen` class（z-index: 9999 + fixed + 白色背景）
- ESC 退出全屏（document keydown 监听）

### Teleport 脱离 transform 祖先

- el-dialog/el-drawer 必须 `append-to-body`（三栏布局 overflow:hidden 截断）
- Teleport 到 body 的内容脱离组件 scoped style 作用域
- 需要样式覆盖时用独立全局 `<style>` 块（非 scoped）
- **🔴 `<style scoped>` 里 `@import './X.css'` 的外部 CSS 同样被 scoped 转换**（2026-07-29 DisclosureEditor 实测）：注入时每条规则**最后一个复合选择器**被追加 `[data-v-xxx]`。因此
  - `popper-class` / teleport 到 body 的 popper 根元素（`.el-popper`、`el-tooltip` 根）在这类文件里**永远选不中，加 `!important` 也无效**（该元素无 `data-v` 属性），`:deep()` 也救不了（popper 不是组件子孙）→ 必须写进 `.vue` 末尾的非 scoped `<style>` 块
  - 但 tooltip **内容**（`#content` 插槽渲染的 div）带 `data-v`，可以留在 scoped 文件里
  - 判定手段：`document.styleSheets` 遍历 `cssRules` 看实际注入的 selector 有无 `[data-v-]` 后缀；**直接 curl `/src/.../X.css` 看到的是未处理源码（`:deep()` 还在），会误判**

### el-table flex 高度

- 表格容器用 `display: flex; flex-direction: column; height: 100%`
- el-table 加 `flex: 1; min-height: 0`（防止溢出）
- 配合 `max-height` 实现表头冻结 + 内容滚动

### Tab 栏同行工具按钮

- el-tabs 右侧工具按钮通过绝对定位或 flex 布局实现同行
- 不允许工具栏独占一行（浪费垂直空间）
- 按钮组用 `el-button-group` 或 `gap: 8px` flex 容器

### Dashboard 视觉规约

- 5 个 dashboard 统一 `GtPageHeader variant="banner"` + dark 主题
- DashboardViewSwitcher 共享组件挂 banner `#actions` slot
- 卡片间距 16px，圆角 12px，阴影 `0 2px 12px rgba(0,0,0,0.08)`

### 借贷成对展示

- 调整分录表格借贷必须成对展示（同一行或相邻行）
- 借方金额列 + 贷方金额列并排，不合并为单列正负数
- 合计行分别显示借方合计 / 贷方合计，差额单独一行

### 底稿模块 Tab 顺序（2026-05-24）

生命周期→委派矩阵→列表→工作台→看板→依赖图→手册（生命周期第一位=先裁剪程序）；树默认折叠

### 程序裁剪页面（2026-05-24 重写）

`ProcedureTrimming.vue` 三大功能 = 一键智能裁剪 / 自定义裁剪 / 自定义新增程序；`chain_orchestrator` 步骤 5b 尊重裁剪 + 步骤 5c 加入自定义程序

## 合并模块规范（consol）

- **抵销分录消费口径统一为 APPROVED**（consol-phase1-arch-lock / ADR-CONSOL-102，2026-05-31）：worksheet（`consol_worksheet_engine`）与 trial（`consol_trial_service.recalculate_trial`）两条计算路径**只消费 `review_status == approved` 的 `EliminationEntry`**（draft/pending_review/rejected 不进合并数）。这是预期修正——**口径变更需通知用户**：未审批的草稿抵销不再影响正式合并报表。抵销审批（→approved）发 `ELIMINATION_APPROVED` 事件自动触发 worksheet + trial 重算（幂等）。
- **ReviewStatusEnum 成员全小写**：`draft/pending_review/approved/rejected`，禁止写 `.APPROVED/.DRAFT` 大写（会 AttributeError）。
- **合并公式引擎复用 report_engine**（ADR-CONSOL-101）：合并报表取数经 `AmountResolver` 注入（`ConsolTrialResolver` 读 consol_trial.consol_amount），公式解析/求值统一走 `report_engine.evaluate_formula`，禁止在 consol 侧复制公式引擎。
- **consol service 全 async**（ADR-CONSOL-106）：`AsyncSession` 上禁止 `self.db.query()`，统一 `await self.db.execute(sa.select(...))`。
- **锁定全端点覆盖**（ADR-CONSOL-103）：子公司写端点（底稿/附注/序时账/报表）必须挂 `Depends(check_consol_lock)`；端点仅含 wp_id/note_id 时 check_consol_lock 自动反查 project_id；project_id 在 body 的端点（reports/notes generate）需在 handler 内 `await check_consol_lock(project_id=..., db=db)`。前端子公司编辑视图挂 `<ConsolLockedBanner />`。
- **负商誉按 CAS 20**（ADR-CONSOL-104）：负商誉全额计入当期损益（营业外收入），无 25% 阈值/递延摊销。
- **minority_share_ratio = 少数股东持股比例**（ADR-CONSOL-105）：附注直接展示，禁止 `(1 - ratio) * 100` 求补数。


## §event_bus 联动铁律（2026-06-12 修 4 处沉淀）

- **🔴 两条发布路径勿混**：①`event_bus.publish(payload: EventPayload)`/`publish_immediate` 单个 EventPayload 位置参数，走 debounce+_handlers+SSE（联动主链用）②`event_bus.broadcast_raw(event_type: str, extra: dict)` 同步、纯 SSE 推送、不触发 _handlers（轻量通知用）。**禁止传裸 dict 或关键字参数给 publish()**（`_build_dedup_key` 访问 `.event_type` 会抛异常，常被 `try/except:pass` 静默吞掉→联动断裂）
- 已修 4 处：`deliverable_writeback._emit_note_saved`（误用 `publish(event_type=,payload=)`）+ `annotations`×2/`review_conversation` 裸 dict→改 broadcast_raw + 最严重 `working_paper.save_univer_data` 第7步裸 dict+`asyncio.create_task`+`try/except:pass` 双重静默（`WORKPAPER_SAVED` 从未分发→一致性比对/B51高风险/底稿域地址/prefill stale 全失联）→改真 EventPayload+从 `Project.audit_period_end` 推导 year
- **🔴 后台作业类 bug 必先查 DB 真实状态再读代码**：第一步 query 状态表看现场；中间层补丁（幂等保护/防御性跳过）≠ 根治；"逻辑推断+单测通过"≠"端到端实测"
- **🔴 联动失效域审计（3 类）**：①公式管理—`FormulaEngine` 的 `formula:*` Redis 缓存是死代码，真缓存=`FormulaReverseIndex` 单例；`FORMULA_CONFIG_CHANGED`/`PREFILL_MAPPING_CHANGED` 已补 `invalidate_reverse_index()` ②高级查询 `custom_query`—`_query_trial_balance` 误查不存在列→改 standard_account_code/unadjusted_amount/audited_amount ③地址坐标库 `address_registry` 5 域—补 `NOTE_SECTION_SAVED→note 域`/`WORKPAPER_SAVED→wp 域`/`LEDGER_DATASET_ROLLED_BACK→全量`
- **🔴 word_export_task 单数表名**（非复数）；query_builder 安全契约：`users` 表禁入 TABLE_WHITELIST（不暴露 user/role/auth）

## §测试掩盖运行时 bug 反模式（同源 4 例铁律）

- `deliverable_writeback._emit_note_saved`(mock 把错误签名编进去)/univer-save(`try/except:pass` 吞)/`refresh_section`(mock 不存在的 `store_version_file`+e2e 显式吞 AttributeError)——**mock 一个不存在的方法/错误签名 = 把 bug 编码进测试**，测试永绿但生产必崩
- 改测试铁律：①mock 必须 mock 真实存在的方法（`assert_awaited_once` 验真调用）②禁止 `try/except: pass` 包住被测调用 ③service 间调用优先 `inspect.signature`/源码静态检查守护契约
- **merge 跨阶段签名变更必 grep 调用方**（sync↔async / 删公开方法）

## §asyncpg / PG 事务铁律

- **asyncpg 事务污染**：事务 aborted 后连 SAVEPOINT 都被拒 → 根治=修最先失败的 SQL（规则内 try/except 吞 SQL 异常不 rollback=反模式）
- **service 只 flush 不 commit**：跨 service 编排由 router 统一 commit 保原子
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ ALTER TYPE ADD VALUE 不可事务内即用 / PG-only SQL 必加 SQLite dialect 检测
- **`dict.get(k, default)` 陷阱**：key 存在但值为 None 时返 None 不返 default（Pydantic 可选字段未填即 None）→ NOT NULL 列插入崩；写库前 `(data.get(k) or fallback)` 显式兜底
- **枚举成员引用前实证**：`python -c "getattr(Enum,'X','MISSING')"` 核对大小写（小写 draft/approved）
- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿；TimestampMixin 表手写 DDL 必显式写 `created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

## §router 与 API 形态铁律

- **router_registry 必查**：新建 router 必在 `backend/app/router_registry/{group}.py` 注册否则前端 404；FastAPI 不热加载 router（改后重启）；**注册顺序**：含静态路径的 router（`/batch-template`）必在同前缀通配 router（`/{project_id}`）之前，否则通配截获→422 UUID parse error
- **🔴 后端端点返回形态不统一陷阱**：`get_trial_balance` 正常返纯 list，过渡期返 `{data:[...], warning:...}`→经 ResponseWrapperMiddleware 信封 `data` 是对象→前端 `rows.value.map` 崩。端点双态返回必须在前端 API 函数层统一归一化（`Array.isArray` 兜底），不可裸传给 ref
- **apiProxy 单层解构**：`api.get/post` 已返业务数据不再 `const {data}=`；`http.get/post`（utils/http）返完整响应体需 `.data`
- **CORS/307**：前端 3030 须在 CORS_ORIGINS；**禁止 `window.open` 下载认证资源**（新标签页不带 token→401），必用 `downloadFile`（axios blob + Bearer header）
- **铁律：原生 fetch 调后端必手动解 `{code,message,data}` 信封**（ResponseWrapperMiddleware 包装所有 2xx JSON）

## §前端 UI 踩坑铁律

- **🔴 `el-input` 只绑 `@change` 不回写 `modelValue` → 用户键入被抹掉**（2026-07-30 浏览器 + DB 双证）：element-plus 的 `handleInput` 在 `await nextTick()` 后调 `setNativeInputValue()`，把 DOM 值重置回 `modelValue`。若只监听 `@change`（modelValue 不随键入更新），用户敲的字会消失，`change` 拿到的是空串。实证：N1 国企「互抵明细」行名落库 `label: ""`，改 `@input` 回写后落库 `label: "同一纳税主体互抵"`。**规矩**：表格里的**文本列一律 `@input` 回写**；金额列走 `components/workpaper/shared/WpAmountInput.vue`（它自持 `draft` + 失焦归一，不受此坑影响）。平台存量 `:model-value + @change` 的纯文本输入（如各披露 Tab 的「原因」「备注」列）普遍有同一风险，逐个核时以浏览器实测为准，vitest 与 `get_diagnostics` 都查不出
- **🔴 `<script setup>` 不允许任何 `export` 语句（含 `export interface`）**：SFC 编译直接失败，而 `get_diagnostics`(Volar) **查不出**，只有 Vite transform 返回 500。组件对外类型必须下沉到同级 `.ts`（范式：`composables/n1DisclosureSegmentTypes.ts` 供 `N1DisclosureSegmentTable.vue` 与 composable 共同引用）
- **🔴 contenteditable + Vue v-model 回写循环**：`@input`emit + `watch(modelValue)` 比较 innerHTML 重设→浏览器规范化 HTML 使 innerHTML 永不等于父串→每次 keystroke 重设光标丢失。修=watch 加 `isInternalChange` 标记跳过自身回写 + 聚焦期间（`document.activeElement===ed`）不重设。`execCommand insertHTML` 内联 style 不解析 `var(--xxx)`，表格用具体色值+`<td><br></td>`保证可聚焦
- **el-segmented 逐项加 tooltip/徽标**：用 `#default="{ item }"` 插槽（渲染在 `.el-segmented__item-label` 内，`options` 可挂任意扩展字段如 `tip`/`rule`）；`<label>+radio` 结构下包 `el-tooltip` 不影响点选。**220px 侧栏内 4 项中文标签放不下数字徽标**（13px 下 4 项≈216px > 可用 208px）→ 用 5px 命中小圆点 + 数量写进 tooltip，改完必查 `scrollWidth === clientWidth`
- **🔴 el-tooltip 包非单元素根组件触发器失效**：`<el-tooltip>` 靠 `ElOnlyChild` 绑事件到子元素真实 DOM 根；包渲染 fragment/teleport 的组件→事件绑不上→hover 不弹（控制台 `non-element root node` 警告）。修=外套真实 `<span style="display:inline-block">` 作触发器
- **UI 必用 GT 紫令牌**（`styles/gt-tokens.css`）：核心紫 `#4b2d77`/浅紫底 `#f4f0fa`/浅紫边框 `#d8b8ee`；禁用 Element 默认蓝 `#409eff` 作 fallback；`el-tag type="primary"` 渲默认蓝需 `:deep(.el-tag--primary)` 覆盖
- **🟢 紧凑表格全局类 `gt-compact-table`**（`styles/gt-table.css`）：用户偏好数据表行间距小。**特异性陷阱**：`gt-polish.css` 全局 `.el-table td.el-table__cell{padding!important}`（0,2,1）会盖回紧凑类（0,2,0）→紧凑类 td/th 必带 `td.`/`th.` 限定符提到 0,2,1 持平，靠 gt-table.css 在 gt-polish.css 之后导入
- **useExcelIO.exportTemplate existingData 必须等宽**：所有行 pad 到 maxCols，否则 `xlsx-js-style` 写 cell 越界致 xlsx 损坏；多子表导出用 `applyStyles: false`
- **附注表格单元格激活编辑**：编辑模式点击/Tab/Enter 激活单个单元格才显示 input，其余轻量 `<span>`（50行×5列 250个 input→1个）；blur 用 `relatedTarget` 判焦点去向

## §附注导出/数据铁律

- **🔴 附注导出按 `sort_order` 排序**：章节号是中文（一/二/七/九/十）`ORDER BY note_section` 按 Unicode 码点乱套→必用 `ORDER BY sort_order ASC NULLS LAST, note_section`。`disclosure_notes` 导出/列表一律 sort_order 优先，禁中文 note_section 字符串排序
- **`disclosure_notes.table_data` JSON 结构**：`{name, headers, rows:[{label, values:[...], _cell_meta:{"列idx":{...}}, _cell_modes}], _tables:[多表]}`。单元格值字段是 `values`（非 cells）；`_cell_meta`/`_cell_modes` 按**列索引**键；`headers[0]` 是 label 列头；**`section_id` 列 DB 几乎全空**→过滤用 `note_section IN(...)` 不能用 `section_id`
- **🔴 openpyxl→WPS 兼容**：openpyxl `Comment` 生成 legacy VML drawing + `ws.protection.sheet=True`→WPS 报"无法打开"。修=移除 Comment（溯源用着色+隐藏 sheet 承载）
- **🔴 附注模板 account_codes 必须是该章节自身科目明细**，不能引用同级别其他一级科目（八、6 应收款项融资配 1124 明细非 1121/1122）
- **JSONB dirty-tracking 坑**：shallow copy 不触发 UPDATE→需 `copy.deepcopy`+`flag_modified`

## §账表导入踩坑铁律

- **🔴 导入卡死无进度无报错=改后端代码触发 --reload 杀 worker**：症状=大文件导入卡某进度不动，四表0行，job 停 writing 不前进不报错。根因=导入跑时 app/*.py mtime 变化→uvicorn `--reload` 重启→async task 里的 worker 子进程被杀（非代码 bug）。触发源：①手动编辑代码 ②**`git stash`/`pop` 重写工作区文件更新 mtime**。确诊（py-spy 黄金法）：`py-spy dump --pid <worker_pid>` 看事件循环 idle 在 `_select`+无 import 帧 + worker StartTime 晚于 job started_at。**铁律：大文件导入期间绝对不做任何会改 app/*.py mtime 的操作**——不编辑代码、不 git stash/pop/checkout/pull/merge。259万行 COPY 协议正常 5~15min
- **🔴 余额表列分级（KEY_COLUMNS 勿乱加）**：`detection_types.py` `KEY_COLUMNS["balance"]`=account_code/opening_balance/closing_balance/debit_amount/credit_amount；**account_name 必须留 RECOMMENDED 不能升 key**——`validate_l1` 对缺非互斥 key 列的行整行跳过，account_name 设 key 会删汇总行/精简表/无名称行。名称缺失可从 account_chart join 补回
- **🟡 同名项目陷阱**：用户在 A 项目导入却打开 B 同名项目看数据→误以为修复没生效。**诊断铁律：报"修复没生效"先 `SELECT ... WHERE client_name LIKE` 查同名项目 + 比对 `created_at`/`sign_convention_version`**
- **🔴 余额表方向显示三层**：①数据层 converter 源数据优先 ②API 层 SELECT tb_balance 返前端的端点必须含 `direction`/`opening_direction`/`closing_direction` 字段（漏查=前端走兜底=备抵科目必错）③前端 `resolveDir` 优先后端 direction
- **数据管理"删除"后重导入唯一约束冲突**：`delete_ledger_data` 只软删四表不删 `trial_balance`，但唯一约束无 `WHERE is_deleted=false`→旧行占位冲突。修=前端删除加 `hard_delete: true` 或 recalc 改 DELETE+INSERT

## §xlsx 渲染踩坑

- **🔴 A1-11 等带冻结窗格 xlsx 加载失败**：`xlsx_to_univer.py` `ws.freeze_panes.row` 把字符串（"A2"）当 Cell 对象→所有带 freeze_panes 的 xlsx 底稿 Univer 加载 crash。修=`coordinate_to_tuple(str(ws.freeze_panes))`。影响面广（所有 freeze_panes 非空底稿），需重启后端

## §OnlyOffice 调试铁律

- **🔴 调试顺序**：①先确认 git HEAD 配置正确（其他人能用→非代码问题）②只改 `.env` 对齐 secret+重启后端 ③禁止 `docker exec` 手动改容器 local.json（不可复现）④docker-compose 环境变量是唯一正确入口。secret 三方一致：config.py 默认值=docker-compose 默认值=.env 值
- **"下载失败"=SSRF 拦私有 IP**→`local.json` 加 `request-filtering-agent.allowPrivateIPAddress=true`（容器重建需重做）；**"无法保存"=ResponseWrapperMiddleware 包装 callback**→`_SKIP_CONTAINS=("onlyoffice/callback",)` 跳过
- **降级预览 previewType 必须按实际文件后缀动态传**（docx→'docx'，xlsx→'unsupported'）；`.env` 本地 dev 须 `ONLYOFFICE_URL=http://localhost:8080`（非 Docker 内部名）


## D~N循环底稿专属组件UI规范（2026-07-02定稿）

### 架构模式
- 主入口接sheetName prop用v-if分发（禁止内部el-tabs，外层GtWpRenderer已有目录chips）
- defineAsyncComponent lazy加载所有子组件（减少首屏bundle）
- 未匹配sheet走OnlyOffice fallback（GtOnlyOfficeSheet全高）
- sheetName是完整中文名（如"营业收入审定表D4-1"），用regex提取末尾编码匹配

### 表格配色约定
- 分组列头配色：浅绿(账面/基础信息) / 浅蓝(核对对象/凭证) / 浅紫(第三方/审批) / 浅橙(申报)
- 公式/自动取数单元格：虚线下划线 + cursor:help + tooltip显示来源
- 差异≠0红色高亮；变动>30%红色；>20%黄色
- 合计行不可编辑（灰底）

### 审计意见区
- el-card包裹（标题"审计意见区"）
- 内含：审计说明textarea + 审计结论textarea + 右侧AI辅助按钮 + 复核按钮
- 不要独立悬浮；不要多个散落的textarea

### 导入导出
- el-dropdown"导入导出▾"下拉菜单（导出模板/导出数据/导入数据用el-upload）
- 复用useXImportExport composable（调后端三端点）
- 必须用http(axios)不能用原生fetch（无auth header）
- StreamingResponse中文文件名用RFC5987编码

### 双/三模式切换
- el-segmented（结构化视图 / 矩阵视图 / 在线编辑）或（结构化视图 / 在线编辑）
- 切换前OO健康检查（/api/workpapers/onlyoffice/health）
- 不可用时禁用"在线编辑"+ tooltip

### 统计仪表板
- 表格上方el-row 3~4张统计卡片（样本数/覆盖率/异常率/金额合计等）
- 数字用大字号 + 色彩编码（绿色正常/黄色警告/红色异常）

### 引导与提示
- 复杂底稿顶部蓝色渐变引导区（序号步骤，2列grid）
- 源模板方法论红字→琥珀色左边线+浅黄背景嵌入对应区域上方
- 编制提示→`<details>`折叠底部（蓝左边线+浅蓝背景默认收起）

### AI辅助
- 每个section标题行右侧放🤖AI按钮（section-header-row flex justify-between）
- 调POST /api/workpapers/{wpId}/{cycle}/ai-generate（传sectionId+上下文）
- 弹确认预览Dialog再填入（不直接覆盖）
- aiHealth检查：禁用降级提示而非报错

### GtIndexChip
- prop名是`value`（不是wp/wp-code/label）
- 聚合包内部sheet(D4-1/D4-2等)不能用GtIndexChip跳转（非独立wp_code）→用静态el-tag
- 点击跳转到目标底稿（resolve wp_code→router.push）


---

## 从 memory.md 下沉的踩坑铁律明细（2026-07-29 精简分流）

> 原 memory.md「踩坑铁律（高频）」全文，逐字保留。memory.md 仅留一句索引指向本节。

## 踩坑铁律（高频）

### 后端
- **大文件导入期间禁改后端代码**→ uvicorn reload 杀 worker
- **🔴 FastAPI路由顺序铁律(2026-07-28,函证match-queue 500)**：`GET /{param}` 会吞掉所有在它之后注册的同级字面路径如 `/match-queue`/`/batch-sync`→字面路径必须注册在参数路径**之前**；且参数路径入口的 `uuid.UUID(param)` 必须包在 `try/except ValueError → 404`（不能裸抛，否则被 generic_exception_handler 包成 500）。已修：confirmations.py 把 match-queue 路由移到 `/{confirmation_id}` 前+get_confirmation 加 UUID 解析保护
- **✅ 底稿粗裁「未生成」修复(2026-07-24,procedure_service.py::_resolve_wp_ids,AST OK+helper真实数据验证,未commit/未Playwright)**：`ProcedureTrimming.vue`(底稿粗裁与委派)操作列 `row._applicable && !row.wp_id`→"未生成"。**根因=LEAP合并程序**:一行代表多张连号底稿,编码用"起至终"(如`D2-1至D2-4`/`D2-6至D2-13`/`D4-*`),该区间串在wp_index无单一对应底稿→`_resolve_wp_ids`(WpIndex.wp_code.in_)回填wp_id失败→"未生成"(而D0/D1/D3科目级单码能匹配故正常显示"程序裁剪")。**修复=`_resolve_wp_ids`三级解析(控制台实际入口位置)**:①精确匹配 ②`_expand_range_wp_code`区间码展开(`D2-1至D2-4`→构成码[D2-1..D2-4])取首张已生成底稿 ③`_parent_subject_code`科目级母底稿回退(子/区间码无构成底稿→`D2-5`/`D2-6至D2-13`→`D2`、`D4-*`→`D4`,与D0/D1/D3同级进该循环程序表控制台)。三级全落空才保留None(真未生成)。纯追加不改精确匹配行,全循环通用。**范式**:区间/合并编码(含"至")解析必须展开构成码+母码回退,不能只做in_精确匹配。
- **event_bus publish 只传 EventPayload**；轻量通知用 broadcast_raw
- **asyncpg不支持IN tuple参数**：必须用`= ANY(:codes)` + `list(...)`
- **router_registry 必查**；**service 只 flush 不 commit**
- **新增 componentType 必须同步更新 VALID_COMPONENT_TYPES**
- **Bundle wpIdMap必须用item.wp_id不能用item.id**
- **D~N专属组件必须有RENDERER_DISPATCH注册**（否则被onlyoffice-sheet吞掉）——C类同理！c1-entity-level-control曾因缺render策略py+DISPATCH注册导致前端只显示OO。**C22再次踩坑：_c22_itgc.py写好但忘了在__init__.py import+注册到DISPATCH dict**
- **🔴 新增 item_id 前缀必须在 checklist_responses.py 白名单注册**：C23A-/C24-/C25-/C26-/C22. 前缀已改为 `pass`(跳过校验)，因为这些专属组件存freeform文本(分析结论/类别/要素等)。其他新专属组件的 item_id 前缀仍需在保存端点的校验链中添加对应 `elif` 分支或 pass
- **🔴 独立子底稿(如C23-1/C23-2)必须在wp_code_overrides中也映射到父组件**：平台可能把多sheet工作簿拆成独立底稿(各有wp_id)，不映射则走OO兜底。**C24-0~C24-5同理已加入**
- **🔴 多底稿共享数据问题**：C24子底稿(C24-3跳号等)各有独立wpId但分录数据存在主C24下→selfLoad数据为空→解法：selfLoad结束后如果journalEntries空+非程序表页→自动调loadFromLedger()从序时账拉取
- **D~N专属组件不能有内部el-tabs**：接sheetName prop用v-if分发
- **🔴 禁止用PowerShell Set-Content/Get-Content操作Vue文件**：会破坏UTF-8编码(中文变乱码)→编译报错。必须只用str_replace工具修改文件内容。C24曾因`-replace`+`Set-Content`导致全文件乱码需git checkout恢复
- **🔴 专属组件复盘3查（F5血泪）**：①双模式别漏——主入口HTML sheet顶部必须放el-segmented(HTML/OO)+useXDualMode，否则Req双模式回归且composable变死代码 ②EventBus跨表值(如审定成本)必须持久化到checklist_responses(独立item_id)+render策略回读seed，只靠同会话事件刷新后丢失 ③TB自动取数字段(只读)必须真接线：render策略查tb_balance(get_active_filter)→html_data返回→FormData提取→组件watch seed setTbValues，光有setter没人调=假只读手填
- **🔴 formula-lib 开发踩坑(可复用)**：①PG模型在sqlite跑PBT须每文件贴`SQLiteTypeCompiler.visit_JSONB=visit_JSON`+`visit_ARRAY→TEXT`+`visit_UUID=visit_uuid`——应抽公共conftest fixture别复制；②Hypothesis与function-scoped async fixture不兼容→用同步`_run(coro)`包装+每example新建StaticPool内存引擎再dispose隔离；③JSONB字段就地改dict不触发ORM脏标记,必须`obj.detail={**obj.detail,...}`重新赋新对象才落库；④V100给表加列会打破`orm_cols==V052基线`契约测试,断言改`V052∪V100扩展`各列对各自迁移DDL校验；⑤Windows GBK控制台`print("✓")`直接崩→用`[OK]`；⑥并行子代理创建同一新文件会竞态(engine.py被2.2和8.1双写),`[-]/[~]`进行中标记不该解锁下游wave；⑦动手前codegraph核实design假设:"18处evaluate_formula待迁移"其实Phase1已迁完/"预设库DB表"其实V100没建(改文件seed+读时收敛)——至少2个任务前提是错的；⑧四表库只读除定义层guard还需engine执行期兜底(auto_calc目标为四表库→跳过回填不改值);⑨vitest http mock空值须`{data:null}`非`{data:{data:null}}`(composable `data?.data??data`回退会把包装当真值);⑩RFC5987校验勿用`email.get_filename()`(同时有filename=和filename*时返ASCII回退名)→用字节级`unquote_to_bytes→decode`
- **account_package_registry sheets顺序=目录行顺序**
- **导入导出composable必须用http(axios)不能用原生fetch**（无Authorization header→401）
- **🔴 导入导出死链三查(2026-07-22 K5血泪)**：手写导入导出前端调用前必须核实——①`sheet`是后端`Query(...)`参数不是body！须`http.post(url,null,{params:{sheet}})`+导入的sheet走params不进FormData(写body→FastAPI收不到→422)；②后端`_XX_SPECS`(create_cycle_import_export_router)必须含该sheet否则400「不支持的sheet」；③新字段须加进`_cycle_import_export_common.is_numeric_field_key`白名单否则数值被当字符串。**diagnostics全清+Vite200但运行时422/400死链**——前端看着对不代表通。正解范式=直接复用`useK5ImportExport`(用params+parseFilenameFromHeader)别手写。K5曾5组件全写成body→全死。多区块检查表(K5-4/5/6)导入导出只覆盖主动态行表(其余政策/历史/假设区块页面直接编辑,spec的storage_field对齐前端remark)
- **🔴 exceljs前端动态import踩坑(2026-07-12)**：package.json声明不等于已安装!`node_modules/exceljs`曾不存在→Vite `Failed to resolve import`(无论`@vite-ignore`还是抽独立文件都无效)。根因=仅commit了package.json声明未跑`npm install`。修复=`npm install exceljs`+重启dev server。铁律:**新增前端依赖后必须验证node_modules/xxx存在**；导出逻辑已抽到独立`exportFormulaTemplate.ts`(避免巨型Vue文件chunk问题)
- **StreamingResponse中文文件名必须RFC5987编码**
- **🔴 禁止逐行存储大量数据到checklist_responses**：C24-5异常分录曾逐行存34万×3字段=102万行→selfLoad 14秒。改为JSON打包存1条(`C24-5-anomaly-notes`)。规则：>100行的动态数据必须JSON打包或不存(从源重算)
- **🔴 render-config慢/并发请求全被拖到8-16s根因=同步openpyxl阻塞事件循环(2026-07-14,commit e3c391a1)**：`wp_render_config.py`为多sheet底稿排tab顺序,每次请求都`openpyxl.load_workbook`同步加载整册模板(J1 23-sheet约0.4s)。同步操作卡住整个async事件循环→并发的checklist-responses(19行简单查询)/active-job也被连累到8s,render-config叠加16s。**诊断法**:①先测DB(实测<5ms排除数据/DB慢) ②隔离profile impl(cProfile sort by cumulative,一眼看到openpyxl占0.42s/0.46s) ③live并发实测。**修复**:sheet排序按`(path,mtime)`模块级缓存(`_get_template_sheet_order`),openpyxl每模板只加载一次→warm 0.46s→0.03s,并发8-16s→<100ms。**铁律:async请求热路径禁止裸调同步openpyxl/重文件IO,必须缓存或asyncio.to_thread;简单查询却慢=找事件循环阻塞源不是查DB**。**🔴 二次复发+根治(2026-07-14,同wp J1 9e783423再现7.5s)**:缓存不够——**首次加载仍在事件循环上同步执行**(heartbeat实测单次冻结循环243ms,冷缓存竞态叠加到秒级)。①`_get_template_sheet_order`改`await asyncio.to_thread(...)`彻底移出事件循环(循环最大阻塞243ms→71ms)。②**整册专属组件N倍冗余渲染**:J1 14 sheet全路由同一`j1-employee-compensation` renderer且输出与sheet无关(组件内部按sheetName分发同份html_data),却逐sheet跑14次=28次DB查询→加`_dedicated_render_memo`按component_type单请求内memo,renderer 14→1次(省26次查询)。惠及全部`_WHOLE_WP_MULTISHEET_DEDICATED`(C1/J1/J2/J3/K10-K13/H5/H7等,H7 26 sheet收益更大)。**诊断利器=heartbeat探测**(5ms tick协程记录max gap=事件循环冻结时长,比cProfile更直观定位阻塞)。**🔴 三次复发根因实为冷启动惰性导入(2026-07-14,同wp J1)**:重启后首个render-config仍7s但warm=20ms/12并发burst=210ms→证明是**冷启动一次性代价**非持久逻辑。`_get_render_config_impl`内`from app.routers.wp_render_strategies import RENDERER_DISPATCH`一次性导入100+策略子模块(+传递依赖openpyxl/resolvers)发生在**首个请求**内,首屏并发争抢事件循环→7s。**根治=main.py lifespan启动预热`_warm_render_caches()`**(在"Ready"前import wp_render_strategies+`_load_templates()`),首请求不再付导入代价。诊断法铁律:**warm快+cold慢=冷启动惰性导入,预热到startup;隔离profile impl快但HTTP慢=看全ASGI栈/首请求导入,用httpx ASGITransport+create_access_token直连app测全链**。**⚠️ dev后端实际带--reload(start-dev.bat run_uvicorn.py --reload),改后端自动重载不用手动重启(与旧memory"无--reload"记录相反,以netstat cmdline实测为准)**
- **🔴 "程序表模板缺失 table_code=J1"根因=sheet名空格不匹配(2026-07-14,非模板真缺失)**：J/G/H/I/L/M/N/S循环**无JSON程序表模板**(procedure_table_templates.json仅A/B/C1/D/E/F/K共62个),但`_a_program.py`会**fallback从源xlsx `extract_program_rows`提取程序行**(J1的"应付职工薪酬实质性程序表 J1A"sheet实测提到18行真实审计程序)→内容其实在。真bug:前端`cycleProcedureSheets.ts`注册的sheetLabel`应付职工薪酬实质性程序表J1A`(无空格)与classification/xlsx真实名`应付职工薪酬实质性程序表 J1A`(**有空格**)不一致→`useCycleProcedureConsole`带`sheet_name`精确过滤render-config→`cls.sheet_name != sheet_name`全落空→返回空sheets→前端GtAProgramConsole兜底`fetchProcedureTableData`→`extractTableCode`正则`/[A-S]\d+/`把"J1A"截成"J1"→请求不存在的`/procedure-tables/J1`→告警+空程序表。**根治=render-config的sheet_name过滤改"忽略空白"匹配`_sheet_name_matches`**(精确优先,回退去掉空格/全角空格/tab比较,不误匹配-原版后缀)。实测spaceless/withspace两种名都返18行。**教训:sheet名过滤用精确==对空格敏感;前端注册表label与xlsx真实sheet名常差空格→过滤要容错**
- **✅ G/H/I/J/L/M/N循环程序表JSON模板已生成(2026-07-14,58个)**：`procedure_table_templates.json` 62→120。原仅A/B/C1/D/E/F/K有JSON模板,G/H/I/J/L/M/N只能render时openpyxl从源xlsx兜底(冷启动开销)。**生成器`backend/scripts/generate_cycle_procedure_templates.py`**(可复用):遍历`wp_templates/{G,H,I,J,L,M,N}/*.xlsx`程序表sheet→`extract_program_rows`抽真实致同审计程序→转D4A同构JSON(seq/content/ref_index/auto_data_source:null/applicable_default)。**content保留「（1）（2）」子步骤供前端折叠展开**(由program_desc+sub_steps反向重建,实测J1A 5/18项可折叠)。**key=sheet级编码**(与`_a_program.render`的`get_template(_sheet_code)`一致:G1A/H1A/J1A...)。**关键坑**:①**base==file_wp_code约束**过滤源工作簿混入的它科目遗留sheet(J2文件里的L2A/M10文件里Q10A修订前/N2里O1A原底稿);②exclude markers加"修订前/原底稿/（原";③**M1特例**:源sheet名是"应付股利实质性程序表M1"(无A!),key="M1"(render正则不匹配M1→fallback wp_code M1;且GtM1DividendsPayable直用GtAProgramConsole空数据→兜底/procedure-tables/M1→extractTableCode("M1A")去A→"M1"→get_template("M1")✓,两路径都对齐"M1")。**S循环排除**(专项底稿S34有数十子检查表非标准*A程序表+未在cycleProcedureSheets.ts注册,需逐sheet人工甄别,避免污染)。纯additive(62旧key字节不变A16 identical),2个A16 PBT失败是pre-existing(测_resolve_auto_values逻辑非模板)。JSON改动经_load_templates mtime热重载自动生效不需重启。实测J1A render 18程序(5折叠+13索引chip)31ms来自JSON
- **🔴 后端直接INSERT checklist_responses必须带project_id**：该列NOT NULL。`INSERT ... ON CONFLICT (wp_id,item_id) DO UPDATE`即使命中冲突走UPDATE,PG仍先校验INSERT行的NOT NULL→漏project_id报`NotNullViolationError`(被信封包成500"服务器内部错误")。修复=先`SELECT project_id FROM working_paper WHERE id=:wp_id`再带入。J1-8导入导出踩过(commit b86fa5dc)。debug信封500须写独立async脚本用app.core.database.async_session复现拿真traceback
- **GtOnlyOfficeSheet健康检查响应解析**：`health.data?.data?.healthy`双层兼容
- **OO sheet_name→wp_code解析必须头尾双匹配**：尾部`re.search(r"([A-Z]\d+(?:-\d+)?[A-Z]?)\s*$")`匹配"xxx**D4-5**"；头部`re.match(r"([A-Z]\d+(?:-\d+)?[A-Z]?)\s*")`匹配"**C14-2**评价控制偏差"——两处端点(config+wopi)必须同步
- **聚合包内独立sheet三端点wp_code必须一致**（config/WOPI/callback统一用sheet级解析）
- **project_assignments列名是staff_id不是user_id**
- **结构化章节数据不能存到textarea content**（用独立item_id分别存checklist_responses）
- **CREATE TABLE IF NOT EXISTS 遇旧表列不同不报错但 CREATE INDEX 会炸**：迁移必须用 DO $$ + information_schema 检测列存在性再 ALTER 补齐/RENAME
- **🔴 render策略SQL列漂移致500（2026-07-11）**：17个render策略(_h1~_h5/_i1~_i6/_k8~_k13)查`p.applicable_standards`(已改名`applicable_standard_v2`)→asyncpg查询失败中止事务→级联render-config 500→阻断H1-H5/I1-I6/K8-K13全部HTML渲染。修复`p.applicable_standard_v2 AS applicable_standards`(保语义,前端消费不变)。**D5也中招(2026-07-13 merge后发现,同修)**。**追加:applicable_standard_v2实际存JSONB(dict)非string→.lower()崩AttributeError,D5追加isinstance防御+dict时取.get("type","")**。**教训:render策略里的裸SQL(sa.text)不受ORM/契约测试保护,列改名会静默漏;Playwright实测render-config才暴露**。Playwright验证H1-1/H5-1审定表渲染全绿。工作正确的策略(K5/K7/L/M)只查client_name/audit_year/business_category不含applicable
- **✅ M/N审定表render策略「TB取数失败」批量修复（2026-07-25，9 render策略+m8，diagnostics全清，dev--reload自动生效，未commit）**：用户报M10 render `TbBalance has no attribute begin_balance`。根因=这批M/N审定表render策略从「查trial_balance」模板复制来却指向`tb_balance`→列名全错，因包在`try/except`里不崩只静默返0+打`TB取数失败`warning（每次渲染都触发=用户"老出现"）。**两类**：①**movement型(查对表tb_balance错列名)**=m4/m5/m6/m7/m9/m10/n1/n2策略→`begin_balance`→`opening_balance`(用`.label("begin_balance")`保下游契约不变)、`end_balance`→`closing_balance`、`standard_account_code`→`account_code`(这是trial_balance的列,tb_balance用account_code) ②**adjudication型(查错表)**=m8要`unadjusted_amount/aje_adjustment/rje_adjustment/audited_amount`全是trial_balance列→整块`TbBalance`改`TrialBalance`(含import)。**🔴 未修(更深一层)**：`n1_deferred_tax_assets_service.py`/`n2_taxes_payable_service.py`/`n3_deferred_tax_liabilities_service.py`的`get_tb_data`/`get_cross_wp_total`等辅助函数同款错列名+叠加`get_active_filter(project_id)`签名错(它是异步四参`(db,table,project_id,year)`被当同步单参→静默失败返0)；这几个函数无router调用方(次要)+签名缺year需线程化才能正确修。**范式**:①`tb_balance`列=opening_balance/closing_balance/account_code/debit_amount/credit_amount(无begin/end/standard_account_code/unadjusted/audited);`trial_balance`列=standard_account_code/unadjusted_amount/aje_adjustment/rje_adjustment/audited_amount/opening_balance ②要期初/期末/借贷发生额→查tb_balance;要未审/AJE/RJE/审定→查trial_balance ③从模板复制render策略必核对表↔列匹配,`try/except`吞异常会把列名错变成静默返0+warning(非崩溃)易被忽略。
- **schema漂移修复模式**：`db_extra`类型漂移=DB有列/表但ORM未定义→在ORM模型中补齐列声明即可（不需要新迁移）；V033遗留列(`is_locked`/`bound_dataset_id`)已补入WorkpaperSnapshot；V095 `review_threads`表+`review_messages.thread_id`/`sender_role`已补入phase10_models；V099 `target_user_id`/`target_user_name`/`target_role`已补入ReviewMessage；**V100 formula-management-library**(迁移已跑但功能未实现)遗留10项db_extra已补入`workpaper_models.py`：WpFormula 7列(formula_type/last_computed_at/refs JSONB/issue_description/hint_text/formula_source/reference_formula_id)+3新ORM模型(DraftMarker/DraftRefreshAudit/DraftRefreshSnapshot)，`SchemaDriftDetector.scan()`验证 total drift=0

### 前端

- **✅ 人员档案(StaffManagement.vue)表格列全被压窄/表头截断/头像裁半修复（2026-07-28，单文件，get_diagnostics清+Vite200，未commit）**：用户报列「都显示不全」（头像半圆裁切+「工号→工...」「CPA→CP」「年限→年」）。**根因=el-table 在 `gt-fade-in` 动画中挂载算错列宽**：页根 `.gt-staff-page gt-fade-in` 用 `transform:translateY(16px)→0`，el-table 挂载时按 `offsetWidth` 计算列宽写进 `<colgroup><col width>`，恰在带 transform 的祖先动画进行中量到被压缩的宽度→所有列写窄且不再重算。修=`el-table` 加 `ref="staffTableRef"`+`relayoutTable()`(nextTick→`doLayout()`)+根节点 `@animationend="relayoutTable"`(动画落定重量)+`loadStaff` 数据加载后也调一次(覆盖后续筛选/翻页无动画场景)。**范式**：el-table 放在 `transform` 动画容器(`gt-fade-in`/`gt-scale-in`/`gt-slide-in`)里挂载会算错列宽(列压窄/头像裁切/表头截断)——加 `@animationend` 触发 `tableRef.doLayout()`+数据加载后 doLayout；同款 `gt-fade-in`+el-table 列表页若现列压缩套此修法(get_diagnostics/Vite200 查不出,唯浏览器渲染或列宽压缩暴露)。
- **✅ 工作台点函证「加载底稿失败(cancelled)」修复（2026-07-25，WorkpaperEditor.vue+WorkpaperEditorShell.spec.ts，get_diagnostics清+Vite200+shell 10测绿+Playwright实测E0→/confirmation无错，未commit）**：从工作台点货币资金函证(E0，`_WP_CODE_OVERRIDE["E0"]=confirmation-hub`)落"加载底稿失败(cancelled)"。**根因=confirmation-hub重定向从不触发**：`WorkpaperEditor.onMounted`的重定向判`componentType.value==='confirmation-hub'`，但`componentType`由`fetchComponentType`读**detail端点**(`GET /working-papers/{wp_id}`→`WorkingPaperService.get_workpaper`**不返回component_type**)→回退`'univer'`→重定向恒不触发→E0落Univer路径→render-config被cancel。confirmation-hub的真实type只能经**classification端点**(`derive_component_type`应用`_WP_CODE_OVERRIDE`)派生，但`wpClassification.load()`在重定向判定**之后**才跑。**修**：①`wpClassification.load()`移到重定向判定**之前**(await) ②重定向判定加`|| wpClassification.componentType?.value==='confirmation-hub'`(optional chaining防mock缺字段)。惠及D0/E0/F0/G0/H0/K0/L0全部函证枢纽。**范式**：detail端点(get_workpaper返回dict)**不含component_type**，编辑器识别confirmation-hub等必靠classification派生(经_WP_CODE_OVERRIDE)；凡依赖`componentType.value`(来自detail)判type的逻辑都拿不到override类型，需读`wpClassification.componentType`。**pre-existing无关失败**：`useEditorMode.spec.ts`断言`HTML_COMPONENT_TYPES`恰79项(实际212=stale硬编码count drift，未碰该set)。
- **✅ 函证中心「从底稿导入」批量创建函证对象（2026-07-25，confirmation_service.py+confirmations.py+audit_platform_models.py+ConfirmationHub.vue+14单测，get_diagnostics清+Vite200+后端AST OK+Playwright+HTTP round-trip，未commit）**：用户报从货币资金点函证落到项目级hub后「新建函证」全手工，函证很多时太慢，要从联动底稿带入。**方案=函证候选从tb_aux_balance按核算维度提取+复用既有batch-sync批量创建**(不新造创建路径)。①后端`list_confirmation_candidates(db,pid,confirm_type,year)`：`_CONFIRM_TYPE_ACCOUNT_PREFIXES`(bank→1001/1002/1012、receivable→1122/1121、payable→2202/2201、loan→2001/2501/2502)+`get_active_filter`查tb_aux_balance+**按`aux_dimensions_raw`分组**(每唯一多维组合=一个函证对象)+`_build_candidate_name`(主名=首个非数字维度值[优先金融机构/客户/供应商/单位关键词]+账号附括号"中国银行（182769895215）")+book=abs(closing_balance)跳过零空。②端点`GET /confirmations/candidates`(**须注册在`/{confirmation_id}`前**否则"candidates"当ID→500)。③ORM补`aux_dimensions_raw`列(修db_extra drift)。④前端加「从底稿导入」按钮+弹窗(选类型→拉候选→el-table多选,已存在行禁选+tag,默认勾选可导入→batch-sync)。**实测**:候选bank=21/receivable=764/payable=775/loan=13;HTTP round-trip(created=2→列表出现→删除清理无污染);Playwright(弹窗21候选全预选)。14单测。**范式**:函证对象候选源=tb_aux_balance按`aux_dimensions_raw`分组(唯一组合=一对象,防多级aux双算)+per-type科目前缀映射;创建复用batch-sync(counterparty+type dedup,已存在跳过);新路由`/candidates`须在`/{id}`前注册。**🔴 PowerShell `$pid`只读自动变量(=进程ID),脚本`$pid='uuid'`会静默clobber成进程号→500,必用`$proj`**。**UI美化(2026-07-25续)**:ConfirmationHub按列表页铁律打磨——13px统一+标题主色左强调条+「共N项」计数+图标按钮(📥从底稿导入plain/➕新建函证primary)+表格去border外包`el-card shadow="never"`(圆角8px/body padding:0/浅灰表头)+类型彩色round tag(银行蓝/应收绿/应付橙/借款红)+**操作列3按钮从填充改单行link按钮**(修原来200px挤成两行的折行丑)+el-empty空态。未commit。
- **🟢 D2-3 坏账准备列对齐源模板(2026-07-12)**：`currentTransferIn`→`currentOtherIncrease`(其他增加G列)+新增`currentOtherDecrease`(其他减少J列)+删`currentRecovery`(源模板无独立"收回"列)。分区标题改"一、按单项计提"+"二、信用风险组合计提"(自定义动态组合:用户可增删+命名+选账龄段,存`D2-bd-custom-groups` JSON)。旧JSON通过`raw.currentTransferIn` fallback向后兼容。公式:`期末未审=期初审定+计提+其他增加-转回-核销-其他减少`。列设置popover已加(14列checkbox+隐藏空列)
- **🔴 F5+G类 ref-unwrap 全面清扫（2026-07-11 续）**：复盘昨天 DEF 修复发现 **F5 全家族(9 tab)被误标"安全"实为真崩**——props 声明 `allResponses:Ref<Map>`+父组件 `:all-responses="allResponsesRef"`(computed 模板绑定自动解包成纯 Map)→ 子传给 composable → `allResponses.value.get()` 对 Map 取 `.value`=undefined→崩。修:props 改 `Map`/`string` 解包类型 + `toRef(props,'x')` 重包喂 composable(对齐 D4/D5)。**G 类逐组件(G0~G14,~15 组件 55+ tab)子代理并发审计+修复+gold打磨**,真 bug 分布:①G1TabDetail/Adjudication/FairValueTest 嵌套-ref(`const x=useGx()` 后模板 `x.rows`/`x.total.foo` 无 `.value` 非解构→el-table 收 ref 空表、computed.foo undefined 空白;修=**解构到顶层** `const{rows,grandTotal,...}=useGx()`) ②G4 SPPI 3 tab 声明父级从不传的 `allResponses/debouncedSave` props→挂载 `.get()` 崩(修=自包含 useG4SppiFormData) ③G5-9/G5-10、G6TabSppiTest/InventoryRollForward **prop 名不匹配**(父传 `:readonly`/`:is-readonly`/`:html-data` 子声明 `isReadonly`/`readonly`/`data`)→只读态失效/数据不加载 ④G13TabDetail `v-model="detail.searchQuery"` 漏 `.value`→搜索崩。**多数 G 组件(G2/G3/G7/G8/G9/G10/G11/G12)本就规范**(模板显式 `.value` 或已解构),仅补 gold 打磨(审计目标 el-alert/编制提示 details CAS/13px/auto-calc-col 灰底虚线title/GtIndexChip canonical/共N行)。铁律:**嵌套 ref 三判**——`obj.refProp` 绑模板(尤其 `:data`/`v-model`/`{{obj.computed.x}}`)必须①解构到顶层 或②显式 `.value`;Vue 只解包顶层 render-context ref(context7 官方文档确认,`{{obj.id+1}}` 不解包)。**父子 props 契约必对齐**(prop 名一致 + 父确实传 + 子不声明父不传的必需 prop)。**单测传真 ref=假绿,get_diagnostics 查不出运行时,必 Playwright**(本轮 admin/admin123,3030+9980 已起,但深度导航到 G 数据未做)
- **🔴 已push `3d8fba7c`（2026-07-11）**：ref-unwrap契约清扫+CI守卫+DEF/G/K修复+voucher 合并 origin(acnr-consumer 100/100+advanced-query 85/85+formula-lib+V100~V102)。合并冲突处理:F5TabMajorAdjustment 取 origin 重构版后 guard 又检出 ref-unwrap 7处→重修;F2×3取 origin;memory 手工合并。全树 guard exit 0
- **🔴 ref-unwrap 契约守卫 + K 系列扩面修复（2026-07-11 三件套复盘）**：Playwright 实测确认 G1-1/G1-2 修复生效(合计/表格正常渲染,0 console error,admin/admin123 登录→项目→G投资底稿逐 tab)。**新增 CI 守卫 `backend/scripts/check/check_wp_ref_contract.py`**(零依赖,`--strict` 阻断;已挂 `governance-checks.yml` job `wp-ref-contract-check`;Windows 需 `sys.stdout.reconfigure(utf-8)` 防 GBK 崩)拦两类客观反模式:①`defineProps` 把 allResponses/wpId/projectId/htmlData/isReadonly 声明成 `Ref<>` ②`props.x.value`(排除局部 `const x:Ref=ref()` 与 `typeof props.x==='string'?...:props.x.value` 防御式)。**守卫首跑揪出 DEF/G 之外同类真 bug 35 处/23 文件 → 已全修**:K5(9)/K6(4)/K7(6 含多处 .value get/set)/K8(1)/K9(2)/K11(1),父入口均 `const allResponses=ref(Map)`+模板 `:all-responses` 解包→子声明 Ref+喂 composable `.value.get()` 崩。修法统一:props 改解包类型+`toRef` 重包。全树 guard 现 exit 0。**三件套复盘结论**:该 bug 类反复穿过 spec 流程因 design 从不写"组件↔composable ref 契约"+tasks 靠单测(传真 ref=假绿)。改进=①ref 契约进 design 模板 ②CI guard 兜底(已加) ③新组件必 Playwright。**注**:嵌套-ref(模板 `x.rows` 无 .value)因需 AST 解析未纳入 guard,靠 Playwright+人工。**嵌套-ref 三向量 grep 排查法**(guard 抓不到,手工扫):①`:data="[a-z]\w*\.[a-z]\w*"`(el-table 绑 obj.prop 无.value,排除 v-for 循环项/reactive/form)②`v-model="(detail|adj|cmp|vc|...)\.[a-z]\w*"`(composable 常量 ref 属性无.value)③`[a-z]\w*\.(totals|summary|grandTotal|subtotal)\.[a-z]`(computed 对象嵌套无.value,排除 `.value.`)。全 workpaper 树扫描:**除 F2DetailSheet.vue 外全清**——F2DetailSheet 作者不一致(rows/filteredRows/searchText 带 .value,但 activeSegment/useVirtualScroll/totals/agingMismatch 漏),致段切换失效/列不渲染(v-if 比较 ref 对象恒 false 落 aging 分支)/合计空白,已补 .value 修复(commit 1175bbed)。**PowerShell `git commit -m "中文"` 控制台回显乱码但仓库存储正常**(GBK 渲染问题,勿 force-push 修消息)。
- **🔴 H~S 全循环 ref/selfLoad/导航系统性清扫（2026-07-11 续，4波12子代理并发）**：guard 全程 exit 0(props ref-unwrap 类已在 K5-K11 轮清完),本轮聚焦 guard 抓不到的 **selfLoad 键名 bug + 导航事件名 bug + 嵌套-ref + gold 打磨**。发现三类新系统性 bug:①**selfLoad 键名 bug**(H1-H5 首现,本轮扩面):后端 render 策略输出 responses 键名是 `responses_snapshot`(部分 `checklist_responses` dict),但主入口 selfLoad 只读 `allResponses`(或用 for...of 当数组遍历)→审定/明细/检查表 seed 永久空白。修:主入口加 `_mergeResponses(map,src)`(兼容 dict/array)合并多键,htmlData+render-config sheets 两分支都合。**中招并已修:H6/H8/H9(htmlData 分支)、K12/K13(真 bug)、K1/K3/K4/K10(未来兼容)、N2/N3/N4/N5**。**豁免(走 /checklist-responses 端点直取,勿乱改):K2/H10/I/J/L/M/S 全部**——子组件各自 useXFormData().loadData() GET 端点,主入口 selfLoad 仅预热丢弃。②**导航事件名 bug**(L/M/N 类全中招):主入口 `emit('navigate',...)` 但 GtWpRenderer 监听 `@navigate-sheet`(onChildNavigateSheet)→二级导航(目录行点击+返回目录按钮)全静默失效;且子 tab 的返回目录按钮仅 Index 绑 @navigate。修:主入口 defineEmits+handleNavigate 改 `navigate-sheet`,全部子 tab 补绑 `@navigate`(N 类双绑 @navigate+@navigate-sheet 兼容混用)。**中招并已修:L1-L8/M1-M10/N1-N5 全部主入口**(含 memory 记录的 N5TabIndex 目录跳转遗漏)。S 类用内部 el-tabs 不 emit navigate→不适用。③**Bug C 持久化断路**(H6/H8/H9):子 tab `emit('save')` 但主入口从不绑 @save(或只写内存 Map 无 http)→checklist 数据永不落库。修:主入口加防抖 persistResponse+PUT+provide('saveResponse')。④**K12-1 是 stub**(el-empty 待实现,composable 早存在)→比照 K13TabAdjudication 完整实现(6301 损益贷方+交叉验证+TB回写+EventBus+gold)。⑤**gold 打磨**:H/K/L/M/N/S 各审定表/内容 tab 补审计目标 el-alert(此前唯一系统缺口),编制提示 details/13px/auto-calc-col/GtIndexChip canonical/共N行本已达标则保留。**遗留(如实报告,非本轮范围)**:H7 25 tab 全 el-empty 占位符(前端未实现);K4/K10-6 抽凭引擎 stale API(K4 已重接,K10-6 待);S12/S13/S14/S15/S20/S21 子表无 checklist_responses 持久化接线(既有设计缺口,主入口丢弃后端 responses_snapshot,属 feature 级改造)。**全程 str_replace(无 PowerShell 破坏 UTF-8),guard exit 0,改动文件 get_diagnostics 零错误,均静态三方对照核验(主入口 selfLoad 键+子 props 契约+composable return 键+模板绑定+后端 render 输出键)——无浏览器未做 Playwright,待 start-dev.bat 起 3030+9980 后逐 tab 实测导航/seed 填充/持久化。**
- **🔴 H~S 遗留三项补齐（2026-07-11 续，3+1子代理）**：①**H7 25个占位tab全部实现**(此前全 el-empty 待实现)——composable 逻辑层已存在(useH7*),子代理按 H5/H3 范式建 UI+接 composable:core(审定成本/公允双版本+明细成本/公允双区段+调整+分析+附注上市/国企)、depreciation(直线法不含减值/含减值/折旧分配)、fairvalue(公允复核)、inspection(增加/减少成本公允双版本+政策检查CAS5+关联交易+互转审核)、impairment(减值测算/可收回金额)、production(产量记录H7独有,变动率>30%预警)、stocktake(计划/检查/小结)。**关键发现:H7 sheet级 composable 全是 getNum/getString 薄stub(非H5式完整逻辑层),故行模型/合计/勾稽在组件内自建,ENGINE(useH7DepreciationEngine/TransferEngine/FormulaEngine calcXxx)真复用**。TB回写1621+substantive:adjudicated EventBus+双计量模式切换。主入口补 persistResponse+provide saveResponse/generateAiText(此前缺失),**修 H 族路径 bug(`http.put('/workpapers')`缺/api→dev proxy不达→改`/api/workpapers`)**。②**K10-6抽凭引擎重接**(stale `v-model:visible`+`sheet-key`→wrap el-dialog+account-code=6117+phase+year+@filled,对齐K4/K8/G6)。③**S12-S21子表持久化接线**(此前主入口丢弃后端responses_snapshot,子表本地ref刷新丢失)——新建共享`useSExpertPersist.ts`(inject saveResponse+seedOnMount+parseResponseValue兼容JSON);6主入口(GtS12/13/14/15/20/21)加allResponses ref+_mergeResponses合并responses_snapshot/checklist_responses+防抖800ms persistResponse(PUT `/api/workpapers/.../checklist-responses`带/api前缀)+provide;~30子表 inject saveResponse+seedOnMount逐字段@change持久化;后端 checklist_responses.py 白名单加 `S12-/S13-/S14-/S15-/S20-/S21-` pass分支(存remark+conclusion=null)。guard exit 0,改动get_diagnostics零错误,S类vitest全绿(41+75),静态三方对照核验未Playwright。**注:H7 sheet composable薄stub若要承载逻辑需后续扩充(非本次UI范围);持久化真落库+刷新恢复需start-dev.bat实测**
- **🔴 DEF精美化Playwright实测发现4类真bug并修复（2026-07-11）**：①**acnr barrel漏导出useAcnr**→GtIndexChip `import{useAcnr}from'@/services/acnr'`失败→全站白屏(路由错误)；修`services/acnr/index.ts`补`export{useAcnr,...types}from'./useAcnr'`。②**D5/D6/D7+F1 ref-unwrap崩**(D3血泪重演):tab声明`allResponses:Ref<Map>`+传`props.allResponses`给composable做`.value.get`,但entry模板`:all-responses="allResponses"`自动解包ref→子收到Map→`.value`undefined崩;修:prop改`Map`+`const allResponsesRef=toRef(props,'allResponses')as Ref<Map>`喂composable(对齐D4)。**F2/F4/F5本就安全**(F4 toRef/F5传ref intact)。③**shared/CycleTabAdjudication嵌套ref模板bug**(F4-1/F1审定走此config组件):`const adj=usePeriodAdjudication()`+模板`:data="adj.rows"`,嵌套ref不解包→el-table收到ref→"data2 is not iterable"崩;修:解构到顶层`const{rows,totalRow,...}=usePeriodAdjudication()`(顶层ref才自动解包)。**教训:composable返回值必须解构到顶层再用,勿`obj.refProp`直接绑模板**。④单测传真ref全绿=假绿,**必Playwright逐tab实测**
- **🔴 composables 相对导入层级 bug（2026-07-11 K类Playwright实测重大发现）**：`workpaper/{cycle}/{sub}/*.vue` 大量底稿 tab 用**错 `../` 深度** import composables——如 `k1/core/K1TabAdjudication.vue` 写 `../../../composables/`(3级→解析到不存在的 `src/components/composables/`)，正确应为 `../../composables/`(2级→`workpaper/composables/`)。Vite transform 报 **500「Failed to resolve import」→ ErrorBoundary 崩溃**，整个 tab 白屏。**血泪教训:get_diagnostics(Volar)/vitest/guard 全都漏检**(Volar 经 tsconfig 解析宽松、vitest 走自己的 alias、guard 只查 ref-unwrap)——**唯有浏览器 Vite 运行时/curl `/src/.../X.vue` 看 http 200/500 才暴露**。全树扫描 **125 文件/244 处**中招(G2/I2/K1-K6/L4-L8/M1-M9/N1 等,凡 `{cycle}/{sub}/` 2级目录用了3级 `../../../`,或 `{cycle}/` 1级目录用了2级 `../../`)。**修复脚本 `backend/scripts/check/fix_wp_composables_import_depth.py`**(按每文件相对 workpaper 深度计算正确 `../`×depth 前缀,正则 `(from ['"])((\.\./)+)composables/` 归一化;显式 UTF-8 读写不碰中文;`--apply` 写回/`--check` CI阻断)。已挂 `governance-checks.yml` job `wp-ref-contract-check` 加 step。K1-1审定表 Playwright 实测修复后 0 error 正常渲染。**判定 Vite transform 健康:curl `http://localhost:3030/src/components/workpaper/{path}.vue` 看 http_code(200好/500坏),比 get_diagnostics 更权威**。根因推测:代码预生成脚本模板用固定 `../../../` 未按实际目录嵌套调整。
- **🔴 vue-tsc CLI假报错 vs get_diagnostics vs Vite transform（2026-07-11 修正前记录）**：`npx vue-tsc --noEmit`默认OOM(需NODE_OPTIONS=--max-old-space-size=8192)吐级联假错。`get_diagnostics`(Volar)判TS/类型准，但**对SFC结构损坏/模板编译错误宽松放过**。⚠️**旧结论"GtReviewChecklist/D4TabProductMargin完好未损坏"是错的**——K类排查证实这两个文件确实是合并串行化损坏(script/template/style打乱交织),Volar/get_diagnostics/vitest全漏检,**唯有Vite SFC编译器(curl `/src/.../X.vue`看200/500)才暴露**。**判定崩溃类bug以全树Vite transform扫描为最终权威**(比get_diagnostics强,能抓模板内嵌引号/结构损坏/import解析失败)
- **🔴 K类底稿白屏崩溃系统性排查（2026-07-11 全树Vite扫描）**：用户报"K类很多bug"根因=一类Volar/vitest全漏、仅Vite 500暴露的崩溃。**全树扫描1559个workpaper .vue**(脚本:curl每个`/src/.../X.vue`看http_code),修前15崩(6 K+9其他循环)。**四类bug**:①**模板属性内嵌ASCII双引号**破坏Vue解析器(如`description="点击"+ 新增"添加"`)→改全角`""`,18处/15文件(K5/K6/N2/H8/H9/G4/G5/G6/D4)②**相对导入层级错**(voucher-sampling/GtGridSheet/F2SheetToolbar `../../../`多一级、GtIndexChip错在`common/`应`workpaper/`、F1错组件名`useF1VoucherCheck`应`useF1ComprehensiveCheck`)③**合并串行化文件损坏**(GtReviewChecklist全文重建/D4TabProductMargin的loadProducts函数重建,均从git干净基线+可见结构复原)④**缺失依赖**exceljs未在package.json(6文件用)→`npm i exceljs@4.4.0`⑤**非法el-tabs `<template #default>`**致tab-pane被忽略(B50)→进度div移出slot。验证:全树1559全200/ref守卫exit0/get_diagnostics净/Playwright K1审定表+K3-5/6+K6-3/7+K5附注+D4-8+A21全0error。**教训:`fix_wp_composables_import_depth.py`只覆盖`composables/`,voucher-sampling/GtGridSheet等错层级抓不到→CI应加全树Vite transform冒烟或扩成任意相对导入校验**。已commit+push `eef7f293`(30文件,含package.json exceljs@4.4.0+components.d.ts ElStatistic自动注册)
- **🔴 底稿崩溃第二轮(2026-07-11 其他循环Playwright实测)**:全树Vite扫描**必须同时扫`.vue`和`.ts`**(首轮只扫.vue漏了composable)。发现并修复:①**F1-7 useF1VoucherCheck导入名**——`useF1ComprehensiveCheck.ts`文件实际导出`useF1VoucherCheck`(文件名≠导出名),我首轮误改导入名致运行时`does not provide an export named`崩溃(**Vite transform 200查不出named-export不存在,只运行时ESM加载报错→只Playwright能抓**),已改回`useF1VoucherCheck`(commit 5cf285b1) ②**useG4MainInterestCalc.ts:297 `export interface`写在函数体内**(非法,esbuild `Unexpected export`)→删export改局部interface ③**useH0/K0/L0ImportExport.ts导入层级**`../../composables/`应`../../../`(confirmation/{sub}/composables/下需3级到workpaper) ④**useD2Detail.ts幻影`ElMessage2`**——源码4处`const{ElMessage}=await import('element-plus')`触发unplugin-auto-import碰撞消歧注入`ElMessage2`+不存在的`message2/style/css`→500(**源码grep不到ElMessage2是注入的**),改单个顶层`import{ElMessage}from'element-plus'`删4处动态import ⑤h7-registry-contract.test.ts截断补全。commit fc192f5c。**遗留:useC1ControlProperties.pbt.spec.ts committed 75个U+FFFD replacement char损坏(commit c4c78791,PowerShell `git show|Select-String`统计U+FFFD不可靠会漏,须python `raw.count(b'\xef\xbf\xbd')`)——纯vitest测试文件非运行时,不影响底稿渲染,需按原意重建未做**。已实测0 error循环:D2/E1/F1(含F1-7)/G1/G4(含G4-4/9/11)/H1/I1/J1/L1/M1/N1/N2/B50,+K类(前轮)。H1的`/api/projects/.../events?topic=control:...`404是既有SSE基础设施噪声非底稿bug。**Playwright会话约30-60min过期→重新admin/admin123登录**
- **🔴 D2类底稿打磨盲区（2026-07-10排查）**：D2各tab曾"建好但未打磨"——大量应可编辑单元格被写成只读文本`{{row.x||'-'}}`(质押/关联方/核销/坏账/ECL/凭证检查/披露/调整分录)，审计师无法录入。打磨检查清单(对照D1TabPledgeCheck标杆)：①审计目标el-alert ②tab-header+GtReviewTrigger ③字段全可编辑(下拉/日期/数字控件,计算列只读+tooltip) ④行级GtReviewDot+索引GtIndexChip ⑤跨表联动核对区 ⑥审计说明+结论+🤖AI+💬复核 ⑦编制提示details(CAS依据)。AI辅助需在`_dX_ai_generate.py`的`_SUPPORTED_SECTIONS`白名单+`_SECTION_PROMPTS`注册section，前端`useDXAiGenerate`同步section类型。坏账/ECL金额列可编辑但audited/unadjusted等计算列须只读。D2共14tab全打磨完成(104测试通过)。**Playwright实测(2026-07-10)发现并修复2个真实bug**：①**路由bug**:D2-7~D2-13缺失于`wp_code_overrides.json`→多sheet按`_SHEET_CODE_RE`提编码查`_sheet_ovr`未命中→OO兜底→HTML tab不可达。补映射后tab图标📄→💰。②**保存bug**:`useD2FormData.doSave`把`project_id: wpId.value`(wpId当project_id发送)→违反`checklist_responses.project_id`外键→500→D2 HTML数据从未真正落库(前端只弹toast)。改为`projectId?.value||undefined`(未传则服务端从wp_id推导)。实测:新增质押行→全单元格可编辑→PUT 200落库。**注意**:`wp_code_overrides.json`改动需后端reload才生效(`_WP_CODE_OVERRIDE=load()`import时只捕获一次,mtime热重载对importer失效)。**源模板示例内嵌已完成**:新建`D2ReferenceBlock.vue`(琥珀色方法论块)+`d2ReferenceExamples.ts`,D2-10嵌ECL计量三要素/账龄对照/概率加权/前瞻性打分卡,D2-12嵌保理合同10条款分析清单+9步终止确认流程,Playwright验证完整渲染。117 D2测试通过。**🔴 D2-12保理终止确认9步判断向导闭环已完成**:`D2DerecognitionWizard.vue`(el-dialog:左侧9步el-steps导航+右侧当前步:判断要点/📎附件OCR/知识库el-autocomplete/🤖AI判断/我的判断radio+底部结论select+保存回填)+`useD2Derecognition.ts`(9步状态+OCR/AI/知识库/决策树suggestedConclusion+save)+后端`_d2_derecognition.py`(POST /d2/derecognition-ocr附件→UnifiedOCRService;POST /d2/derecognition-judge步骤+证据+知识库→chat_completion→{suggestion符合/不符合/不适用,reasoning};已在router_registry/workpaper.py注册)。存item_id `D2-derecognition`(JSON steps+conclusion)。接入D2TabPledgeCheck保理区"▶终止确认判断向导(9步)"按钮+结论tag+@applied回填审计说明。**Playwright全链实测通过**:向导渲染完整→AI判断200(vLLM未启优雅降级)→点选"符合"+结论"终止确认"→保存→PUT 200→postgres确认D2-derecognition落库(conclusion=终止确认)→审计说明回填摘要→保理区显示"判断结论:终止确认"tag。104 D2测试通过。**🔴 D2-12保理终止确认升级为「逐份合同」判断+复核视图**:判断从单份→per合同(按factoringRow.rowId分别存,存储格式`{byContract:{[rowId]:{steps,conclusion,updatedAt}}}`,parseJudgmentStore兼容旧单份格式→`__legacy__`键)。新增`D2DerecognitionOverview.vue`(el-segmented切换**卡片视图**(每份合同一张卡:债务人/金额/保理商/日期+9步状态色块S1~S9+进度+结论tag+编辑按钮)+**矩阵视图**(el-table:债务人|金额|保理商|S1~S9色块|进度|结论|操作,含图例),面向复核人一屏看全)。`useD2Derecognition`加contractId参数,load/save按合同键读写。向导标题带合同标签,每份独立0/9起判。**旧数据迁移**:overrideLegacy归入factoringRows[0]并持久化(persistStore避免孤儿)。Playwright实测:2份合同独立判断(合同1终止确认/合同2不终止确认)+卡片/矩阵双视图渲染+postgres byContract双entry确认。D2TabPledgeCheck移除单向导按钮改嵌Overview。104 D2测试通过
- **🔴 D~N tab组件 props ref解包陷阱（D3全崩血泪，2026-07-10）**：子tab组件把 `allResponses`/`wpId`/`projectId` 声明为 `Ref<Map>`/`Ref<string>` 并访问 `.value`，但父级(GtD3PrepaidAccounts等)经**模板绑定** `:all-responses="allResponses"` 会**自动解包 ref**→子组件实际收到的是解包后的 Map/string→`props.xxx.value` 为 undefined→`.value.get` 崩溃(ErrorBoundary)。**D3 全部9个内容tab因此在浏览器全崩**，但单测传真ref故全绿=典型假绿。**修复(对齐D2可用模式)**：子组件 props 声明为**解包类型**(`Map`/`string`)，再用 `const xxxRef = toRef(props,'xxx') as Ref<...>` 重新包成ref喂给composable；直接 `props.allResponses.value.get`→`allResponsesRef.value.get`。**必 Playwright 实测每个tab(diagnostics/单测查不出)**。D3还修了披露tab `applicableStandards` 父级未传(归一化 computed 防崩+父级补传)
- **D3打磨(参照D2)**：9内容tab补 审计目标el-alert + 编制提示details(CAS依据) + D3-7异常列自由文本→`el-select filterable allow-create`点选(跨期疑点/金额异常等6项,保留自定义+auto-mark) + D3-5/6行级GtReviewDot。实测9tab全0错误+异常标记"跨期疑点"落库
- **底稿编码→实际内容必须查源模板**：不能凭编码猜内容
- **🔴 底稿列表名称清洗规则(2026-07-12)**：`cleanWpName(raw)`去掉"审定表/明细表/审定表及明细表/及明细表"后缀只保留科目名（如"应收账款审定表"→"应收账款"）。`WorkpaperWorkbenchView`(列表+卡片)和`WorkpaperEditor`(编辑器标题)都用此规则。不改DB数据(wp_index.wp_name不变)只改前端显示
- **🔴 computed传prop的深层响应陷阱**：`computed(() => state.value.arr[idx])` 只追踪数组元素引用不追踪属性变化→子组件收到prop不更新→"点击没反应"。**修复：`return { ...s }` 展开读取所有属性建立依赖**（C15-2偏差评价决策树踩坑）
- **专属组件跨sheet跳转标准模式**：子组件emit('navigate-sheet', sheetName)→GtWpRenderer.onChildNavigateSheet按sheet_name模糊匹配切换activeSheetName。已注册全局通道，所有专属组件可复用
- **C24四表联动端点**：`GET /ledger/entries-all?year=&page=&page_size=` 全量序时账查询(不限科目,max 5000/页)，供C24细节测试一键拉取分录自动分析
- **render-config返回结构是`{sheets:[{html_data:{...}}]}`**
- **新专属组件必须有selfLoad逻辑**（bundle内嵌场景htmlData为null）
- **A1 Dashboard子Tab组件必须自加载**
- **GtIndexChip的prop名是`value`不是`wp`**
- **API调用可能触发全局404弹窗**：预期404请求加`{_silent:true}`
- **naive UTC时间戳前端少8小时**：补`Z`标记再交fmtDateTime
- **GtAProgramConsole需selfLoad**（bundle内嵌场景）
- **通用AI文本生成端点**：`POST /api/workpapers/{wp_id}/ai/generate-text`在`wp_guidance_chat.py`中，接收prompt/context/existingContent/section，调用`chat_completion`返回内容；所有底稿的AI辅助按钮统一调用此端点
- **Cx-2独立底稿wpCode含"-2"后缀**：`extractCycleNumber`正则不能用`$`锚定尾部；传入composable前必须`.replace(/-\d+$/, '')`去后缀，否则cycleNum=0数据全丢
- **C2~C15 conclusion白名单必须含null守卫+决策树值"是/否"**：`checklist_responses.py`中C2~C15校验缺`and item.conclusion`守卫→null触发422；决策树step1/step4值"是/否"也需加入allowed元组

### OnlyOffice
1. JWT：开发环境 `JWT_ENABLED=false`
2. URL：`ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:9980`
3. callback 返回裸 `{"error":0}`
4. 改 URL 后需 `docker restart` 清 session
5. 统一用 GtOnlyOfficeSheet；健康端点=`/api/workpapers/onlyoffice/health`
6. fileType 动态检测（从file_path后缀推断）
7. 聚合包内sheet三端点统一用sheet级wp_code解析
12. **✅ 交付中心「生成附注」docx 乱/空白 根因修复（2026-07-25，`deliverable.py`路由+`note_word_exporter.py`，in-process 实测 0 残留占位符+0 blank-with-data+库存现金376.73 渲染，未commit）**：用户报生成的 `disclosure_notes_2025.docx` 乱且科目注释有数据却空白。**三层根因**：①**变体口径错配（乱=291 原始 token）**——附注模板 soe 用「四、」前缀 / listed 用「三、」前缀，DB 附注按 `Project.template_type='listed'`(三、) 生成，但交付中心「生成附注」前端不传 template_type → 后端 `DeliverableExportRequest.template_type` **默认 "soe"** → 用 soe 模板(四、)填 listed 附注(三、)→ `{{section:code}}`/`{{table:code:N}}` 全部匹配失败 → 291 原始占位符泄漏。**修=`render_disclosure_notes` 从权威源 `Project.template_type` 解析变体**(与附注编辑器/生成/编号端点一致)，不再用 body 默认；复用既有 task 时同步 variant 元数据。②**残留占位符防御网**——`_export_template_mode` step7 新增 `_strip_residual_note_placeholders`(扫全段落含表格单元格/嵌套表格抹除任何 `{{section/table/seq:..}}`+warning 日志)，保证交付文档永不泄漏 token。③**🔴 科目注释有数据却空白（真主因）**——五、1/2/4/22 等 ~25 张 legacy 表 `table_data.headers=[]`(空) 但 rows 非空(带 `values`+`_cell_meta[col].semantic`)，`_render_table` 遇空表头**直接 return→整表不渲染→空白**；前端读路径(`get_note_detail`)早已用 `note_header_projector.project_headers` 从行语义派生表头，但 **Word 导出器从未接入**。**修=`_note_tables` 对每张表调 `project_headers`**(从 `_cell_meta.semantic` 派生中文表头 首列"项目"+期末余额/上年年末余额等，读时派生不改存量，与前端同一纯函数)。**实测(项目0ec33ac9/listed)**：soe=291 残留→listed=0；无 header projection 时 376.73(五、1库存现金)缺失→有 projection 后渲染(+25 张表恢复)；145 blocks 139 matched 0 blank-with-data，6 unmatched 无 DB note(同一控制合并/十七非经常性损益等)正确显模板参考。**范式**：①附注导出变体必须=`Project.template_type`(soe四、/listed三、前缀不同，错配则占位符全泄漏)；②交付文档必须清除所有残留 `{{..}}` token(防御网)；③附注表格 `headers=[]`+rows 带 `_cell_meta.semantic` 是历史生成/绑定合并的普遍形态，**任何渲染路径(前端 el-table + Word 导出)都必须读时派生表头**(`note_header_projector.project_headers`)否则空白，Word 导出器易漏。改动文件 `backend/app/routers/deliverable.py`+`backend/app/services/note_word_exporter.py`，get_diagnostics 全清+import OK+health 200，未commit/未 Playwright(in-process 实测充分)。
11. **✅ 交付中心「更多」下拉字号统一 + 「下载编制参考版」功能落地（2026-07-25，5前端+1后端文件，diagnostics全清+两SFC Vite200+后端AST OK+端点已注册9980，未commit）**：①**下拉字号偏大**——`DeliverableGroupList.vue` 的 el-dropdown 菜单 teleport 到 body，scoped 样式够不到→加 `popper-class="deliverable-more-dropdown"`+**非scoped**样式块把菜单项统一 13px(对齐表格内容与「更多」链接按钮)+收紧行高/padding。②**「下载编制参考版」原为占位「即将上线」→打通全链路**：后端 `deliverable.py` 新增 `GET /{task_id}/versions/{version_no}/guidance-download`(权限=download,仅 audit_report,定位交付件目录 `with_notes_v{n}.docx`[confirm 阶段落盘的含内部提示副本,与正式版同目录按 task+version 定位],中文名,文件缺失[旧流程版本]返404引导重新生成);`apiPaths`+`deliverableApi` 加 `guidanceDownload` URL;`DeliverableCenter.downloadGuidanceVersion` 改 axios blob 认证下载(`downloadFile`)+成功提示「仅供项目组编制参考不可对外出具」。**顺带扩 `utils/http.ts::downloadFile` 加可选 `silent` 参数**(转发 `_silent` 抑制拦截器全局404 toast,由调用方处理预期404;additive 对既有调用零影响)。**范式**:①teleport 到 body 的 EP popper(el-dropdown/el-select 菜单)scoped 样式不可达→用 `popper-class`+非scoped 样式块定向(不能靠 :deep);②预期404的认证下载(如旧版本无参考版)用 `downloadFile({silent:true})` 抑制拦截器 toast+调用方 catch 自定义提示,避免双 toast;③交付件"参考版/含提示副本"文件与正式版同目录(`_deliverable_dir/with_notes_v{n}.docx`),下载端点按 task_id+version_no 定位不依赖 report_body_json 只存最新路径。
10. **✅ 「生成报告正文预览失败」根因修复（2026-07-25，`template_manifest_loader.py`+`deliverable.py`路由+回归测试，live HTTP 200+11测试绿，未commit）**：用户报生成不了报告正文（怀疑我改封面 docx 导致）。**进程内+live HTTP 复现定位真因（与 docx 改动无关）**：前端 DeliverableCenter 意见类型下拉有 `unqualified_with_emphasis`（带强调事项段的无保留意见），但 `template_manifest.json` 的 report_body 只有 `unqualified/qualified/adverse/disclaimer` 四族→`resolve_report_body` 抛 **`KeyError: unknown opinion_type: unqualified_with_emphasis`**；preview 路由只 `except ValueError`→KeyError 漏网成 **500→前端 toast「预览失败」**。**这是预先存在的 bug**（强调事项段本质是无保留报告里的可选段落 OPT，非独立模板族；`ReportBodyService._resolve_opinion_enum` 早已 emphasis→unqualified）。**修**：①`template_manifest_loader` 加 `_OPINION_TYPE_ALIASES={unqualified_with_emphasis:unqualified}`+`resolve_report_body` 归一 opinion+`variant=variant or "simple"`（前端可能传 null 兜底）②preview/confirm 路由补 `except KeyError→422`（清晰报错非 500）。live HTTP 实测两种意见类型均 200（emphasis 修前 500）。回归测试 `test_template_manifest_loader.py`+2（emphasis 别名/None variant 兜底）。**🔴 教训**：①preview/confirm 路由异常映射只 catch ValueError→其它异常(KeyError)成 500 静默；前端下拉选项值必须与后端 manifest key 对齐(unqualified_with_emphasis 是 UI-only 语义,后端归一到 unqualified);②「生成失败」类 500 定位=进程内脚本直调 service 拿真实 traceback(async_session+真实 project/user)>翻日志;③schema `template_variant:str="simple"` 非 Optional 但 service 签名默认被路由透传的值覆盖,None 兜底要在 resolver 单点做。**🔴 误判纠正**：我上一轮改封面落款行距(fix_report_cover_firm_spacing.py 用 python-docx 重存32模板)**并非**生成失败主因——离线复现证明修复后模板 preview 解析全链路正常(填充服务本身也 Document()+save());但出于稳妥已 `git checkout` 还原全部模板(封面 page2 问题因此回退,待用户确认是否重新应用封面修复)。已生成交付物(storage)的封面修复未回退(gitignored)。
9. **✅ 审计报告 docx 封面落款「致同会计师事务所（特殊普通合伙）」被挤到第2页修复（2026-07-25，`scripts/fix_report_cover_firm_spacing.py`+32源模板+已生成交付物，端到端验证[新生成v10 firm段行距=360+MuPDF落款首现第1页/共5页]+OnlyOffice实测加载，已重新应用[先误还原后确认无害重新应用]，未commit）**：**🔴根因=致同封面模板用巨大行距做"页底锚定"**——落款段设 `w:spacing w:line="2400" w:lineRule="auto"`（**10× 行距**）把落款撑成 ~253pt 高的**不可分割行框**顶到页底；OnlyOffice 的 CJK 行高比 MS Word 略大→封面"8空段+标题块(24pt×1.5)+11空段"累计高度超过 `可用页高628pt − 253pt = 375pt`→253pt 大行框**整块无法跨页断开→跌到第2页**（页1只剩标题块）。修=把落款段行距 2400→360（1.5×），行框 253pt→37.9pt，落款末尾从溢出回落到 386pt(<<628)，余量>240pt，任何渲染器行高浮动都留在第1页。**🔴关键验证点=目录靠分节符独立强制第2页**：封面(section0)与目录(section1)之间段23有 `w:sectPr` NEW_PAGE 分节符，目录始终在第2页**与封面高度无关**→缩小落款行框不会把目录拉回第1页(无回归)。全部32个致同报告模板(report_body 16+standalone 16)同款2400 anti-pattern，脚本一次修复(前30段内匹配含`{{firm_name}}`/`致同会计师事务所`且`w:line>=1000`的段→改360);已生成交付物(audit_report_v2~v8)也一并修(否则用户看的旧文件不变)。docxtpl简版报告(render_docx路径,29段无封面,firm在末尾签章段)无此问题正确跳过。**🔴 OnlyOffice doc_key=`{task_id}_{version_no}_{int(time.time())}`含时间戳→每次打开新key必重载最新文件不返缓存**,改文件后重开编辑器即见效。**范式**:①docx页底锚定禁用巨大行距(`w:line`>=1000)造不可分割行框(渲染器行高浮动会整块跳页),用适度行距+段落定位;②docx分页问题诊断=python-docx读段落spacing/sectPr(EMU→pt:page_height-top-bottom margin=可用高;`w:line`auto值/240×字号×1.15=行框pt)+MuPDF(fitz)独立分页交叉验证(注:MuPDF对分节符处理较松会合并页,以真实渲染器OnlyOffice为准,OnlyOffice严格遵守sectPr);③模板类改动同时修源模板(影响新生成)+已生成交付物(用户当前看的)。
8. **✅ 交付模块 OnlyOffice 编辑器「弹窗最大化」改为 OO 自身原生全屏（2026-07-25，`deliverable/OnlyOfficeEditor.vue`，Playwright 实测 enter/exit 通过·0 error，未commit）**：原「最大化」是切 `maximized`→el-dialog `:fullscreen`（弹窗撑满但标题/底部还在）；改为浏览器 Fullscreen API 让 OO 编辑器铺满物理屏幕。**🔴 关键坑1=`DocsAPI.DocEditor(elementId,config)` 会用 iframe 整个替换传入的占位 div（id 消失）**→`document.getElementById(editorContainerId)` 返 null→全屏点了没反应；必须对**不被替换的稳定父层**（`.onlyoffice-editor__main` 用 ref）请求全屏，`:fullscreen` CSS 也挂父层。**🔴 关键坑2=Esc 退全屏与 el-dialog `close-on-press-escape` 冲突**：真人 Esc 退全屏时同一 Esc 被 dialog 捕获→连编辑器弹窗一起关（编辑器有改动=误关风险）→设 `:close-on-press-escape="false"`，Esc 只退全屏、弹窗用 ✕/关闭 按钮关。全屏按钮 `v-if="!degraded && editorReady"`+监听 `fullscreenchange`/`webkitfullscreenchange` 同步图标（真人 Esc 退出也复位）。**🔴 Playwright 坑**：①`keyboard.press('Escape')` 是 DOM 合成事件，**不能触发浏览器 chrome 级的「Esc 退全屏」**（真人一定退，合成键不退）→验证退出用 `document.exitFullscreen()`（真人 Esc 走同款 fullscreenchange）；②全屏后 OO iframe 铺满全屏层拦截指针→我的「退出全屏」按钮不在全屏子树内不可点（原生全屏标准 UX，靠 Esc 退）；③该编辑器被并发会话 SSE 反复跳走→整个「中和 EventSource→打开→全屏→Esc」链路放单次 `run_code_unsafe` 内完成才稳。全栈起法：docker `audit-onlyoffice`(8080 healthy)+后端9980+前端3030，`VITE_ONLYOFFICE_URL=http://localhost:8080`；交付中心路由 `projects/:projectId/deliverable-center`（需完整32位UUID，8位简写后端422）。**✅ 补：全屏内「退出全屏」按钮已可见可点（2026-07-25）**：原先退出按钮在弹窗头部=不在全屏子树内→全屏后消失（用户报红框空只剩 OO 自带顶栏+浏览器 Esc 提示），只能靠 Esc。**修=照搬 `GtOnlyOfficeSheet.vue` proven 范式**——在全屏元素(`.onlyoffice-editor__main`)内部、iframe 容器**上方**加一条「退出全屏」工具栏行(独立 sibling 非 overlay→不被 iframe 指针拦截)，平时 `display:none`，纯 CSS `:fullscreen`/`:-webkit-full-screen` 选择器命中时 `display:flex`(iframe 占其下 `flex:1`)；`.onlyoffice-editor__main` 改 flex 列。进入全屏仍用弹窗头部按钮，退出用该条(Esc 也仍可)。**范式**:全屏内的控制按钮必须放进全屏元素子树内且作为 iframe 上方的独立行(非绝对定位 overlay，iframe 会拦截指针)，用 CSS `:fullscreen` 选择器控制显隐(不依赖 JS ref，更稳)。


## §stale 联动闭环铁律（2026-07-29 沉淀）

- **`working_paper.prefill_stale` 语义 = 「该底稿持有的已落库派生值可能过期」**，不是「所有底稿都要重算」。只有 `parsed_data.html_data` / `univer_snapshot` / `cell_provenance` 或 `prefill_tb_snapshot` 非空的底稿才可能过期；从未编辑过的底稿 render 时实时取数，永不 stale。`prefill_engine.mark_stale` 已按此收窄（此前无条件全标 → 实测 340/340 常亮）。
- **标脏必须有对应的清除路径**：`prefill_engine.clear_stale` + `resolve_stale_after_recalc`（TB 全量重算后按底稿实际持有的派生值三分：有公式快照→重跑 prefill 成功即清；无落库派生值→直接清；仅有 `html_data`(人工保存正文)→**保留 stale**，重算不覆盖持久化值，须打开底稿刷新后重存）。`/trial-balance/recalc` 返回 `stale_resolution={cleared,refilled,kept_stale}` 供前端说真话。
- **JSONB 条件禁用 PG 专属 `has_key`**（编译成裸 `?`，sqlite 测试库与占位符冲突直接语法错误）→ 统一用 `col[key].isnot(None)`（PG `jsonb[...]` / sqlite `JSON_EXTRACT`，两边都能编译）。
- **`apiProxy.get` 的 in-flight 共享只对「无 config 的纯 GET」生效**。带任意 config（如 `validateStatus`）就走非共享分支，与另一处同 URL 轮询相撞时被 `utils/http.ts` 的 GET 去重 **abort 前一个**，表现为「横幅/数据随机不渲染」且被 catch 静默。多消费者共用的只读 GET 一律不传 config。
- **`validateStatus: s => s < 600` 会吞掉 422/403**，配上漏传必填 query（如 recalc 的 `year`）就是「点了完全没反应」。只读探测可静默降级，**用户主动触发的写操作必须让错误可见**（`handleApiError`）。
- **`DefaultLayout` 用 `:key="viewRoute.fullPath"` 重建子视图** → 任何 query 变更（含自身 `router.replace` 补参数）都会**重挂载**当前视图，新实例的同 URL GET 会 abort 旧实例在飞的请求。视图内 fetch 必须把 `err.code === 'ERR_CANCELED'` / `err.name === 'CanceledError'` 当正常取消吞掉，否则冒泡到 ErrorBoundary。
- **横幅/状态条的 CTA 必须有落地页**：`?filter=stale` 这类 query 只有在目标页真正实现过滤器时才不是死链；跳转要带 `view=`（筛选栏可能只在特定视图渲染）+ `year=`（漏传会退到当前自然年，跨年度串数据）。


## §J1 披露复盘沉淀（2026-07-30，从 memory.md 下沉明细）

> memory.md 只留「披露同步载荷极易漏合计行」一条索引，明细在此。

### 明细底稿 → 披露表 按行名带入范式

首建 `audit-platform/frontend/src/composables/workpaper/j1/j1DisclosureDetailPull.ts`
（`applyDetailPullToDisclosureRows`），其它循环可照抄。

源模板披露行往往逐行引用明细底稿（J1 实证：`A18='明细表J1-2 '!J13`、`A21=J21+J22`、
`A29=J26+J27`），所以「带入」不是只带汇总，而是按行名逐行带。五条约束：

1. **两趟匹配**：先做全表精确匹配，再做包含聚合 → 消除"先处理的行把后面行需要的明细项
   贪心吃掉"（单趟时披露行排列顺序会影响结果）。守卫用「正序 vs 倒序结果一致」断言。
2. **包含匹配最短 3 字**：否则「其他」（2 字）会命中「其他短期薪酬」「其他长期职工福利」。
   两字词只走精确匹配 + **队列配对**（明细里两个「其他」按出现顺序配给披露里两个「其他」）。
3. **包含聚合是双向的**：披露名 ⊂ 明细名（`医疗保险费` ← 基本 + 补充医疗保险费）与
   明细名 ⊂ 披露名（`工会经费和职工教育经费` ← 工会经费 + 职工教育经费）都要支持。
4. **源模板公式明确合并的用 `absorb` 显式别名**，不靠字符串猜：国企 `B28=J1-2!J30+J31`
   → 「其他短期薪酬」吸收「非货币性福利」；上市 `A32=J1-2!J30` 是独立行，**不得套用**。
   反向断言（去掉 absorb 时该行必被追加成多余行）证明别名不是可省的装饰。
5. **未匹配「其中：」子项跳过**（金额已含在已匹配的父行，追加会双算），只有未匹配且
   **非零的顶层行**才追加为新行（对齐 J1-7 的"未匹配追加"范式）；未匹配的披露行
   **保持原值**不清零手工录入。UI 如实提示「命中 N 行 / 追加 M 行 / K 个子项未匹配」。

金额口径 = **审定数**（未审 + 期初调整 / 账项调整）。标签归一化复用既有
`normalizeJ1Label`（去空白 / 「其中：」前缀 / 序号前缀 / 「（不适用的删除）」尾注），别重写。

### 抽零依赖 leaf 模块消除循环依赖

新纯函数模块要用 composable 里的行模型 / recalc / 合计口径，而 composable 又要 import
新模块 → 直接互相 import 就形成运行时循环依赖（ESM 有时能靠函数提升侥幸跑通，很脆弱）。

范式：把 `行模型 interface + recalcXRow + buildXSubtotal` 抽到零依赖 leaf
（`j1DisclosureRowModel.ts`），composable **re-export 全部符号** → 既有
`from '.../useXDisclosureSections'` 的 import 一个都不用改。改完 `get_diagnostics`
逐个消费方复查（含 `.vue` 与 `XNoteSectionMap.ts`）。

### spec 三件套格式校验（`get_diagnostics` 对 `.kiro/specs/**/*.md` 生效，写完必查）

| 文件 | 必需 |
|---|---|
| requirements.md | `# Requirements Document` + `## Introduction` + `## Glossary`（推荐） |
| design.md | `## Overview` / `## Architecture` / `## Components and Interfaces` / `## Data Models` 四个必需；`## Correctness Properties`（每条必须是 `### Property N: xxx` 且带 `**Validates: Requirements X.Y**`）/ `## Error Handling` / `## Testing Strategy` 三个推荐 |
| tasks.md | `# Implementation Plan: xxx` + `## Overview` + `## Task Dependency Graph`（waves JSON）+ `## Tasks` + `## Notes` |

任务行必须 `- [ ] N.` 形式 —— `- [ ] 16* 可选（另立任务）` 会报
"Task line does not match expected format"，写成 `- [ ] 16. 可选（另立任务）`；
可选标记 `*` 放在子任务编号后（`- [ ] 10.2* ...`）。

### PowerShell 输出编码与 heredoc

- **`>` 重定向会把 UTF-8 中文输出腌成乱码并落盘**：python 以 utf-8 emit → PS 按 cp936
  解码 → 乱码写入文件 → `read_file` 读到的就是乱码（不是显示问题，是内容问题）。
  → 诊断 / 修订脚本一律用自带 `--out` 参数**自己写盘**；必须看终端时先
  `[Console]::OutputEncoding=[System.Text.Encoding]::UTF8`。
- **PS 不支持 heredoc**：`python - <<'PY' ... PY` 报「无法初始化设备 PRN」
  → 临时脚本写成文件再跑。
- `set X=v & cmd` 是 CMD 语法，PS 用 `$env:X="v"; cmd`（`&` 在 PS 里保留字会报错）。

### `composables/__tests__` 全量预存在失败基线（2026-07-30 实测）

693 文件 / 7132 测试里 **5 例失败**，**单独跑同样失败**（非并发污染）：

| 文件 | 失败点 |
|---|---|
| `l4-bonds-payable.integration.test.ts` | `adjudicationVsDetail` 差异计算（2 例） |
| `useD1FormulaEngine.spec.ts` | `calcChangeRate` 三分支 PBT |
| `useF3Integration.spec.ts` | `substantive:adjudicated`(2201) EventBus 刷新 section1 |
| `useF5Integration.spec.ts` | `substantive:adjudicated`(6401) EventBus 消费 |
| `useH4DualMode.spec.ts` | OO 健康检查后切模式 |

判「是否本次引入」看**失败断言是否触及本次改动的符号**，别当新增回归；
也别用 `git stash` 做基线对比（并发会话 / IDE 缓存会把文件回写成另一版本）。


## §J1 披露 wave 3~6 沉淀（2026-07-30，从 memory.md 下沉明细）

> memory.md 只留三条铁律索引（`useAuditContext` setup 顶层 / 同步成功不得自触发 /
> 读源码守卫先去注释），明细在此。

### 变动表子组件抽取范式（`J1MovementTable.vue`）

同一循环的多张「五列变动表」在上市 / 国企两个 Tab 里往往各写 N 遍（J1 是 3×2 = 6 份，
约 55 行 × 6）。抽子组件时差异全部由 props 表达：

| prop | 差异来源 |
|---|---|
| `beginLabel` / `endLabel` | 上市「上年年末数 / 期末数」vs 国企「期初余额 / 期末余额」（源模板各自口径） |
| `labelEditable: 'all' \| 'indent' \| 'none'` | 汇总表全行可改名；明细表只有「其中：」缩进行可改名 |
| `removable` 同上三态 | 删除按钮可见范围 |
| `selectable` | 明细表需 `highlight-current-row` 支持"在选中行后插入"，汇总表不需要 |
| `derivedIds` | 派生父行（渲染成只读公式单元格） |

**只读单元格三类**（都渲染成虚线下划线 + tooltip）：①合计行全部金额列 ②任意行的期末列
③派生父行的期初/增加/减少列。抽完后加一条守卫断言「模板内 0 处裸 `el-table`」防回退。

### 同表内父行派生（`applyParentSums` / `derivedParentIds`）

源模板里父行常是 SUM 公式而非录入项（J1：`B20=SUM(B21:B27)` 社会保险费、
`B41=SUM(B42:B45)` 离职后福利），且合计行公式显式排除这些「其中：」子行。

通用规则：**非缩进行若其后紧跟 ≥1 个连续缩进行，则该行 期初/增加/减少 = 子行之和**。
一条规则覆盖多处且对「+ 新增行」自动生效。要点：

- 期末列**不**单独求和，仍由 `recalc` 按「期初 + 增加 − 减少」派生（同口径）
- **合计行截断子项区间**（合计行之后的缩进行不归前一父行）
- 无缩进子行的行**完全不动**（保持可手工录入，行为与历史一致）
- 返回"被改写的父行数"，值本就相等时不计入 → 调用方据此判断是否需落库（幂等）
- 调用时机：`hydrate`（历史手工值对齐源模板口径，不落库靠首次编辑一并持久化）/
  `onRowChange` / 增删行（`afterRowSetChange`）/ 明细带入之后

### 披露内部勾稽引擎（H1 范式的第二次落地）

`buildJ1ConsistencyChecks(input): J1CheckResult[]` + `summarizeJ1Consistency`。
只取**源模板 Excel 公式可判定**的关系，每条 `rule` 字段写明证据（如"两处同引
`'明细表J1-2 '!J33`"）。容差 1 分，金额勾稽无 warn 中间态。

设计要点：

- **跨表规则按列拆**（4 列各一条）→ 差异能定位到具体列，而不是只说"不平"
- **缺行 / 无子项 / 空表时跳过该条**，不产出 `0 = 0` 的假通过
- **J1-1 未编制（合计为 0）时不产出审定勾稽项**，避免恒不平的噪声
- 合计行不参与"逐行期末公式"校验（其值由 computed 产出）
- 反向断言是必需的：制造差异必须报出 + 只报出错那一列 + 容差 0.01 通过 / 0.02 报错

### 说明文本域收敛为单一真源

各循环披露 Tab 的说明 placeholder、文本域标题、持久化键、推给附注的 `_note_texts`
小节标题**是同一份东西**，散落四处必漂移。收敛成
`X_LISTED_NOTE_FIELDS` / `X_SOE_NOTE_FIELDS`（`{key, title, placeholder}`）+
`xNoteFields(variant)` / `xNoteKeys(variant)`，放在 `XNoteSectionMap.ts`；
组件 `noteKeys: xNoteKeys('soe')` + `:placeholder="FIELDS[i].placeholder"`。

placeholder 必须是**源模板说明段原文**，不得改写截断（J1 国企第 3 条历史实现被截断，
丢了「及其变动、对未来现金流的影响、重大精算假设及有关敏感性分析等」）。

### AI section prompt 登记（通用端点是放行式的）

`POST /api/workpapers/{wp_id}/ai/generate-text`（`wp_guidance_chat`）对 section
**不做拒绝式白名单** → 未登记的 section 静默落到通用兜底
「请根据提供的上下文信息生成专业的审计文本。」= 放任模型自造披露内容。

新增披露文本域必须同时：①组件里的 `aiSection` ②`_SECTION_PROMPTS` 登记
③prompt ≥20 字 + 点名准则（应付职工薪酬是 CAS 9）+ 含「不得虚构」类约束
④参数化守卫（section 名从前端 `.ts` 源码正则读出防双真源漂移，并用测试**锁住
"端点不做白名单"这一前提**——前提变了守卫的价值判断要重估）。

设定受益计划这类"可能不存在"的小节，prompt 要明确允许直接声明「本公司不存在xxx」，
否则模型会硬凑内容。

### 浏览器实测的可复用手法（chrome-devtools MCP + postgres 只读）

1. 登录：`admin` / `admin123`（既有 e2e 通用凭据；token 在 `sessionStorage.token`）
2. 底稿编辑器路由：`/projects/{pid}/workpapers/{wpId}/edit`；切 sheet 靠
   `[...document.querySelectorAll('*')].find(e => e.children.length===0 && e.textContent.trim()===sheetName)`
   再 `.closest('[role=tab], .el-tabs__item, li, div').click()`
3. 模拟录入 `el-input-number`：`focus()` → 改 `value` → `dispatchEvent(new Event('input',{bubbles:true}))`
   → `change` → `blur()`，每格间隔 ~60ms
4. **判"请求到底发出了没"**：临时包 `window.fetch` + `XMLHttpRequest.prototype.open/send`
   收集 URL。`performance.getEntriesByType('resource')` 缓冲区只有 250 条，页面加载多时会溢出，
   **不可靠**
5. **`el-message` 3 秒自动消失** → 轮询收集（每 250ms × N 次）而不是等待后一次性读，
   否则会漏掉关键错误提示（本轮就因此第一次没看到失败原因）
6. 落库真相一律用 postgres 只读比对（`_last_sync_at` / `_source` / `sub_table_data` 键 /
   合计行 / `_column_groups`），不看截图


## §披露自动同步「活体验证」手法（2026-07-30，12 Tab 实测沉淀）

> 验证目标：`watch(实际数据) → scheduleAutoSync → syncToNotes → POST` 全链在**用户编辑**
> 路径下真的通，且**静置期不误触发**。memory.md 只留结论，手法在此。

### 判定范式（每个 Tab 三步）

1. **静置基线**：切到该 Tab 后再等 4~6s，统计 `sync-from-workpaper` 请求数 —— 必须为 **0**
   （否则说明挂载/数据加载会误触发，`_last_sync_at` 的前移就不能归因于编辑）
2. **数据变更**：改一个响应式字段，等 6s，统计请求数 —— 必须为 **1**
3. **落库比对**：postgres 只读查 `_last_sync_at` / `_source` / `sub_table_data` 键数

三者齐备才算通过；只看 ②会把噪声当成功，只看 ③无法排除是别的路径写的。

### 🔴 不要用合成 DOM 事件驱动录入（两次误判的根源）

`el.value = x` + `dispatchEvent(new Event('input'))` **不可靠**：

- **`el-input-number` 不响应**合成事件（内部有自己的 parse/setCurrentValue 流程）→ UI 显示变了、
  **零保存请求**、响应式数据没动。而 **`el-input` 会响应** —— 这解释了为什么同一手法在
  J1/K1/G1（改的是文本列）成功、在 G6（改数值列）失败。
- **`el-table` 重渲染会替换元素**：复用上一次拿到的元素引用，v-model 已断，写 `value` 只留在
  detach 的 DOM 上。每次操作前必须重新 `querySelectorAll`。

**正确手法 = 直接改响应式数据**（语义上就是"数据变更"，且绕开控件实现细节）：

```js
const root = [...document.querySelectorAll('div[class*=disclosure]')]
  .filter(e => e.offsetParent !== null && e.__vueParentComponent?.setupState)[0]
const ss = root.__vueParentComponent.setupState   // script setup 的绑定全在这里
const disc = ss.disc ?? ss.dis                    // 各 Tab 的 composable 实例名不统一
const arr = disc.rows?.value ?? disc.rows         // ref 与裸值都兼容
arr[0][numericField] += 12345                     // deep watch 会追踪
```

`setupState` 里能看到全部 setup 绑定（含 `buildSyncData` / `syncToNotes` / 各 ref），
调试极方便；dev build 才有 `__vueParentComponent`。

### 🔴 先读模板确认"真实用户路径"，别对着 API 猜

H3 曾被我判成「行数据变更不触发」：我调 `updateRow(key, {...row, x: v})` 传**新对象**，
数据没变。读模板才知道真实路径是 `v-model="row.beginBalance"` —— **直接 mutate
`getSectionRows(key)` 返回的响应式行对象**，`@change` 上的 `updateRow` 只负责持久化。
按真实路径（直接 mutate）测即 1 次 POST。**`updateRow` 不是坏的，是用法不对。**

判「某个 API 是否该改数据」先看模板怎么用它，不要按名字推断语义。

### 手动调 syncFn 返回 `canceled` = 内部有 ElMessageBox

I6 的 `syncToNotes` 在勾稽有差异时弹确认框；脚本里直调它会被 `ElMessageBox.confirm`
reject → 捕获后静默返回、零请求，`el-message` 显示 `canceled`。验证时需轮询
`.el-message-box`、点 `.el-button--primary`（**按钮文本可能是「仍要同步」而非「确定」**，
按 class 取比按文本正则稳）。

### 其它实测坑

- **token 会中途过期**（跳 `/login`）→ 脚本开头判 `location.href` 含 `login` 就先登录
- **Chrome 实例被多会话共享**：本轮页面被别的会话导航到 D6 底稿 → 每次 evaluate 前确认
  `location.href` 与预期底稿一致
- **`el-message` 3 秒消失** → 轮询收集，别等完再读
- **测完把数据改回原值**（这些是真实在册项目的底稿）；改回也会触发一次同步，正好二次验证


---
## 【从 memory.md 下沉的踩坑铁律与披露链路脚手架（2026-08-10 精简迁移）】

## 踩坑铁律

- **🔴🔴🔴 「固定字符窗口」在**留痕/文案类判据**上会按写法差异误杀，且相邻同构条目一个过一个红时几乎一定是判据缺陷（2026-08-09 K 类 Task 4 实测，第 N 次踩窗口坑）**：判「留痕是否写明了 row_code 指向哪个科目」的正则写 `row_code + [^\n]{0,12}? + 分隔符 + 中文`，实测 K12 的 `IS-041（listed 侧「（一）基本每股收益…` 在 12 字窗口内**恰好**命中 `（一` 而通过，完全同构的 K13 `IS-043（listed 侧「4. 其他债权投资…` 因名称前多了 `4. ` 三字符落到窗口外被打红 ⇒ 看起来像「声明表少写了东西」，实为判据不完备。**正解 = 按 row_code 切段**（`finditer` 取每个码到下一个码之间的片段）再在段内找「分隔符/引号 → 中文」，与距离无关。**同一处还踩了第二个坑：`[\u4e00-\u9fff]{2,}` 要求连续两个汉字** —— 而真实报表行名普遍在第 2 字符就是全角标点（`减：所得税费用` / `三、利润总额` / `（一）基本每股收益`）⇒ 该写法会把三条真实留痕全判缺失。正解 = 分隔符后**只要 1 个汉字** + 另配「该段汉字总数 ≥ N」防 `（已改正）` 这类噪声通过。→ **判据要么按结构边界切段、要么统计计数，禁按字符距离**。
- **🔴🔴 变异检验 ANCHOR-MISS 的两个高频成因，都属**脚本缺陷不是守卫缺陷**（2026-08-09 K 类 Task 5 一轮 4/4 全 MISS）**：①**引号形态猜错** —— 我按 `is_liability=True,          # 预计负债：贷方` 写锚点，真实源码是 `is_liability=True,`（注释在别行）且用**双引号** `row_code_soe="BS-050"` 而我写了单引号 ②**锚点在同文件重复** —— `is_liability=True,` 在 K3/K4/K5/K7 + `liability_spec_for` 共 5 处出现 ⇒ 即便文字对了也是 hits=5。正解 = **先落一个「打印目标文件全部含关键字的行号 + repr(行内容)」的探针**，再按「行号 + 该行 repr 精确匹配 + 断言 hits==1」定位。**RED 0/N 时第一件事是看是 MISS 还是 GREEN**，MISS 一律先修脚本别去改守卫。
- **🔴 `provision_resolved_from` 在 `provision_exact=False` 时被平台**强制降级**为 `fallback`，故它不能作「`provision_row_code` 是否生效」的判据（2026-08-09 K6 实测）**：`report_line_accounts` 有一行 `if not provision_exact: provision_from = RESOLVED_FROM_FALLBACK`（保守口径，保 D1 零回归）⇒ K6 的备抵明明是从独立报表行 `IMP-007` 解析出来的（`prov_row='IMP-007'` + `prov_formula="TB('1482','期末余额')"` 都非空），`prov_from` 仍显示 `fallback`。**正确判据 = `provision_row_code` 与 `provision_formula` 两个字段非空**；要判「前缀是否退化」才看 `provision_exact`。
- **🔴 `extra_standard_codes` 的产出形态是 `{标准码: [原始码前缀,...]}` 且**不进 `gross`**（2026-08-09 K3 实测确认设计正确）**：`BS-050 = TB('2241') + TB('2231')` 解析后 `gross=['2241']` / `extra={'2231': ['2231']}` / `signed_codes=[('2241',1),('2231',1)]` ⇒ 「附加科目单列不并入原值」这条不需要额外实现，共享件已保证；守卫应同时断言「在 extra 里」与「不在 gross 里」两侧。
- **🔴 `_wip_run.py` 这类通用跑批器已在 `backend/scripts/diagnose/`，**别再往里传 `-m pytest`**（2026-08-09 踩，rc=5 collected 0）**：它内部已拼 `python -m pytest`，再传一次会让第二个 `pytest` 被当成 **marker 表达式** ⇒ `289 deselected`、退出码 5。同族：`--out` 参数已含扩展名时别再拼 `.txt`（会产出 `x.txt.txt`）。 ⇒ `zipfile.write` 把「当前目录」写成一个**目录条目**（2026-08-09 批量下载 ZIP 实测 P0，本轮最贵一条）**：`WpDownloadService.download_pack` 只写 `if not Path(wp.file_path).exists(): continue`，而 `working_paper.file_path` 实测**四种形态并存**（全库 2798 份：**空串 1564** / `wp_templates/...` 相对 956 / `storage\projects\...` 相对 246 / 绝对 6 / 其它如 `/tmp/xxx` 26）⇒ 空串那 1564 份**全部**被判「存在」并写成名为 `D/xxx.xlsx/` 的目录条目，解压出来是一堆空文件夹 = 用户看到的「导出来都是空的」。**ZIP 实收 1000/2798，误写目录 1564**。三条配套：①该函数**零测试覆盖**（codegraph blast radius 直接报 no covering tests）②紧邻的 `download_single` **有** `backend/` 前缀回退而 `download_pack` 没有 = 同文件漏改 ③`include_prefill` 形参收了但函数体一次没用 = 死参数。⇒ **凡「按 DB 里的路径字符串打包/读文件」的代码，判可达一律用 `is_file()` 不用 `exists()`**，且必须先连库统计该列的形态分布（`CASE WHEN file_path=''/LIKE...` 分桶）再决定解析策略。
- **🔴 路径解析在平台已有 4 套各写一份的实现（2026-08-09 收敛前实测）**：`wp_download_service.download_single`（cwd → `backend/`）· `export_engine._resolve_docx_template`（cwd → 仓库根 → 模板库）· `wp_xlsx_export_service._resolve_template_path`（仓库根 → `_TEMPLATES_ROOT`，剥 `backend/wp_templates/` 前缀）· `wp_render_config_helpers._resolve_template_path`（`is_file` → `find_template_file_any`）。四套的候选根、回退顺序、失败语义（返 None / 抛 `TemplateNotFoundError` / 返原值）**全不相同** ⇒ 同一份底稿在导出、渲染、下载三条路径上可达性不一致。已建单一真源 **`app/services/wp_export/wp_file_resolver.py`**（`resolve_wp_file(file_path, wp_code=None, *, allow_template_fallback=True) -> WpFileResolution`，四态 verdict `file`/`template_fallback`/`empty`/`missing` + `reason` 中文可读原因 + `WP_FILE_VERDICTS` 字面量真源）。**verdict 是 `Literal` 别名不是 Enum** ⇒ 守卫写 `mod.WpFileVerdict.MISSING` 会 `AttributeError`（本轮踩，判据必须用字符串字面量 + 与 `WP_FILE_VERDICTS` 交叉锁死）。
- **🔴 把回退逻辑抽成辅助方法后，「函数体内必须含某字样」的守卫会以**假红**形态复发（2026-08-09 又踩）**：判据截 `_export_xlsx` 体找「导出失败」，而我把回退抽成了 `_build_failure_fallback_workbook` ⇒ 字样在辅助方法里、主函数只剩一行调用 ⇒ 守卫红而实现完全正确。正解 = 判据同时接受「主函数体内」或「主函数调用的辅助方法体内」，并断言主函数确实调用了它。同族已记：「判据落错函数」「固定字符窗口截函数体」。
- **🔴🔴🔴 「守卫在保护错的那一侧」是错值长期存活的头号机理，判「某真源对不对」不能看它的守卫是否全绿（2026-08-09 I 类实证，最贵一条）**：`test_i_cycle_accounts.py::TestResolveRowCode` 的 12 个参数化用例**逐条断言 11 个错码**（连 `test_empty_standards_returns_listed` 也断言错值），于是「把真源改对」会让它打红、看起来像**改坏了**；而真源的模块 docstring 还写了一整段论证为什么那些码是对的（把 `BS-050`/`BS-040` 在两准则下的语义差异当成「I5 的正确行」，实为其他应付款/流动负债节标题）—— **守卫 + docstring 双向自我印证，形成闭环**。⇒ 判据必须**外部化**：新守卫的类 A 断言自己连库查 `report_config` 得 `(row_code, standard) → (row_name, formula)` 全表再对账，**不引用任何既有常量**；发现旧守卫锁死错值时**诚实改写 + 在类 docstring 写明「旧期望值 N/M 为错码，修正依据见 X」**，并加一条交叉锁死（改回旧错码时新守卫必红），不得为让旧守卫继续通过而回退真源。同族信号：**真源里出现「为什么这个反直觉的值是对的」的长篇论证**，往往正是错值的思想来源。
- **🔴🔴🔴 「存在性」判据结构上覆盖不了「归属」，凡按码/名查白名单的守卫都要再加一条归属闸（2026-08-09 I 类变异 M6 挖出，可推广到全平台）**：`test_account_codes_exist_in_chart` 查 `standard_account_chart.json`，而 **`6602 管理费用` 确实存在**（它是 K9 的科目）⇒ 把 I2 明细表的 `TB('6604')` 回退成 `TB('6602')`（正是 Task 7 修掉的那个真缺陷）**93 条断言一条不红**；`test_no_forbidden_code_residue` 只禁 `1712/1717/1911` 也放行。⇒ 正确判据 = 「每块 `formula` 抽出码 ∪ `account_codes` 必须 ⊆ 本循环各段 `fallback` 的一级码集合」，跨循环勾稽走**显式登记表**（本例 `_CROSS_CYCLE_TIE_OUTS`，实测全库只 1 条 = I2 明细表引 `6604` 与 I6 勾稽）。登记表须配**三向自检**：①外来码必须真属登记的那个循环（否则登记成万能逃逸阀）②理由 ≥20 字 ③**stale 检测**（该块不存在 或 数据里已不引用该码即打红）。**抽码前必须先把区间 `SUM_TB('a~b')` 整体消费掉**（否则上界被当引用，同族已记 H1）。→ 排查同类守卫的问法：「这条判据只要求它是个合法的 X，还是要求它是**这里该用的**那个 X？」
- **🔴🔴 双键结构（`{listed, soe}`）的错值会**只错一半**，按单键抽查必漏（2026-08-09 I 类实测）**：memory 上一版只记了 soe 侧 6 个错码，实测 listed 侧是**另一套错值**且更隐蔽 —— `BS-033/035/037/038/040` 呈**整体错位一个循环**（`I1.listed=BS-033` 恰是 I2 的正确码、`I2.listed=BS-035` 恰是 I4 的正确码），且 `I6.listed` 恰好正确（12 个里 11 错，一致性检查会被那 1 个正确值干扰）。⇒ 守卫必须按 **`(循环, 准则)` 二元组**逐条参数化断言，禁按循环聚合；调查报告里写「N 个全错」前先确认 N 是**二元组数**不是循环数。
- **🔴🔴 「删掉零消费方的双真源文件」在平台级守卫下常常不可行，正解是改成单向派生（2026-08-09 I 类实测）**：`i_cycle_specs.py` 的 `I_CYCLE_SPECS` 虽无 render 消费方，但有 **6 个跨 spec 消费方**（`test_cycle_specs_row_code_evidence` / `test_cycle_specs_account_evidence` / `test_semantic_resolver_coverage` / `test_render_fetch_smoke` + 2 个诊断脚本），其中跨循环兜底码互斥判据要**迭代 `spec.slots[].fallback_standard_codes`** ⇒ 删文件或改成薄 re-export 都会让平台守卫打红或空转。正解 = **保留文件、保持 `SemanticAccountSpec` 形态、但全部取值从上游真源派生**（本例从 `I_CYCLE_ROW_CODES` + `I_CYCLE_SEGMENTS` 构造，文件内零 row_code/兜底码字面量），守卫判据相应改为「AST 级断言无 `SemanticAccountSpec(row_code=<常量>)` 字面量」而非「文件不存在」。**删之前先 grep 消费方要含 `backend/tests/**` 与 `scripts/diagnose/**`**。
- **🔴 守卫按 spec 的字段假设写会产出「实现缺陷」假象，先查真实 dataclass 字段（2026-08-09 I5 三态实测）**：spec 通篇写「`found=False` 时…」，而 `ISegmentAccounts` **压根没有 `found` 字段** —— 三态判据实际是**码集空/非空**（前端共享件 `isAccountAbsent()` 同源）。⇒ 不为守卫给生产 dataclass 新造字段（会多一个需与码集同步维护的真源），改断言 + 加一条「有意不设 `found` 字段、判据是码集」的反向锁死。判据形态选定前一律 `grep 'class X'` + 读字段清单。

- **🔴🔴🔴 「既有守卫全绿」可能是因为它把**错值当基线钉死**了 —— 判某声明表对不对，禁把既有守卫的期望值当判据（2026-08-09 I 类实测，错码长期存活的唯一原因）**：`test_i_cycle_accounts.py::TestResolveRowCode` 用 12 个参数化用例逐条断言 `resolve_row_code('I1',['listed_standalone']) == 'BS-033'` 等**全部错值**，连 `test_empty_standards_returns_listed` 也断言错码 ⇒ 守卫在保护错的那一侧，任何「按守卫判断现状是否正确」的复核都会得出「已验证」的反向结论。**判据只能是外部真源**（本例 `report_config` 连库对账）。**配套的新守卫必须双向锁死**：既断言真源正确（Property 1），又断言**旧守卫的期望值里不得残留错码 + 必须出现正确码**（Property 42），否则改完真源后旧守卫会以「回归」形态打红，下个会话很可能把真源改回去让它变绿。同族已记：「守卫的表名清单漏一张 = 假失败」「按版本号手写清单的守卫会静默过期」。
- **🔴🔴 「A 循环的 row_code 被整体错位成 B 循环的正确码」是可复现的抄袭型缺陷，判错值要逐个查 row_name 不能只看「像不像本循环的码」（2026-08-09 I 类第二例，L 循环公式预设已有第一例）**：I 类 listed 侧实测 `I1=BS-033`(实为开发支出=I2 正确码) / `I2=BS-035`(长期待摊=I4 正确码) / `I3=BS-037`(其他非流动资产=I5 正确码) / `I4=BS-038`(**非流动资产合计**，ROW 派生行) / `I5=BS-040`(**流动负债：**节标题，formula NULL) —— 前三个是**整体偏移**、后两个溢出到派生行与节标题。**这类错值天然「看起来合理」**（都在 `BS-03x` 段、都在资产段附近），只有连库查 row_name 才能判。且 **`ROW()` 派生行与节标题这两类错值最隐蔽** —— 前者 `extract_signed_codes` 抽不出 `TB()` ⇒ codes 空 ⇒ 静默退兜底；后者 formula 为 NULL ⇒ 同样静默退兜底，两者都表现为「金额正确、只有溯源失真」。
- **🔴🔴 「为掩盖错码而建的护栏」会让错码永久潜伏，读到这类护栏的 docstring 要反问「它挡的到底是不是真问题」（2026-08-09 I 类行名闸实证）**：`i_cycle_accounts` 的 `row_name_matches` 校验闸 docstring 写着「实证 `BS-050` 在 soe 下 formula 为 None，共享件兜底会取到 listed 的『合同负债』公式 → 行名不符即丢弃」—— 逻辑本身对，但**前提是错的**：`BS-050` 压根不是 I5 的行（它是「其他应付款」），I5 正确行是 `BS-037`。⇒ 作者把「用错了行号」的症状当成「平台兜底机制有缺陷」，建了个闸门把症状挡住，于是 6 个 render 的报表行解析层**整体空转**（`resolved_from` 全退 `fallback`）而无人察觉。**该闸门本身要保留**（它对真实的跨准则兜底问题确实有效），但要从「掩盖」转为「防回退」，并配一条 row_code ↔ row_name 的外部对账守卫。
- **🔴🔴🔴 `ast` 的 `col_offset` 是 **UTF-8 字节偏移**，按字符切片改中文行必错位并写出语法错文件（2026-08-09 G7 Task 5 实测）**：改 `("项目", "被投资单位")` 得到 `("label"投资单位")` —— 前面的中文让字节偏移比字符偏移大，切片位置整体右移。正解 = 按**行**取原文后 `line.encode('utf-8')` 做字节切片再 decode（`col_offset`/`end_col_offset` 都是该行内的字节偏移）；改完必须 `ast.parse` 二次解析自检。同族已记：`strip_comments` 剥掉 SQL / 固定字符窗口截函数体。
- **🔴🔴 批量替换后必须**独立查数据**确认落盘，脚本自报与被淹没的终端输出都不算（2026-08-09 G7 Task 5 踩：apply 静默未生效）**：`execute_pwsh` 的输出被 codegraph 同步日志（几千字符 ANSI 进度条）淹没 ⇒ 看不到脚本是否真跑；随后独立查 md5 + 逐表查 key 才发现 **38 处仍是旧值**。正解 = 落地判据一律「md5 前后对照 + 抽查目标字段真实值」，且 apply 命令与核验命令**分两次执行**（合成一条时前者输出会挤掉后者）。同族已记：`--apply` 被 Ctrl+C 中断但写入已提交 / 判成败查数据不看 exit code。
- **🔴🔴 拆分「被多表共用的列常量」必须 grep 全部引用点，漏一个即运行时 `ReferenceError` 而 `get_diagnostics` 零诊断（2026-08-09 G7 一天内踩两次）**：①删 `balanceColumns` 改成两个新常量后只改了 1 个引用点（另一处在 `columns:` 与 `rows:` 两行）②笔误写成从未声明的 `importantJvPlColumns`（真名 `jointVenturePlColumns`）。两次 Volar 都返回 No diagnostics、Vite transform 也不报，**只有真跑 vitest 才暴露，且症状是 `numTotalTests: 0`（整个 suite 收集失败）不是断言失败**。⇒ ①改完这类文件一律以 vitest 真跑收尾 ②JSON reporter 的解析脚本必须打印 `numFailedTestSuites` 与 `testResults[].message`，否则「零收集」会被误读成「全绿」。
- **🔴 「一份列常量被两张表共用」是 G7 偏差的主因，判据 = 两表在源 xlsx 的列名/父表头是否相同（2026-08-09 归纳，本轮修 4 处）**：`balanceColumns`（期末数 vs 期初数）· `currentPriorColumns`（FS `期末数/期初数` vs PL `本期发生额/上期发生额`）· `IMPORTANT_ASSOCIATE_SUB`（同上，FS/PL 共用一个 sub）· soe 侧 `_ASSOC_FS_SUB`/`_ASSOC_PL_SUB` **已是正确的拆分范式**（带「不得简写」注释）⇒ 遇到共用常量先照 soe 侧范式拆，**拆分只动 label/group、列 key 一律不变**（key 变了才丢数据）。
- **🔴🔴🔴 「幂等脚本 `--check` 归零 + 守卫全绿」不足以判「数据落地成功」——先问「这份数据有几个写者」（2026-08-09 `row_type` 实测，本轮最贵一条）**：`fix_note_expandable_rows.py` 标好 121 行、`--check` 0 欠账、100 例守卫全绿，而**下一次别人跑 per-cycle `--apply` 就把 4 行翻回去**。成因不是「并发会话互相回退」（那是两个会话改同一文件），而是**两个脚本都在正确执行自己的意图、只是判据各写了一份** —— `fix_note_h_policy_chapter_structure.py` 的 `ADD_TABLES` 走 `if len(tables) != 1 or tables[0] != want:` **深比较整表**后 `sec["tables"] = [want]` 整表重写，`want["rows"]` 里硬编码 `"row_type": "data"`。⇒ **判据 = 对目标字段做 AST 级全库写者扫描**（不是数字符串），逐个确认判据是否同源；消解方式是**把判据收敛到 service 层 + 让共享行构造器（`_note_structure_kit.data_row()`）marker-aware**（凡走它的脚本自动免疫，本轮 4 个脚本因此无需改），而不是逐个脚本各修一遍。**冲突消解的硬判据 = 两个写者的 `--check` 同时 0 欠账**（守卫真跑 subprocess，不做源码级近似）。
- **🔴🔴 同一关键词有「构造/检测/打印」三种用法，守卫判据必须用 AST 区分（2026-08-09 实测：字符串计数法报 11 处冲突，真的只有 5 处）**：①**构造行** `{"label": "……", "row_type": "data"}` = 冲突；②**检测/删除集合** `PLACEHOLDER_ROW_LABELS = {"……","..."}` / `in {...}`（`ast.Set`）= 合法，5 个脚本在用；③**打印截断** `print(f"{t[:40] + '…'}")`（`JoinedStr`）= 合法；④**只在 docstring 出现** = 合法。判据 = `ast.Dict` 同时含 `"label": <关键词常量>` 与 `"row_type": "data"`；或本地行构造 helper（形参含 `label`、return 的 dict 里硬编码）被关键词字面量调用。按字符串计数会打红 7 个正确脚本。
- **🔴🔴 「判据只许声明一份」的守卫不能按名字判，要按**值形态** + 排除过于通用的函数名（2026-08-09 两处假阳性）**：`mutate_*.py` 里 `MARKERS = BACKEND / "scripts" / "x.py"` 是个 **`Path`**（纯名字撞车）；`remap_note_report_row_codes.normalize_label` 是**报表行名归一**（去 `△▲`/章节序号/`其中：`前缀），与本域判据毫无关系。⇒ 词表判据改「只有含目标字符串的 tuple/list/set/dict **字面量**才算副本」；把 `normalize_label` 这类通用名移出专有名清单；并配「扫描器对 service 自己必命中」的反向自检防解析失效空转。
- **🔴 `--deselect` 对**参数化用例**必须写全 nodeid（带 `[参数]`），写不带参数的形式**静默不生效**（2026-08-09 CI 实测仍 4 failed）** → 排除整组参数化一律用 `-k "not test_a and not test_b"`。配套：逐步实跑 yml 的探针必须用 `shlex.split`，按空格 split 会把 `-k "not a and not b"` 拆成多个参数 ⇒ pytest 报 `file or directory not found: not`（**探针缺陷不是 yml 缺陷**）。
- **🔴 「我的 CI job 为别人的欠账背红」有三种正确处置，按成因选（2026-08-09 一次遇到三种）**：①**下游常量未跟随上游改动**（`BS-031`→`BS-041`）⇒ **代为修常量**（值三重确证 + 纯常量零风险 + 有反向锁死守卫防误改）②**别的域的历史欠账**（`_tables` 残留缺 `row_type` + 第 7 个取值 `section_header`）⇒ `-k` 排除那几个用例 + 在 yml 里写明归属与 HEAD 对照证据（**不删整个 step**，保住其余信号）③**别人刚引入且违反平台铁律**（guidance 写了 markdown 粗体）⇒ 精确修那一处（脚本常量 + 数据双侧同改），**不跑平台级全量 `--apply`**（会剥掉另 2 处预存在的、让别的 spec `--check` 变红），**也不调基线**（「只许降不许升」的锁调高等于放行）。
- **🔴 跨 spec 判据冲突的典型形态 = 「自律断言写成了全局断言」（2026-08-09 E spec Property 30 实测）**：其 docstring 明写「`expandable` 归 C spec，**本 spec** 不改取值域」（自律），实现却是**扫全库模板断言取值域恰为 5 值** ⇒ C spec 正当落地第 6 个取值后它必红，且与自己的 docstring 自相矛盾。**这条红由引入方修**（不留给对方）：取值域放宽到 ⊆ 六值 + 第 6 个取值**从对方 service import**（交叉锁死，禁硬写字面量）+ 另加一条收窄的自律断言保住原意（本例「E1 自己负责的两张表不得出现 expandable」——**不能按章节整体排除**，因为 E1 章节里确有 9 行是正当标的）。
- **🔴 改数据文件的最小写盘脚本必须两道闸（2026-08-09 范式）**：①**命中数必须恰为 1**，否则中止（避免误改同类文字）②**round-trip 硬闸** `json.dumps(indent=2)+"\n"` 必须逐字复现原文才允许写盘（否则会重排整个 1 MB 文件并与并发会话互相回退）。

- **🔴🔴 反向自检的 fixture 必须**真的复现缺陷形态**，否则自检本身空转（2026-08-09 实测，比「守卫写坏」更隐蔽）**：给 `_ts_function_body`（花括号配对取函数体）写的自检里，朴素正则 `function f[\s\S]*?\n\}` 在**单行参数列表**的 fixture 上**恰好работает** ⇒ 「朴素正则必须失败」这条断言自己打红，而被测提取器完全正确。根因 = 真实缺陷只在**多行参数列表**（`function f(args: {\n  a?: string\n}): string {`）时出现：此时参数类型字面量的 `}` 单独成行，`\n\}` 提前命中它。⇒ **写「旧实现必红」类自检时，fixture 必须与真实触发场景同构**（本例即照 `formatTrimReason` 的真实多行签名写），并加一条「朴素实现在本 fixture 上确实失败」的元断言把这个前提钉死 —— 否则 fixture 一简化，自检就静默失去意义。
- **🔴 守卫里的「函数名」必须与实现实际导出名逐字一致，猜名会产出**假红**（2026-08-09 一轮踩 3 次）**：先写守卫后写实现时，守卫按设计文档里的名字断言（`TRIM_REASON_CODE_LABELS` / `trimReasonLabel`），而实现用了更短的名（`TRIM_REASON_LABELS` / `reasonCodeLabel`）⇒ 3 条断言以「前端镜像未找到 X（守卫自身缺陷或已改名）」失败，看着像实现缺失。**且判据落错函数同样假红** —— 「存量自由文本可读」这条语义在 `formatTrimReason`（组合码+文本）而非 `reasonCodeLabel`（纯翻译）里，落错函数会要求正确实现去做不属于它的事。⇒ 写完实现后先 `grep '^export (const|function|type)'` 核一遍真实导出集再对齐守卫。
- **🔴 通用跑批器要处理 Windows 的 `.cmd` 包装（2026-08-09 踩）**：`subprocess.run(['npx', ...])` 报 `OSError: [WinError 193] %1 不是有效的 Win32 应用程序` —— `npx`/`npm` 在 Windows 上是 `.cmd`，必须走 `shutil.which()` 解析或 `shell=True`。python 命令不受影响。
- **🔴🔴🔴 「无模板」的底稿在 OnlyOffice 链路上整条不通，且表现为 config **404**（2026-08-08 自定义底稿实测 P0；凡新增无模板 componentType 必查）**：`wp_onlyoffice_router._resolve_wp_file` 只认两个来源 —— ①OO 缓存副本 `{project}/workpapers/onlyoffice/{wp_code}.xlsx` ②**模板文件**（`find_template_file_any`）。自定义底稿没有模板、xlsx 在 `working_paper.file_path` 指的业务存储下 ⇒ 两来源都不命中 ⇒ `FileNotFoundError` ⇒ **`onlyoffice-config` 404、「在线编辑」从上线起打不开**。**更深一层：复制一份到缓存同样错** —— callback 落盘写缓存，而 `refresh_custom_projection` 读 `wp.file_path`（业务文件）⇒ OO 改动永远进不了 HTML 侧，且「xlsx 本体唯一权威」退化成两份 xlsx 打架。正解 = `_resolve_custom_wp_file(wp, wp_code)` 分流到**业务文件本体**并接进 **config / WOPI 下载 / callback 落盘三处**（非 custom 返 None 退回既有路径 = 零回归方向）；**不得对业务文件本体调 `_hide_non_target_sheets`/`_ensure_all_sheets_visible`**（会真实改写用户底稿，且 custom 恒单 sheet 不需要）。配套 `resolve_is_custom_sync`（OO 调用链是同步的，那里 await 异步判定会抛 TypeError 被吞成「退回旧路径」），**有意只判「manual + 非标准编号」一支** —— 漏判退回旧路径（安全），误判会把标准底稿本体暴露给 OO 直编。
- **🔴🔴🔴 「求值结果双写 xlsx」的副作用：靠 `cells[*].formula` 判公式格必恒空（2026-08-08 自定义底稿实测 P0）**：公式定义在 **`wp_formula` 表**，而 `write_cells_to_xlsx` 往 xlsx 写的是**求值结果**（`D4` 存数字 `0`，不是 `=TB(...)`）⇒ 前端 `formulaCells` 从 `htmlData.cells[*].formula` 派生时**恒为空** ⇒ 公式格既无 `ƒ` 标记、也不被 `canEdit` 判只读 ⇒ **审计师可双击改写公式格，改完在下次求值时被静默覆盖**（数据丢失且无提示）。正解 = `formulaCells` 由公式清单派生 + **挂载即拉**（只在打开抽屉时拉 ⇒ 用户不点就一直可编辑）+ 保存/删除后同步刷新。→ **凡「值与公式分开存」的场景，判「这格是不是公式格」必须查公式定义表，不能查值所在的载荷**。
- **🔴🔴 源码字样断言挡不住「字面还在、行为已错」，能真跑就真跑（2026-08-08 变异 M2 在纯源码判据下 GREEN）**：守卫断言「函数体里出现 `wp.file_path`」，而变异把 `raw` 改指 OO 缓存目录后**字面仍在** ⇒ 不红。正解 = 测试里真跑该 helper（造临时 xlsx + monkeypatch 判定为真）并断言返回路径 == 业务文件、且路径不含 `onlyoffice`。与「判据必须是形态而非字符」同族但更强一档。
- **🔴 前端守卫截函数体要支持**三形态**且先跳参数列表（2026-08-08 一条守卫连踩三次）**：①`onMounted(() => {...})` 是**调用式回调**不是命名声明 ⇒ 只按 `const|function` 找会报「未找到声明」②正则交替**左优先** ⇒ `function|async function` 会让 `async function foo` 里的 `function` 先命中致位置错位（须写 `async\s+function|function`）③`async function f(payload: { a: string })` 的第一个 `{` 是**参数的内联类型字面量** ⇒ 必须先圆括号配对跳过参数列表（后端已记，本轮在前端再现）。三条都要配自检钉死，否则以**假红**复发、让人误判生产代码坏了。
- **🔴🔴🔴 「守卫只断言标识符存在」抓不住「删掉调用」这一最核心变异（2026-08-08 Wave 1 变异检验实测两例，与已记的「`if False:` 逃逸」同族但更常见）**：`expect(src).toContain('resolveB50Completeness')` 在把整个 computed 换成写死值 `{ state: 'completed', ... }` 后**仍然通过** —— 因为该标识符还留在 **import 行**里。正解 = 断言「**该 computed 的实参区内**真的调用了纯函数」。**两种形态都要支持**：块体 `computed(() => { ... })` 用花括号配对（`fnBody`）、**表达式体** `computed(() => f(x))` 无花括号必须用**圆括号配对**（新增 `computedArg` helper）—— 只写 `fnBody` 会对表达式体返回空串 ⇒ 断言在空文本上求值 ⇒ 又一种假绿。→ **凡守卫要证明「A 真的被 B 调用」，判据必须落在 B 的函数体/实参区内，不能在整份源码上 `toContain`**。
- **🔴🔴 「取声明后第一个 `{` 当函数体」这个坑在 TS 的**返回类型注解**上再踩一次（2026-08-08）**：`export async function f(p: string): Promise<{ fs_risks: any[]; accounts: any[] }> {` 的第一个 `{` 是**返回类型字面量** ⇒ 截出来的"函数体"是那段类型 ⇒ 断言「函数体内含 apiPaths 访问器」在正确实现上打红（报错文本会显示 `expected 'export async function fetchB50RiskRows…' to contain 'b50RiskRows'`，看着像实现缺陷）。正解 = 从声明处起逐个候选 `{` 做配对，取第一个**含语句特征**（`return`/`const`/`await`/`if`/`for`/`throw`）的块，并配一条「跳过返回类型注解」的 fixture 自检。同族已记：参数列表内联类型字面量。
- **🔴 变异脚本的锚点含 `\n` 在 CRLF 工作树必 ANCHOR-MISS，且「命中 2 行」同样是脚本缺陷（2026-08-08 一轮 5 条 ANCHOR-MISS）**：`'                    except (TypeError, ValueError):'` 在同一文件命中 2 处（另一处是别的函数）；`normalizeFromMatrixRows` 写成独立行锚点而实际在同一行内。正解 = **行级定位**（`splitlines()` + 锚点行号 + 相对偏移 + 断言命中行数 == 1），与行尾无关；且要区分「锚点在注释里」（本轮 M9 有 1 处命中落在注释行）。**ANCHOR-MISS 既不是 RED 也不是 GREEN**，把它当 GREEN 处理会漏掉真守卫缺陷。
- **🔴🔴 判「零回归失败是否自己造成」的前后对照要看**两侧失败集合逐条相同**，别只看总数（2026-08-08 Wave 3 实测 25 failed 全预存在）**：本轮四类成因值得记 —— ①sqlite fixture 缺 `project_users`/`staff_members`/`wp_visibility_policy_epoch` 表 ⇒ wp_gate 判 `not_delegated` → 404 ②`procedure_row_task_history` **append-only 触发器**拒绝测试 fixture 的 `DELETE FROM`（DB 层保护，不是代码 bug）③coverage ledger 长期漂移 178 条（既有 `preview`/`apply` 在 ledger 里也是 0 命中 ⇒ 不是「新端点没登记」这一类）④迁移号常量过期（守卫写死 `V105__procedure_row_tasks.sql` 而实际已到 `V112`）。**`b60_chapters` router 在 `system.py` 与 `workpaper.py` 被 include 两次** ⇒ 产生一条无 `dedicated_wp_gate` 的重复路由，`test_all_dedicated_routes_have_gate_dependency` 的 `496 == 497` 就是它（判「是不是自己的新端点缺 gate」先查 `DEDICATED_COMPONENT_ROUTER_MODULES` 是否含该模块）。
- **🔴 spec 的 tasks.md 原文举的反向自检样本可能证明不了它想证明的东西（2026-08-08 Task 1 实测）**：`_parse_matrix_item_id` 有**三道互相独立**的闸（前缀锚定 `body == item_id` / suffix 白名单 / assertion 白名单），而 spec 举的 `B50-T3-balance-货币资金` 末段是「货币资金」⇒ 即便移除闸 1 也被**闸 2** 挡住 ⇒ 该样本证明不了闸 1 承重。正解 = 构造能**穿透**其余闸的样本（`B50-T3-otherprefix-货币资金-existence-RMM`，末两段恰为合法 assertion+suffix），并**另留一条断言登记「spec 原样本被闸 2 挡住」**防后续会话按原文改回去（改回去会得到「移除闸 1 仍返回 None」的假绿结论，进而误判闸 1 可删）。
- **🔴🔴 B50-3「审计范围」三键的值列不同，照抄同一列会让两个恒空（2026-08-08 实证 `useB50RiskMatrix.ts`）**：`B50-T3-balance-{account}` 值在 **`remark`**（数值字符串）· `B50-T3-category-{account}`（`scot`/`amount_only`/`other`）与 `B50-T3-estimate-{account}`（`Y`/`N`）值在 **`conclusion`**。且 **balance 不可解析时必须留 `None` 不写 0** —— 写 0 会被下游重要性判据当成「余额为零」自动裁掉该科目程序（「未填报」与「余额为 0」必须可区分）。
- **🔴 同一语义的两个「完成度」口径可以并存且不得统一（2026-08-08 B50 定论）**：`useB50RiskMatrix.incompleteAccounts` = 「**任一**认定 combinedRisk 为 null 即未填完」（服务矩阵填写完整性提示）；本 spec 的 `assessedCount` = 「**至少一个**认定有 RMM 即已评估」（服务「风险数据能否用于裁剪判据」，裁剪只消费 `max_risk`/`has_special`，一个认定就够派生）。统一到严格口径会让「只填了关键认定」的项目在裁剪页恒显示「B50 未填」而无法使用风险维度 ⇒ 守卫要有一条「同一份数据下两个口径结论不同」的断言把差异钉死。
- **🔴 `load_b50_accounts()` 已有现成端点暴露，做 B50 相关前端功能前先查（2026-08-08）**：`GET /api/b60/b50-risk-rows`（`b60_data_pull.py`，本为 B60 六/七章一键带入而建）直接返回 `{fs_risks, assertion_risks, accounts}`，`accounts` 就是 `load_b50_accounts()` 输出 ⇒ 裁剪页取 B50 完成度**零后端改动**。别新建 `/api/b50/risk-rows` 之类第二个端点（会让同一数据出现两个读取口径）。**apiPaths 此前完全没有 B50/B60 条目**，新增挂在已被 barrel re-export 的 `riskAssessments` 对象内即可（不必改 `index.ts`）。

- **🔴🔴🔴 前一轮/前一会话给出的「量化台账」必须独立复算才能写进设计，照抄会让整份实现路径走偏（2026-08-08 G7 实测，一次推翻 7 处）**：初稿 requirements 的偏差数字全部由人工目视得出，实算探针一跑，**成因判反 1 处、数量错 4 处、已绿被当待修 1 处、待裁决问题压根不存在 1 处**。最贵的是**成因判反** —— 「flat 表态不一致 ≈15 处」实为「6 张表丢了 `group`」，`flat` 只是症状；照初稿「补 flat」会让 `_extract_column_groups` 见 `flat` 即返 `[]` 把 group **永久打掉**（修症状反而制造新缺陷）。→ **判据三条**：①台账里的总数要能对上「表数」或「某一类计数」之一，对不上（G7 的「32」两者都不是）说明来源不可靠 ②同一份文档里数字与清单矛盾（写「5 处」列了 6 项）即整份重算 ③**「A 与 B 两类偏差完全同表共现」是成因单一的强信号**，别按两类分别修。复算成本极低（一个 `.spec.ts` 探针跑真实 `build*Columns()`），收益是避免整波返工。
- **🔴🔴 判「列 key 分叉」的风险前必须先分清**标签列**与**数据列** —— 前者零数据风险且是单一裁决，后者才需要量化闸（2026-08-08 G7 定论，全平台适用）**：行名真源是 `rows[].label`，`_cell_meta`/`_cell_modes` 按 **value 列**索引键、标签列不算数据列；且投影器 `note_sub_table_projector._project_row` 有**双向兜底** —— L67-68 在 `label_key != "label"` 且行内无该键时从 `label` 复制过来，L204-205 反向在标签值为空时回退 `r.get("label")`。⇒ 改标签列 key **不丢数据**，16 处「偏差」实为 1 次裁决。**平台惯例 = `key: 'label'`**（266 个标签列定义里 **241 个（91%）**、跨 70 个文件；G7 硬编码的 `'项目'` 全平台仅 7 处且全在 G 循环 = 少数派偏离，另中文字面量当 key 违反禁硬编码）。→ 遇到「两侧列 key 不一致」先看该列有没有 `is_label: true`，有则按惯例统一、不必量化。
- **🔴🔴 `ColumnDef.is_label` 是比 label 文字更危险的对齐维度 —— 两侧表态不一致会让 group 索引**整体偏移一位**（2026-08-08 G7 新登记）**：`_extract_column_groups` **跳过** `is_label` 列且 `header_idx` **从 1 起**（headers[0] 是标签列），故一侧标了一侧没标时，`{group,start,span}` 的 `start` 全体错一位 ⇒ 两级表头父子对应关系整体错开，而列名列数看着都对。实测 G7 当前 0 偏差（属**已绿需防回退**），但原设计完全没覆盖它。→ 凡做「seed ↔ 运行时」列对齐守卫，必须把「每表两侧 `is_label` 列数相等且为 1」作独立断言，不能只比 key/label/列数。
- **🔴 附注模板跨章节**同名表大量存在**，三方比对必须按 `(章节, 表名)` 二元组索引（2026-08-08 G7 实测，按表名全局索引已产出一次假结论）**：listed **63 个**表名出现 >1 次（`长期股权投资` 出现 3 次）、soe **40 个**。我第一版探针按表名全局查，把 `长期股权投资` 匹配到**会计政策章的空壳版**（`columns=0`）→ 报出「seed 无列定义」的假偏差。同族已记：「按 `section_number` 查模板必须先由 `current_standard` 定变体」「20 个章节号在两份模板间撞号」。→ 凡以表名为键跨 seed/运行时/源模板比对的，索引一律带章节；且要断言「同章节内表名唯一」（撞名会让 `sub_table_data` 字典去重丢整张表）。

- **🔴🔴🔴 characterization 的期望值必须**先跑实测再冻结**，按直觉写就是「拿假设当基线」（2026-08-08 一轮踩 3 条，B spec Task 18）**：①`is_guidance_paragraph` 的真实判据是「**整段被成对括号包裹**（`（）`/`()`/`【】`/`《》`）**且**含指引关键词」两条同时成立 ⇒ 裸 `提示：不适用的项目请删除` = **False**、`（注：…）` = True、`【本表由系统自动生成】` = False（有包裹无关键词）；按「含『提示』二字即指引」写必红 ②**`note_word_exporter.fmt_amount_gt(0)` = `''` 不是 `'-'`**（该函数 docstring 明写「空值/零值留白」R5.2 验收 8），而同模块 `_format_amount(0)` = `'-'`、前端 `displayPrefs.fmtAmount(0)` = `'-'`（`showZero` 偏好）—— **三者不同源，是有意分叉，禁「顺手统一」**（守卫已加反向锚定：`_format_amount(0)` 一旦不再是 `'-'` 即打红）③`_extract_column_groups` 在真实两份模板上实测 **none=0 / empty=506 / grouped=159** ⇒ `None` 态（未声明 flat/group）**在真实数据里根本不出现**（各 per-cycle spec 已把列元数据补齐），断言「三态都要有样本」会把「列元数据已补齐」这件好事打红 ⇒ 三态**语义**改用替身行使、真实数据只断言实际分布。→ **凡写「某函数对某输入应返回 X」的断言，先落一个探针打印实际返回值**；且这类判据要写清「按实测冻结」，防下个会话又按直觉改回去。
- **🔴🔴 「同一不变式两处实现」在守卫与被测脚本之间同样会发生，正解是让守卫 `import` 被测方的函数（2026-08-08 Property 37 实测）**：验收脚本内有运行期自检 `_self_check_no_forbidden_writes`，守卫文件里又自带一份 136 行的同款判据 ⇒ 改一处另一处不红（本 spec 全程在治的缺陷模式，自己却犯了）。正解 = 脚本导出**模块级纯函数** `find_forbidden_writes(src) -> list[str]`，脚本自检调它、守卫用 `importlib` 加载脚本模块后 import **同一个函数对象**，并加一条 `TestCriteriaSingleSource`（断言函数对象 `is` 同一 + 本守卫文件里不得再出现 `def find_forbidden_writes`）。**动态加载脚本当模块必须先 `sys.modules[name] = mod` 再 `exec_module`**（否则 `@dataclass` 在 `dataclasses._is_type` 里拿 `sys.modules.get(cls.__module__).__dict__` 得 `None` → `AttributeError`，与被测代码毫无关系、极易误判成脚本坏了）。
- **🔴 源码守卫「必须含某调用形态」的判据禁用 `[^)]*` 截实参（2026-08-08 又踩，与固定字符窗口同族）**：`write_text\([^)]*encoding=` 遇到实参里的任何 `)`（如 `"\n".join(x)`）就提前结束 ⇒ 在**正确实现**上假红。正解 = 写一个**圆括号配对**的 `_call_args(src, func)`（跳过字符串字面量内的括号）取完整实参文本再判，并配「不含该关键字的替身必须打红」反向自检。
- **🔴🔴🔴 「N 向锁死」里**两条边各自成立不蕴含第三条边成立** —— 判守卫覆盖面要按**边**数而非守卫数（2026-08-08 G7 列结构实证，平台级，可套用到全部「源模板 ↔ 模板 seed ↔ 运行时载荷」三真源场景）**：G7 有两个守卫且各自全绿多轮，却让 **32 处列偏差**长期存在。逐个探针后成因清楚 —— `backend/tests/test_note_g7_structure.py` 对两个运行时模型的引用数 **0**（只覆盖 源xlsx↔seed）、前端 `_disclosureSubtableContract.helper.ts` 对 `xlsx` 的引用数 **0**（只覆盖 seed↔运行时，且其 P3「group/flat 必表态」只对**主章节**生效，跨章 `七、1` / soe 13 个 `七、…` 落在两守卫的交集之外）⇒ seed 可以同时「与源 xlsx 一致」且「与运行时不一致」。**探针手法（几秒出结论）**：对每个守卫数 `openpyxl`/`load_workbook`（源模板侧锚点）与被测运行时模块名的引用数，**任一为 0 即该守卫不覆盖那条边**。**闭合方式禁新建第三份判据**（平台已多次踩「同一不变式两处各写一份 ⇒ 改一处另一处不红」）：让三条边各被断言恰好一次 —— 源模板真源仍 openpyxl 直读，另一端在 TS 时用「后端生成源模板**列事实投影 JSON** + 后端守卫钉死它与实时读取逐字相等（stale 检测） + 前端守卫读该 JSON 并**真调**运行时构造函数」，投影层不会变成独立真源。
- **🔴🔴🔴 「按某数组顺序」类断言的 fixture 顺序必须复现**真实真源顺序**，否则断言恒真且会掩盖缺陷（2026-08-09 E1 受限桶实证，这是上一条能潜伏这么久的根因）**：`e1CurrencyScope.spec.ts` 的 `DEFS` 样本按 docx 序排列（`bank_acceptance` 在前），而后端真实声明序是 `letter_of_credit` 在前 ⇒ 「行序按数组下标」的旧实现在该 fixture 下**照样通过**，用例标题「行序按后端 bucketDefs 声明顺序（与源模板行序一致）」声称的等价关系本就不成立却无人察觉。正解 = fixture 复现真实声明序 + 另加一条反向自检（去掉新排序字段时行序退化成数组下标 = 复现旧缺陷形态）。→ 写这类断言时先问一句「我的 fixture 顺序和被测真源的顺序一样吗？」
- **🔴🔴 展示序真源不能一律按 `source_ref` 单元格行号派生 —— 两个真源（xlsx / docx）的行号不在同一坐标系（2026-08-09 E1 Task 23 实测，偏离 design 初稿）**：受限桶前 5 类 `source_ref` 是 `附注披露信息(国企)!A17~A21`，而第 6 桶真源是**附注 docx**（`r6`，xlsx 压根没这行）⇒ 混排会把它排到最前。正解 = 展示序另立显式元组（`E1_RESTRICTED_DOCX_ROW_ORDER`，零新增 dataclass 字段），并**保留初稿的洞察作交叉锁**：五个 xlsx 源桶的元组顺序必须与其 `source_ref` 行号升序一致（两个独立口径互证，任一侧被改都打红）。→ 凡「从引用串里抽行号排序」的方案，先确认全部条目的引用串同源。
- **🔴 分类桶新增关键词要覆盖**客户实际简写形态**，否则被兜底桶的宽关键词吃掉（2026-08-09 实测）**：`statutory_reserve` 按 spec 只写 `法定存款准备金`/`存款准备金`/`备付金` 时，`存放中央银行法定准备金专户` 落到 `other`（命中它的「专户」）⇒ 必须补简写 `法定准备金`，并用同一形态做「挪到 other 之后必红」的反向自检。
- **🔴 幂等脚本 docstring 里的「改造前欠账」清单在真源改判后必须同步改写（2026-08-09 E1 附注实测）**：`fix_note_e1_monetary_fund_structure.py` 原 docstring 把「首行是库存现金」「境外款项行是假行」「②表多第 6 类」当作**要修的缺陷**记载（那是以底稿 xlsx 为附注真源得出的结论，已被「真源是 docx」推翻）—— 不改它，下个会话会照它把这三处再改回去（平台已因此返工过一轮）。
- **🔴🔴🔴 「一份顺序被两个语义共用」是隐蔽的双真源，且既有守卫可能正在锁死错的那个（2026-08-08 E1 受限桶实证，可推广到全部「顺序有语义」的常量表）**：`E1_RESTRICTED_BUCKETS` 的声明序同时承担 ①**匹配优先级**（含包含关系者必须先声明：「信用证保证金」含「保证金」须先于兜底桶、「境外冻结存款」同含两词须境外优先）②**附注行序**（前端推送排序用 `bucketDefs` 数组索引）。两者实际不同（`信用证↔银行承兑`、`境外↔质押` 各互换）⇒ **附注行序与源 docx 不符**，而既有用例标题写着 `行序按后端 bucketDefs 声明顺序（与源模板行序一致）` —— **标题声称的等价关系本就不成立**，守卫在保护一个错的不变量。**判据**：凡「顺序有语义」的常量表都要问「有几个消费方？它们要的顺序是同一个吗？」**低成本落法**：展示序往往已隐含在既有字段里（本例 `source_ref` 的单元格行号 `A17`~`A21` 恰为 docx 行序）⇒ 派生出 `displayOrder` 即可，零新增字段；守卫必须**双向锁死**（打乱声明序 → 分类红/展示序绿；改 source_ref → 展示序红/分类绿）。
- **🔴🔴 「注释承诺了但零实现」要按 dead output 一类对待，排查手法 = grep 承诺词（2026-08-08 第三例）**：`E1_MAIN_ROWS_LISTED` 的 `finance_co`/`accrued`/`digital` 三行 `crossKey: ''`，注释明文「由审计师手工填或**由 render 的语义槽预填**」而预填链零实现；同族已记 E1-4 预设 description 承诺「由 render 语义槽 `digital` 下发」同样未兑现。⇒ 扫「由…预填 / 由…下发 / 后续由… / 待接入」这类**承诺词**再核实现，比按符号 grep 更有效；它比普通 dead output 更坏（读者以为已实现故不会再问）。
- **🔴 `tb_aux_balance` **没有期末原币余额列、也没有汇率列**（2026-08-08 E1 实测，补上条 aux 条目）**：只有 `opening_fc`（且 `aux_type='银行账户'` 下**全库为 NULL**），无 `closing_fc`；`currency_code` 是 `String(3)` NOT NULL 默认 `'CNY'` 且银行账户维度 308 行**全为 CNY**。⇒ 任何「从 aux 下发原币金额/汇率」的方案不可实现，只能下发币种、其余留空由审计师填（禁由本位币金额反推）；「有外币账户则提示」这类分支当前 **0 命中 = 潜伏态**，须用替身构造非 CNY 账户证明分支可达。
- **🔴 python-docx 抽「某章节下的表格」必须沿 `document.element.body` 的段落/表格**顺序流**走（2026-08-08）**：只遍历 `doc.tables` 拿不到「哪张表属哪个章节」。配套：章节定位按 `paragraph.style.name == 'Heading N'`（Word 自动编号，段落文本不含「五、」），**listed 是 Heading 2 而 soe 是 Heading 3**（两版层级不同，已记）。实证收获：**listed docx「货币资金」标题下只有 1 张表**（受限内容是文字段落）⇒ 平台的 listed 受限表是补充表、无 docx 依据；soe 主表 6 行**不含**「存放财务公司款项」「存款应计利息」（listed 8 行有）= 准则口径差异不得对齐。
- **🔴🔴 `.el-overlay` 是**嵌套**的：子对话框与宿主共用同一个 overlay 节点，点它的 `.el-dialog__headerbtn` 会把宿主一起关掉（2026-08-08 抽凭实测丢掉一次已填样本）**：`Array.from(document.querySelectorAll('.el-overlay')).find(o => o.innerText.includes('子对话框标题'))` 命中的是**宿主** overlay（宿主 innerText 含子对话框全文）。关最上层对话框一律用 `press_key Escape`；判「哪个 overlay 是可见的那个」看 `offsetParent !== null || clientHeight > 0`（同页可有 20 个隐藏 overlay）。
- **🔴🔴🔴 `-k "a or b"` 经 cmd/PS 会被拆成多个参数 ⇒ pytest 报 `file or directory not found: or` 且 **collected 0**，而差集比较看起来「两侧失败集合相同」= 假绿（2026-08-08 零回归脚本实测）**：`python -m pytest -k "sampling or voucher"` 的引号被 shell 吃掉，`or`/`voucher` 变成两个位置参数。**两条配套**：①零回归/变异脚本一律用 `subprocess.run([...])` **不经 shell** 传参数列表；②必须加「passed < N 即中止」自检闸（collected 0 时 passed=0，闸门立刻打红），否则「跑了 0 个用例」与「全部通过」在退出码上不可区分。同族已记：vitest 的 `-t ""` 把全部用例判 skipped。
- **🔴🔴 PowerShell 的 `>` 与 `Out-File` 都会二次编码 python 的 UTF-8 中文输出（2026-08-08 连踩两次，`Out-File` 更糟）**：脚本内已 `TextIOWrapper(encoding='utf-8')` 强制 UTF-8，PS 再按 GBK 解码后存成 UTF-8 ⇒ 全文 mojibake。唯一可靠写法 = **`cmd /c "python x.py > f 2>&1"`**（字节直通）；或让脚本自己 `Path.write_text(..., encoding='utf-8')`。
- **🔴 判「浏览器实测能不能安全点某个按钮」要先用源码探针数该端点的写库动作（2026-08-08 抽凭范式）**：`voucher_extract` 函数体内 `record_extraction_log`/`db.add(`/`commit`/`flush`/`INSERT`/`UPDATE` 命中数**全为 0**（唯一疑似写入的 `VersionTrailService.create_snapshot_fire_and_forget` 实测 `workpaper_snapshots` 164→164 未增行）⇒ 抽样预览可安全实测；真正写库的是 **`重新推断`**（`POST /voucher-evaluation` 同时写权威 `extraction_criteria.evaluation` 与投影表 `sampling_records` 五个字段）⇒ 实测前必须抓 `jsonb_typeof(...->'evaluation')` + 那五个字段作基线。**`updated_at` 不可作变更判据**（该 UPDATE 不触发 onupdate，实测前后逐位相同）。
- **🔴🔴 守卫里写下的期望数字必须**独立复算**，禁拿被测代码的输出当期望（2026-08-08 实测，首版手算错 0.013%）**：本轮用 python `Decimal` 独立算出 `20850.69/67022.89×4857866.37 = 1511272.73`，并用「真实库那次落库的 3412422.05」交叉验证旧口径 ⇒ 两个方向都不是自证。**浏览器复测要固定随机种子**（本轮 seed=20260808）否则样本每次不同、无法与手算值对账。
- **🔴🔴 「先打红」守卫必须把断言分两类，否则无法区分「功能未实现」与「守卫自己写坏了」（2026-08-08 E 类 Task 1 落地范式，可推广到全部 Wave 1 守卫）**：**类 A = 独立口径判据**（用守卫自己的 SQL/纯计算算出事实：数据存在性 / 冻结基线 / 与另一张表勾稽 / 反向自检），**现在就应该全绿** —— 绿了才证明判据基础设施有效而非空转，同时天然兑现「不拿被测函数证明自己」；**类 B = 被测实现**（API 齐备性 + 实现产出与类 A 口径一致），**现在应该全红**。实测 10 例 = 7 绿 3 红，红的消息直接写「xxx 尚未实现（Wave N Task M）。本条红是**预期**的 Wave 1 打红结果」。**配套三条**：①**禁在模块顶层 import 生产模块** —— 顶层 import 失败会让整个文件 collection error、零断言执行，那时「全红」既可能是功能没做也可能是守卫写坏；改为测试内 try-import 后 `pytest.fail`（**不是 skip**）②反向自检若依赖「库里恰好有某种脏数据样本」，无样本时必须 `pytest.skip` 并在 reason 里写明「暂不可验证 + ⚠️ 这不等于可以省掉该逻辑」，否则数据一变就成静默假绿 ③冻结基线的口径要**不依赖被测实现**（本例按 `count(DISTINCT aux_name)` 而非「解析器解析出的账号数」，否则解析器一改基线就跟着漂）。
- **🔴 用 subprocess 跑 pytest 必须传 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，否则中文断言消息全成乱码（2026-08-08 踩，与已记的「GBK 不可编码字符被转义成 `\uXXXX`」是**不同**的坑）**：pytest 在 Windows GBK 控制台按 GBK 编码输出中文，而 subprocess 用 `encoding="utf-8"` 解码 ⇒ 断言消息变 `��δʵ��`，**完全无法判读失败原因**（不是部分转义而是整段乱码）。已建通用跑批器 `backend/scripts/diagnose/_wip_run.py`（写盘 + 强制 UTF-8 + 超时 1800s），后续跑测试一律走它，别再手写 subprocess。
- **🔴🔴🔴 `tb_aux_balance` 的 `aux_dimensions_raw` **一行即含全部维度组合**，是「账户级/多维度」取数的隐藏金矿（2026-08-08 E 类实证，可推广到全平台）**：格式 `金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296`（`维度名:码,名称` 分号分隔）⇒ **不需要跨 `aux_type` 配对**就能同时拿到「开户银行 + 银行账号」。E 类实证：`aux_type='银行账户'` 全库 **114 个账户名**，各项目 1002 账户数 38/22/21/23/17/6/2/1，而 `tb_balance` 侧客户 **1002 不分户**（叶子恒 1 行）⇒ 账户级明细**只能**从 aux 取。**带 `get_active_filter` 后与 `tb_balance` 逐分勾稽成立**（8 项目 × 全部科目：`1002`/`1012.02`/`1012.03`/`1012.04`/`1012.11.03` 全等）。**两个坑必堵**：①非 active dataset 有**完全重复行**（同 `aux_dimensions_raw` 两行、`closing_balance` 相同、一行有 `raw_extra` 一行无）⇒ 裸求和翻倍，必须走 `get_active_filter`（这正是「四表查询统一入口」铁律的由来）②active 内**同账号可有多行**（`a7fc75e5` 的 `1207014210004455` 有 +25,954,468.80 与 −25,874,468.80 两笔，`rows=39 names=38`）⇒ 必须按 `aux_dimensions_raw`/`aux_name` GROUP BY + `SUM(COALESCE(...))`。**`aux_code` 全库为 NULL**，只能用 `aux_name` 作标识；`closing_balance` 可为 NULL（非 0）。→ **凡「底稿要逐户/逐项目/逐维度列示，而 tb_balance 叶子给不出」的场景，先查 `tb_aux_balance` 有没有对应 `aux_type`**（`银行账户`/`金融机构`/`成本中心`/`客户`/`职员`/`保证金类别`/`借款性质`/`政府补助项目`/`金融工具` 等 33 种）。
- **🔴🔴 外币货币性项目章节 soe 八、92「短期借款」段首行 `report_row_code='BS-031'` 是错码（2026-08-08 实测，未修）**：`BS-031` = **使用权资产**（四准则一致 `TB('1641')+TB('1651')-TB('1642')-TB('1652')-TB('1643')`），短期借款真值 **`BS-041`**（`TB('2001')` 四准则一致）；该行 `account_codes:['2001']` **是对的**，只有 row_code 错。**两类后果**：①K 循环接入该表推送时按 `BS-041` 声明 `_row_scope` → `find_segment` 返 None → **fail-closed 整表跳过写入**（表现为「推了但没进附注」）②H8（使用权资产 `BS-031`，`h8_account_scope.py`/`dual_family_codes.py` 正确使用该码）若接入外币表 → **错配到短期借款段、把该段行替换成使用权资产的行**（数据污染）。连带需改：`e1FxNoteSectionMap.ts` 的段归属注释表、派生清单 `note_shared_table_segments.json`（**该 manifest 的 `_note` 明确「服务端运行期直接读模板、不读本清单」** ⇒ 运行期错的是模板本身）。→ **凡共享表段首行的 `report_row_code` 都要与 `report_config` 对账**，`account_codes` 对不代表 row_code 对。
- **🔴🔴 共享表段切分的字段名是 `row_code` 不是 `owner_row_code`，且 `find_segment(rows, owner_row_code)` 第一参是**模板 rows** 不是 segments 列表（2026-08-08 踩，一度误判「E1 外币段推送从来没成功过」）**：`split_segments(rows) -> list[Segment]`、`Segment.row_code`、`find_segment(rows, code)`、`resolve_segment_window(variant, section_number, table_name, owner_row_code)`。按 `sg.get('owner_row_code')` 读派生清单会全得 `None`、把 `find_segment(segs, code)` 当「在段列表里查」会全返 `None` ⇒ 两个假警报叠加，看起来像 fail-closed 全线失效。→ **调共享件前先 `inspect.signature` + 读一次 docstring**，别照别处的调用形态猜（同族已记：G6 `await select_leaves(...)` 整段静默失效）。
- **🔴🔴 判「render 输出是不是 dead output」不能只 grep 子组件的 prop 与键名 —— 平台有「宿主种子化」这条通道（2026-08-08 E 类踩，差点写错整份 spec）**：E1 的 24 个子 Tab **都没有 `htmlData` prop、也不出现任何四表键**，但数据是通的 —— 宿主 `GtE1MonetaryFund` 拿 `props.htmlData.four_table_prefill` → `buildXSeedRows()` → `seedRowsKey()` 写进 `allResponses`（`if (allResponses.value.has(key)) return` = persist-first）→ 子 Tab 经既有 `:all-responses` 通道读。⇒ **判据必须是「从 render 输出键出发，沿消费链一路走到底」**：先 grep 该键在**宿主**里有没有消费，再看宿主把它写到哪个 `allResponses` 键，最后 grep 该键在子 Tab/composable 里有没有读。只查子组件必得「全是 dead output」的错误结论。同族反向教训：`e1FourTablePrefill.ts` 的消费方就是宿主自己，按「子 Tab 有没有 import」判会判成孤儿。

- **🔴🔴🔴 `TB('1511.01')` 这类**点号子科目**公式恒返 0 且不报错（2026-08-08 G7 实证，与已记的 `IMP-002 = TB('1231.02')` 同型，此处补全机理）**：`_handle_tb` 从 `ctx.tb_data.get(code, {})` 取，而 `tb_data` 按**标准码**构造（余额来自 `trial_balance`，发生额来自 `tb_balance` 经 `aggregate_occurrence` 按标准码归集）。实证 `trial_balance` 的 151x 段**只有 `1511`/`1512`/`1519`**，点号子科目 `1511.01`~`1511.04.02` 只在 `tb_balance` ⇒ 键查不到 → `account_data={}` → `_resolve_tb_column` 返 0；而 `期末余额` 是**已注册列**故 `is_unregistered_column` 为 False ⇒ **不进 `errors`**，走「诚实的 0」路径 ⇒ 与「该科目余额确实为 0」**不可区分**，公式管理页看着有配置实则恒 0。→ **凡公式预设里出现带 `.` 或 `-` 的多级码，先查 `trial_balance.standard_account_code` 有没有该码**；子科目级取数一律走 render 的叶子聚合（`tb_leaf_categories` / `adjudication_prefill`），预设侧改 `PLACEHOLDER` + description 写明真源。
- **🔴🔴🔴 `SemanticAccountSpec` 只有**单个 `row_code`**，导致 16 个多槽 spec 的非首槽产生**假冲突告警**（2026-08-08 G7 实证，平台级）**：旧 `ReportLineAccountSpec` 有 `provision_row_code`（`G7_RLA_SPEC` 里还留着、只作过渡期守卫用），语义解析器迁移时**丢了「附属槽可以有自己的报表行」这个能力** ⇒ `build_conflicts(slots, report_codes)` 拿主行 `BS-024` 的码集 `{1511}` 逐槽比对，provision 槽定位到 `1512` 无交集 → 判冲突。实测 **7/8 项目**的 G7 溯源面板恒亮 `[['provision','1511','1512']]`，而 G7 备抵**本就自成报表行** `IMP-009 = TB('1512')`。**影响面 16 spec**（G1/G4/G7/G10 + H1~H4/H7/H8/H9 + D1/D2/D6 + I1/I3），按 `report_config` 实际公式判定：**必假冲突** = G4(`BS-021` 只 1504)/G7(`BS-024` 只 1511)/H2(`BS-029` 只 1604)/H7(`BS-030` 只 1621)/D6(`BS-011` 只 1141)/I3(`BS-034` 只 1711)；**部分变体假冲突** = D1(`soe_standalone` 含 `1231-01` 不报、另三变体报)/D2/H3(`consolidated` 只 1521)；**不受影响** = H1(含 1602)/H8(含 1642·1643)/H9(含 2602)。这是**告警疲劳型**缺陷 —— 常亮假告警会让审计师忽略真冲突，而真冲突正是该机制存在的理由（`report_config` 已实证 6 处错码）。修法 = 给 `SemanticAccountSlot` 加可选 `row_code`（该槽自己的报表行），或让 `build_conflicts` 对「主行公式确实不引用该槽科目」的情形**不判冲突**。
- **🔴🔴 `subprocess.run(..., capture_output=True, text=True)` 在 Windows 上会让含中文输出的守卫**恒红且零信号**（2026-08-08 实测，backend 还有 **30 处**同款）**：`text=True` 用 locale 编码（GBK）解码子进程 stdout → reader thread 抛 `UnicodeDecodeError` → **`result.stdout` 变 `None`** → 断言以 `TypeError: argument of type 'NoneType' is not iterable` 失败 ⇒ 既判不出被测脚本真有欠账、也判不出它是好的（`test_g_cycle_formula_presets::test_disclosure_presets_script_check` 长期如此；补 `encoding="utf-8", errors="replace"` 后转绿并拿到真信号「0 项欠账」）。→ 凡守卫用 subprocess 跑幂等脚本 `--check`，**必须显式 `encoding="utf-8"` + 断言 `stdout is not None`**；同族已记：GBK 控制台 `print('✅')` 崩在写盘之后 / PS `>` 重定向腌坏 UTF-8。
- **🔴 前缀断言 `id.startsWith('ul-assoc-')` 会把结构行 `ul-assoc-group`/`ul-assoc-subtotal` 一起数进去（2026-08-08 自己踩）**：得 3 而数据行只有 1，**且与旧断言的「3 行数据」巧合重合** ⇒ 行数回退会被掩盖。判「某段有几行数据行」一律锚定 `^{prefix}-\d+$`。同族已记：`toContain('<Foo')` 被 `<FooREMOVED` 骗过 / `"DELETE" in sql` 被 `is_deleted` 骗。
- **🔴 `projects` 表列名是 `name` 不是 `project_name`**（2026-08-08 踩）：另有 `client_name`/`short_name`/`parent_company_name`/`ultimate_company_name`/`audit_year`/`template_type`/`report_scope`/`is_deleted`。同族铁律：写连库 SQL 前一律先 `information_schema.columns` 查真实列名。
- **🔴 「测试断言对象为 `undefined`」有两种成因，判生产缺陷前先看被断言的东西该不该存在（2026-08-08 G7 实测）**：`g7SoeDisclosureModel.spec.ts` 断言 `ul-assoc-3`（超额亏损联营段第 3 行）的 `source`，报 `(undefined and string) is invalid` —— 看着像「联营段血缘丢了」，实为**过时测试锁定「写死 3 行骨架」的旧行为**（后来按平台铁律⑥改成 `dynamicRowCount(seedRowCount)`，无 seed 时每段只 1 行）。生产侧血缘公式 `第${17+index}行` 完全正确。→ 诚实改写为与动态行数一致 + 保住原意图（**联营段血缘起点 G7-16 第 17 行、合营段第 12 行**，源模板 r308→`G7-16!B17` / r303→`G7-16!B12`）+ 加「两段起点必须不同」反向自检。

- **🔴🔴🔴 GBK 控制台会让 `--apply` 类脚本**在写库前就崩**，表现为「一次都没写进去」而看着像失败（2026-08-08 legacy 迁移实测）**：`migrate_legacy_note_snapshots.py` 的报告尾部含 `⚠️`，`print(text)` 抛 `UnicodeEncodeError`，而**这个 print 排在 `_apply()` 之前** ⇒ 迁移逻辑一行没执行。`--quiet` 不解决（它仍打印汇总尾）。正解 = `$env:PYTHONIOENCODING='utf-8'`。→ **凡跑带中文/emoji 输出的破坏性脚本，先设该环境变量**；且判成败一律查库不看 exit code（本轮批 3 又复现「Ctrl+C 中断但写入已提交」）。
- **🔴🔴 备份/元数据键的**嵌套路径**写错 ⇒ 基线探针静默报 0，会把「存量」误判成「本轮新增」（2026-08-08 实测）**：`_legacy_backup` 在 `table_data._template_lineage` 下而**不在顶层**，按 `table_data ? '_legacy_backup'` 抓基线得 0，而库里实有 **133 条 2026-08-01 那轮迁移的存量**（08-01 12:54~12:56 + 08-03）。⇒ 判「本轮写了多少」必须叠 `updated_at >= 本轮开始时间`，不能只看键存在性；抓基线前先用 `jsonb_pretty` 看一眼真实嵌套层级。
- **🔴 破坏性迁移的**回滚往返验收不需要「迁移前逐字节快照」**（2026-08-08 范式，可复用）**：在回滚**之前**用纯函数（`build_rollback_table_data`）算出 expected md5，回滚后比 **DB 列真值** —— 验的是「写库路径 ≡ 纯函数」，纯函数正确性由既有单测（含往返深度相等）保证，不是拿被测函数证明自己。**幂等的最强判据也不是 `skipped_already`** 而是「已处理记录不再匹配扫描 WHERE、连扫都扫不到」。**二次迁移比对必须忽略时间戳字段**（`_legacy_backup.at` 每次重新生成）。**判据方向别写反**：`md5(迁移后) == md5(回滚后)` 恒 False 是预期。
- **🔴 「返回 N 行/N 项」是恒真弱判据，结构性判据才能抓变异（2026-08-08 两级表头实测）**：`_build_two_level_header_rows` 对**任何**输入都返回 `[row0, row1]` ⇒ 断言 `len(hdr)==2` 永远通过。强判据 = row0 colspan 之和 == 列数 / 每个 group 的 colspan == 其 span / row1 逐字 == 各 group 覆盖区的 headers 切片 / 无分组列 rowspan==2 的个数正确。**且「group 只覆盖 1 列」是合法自洽形态 = 无效变异**（判据不红是对的），有效变异要让 groups 与 headers 不自洽（span 越界 / 两 group 重叠）。
- **🔴 动态加载脚本当模块时必须先 `sys.modules[name] = mod` 再 `exec_module`（2026-08-08 踩）**：否则 `@dataclass` 在 `dataclasses._is_type` 里 `sys.modules.get(cls.__module__).__dict__` 拿到 `None`，报 `AttributeError: 'NoneType' object has no attribute '__dict__'` —— 与被测代码完全无关，极易误判成脚本有语法问题。
- **🔴 `test_g_cycle_formula_presets::test_disclosure_presets_script_check` 在未设 `PYTHONIOENCODING=utf-8` 的终端**恒红**（2026-08-08 定性）**：它跑子进程后断言 `'0 项欠账' in output`，GBK 控制台把中文腌成 `0 ��Ƿ��` ⇒ 落空。设该变量后该文件 5/5 passed。→ **判 `four_table/` 域有无回归前先确认终端编码**，否则会把它当新增失败（本轮 1647 例里唯一那条失败就是它）。
- **🔴🔴🔴 裸 SQL 里写错**列名**与写错函数名同样致命，且更难发现（2026-08-07 `prefill_anchor_map` 实测 P0）**：`WHERE workpaper_id = ...` 而 `checklist_responses` 的真实列名是 **`wp_id`** ⇒ `asyncpg.UndefinedColumnError` → 被 resolver 的 `except Exception` 吞成 WARNING → 整条取值链恒返 `None`，与「本项目未编制」不可区分。**四层验证全绿**：61 例单测全用替身（`parse_anchor_value` 是零 DB 纯函数，天然测不到 SQL）· `get_diagnostics` 对 `sa.text()` 里的字符串零诊断 · 连库守卫只查 `working_paper` 那半边 · CI 无该 job。→ **凡新写裸 SQL 必须配「列名存在性」守卫**（`information_schema.columns` 比对 SQL 里抽出的列名），或至少让某一条测试真的连库跑一次该查询。判 `checklist_responses` 列名的权威 = `wp_id`/`item_id`/`remark`/`conclusion`/`wp_ref`/`project_id`（唯一约束 `(wp_id, item_id)` ⇒ 一格一行，取值查询不需要 `ORDER BY ... LIMIT 1`）。
- **🔴🔴 「HEAD 换文件跑同一组」这条零回归判据在**改动文件含他人未提交成果**时会破坏数据，一律禁用（2026-08-07 C spec 真实事故）**：三重问题叠加 —— ①`git show HEAD:` 拿到的不是「我改之前」而是「**别人那个 spec 之前**」（A spec 给两份 `note_template_*.json` 补的 104 张表 columns + soe 十二章 slug 全未 commit，换 HEAD 进去等于抹掉）②HEAD 侧有测试模块在 **import 期**读该数据文件并构造 parametrize，旧数据下抛异常 ⇒ pytest **`Interrupted: N errors during collection` 整轮 abort**（实测只执行 3 例 vs 对照 6504 例），差集全是噪声 —— 必须加 `--continue-on-collection-errors` ③脚本被 **Ctrl+C 打断时 `finally` 不执行** ⇒ HEAD 版留在工作树（本仓库并发度下 `execute_pwsh` 高频被打断，实测 52 个后台任务同时在跑）。**正解 = 前后对照**：当前态 = before → 施加自己的（幂等）改动 → after，差集即因果；幂等脚本天生可重放，被打断也只是「没应用」而非「数据被换掉」。判「是否属这类文件」= `git diff --stat <file>` 有大量非本次改动的 diff。**要临时替换文件的脚本，备份必须落 `.bak` 且提供 `--restore`，只靠 `finally` 不可靠**。**判「某批失败是否预存在」优先复用已有的历史运行产物**（本次靠改动落地后那次全量运行的 `FAILED` 清单，证明 8 组 note 模板守卫失败在动手前就全部存在）。**Kiro local history 在大文件上救不了**（两份模板只有 4 月的 18KB/16KB 早期快照）。**恢复手段 = 各 per-cycle 幂等脚本 `--apply`**（本次靠 `fix_note_parent_company_chapter.py`(105 项) + `fix_note_d4_segment_structure.py` + `fix_note_h_policy_chapter_structure.py` 完整恢复，逐项核对计数与损坏前相等）。
- **🔴🔴 源码守卫扫「某字段有没有消费方」必须剥 docstring，且 raw/code 两个口径要分开登记（2026-08-07 A spec 推送前踩，与已记的「守卫注释里写反例被数成真实调用」同族但更隐蔽）**：并发 spec 在 `note_conversion_service.py` 的 **docstring** 里写下「`legacy_aliases` 列也不存在」= 纯说明文字，裸 `"legacy_aliases" in src` 把它数成消费方 ⇒ 守卫假红且**红在别人的文件上**（极易误判成对方引入回归）。正解 = `tokenize` 剥 `#` 注释 + `ast` 剥 docstring（**不剥普通字符串字面量** —— 字典键名 `{"legacy_aliases": ...}` 是真消费）+ `DOCSTRING_ONLY_MENTIONS` 登记表配「raw 必有命中 / code 必无命中」双向自检（它哪天变成真消费方即打红，登记不会变成永久盲区）。
- **🔴🔴 基线常量必须由**实测复算**得出，禁按「apply 后应该是什么」写（2026-08-07 A spec 两条守卫红的根因）**：`TASK6_REMOVED_KEY_COUNT` 记 15（含 Task 4 的四个中间名 `其他应收款（表8..11)`），而**工作树与 HEAD 两侧该中间名计数均为 0** —— 那轮正名从未落盘（memory 已记「判某任务是否真做完必须同时查工作树与 HEAD」的又一实例）。正确值 11 = 由 HEAD 的 15 个原始表名推导后与新表名求差集。⇒ 数量类基线一律配一条「由上游状态推导的期望 == 实际」的**复算断言**（不是写死数字），并把依赖「某中间名存在」的断言降级为**条件断言**（该名真出现过才要求留痕），否则前置任务被回退时它会以「数据回归」的形态误报。
- **🔴 幂等脚本之间有**执行顺序依赖**，顺序反了会出现「都曾 --check 归零、之后又报欠账」的假象（2026-08-07 实测）**：`fix_note_parent_company_chapter.py` 的「同构子节」判据是**从合并章复制**（母公司章 `营业收入与营业成本` 表[3] 必须与 `五、62`/`八、64` 逐字段一致）⇒ 任何改合并章的脚本（`fix_note_d4_segment_structure.py`）必须**先跑**。批量恢复/重放前先查各脚本的判据是否「从别的章节复制」。
- **🔴 反向自检若依赖「真实数据里存在坏值」，坏值被清零后会变成假红（2026-08-07 又一实例）**：`test_note_shared_table_segments::test_empty_table_name_is_excluded_from_lookup` 原断言「listed 确实有 1 张空名表」，空名清零后必红。**诚实修正**为「不得出现空名表 + 扫描面非空自检 + 空串查表必返 None」，不再依赖脏数据存在。同族：派生 manifest（`note_shared_table_segments.json` 由表名派生）在改表名后必漂移 ⇒ 改名类改动要同 job 守住其生成器 `--check`。

- **🔴🔴 `ast.unparse` 会把字符串下标统一规范化成**单引号**，手写源码形态去比恒不相等（2026-08-07 spec B Task 10 实测）**：守卫判据里写 `_TARGET = 'result["format_adapted"]'` 再拿 `ast.unparse(node.target) == _TARGET` 比 → **恒收集不到任何节点** → 判据静默返回 False → **在正确实现上打红**。正解 = `ast.unparse(ast.parse(SRC, mode="eval").body)` **派生**，并配一条「派生值 ≠ 手写源码形态」的自检防下个会话改回手写。同族已记：「守卫判据必须是形态而非字符」。
- **🔴🔴 `@pytest.mark.parametrize` 的参数集为空 ⇒ pytest 整条 **SKIP** = 判据空转（2026-08-07 实测）**：`ASSERTION_MIGRATION` 里 `obsolete_by_design` 条目为 0 时，那条按它 parametrize 的理由质量闸一条都不跑，报告里只显示 skipped 不显示红。正解 = 改非参数化 + 校验逻辑抽**纯函数** + **无条件替身自检**（合格/过短/占位三态）。**且替身必须逐个闸门单独构造** —— 占位理由若不足最小长度会先被长度闸拦下，真正要验的 `no_marker` 闸测不到（须 `assert len(替身) >= 阈值` 锁死）。
- **🔴🔴 源码守卫扫「某符号是否残留」必须剥 docstring，否则会把**有意留证的删除记载**判成 offender（2026-08-07 spec B Task 10）**：删掉孤儿函数后，服务 docstring 要写「已删除（生产零调用方 + 断言已迁移）」、测试 docstring 要写迁移对照表、断言消息要写「那是旧实现的缺陷形态」—— 这些是**资产不是残留**，裸 `symbol in source` 会逼人删掉正是下个会话需要的记载。正解三件套：①判据 = `tokenize` 剥 `#` + `ast` 剥全部 docstring（含独立 `ast.Expr(Constant(str))` 语句）后扫**剩余代码**；**普通字符串字面量不剥**（可能是真消费）②文字提及逐条登记 `DOCSTRING_ONLY_MENTIONS` + 三向自检（登记项必须真含该字样防 stale / 真调用的替身必须打红 / 条目数封顶只许缩短）③另加一条**不豁免登记表**的兜底：定义形态 `def X(` 与调用形态 `.X(` 在任何文件都打红。
- **🔴🔴 「迁移对照表」类基线常量必须由**实测名**复算，禁按「应该叫什么」写（2026-08-07 实测，15 条断言假红）**：v2 测试断言迁移表的 `prod_test` 列按预期名写（`test_source_only_sections_are_archived`）而实际叫 `test_source_only_sections_archived`（少个 `are`），26 个生产测试**一个都没被指向**，而旧的「用例数 ≥ 20」断言照样通过 ⇒ 表与代码完全脱节无人察觉。**正解 = 补一条反向断言「生产测试的每个用例必须被迁移表指向 或 在 `PRODUCTION_ONLY_TESTS` 登记（带 Requirement 号 + 理由 ≥30 字 + 必须说明旧实现为何无对应断言）」+ 两表不得重叠**。「多对一」迁移（两条旧断言并入一条新测试 / 一条旧测试拆给两条新测试）必须**逐条读新测试的断言体**确认语义真被承接，不能只对名字。
- **🔴 替身 savepoint 的 `__aexit__` 必须 `return False`（2026-08-07 spec B Task 8 探针实测）**：写 `return True` 会**吞掉异常** ⇒ 生产代码的 `except Exception → failed.append` 永不触发 ⇒ 「失败章节进 failed 桶」这条根本测不出来（真实 SQLAlchemy `begin_nested()` 回滚后**会重新抛出**）。同族：失败注入要按 **note id 精确匹配**，按「第 N 次 flush」注入会让失败落在不确定的章节上，测不出隔离语义。
- **🔴🔴🔴 `ast.unparse` 把字符串下标规范化成**单引号**，手写源码形态的判据会恒 False 并在**正确实现**上打红（2026-08-07 spec B Task 10 实测）**：守卫写 `ast.unparse(node.target) == 'result["format_adapted"]'`（双引号，照生产源码抄）→ unparse 实际产出 `result['format_adapted']` ⇒ 收集恒空 ⇒ 判据静默 `return False` ⇒ 守卫报「未见守卫包住计数」而代码完全正确。正解 = **由 unparse 派生**（`ast.unparse(ast.parse(SRC, mode="eval").body)`）+ 配一条「派生值 ≠ 手写源码形态」的自检防下个会话改回手写。同族已记：「守卫判据必须是形态而非字符」。
- **🔴🔴 源码守卫扫「某符号有没有残留引用」必须同时剥 `#` 注释**与 docstring**，否则「有意留证的说明文字」会被数成 offender（2026-08-07 实测）**：删掉 v2 后，服务模块 docstring 写着「v2 已删除（生产零调用方…）」、生产测试 docstring 是 21 条断言的迁移对照表、一条**断言消息字符串**把「note_section 写成 sid」标注为「那是 v2 的缺陷形态」—— 裸 `symbol in source` 把这三处全判红，逼人删掉正是下个会话需要的记载。正解三件套：①`tokenize` 剥注释 + `ast` 剥全部 docstring（含独立 `ast.Expr(Constant(str))` 语句），**普通字符串字面量不剥**（可能是真消费）②文字提及逐条登记 `DOCSTRING_ONLY_MENTIONS` + 条目数上限 + 「登记项必须真含该字样」stale 检测 ③**另加一条不受登记表豁免的兜底判据** —— 定义形态 `def X(` 与调用形态 `.X(` 在任何文件都不放行。
- **🔴🔴 `@pytest.mark.parametrize` 的参数集为空 ⇒ 整条测试 SKIP = 判据空转（2026-08-07 实测）**：`obsolete_by_design` 关系当前为 0 条 ⇒ 按它 parametrize 的理由质量闸一个用例都不跑，而报告里显示 skipped 容易被当噪声。正解 = 判据抽**纯函数** + 非参数化测试里「对现存条目（可能为零）逐条校验 + **无条件**用替身验证判据本身有效」。**替身构造也要自检** —— 想验「理由缺实证标记」那道闸，替身必须先足够长否则被长度闸先拦下（本轮踩中，已加 `assert len(bad) >= MIN_LEN`）。
- **🔴🔴 测试替身的 savepoint `__aexit__` 必须 `return False`（不吞异常），否则「失败章节进 failed 桶」这类隔离语义永远测不出来（2026-08-07 实测）**：替身写 `return True` 会把异常吃掉 ⇒ 生产代码的 `except Exception` 永不触发 ⇒ 断言「注入失败后其余仍处理」得 0 而看起来像实现缺陷（真实 SQLAlchemy `begin_nested()` 回滚后**会重新抛出**）。同族：失败注入要按 **note id 精确匹配**，按「第 N 次 flush」注入会让失败落在不确定的对象上、健康对象也被牵连。
- **🔴🔴 变异检验的残留核验不能按「变异字样是否出现」判，`git status` 也不能当判据（2026-08-07 各踩一次）**：①注入的字样在生产代码里可能本就有**合法同形**出现（`new_prov[key] = value` 是 `_apply_row_filter` 的合法 `else` 分支，与变异注入逐字相同）⇒ 按字样判必假阳性；正解 = **正向断言「被变异的那一行是否回到正确形态」**（整行精确匹配 + hits==1）②被变异的文件在 HEAD 侧**本就是 ` M`**（前序任务未 commit）⇒ 只能用「与变异前 md5 逐字相同」判残留。
- **🔴 守卫判据「A 先于 B」是**行号偏序**，弱于「B 被 A 包住」（2026-08-07 升级实例）**：原判据「空操作守卫出现在计数之前」挡不住「守卫在别的分支里、计数其实没被它包住」，也挡不住**第二个未受守卫的计数点**。正解 = 收集全部计数节点 → 断言「`test` 为目标条件的 `If` 体内的计数数 == 全部计数数」，并配第三个替身（一个在守卫内、一个在 `else` 里）证明新增强度有效。
- **🔴 迁移表/基线常量必须由**实测复算**得出，且要配「反向：不得有无人指向的项」（2026-08-07 实测，15 条假红的根因）**：`ASSERTION_MIGRATION.prod_test` 按「应该叫什么」写（`test_source_only_sections_are_archived`）而实测名少个 `are`，21 条里 15 条目标不存在；更坏的是旧的反向断言写成 `len(names) >= 20`，在「26 个生产测试**一个都没被指向**」时照样通过 ⇒ 迁移表与被测文件完全脱节却无人察觉。正解 = 反向断言取**差集为空**（每个用例要么被迁移表指向、要么在 `PRODUCTION_ONLY_TESTS` 登记并写明 Requirement 号）+ 两表不得重叠。
- **🔴 扫描面的排除规则（如 `_wip_*` 探针）必须统一在一处做（2026-08-07 实测）**：`_non_test_call_sites` 内部单独排除了、两条符号残留判据没排 ⇒ 同一文件的自己的诊断探针把守卫打红。正解 = 在 `_iter_py_files` 这一层统一排除。
- **🔴🔴🔴 「把 null 补记成真实落点」这类 additive 数据修正，必须先查**跨行撞码**（2026-08-07 spec B Task 12 实测，差一步就把既有缺陷放大成新缺陷）**：`variant_matrix` 补记 11 个科目后，`tou_zi_shou_yi` 与 `tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d` **四个变体全部撞码**（HEAD 0 组 → 补记后 4 组）。根因是这两条本是**同一科目被矩阵拆成两条**（`build_variant_matrix.normalize_title` 只剥 `【】` 不剥括注文本，「投资收益【下表中不适用的项目，删除】」与「投资收益」归一后不相等 ⇒ 未配对，A spec 已登记为既有缺陷）—— 补记会让「未配对」升级成「两条指向同一章节号」。⇒ 已改判 CROSS_GRAIN + 给幂等脚本加**撞码闸**（同变体下多个 account 指向同一 code 即 exit 2 拒绝写盘，且只在**本次新增**的码上判、不追责 HEAD 既有状态）。→ **凡按清单批量补记「码/落点」类字段，闸门至少三道：撞码 / 落点形态 / additive（既有非 null 不得覆盖）**，三道都要用变异证明会打红。
- **🔴🔴 Kiro local history 的第二个用途 = 取证「我的文件被谁在什么时候覆盖」（2026-08-08 Task 17 实测，此前只记了「误删可恢复」）**：`%APPDATA%\Kiro\User\History\<hash>\entries.json` 的 `entries[].timestamp`（毫秒）+ 快照文件大小连起来就是一条**时间线** —— 本轮据此得出「17:18/17:21/17:23 是我三次写入（14377→29091→44352 字符），17:24:07 被整文件覆盖成 14456 B（对方第一块），此后连续追加」，比 `git status` 与 mtime 都硬（未跟踪新文件在 git 里无历史）。**配套判据**：40 秒双采样比 md5，若「只有这一个文件在变、其余相关文件全不变」即可确证是并发会话在写该文件而非环境噪声。**撞车后正确顺序 = 先抢救自己的版本（写成 `.py.txt` 留证）→ 逐例对比两版覆盖面 → 判互补还是重复 → 再决定处置**，不要看到被覆盖就直接写回去。
- **🔴🔴 `preview_note_conversion` 与 `preview_conversion` 是两个不同口径的入口，不可混用（2026-08-08 实测）**：前者是本 spec Task 15 新增的**附注章节**预览（返回 dict，走 savepoint + 显式 rollback），后者是历史**报表行次**口径（返回 `ConversionPreview` 对象）。按 spec 文字 `GET /note-conversion/{project_id}/{year}/preview` 去 grep 路由也找不到 —— 真实路由是 **`GET /api/projects/{project_id}/notes/conversion/{year}/preview?target_type=`**（挂既有 router 前缀，spec 写的是简写）。→ 写守卫前一律 `inspect.signature` + 查真实 route path，别按 spec 文字猜。
- **🔴🔴 同一服务里对同一张表的多个查询可能带**不同的软删过滤**，内存替身必须按 SQL 文本分流（2026-08-08 实测编译文本）**：`_map_disclosure_notes` 的存量查询带 `AND is_deleted = false`，而 `_create_snapshot` 与 `_rollback_section_state` 的查询**不带**（归档走软删 ⇒ 快照必须含软删记录才能复原）。替身只实现「仅未软删」那一种时，「归档进快照 / 回滚复原归档」两条路径**结构性测不到**且不报错。判据 = `"is_deleted = false" in str(stmt)`（先按 `SELECT ... FROM` 之前的列清单区分是全列查询还是 `id + note_section` 这类窄查询）。同族已记：替身要按 SQL/params 区分同一张表的多次查询。
- **🔴🔴 判「某个章节号能不能当披露落点」的判据是「有没有子节」，不是「有没有表格」（2026-08-07 实测，用错判据会连误两次）**：listed 模板有 **48 个 `level=2 且 tables=0` 的节**，它们是**纯文字披露节**（会计政策章下的政策描述，带 `text_sections`），是合法落点 —— 现有落点 `五、72` 就是这种形态且已被 2 处引用。真正不能当落点的是**章标题容器**（listed 第十二章「股份支付」`level=1` / **6 个子节** / 0 表）：指过去会让底稿同步解析出零张表。⇒ 判据 = `child_count == 0`；按 `tables > 0` 写会把 `三、借款费用`/`三、债务重组` 这两个合法落点误拒。
- **🔴🔴 `section_code_index.json` 是 **POC 产物**（`version='poc-v1'`），不能当「章节全集」判据（2026-08-07 定性，一条长期红的真因）**：生成器 `build_section_code_index.py` 自述「仅扫描已打标的章节；未打标节输出到 stdout 供人工补录」；实测 listed 侧「三、」章收录 43 节但**缺**资产减值损失/营业外收入等 5 节、「十四、」段只收 4 节缺终止经营、soe 的 `八、9x` 段只到 `八、93`（缺 m-cycle 新建的 `八、94`）。它的**唯一运行时消费方**是 `note_word_exporter._load_section_code_index`，且缺失时 `return []` **fail-open**。⇒ `test_every_matrix_code_exists_in_index` 那条「矩阵 code 必在项目注释章」的断言 HEAD 侧本就红 6 项（memory 已记「归 spec B/C」），本轮改成**分级判据**：**强断言** = code 必在目标模板 `note_template_{listed,soe}.json`（真源，index 自身也是从它派生）；**弱断言** = code 若已被 index 收录则必须落在项目注释章（保留防 POC 错码 `五、12` 回潮），未收录/归别章的进 `INDEX_UNCOVERED_CODES` 登记表（12 条上限 + stale 检测 + 理由 ≥30 字）。→ **凡拿派生索引当判据前，先查它的 version 与生成器 docstring 是否声明「部分覆盖」**。
- **🔴 裁决表语义要随数据落地**翻转**，否则「补记完成」会把自己的守卫打红（2026-08-07）**：`LISTED_NULL_AUDIT` 原语义是「当前 null 的裁决」，配套断言「表里每条在 JSON 中确实是 null」。补记后 9 条变非 null ⇒ 三条断言同时红。正解不是删表（会丢台账），而是把语义改成「**历史 null 台账**」：`FALSE_NULL` 条目断言「已落地且落地值 == `target_section`」（比原断言更强，能抓「补错值」），`CROSS_GRAIN`/`TRUE_NULL` 仍断言「保持 null」，并加一条「未裁决集合 = 当前 null − 台账 ⇒ 必须为空」防漏判。
- **🔴🔴 改跨循环共享件时，把零回归做成**结构性保证**而不是靠回归测试碰运气（2026-08-07 `build_parent_check` 范式，可推广）**：需求是「族内 contra 子科目要按方向聚合」，但该函数被 D/H1~H10/I/K/L 共十几个 render 消费。写法不是「统一改成方向聚合」，而是 **`if 裸求和与父额不平: 试方向口径; if 方向口径能让勾稽成立: 才采用`** —— 于是「原本已平」的调用方**走不进新分支、输出逐字不变**，无需逐个回归即可断言零影响；再加一个 `convention` 字段把实际采用的口径下发出去，让同一响应内两种口径并存成为**活证据**（实测 H9 的 `gross` 走 `directional`、`unearned_finance` 走 `as_stored`）。守卫要专门加一条「方向口径不能让勾稽成立时必须回退原样求和」，并用变异（去掉该条件）证明它会打红。
- **🔴 按缩进截 Python 顶层函数体必须先用**圆括号配对**跳过参数列表（2026-08-07 又踩，与已记的「第一个 `{` 命中类型注解」同族）**：多行签名的 `) -> dict:` 那行缩进为 0，按「首个缩进 ≤ def 缩进的行即结束」会在签名处提前中断 ⇒ 截出来的"函数体"只有签名，`assert 'xxx' in body` 恒假红。正解 = 从 `def name(` 的左括号起做括号配对找到签名结尾，再从那里按缩进截。
- **🔴🔴🔴 `DisplayPrefs_Key` 的真源是 `components/workpaper/composables/displayPrefsKey.ts`，**不在** `stores/displayPrefs.ts`（2026-08-07 浏览器实测，5 处中招、每处都让整页白屏）**：store 只导出 `useDisplayPrefsStore`/`TableDensity`/`TABLE_DENSITIES`/`FixedColumnsConfig`。从 store 连带 import 该 key ⇒ 浏览器抛「does not provide an export named 'DisplayPrefs_Key'」+ 底稿页崩成「页面渲染出错」，而 **`get_diagnostics`(Volar) 零诊断 / vitest 全绿 / Vite transform 200** 三层全查不出（命名导出缺失是 **ESM 运行时**错误，Vite 只做单文件编译不解析跨模块导出集合）。实测中招：`d4/core/D4TabDisclosureSoe.vue`·`D4TabDisclosureListed.vue`·`f3-notes-payable/F3TabDisclosureListed.vue`·`F3TabDisclosureSOE.vue`·`custom/GtCustomGridSheet.vue`（横跨 D4/F3/custom 三循环 = 可复现的抄袭型缺陷）。已建平台守卫 `__tests__/displayPrefsKeyImportSource.spec.ts`（7 例，含「store 确实**不**导出该 key」正向断言 —— 哪天真加了导出也要打红提醒收敛）。与已记的「`fmtAmount` 是 store 成员不是模块级导出」同族。
- **🔴🔴 Vue 模板绑定**不存在的字段**渲染空串且不报错 —— 与「传不存在的 prop 静默失效」同族（2026-08-07 D4（4）表实测，一次连出两个 P0）**：①`{{ row.item }}` 而真源字段是 `label` ⇒ **9 个行标签全部消失**（主营业务/其中：在某一时点确认/…/合  计），表格只剩空可扩行提示文字；②`:class="{ 'font-bold': row.readonly }"` + `v-if="!isReadonly && !row.readonly"` 而真源无 `readonly` 字段 ⇒ 恒 `undefined`(falsy) ⇒ **小计/合计行既不加粗也没被禁用，用户可直接改写派生格把勾稽改坏**。四层验证全绿。**守卫范式**：从真源 `.ts` **动态抽**接口字段名（不写死清单，否则真源加字段时误判）+ 扫 SFC 里 `v-for` 块内所有 `row.xxx` 求差集；composable 额外派生下发的字段走 `DERIVED_FIELDS` 豁免，并配一条「该字段必须在 composable 里真被赋值」防豁免退化成空转。②的正解 = 真源加 `isSegmentRowReadonly(row)`（判据只看 `kind`）+ composable 派生下发（此前只做 `{ ...r }` 浅拷贝）。**P0-② 正是修完 P0-① 后新守卫立刻打红报出来的**。
- **🔴🔴 asyncpg 下 `WHERE item_id <> ALL(:keep)` 传 Python list **绑不成数组、谓词恒不命中**，而脚本照旧打印「已复原」= 假成功（2026-08-07 实测）**：`rowcount=0` 但目标行仍在。正解 = 显式展开具名参数 `NOT IN (:k0,:k1,:k2)`。→ **复原/清理脚本的成功判据必须是独立查询**（本轮是 postgres MCP 查出 `D3-det-rows` 仍在、cr=4 才发现），不能看脚本自己的输出；与已记的「`--apply` 被 Ctrl+C 中断但写入已提交，判成败查数据不看退出码」同族。
- **🔴🔴 Playwright MCP server 是**共享单实例**，协作者同时在用会把你的 tab 导走（2026-08-07 实测：`browser_tabs list` 只有 1 个 tab 却换了 project/wp UUID）**：故它**不能**用来做「另开浏览器避开协作者」。真正隔离用 **chrome-devtools 的 `isolatedContext`**（`new_page` 传该参数，cookie/sessionStorage 与协作者完全不共享）。**但 chrome-devtools 这条通道只能传纯字符串参数** —— `boolean`/`number`/`array` 会被序列化成字符串而报 schema 错 ⇒ 避开 `includeSnapshot`/`timeout`/`fullPage`/`fill_form`/`wait_for` 这类带非字符串参数的调用，改用 `evaluate_script` 自己轮询等待。另 `browser_run_code_unsafe` 的两条约束互相冲突（要 `await (async (page)=>{})(page);` 又拒尾分号）⇒ 该工具在本环境不可用。
- **🔴 el-table 把 header 与 body 拆成两个独立 `<table>`，而部分底稿表是原生 `<table>`（2026-08-07 实测）**：按「含某文字的 `<table>`」定位会落空、按 `.el-table` 容器定位又抓不到原生表。判表结构一律先 `document.querySelectorAll('table').length` 与 `.el-table` 计数**双查**，再按 `r.parentElement.tagName`（THEAD/TBODY）区分行归属；取两级表头要读 `colSpan`/`rowSpan`。
- **🔴🔴 「按名字找位置」判顺序/存在性时，**函数体内的局部 import 会冒充调用点**（2026-08-06 前后端各踩一次，两次都让核心变异静默逃逸）**：①前端 `body.indexOf('write_cells_to_xlsx')` vs `indexOf('refresh_custom_projection')` 判「xlsx 先于投影」→ 命中的是 `from ... import (refresh_custom_projection, write_cells_to_xlsx,)` 这行，而 import 清单按**字母序**把 refresh 排在前 ⇒ 假红「顺序反了」；②后端 `body.find('write_cells_to_xlsx')` 判「调用在 custom 门控之内」→ 把整个调用块删成 `pass` 后**仍然通过**（import 还在）⇒ 变异 GREEN。正解 = 一律匹配 **`name\s*\(`**（调用形态）并**另加一条 `pos >= 0` 的「必须真有调用」断言**。同族已记：`toContain('<Foo')` 被 `<FooREMOVED` 骗过 / 只断言标识符抓不住 `if False:`。
- **🔴🔴 固定字符窗口第 N 次踩：`/formulaCellSet[\s\S]{0,200}?props\.formulaCells/` 会**越过本函数尾部**命中紧随其后的 `formulaExpr()`（2026-08-06 变异 M3 实测 GREEN）** ⇒ 把 `formulaCellSet` 内部改成不读 prop 时守卫仍通过。正解 = 花括号配对精确截该常量自己的函数体（新增 `arrowBody(src, name)` helper，配「邻居函数内容不得被截进来」自检）。**凡「A 附近有 B」形态的判据都要改成「A 的函数体内有 B」**。
- **🔴 `propBody`（找 `key:` 后第一个 `{`）对**引用式**配置项会越界到后面的无关函数（2026-08-06）**：`onSwitchToHtml: refreshProjection,`（无花括号）会让它一路找到下一个函数的 `{`。正解 = 先用 `propValue` 取「到同层 `,` 或 `}` 为止」的值表达式，再按「标识符 → 找该具名函数体」/「内联箭头 → 截花括号体」两形态分流。
- **🔴 守卫禁某个键名时必须只盯「响应体取键」，不能笼统禁 `.xxx`（2026-08-06 自己打自己）**：为禁「把响应当 `formulas` 键读」写了 `not.toMatch(/\.formulas\b/)`，结果把**合法的** `apiPaths.workpapers.formulas(...)` 路径访问器打红。正解 = `\bres\s*\??\.\s*formulas\b` / `\bdata\s*\??\.\s*formulas\b` 精确到取值形态。
- **🔴 改用 `apiPaths` 后，按字面量 URL 写的旧守卫会把正确写法打红（2026-08-06 Wave 3↔Wave 4 自相撞）**：判据要同时认「字面量 URL」与「apiPaths 访问器」两形态，并**补一条交叉锁死**断言 `apiPaths` 里该访问器确实指向那个端点（否则出现「访问器名字对、URL 指到别处」的静默错误）。
- **🔴 `apiPaths/index.ts` 用**具名 re-export** 不是 `export *`（2026-08-06）**：新增 `export const X` 必须同步改 index.ts 的 3 处 import/export 清单，否则外部拿不到。低成本做法 = 把新端点加进**已被 re-export 的既有对象**（如 `workpapers`）。
- **🔴 变异脚本的锚点在同一文件里可能因**缩进相同**而重复（2026-08-06）**：`                    write_cells_to_xlsx(` 在 `save_formula` 与 `delete_formula` 里缩进一致 ⇒ hits=2 ANCHOR-MISS。正解 = 锚在**整个多行调用块**（含实参行）上；且变异必须**真正移除调用**（改成写空 dict 仍留着调用，源码级守卫抓不到 = 无效变异）。
- **🔴 vitest 的 `FAIL` 行会按控制台宽度折行，正则抓失败名必得 0 命中（2026-08-06 一次让 6/6 变异全部误判成 GREEN）**：变异检验一律 `--reporter=json --outputFile=<abs>`，从 JSON 的 `assertionResults[].status=='failed'` 收集。同族已记：PS `>` 重定向腌坏 UTF-8。
- **🔴 诊断脚本写盘一律用 `Path(__file__).resolve().parent / 'x.txt'` 绝对路径（2026-08-06 连踩 3 次）**：写相对路径时文件落在 CWD 而非脚本目录，`read_file` 按预期路径读会 ENOENT，白跑一轮。且 GBK 控制台 `print('🔴…')` 会 `UnicodeEncodeError`（含 emoji 的诊断一律写文件不 print）。


- **🔴🔴🔴 「返回 None 的原地修改函数」被写成 `return f(...)` = 每次调用都返 None，四层验证全绿（2026-08-07 母公司附注实测 P0）**：`_attach_parent_source_meta(table_data, ctx) -> None` 只原地改 dict，而 `_build_table_data` 的 legacy 路径写 `return self._attach_parent_source_meta({...}, parent_ctx)` ⇒ **每一张无 binding 的表返回 `None`**（整章表格凭空消失）；同函数不容忍 `ctx=None`，而非母公司章时 `parent_ctx` 就是 `None` ⇒ `AttributeError: 'NoneType' has no attribute 'get'` **全线崩**。`get_diagnostics` 零诊断 / vitest 全绿 / HEAD-swap 基线证明它**既不打红也不被任何既有测试抓到**（两侧失败集合逐条相同 152 项）。正解 = 原地修改函数也**返回 `table_data`** + 入口 `if not isinstance(table_data, dict) or not ctx: return table_data`。→ **凡把「原地修改 + 返回 None」的 helper 用在 `return` 位置，必须先看它返回什么**；且这类函数的 `ctx`/`extra` 形参要显式容忍 `None`（调用方在「不适用」分支传 None 是常态）。
- **🔴🔴 `ColumnDef.flat` 与 `group` 并存时 **group 被整体丢弃**，两级表头静默降级成单级（2026-08-07 实测，`_extract_column_groups` 源码级）**：`if any(d.get("flat") for d in defs): return []` —— `flat` 标在**任意一列**即对整表生效。实测并发会话给合并章「营业收入、营业成本按分解信息」（listed 五、62 表[3] / soe 八、64 表[3]）的**标签列**加了 `flat: True` 而其余 8 列带 `group` ⇒ 该表两级表头当场失效。→ 补列时「单级表标 flat」只能标在**确实单级**的表上；两级表的标签列**不得**标 flat（它不是数据列，rowspan=2 的独立列靠「不带 group」表达即可）。守卫应加「同表 flat 与 group 不得并存」判据。
- **🔴 上游只读源的缺陷用「登记 + 双向锁死」而非在下游自行纠正（2026-08-07 母公司同构子节范式）**：同构子节的列结构真源是合并章，母公司侧自行"纠正"会与合并章分叉 ⇒ 深相等判据永远报欠账、`--apply` 每轮报变更（幂等空操作永不成立）；而合并章是只读源不得反改。正解三件套 = ①`UPSTREAM_MERGED_COLUMN_CONFLICTS` 登记（含上游位置 + 依据）②豁免**只放行那一条**判据，其余不豁免，配「不传豁免时登记表也必须打红」+「未登记表的同类违规必须打红」双向自检 ③**stale 检测**：断言该缺陷在上游仍复现，上游修好后登记项即打红提醒移除 ⇒ 豁免不会变成永久盲区。
- **🔴 characterization 的判据形态要选「管道前后对照」而不是「冻结上游快照」（2026-08-07 Property 28 返工）**：合并章由别的 spec 持续在改，冻结快照会变成与本 spec 无因果的**假红发生器**。正解 = 内存里跑一遍完整 `apply_*` 管道，断言上游章节序列化后逐字节不变，并配「同一管道确实改动了本 spec 范围内的章节」反向自检防空转。→ 凡「X 不得被我改动」的零回归断言，都优先写成「跑我的管道前后 X 不变」。
- **🔴 守卫的裸子串判据会被**合法写法**命中（2026-08-07 实测，与「`toContain('<Foo')` 被 `<FooREMOVED` 骗过」同族但方向相反）**：`assert "in code" not in body`（意图禁「把章节号当字符串做子串搜」）被合法的**集合成员判定** `code in codes` 命中（`"code in codes"` 含子串 `"in code"`）⇒ 该断言对正确实现恒红、对错误实现也红 = **零信号**。正解 `re.search(r"\bin\s+code\b", body)`（`in codes` 因 `code` 后接词字符不成立），并配「对真用子串匹配的实现必红 + 不误伤集合成员判定」双向 fixture 自检。
- **🔴 `ast.parse` 不能直接解析「缩进的方法片段」（2026-08-07 踩）**：缩进 + 多行签名会 `SyntaxError: invalid syntax`。正解 = 对**整份文件**解析一次算出「字符串字面量占据的行号集合」，再按行号裁切某方法（`_func_span`/`_func_code` 范式）。同族：`inspect.getsource` 取模块级函数后要 `textwrap.dedent` 才能解析。
- **🔴🔴🔴 「投影/派生结构」在被写回之前必须先验坐标是否恒等，`extract_grid` **会重编行号**（2026-08-06 自定义底稿 spec 审查实测，差一步就写坏用户数据）**：`extract_grid_from_sheet` 里 `row_offset = data_start_row - 1` + `new_coord = f"{_col_letter(c)}{new_r}"` ⇒ 探针实测 xlsx **`B6`=123.45 投影成 `B2`**（列不变、只有行位移）。若照「投影键 == xlsx 键」把用户在网格里编辑的格写回 xlsx，会**写进表头区覆盖别的单元格**；且 `data_start_row` 是启发式（首个含「项目」/「序号」的行），用户录入过程中会**跳变** ⇒ 同一投影坐标在两次加载间指向不同 xlsx 行。**它对只读渲染是有意设计**（剥表头 + 裁空列 + 重编号，11 个既有调用方依赖），故正解是给「可写回」场景**另建恒等坐标投影**（不剥表头/不重编号/不裁空列），`extract_grid` 保持零改动。→ **凡把只读派生结构改成可写回的，第一步是拿替身数据跑「写 X 读 X」往返探针**，别信「键集恰好覆盖」这类静态比对。同族：`extract_grid` 的空/失败路径**只返 5 键**（无 `header_rows`/`column_meta`），按「键集 ⊇ 六键」写的守卫在 fail-open 路径必红。
- **🔴🔴 `WorkingPaper` 表**没有 `component_type` 列** —— componentType 是 render 期派生的，任何「按 componentType 门控写入」的端点都要另建判定真源（2026-08-06 自定义底稿实证）**：`custom` 由 `wp_render_config_helpers._maybe_custom_classifications` 合成（无模板归类 AND（有自定义程序实例 OR（`source_type==manual` AND 编号不像标准编号）））。已建真源 `app/services/custom_workpaper_context.py`（`resolve_is_custom` / `load_custom_context` / `READ_ONLY_FILE_STATUSES`）。**两条设计要点**：①**判不出时返 `False`（拒绝写入）不是 `True`** —— fail-closed 方向，宁可 409 也不能往标准底稿 xlsx 直写格；②**有意不 import `wp_render_config_helpers`**（它是并发 spec 的高频改动热点），改为直接复用更底层的 `app.services.acnr.grammar.is_standard_wp_code` + 一条 `ProcedureInstance` 计数查询，两者语义一致性由守卫锁死。**`ProcedureInstance` 在 `app/models/procedure_models.py` 不在 `workpaper_models.py`**（按后者 import 会 `ImportError`，而 `get_diagnostics` 查不出 —— 必须 `python -c "import 模块"` 实跑）。
- **🔴 后端新 router 的真实注册点是 `app/router_registry/workpaper.py` 的 `groups[...]`，不是 `app/main.py`（2026-08-06）**：`main.py` 全文无 `include_router(wp_*)`。**只 import 不加进分组 = 端点仍 404**（前端只见「保存失败」）→ 守卫要**双断言**（import 行 + 分组列表里出现）。判是否真注册：`from app.main import app` 后扫 `app.routes` 的 path。
- **🔴🔴 源码级守卫的「字符串存在」判据挡不住「把条件改成 `if False:`」（2026-08-06 变异检验抓出自己写的弱判据）**：`test_overflow_branch_exists` 初版断言「`MAX_CELL_UPDATES` 与 `overflow` 出现在函数体里」，把 `if len(updates) > MAX_CELL_UPDATES:` 改成 `if False:` 后**仍然通过**（常量与字面量都还在别处）⇒ 最核心的变异静默逃逸。正解 = 断言**条件形态**正则 `if\s+len\(\s*updates\s*\)\s*>\s*MAX_CELL_UPDATES\s*:`。同族已记：`toContain('a.b.length')` 抓不住删判断 / `toContain('<Foo')` 被 `<FooREMOVED` 骗过。→ **凡守卫断言「某个校验存在」，判据必须是条件表达式的形态而非其中出现的标识符**。
- **🔴 `extract_grid` 行偏移已用替身 xlsx 逐格复现（2026-08-06，可直接引用不必重测）**：xlsx `A1..A5/B5/B6=123.45/D10` → `extract_grid` 产出键集 **`['A1','B1','B2','D6']`**（`data_start_row=5` 因 A5 含「项目」⇒ 偏移 4，xlsx `B6`→投影 `B2`、`A5`→`A1`，且裁掉了 `A2..A4`）；恒等投影产出 `['A1'..'A5','B5','B6','D10']` 且 `header_rows=0`。fail-open 路径：恒等投影 6 键、`extract_grid` **5 键**（缺 `header_rows`）。
- **🔴 `GtGridSheet` 实际消费的 `htmlData.*` 键恰为六个**（`cells`/`max_row`/`max_col`/`col_widths`/`merged_cells`/`header_rows`），`column_meta` 只在类型声明里出现、不参与渲染分支；`hasData = Object.keys(cells).length > 0 && maxRow > 0`；`defineProps<...>(), { readonly: true }` 且全文 `emit(`/`defineEmits` 计数均 **0**（传 `readonly=false` 也不可编辑）。→ 后端若做「投影是否有内容」判定必须与该口径一致（已落 `grid_has_content`，守卫读 `.vue` 源码交叉锁死），两侧不一致会让存量补齐白跑（后端判有内容不再补、前端判无内容显示空态）。
- **🔴 `backend/scripts/diagnose/_wip_*` 诊断产物也会被并发会话清掉（2026-08-06 实测：`_wip_spec_trace_check.py` 中途消失而同目录另 32 个 `_wip*` 仍在）** → 反复要用的校验脚本不要只留一份在那里，关键结论要及时写回 spec/memory；`Test-Path` 返回 False 不等于自己没建过。
- **🔴🔴 spec 三件套的 `_Requirements:` / `**Validates:**` 交叉引用必须机器校验，可能整体错位到**另一套需求编号**（2026-08-06 实测，比个别笔误毒得多）**：`custom-workpaper-dual-mode-formula-and-batch` 的 requirements 有 **12** 个需求，而 design/tasks 的引用最大只到 **7/10** —— 两份文件是对着早期 7 需求版写的，且**同一个 `4.x` 在两边指不同需求**（design 的 4.4 指双模式、tasks 的 4.x 指公式）。`get_diagnostics` 对三件套只校验章节骨架与 `### Property N` 格式，**不校验引用是否存在** ⇒ 照 tasks 干活会做错需求。**校验脚本三行**：抽 requirements 的 `^### Requirement (\d+)` + 其下 `^(\d+)\.` 得 AC 全集，抽 design 的 `\*\*Validates: Requirements ([\d., ]+)` 与 tasks 的 `_Requirements: ([^_]+)_`，求「引用了但不存在」（悬挂）与「存在但无人引用」（漏覆盖）两个差集，两者都要为空。顺带校验 waves JSON 的 id 集合 ≡ 任务复选框 id 集合。**🔴 「未被引用的 AC」这一侧最容易漏查且必然发生**（2026-08-08 E 类实测：结构全对、悬挂 0，但仍有 3 条 AC 无人引用 —— 都是「保持不变 / 不得写死 / 必须由脚本落地」这类**约束型 AC**，写需求时容易忘了给它挂 Property 与任务）。正解 = 给这类 AC 补挂到既有 Property 的 Validates 里或新增一条 Property，不要为了让校验通过而删 AC。同时断言 **Property 编号无缺号**（`set(range(1,max+1)) - 实际` 为空）与**任务/waves id 无重复**。
- **🔴 同一能力常有**第二条路径**且带静默降级兜底，只改主路径 = 换一种方式失败（2026-08-06 导出实测）**：底稿导出有 `wp_xlsx_export.py`（缺 schema → **500**）与 `WpExportEngine._export_xlsx`（挂 `wp_export_import_router`，两个调用点）两条；后者写 `except (TemplateNotFoundError, Exception)` → **回退空白 workbook**，自定义底稿走这条路不报错而是**静默导出内容不全的文件**（比 500 更坏，用户拿去归档才发现）。→ 立 spec 说「某端点报 500」之前先 grep 该能力的全部入口，并逐个看 `except` 里是抛还是兜底。
- **🔴 往 `_XLSX_TYPES`/`_DOCX_TYPES` 这类分类集合加取值前先查有没有测试自带副本（2026-08-06）**：`test_pbt_export_format.py` 自带 `XLSX_TYPES` 清单并断言「每个已知类型映射到 xlsx 或 docx」⇒ 只改生产集合不同步副本，该 PBT 会红（同族 = 已记的「守卫的表名清单漏一张 = 假失败」）。


- **🔴🔴 根目录 `tmp_verify_*_out.txt` 这类**别人留下的探针输出是过期产物**，不能当实证（2026-08-06 实测，一次误判）**：`tmp_verify_engine_out.txt` 报 `formula_engine.py` len=60183 / `COLUMN_ALIASES` **15 键** / 有 `_resolve_tb_column`，而磁盘真相是 len=**58166** / **8 键** / 两处静默回退（L631·L936）仍在 —— 同一路径同一文件。⇒ Wave 2 的修复**曾落盘后被回退**（并发会话互相回退第 4 次实证）。**判据 = 探针输出里的 `file len` 与当下 `len(read_text())` 是否相等**；不等即整份输出作废。别人的 `tmp_*` 只能当「线索」不能当「判据」。
- **🔴🔴 `wp_template_files.py` 在 `backend/app/routers/` 不在 `backend/app/services/`（2026-08-06 实测，spec 三件套写错）**：按 `app/services/wp_template_files.py` 写的守卫/任务会 ENOENT → 表现为**文件级失败**（零断言执行）而非断言失败，极易当噪声跳过。同族已记：`prefill_formula_mapping.json` 在 `backend/data/` 不在 `backend/data/ledger_adapters/`。→ **spec 里出现的每个文件路径落地前必须 `file_search` 核一遍**。
- **🔴🔴🔴 列名映射有**三个**真源，改一个不够（2026-08-06 Wave 2 实测）**：①`formula_engine.COLUMN_ALIASES`（两条求值路径 `_handle_tb` L631 / `_execute_regex` L936 静默回退期末余额，48 格数字错）②`wp_formula_eval_service._COLUMN_MAP`（**第三真源，spec 未记**）把 `借方发生额→debit_amount` 映到 **`TrialBalance`**，而该表**没有** `debit_amount`/`credit_amount` 列（ORM 实测只有 `unadjusted_amount`/`rje_adjustment`/`aje_adjustment`/`audited_amount`/`opening_balance`）+ 取值处 `getattr(row, field, None)` **带默认值** ⇒ **静默返 0** = 看着已注册实则死映射，**24 个生产消费方**（D1~D7/H5~H10/I1~I6 全部 render）③`wp_grid`/各循环局部构造点。**发生额明细只在 `tb_balance`** → 一律走共享件 `four_table/occurrence_by_standard_code`（`fetch_occurrence_by_standard_code(db,pid,year)` **async** / `merge_occurrence_into_tb_data(tb_data,occ,*,as_float=False)` **同步就地改** / `DEBIT_KEY='本期借方'` `CREDIT_KEY='本期贷方'`）。**规范名必须是 `本期借方`/`本期贷方`**（守卫断言 `DEBIT_KEY ∈ set(COLUMN_ALIASES.values())`，写 `借方发生额` 必红）。
- **🔴🔴 `SUM_TB` 两条路径**取了 `col_name` 却丢弃**、写死 `data.get("期末余额")`（2026-08-06 实测，比 `TB` 的静默回退更彻底：连别名表都不查、trace 也不打印列名）**。影响面实测 **0 格**（预设里 `SUM_TB` 第二实参全是期末余额语义）⇒ **潜伏缺陷不是当期数字错**，但任何新增「`SUM_TB` + 发生额列」的预设会静默取错。
- **🔴 「取不到列」的返回值必须是 `Decimal` 不能是哨兵对象（2026-08-06 一次返工）**：`TB()` 结果要参与四则运算，哨兵会污染算术；且既有守卫按「**两种缺失态都返 0、靠 trace 文案区分**」这一契约断言。正解 = helper 恒返 `Decimal("0")` + 独立谓词 `is_unregistered_column(col)` 让调用方决定记 `errors`（配置错）还是只记 `trace`（数据缺）。**trace 文案是守卫判据**（须含「列无数据」/「列名未注册」），改文案前先看守卫。
- **🔴 新异常类必须插在兜底 `except Exception` **之前**，否则等于没加**：`_execute_ast` 的 `except Exception` 会把 `FormulaColumnError` 归成「AST 求值失败」⇒「列名拼错」与「解析崩溃」在 errors 里不可区分。且**抛一个未定义的异常名**会以 `NameError` 被同一兜底吞掉（本轮踩过：先写 `raise FormulaColumnError` 后才定义该类）。
- **🔴 `_execute_parallel` 会用 regex 结果覆盖 AST 结果并只记 warning** ⇒ 只改 AST 一条路径时，`FORMULA_PARSE_MODE=parallel` 下修复被完全掩盖。默认 `_PARSE_MODE='ast'` 故非生产路径，但**两条路径同时改**才使 parallel 也安全（regex 侧也记 error → `not ok` → 上层不写值）。
- **🔴🔴 立 spec 前必须查「该不变式是否已有守卫」，否则会造第二份判据（2026-08-06 `formula-management-runtime-closure` 实测）**：其 Task 6 计划新建 `test_formula_column_alias_registration.py`，而 `h-cycle-…` spec 的 Wave 1 Task 2 早已交付 **`backend/tests/test_formula_column_alias_coverage.py`**（12 例，已打红 48 格 + 2 处静默回退，2 变异全打红）覆盖同一不变式 ⇒ 两份判据并存 = 改一处另一处不红。**同一不变式择一实现，另一侧只许引用**。

- **🔴🔴 跨变体 row_code 有三类，「两侧异名」本身不构成禁止改写的理由（2026-08-06 `report_config` 四变体 1222 行实证，一次立项返工的根因）**：①**稳定码**（同码两侧 `row_name` 相同）⇒ **不需要**改写，改了才是 bug；②**同义两码**（同 `(report_type,row_name)` 两侧各挂不同码）⇒ **需要**改写，实测 **12 条**（`BS-111→BS-077` 优先股 / `BS-112→BS-078` 永续债 / `CFS-038→CFS-016` / `IS-055→IS-033` 起其他综合收益明细段**整段偏移 22 位**）；③**两侧异名**（同码在两侧是不同科目）实测 **78 条**（spec 立项只列 3 条）。🔴 第 ③ 类**不是**禁止理由 —— 12 条正确映射的 value **12/12 全部两侧异名**（码位偏移的必然结果，`soe BS-077`=▲应付手续费及佣金 / `listed BS-077`=其中：优先股，转换后读 listed 那套配置行故映射正确）。⇒ 「两清单互斥」若理解成「MAP ∌ 全部 78 个两侧异名码」**不可满足**；真不变量 = **MAP 的 key/value 都不得是稳定码**。立项初稿 `BS-013→BS-016`/`BS-053→BS-058`/`BS-043→BS-059` 错在 **key 是稳定码**（两侧同名本不需改写），而非目标码有两义；按它改写会把「一年内到期的非流动资产」指向「其中：应收股利」、把明细行指向**合计行**（listed `BS-059`=流动负债合计）。**生成判据天然排除这三条**（要求「同 `(report_type,row_name)` 两侧**各恰 1 码**」，而 `一年内到期的非流动资产` 在 listed 侧有 2 码 ⇒ 整个 row_name 被排除）= 结构性保证不靠人工排除。真源 `backend/app/services/note_conversion_row_codes.py` + 复算脚本 `diagnose_cross_variant_row_codes.py`。
- **🔴🔴🔴 `report_config` **无 `project_id` 列** = 纯模板表，故「切准则要改写项目级公式/row_code」这类需求多半不成立（2026-08-06 全库实证，推翻一条 spec 前提）**：它按 `applicable_standard` 分行，切 `project.template_type` 后自然读另一套配置行；报表数值在 `financial_report`，由全链重算重新生成。配套三条否证：①全库 `report_config.formula` 引用那 12 组跨变体 row_code 的行数 = **0**（`ROW()` 引用集只覆盖 `BS-002~BS-128`/CFS/CFSS/EQ/IMP/`IS-001~IS-030` 等主表行）②`wp_formula` 表 **0 行** ③**附注侧没有 row_code 级公式** —— `table_data` 里 446 条 binding 的 `binding_id` 形如 `五、11.分公司B.prior_year_value`（章节号 + 行标签 + 列键），`note_source_resolvers` 的 `ROW()` 参数是**单元格坐标**（`R2C1`）不是报表行码。⇒ 返回 0 时原因码必须区分 `no_mapping_needed`（已扫描确无对象）与 `not_implemented`（没做）。**排查同类需求先问三句**：这张表有 `project_id` 吗？公式真的引用了那批码吗？附注 `ROW()` 的参数是什么域？
- **🔴🔴 `disclosure_notes` **没有 `section_number` 列**（真实列名 `note_section`）也没有 `legacy_aliases` 列（2026-08-06 实证）**：而附注转换 spec 通篇写「改写 `section_id` + `section_number`」⇒ 照写必 `column does not exist`。别名只能落 `template_lineage` JSONB。**且改章节号有未登记的连带缺陷** —— `table_data` 里 **446 条** 公式 binding 的 `binding_id` **内嵌章节号**（`五、11.分公司B.prior_year_value`），改 `note_section` 会让这批绑定失联 ⇒ 任何「章节号改写」方案必须同时处置 binding_id 或明确排除。
- **🔴🔴 判 `variant_matrix` 的 null 是「真无落点」还是「落点在别名章」，精确标题匹配会误判一半（2026-08-06 实测，首轮 8 条判错）**：listed 侧 25 个 null / soe 侧 10 个 —— 精确匹配得「TRUE_NULL 15 条」，加关键词复核后 **8 条被推翻**：`实收资本`→listed `五、53 股本`、`股本`→soe `八、58 实收资本`（**两版用语互换**）、`外币折算`→`五、73 外币货币性项目`、`分部信息`→`十四、分部报告`、`合并现金流量表相关事项`→`五、71 现金流量表补充资料`、`其他综合收益`→soe `八、79 归属于母公司所有者的其他综合收益`、三条`一年内到期的X`→`五、43 一年内到期的非流动负债`（**明细项并入汇总章**）。**真 TRUE_NULL 只有 11 条**（listed 4：应收资金集中管理款/油气资产/非货币性资产交换 + soe 7：设定受益计划净资产/库存股/税金及附加/股东权益变动表项目注释 等），全部是「该准则确实不列报此项」的业务事实。→ 判据必须**精确匹配 + 关键词复核 + 别名对（用语互换）+ 明细→汇总章归并**四层，缺一层就会把「有落点」判成「不适用」，让底稿同步误报。真源 `note_variant_matrix_null_audit.py`。
- **🔴🔴 改**共享数据文件**前必须 grep 其他 active spec 是否也要改它，别只看 `git status`（2026-08-06 险踩）**：`note_template_variant_matrix.json` 被并发 spec `parent-company-note-chapter-and-sourcing` 的 Task 10（`[~]` 排队中）声明要改，且其需求写明「其余 100 个非母公司科目取值**不变**」—— 正是我要改的 35 条 null 所在 ⇒ 两侧同时动必互相回退（memory 已记 3 次实测）。**判据 = 在 `.kiro/specs/*/{requirements,design,tasks}.md` 里 grep 该文件名**；撞车时的正解 = **只落判据真源 + 守卫（不碰数据文件）**，把数据改写留到对方收口后跑幂等脚本，并在 tasks.md 里把该任务标 `[-]` + 写明阻塞原因（不要标 `[x]` 假绿，也不要硬改）。
- **🔴🔴 只读诊断脚本里多条查询共用一个 session，**一条失败会让后续全部假失败**（2026-08-06 实测，看起来像「全线崩」）**：`note_validation_results` 无 `status` 列（实际列名待查）→ 该条抛 `UndefinedColumnError` 后，同一 session 的后续 4 条查询全部报 `InFailedSQLTransactionError: current transaction is aborted`，报告里表现为「5 个判据全部 ERR」而其中 4 条其实压根没执行。→ 探针脚本每条查询要么 `try/except` 内 `await db.rollback()`，要么 `async with db.begin_nested()` 逐条隔离（范式已在 `gate_engine.evaluate` 里）。**判「是不是级联假失败」看报错文本是不是 `current transaction is aborted`**，那条一定不是真缺陷。
- **🔴 `backend/scripts/diagnose/` 下 `pathlib.Path(__file__).resolve().parents[2]` 已经是 `backend/` 不是仓库根（2026-08-06 一轮踩 3 次）**：再拼 `"backend"` 就得 `backend/backend/...` → `FileNotFoundError`。`DATA = parents[2] / "data"` 是对的、`OUT = parents[2] / "scripts" / ...` 是对的，写成 `parents[2] / "backend" / "scripts"` 就错。仓库根要用 `parents[3]`。**且诊断产物别放仓库根的 `tmp_*`** —— 并发会话会批量清掉（本轮脚本与输出被清空两次），改放 `backend/scripts/diagnose/_wip_*` 并在收口时自行删除。
- **🔴🔴 断言消息里出现 GBK 不可编码字符（`⇒` U+21D2 / `⊆` U+2286 / `−` U+2212 / emoji）会让 pytest 把**整条消息**转义成 `\uXXXX`（2026-08-06 H 类实测）**：现象是「同一个测试文件里有的失败消息中文正常、有的整段变 `\u4e14\u0031...`」，极易误判成编码配置问题。差别只在该条消息里**是否夹了一个**不可编码字符。**docstring/注释里的这些字符无害**（不进输出），只有 `pytest.fail(...)`/`assert ..., msg` 的消息体要换 ASCII（`=>` / `包含于` / `-`）。→ 写守卫时消息体一律只用 ASCII 符号 + 中文汉字。
- **🔴🔴 变异检验的 baseline 若本身就有红（Wave 1「先打红」范式必然如此），只看 exit code 判不出有效性（2026-08-06 H 类三轮实测）**：`rc` 恒为 1，三个变异全被判成「RED 有效」而其中一个其实是守卫缺陷。正解 = **按失败测试名集合做差集**（`new_fails = fails_after - fails_baseline`），并区分四态：`new_fails` 非空 = 守卫有效 / 空 = **守卫缺陷** / 该变异让某条基线红**转绿** = 证明它不是死断言（同样是有效信号）/ 锚点命中数 ≠ 1 = ANCHOR-MISS 脚本缺陷。**「转绿」这一态最容易漏** —— 它是验证「Wave 2 修完后守卫会转绿」的唯一手段。
- **🔴 「无效变异」在带实证的守卫上高频出现，判缺陷前先确认变异真的改变了判据（2026-08-06）**：把 `evidence` 四段拼接中的**一段**抽空 → 剩余段仍含数字且长度 >30 ⇒ 守卫不红是**正确**的，不是缺陷。要做决定性变异必须整段抽空。同族：只改外层判空 / 只改内层比较（JS `a < null` 恒 false）。
- **🔴 `dataclass` 里写在 `property` 分支中的收敛逻辑（如 `if alternate == primary: return (primary,)`）极易零覆盖（2026-08-06 变异抓出）**：真实数据里 `alternate != primary`，全部既有断言都走不到该分支 → 删掉它测试全绿。**凡 `property`/方法内有「退化情形」分支，必须用直接构造的替身对象专门断言一次**（真实常量覆盖不到）。
- **🔴 判「预设里某列名/科目码用了多少处」要数**公式格数**不是字符串出现次数（2026-08-06 自己踩）**：我按后者报「72 处」，实测受影响的公式格是 **48 个**（`本期借方` 19 / `本期贷方` 17 / `贷方发生额` 7 / `借方发生额` 5）—— 差额全在 `description` 文字里。汇报数字前先确认口径是 cells 还是 raw string hits。
- **🔴 `prefill_formula_mapping.json` 在 `backend/data/` 不在 `backend/data/ledger_adapters/`（2026-08-06 踩，探针 FileNotFoundError）**：后者是 `wp_render_schema` 所在目录。写探针前先 `file_search` 确认。
- **🔴 `formula_engine` 的静默回退有**两条**求值路径，只改一条不算修好（2026-08-06 H 类实测）**：`_handle_tb`（AST 路径，L631）+ `_execute_regex` 的 TB 分支（降级路径，L936），两处都是 `account_data.get(resolved_col, account_data.get("期末余额", Decimal("0")))`。守卫必须按「命中数 == 2」断言，并用「只改 AST 路径」做反向自检（此时应仍红）。
- **🔴 区间函数 `TB_SUM('a~b')` 的上界越界是隐蔽真缺陷（2026-08-06 H1 实测）**：`TB_SUM('1601~1604','期末余额')` 把 **`1604` 在建工程**（BS-029，H2 的科目）算进「固定资产合计」；同族 `1605` 工程物资 / `1606` 固定资产清理。固定资产族真实边界是 `1601~1603`。→ 凡区间预设都要核「上界是否跨到别的循环科目」，且守卫抽码时**区间端点要单独判越界**，不能只判「是否在 accounts 声明里」。


- **🔴🔴 变异检验必须比对「失败测试名集合」而非退出码，且要区分**无效变异**（2026-08-06 H 类 Wave 1 三次踩）**：①Wave 1 守卫**基线本身就是红的**（故意先打红），此时 `rc` 恒为 1 ⇒ 按 rc 判红绿必得「全部 GREEN=守卫缺陷」的假结论 → 正解 = 抓 `FAILED ...::(\w+)` 收**集合**，`new_fails = fails - baseline_fails` 非空才算 RED；想验「修好后转绿」则看 `resolved = baseline_fails - fails`。②**无效变异会伪装成守卫缺陷** —— 把 `evidence` 四段拼接中的**一段**抽空，剩余段仍含数字且长度 >30 ⇒ 守卫不红是**正确的**；只有整段抽空才是有效变异。判据 = 变异后被测属性是否真的越过了断言阈值，不是「改了字就该红」。③**收敛/去重分支要单独造用例**：`DualFamilyGroup.codes` 的 `alternate == self.primary` 去重分支，因所有真实分组都是 `alternate != primary`，删掉它**全部断言仍绿** → 必须显式构造 `primary == alternate` 的替身 + 断言 `len(codes)==1`（同族：`is_provision` 翻转、区间端点）。
- **🔴 从公式抽科目码必须区分「单码」与「区间端点」（2026-08-06 H 类实测，守卫首版假红）**：`TB_SUM('1601~1604','期末余额')` 抽出的 `1604` 是**区间上界**不是被引用科目 → 会把 `H1 分析程序H1-3`（声明 1601/1602/1603）误判成「引用了未声明的 1604」。正解 = 先匹配 `SUM_TB|TB_SUM\('(\d+)~(\d+)'` 把区间整体消费掉，再抽剩余单码；且守卫要配一条「区间端点不算引用」的反向自检。同族已登记：`_F2_INVENTORY_CODE_HI = "1499"` 常量。
- **🔴 `pytest.fail()` 的多行中文消息在 GBK 控制台会被转义成 `\uXXXX`（2026-08-06 实测）**：同一次运行里有的消息正常、有的全转义 —— 差别是**该消息是否经过 f-string 拼接了含非 ASCII 的变量**。判读失败原因时若看到 `\u3010Wave 1`，改从 `--tb=long` 或落盘文件读（`Out-File -Encoding utf8` 或让 pytest 自己 `--junitxml`），不要以为是守卫写坏了。
- **🔴🔴 `prefill_formula_mapping.json` 在 `backend/data/` 不在 `backend/data/ledger_adapters/`（2026-08-06 踩）**：后者是 render schema 的目录。路径写错时 `FileNotFoundError` 会让整个探针/守卫零断言执行（表现为「文件级失败」而非断言失败）→ 凡按路径读数据文件的守卫都要配一条「文件存在且条目数 ≥ N」的存在性自检。
- **🔴 `formula_engine` 有**两条求值路径**，静默回退要同时改（2026-08-06 实证）**：`_handle_tb`（AST 路径，L631）+ `_execute_regex`（旧 regex 降级路径，L936）**各有一份** `account_data.get(resolved_col, account_data.get("期末余额", 0))`。只改 AST 路径 → 降级路径仍静默回退期末余额，且守卫若只扫一处会判「已修好」。变异实测：只改一处时守卫必须仍红（已加断言）。
- **🔴🔴🔴 `disclosure_notes` **没有 `section_number` 列**，也没有 `legacy_aliases` 列（2026-08-06 实测全 38 列）**：章节号存 **`note_section`**（`八、1` / 也可能是截断的 `十、重要的资产负债表`），另有 `section_id`/`level`/`parent_section_id`/`sort_index`/`locked_number`/`template_lineage`。`section_number` 只是**模板 JSON 与 service 层的字段名**（`note_template_*.json` 的 `sections[].section_number` / `note_section_instances.section_number` / `wp_disclosure_sync_service` 的形参）。→ 凡 spec/设计文档写「改写 `disclosure_notes.section_number`」的一律要落到 `note_section`；「追加 `legacy_aliases`」只能落 `template_lineage` JSONB（除非新开迁移）。**实测 `section_id` 大面积为 NULL**（1030 章节里多数只有 `note_section`），故按 `section_id` 索引的映射逻辑对存量数据会大面积落空。
- **🔴🔴 附注公式的 `binding_id` 内嵌**章节号**（`五、11.分公司B.prior_year_value` / `八、9.其他应收款项.opening_balance`，实测 446 条 note 带 binding）→ 任何改写 `note_section` 的操作都会让这些 binding 静默失联**（未登记缺陷）。且 `note_source_resolvers`/`note_formula_derivation` 里的 `ROW('R2C1')` 参数是**单元格坐标**不是报表行码 —— 附注侧**不存在 row_code 级公式**，report_config 才是。→ 判「转换要不要改公式」先分清这两个 `ROW()` 域，别混为一谈。
- **🔴 `report_config` 是**纯模板表、无 `project_id` 列**（2026-08-06 实测 18 列）**：按 `applicable_standard`（`soe_standalone`/`soe_consolidated`/`listed_standalone`/`listed_consolidated`）分行，四变体合计 1222 行。⇒ 切 `project.template_type` 后天然读另一套行，**不需要**也**不可能**「按项目改写 report_config 的 row_code」。判「某表是不是项目级」先查有没有 `project_id` 列。
- **🔴🔴 「同义两码」与「一码两义」两张表**会交叉**，互斥断言写不出来（2026-08-06 `report_config` 四变体全量对账）**：同义两码 12 条的 **listed 侧目标码**（`BS-077`/`BS-078`/`CFS-016`/`IS-033`~`IS-048` 等）**同时是一码两义码**（同一码在 soe 侧是另一科目）⇒ 「把 soe 的 `IS-055` 改写成 `IS-033`」在 soe 语境里正好指向「以摊余成本计量的金融资产终止确认收益」。**一码两义实测 78 条不是 3 条**（`IS-025`~`IS-055`/`CFS-012`~`CFS-039`/`EQ-018`~`EQ-030` 几乎整段错位，两准则的利润表/现流表/权益表行序完全不同）。→ 跨变体 row_code 映射**必须同时给出方向与语境**（`(source_standard, code) → (target_standard, code)` 四元组），单向 `code→code` 的映射表在这里是不成立的。
- **🔴 附注模板源 docx 的 Heading 层级两版完全不同**（2026-08-06 实测）：listed 是 `Heading 1`=章 / `Heading 2`=节；**soe 是 `Heading 1`=章 / `Heading 3`=节 / `Heading 4`=子节 / 局部到 `Heading 5`**（第四章会计政策、第八章项目注释都跳过 Heading 2）。→ 按 `Heading 2` 抽节在 soe 上会**只拿到会计政策变更等少数几节**、漏掉全部科目节。另 **listed 母公司章标题是「公司财务报表主要项目注释」（无「母」字）** ⇒ 禁止匹配对必须同时含「母公司财务报表主要项目注释」（JSON 现值）与「公司财务报表主要项目注释」（docx 原文）两种写法。soe 母公司章 = `Heading 1` 的「母公司财务报表的主要项目附注」（**确认国企源 docx 14 个 Heading 1 里没有「股份支付」章**，股份支付在 soe 是第八章下的 `Heading 3`）。
- **🔴 源 docx 实测的 5 对章节别名（Task 4 的 evidence，逐字）**：`财务报表编制基础`↔`财务报表**的**编制基础` / `递延所得税资产**和**递延所得税负债`↔`递延所得税资产**与**递延所得税负债` / `所有权**和**使用权受到限制的资产`↔`所有权**或**使用权受到限制的资产` / `营业收入**、**营业成本`↔`营业收入**和**营业成本` / `**研究**开发支出`↔`研发支出`（listed 侧「研发支出」既是 `Heading 2` 会计政策节也是 `Heading 1` 独立章 ⇒ 别名匹配要限定在同章层级内，否则会把会计政策节配到独立章）。
- **🔴🔴🔴 `is_replied` 布尔/字符串双形态 —— 裸真值判断把「明确未回函」当成「已回函」（2026-08-05 F0 Task 20.2 实测，七枢纽共享，已修）**：两种持久化形态都是真实历史数据 —— 完整表格视图 `ConfirmationFullGrid` 按 `confirmationColumnSpec` 的 `kind:'bool'` 渲染 checkbox 写**布尔**；明细面板与 Excel 导入按源模板 X0-1 数据有效性 `是,否` 写**字符串**。由此三类错法并存：①`row.is_replied === '否'`（`ConfirmationDetail` ×2）对布尔 `false` 恒不成立 ⇒ 「消极式未回函→视同相符」「积极式未回函→需替代程序」两条派生提示**从未渲染过** ②`r.is_replied === false`（`defaultUnrepliedFilter` + `alternativeG06`/`alternativeH05` 两份内联副本）对 `'否'` 恒不成立 ⇒ **明细面板录入的未回函行永远进不了 F0-5/F0-6「从 X0-1 带入」** ③**`if (row.is_replied)` 裸真值最毒** —— JS 里 `'否'` 是 **truthy** ⇒ 显式未回函的行被计成**已回函**，波及 `useConfirmationData` 的 `replied_count`/`coverageMetrics`、`GtConfirmationSummary` 覆盖率、`fraudRisk` 回函率（<50% 触发舞弊迹象，方向正好反了）、`useD01DiffImport` 的 D0-4 差异导入过滤。正解 = 单一真源 `confirmation/replyStatus.ts`（`normalizeReplyFlag` 三态 / `isRepliedTrue` 计数用 / `isNotReplied` **未填返 false** 防空行被带进替代程序 / `shouldShowReplyBlock` 兼容「只填相符情况未填是否回函」的既有数据）；**读时归一不迁移已存值**（数据零丢失）。
- **🔴🔴 `match_status` 被 gate 在「已回函」块内 = 分类错误导致死锁（2026-08-05 实测，同批修）**：`ConfirmationDetail.vue` 把「相符情况」放进 `v-show="row.is_replied"` 的回函信息块，而该面板**完全没有 `is_replied` 录入控件**（全仓 `emitUpdate('is_replied'` 0 命中）⇒ 新建行 `undefined` → 块 `display:none`（实测 w=0,h=0）⇒ 既设不了 `match_status='未回函'` 也设不了 `is_replied=false` ⇒ 两个未回函判据都不成立。**`match_status` 是三态且「未回函」恰在没有回函时才有意义** → 必须移到常显区。→ **判「某字段能否录入」要 grep 它的 `emitUpdate`/`v-model` 写入口，不能只看类型声明里有这个字段**；`v-show` 里的 gate 字段自身若无录入口即死锁。
- **🔴 用 `evaluate_script` 遍历/点击页面元素探测结构会误触组件（2026-08-05 实测丢数据两次）**：探测折叠块可见性时误触 `GtIndexChip` 跳转 → 页面导航到 F0-5、**3 行未保存数据全部丢失**；点视图切换 radio 报 `did not become interactive within timeout` 但已触发组件重载，行又被丢弃。→ 实测一律用 chrome-devtools 的 `take_snapshot`/`click`/`fill`（真实交互），**禁用 JS 遍历 DOM 探测**；函证行**离开 sheet 即丢弃未保存内容**，切视图/切 sheet 前必须先点「保存」。
- **✅ memory 旧记「完整表格视图编辑永不落库（七循环 P0，未修）」已过期（2026-08-05 源码核实）**：并发会话已修 —— `GtConfirmationSummary.handleGridUpdate` 现为 `data.updateField(...)` + `markDirty()`，工具栏有统一「保存/未保存」按钮（tooltip 明写两个视图的编辑都只在内存、必须点保存才落库）。用户裁决是**补显式保存按钮不做自动保存** ⇒ 所有改内存的入口都要 `markDirty()`。
- **🔴🔴 「同一语义在共享组件与专属下区组件各有一个录入口」= 双真源，正解是在共享组件里用 `v-if="!isX"` 关掉而不是开 `isX` 分支（2026-08-05 L0 定论，反直觉易被下个会话「修正」）**：L0 的「二、样本选择」6 项属 `L0-1` 下区（源 `J28` 段，落 `L0-1-lower-sample-*`），已由 `L0SummaryLowerZone.vue` 承载；而 G0 的同名 6 项走共享 `ConfirmationSampling.vue`（落 `SamplingData` 字段）。故共享组件里 L0 的正确形态是 `<el-collapse-item v-if="!isL0">`、**`ConfirmationSampling.vue` 里 `isL0` 计数为 0 是正确状态**。→ 判「某枢纽是不是漏接门控」不能只 grep `isX` 计数，要先确认该语义的**唯一承载位置**在哪；两处都渲染 = 审计师在两个地方填同一件事、互相看不到。
- **🔴 复合键 skip（`{wp_code}-{sheet_name}`）已落地在 `wp_render_config.py`，接在既有三条之后（2026-08-05 L0，实证有效）**：判定顺序 = ①完整 sheet_name ②尾码 `_SHEET_CODE_RE` ③首码 `^[A-Z]\d+(-\d+)*` ④**复合键**。用于「同一 sheet 名在不同循环可见性不同」—— `函证差异检查表（示例）` 在 L0 是 hidden、在 D0/F0 是 visible ⇒ 只能 `L0-函证差异检查表（示例）` → `skip`，**裸键 `函证差异检查表（示例）` → `confirmation-diff-checklist` 必须保留**（它是 D0/F0 的 componentType 来源）。实测 L0 visible=9 / D0=11 / F0=11，三者与源 xlsx `sheet_state` 逐一相符。**🔴 但 `_real_sheets`（判 `_is_multi_sheet` 的那段列表推导）仍只用裸键 `_WP_CODE_OVERRIDE.get(c.sheet_name)`，没跟进复合键** → 对「复合键 skip 后恰好只剩 1 张可见 sheet」的底稿会把 `_is_multi_sheet` 算错（L0 有 9 张故当前无影响，属潜伏）。
- **🔴🔴 `VARIANT_COLUMN_DEFS` 曾有重复键 `l0_row_conclusion`（2026-08-05 变异检验顺带挖出并修掉，平台级共享件）**：同一对象字面量里定义两次（内容相同），JS 静默取后者 ⇒ `get_diagnostics` / vitest / Vite transform **四层全绿**。发现路径不是守卫而是**变异脚本报「锚点命中 2 处」** —— 变异脚本的 ANCHOR-MISS/多命中本身就是一种缺陷信号，别只当脚本问题跳过。已删前一条并加守卫「注册表顶层键无重复」。同族 = 已记的「AST 重复 dict 键守卫」「H1 payload 两个 `tb_source_codes` 键」。→ **凡按名注册的大对象（列 def / componentType / prompt 表）都要配一条键唯一性断言**。
- **🔴 变异检验脚本的锚点必须**行级唯一**，多命中与零命中都要显式报错而非静默跳过（2026-08-05 三次踩）**：①含 `\n` 的跨行锚点在 CRLF 工作树必 MISS（memory 已记，本轮自己又踩）②`v-if="isL0"` 在注释里也出现 → 命中 2 处 ③`confirmation_method: '函证类型…'` 在 G0/H0/L0 三个 block 各有一份 → 命中 3 处，锚点需带 cycle 上下文（按 `X0:` 块起点切片后再定位）。正解 = 按**标签/常量声明行号**定位再取其后紧邻行，并断言 `hits == 1`。
- **🔴 「固定字符窗口」这个坑在**前端守卫**同样成立（2026-08-05 两次）**：①取标签开标签用 `slice(i, i+400)` 而该块约 430 字符 → `indexOf('>')` 返 -1 → 空串 → 断言假红 ②`SOURCE_TEMPLATE_TYPOS` 的 1500 字符窗口把紧随其后的 `CORRECT_INDEX_REFS` 一起吞进来 → `not.toContain('S33')` 必红。正解 = **按配对边界精确取常量体**（新增 `pyListBody` 按 ASCII 方括号配对），禁固定窗口。
- **🔴 交叉锁死前必须先确认对侧常量的**存储形态**（2026-08-05 一次踩出 4 条假红）**：`CONFIRMATION_SOURCE_MANIFEST.L0` 是**英文 key 清单（33 条）**，`CONFIRMATION_SOURCE_COLUMN_LABELS.L0` 才是**中文 label 清单（28 条）**；`COLUMNS_ABSENT_IN_SOURCE` 存**英文 key** 不是中文 label。拿 label 清单去比 key 集合 → 断言必红且看起来像生产代码有问题。→ 写交叉锁死断言前先落一个探针把对侧常量**原样打印**出来。
- **🔴🔴🔴 pytest 一律从**仓库根**跑，从 `backend/` 跑会让 16 个用相对路径的测试假红（2026-08-05 实测）**：`tests/four_table/` 从 `backend/` 跑 = **17 failed**，从仓库根跑 = **1458 passed / 0 failed**。假红形态 = `FileNotFoundError: 'backend/wp_templates/G/G7 …xlsx'` / `'backend\app\routers\wp_render_strategies\_k3_other_payables.py'`（路径被拼成 `backend/backend/...`），极易误判成回归。判「某批失败是否 CWD 依赖」最快判据 = **换 CWD 再跑一次，失败集合归零即是**。
- **🔴🔴 变异脚本的备份必须落**磁盘 `.bak`**，只在内存会因中断留下变异残留（2026-08-05 实测，代价是丢了一行门控）**：第一次变异脚本被 Ctrl+C 中断 → `finally` 未执行完 → `wp_render_config_helpers.py` 的 `startswith("L0")` 门控行被删且留在文件里；第二次变异脚本启动时把它当成原文基线（`orig[H]`），于是「写回校验 True」而门控实际已丢，`test_gate_before_fetch` 报 `ValueError: substring not found`。同族 = 已记的「`--apply` 被 Ctrl+C 中断但写入已提交」。→ ①备份写 `.bak` + 提供 `--restore` ②**共享热点文件（`wp_render_config_helpers.py` / `confirmationColumnSpec.ts` / 两个 JSON 数据文件）的判据改用「替身字符串」在测试内验证，不做磁盘变异**（范式 = `test_l0_book_amounts.TestInjectorGuardSelfCheck`：GOOD / LATE_GATE / NO_GATE 三个替身 + 同一判据施加于真实源码做交叉验证）。
- **🔴🔴🔴 变异检验有**四态**不是三态，漏掉「WRONG-TEST」会把守卫缺陷判成有效（2026-08-09 I 类 Task 9 实测，本轮最贵一条）**：M3/M4/M5 三条变异都报 RED、但**新增失败测试名全是同一个**（`test_no_stale_sheet_label_whitelist`）—— 因为 M1 的还原逻辑没进 `finally`，后三条都在读被污染的文件。只按「有没有新增失败」判会得出「全部有效」的假结论。⇒ 变异脚本必须为每条变异**声明期望打红的测试名**并断言 `want_test in added`，四态分别为 **RED（打红且是预期那条）/ WRONG-TEST（打红了但不是预期的 ⇒ 污染残留或锚点错行）/ GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）**；且「三条变异报同一个失败名」本身就是污染信号。**配套两条**：①失败名正则要取 nodeid **最后一段**（`FAILED [^:]+::([\w\[\]-]+)` 对类内测试 `file.py::TestX::test_y` 只捕到 `TestX`，全部类内 Property 守卫因此不可见）②输出文件名接受 `sys.argv[1]`（复用同名文件会读到上一轮日志，把有效变异误判成 ANCHOR-MISS）。
- **🔴🔴 变异必须让**被测属性**变坏，改守卫自己的断言是无效变异（2026-08-09 实测）**：M3 首版写「删掉守卫里的 md5 断言」= 把守卫改弱 ⇒ 只会更绿，永远测不出 Property 10 有效性。正解 = 破坏**被测脚本**的幂等性（往 `apply_fixes` 里塞一条无条件写入）。判据 = 变异的目标文件应当是**生产代码/数据**，改守卫文件的变异只在验证「stale 检测」这类以守卫自身状态为被测对象的 Property 时才合法。
- **🔴 锚点在同一文件多处**合法**复现时要用行号消歧，但仍须校验该行确实含锚点（2026-08-09 I 类 `TB('6604')` 三处命中）**：`line_hint` 只做消歧、不替代锚点校验 —— 否则行号漂移后会静默变异到错行并产出 WRONG-TEST。
- **🔴🔴 声明表守卫必须**单独逐字断言持久化键**，「长度 + 展示字段」三条断言全绿也拦不住键漂移（2026-08-05 变异检验抓出）**：把 `sample-6` 改名成 `sampleX` 时，`toHaveLength(6)` / `label` 数组 / `source_ref` 数组**全部通过** —— 而 `field` 是持久化键，漂移 = 既有项目已录入内容读不回来（数据零丢失红线）。→ `label`/`source_ref` 是展示与溯源，`field`/`key` 是**数据契约**，二者漂移后果完全不同，必须各有一条 `toEqual` 逐字断言。
- **🔴🔴 `ProcedureInstance` **没有 `is_mandatory` 列** ⇒ 裁剪页 `decide()` 里的 `if (p.is_mandatory) return null` 从上线起是**死判据**（恒 undefined→falsy，从不保护任何程序）（2026-08-09 实证 16 列全量）**：`is_mandatory` 只在 **`WorkpaperProcedure`**（`wp_optimization_models.py`，底稿内程序行，另一张表另一套主键）上，实例层无从 JOIN。⇒ ①「强制程序不得裁剪」这条需求在 `procedure_instances` 域**结构上不可实现**，只能如实传 `false` + 登记已知限制，禁在 `_to_dict` 里凭空补该键（列不存在，补了就是伪造）②真正生效的保留判据是 A/S 循环 / 执行进度 / 已手工理由 / 底稿已录入 / 风险保护五条 ③前端 `useProcedures.ts`(1)/`ProcedureTrimming.vue`(2)/`ProcedurePanel.vue`(4) 共 7 处读 `is_mandatory` 全是死读。→ **判「某保护判据是否真生效」必须查该列在被查询的那张表上存不存在**，别按字段名在别的模型里出现就当有。
- **🔴 `procedure_table_templates.json` 的 `tables` item 字段名是 `content` 不是 `description`，且**无 `hint` 透传通道**（2026-08-05 实证）**：`ProcedureTableService.get_procedure_table` 以 `item["content"]` **必填**读取（写 `description` 会 KeyError），输出字段恒为 `{_key, seq, content, ref_index, phase, category, **merged}` → 新增 `hint` 字段会被**静默丢弃**（又一个 dead config）。源模板 G 列批注只能承载在 `content` 末尾的 `\n【提示】…`。`program_category` 走 `item.get("category") or item.get("program_category")`。
- **🔴 `PLACEHOLDER` 白名单的**第 4 处**在 `test_k_cycle_formula_presets.py`，且根因是双真源（2026-08-05 修）**：模块级有 `_PREFILL_ONLY_FUNCS`，`test_formula_syntax_valid` **函数内又硬编码一份 `known_funcs`** → 补模块级常量不生效、必须两处都改。已改为 `known_funcs = {"TB"} | _PREFILL_ONLY_FUNCS` 消除双真源。前三处见既有记载；另 `test_l_prefill_extension.py` 的白名单虽无 `PLACEHOLDER` 但**按 7 张特定 sheet 过滤、不扫 L0**，是真绿。
- **🔴 幂等脚本的控制台输出禁用 emoji（`✅`/`❌`），崩点在**写盘之后**（2026-08-05 实测）**：Windows GBK 控制台 `print('✅ …')` 抛 `UnicodeEncodeError` → 退出码非零**但改动已落盘**，极易误判成「apply 失败」（同族 = `migration_runner` 那条）。改用 `[OK]`/`[ERR]` ASCII 标记；`description` 里的 🔴 进 JSON 不进控制台可保留。判 apply 成败一律查数据不看退出码。
- **🔴 「读源码型守卫必须先 `stripComments()`」对**核验脚本**同样适用（2026-08-05 自己踩）**：核实「K0 白名单已移出 L0」时用裸 `'("L0", "审定表L0-1")' not in src`，而移出时**保留了原字面作留证注释**（`# ("L0", "审定表L0-1") 已于…`）→ 误报「被并发会话回退」。正解 = 剥注释后判定 + 另加一条「留证注释仍在」的正向断言（防将来被静默删掉）。
- **🔴 `asyncpg` 不能推断裸参数类型，`WHERE (:pid IS NULL OR ...)` 必炸（2026-08-05 实证）**：报 `AmbiguousParameterError: could not determine data type of parameter $1`。正解 = **Python 侧分支构造两条 SQL**，参数一律显式 `CAST(:pid AS uuid)`。同族 = 已记的「`sa.table()` 裸 `sa.column()` 让 UUID 比较报 `operator does not exist: uuid = character varying`」。
- **🔴🔴 「点号码」与「横杠码」是两套体系且**语义可能完全不同**，跨表比对必须先归一（2026-08-05 D 类实证，比已记的「一码两义」更毒）**：`account_chart` 里 client 侧 **`1231.05` = 坏账准备_长期应收款**，standard 侧 **`1231-05` = 坏账准备-合同资产** —— 同一「05」子号在两套体系下是**不同科目**。且 `trial_balance.standard_account_code` 用**横杠**，`tb_balance.account_code` 用**点号**。由此产生两类活缺陷：①**`report_config` 的 `IMP-002 其中：应收账款坏账准备 = TB('1231.02','期末余额')` 用点号** → `TB()` 读的是 `trial_balance`（横杠体系）⇒ **该行取数恒空**（同表 `BS-006` 用的是 `1231-02` 横杠，自相矛盾）②`account_mapping` 有一条 `auto_fuzzy` 错映射 **`1231.05 坏账准备_长期应收款 → 1231-02`（2 项目）** ⇒ 任何按 `1231-02` 反解取 D2 备抵的路径都会把长期应收款坏账算进应收账款 → 反解结果必须再叠**名称过滤**（同 F1 的 `use_provision_name_filter` 范式）。→ 凡写「标准码 ↔ 客户原始码」的取数一律经 `account_mapping` 反解，禁在两种写法间手工替换分隔符。
- **🔴🔴 「一名多码」在负债/损益侧同样存在，`account_mapping` 反解是唯一通路（2026-08-05 D 类实证）**：**合同负债 client 侧是 `2204`**（1 项目）而 standard 侧 `2205`（6 项目）· `6051 其他业务收入 ← 6002`（1 项目）· `6402 ← 6404`（1 项目）。硬编码标准码前缀在这些项目**必取空且无报错**；而 `account_mapping` 里 `2205 ← 2204` 的 `auto_exact` 行早已存在 ⇒ 走「报表行公式解析标准码 → 反解客户原始码 → 前缀匹配 `tb_balance`」即可命中。**判「某循环取数恒空是数据事实还是接线缺陷」的三步**：① `account_chart` 按**名字**查（名字都没有 ⇒ 业务事实，如「应收款项融资」全库 0 命中）② `account_mapping` 查该标准码有没有反解行（有 ⇒ 接线缺陷）③ `tb_balance` 查反解出的原始码有没有数据行。
- **🔴 `tb_balance.closing_balance` 可以是 NULL 而不是 0（2026-08-05 实测 5 处：`1121.03 信用证`/`1122.02 暂估应收款`/`1122.12 暂扣质保金`/`1231.05`/`2203.02`）**：`sum()` 遇 NULL 会让**整列聚合变 NULL**（不是当 0 跳过），下游 `Number(null)===0` 又把它变成假 0 → 「余额为 0」与「未填报」不可区分。聚合一律 `COALESCE(closing_balance,0)`，判「有无数据」另用 `IS NOT NULL` 计数。同族：`1122.11 应收账款_收款通` 期末 **−114,209,110.16**（贷方性质叶子）⇒ D2 叶子聚合必须带符号，套 `abs()` 会让合计偏 2.28 亿。
- **🔴🔴🔴 孤儿扫描禁用「符号级匹配」，唯一可靠判据是 import 路径（2026-08-04 实测，守卫连续三次假阴性）**：`moduleHasConsumer` 若按「导出符号名在别处出现」判有消费方，会把**真孤儿判成有消费方**（假阴性＝漏判，比误报更坏），三种成因逐个踩到：①**注释里提到符号名**（`blockColumnConfigs.ts` 文件头写着「`blockColumnAmountRegistry.ts` 的 `NON_AMOUNT_NUMBER_COLUMNS` 里登记理由」）→ 必须 `stripComments`；②**平台有意的多副本各自 `export const` 同名符号**（`CONVERGENCE_TARGET` 在 4 个文件各声明一份，是已登记的收敛锚点范式；`E1RestrictedRowLike` 在 `e1NoteSectionMap.ts` 独立 `export interface` 一份）→ 「同名」不是「引用」；③**通用类型名撞车且救不回来** —— `BlockKey` 由 `useB22CDesignEffectiveness.ts` 导出，消费它的 `.vue` **只 import 不 export**，故「跳过自行导出者」规则对它无效。→ TS/Vue 里消费一个模块**只能**经 import，符号匹配既多余又有害，判据收敛为 `import '.../{stem}'` 路径正则单条。
- **🔴🔴 平台 40+ 处宿主注释写「`openReviewDialog` 由 Runtime Boundary(`GtWpRenderer`) 统一 provide」，而 `GtWpRenderer.vue` 全文（40512 字符）不含 `ReviewDialog` 字样（2026-08-04 实证）**：真链是 `useWorkpaperScaffold` → `useWorkpaperReviewProvide` → `useReviewDialogProvider.provide('openReviewDialog')`。→ **按注释写守卫会直接打红**（我首版就中招）；判 provide/inject 链一律 grep `provide\('键名'` 找真源，不信注释。`g0OrphanClosure.spec.ts` 已加反向自检：`GtWpRenderer` 哪天真 provide 了就打红，提醒同步修那批注释。
- **🔴🔴 合成 `focus` 事件驱动 `WpAmountInput` 会得出「输了变成 0.00」的假缺陷（2026-08-04 实测）**：`dispatchEvent(new Event('focus'))` **不触发** el-input 的 `@focus` → 组件内 `focused` 恒 false → `display` computed 回退 `amountFormatter(0)` 并把 DOM 值覆盖成 `0.00`，看起来像千分符功能坏了。正解 = 用 chrome-devtools 的 `fill`/`fill_form`（真实交互）。**纯 `el-input` 用合成 `input` 事件仍有效**，坏的只是「依赖 focus/blur 状态机」的控件 → 判金额控件行为必须真实交互。
- **🟡 判「区块内某列是金额还是数量」可直接读 a11y 树（2026-08-04 实测手法）**：`WpAmountInput` 在快照里是 `textbox`（底层 `el-input`），`el-input-number`/`type=number` 是 `spinbutton` → 一次 `take_snapshot` 即可逐列判定，比逐个 evaluate 查 DOM 快且不受滚动/虚拟列表影响。
- **🔴🔴 变异检验脚本必须把还原放进 `finally`，否则一处断言失败就把假条目留在真源里（2026-08-04 实测）**：我在一个脚本里连做 3 个变异，变异 C 的锚点未命中抛 `AssertionError` → 变异 A 注入基线的假条目 `owner: 'mutation-probe'` **留在了 `orphanHostBaseline.ts` 里**，而守卫此时反而是绿的（假条目本身合法）。→ 规矩：①一个脚本只做一个变异 ②`try/finally` 无条件写回原文 ③做完立刻用**独立探针**核验残留。**核验探针也不能用朴素 `includes`** —— 我查 `CrossWorkpaperNav` 残留时命中的是注释与另一条 reason 文字里的同名字样，误报「仍在基线里」（正是这条 spec 自己在治的坑）→ 判「某条目是否在数组里」要解析 `file: '...'` 字段，不要全文搜名字。
- **🟡 `alternativeBlockManifest.ts`（七枢纽替代程序区块契约真源）是「有意只被守卫消费」的合法孤儿（2026-08-04 登记）**：它的全部消费方都在 `__tests__`（`alternativeBlockManifestContract.spec.ts` / `alternativeH05SourceFidelity.spec.ts`），零生产消费方 —— 但它是**判据真源**（各 `blockColumnConfigs*` 的区块 title/sumField 与它双向锁死），删掉会连带删掉守卫保护 → 登记豁免而非删除。**判「孤儿该删还是该接还是该豁免」的第三条分支**：既有真源类（manifest/registry/枚举清单）若被守卫双向锁死，属合法豁免。
- **🔴 函证域孤儿实测数（2026-08-04，推翻立项假设 0 组件 / 3 模块）**：`confirmation/**` ∪ `g0-confirmation/**` 实有 **2 个零渲染宿主组件**（`e0-send-list/SendListConsistencyPanel.vue` · `E0SummaryLowerZone.vue`）+ **22 个零生产消费方模块**（6 个 `*Enums.ts` / 5 个 `composables/useConfirmation*.ts`·`useE0BookAmounts`·`useEntitySuggestion` / `useK0ImportExport`·`useL0ImportExport` / `sendListScopeChecks`·`sendListE05Checks` / `confirmationColumnSourceManifest`（只有测试消费方）/ `confirmationLinkageMatrix`·`migrateDformToConfirmation`·`e0RestrictedToE1`·`k0LowerZoneSpec`·`useD01Linkage`·`blockColumnAmountRegistry`）。**「只被 `__tests__` 引用」= 守卫在保护死代码，仍判孤儿**。
- **🔴 按数组名分区扫 TS 配置文件会漏掉声明在前的共享数组（2026-08-04 替代程序金额列标注实测）**：H0-5/K0-5/K0-6/G0-6 把「记账凭证」5 列抽成 `const VOUCHER_COLS` 并在四个区块各 spread 一次，它**声明在 `BLOCK1_COLUMNS` 之前** → 只认 `BLOCK([1-4])_COLUMNS` 的扫描器少标 4 列（dry-run 报 72 而实测应 76），且少标的那几列在 UI 上只表现为「金额不带千分符」，四层验证全绿。→ 分区扫描前先 grep 该文件全部 `: BlockColumnDef[] =` 声明。
- **🔴 PowerShell `>` 重定向产出的是 UTF-16**，python 以 `encoding='utf-8'` 读会报 `can't decode byte 0xff in position 0`（BOM）→ 要让 python 读的中间文件**必须由 python 自己写盘**；且脚本输出名不能与 PS 重定向目标同名（否则 `PermissionError`）。
- **🔴🔴🔴 `@/utils/http` 与 `@/services/apiProxy` 返回形态不同，错配即静默取空（2026-08-03 F0 实测 P0，平台级高频陷阱）**：`apiProxy.ts` 文件头自己写着 —— **`http.get(url)` 返回 `AxiosResponse`（要 `const { data } = await http.get(...)`）/ `api.get(url)` 直接返回业务数据**（`http` 的响应拦截器只把 `{code,message,data}` 信封剥进 `response.data`，**不返回 data 本身**）。写 `import api from '@/utils/http'` 再按 apiProxy 形态读 `(res as any)?.wp_id` → **恒 undefined**，而响应体在 TS 里是 `any` → `get_diagnostics`/vitest/Vite 200 全绿，**只有浏览器能发现**。F0 矩阵三个品种账面金额因此全部静默取空。**判据**：`wp-id-by-code` 一类跨底稿取数，平台既有 20+ 处一律 `import { api } from '@/services/apiProxy'`，照抄它；若确要用 `@/utils/http` 则必须 `.data`。守卫要同时钉「客户端来源」与「读法」两侧。
- **🔴🔴 `utils/http` 的 GET 去重会 abort 掉并行的同 URL 请求（2026-08-03 实测，凡 `Promise.all` 并发取数都要查）**：`getRequestKey = \`${method}:${url}:${JSON.stringify(params||'')}\``，`addPending` 里 GET 命中已存在的 key 就 `pendingMap.get(key)!.abort()` —— **取消的是先发的那个**。故「并行拉同一底稿的 render-config 两次（各取一个 sheet）」必然丢一个，症状是自己的 diagnostics 里出现 `xxx: canceled`。正解 = **一次请求取全部需要的 sheet**。params 不同则 key 不同（如 `wp_code=F1/F3/F4` 并行是安全的）。
- **🔴🔴 F1/F3/F4 的 TB 核对标量键名三者各不相同，禁统一假设 `project_context.tb_amount`（2026-08-03 后端源码 + 浏览器双证）**：**F1 = `project_context.prepaid_tb_amount`**（另有并列口径 `prepaid_tb_leaf_amount`）／**F3 = `html_data.tb_values['2201']`**（顶层，不在 project_context，且是 `{code: 值, code_opening, code_closing_leaf, code_closing_tb, …}` 字典）／**F4 = `project_context.tb_amount`**。统一读 `tb_amount` 只有 F4 命中，另两个静默落空。**且三者下发的都是叶子聚合口径**（带 `parent_check.diff==0` 自证），与 `trial_balance` 可能不等 —— 实证 `2aa00f57`：F3 叶子 15,029,046.64 vs TB 30,058,093.28、F4 叶子 267,308,976.77 vs TB 534,617,953.54，**均正好 2 倍**（旧版 recalc 父子双算），两个循环的 docstring 都明确「取叶子口径是有意为之，TB 口径另放 `{code}_closing_tb`/`tb_amount_tb` 供并列核对」→ 跨循环取这三个数时**不要再拿 trial_balance 去"纠正"它们**。
- **🔴 `_silent: true` 的取数错误必须有 UI 出口，只收集不渲染 = 自己蒙住眼睛（2026-08-03 F0 实测）**：`loadF0MatrixSources` 把错误收进 `diagnostics.errors` 却从不显示，界面只显示「待手工填写」→ 与「本项目确实没这科目」不可区分，正是它掩盖了上面那个 http 形态错配。凡 `_silent` 取数都要么渲染 errors，要么在 console 打点；守卫应断言「errors 有模板消费点」。
- **🔴 函证完整表格视图的编辑永不落库（2026-08-03 实测，七循环共享，未修）**：`GtConfirmationSummary.handleGridUpdate` 只调 `data.updateField` **不 `emit('save')`**，`useConfirmationData` 也无 autosave；只有列表视图的 `ConfirmationMaster @save="handleSave"` 有保存入口。实测录一行 + 四字段 → 刷新 → onboarding 回来、`checklist_responses` 0 条、`html_data` 仍空、**无任何提示**。影响 D0/E0/F0/G0/H0/K0/L0；修法（自动保存 vs 补保存按钮）需裁决。**副作用**：在完整表格视图做实测天然不产生落库数据，无需复原（但也测不到落库）。
- **🔴 用合成事件驱动 `el-select` 只改 DOM 不改 model（2026-08-03 实测）**：直接给 el-select 内层 `input` 赋 `value` + 派发 input/change/blur，a11y 树里能看到新值、界面也显示，但**派生字段不重算**（实测 `相符情况` 看着是「相符」而 `差异金额` 仍按空值算出 1,000）→ 会让人误判成「派生逻辑坏了」。正解 = 点开下拉再点 option（`.el-select-dropdown__item`）；**注意页内可能有多组同名 option**（本次「相符」在第 3 组），要按组或取 `.pop()` 定位。纯 `input`/`el-input-number` 用合成事件是有效的。
- **🔴🔴🔴 `@/utils/http` 与 `@/services/apiProxy` 的返回形态不同，混用＝取值恒 undefined（2026-08-03 F0 实测，平台级高频坑）**：`apiProxy.ts` 文件头自己写着 —— `http.get(url)` 返回 **AxiosResponse**（payload 在 `.data`，响应拦截器只是把 `{code,message,data}` 信封剥进 `response.data`、**仍返回 response**）；`api.get(url)` **直接返回业务数据**。F0 的 `f0MatrixDataSources` 写 `import api from '@/utils/http'` 却按 apiProxy 语义读 `idRes.wp_id` → **恒 undefined → 后续 render-config 根本没被调用**，三个品种账面金额全取不到，而 `get_diagnostics`/vitest/Vite 200 全绿。**跨底稿 pull 一律用 `import { api } from '@/services/apiProxy'`**（平台 20+ 个模块 `h1CipH2Pull`/`g13FvCrossHelpers`/`h2L1LoanPull`… 都是它）。**掩盖机理**：`cfg?.sheets ?? cfg?.data?.sheets` 这类双写 fallback 会让一半路径"碰巧能用"，不对称就看不出来 → 守卫要断言 import 路径本身。
- **🔴🔴 `utils/http` 的请求去重会 abort 并行的同 URL 请求（2026-08-03 F0 实测）**：去重键 `method:url:JSON.stringify(params)`，`Promise.all(...)` 并行拉同一个 render-config 时后发者 `addPending` 会 `pendingMap.get(key)!.abort()` **打掉先发者** → 症状是其中一路恒 `canceled`（F0-5 的替代确认合计恒 0、勾稽恒不成立）。**任何「并行请求同一 URL」的写法都中招** → 改成一次请求取多份数据。
- **🔴🔴 F1/F3/F4 下发账面金额的键名**三者各不相同**（2026-08-03 真实库对账，别按一个键统一读）**：F1=`project_context.prepaid_tb_amount`（并列 `prepaid_tb_leaf_amount`）· **F3=`html_data.tb_values['2201']`（顶层，不在 `project_context`，且是 code→值 字典）** · F4=`project_context.tb_amount`。统一读 `project_context.tb_amount` 只有 F4 能取到，另两个静默落空。→ 跨循环取数一律**逐循环声明取值路径**（F0 用 `F0_BOOK_AMOUNT_SOURCES[cat].pick(htmlData)`）。
- **🔴 `trial_balance` 父子双算再添三个 F 循环样本（2026-08-03 `2aa00f57` 实证）**：`trial_balance` 值**正好是叶子聚合的 2 倍** —— F1 `2,603,836.86 = 2 × 1,301,918.43` · F3 `30,058,093.28 = 2 × 15,029,046.64` · F4 `534,617,953.54 = 2 × 267,308,976.77`（与 memory 已记的 H2/H8 同款）。→ 跨循环取账面额一律用**叶子口径**（各循环 render 的 `*_leaf_*` / `tb_amount` 就是叶子），不做换算、不取 `*_tb`。
- **🔴🔴 未修 P0：函证「完整表格视图」的编辑永不落库（2026-08-03 F0 实测，波及 D0/E0/F0/G0/H0/K0/L0 七循环）**：`GtConfirmationSummary.handleGridUpdate` 只调 `data.updateField` **不 `emit('save')`**，`useConfirmationData` 也没有 autosave；只有列表视图的 `ConfirmationMaster @save="handleSave"` 有保存入口。实测录一行 + 四字段 → 刷新 → onboarding 回来、`checklist_responses` 0 条、`parsed_data.html_data` 仍空 → **数据全丢且无提示**。修法（自动保存 vs 补保存按钮）属共享组件级决策待裁决。**副作用**：在完整表格视图做的实测不产生落库数据，也就不需要复原。
- **🔴 「取数诊断只收集不渲染」会让整条链路失效与「本项目确实没这科目」不可区分**（2026-08-03 F0 实证，正是它掩盖了上面的 http 客户端错配）：`diagnostics.errors` 一直只存不显，界面只显示「待手工填写」。→ 凡 `_silent: true` 的取数编排，**errors 必须有渲染出口**（warning 提示条）并加守卫钉死。
- **🔴🔴 F0-1「一、函证情况」矩阵三条 SUMIF 是源模板确切公式（2026-08-03 `data_only=False` 直读，凡做函证汇总矩阵先照抄别自拟）**：上区 R6 列语义 `E=账户/交易 · F=金额 · U=可确认金额 · Y=替代后可确认金额`；`R31=SUMIF(E,品种,F)` / **`R33=SUMIF(E,品种,U)`（无相符过滤）** / **`R36=SUMIF(E,品种,Y)`** / `R37=(R36+R33)/R30`。→ ①「回函确认金额叠加 `match_status='相符'` 过滤」是**双重口径** —— 平台 `useConfirmationData.computeConfirmedAmount` 已按相符→amount / 不符→reply_amount / 未回函→amount 或 alt_confirmed 派生出 U 列，业务规则本就在里面（E0 的 `e0SummaryMatrix` 同样直取 `confirmed_amount`）②「替代确认金额按 F0-5/F0-6 底稿合计反推品种归属」是**编造** —— 替代金额本就逐行记在上区 Y 列；替代程序底稿合计只配做**勾稽**（Y 列合计 ?= 两表凭证金额合计，不符即提示「Y 列漏填 / 底稿漏编」）③**`computeConfirmedAmount` 对「积极式+未回函」返回 `alt_confirmed` → 该行 U===Y，源模板 R37 会双算**；正解是**忠实实现公式 + 如实提示风险行**，不擅自改公式（改了就不是源模板口径）。
- **🔴🔴 `review_dialog._SECTION_PROMPTS` **没有门**，缺登记≠空转（2026-08-03 修正 memory 铁律的适用范围）**：memory 记的「`_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS` + 前端联合类型 + `AI_TARGETS` 四处缺一即空转」只适用 **`wp_ai` 的 `/ai/generate-text`**（那里 `if body.section not in _SUPPORTED_SECTIONS: raise 400`）；`review_dialog.resolve_review_ai_prompt` 是 `.get()` **回退通用 prompt**，未登记只影响 prompt 质量。→ 判「某 prompt 有没有用」的正确判据是**有没有前端消费方**：section_id 只来自 `useReviewDialog(props.sectionId)`，而 **confirmation 目录确实有组件走这条路**（`GtConfirmationAlternativeH05/K05/K06` 五个 `GtReviewTrigger`，section-id 形如 `H0-5-alternative`/`K0-6-conclusion`，且这些 id 全未登记专属 prompt = 正常走回退），**只是 F0 一个都没接** → 给 F0 加的 6 条 prompt 无论内容对不对都不触发，已撤回。**撤回的另两条依据**：F0-1「三、审计说明」实为 **5 段**（`S29` 对询证函保持的控制的说明 / `W29` 对误差的分析 / `S33` 对回函可靠性的考虑 / `S34` 针对不符事项的程序 / `S37` 针对未回函的替代程序），原 4 条自造了不存在的「第三方平台评估」段又漏两段；**F0-4 压根没有审计说明/结论区**（只有 9 列明细 + R21 合计）。**源模板笔误留证**：`S33` 写「（F0-6）」而可靠性验证表实为 **F0-7**（F0-6 是应付及采购替代程序），按原文保留禁「顺手修正」。**遗留裁决**：要给 F0 做源模板忠实的分段审计说明＝让 F0 脱离共享 `ConfirmationNotes`（平台通用 5 段 总体/异常/未回函/替代/其他），F0 的 5 段与平台 5 槽**不能双射**，硬塞就是「压扁」反模式，且 F0 已有 `ai-generate-notes` 批量预填 → 再加会变成两处审计说明双录入，属共享组件级决策。
- **🔴 抽 `_SECTION_PROMPTS` 键集不能用 `\{(.*?)\n\}` 截字典体**：prompt 值本身是多行括号表达式，非贪婪会停在第一条 entry 的收尾括号上（实测只抽到 10 个键，真实 45+）→ 改「声明处 → 下一个顶层 `def`」切片；且该字典用 `**{...}` 推导式批量注入 I 循环/H7 的 id，**字面键 ≠ 全部键**，判「某前缀是否存在」要对声明体原文做全量扫描。
- **🔴 函证汇总表有 onboarding 分支会把整个下区藏起来（2026-08-03 F0 实测，判「实测是否有效」的硬判据）**：`GtConfirmationSummary` 的 `v-if="data.rows.value.length === 0 && !hasInteracted"` 命中时只渲染引导页，矩阵/样本选择/审计说明**全不在 DOM 里** → 空底稿下「打开看了眼没报错」等于什么都没测。必须先点「+ 新增函证对象」（同时置 `hasInteracted`）才有可测内容。**实测三件套仍是：录 ≥2 行真实数据 → 看目标区域真出数 → postgres 查 `checklist_responses` 落库，缺一不算实测**。
- **🔴 chrome-devtools MCP 里两条复现取数的路都不通（2026-08-03 实测）**：`sessionStorage` 抛 `SecurityError: Access is denied for this document`；`fetch('/api/...')` 抛 `Failed to parse URL`，补 `location.origin` 后仍得 `null/api/...`（evaluate 上下文的 origin 为 null）→ 想验「某请求为何没发」应读**组件自己的 diagnostics 状态**或 devtools 网络面板，不要在页面里手写 fetch。另 `performance.getEntriesByType('resource')` 在长开页面上会被清空（返 0 条），不能当「请求没发生」的证据。
- **🔴 一个诊断脚本里**两次 `asyncio.run()` 必炸**（2026-08-03 实测）**：连接池绑定首个事件循环，第二次 run 拿到已关闭的 transport → `AttributeError: 'NoneType' object has no attribute 'send'` + `RuntimeWarning: coroutine 'Connection._cancel' was never awaited`。多轮查询一律合并进**同一个** `async def _all()` 再一次 `asyncio.run`。
- **🔴🔴🔴 修真源错码会把「潜伏错误」变成「活的取数错误」—— 凡改 `report_config` 必先查谁在拿这个 row_code（2026-08-05 V138 实证，本 spec 最贵的一条）**：`l_cycle_extraction/account_scope.py` 声明 L3 `row_code_soe="BS-085"`（soe 侧长期借款实为 `BS-061`，那个 soe 编号来自 seed 脚本里的**第三套历史编号**）。V138 前 `BS-085=TB('4102')` 是全库零命中码 → 反解为空 → `resolve_report_line_account_codes` 的 `return codes or fallback` 回退到 `2501`（**碰巧正确**）；V138 把它改成**存在的** `4003` 后反解成功 ⇒ **L3 在国企项目开始查「其他综合收益」**。机理三件套：①该函数**不做存在性校验** ②`pick_row_codes` 对 soe 返 `[soe, listed]` 并在 `resolved_from==report` 时 **break** ③零命中码天然被 fallback 兜住 ⇒ **「错 row_code + 零命中码」是稳定的假正确，一旦把码修对就暴雷**。→ 改真源前必须扫全部 `row_code` 消费方并逐个对账（本轮据此连修 5 处：L1/L3/L4/L5 + K5 `BS-068→BS-065`，后者与 L7 撞码）。
- **🔴🔴 同名导出 + 守卫导入错模块 = 整类错误永久逃逸（2026-08-05 实证，上条能潜伏这么久的根因）**：`four_table/l_cycle_specs.py` 与 `l_cycle_extraction/account_scope.py` **都导出 `L_CYCLE_SPECS`**，前者 row_code 全对、后者才是被 render 真实消费的且有 4 处错；`test_cycle_specs_row_code_evidence._all_specs()` 导入的是前者，且**只覆盖 D/F/G/I/L/M/N —— 缺 K 和 H** ⇒ K5/L7 撞码与 L 的 4 处错行全部逃逸。→ 写「声明真源」守卫前先确认**导入的模块与生产路径消费的是同一个**（同名导出要按文件路径区分），且覆盖面要枚举全部循环而非手写清单。
- **🔴🔴 `report_config.formula` 的区间函数名是 `SUM_TB` 不是 `TB_SUM`（2026-08-04 全表实证：`regexp_matches(formula,'([A-Za-z_]\w*)\s*\(','g')` 去重只有 `TB` / `SUM_TB` / `ROW`）**：正则写 `\bTB(?:_SUM)?` **漏掉 `SUM_TB`**（`_` 是词字符，`\bTB` 在 `SUM_TB` 中间不成立）→ `BS-010 存货 = SUM_TB('1401~1499') − TB('1416')` 被误抽成**单码行**，于是拿「存货」比对备抵科目「存货跌价准备」而误报。正解 `\b(?:SUM_)?TB\s*\(`，并加「全表 formula 只允许 TB/SUM_TB/ROW，出现新函数名即打红」的守卫。
- **🔴🔴 `report_config` 行名 ↔ 科目名对账的适用范围（2026-08-04 定论，误报约 40 行后收敛出来的）**：**严格名称比对只适用「余额类报表(`BS`/`IMP`) + 去重后单码 + 非区间」的行**，四类必须排除 —— ①**多码合成行**（`BS-002 货币资金=1001+1002+1012` 无一叫「货币资金」；`BS-028 固定资产=1601−1602` 减项当然不叫固定资产；`BS-005/006/009/010/027/031/032/050/063` 全是减备抵）②**流量/变动额表**（`CFSS`/`IS`/`EQ` 的行名是「XX的增加/减少/折旧/摊销/损失」或多科目合计：`CFSS-005 固定资产折旧←1602 累计折旧`、`CFSS-013 投资损失←6111 投资收益`、`EQ-001 上期期末余额←五个权益科目`）③**「其中：」明细行**（`IMP-002 其中：应收账款坏账准备←1231.02`，父科目名是「坏账准备」→ 仅对明细行放宽为子串包含）④**双算判据必须按 (报表, 完整码, 取数列) 归并，不能按 head**（按 head 会把「1231-01/1231/1231-03 三个不同备抵明细」「父行+明细行」「期末 vs 期初两时点」全误判成双算）。**排除的行仍要过「码必须存在」与「派生行必须 NULL」两道检查**，不是放行。
- **🔴🔴 连库 pytest 守卫要用「一次 `asyncio.run` 取快照 + 全部断言同步」，别每个测试各自 async（2026-08-04 实测）**：`app.core.database` 连接池绑定**首个**事件循环，pytest-asyncio 默认每个测试新建 loop → 第二个测试起报 `AttributeError: 'NoneType' object has no attribute 'send'`，若 fixture 里 `except → pytest.skip` 就变成**静默跳过 = 假绿**（实测 6 个连库断言全跳）。**自定义 module 级 `event_loop` fixture 被当前 pytest-asyncio 忽略（试过无效）** → 正解是一个 `Snapshot` dataclass + 一个 `async def _load_all()` 里跑完全部查询 + 一次 `asyncio.run`。与「一个脚本里两次 `asyncio.run()` 必炸」同源。
- **🟡 `test_g_cycle_formula_presets::test_disclosure_presets_script_check` 失败属并发会话（2026-08-04）**：它扫 `backend/scripts/fix/`，而并发会话的 G0/H0 spec 刚往那里加了 `fix_g0_prefill_presets.py` / `fix_f_cycle_prefill_presets.py` / `fix_e1_orphan_sheet_presets.py` 等未跟踪新脚本。判归属：该测试文件自身 `git status` 干净且零引用你改的符号。
- **🔴 从源码抽科目码时要排除区间端点常量**：`_F2_INVENTORY_CODE_HI = "1499"` 是 `SUM_TB('1401~1499')` 的边界不是真科目码，拿去查 `account_chart` 必然「零命中」= 假阳性。判据 = 常量名带 `_HI/_LO/_MAX/_MIN/_BOUND/_END/_START` 或紧邻 `~`。
- **🔴 postgres MCP 的校验器会拒绝含 `unnest(...)` 相关子查询的 SQL**（`Error validating query`，不是语法错）→ 复杂名称比对改「SQL 只取原始对，Python 本地判定」。
- **🔴🔴 守卫里的 `SKIP_PATTERNS` / 白名单用**子串**匹配会误伤真实文件，且症状是「漏检＝假绿」不是打红（2026-08-03 Task 31 实测）**：`test_semantic_resolver_coverage.SKIP_PATTERNS` 的 `_engine` 吃掉 `_h4_engineering_materials.py`、`_special` 吃掉 `_m7_special_reserve.py` → **M7 这个确实未迁移的四表策略直接逃出裁决名单**（域 57→59、未迁移 32→33）。正解 = 加 `DOMAIN_FORCE_INCLUDE` 显式纳回 + **一条「这些文件确实仍被 SKIP_PATTERNS 误伤」的非空操作自检**（误伤消失就该把它们移出，防常量变死代码）。**凡按文件名子串排除的守卫都要核一遍实际被排除清单**，别只看模式表看起来合理。
- **🔴 守卫的基线常量必须写明**度量域**（2026-08-03 Task 31 实测）**：`REAL_CONSUMPTION_BASELINE=24` 是「过滤集」口径、tasks.md 记的 28 是「全量 render 文件」口径 —— 两个口径差 2，把 28 直接填进旧断言会假红、把 24 当全量会低估。同一个数字在不同域下不可互换 → 常量注释里必须写清「域 = 哪个函数返回的集合」，并配一条按维度拆分的下限（本例 `REAL_CONSUMPTION_BY_CYCLE`）防总数不变但内部互相掩盖。

- **🔴🔴🔴 「批量脚本 additive 注入 + grep 式守卫」= 自造假绿（2026-08-03 语义解析器全量迁移复盘，代价是一轮 57/57「100% 完成」全部推翻）**：①**注入即死代码** —— 脚本给 23 个 render 塞 `_sem_accounts = await resolve_semantic_accounts(...)` 但**从不读取**（assigns=2 / reads=0），取数前缀一行没改，每次 render 白跑 3~7 条 DB 查询后丢弃（比不迁移更差）；8 个的 `as_dict()` 还被插进 `except` 分支（只在取数失败时生效）。②**守卫只 grep 字符串就是假绿源** —— `test_semantic_resolver_coverage.py` 第一版查 `resolve_semantic_accounts` 是否出现 → 死代码全判绿 → tasks.md 记 28/28。正解 = 断言**结果被真实消费**（`codes_of`/`slots`/`as_dict`/整体传参下游）+ **拿死代码样本做反向自检**。③**换共享件解析器必须先查下游读什么属性** —— F1/F3/F4/F5 换成 `resolve_semantic_accounts` 但下游仍读 `accounts.gross`/`.resolved_from`（`ReportLineAccounts` 字段，`SemanticAccountResult` 没有）→ 运行时 AttributeError，**962 例测试全绿一个没抓到**（各循环 `_fetch_tb_data` 基本无测试真调用）；G7 当初加 `_extract_codes` 桥接才没炸。`dir(类)` 查不出 dataclass **字段**（`gross`/`gross_standard`），排查要按字段名 grep。④**新建 `_specs.py` 的兜底码禁按通用 CAS 猜** —— 我按 CAS 常识写的 `m_cycle_specs` **7/7 与平台实证值全不符**（资本公积我写 4101、平台实证 4002），且 L7 与 K5 撞 `2801`、I6 与 K9 撞 `6602`（6602 是管理费用）；未接线时"无害"= 给下个会话埋地雷 → 必须核 `report_config` + `account_chart` + `tb_balance` 三方，无实证一律 `fallback=()`。⑤**跨循环互斥守卫必须覆盖全部 spec 格式** —— 第一版排除了 K（`KCycleSpec`）与 H，恰好漏掉 L7/K5 撞码。
- **🔴🔴 「立 spec 前必须逐个核实共享组件的既有实现度」（2026-08-03 F0 实证，代价是写了 4 个零消费方模块）**：F0 立项时按「组件缺失」判断，逐个核实后发现 6 个共享 confirmation 组件（summary / diff-checklist / diff-reconcile / reliability / fraud-risk / followup）**既有实现度远超预估** —— 差异九段公式（`useDiffChecklistData.computeFormula` 已有 D=A+B−C / H=E+F−G / I=H−D + 动态行 CRUD + 重要性判定）、19 条舞弊迹象三态 + 预置应对措施库、可靠性结构化列（身份确认/邮箱验证/致电确认/结论四组）、跟函三核对点 el-select、抽样四选一下拉 **全都已在线**。→ 立 spec 时的「缺口清单」必须先 grep 既有 composable 与 `*Types.ts`，**不能只看源模板 vs UI 截图**。判据：既有 `useXData` 的 `computeFormula`/`derive*` 函数 + `XEnums.ts`/`XTypes.ts` 的字段声明。
- **🔴🔴 「纯函数写完 ≠ 需求实现」，接线才是交付（2026-08-03 F0 四个模块全零消费方）**：`f0AltSupplierSeed`/`f0DiffChecklistEngine`/`f0FraudRiskPush`/`emailDomainCheck` 四个模块 167 测试全绿、`get_diagnostics` 零诊断、Vite 200，但**没有任何调用方** = 与 E1 spec 抓到的「8 个组件写好从未渲染」同款。更隐蔽的一种：组件里把入参全传 `undefined` 并留 `// TODO` 注释（F0 矩阵的 `bookAmounts`/`altTotals`/`manualOverrides`）→ UI 渲染出来了、测试也过了，但**4 个百分比行恒 `-`、替代确认恒 0**，立项要解决的痛点原地不动。→ **自查清单**：①新建模块 grep 消费方，0 命中即未交付 ②组件里搜 `undefined,\s*//\s*TODO` ③矩阵/表格类要断言「入参不得全为 undefined」。
- **🔴 「浏览器实测」的最低标准 = 录数据 + 查库，不是「挂载无报错」（2026-08-03 F0 退回 3 项）**：上轮 Task 20~22 只做了「11 Tab 挂载 + 零 console error」就标 `[x]`，而空底稿下矩阵区域因 `v-if="rows.length > 0"` **压根没渲染**（看到的是 onboarding 页）。验收标准写的是「修改 grid 后刷新 → 值变化」。→ 实测三件套：**①录 ≥2 行真实数据 ②看目标区域真出数 ③postgres 查 `checklist_responses` 落库**，缺一不算实测；测完必须复原数据。
- **🔴 从源模板抄常量前先查平台是否已有一份（2026-08-03 F0 双真源）**：`f0FraudRiskPush.F0_FRAUD_INDICATORS`（19 条舞弊迹象）与既有 `fraudRiskPresets.ts` 构成双真源，且浏览器实测显示**两套文字完全不同**（我抄的源模板「管理层不允许寄发询证函」vs 平台既有「被审计单位管理层凌驾于内部控制之上」）。改一份另一份不动 = 漂移。
- **🔴 「简化设计 v1」是「宁缺勿造」的违规信号词（2026-08-03 F0 自查）**：`distributeAltAmounts` 的「F0-5 全归预付账款 / F0-6 平分应付票据+应付账款」无任何源模板依据，注释里自己写了「简化设计 v1」。**凡在注释里给分摊/归属逻辑写「简化」「暂定」「v1」的，都要么补源模板依据、要么返 null 显示「-」**；更坏的是配套测试只是把编造重复了一遍 → 全绿证明不了任何事。

- **🔴🔴 判 openpyxl 数据验证（DV）必须 `coord in dv.sqref` 逐格测试，禁按打印顺序取第一个 sqref（2026-08-04 H0 实证）**：openpyxl 打印 `dv.sqref` 时会带出 `JF/JK/TG/ACX` 等远端列范围 —— 那是 Excel **列重复产生的残留 sqref**，**不落在真实列上**。照打印顺序取值会得出「H0-1!G 列（函证方式）DV = `跟函,邮寄,电邮,其他`」的错误结论（实测 H0-1 真实 DV **只有 C/L/N/X 四列**，那条 DV 只存在于镜像列）。守卫要加反向自检断言「该镜像 DV 确实存在于文件中但不覆盖真实格」。**六枢纽 X0-2 的三处 DV 完全同构**（`C7` 发函渠道=邮寄/跟函/电子函证/其他 · `P7` 回函介质=纸质原件/电子函证/其他介质 · `L7` 核实方式 6 项），`X0-1!C8` 选样目的 5 项亦同构 → 这四组是**七枢纽共享的源模板事实**，不是某一循环专属。
- **🔴🔴 平台的「函证方式」有两个不同维度，不可互相替代（2026-08-04 H0 定论）**：源模板 X0-1/X0-2 的「函证方式」列 DV 是**发函渠道**（邮寄/跟函/电子函证/其他）；而平台既有 `ConfirmationRow.confirmation_method` 是准则 1312 的**积极式/消极式**，且 `ConfirmationDetail.vue` 的可确认金额派生依赖 `confirmation_method === '消极式'`（消极式未回函→视同相符）→ **把它改绑渠道枚举会让该派生分支永久失效**。正解 = 渠道另立字段 `send_channel`（新增 `confirmation_send_channel` 字典），`confirmation_method` 语义不动、仅在 H0 上把 label 改为「函证类型（积极式/消极式）」以区分。
- **🔴 H1~H10 十个 render 策略 `tb_amount` 零命中（2026-08-04 实证）**：H 循环下发的是 `html_data.tb_values`（按槽前缀键如 `cost_unadjusted`/`rou_asset_audited`）+ `tb_source_codes`，**没有** `project_context.tb_amount`。凡想「读相邻 H 循环账面额」的场景不能照抄 F0 的 `F0_BOOK_AMOUNT_SOURCES` 口径（照抄必得 `undefined` = 又一个 dead output），须自己按品种走 `four_table/h{n}_account_scope.py` 语义定位 + 叶子聚合。
- **🔴 前端守卫的 `REPO_ROOT` 一律用「哨兵文件」向上查找，禁写死回退级数；且哨兵必须是**具体文件**不能是目录（2026-08-04 两次踩中）**：①`e0-send-list/__tests__/sendListSpec.spec.ts` 写死回退 7 级而实为 **8 级** → 解析到 `audit-platform`、`audit-platform/backend/data/...` ENOENT → **该文件 12 条断言从未执行过**（全量报告里表现为「文件级失败」而非断言失败，极易被当噪声跳过；已修，修好后 15 例全过）②哨兵写成 `backend/app/routers` **目录**会在 `audit-platform` 层提前停下 —— `audit-platform/backend/app/routers` 是历史遗留空目录，确实存在。**判「某守卫是不是真在跑」看它有没有文件级 message，不只看断言数**。
- **🔴 动态列/动态行的稳定 key 需要**持久化单调计数器**，只取「现有最大 seq + 1」会复用已删除的 key（2026-08-04 H0 矩阵实证）**：删掉 `cat_3` 再增列又得 `cat_3`，历史手工覆盖值 `H0-1-matrix-cat_3-0` 会串到新列显示错误金额。正解 = 另存一个 `X-seq` 持久化键，`next = max(现有最大, 已存计数器) + 1`；守卫保留一条反向自检「不传计数器必复用旧 key」。H7 的 `{slot}_{seq}` 范式同样适用本补强。
- **🔴 共享 componentType 的循环专属数据走 `wp_render_config_helpers` 的加法式注入，禁注册 `RENDERER_DISPATCH`（2026-08-04 H0 落地）**：`confirmation-summary` 是七枢纽共享，注册即让 D0/E0/F0/G0/K0/L0 载荷全部改道。范式 = 仿 `_inject_confirmation_population`，注入器内部**先按 `wp_code` 前缀门控再取数**（门控必须早于取数调用），守卫断言「其余六枢纽载荷注入前后深比较逐字节不变」+「`confirmation-summary` 不在 dispatch 表里」。另：**「注入整体失败」与「本项目无此科目」必须可区分** —— 前者键不存在，后者键存在值为 `null`；前端**不得写 `?? {}` 兜底**（会把前者变成后者，全部品种显示「本项目无此科目」）。
- **🔴 各循环有专属 AI 端点，通用 `/ai/generate-text` 未登记的 section 会 400 被 catch 静默吞（2026-08-04 H0）**：H0 走 `POST /workpapers/{id}/h0/ai-generate`，载荷 `{section, existingContent, relatedContext}`（**驼峰**），section 须在 `_h0_confirmation_ai.py` 的 `_SUPPORTED_SECTIONS` 登记。守卫要交叉锁死「前端 `aiSection` 集合 ⊆ 后端已登记」+「每条 prompt ≥40 字且含 `_NO_FABRICATION`」。
- **🔴🔴 「裸通名兜底」会把别的循环的备抵抓走（2026-08-04 真实库实证，H3 是活的错数）**：`match_slot_in_chart` 按 `names` 声明顺序取**第一个精确命中**的名字。DB 实证裸名归属：`累计折旧`=`1602`（**H1 固定资产**，standard 10 项目 / client 7 项目都是裸名）· `累计摊销`=`1702`（无形资产）· `累计折耗`=`1632`（**H5 油气资产**，正主）· **`未确认融资费用` 同时是 `2602`（租赁负债）与 `2702`（长期应付款）两个顶层科目**。而 `1525 投资性房地产累计折旧`/`1526` 只在 4~5 个项目存在 → H3 原把裸名列作第二兜底名，缺 1525/1526 的项目精确命中 1602/1702，**把固定资产累计折旧+无形资产累计摊销从投资性房地产原值里扣掉** → 投资性房地产账面金额变负（`4f6dbc36` −21,601,944.08 / `df5b8403` −11,322,704.22 / `f064f5e4` −21,864,702.78）。`exclude_names` **拦不住**（裸名里没有「固定资产」这类关键词）。修法 = 只留带主体前缀的专名 + `fallback_standard_codes`，缺该科目就 `found=False` **不扣减**（宁缺勿造）。已同款处理 H8 `accum_dep`、H9 `unearned_finance`（均潜伏态）；**H1/H5 保留裸名是对的**（1602/1632 本就是它们自己的）。守卫 `tests/four_table/test_h3_account_scope.py`（+12 例，含 3 条反向自检）。
- **🔴🔴 `aggregate_leaves` 忽略 `closing_direction`，族内方向不一致时会把 contra 子科目加成正数（2026-08-04 实证）**：`c8621493` 的 `2651 租赁负债` 家族 `2651.01 租赁付款额 98,176.48(credit)` + `2651.02 未确认融资费用 3,956.64(**debit**)`，父额 94,219.84；裸 `aggregate_leaves(absolute=True)` 原样求和得 **102,133.12**。正解 = `resolve_leaf_totals(rows, prefix, absolute=True)`（两种符号约定都算、取与**父额**勾稽成立的那一种），且**不得**先 `select_leaves()` —— 父科目行是符号约定的判定依据，剔除即退化成原样求和。**另需一条规则**：备抵槽若是原值科目族的**子科目**（`2651.02` 在 `2651` 下），父族聚合已按方向净掉 → **再减一次就是双算**，须跳过并如实记 `net_of_skipped`。
- **🔴🔴 `confirmation-summary` 的宿主 save 处理器把载荷整体写成 sheet 的 `html_data` —— 下区/itemId 维度录入绝不能 `emit('save', {itemId, value})`（2026-08-04 H0 实测，一次点击就 brick 掉整张表）**：实测 `html_data['函证结果汇总表H0-1']` 被覆盖成 `{"itemId":"H0-1-matrix-seq","value":"4"}`，**函证行全丢** + `_format` 消失 → 该 sheet 下次打开显示「此底稿使用旧格式，仅支持只读查看」。itemId 维度录入一律直接 `http.put('/api/workpapers/{id}/checklist-responses', {project_id, items:[{item_id, remark, conclusion}]})`（平台 40+ 处同形）。
- **🔴 `PLACEHOLDER` 是一等 `formula_type`，但三处白名单都可能漏它（2026-08-04 补齐）**：语义 = 「该格值无法用单一科目码公式表达，取数真源在别处」，**有意永久 pending**（grammar_v1 里不会有等价函数头）。三处白名单：`preset_acnr_migration.PENDING_FUNCTION_ALLOWLIST`（生产代码）· `tests/test_h_prefill_extension.VALID_FORMULA_TYPES` · 各 preset purity 守卫。全库用它的 wp_code = **N1 / E1 / N3 / H0 / G0 / N5**（`test_h0_prefill_presets._PLACEHOLDER_REGISTRY` 逐条登记理由，新增须写「为什么写不成公式」防它变逃逸阀）。**顺带发现 `test_h_prefill_extension.VALID_H_ACCOUNT_CODES` 长期错**（把使用权资产写成 1621/1622 实为生产性生物资产、租赁负债写成 2802/2803 全库不存在、投资性房地产备抵写成 1522/1523 全库不存在），该条断言长期为红，已按实测校正。
- **🔴 单 sheet 遗留 wp_code（`H0-1`/`H0-2`…）render 出 `html_data=null`（2026-08-04 实测）**：`wp_render_config` 的 `_confirmation_initial_data` 与 grid 兜底两个分支**都要求 `_is_multi_sheet`**，单 sheet 工作簿两条都不命中 → `sheet_html_data` 停在 `None` → `_inject_confirmation_population` / `_inject_h0_book_amounts` 被 `isinstance(dict)` 挡掉。**函证实测入口必须用 `wp_code=X0` 的整册工作簿**（9 sheet），别用 `X0-1` 单 sheet 记录，否则会误判「注入没生效」。
- **🔴 并发会话的 HMR 中间态会让共享组件在浏览器里报 `Property "isG0" was accessed during render but is not defined`（2026-08-04 实测）**：磁盘源码是完整的，**硬刷新（`ignoreCache`）即恢复**。判「共享组件是不是真坏了」必须先硬刷新再看；否则会把并发会话的编辑中间态当成自己的 bug。
- **🔴 后端下发的 `conflicts` 是三元组 `[槽键, 报表公式给的码, 按名定位到的实际码]`，前端 `v.map(String)` 会渲染成 `impairment,1601,1602,1606,1603`**（读不出含义，违反「审计 UI 必须有逻辑追溯能力」）→ 需槽键中文标签表（`H0_SLOT_LABELS` 镜像后端 `h_cycle_specs` 各 slot.label，守卫读 py 源码交叉锁死）+ 翻成完整句子。**另注意 `build_conflicts` 在报表公式为空时返 `[]`** → conflicts 只是部分视图，不能当「没冲突」的证据。
- **🔴 `openpyxl` dump 源模板要取到 `ws.max_column`**（2026-08-04 H0-5 踩）：只扫 A~G 列会漏掉 `I/J/K/L` 列的字段，得出「样本选取只有 3 个字段」的错误结论（真实 6 个：`A7/A8/A9` + `I7/I8/I9`）。
- **🔴🔴 「共享过滤件靠 duck-typing 读 `getattr(codes,'subject_keywords',())`」= 少一个字段就静默空转（2026-08-05 D1 实证，本轮最贵一条）**：`fetch_d_cycle_tb` 对全部 D 循环无条件叠名称过滤，但 D2~D7 走 `DCycleAccountCodes`（有该字段）、**D1 走 `D1AccountCodes`（没有）** → 默认值 `()` ⇒ `filter_provision_codes` 的 `applied=False` 空操作 ⇒ D1 备抵取到整个 `1231`（一个项目 **1.02 亿**）。**四层验证全绿**（该函数的 fail-open 与默认值都合法）。→ **凡共享件用 `getattr(x, field, default)` 读「行为开关型」字段，必须配一条「全部调用方类型都真有该字段」的守卫**（遍历同域 dataclass 断言 `hasattr` + 值非空），别指望默认值兜底 —— 默认值恰好就是「功能关闭」。同族：additive 注入即死代码 / 换解析器先查下游属性。
- **🔴 判「某道过滤/兜底有没有真生效」不能只看它被调用了，要看它的**入参是否非空**（2026-08-05）**：源码级守卫断言「无条件调用 `filter_provision_codes`」是**通过**的，缺陷在第三个实参恒为 `()`。→ 这类断言要连带钉住「实参不得是空字面量」且「各调用方传入的关键词集合非空」。
- **🔴 只读诊断脚本的字段名错会伪装成「业务全线失败」，判 FAIL 前先分清脚本层与业务层（2026-08-05 一轮踩 3 次）**：`tb.fetch_ok`（载荷键 vs dataclass 字段 `ok`）/ `slot.standard_codes`（挂在另一个 dataclass 上）/ `for c,r in dropped`（元素是 dict，迭代得键名 → `ValueError: too many values to unpack`）—— 三处都让报告输出「48 处判据违规 / FAIL」，而取数其实是好的。**fail-open 只保护业务代码、不保护脚本自己** → 判据违规数 == 组合总数（8×6=48）这种「整齐的全错」几乎一定是脚本 bug；真实业务缺陷是零散的。
- **🔴 `tb_source_codes` 落点平台有两套并存约定，前端消费前必须实测（2026-08-05 D 类实证）**：**6 个 D render 写 `html_data` 顶层**（共享件 `composables/shared/cycleAccountScope.ts` / `tbSourceCodes.ts` / `semanticAccountSource.ts` / `WpSemanticAccountSourcePanel.vue` 正是读这层），**只有 D4 写 `project_context`**（由 `d4AccountScope.ts` 读；F1/F3/F4/F5/E1/G1 亦是这层）。全前端 `pc.tb_source_codes` 12 处 / `htmlData.tb_source_codes` 35 处并存。design.md 写的是 `project_context` 一种 ⇒ 照它写消费方会读到 `undefined`（又一个 dead output）。**另：D 类 render 直接返回 html_data 本身，不套 `{"html_data": ...}` 外层** —— characterization 守卫按「先取 `payload['html_data']`」找会 7 个循环全落空。

> **完整清单（后端/前端/OnlyOffice 各 30+ 条）见 `#conventions`**。最高频三条：

- **🔴🔴🔴 母公司附注章节 = listed 第十六章 / soe 第十二章（2026-08-05 先逐 section 后按源 docx 双重实证，**推翻并撤回「孤儿重复章应删」的旧判断**）**。**⚠️ 下面「soe 错挂/缺章」的表述已被源 docx 修正** —— soe 源 docx 第 12 章本身就是「母公司财务报表的主要项目附注」，14 个 Heading 1 里**根本没有股份支付章**（那是 listed 第 12 章），故真实缺陷是 **JSON 把第 12 章的 `section_title` 写成了「股份支付」、`section_id` 写成 `chapter-12-gu-fen-zhi-fu`**，6 个子节 `parent_section_id` 指向该章其实**没挂错位置**，只是父节点自己名字错。listed 源 docx 第 16 章标题是「**公司**财务报表主要项目注释」（JSON 多一个「母」字，已裁决保留 JSON 现值）。**源模板明文把母公司子节分两类**：①**同构子节**（源 docx 无自有表，listed 标题内直接写「披露格式参考附注五、X」、soe 章首说明「应参照上述相应项目的要求加以注释」）= listed 应收票据/应收账款/其他应收款/营业收入和营业成本、soe 应收账款/其他应收款/营业收入与营业成本 → **结构取合并章** ②**自有表子节**（与合并章不同构）= listed 长期股权投资(3 表 **7/9/13** 列均两级)+投资收益(1 表 3 列 16 行)、soe 长期股权投资(3 表 **5/7/12** 列)+投资收益(1 表 21 行)+现金流量表补充资料(1 表 31 行)。**两版子节集合不对称且禁对齐**：listed 独有「应收票据」、soe 独有「现金流量表补充资料」。JSON 现状长期股权投资列被压成 listed 3/4/4、soe 4/4/4。以下为首轮 section 级实证（部分表述已被上面修正）：`note_template_listed.json` 有 `十六、母公司财务报表主要项目注释`（level=1 章标题、`_synthesized=True`、`sid=chapter-16-mu-gong-si-...`），其下 6 子节 = 应收票据(14表)/应收账款(15)/其他应收款(18)/长期股权投资(3)/营业收入与营业成本(6)/投资收益(1)，`parent_section_id` 挂对；**合并章节是 `五、合并财务报表项目注释`(74 子节)**。`note_template_soe.json` **14 个顶层章里没有母公司章**，6 个母公司子节（应收账款11/其他应收款15/长期股权投资3/营业收入与营业成本5/投资收益1/**现金流量表补充资料**1）全部 `parent_section_id='chapter-12-gu-fen-zhi-fu'`（股份支付章）且 `section_id` 亦带该前缀 ⇒ **国企附注目录树上母公司科目显示在「十二、股份支付」下**（待修）；soe 合并章节是 `八、财务报表主要项目注释`(93 子节)。**三条配套事实**：①母公司章节全部 `scope='consolidated_only'`，该取值**语义正确**（`note_section_catalog.note_applies_to_report_scope` = 仅合并口径显示，单体报表本身即母公司报表），只是命名易误读 ②`note_template_variant_matrix.json` 102 科目 × 4 变体里 `soe_standalone`≡`soe_consolidated`、`listed_standalone`≡`listed_consolidated`（逐条比对差异 **0**）⇒ **单体/合并不区分**，母公司章节在矩阵**零条目**，全前端 40+ 个 `*NoteSectionMap.ts` 无一指向十六/十二章 ③母公司 57 张表 `columns` 全 0 / `report_row_code` 全 None ⇒ **母公司附注 100% 无数据来源、只能手工填且投影降级**。→ 「表数与主章节高度接近」是母公司口径重复列示同一批科目的必然结果，**不是 md 重建重复落章**；删它 = 删掉上市第十六章整章 + 国企母公司附注全部。
- **🔴🔴🔴 「国企↔上市转换」**生产路径的 6 步里有 3 步是空操作**，且真正实现映射的 v2 是孤儿（2026-08-05 逐方法读源码实证）**：生产入口 = `POST /note-conversion/execute`（`routers/note_conversion.py`）**或 `STANDARD_CHANGED` 事件自动触发**（`event_handlers/_impl._on_standard_changed_notes`）→ `NoteConversionService.execute_conversion()`，其 6 步 = ①`_create_snapshot` ✅ ②改 `project.template_type` ✅ ③**`_map_report_rows` = `return 0` 空操作**（docstring 写「按 row_name 映射报表行」，注释自承认「For now, return 0 as the chain refresh will handle regeneration」）④**`_map_disclosure_notes` 只 `SELECT count(*)` 返回个数、一行不改**，而该返回值被当 `mapped_notes` 报给用户 ⇒ **假成功反馈**（审计师看到「已映射 N 个章节」实际零映射）⑤**`_update_formula_references` = `return 0` 空操作**（理由「两准则 row_code 方案相同」—— 对多数行成立但**不完全**：同一语义派生行在不同变体挂不同 row_code，`BS-013`/`BS-016` 都叫「一年内到期的非流动资产」，`BS-053`/`BS-058`、`BS-043`/`BS-059` 同族 ⇒ `ROW('BS-013')` 切换后指向另一行）⑥`_trigger_chain_refresh` → `execute_full_chain(force=True)` ✅ 但 **fail-open**（失败仅 warning 不阻断转换）。⇒ **实际行为 = 只改 template_type + 全链重算，`disclosure_notes` 的 `section_number`/`section_id` 一行不改**；而两份模板有 **20 个章节号重合且 13 个标题不同**（`八、1` soe=货币资金 / listed=政府补助）⇒ **切换后原「八、1 货币资金」数据显示在上市「八、1 政府补助」位置**。**真正实现映射的 `convert_disclosure_notes_v2` 是孤儿** —— `Called by` **11 个全是测试、生产 0 调用方**（「未完成的重构」又一例），且它自身另有 3 个缺陷：`format_diff` 无 `section_id` 键 ⇒ `format_adapted_count` 恒 0 · `field_mapping` 全 null ⇒ `adapt_table_data` 空转 · **共有章节只计数、不把 `note.section_id` 改写成目标类型 sid** ⇒ 即便接线共有章节在新模板下仍对不上。→ 修转换必须从 `execute_conversion` 入手，别只改 diff JSON。
- **🔴🔴🔴 附注列结构真源按章节**三分且互斥**，「参照底稿披露表」只对第 ① 类成立（2026-08-05 全量实证，用户澄清后核出，**推翻 C spec 初版把真源统一写成模板 JSON 侧的前提**）**：337 张 `columns==0` 表分三类 —— ①**科目章节且有底稿披露 sheet**（listed 20 张/7 章 + soe 41 张/17 章）→ 真源 = `backend/wp_templates/**` 的披露 sheet，openpyxl 三向比对（平台既有范式）②**母公司章**（listed 57 + soe 36 = 93 张）→ 真源 = 母公司章 docx，**归 A spec** ③**非科目章节**（listed **163 张/53 章** + soe 20 张/11 章）→ **`backend/wp_templates/**` 里压根没有对应披露 sheet**（套期 16 / 关联交易 13 / 处置子公司 12 / 金融资产转移 12 / 风险管理 11 / 现金流量表项目注释 9 / 在合营安排或联营 8 / 在子公司中的权益 6 / 分部报告 5…），真源只能是附注模板 docx，**套「参照披露表」口径即自造**。→ 凡「批量补 columns」的方案必须先按此三分，否则第 ③ 类会被按不存在的披露表口径造出列结构。
- **🔴 「列参照披露表」范式平台已建立且覆盖约 35 个循环（2026-08-05 实证，勿重造）**：**38 个后端结构守卫**（`test_note_*_structure.py`，其中 **17 个 openpyxl 直读源 xlsx** 做「源 xlsx ↔ 模板 headers ↔ 同步 columns」三向比对）+ **40 个前端子表契约**（`*NoteSubtableContract.spec.ts`）+ **42 个幂等脚本**（`fix_note_*_structure.py`）。**真缺口只有 18 章**（科目章节且守卫未覆盖）：listed 4（`五、12` 一年内到期的非流动资产 / `五、35` 衍生金融负债 / `五、71` 现金流量表补充资料 / `五、74` 租赁）+ soe 14（`八、8`/`八、13`/`八、45`/`八、46`/`八、51`/`八、80`/`八、81`/`八、83`/`八、84`/`八、85`/`八、87`/`八、89`/`八、90`/`八、91`）。→ 新循环补列一律照抄既有守卫范式，别另写判据。
- **🔴 附注模板无「动态行」语义（2026-08-05 实证）**：`row_type` 取值域实测恰为 5 个 —— `data`(listed 2415/soe 1536) / `total`(332/236) / `subtotal`(62/58) / `header_label`(62/28) / `unowned`(0/1)，**没有 `expandable`**。而源披露 sheet 的可扩标记有 **6 种写法**（`……` 116 处 / `预留` 36 / `可改名` 24 / `可无限量添加行` 23 / `......` 6 / `…` 5），附注 JSON 已 seed 了 **90 个省略号行**（listed 59 / soe 31）但前端不认它是可扩位、投影会渲染成空数据行。平台动态行能力全在前端（`addRow` 865 处 / `ElMessageBox.prompt` 443 / `dynamicAdjudicationRows` 6 / `blankRows(` 3）。→ 模板侧标记（additive 第 6 个取值 `expandable`）与前端增行 UI 是两层，别混做一个任务。
- **🔴 `diagnose_disclosure_sheet_vs_template.py` 的表边界切分是启发式，脚本自己写明「不自动生成列定义、辅助人工核对」（2026-08-05 我按它批量跑后误报一批）**：对 D1 报「表1 源3列 vs JSON7列」，而 D1 早有 243 例 openpyxl 三向守卫全绿 ⇒ **批量启发式结果不可作为判据**，只能定位「哪些章节需要人工读源 xlsx」。判某循环列结构对不对，先查它有没有 `test_note_*_structure.py`（有且 openpyxl=Y 就是已裁决过的）。
- **🔴 附注模块地图（2026-08-05 盘点，避免重复调查）**：**36 个端点**（`routers/disclosure_notes.py`，分 9 组：生成读写 / 就绪度校验 / 底稿联动 / 单元格溯源 / 章节编号裁剪 / 公式 / 取数模板 / 导出导入 / AI）+ **75 个 `note_*` service + 18 个 disclosure service**（最大三个 `note_word_exporter` 97 符号 / `disclosure_engine` 86 / `wp_disclosure_sync_service` 57）+ 前端主视图 `views/DisclosureEditor.vue` + 11 个 `useNote*` composable + **约 173 个循环级 `*TabDisclosure*.vue`**。**5 个开关默认关 ⇒ 对应功能用户不可达**：`DISCLOSURE_NOTE_FORMULA_ENABLED=False`（附注公式 8 个 service 整体不求值）· `DISCLOSURE_NOTE_RAG_ENABLED=False` · `CONSOL_NOTES_V2_ENABLED=False`（合并附注走老版 7 骨架章节）· `CONSOL_CROSS_TEMPLATE_ENABLED=False`（跨模板翻译，双开关防御）· `CONSOL_MODULE_DEV_MODE=True`（前端「开发中」banner）。
- **🔴🔴 「国企↔上市转换」的 diff 数据侧另有四个硬缺陷（2026-08-05 实测 `note_template_diff.py` + `note_soe_listed_diff.json`）**：①落盘 JSON 自标 **`is_mock=True`** 且已 stale —— 实时 `compute_diff_from_templates()` 返 `is_mock=False` 且数量不同（common 106 vs **107** / listed_only 71 vs **70** / format_diff 33 vs **39**、common 集合比对 `False`），而生产走 `load_diff_data()` 拿的是 stale 那份 ②**`field_mapping` 全部 null（0/33）**，实测 `adapt_table_data()` 在 None 时**输入==输出**（某章节 soe 1 表 / listed 5 表，转过去仍 1 表）③format_diff 条目**没有 `section_id` 键**（实际键 = `field_mapping/listed_format/listed_section_id/section_title/soe_format/soe_section_id`）而 `convert_disclosure_notes_v2` 读的正是 `fd.get('section_id')` → 恒 None ⇒ 33 条格式差异一条都匹配不上 ④**按 `section_title` 精确匹配 ⇒ 20 对措辞差异被误判成「各自独有」**（`财务报表编制基础`vs`财务报表**的**编制基础` 0.94 / `递延所得税资产**和**…`vs`**与**…` 0.93 / `所有权**和**使用权受限`vs`**或**` 0.93 / `营业收入**、**营业成本`vs`**和**` 0.89 / `**研究**开发支出`vs`研发支出` 0.80）→ 转换时走「源独有归档 + 目标独有新建空章」**丢已录数据**；**但阈值不能简单放宽** —— `财务报表主要项目注释`(soe 八，合并) vs `**母公司**财务报表主要项目注释`(listed 十六) 相似度 **0.87**，放宽到 0.85 就把合并章节错配到母公司章节，这一对**必须人工裁决**。**另两处**：章号主映射 soe ch08→listed ch05(49)、soe ch04→listed ch03(26) 正确，但 **soe ch08→listed ch03 有 10 条**（财务报表项目注释映到会计政策章）+ soe ch12→listed ch05 2 条（母公司错挂的连带后果）；**variant_matrix 的 null 有假 null** —— 标 listed 侧 null 的 25 个科目里至少 12 个 listed 模板其实有落点，只是归在「三、重要会计政策」/「十四、日后事项」/「十七、补充资料」章（`三、资产减值损失（损`/`三、营业外收入（注：`/`三、现金流量表项目注`(9表)/`三、优先股、永续债等`/`三、借款费用`/`三、债务重组【不适用`/`十四、终止经营`/`十七、净资产收益率和每股收益`），矩阵按「同章节」找不到就记 null。
- **🔴🔴🔴 「国企↔上市转换」的公式改写判据已被否证 = `report_config` 域内**零可改写对象**（2026-08-06 B spec Task 7 实证，四条证据）**：①**`report_config` 无 `project_id` 列** —— 它是纯模板表、按 `applicable_standard` 分四象限存行，切 `template_type` 后自然读另一套行，**不存在「项目级公式需要跟着改写」这回事**；②全库 `report_config.formula` 中对那 14 条同义两码的引用 **= 0**（`ROW()` 引用集实测只覆盖 `BS-002~BS-128`/`CFS-*`/`CFSS-*`/`EQ-*`/`IMP-*`/`IS-001~IS-030` 等主表行，无一条命中 `BS-111`/`IS-055`/`EQ-030` 这类高编号行）；③**`wp_formula` 表全库 0 行**；④**附注侧根本没有 row_code 级公式** —— `disclosure_notes.table_data` 里 446 条 binding 的 `binding_id` 形态是「**章节号.行标签.列键**」（`五、11.分公司B.prior_year_value`），而 `note_source_resolvers`/`note_formula_derivation` 里的 `ROW()` 参数是**单元格坐标**（`R2C1`）不是报表行码 ⇒ 全库 `ROW('BS-xxx')` 形态的附注公式**不存在**。→ `_update_formula_references` 保留 `return 0` 是**正确**的，但必须返回原因码 `no_mapping_needed`（≠ `not_implemented`）并把上述四条写进 docstring、删掉「For now」措辞。**双清单仍要建**：它是判据真源 + 防「下个会话凭 row_name 相同就建映射」的护栏（立项已犯过一次）。
- **🔴🔴 `disclosure_notes` **没有 `section_number` 列**、也没有 `legacy_aliases` 列（2026-08-06 实测，B spec 通篇写错）**：真实列是 **`note_section`**（存章节号如 `八、9`、`四、研究开发支出`）+ `section_id`（slug）+ `section_title` + `locked_number`。故「改写 `section_id` + `section_number`」实为改写 `section_id` + **`note_section`**；「源侧 sid 追加进 `legacy_aliases`」只能落 `template_lineage` JSONB（本 spec 无迁移）。**且 `note_section` 与 `section_id` 大面积不同步** —— 抽样 12 条里 8 条 `section_id`/`level`/`parent_section_id` 全 NULL 而 `note_section` 有值 ⇒ 任何「按 `section_id` 驱动映射」的实现都必须对 `section_id IS NULL` 的存量行有明确处置（否则那批行静默不参与转换）。
- **🔴🔴 附注公式的 `binding_id` 内嵌章节号 ⇒ 改写 `note_section` 会让 446 条 binding 集体失联（2026-08-06 新查出，B spec 未登记的缺陷）**：形态 `{章节号}.{行标签}.{列键}`（`五、11.分公司B.prior_year_value` / `八、52.租赁负债净额.opening_balance`）。转换若只改 `note_section` 而不同步重写 `table_data` 里的 `binding_id`，公式绑定会指向不存在的章节号。→ Wave 3 落地时必须把 binding_id 重写纳入同一 savepoint，或显式登记为已知限制。
- **🔴🔴 「同义两码 vs 一码两义」两清单**不该互斥**，互斥断言会把正确设计判红（2026-08-06 定论，纠正 B spec 需求 3.8）**：14 条映射的 listed 目标码**全部**属「一码两义」——`BS-077` 在 listed 是「其中：优先股」而在 soe 是「▲应付手续费及佣金」，**正因为同一码在两侧是不同科目，才需要把 soe 的 `BS-111` 改写成 listed 的 `BS-077`**。正确不变量三条：①映射两侧码不得相同 ②**改写源**（正向=soe 码 / 反向=listed 码）不得落在该 scope 禁止清单里（否则 `resolve_target_row_code` 被禁止清单先短路 = 映射**静默永久失效**）③同 scope 内同源码不得映射到两个目标。→ 凡「A 清单与 B 清单不得有交集」这类断言，先问一句：交集是不是恰好就是该机制的工作原理？
- **🔴 变异检验的「前置校验先触发」会掩盖真正要验的断言（2026-08-06 实测，4 个变异全部因同一条无关原因打红）**：给 `SECTION_TITLE_ALIASES` 注入禁止对做变异时，因为构造的假条目 `evidence` 为空，**`evidence` 长度校验先抛** → 4 个变异的报错文本全是「evidence 过短」，而我真想验的「禁止对混入别名必红」「别名两侧归一后相等必红」两条**一次都没执行**。**判据：看变异打红的 message 是不是你预期的那一条**，只看「变红了」等于没做变异检验。正解 = 变异条目要把**除被变异字段外的所有字段填成合法值**。
- **🔴 「ANCHOR-MISS」是变异检验的第三种结果，既不是 RED 也不是守卫缺陷（2026-08-05 L0 Task 19 实证）**：变异脚本报锚点未命中时**变异根本没施加**，此时「测试仍绿」不能作为任何结论。本轮 M1/M2 两项 ANCHOR-MISS 的根因就是下一条（跨行锚点 + CRLF）。→ 变异脚本必须显式区分三态（RED / GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷），把 ANCHOR-MISS 当 GREEN 处理会漏掉守卫缺陷。
- **🔴🔴🔴 复原实测数据时用 ORM 给 JSONB 列赋 `json.dumps(dict)` 会写成**JSON 字符串标量**而非对象（2026-08-06 L0 实测踩，比「就地改嵌套不落库」更隐蔽）**：`wp.parsed_data = json.dumps(d)` → `jsonb_typeof` 变 `string`、`length` 由 75 变 83、内容被双重转义（`"{\"audit_checks\": []}"`）⇒ 下游一切 `->>` / `? 'key'` 全失效，而**脚本自报「[OK] restored」、`git status` 干净、测试全绿**。正解 = 直接赋 **dict**（`wp.parsed_data = d`）或走 `CAST(:v AS jsonb)`。**判复原是否成功必须查 `jsonb_typeof` + `md5(col::text)` 与基线比对，不能只看 `length` 或脚本退出码**（我第一次「修正」脚本因 `row.t` 取到整行元组而静默 abort，仍打印了诊断信息，误以为已修）。同族：已记的「`type_coerce` 配 `sa.text()` 在 asyncpg 下必失败」「JSONB 嵌套就地改不标脏」。
- **🔴 实测前必须抓「基线全文 + md5 + `jsonb_typeof`」三件，只记 `length` 不够（2026-08-06 实测）**：我只记了 `parsed_len=75` / `parsed_md5`，复原时才发现保存操作**新增了 5 个副产键**（`_version`/`changed_sheets_last_save`/`html_data`/`last_modified_at`/`last_modified_by`/`schema_version`）→ 只删 `html_data` 得 268 字节，与基线 75 字节不符。反推基线形态靠**全库同形记录**（`SELECT ... WHERE parsed_data::text LIKE '%audit_checks%' AND length(...)=75` 实测 315 条同形）—— 这是「取基线要多方交叉」的又一次兑现。
- **🔴 `SELECT jsonb_typeof(x) AS t` 后用 `row.t` 会取到**整行元组**（SQLAlchemy 2.0 的 `Row.t` 是已废弃的元组访问器，与列别名 `t` 撞名）**：表现为判定分支全错并 `abort`，且伴随 `SADeprecationWarning: Row.t attribute is deprecated`。列别名避开单字母 `t`/`c`/`_t`，或用 `row[0]` 索引取值。
- **🔴 Playwright MCP 的 `browser_run_code_unsafe` 有三条硬约束（2026-08-06 各踩一次）**：①**必须写成 `await (async (page) => {...})(page);` 形式**，写 `async (page) => {...}` 裸函数报 `ReferenceError: await is not defined`；②**函数体内禁用分号结尾的某些语句形态**（实测 `SyntaxError: Unexpected token ';'`），改写成不带尾分号的表达式即过；③**分步调用之间 session 会丢**（sessionStorage 里的 token 不跨调用保留）→ 登录 + 导航 + 点签 + 读取**必须压进同一个原子脚本**（memory 已记该铁律，本轮再证）。
- **🔴🔴 `.py`/`.ts` 工作树多为 CRLF，变异脚本与源码守卫的**跨行锚点必 MISS**（2026-08-05 一轮踩 4 次）**：`'if not rows:\n    # 注释'` 这类锚点在 CRLF 文件里匹配不到，`assert old in text` 直接把变异检验拦下（表现为「锚点未命中」而非静默）。正解 = 单行锚点，或按**行级**定位（`splitlines()` + 锚点行号 + 相对偏移找目标行），与行尾无关。同源：**含 `\n` 的字面量断言在 CRLF 源码上必失效** → 读文件后统一 `.replace(/\r\n/g, '\n')`。
- **🔴 `Path.write_text` 在 Windows 把 LF 转成 CRLF**（newline=None → os.linesep）→ 变异脚本出现「内容已还原但哈希不符」的假 DIRTY。改 `write_bytes` 字节级还原。
- **🔴🔴 `blockOf`/`extractFunctionBody` 取「声明后第一个 `{`」会命中**内联返回类型注解**（2026-08-05 再踩，memory 已记参数列表变体）**：`function f(): { a: X } {` 的第一个 `{` 是类型字面量，截出来的"函数体"是那段类型 → 后续断言全在无关文本上求值（表现为莫名打红，也可能静默通过）。正解 = 逐个候选 `{` 配对，取第一个**含语句特征**（`return`/`const`/`if`/`await`…）的块，并配「跳过类型注解」的 fixture 自检。
- **🔴🔴 `toContain('a.b.length')` 抓不住「删掉判断」这个核心变异（2026-08-05 变异检验实证）**：把 `if (unchecked.pending.length > 0)` 改成 `if (false)` 后该字符串仍在**返回消息的模板串**里 → 守卫全绿。判据必须断言**条件形态** `/if\s*\(\s*a\.b\.length\s*>\s*0\s*\)/`，并配一条「弱判据仍通过」的对照自检把差别钉死。同族：`"DELETE" in sql` 被列名 `is_deleted` 骗（正解 `\bDELETE\s+FROM\b`）。
- **🔴 「无效变异」会被误判成守卫缺陷，判缺陷前先确认该变异**真的改变了行为**（2026-08-05 四例）**：①`if (a < b)` 在 b 为 null 时 JS 恒 false ⇒ 只改外层判空或只改内层比较都不改变行为 ②黑名单语义下 `if not rows:` 分支删掉后仍返回全部规则 ③`if not batches:` 早退删掉后空列表进循环也返回 `[]`。有效变异要么改判据方向，要么改返回值本身（行级替换 `return all_rule_ids` → `return set()` 才打红）。
- **🔴 新增归档章节前必须 `archive_section_registry.list_all()` 查已占前缀**：`register` 对同 `order_prefix` 是**覆盖**语义（后注册顶掉先注册），撞号会静默删掉别人的章节。现已占用 `00/01/02/03/04/05/06/99`（05=AI 贡献明细，06=抽样记录汇总）。
- **🔴 数 spec 复选框必须用**行首锚定**正则，`re.findall(r'-\s\[ \]', s)` 会把正文数成任务（2026-08-05 实测）**：`sampling-compliance-closure` 的 Notes 里有一行踩坑说明引用了命令 `python -c "...'- [ ] 17. 共享件...`，未锚定时被数成第 26 个任务 → 得出「任务总数由 25 变 26」的错误结论并写进了 memory。正解 `^\s*-\s\[([ x~-])\]\s`（同时拿到四态计数）。**判「某 spec 是否满」不能只看 todo 数，要把每条未完成项的标题打出来肉眼确认它是真任务**。
- **🔴 判「重复归档副本能不能删」要逐文件哈希 + 看内容语义，别按目录名与文件大小（2026-08-05 实测）**：同名 evidence 目录里的 JSON 报告往往是**不同测量轮次**（并发数/请求数/项目 UUID 全不同），大小相近但内容实质不同 → 直觉上的「重复副本」其实是唯一留存的历史轮次。处置一律**移动 + 明确标注的子目录名**（`artifacts-superseded-run/`）而非删除，并在移动前后做哈希相等断言。
- **🔴 源码级守卫用裸 `in` 匹配类名/模型名会被同前缀符号骗（2026-08-05 实测）**：`'FinancialReport' not in src` 被 `FinancialReportDriftService` 命中 → Property 20 假红。一律 `re.search(rf"\b{name}\b", src)`（`\bFinancialReport\b` 对 `FinancialReportDriftService` **不**成立，后接 `D` 是词字符），并配「该长名确实在源码里」的反向自检，防词边界写法把整段判空。
- **🔴 `app.models.core.User` 的 NOT NULL 无默认列 = `username` / `email` / **`hashed_password`** / `role`**（2026-08-05 fixture 踩）：列名是 `hashed_password` **不是** `password_hash`，写错以 `TypeError: 'password_hash' is an invalid keyword argument` 在**构造时**炸（不是断言失败，易误判成实现问题）。写 ORM fixture 前先 `Model.__table__.columns` 过一遍。
- **🔴 `read_file` 对**本会话自己刚改过**的文件同样返回陈旧内容（2026-08-05 又踩）**：按它返回的版本写 `str_replace` 直接失配（磁盘上已有的方法在返回内容里不存在）。判磁盘真相一律 `python -c "open(p,encoding='utf-8').read()"` 或落 `tmp_*.py` dump 行号区间。
- **🔴 禁用 PowerShell `Set-Content`/`Get-Content` 操作 .vue/.md**（破坏 UTF-8 中文 + 加 BOM）→ 只用 `str_replace`/`fs_write`；批量改用 Python 显式 `encoding='utf-8'`
- **🔴 `python -c "..."` 里写 f-string 且内部含引号/`%` 格式化必被 PS 引号解析腌坏**（实测 `time.strftime("%m-%d")` 嵌在 f-string 里报 `SyntaxError: unterminated string literal`）→ 一行探针可以用 `python -c`，**带 f-string/嵌套引号的一律 `fs_write` 落 `tmp_*.py` 再 `python tmp_x.py`**（用完即删）；PS 里用 `%` 占位符格式化替代 f-string 可绕过
- **🔴🔴 `get_diagnostics` 查不出「漏 import」（2026-08-04 一天内踩两次，Python 与 TS 各一次）**：后端加 `datetime.now(timezone.utc)` 而顶层只 `from datetime import date` / 前端 composable 加 `watch(...)` 而 import 只有 `ref, computed` —— **两次都返回 No diagnostics**，后端要到运行时 NameError、前端要到运行时才炸。→ **新增引用必须用「真实执行」收尾**：后端 `python -c "import app.routers.X"`（需 `sys.path.insert(0,'backend')`），前端跑一次覆盖该文件的 vitest + `curl` Vite transform；或直接 `python` 读文件前 30 行确认 import 清单。
- **🔴🔴 同一个 `row_code` 在不同准则下 `row_name` 可能是完全不同的科目（2026-08-04 K0 实证，比「同名不同 row_code」更毒）**：`BS-075` 在 `listed_*` 下 row_name = **「股本」**，在 `soe_*` 下 = 「其他应付款」（formula 均 NULL）。→ 「按 row_name 匹配」不只是会撞同名行，**切准则时会拿到另一个科目**。已知同族：`BS-014`/`BS-017`（K2）。**判「某科目该用哪个 row_code」必须四准则全查 + 看 formula 是否为 NULL** —— 其他应付款有公式的行是 **`BS-050` = `TB('2241')+TB('2231')`**（`2231` 应付利息按财会[2018]15 号并入其他应付款列报，只取 2241 会漏一块）。
- **🔴 判「一批失败是否预存在」的可靠做法 = 只换那一个数据文件跑同一组测试（2026-08-04 K0 实证，替代被禁的 `git stash`）**：`git show HEAD:<path>` 取原版 → 写盘 → 跑测试集收 `FAILED` 集合 → 换回自己的版本 → 再跑一遍 → 求差集。本轮 26 个失败两侧**逐条相同**（新增 0/消失 0）⇒ 与本次改动无关。比「看着像别人的活」硬得多，且只动一个文件、`finally` 里复原，不会波及并发会话。
- **🔴 前端守卫读 python 常量时禁用 `\)\n` 之类行尾正则（2026-08-04 K0 踩）**：python 隐式拼接常量 `NAME = (\n "a"\n "b"\n)` 用 `/NAME = \(\s*([\s\S]*?)\)\n/` 抽会因 CRLF/LF 差异**静默不命中**（表现为「后端未找到常量」）。正解 = 按 **ASCII 括号配对**扫（源文字里的「（）」是全角、不参与配对），并配一条「对不存在的常量必须 throw」的 helper 自检防解析失效变成空转。
- **🔴 反向自检要盯住**常量本身**，不能只断言从源文件读出的值（2026-08-04 K0 变异检验抓出）**：`test_..._must_differ` 只比 `ws5[coord].value` 与 `ws6[coord].value`，把常量表里的 label 改错**不打红**（断言根本没读常量）→ 必须先 `assert (decl5, decl6) == (v5, v6)` 把常量与源模板绑死，再断业务不变式。**每写完一个守卫都要真做一次变异检验**（改一字看是否变红），别只看「全绿」。
- **🔴🔴 `openpyxl` 的 `wb.sheetnames` 含隐藏 sheet，判「某 sheet 是否属于底稿集合」必须查 `wb[s].sheet_state`（2026-08-02 E0 实证，平台级 P0 未修）**：`backend/scripts/analyze/analyze_wp_templates.py` L625-626 `for sheet_name in wb.sheetnames:` **无可见性过滤** → `workpaper_template_analysis.json` → `seed_workpaper_sheet_classification.py` → `workpaper_sheet_classification` → render-config sheets → **前端页签**，全链一处不过滤。**实测影响面**：351 模板 / 2722 sheet 中 **247 张隐藏**（分布 180 个模板）；去掉 4 个「此处隐藏别处可见」的歧义名后 66 个 hidden-only 名对应 **353 行 / 228 个 wp_code** 是本不该出现的页签（分类表共 4640 行）。**✅ E0 已按 A 方案收口（2026-08-02，用户裁决，未 commit）**：用平台既有机制 `wp_code_overrides.json` 的 **`skip`**（不动 DB、不动扫描器）—— E0 十张隐藏 sheet 里另 7 张早已 skip，本次补齐最后 3 张（`回函情况汇编`/`银行函证其他信息核对表E0-5`/`邮件传真回函核对记录F1-12`）。**🔴 必须按完整 sheet_name 标 skip 不能按尾码** —— `wp_render_config` L708 精确匹配 / **L722 按 `_SHEET_CODE_RE` 尾码匹配**，把 `E0-5` 标 skip 会连真实的 `应付银行承兑汇票发函记录表E0-5` 一起杀掉。`refresh_wp_code_overrides()` 在 render-config 每次请求开头调 → **改 JSON 免重启**（推翻「改后端 json 不生效」的一般结论，此文件是热重载的）。**实测**（真实后端 + 项目 `2aa00f57`/wp `170057eb`）：sheets 由 13 → **10**，与 Excel 可见 sheet 逐字一致、顺序一致，三张已剔除。守卫 `test_e0_hidden_sheets_skipped.py`（openpyxl `sheet_state` 为裁决者，复刻三段 skip 判定，双向断言「隐藏必 skip / 可见必不 skip」+ 底稿目录 9 项 + 数量锚点反向自检）。**B 方案（平台级 353 行 / 228 wp_code）仍未做**，须另立 spec。**顺带修掉一个失效守卫（后端基线 −232 红）**：`test_render_config_smoke.test_wp_code_override_returns_nonempty_component_type` 的 `assert expected_ct != "skip"`（2026-06-18 写下，理由「已注册底稿应有专用组件」）在 `skip` 成为一等值后**对 232 个条目恒红、零信号** —— `skip` 就在 `VALID_COMPONENT_TYPES` 白名单里且被 L708/722/727 消费 → 改为白名单断言，`test_render_config_smoke.py` **235 failed → 1706 passed / 0 failed**。**该文件另 37 个失败属预存在**（`test_wp_classification_service` 全类派生返 `d2-accounts-receivable` / `test_e_cycle_*` 的 E0-1·E0-2 期望 `d-form-table` 而实为 `confirmation-*` / E0·D0 `confirmation-hub` / `test_e0_send_list_columns` 的 E0-4 列 type），与本次三个 sheet 名无关。**两条配套判据**：①WPS/Excel 页签栏只显示可见 sheet，**且页签栏会被右侧截断 → 「看不到」≠「没有」**，用户截图不能当唯一证据，须 `sheet_state` 实证；②`.kiro/specs/workpaper-html-renderer/workpaper_template_analysis.json` **已随 spec 归档不存在**，判定真源改用 `workpaper_sheet_classification` 活体表。
- **🔴🔴 `*_cycle_specs.py` 的 `row_code` 大面积错位（2026-08-03 首次对账 `report_config`，此前只对过兜底码）**：18 个声明文件里查出 **16 处指向完全无关的报表行** —— M 循环 **9/10 错**（M2 声明 `BS-070` 实为**负债合计** / M8 声明 `BS-076` 实为「其他权益工具 / 其中：应付股利」/ M7 声明 `BS-075` 实为「其他应付款 / 股本」）、**L3~L8 整体偏移一位**（L3→`BS-060` 是节标题「非流动负债：」、L4→`BS-061` 是长期借款、L7→`BS-066` 是递延收益即 K7 的行、L8→`IS-009` 是利息收入）、I5→`BS-039` 是**资产总计**、I6→`IS-007` 是**财务费用**、N2→`BS-052` 是一年内到期的非流动负债。**其中 4 条是活的数字级错误**（该行有公式且码在科目表里存在 → 单槽规格下第③层会静默返回错科目）：M1 指的 `BS-048` 公式 `TB('2211')` 应付职工薪酬 / I6 指的 `IS-007` 公式 `TB('6603')` 财务费用 / L6 指的 `BS-065` 公式 `TB('2801')` 预计负债（K5 的科目）/ N2 指的 `BS-052` 公式 `TB('2501')` 长期借款。已全部按 DB 对账改正 + 新建守卫 `backend/tests/four_table/test_cycle_specs_row_code_evidence.py`（24 例：证据表冻结 `row_code`↔行名 + 16 条改正值防回退 + 「同一 row_code 不得被两循环认领」+ 双向自检）。**正确落点**：M1`BS-055` M2`BS-081` M3`BS-084` M4`BS-083` M5`BS-087` M6`BS-088` M7`BS-086` M8`BS-124` M9`BS-085` M10`BS-082` / I5`BS-037` I6`IS-006` / L3`BS-061` L4`BS-062` L6`None`（专项应付款在 BS 无独立行）L7`BS-068` L8`IS-007` / N2`BS-049`。
- **🔴🔴 跨 spec 接缝：`report_config` 错码由 `report-config-account-code-integrity` spec 的**迁移 V138**统一修（并发会话 2026-08-03 立，0/12）**，其 13 行错码清单含本会话独立查出的 5 行权益类且修正值吻合（`BS-082 4003→4401` / `BS-084 4005→4201` / `BS-085 4102→4003` / `BS-086 4103→4301` / `EQ-015 4201→4301`），另加 7 行（`BS-033 1703→1704` / `IMP-008 1502→1505` / 置 NULL 的 `BS-090`·`BS-043`·`BS-053`·`BS-013`·`CFSS-016`·`IMP-017`）；该 spec 还记录 **V136 从未生效**（WHERE 从不命中 + 前提错，真正写 `4103` 的是 `BS-086`）。→ **V138 落地后必须清空 `test_cycle_specs_row_code_evidence._WRONG_FORMULA_ROWS` 并移除 5 个 `trust_report_config=False`**（M3/M7/M9/M10/I6）—— 那是针对错码的**临时**防护，数据改对后继续关层③会让「客户科目表缺该科目」的项目白白取不到数。**不清空不会打红**（静态冻结值不连库）→ 已加断言 `test_wrong_formula_rows_carry_v138_seam_note` 强制该说明存在，防静默过期。
- **🔴🔴 `report_config` 权益类另有 5 处错码（2026-08-03 新发现，与已记录的 `BS-022/025/026` 偏移、`IS-016↔017` 互换同族）**：`BS-082 其他权益工具=TB('4003')`（4003 实为**其他综合收益**）/ `BS-085 其他综合收益=TB('4102')`（**4102 全库两张科目表都不存在**）/ `BS-086 专项储备=TB('4103')`（4103 双侧都是**本年利润**）/ `BS-084 减：库存股=TB('4005')`（不存在，库存股是 `4201`）/ `BS-090 少数股东权益=TB('4201')`（4201 实为**库存股**）+ `EQ-015 （五）专项储备` 同款。另 `BS-052 一年内到期的非流动负债=TB('2501')`（2501 是长期借款）、`BS-053 其他流动负债=TB('2901')`（2901 是递延所得税负债）也是错码。**`account_chart` 的 `source='client'` 侧才是权威**（实证 4001 实收资本×8 / 4002 资本公积×7 / 4003 其他综合收益×8 / 4101 盈余公积×8 / 4103 本年利润×8 / 4104 利润分配×8 / 4201 库存股×5 / 4301 专项储备×4 / 4401 其他权益工具×5）。→ **`SemanticAccountSpec` 新增 `trust_report_config: bool = True`**，对这些行显式声明 `False`（M3/M7/M9/M10/I6 共 5 个）：`row_code` 仍如实填（溯源展示 + `conflicts` 检测靠它），但**不许它参与定位**。**`TB('4103')` 最危险** —— 4103 确实存在（本年利润），第③层「码必须在本项目科目表里存在」那道闸**拦不住它**，只有显式关闭才行。守卫双向锁死：引用错码行必须关层③ + **关层③必须在 `_WRONG_FORMULA_ROWS` 登记理由**（防当万能开关用，关掉是有代价的 —— 客户科目表缺该科目的项目会彻底取不到数）。
- **🔴 判「某 render 是否真消费 `resolve_semantic_accounts`」必须变量名无关（2026-08-03 二次实证）**：先抓 `(\w+) = await resolve_semantic_accounts` 再数该变量被 `.`/`[` 读取次数。按 `accounts.` grep 会**假阴性** —— G6/G7 的 `_service` 子策略赋值给 `result`，曾被误判成死代码。准确基线：**真消费 28**（G 16 / H 10 / E1 1 / M8 1），**死代码 0 / 仅 import 0**（上一轮清理是干净的），D·F·I·J·K·L·N **全为 0**。spec 里「I 循环全部已迁移」「M3~M10 已迁移 7 个」两处声称**不成立**。
- **🔴 `_h8_right_of_use_assets._build_h8_detail_prefill` 曾遗留硬编码 `1901`（2026-08-03 修）**：render 主路径已改语义定位，但这个给 H8-2 明细表种子预填的函数漏改 → 一直在拿**待处理财产损溢**（活体期末全 0.00 → 表现为「恒空」而非「数字错」，更隐蔽）。原「>=6 位且名称含折旧/摊销/减值则跳过」的备抵判定在新模型下也失效（累计折旧是独立一级码 `1642`，不是 `190101` 式子科目）。**教训：改完 render 主路径要 grep 该文件全部硬编码码**，`backend/scripts/diagnose/audit_render_hardcoded_account_codes.py --scan/--reconcile` 就是为此建的（59 个策略 / 117 处硬编码码，`--reconcile` 连库做一码两义 + 跨项目漂移 + 仅客户表 + 两表全无四类分类）。同批查出 `_m8_general_risk_reserve.py` 硬编码 `4302` **全库两张科目表都不存在** → `tb_snapshot` 恒空（该文件 docstring 还写着「科目4104」，而 4104 是**利润分配**，两者都错），已改走 `M8_SPEC` 语义定位。
- **🔴🔴 平台级 P0：裸 `v-if` 插进宿主 sheet 分发链中间 = 后续 `v-else-if` 全成死分支（2026-08-03 浏览器实测，已修 11 宿主 / 140 个分支）**：`HiFourTableSourcePanel` 被写成 `<Panel v-if="props.htmlData?.hi_extraction_enabled">` 插在 `<XTabIndex v-if=currentSheet…>` / `<CycleTabProcedure v-else-if=…>` 与 `<XTabAdjudication v-else-if=…>` 之间 → `v-if` 开**新链**，flag 为真时面板胜出、**它之后按 `currentSheet` 分发的全部 `v-else-if` 永不渲染**。波及 **H5/H6/H8/H9/H10 + I1~I6 共 11 个宿主**（`GtH7BiologicalAssets.vue` 一直用 `<template v-else-if>` 是唯一正确的范式）；`HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` **2026-08-02 翻 True 后这 12 个循环的审定表/披露 Tab/各明细表当天起全部打不开**。**Vue 编译器对此不报错（语法完全合法）**，`get_diagnostics` 零诊断 / Vite transform 200 / vitest 不覆盖模板分发 → 四层全绿，**只有浏览器打开对应 Tab 才暴露**（症状：页面只剩工具栏+面板+编制指导，`sheetName`/`currentSheet`/`currentMode` 全正确、零 console error）。修法 = `<template v-else-if="currentSheet === 'X-1'">` 包住「面板 + 该 sheet 内容」；幂等脚本 `backend/scripts/fix/fix_hi_source_panel_vif_chain.py`（`--check` 已归零）+ 平台守卫 `components/workpaper/__tests__/hostSheetDispatchChain.spec.ts`。**🔴 守卫判据必须收窄三轮才可用**：①「同缩进 `v-if` 前有链后有 `v-else-if`」→ **190 个误报**（表格列内 `<el-input v-if="isEditable(row)">`/`<span v-else-if="!row.isSection">` 同缩进但**不同父节点**，缩进不等于兄弟）②加「只看条件含 `currentSheet` 的链」→ 10 个 ③加「**紧前同级兄弟必须是 `v-else-if`**（不能是 `v-if`）」→ 归零 —— 那 10 个是 G8~G14/N2~N5 的 **OnlyOffice 双模式短路**（`<div v-if="isHtmlSheet && currentSheet !== 'N4'">工具栏</div>` + `<GtOnlyOfficeSheet v-if="…onlyoffice">`），后者是**合法链首**、前者只是恰好提到 `currentSheet` 的独立条件块 → **判「是否在链中间」不能只看前一个兄弟提到什么变量，必须看它是不是 `v-else-if`**。
- **🔴 三类「Vite 200 + vitest + get_diagnostics 全绿，只有浏览器挂载才暴露」的缺陷（2026-07-31 H7 重建实测各踩一次）**：①**`fmtAmount` 是 store 成员**（`useDisplayPrefsStore().fmtAmount`）**不是** `@/stores/displayPrefs` 的模块命名导出 → 写成 `import { fmtAmount } from '@/stores/displayPrefs'` 在**运行时**抛 `does not provide an export named 'fmtAmount'`，整个组件不渲染（`ErrorBoundary` 只在 console 留一条）。模块级命名导出在 `@/utils/formatters`，但**平台单一真源是 store 成员**（带单位/showZero 偏好）②**宿主没有 `@save` 处理器时组件只 `emit('save')` = 录入只在内存**（H7 循环全部 Tab 都自持久化，宿主无统一保存器）→ 实测自动同步已写进附注但 `checklist_responses` 一条都没有，刷新即丢 ③**`watch(props.allResponses)` 重新 hydrate 会用宿主旧值覆盖刚录入的数据**（宿主 map 异步加载、自持久化后未必刷新）→ 改本地镜像 + `onMounted` 自取。**新建披露组件必查这三条**，且判「录入是否真落库」只能查 `checklist_responses`，不能看界面显示值。
- **🔴🔴 平台级 P0：`wp_grid_extract.strip_standard_header` 曾把**列头行**当编制信息行删掉（2026-08-02 修，影响 503 张 sheet）**：旧判据是「整行文本包含 致同/被审计单位/编制人/编制日/截止日/复核人」子串命中 + 取 rows1..7 最后一个命中行 → 列头含**「报表截止日」（内含「截止日」）**的表整个列头行连同上方被删。后果：E0-3/E0-4 前端只剩无表头空网格（E0-4 实测只显示源模板残留的两个 0）、E0-5/E0-6 `cells=0` 完全空白；`get_diagnostics`/vitest 全绿，只有拉 render-config 或打开页面才发现。修法 = 判据改「**关键词锚定标签**（格以关键词**开头**且后面还有分隔符/取值 → `报表截止日` 不算、裸 `索引号` 不算）+ 短标签形态（无换行/≤30 字/冒号在第 1~12 字符）**过半**」。**🔴 关键词表不得扩充**（加过 `页次/索引号/会计期间/复核日` → 83 张 sheet 反而多删 1~3 行）：关键词相同 ⇒ 新判据是旧判据真子集 ⇒ 结构性保证「只少删不多删」，守卫 `test_prep_keywords_are_identical_to_legacy_set` 钉死。**改这个函数必须重跑全量 characterization**（351 模板 × 2722 sheet 逐 sheet 比 old/new skip，断言 `new <= old` 且复活行中无一行仍被判为编制信息行）。**注意 `header_rows` 被 strip 硬编码回 1**（两级表头 sheet 在 skip>0 时会被压成 1，属预存在遗留）。
- **🔴 `wp_render_schema/generated/` 运行时**从不加载**（2026-08-02 实证）**：`WpRenderSchemaService._SCHEMA_DIR` = `backend/data/ledger_adapters/wp_render_schema/`（无 `generated/`），且 `backend/app/**` 全文无任何读 `generated/` 的代码 → 只有 `{wp_code}.yaml` / `{prefix}-template.yaml` / `C-{wp_code}-disclosure.yaml` / pattern 泛型才生效。实测 E0 无 `E0.yaml` 也无 `E-template.yaml` → render-config 里 **20 个 E0 sheet 的 `schema` 全为 null**，归档 spec `e0-send-list-components`（12/12）审定的四张发函清单 16 列全是 **dead config**。**判「schema 有没有生效」看 render-config 的 `sheets[].schema` 是否为 null，别看 yaml 文件写没写**；往 `_SCHEMA_DIR` 放文件会让整册 sheet 同时拿到 schema（波及 `sheet_type`/`field_sources`/auto-fill），属需逐 sheet 验证的改动。
- **🔴 E0-1 对四张发函清单的取数键各不相同，且 E0-4 的品种权威列是 A 列不是 O 列（2026-08-02 源模板公式实证）**：`E0-1!F8` 逐字 —— E0-3 `SUMIF(E0-3!$G:$G, E0-1!$E, E0-3!$K:$K)`（银行账号→账户余额（原币））/ **E0-4 `SUMIFS(E0-4!$I:$I, E0-4!$A:$A, E0-1!$D, E0-4!$G:$G, E0-1!$E)`（所属科目+借款账号→余额）** / E0-5 `SUMIF(E0-5!$A:$A, E0-1!$B, E0-5!$G:$G)`（索引号→票面金额，**一函多票求和**）/ E0-6 `SUMIFS(E0-6!$H:$H, …$A:$A, E0-1!$B, …$D:$D, E0-1!$E)`（索引号+产品名称→产品净值）。→ E0-4 品种分流读 **A 列「所属科目」**（取值域 `短期借款`/`长期借款`，「一年内到期的长期借款」并入长期借款，依据 `回函情况汇编!V9` 表头），**O 列「借款类型」在整册零公式消费方 + 零数据有效性 + 零示例值** → 不得给它臆造枚举（改造前 manifest/E0.yaml 写的 4 项枚举是把 A 列语义抄了一份，已撤回为 text）。**E0-5/E0-6 源模板没有「是否函证」列**（10/11 列实证），套「是否函证=是」门控会让这两品种恒产出 0 行。守卫 `test_e0_send_list_columns.py` 的三向锁死（源 xlsx 公式 ↔ manifest ↔ E0.yaml）+ 反向自检（全册不得引用 E0-4 的 O 列）。
- **🔴 `fetchWorkpaperHtmlRows(projectId, wpCode, format)` 有两个静默失效点（2026-08-02 E0 实证）**：①按 `wp-id-by-code` 解析 wp_code —— **多 sheet 工作簿的 sheet 不是独立 wp_code**（5 个项目里 3 个 `wp_index` 只有 `E0`、没有 `E0-4`）→ 直接返 null；②按 `hd._format === format` 匹配，而 `d-form-table` 的 **grid 载荷根本没有 `_format` 键**（keys 只有 cells/col_widths/column_meta/header_rows/max_col/max_row/merged_cells/project_context）→ rows 恒空。故「E0 清单→E0-1 带入」三处断点叠加（+ 列头被删），**从来没有工作过**；改 `importE0ListsToSummary` 的取数口径前必须先解这两处，否则仍是 dead code。

- **🔴🔴 `semantic_account_resolver` 的「报表公式兜底层（层③）」只对**单槽**规格生效（2026-08-02 E1 真实 DB 实测修复，平台级 P0）**：层③给的是**整条报表行**的科目集（`BS-002 货币资金 = TB('1001')+TB('1002')+TB('1012')`），单槽规格下成立，**多槽规格下会把整行金额塞进某个子项槽**。实测后果：①E1 的 `finance_co`/`digital`（准则解释15号「可增设」，`fallback=()`）各自拿到全部三码 → `finance_co_closing == digital_closing == total_closing`，一点「带入未审数」就把货币资金全额填进这两行 ②项目 `2aa00f57` 无「库存现金」→ `cash` 拿到 `['1002','1012']` → `total = cash+bank+other` 双算，**8,935,072.24 vs 真值 4,467,536.12（虚增一倍）**。**同款风险在 G/H 是潜伏态**（层③排在层④之前 → 槽自有兜底码用不上）：G1/G10 的 `derivative` 会拿原值科目、G4/G7 的 `provision` 与 H3 的 `accum_dep`/`accum_amort`/`impairment` 会拿到**原值科目码**（备抵 == 原值）。修法 = `allow_report_config_tier = len(spec.slots) == 1`。守卫在 `test_semantic_account_resolver.py`(4 条，含「单槽仍生效」反向自检) + `test_e1_account_scope.py::TestMultiSlotReportConfigFallback`(4 条，含「复现旧行为必产出 8,935,072.24」反向自检)。**判「多槽 spec 取数对不对」必须真实 DB 直跑，自造 fixture 与错误假设同构测不出来**。
- **🔴 `parent_check` 类「码→槽」映射一律 `setdefault` 不用赋值**：多个槽可能声明同一科目码，无条件赋值会让**最后一个槽**覆盖 `slot` 标签（E1 实测三个码全被标成 `digital`，溯源面板归属完全错）。
- **🔴 同一份 `html_data` 的 render 输出分两层放，逐个 key 都要核实位置（2026-08-02 E1 实测）**：`tb_source_codes` 在 **`html_data.project_context.tb_source_codes`**（各循环 render 写 `project_context["tb_source_codes"] = ...`，这样每个 sheet 都拿得到），而 `adjudication_prefill`/`restricted_prefill`/`tb_values`/`four_table_prefill` **在 `html_data` 顶层**。组件读错层 → 恒 `undefined` → 面板/按钮静默失效（又一个 dead output；`get_diagnostics`/Vite/vitest 全绿，**只有浏览器打开才发现**）。新接溯源面板一律写「`project_context` 优先、顶层兼容」。
- **🔴 变体专属的勾稽项必须按 variant 门控（2026-08-02 E1 实测）**：源模板 B16「主表合计 = 原币表人民币合计」只在上市披露 sheet（外币原币表国企版没有），组件无条件传 `fxRows` → 国企侧 `foreignCurrencyRows` 返回**未渲染的默认分组骨架**（金额全 0）→ 拿 0 比主表合计 → **假「不一致」**。守卫要含反向自检（传骨架必产 error，证明门控必要）+ 源码级断言门控存在。
- **🔴🔴 `semantic_account_resolver` 是新循环科目定位的首选，`report_line_accounts` 降为次选（2026-08-01 并发会话建，`four_table/semantic_account_resolver.py` + `g_cycle_specs.py`/`e_cycle_specs.py`/`h3_account_scope.py` 已消费）**：`report_line_accounts` 隐含假设「标准码在各项目一致且客户科目能反解到它」，DB 实证不成立 —— ①`account_mapping` 同一原始码在不同项目映射到**不同标准码**（`1532`→1532(3项目) vs →1541(2项目)）②`account_chart source='standard'` 本身各项目不一致（4 项目有 `1519` / 2 项目只到 `1507` / 4 项目整族没有；`2aa00f57` 只有 58 个标准科目）③客户科目表里压根没有 `1504~1507`，唯一有投资类科目的项目用旧准则 `1501`/`1503`。→ **按科目名在该项目自己的 `account_chart` 里定位**（客户表优先于标准表 → `report_config` 码但要求本项目确实存在 → 调用方兜底码 → 返空），`report_config` **降级为提示 + 冲突检测**（`conflicts` 供溯源面板告警；实证它有 4 行错码：`BS-022`/`BS-025`/`BS-026` 连续偏移一位、`IS-016`↔`IS-017` 整整互换）。**名称匹配只在一级科目层做**（子科目名很随意，一级名规范）。**旧准则拆分不自动化**（`1503 可供出售金融资产` 按 SPPI 拆三处是会计判断）→ 进 `unmapped_candidates` 提示人工映射。配套 `four_table/tb_query.py`（`fetch_tb_subtree` 宽取整棵子树含父行**不筛叶子**，父行给「叶子和==父额」勾稽用；`fetch_trial_balance_amounts` 并列展示两口径）。**槽未命中时 `found=False` + `codes=[]`，调用方必须显示「本项目无此科目」而不是取 0**。
- **🔴 「按需增设」的会计项目不得给兜底科目码（2026-08-01 E1 实证）**：准则解释15号的「存放财务公司款项」（货币资金项下增设单独列示）与「数字货币」（增设二级科目）**没有一级标准科目** —— E1 公式预设原写 `TB('1502')` 而 `1502` 实为**持有至到期投资减值准备**（活体全库仅 1 行/1 项目）。正解 = 语义槽 `fallback_standard_codes=()` + 预设写 `PLACEHOLDER`，由按科目名的逐项目定位决定有无。**写死一个码「静默产出 0」比返空更坏**（掩盖「本项目无此科目」这一事实）。
- **🔴 附注章节号在两份模板间会撞号，「章节号 → 变体」不可推导（2026-08-02 实测）**：20 个章节号同时存在于 `note_template_listed.json` 与 `note_template_soe.json`，其中 **13 个标题不同** —— `八、1` listed = 政府补助 / soe = **货币资金**；`五、42` listed = 其他应付款；`五、82` listed = 所有权或使用权受到限制的资产（soe 对应 `八、93`）。故凡「按 section_number 查模板」的逻辑必须**先由 `current_standard` 前缀（`listed*`/`soe*`）定变体**，`source_template` 只作兜底（memory 已记它有错配：项目 `2aa00f57` 的 `五、1` 记成 `soe`）。查错模板 → 行集/段边界全错。
- **✅ 附注同步已支持**行级合并**（2026-08-02 落地，spec `disclosure-note-row-level-merge` 14/14）**：推共享表时在 `sub_table_data._row_scope` 声明 `{表名:{owner_row_code}}` 即只替换自己那一段，段外行原样保留；不声明仍走原表级覆盖（零回归）。**平台守卫 `disclosureSharedTableRowScope.spec.ts` 强制「推共享表必带 `_row_scope`」**（`WHOLE_TABLE_OWNER` 豁免「单一 owner 独占整张表」如 N1 递延所得税两表）。以下为历史背景：
- **🔴🔴（已修，保留背景）附注同步的合并粒度原本是**表级**（按子表名浅合并），故「同一张表内按科目分段」的跨循环共享表**无法分段推送**（2026-08-01 E1 外币章节实证）**：`wp_disclosure_sync_service` 注释原文「按子表 key 浅合并，同名 key 覆盖，未推送的 key 保留」→ 单个循环推该表会**整表覆盖**、清掉他循环段落及审计师在附注模块手填的数据。「外币货币性项目」（listed `五、73` / soe `八、92`）就是这种表：一张表内分 货币资金/应收账款/短期借款/长期借款/应付债券 各段，每段下按币种列「其中：」明细。**现存的跨循环共享表都是靠「恰好各推不同子表」绕过的**（H4→H2 工程物资、H6→H1 固定资产清理），一旦「同一张表内分段」就无解 → 需平台级**行级合并**能力（载荷声明「本次只负责这些行」，未声明的行保留），值得独立 spec（收益覆盖 D2/K/L 等所有想接外币章节的循环）。E1 已按「宁缺勿造」只补 columns/guidance（`rows=None`）+ guidance 如实写明「尚未接自动推送」及原因，并加守卫钉死「全前端不得有 map 推向该章节」。**判定某章节有无 pusher 的三个证据**：registry 有无该章节 / 有无 `*NoteSectionMap.ts` 指向它 / 代码注释里的历史误映射记录。
- **🔴 「预聚合」是有损表示，凡下游可改归属的分类结果都必须下发逐项明细（2026-08-01 E1 受限资金实证）**：首版 render 下发 `buckets{key:{opening,closing,codes}}` + `unclassified[]`，写前端合并时发现**审计师把某叶子改归到别的类别后，原桶余额无法重算**（载荷没给逐叶子金额）。正解 = 下发扁平 `leaves[{code,name,opening,closing,slot,autoBucket}]`，聚合全在前端按「人工归类 > 自动分类」做，两侧余额都能精确重算。守卫要断言 `'buckets' not in payload`。**同款风险存在于任何「后端分类 + 前端可改判」的场景**（G7 投资分类桶 / F2 存货分类 / K1 款项性质）。
- **🔴 「境外」类关键字必须叠共现要求，否则会改变披露结论（2026-08-01 E1）**：源模板 R21 是「放在境外**且资金汇回受到限制**的款项」，光凭「境外」二字归类会把香港子公司基本户判成受限款项。`E1RestrictedBucket.require_any_of=('受限','限制','冻结','管制','汇回','不可')`；且「境外」桶排序**必须先于**「质押」桶（否则 `境外冻结存款` 被「冻结」抢走）；「质押」桶不放裸「保证」（`投标保证金` 不是定期/通知存款，应落兜底桶）。
- **🔴 跨 sheet 聚合键是跨 spec 数据契约，改键 = 断链 + 丢已持久化数据（2026-08-01 E1 险踩）**：`E1-adj-total-1001/1002/1012` 被归档 spec 明确登记为「写出…供报表/附注引用」，`backend/app/routers/wp_formula.py` 亦在引用，既有项目已按此键持久化 → 一度想改成语义槽名 `E1-adj-total-cash` 更"好看"，发现后改回并加守卫钉死形态 `^E1-adj-total-\d{4}$`。**重构前先 grep 键名的全部引用方（含归档 spec 文档与后端 router）**。
- **🔴 幂等脚本的校验器不能对整块 `json.dumps` 做「不得出现 xxx」断言（2026-08-01 E1 实证）**：`description`/`notes` 里会**如实写出被纠正的反例**（「原 `TB_SUM('1001~1012')` 会虚增」「改造前本块引用 `TB('1502')`」）→ 整块扫描把说明文字数成真实引用而误报，`--apply` 被自己的校验拒绝。正解 = 只扫**语义字段**（`formula`/`formula_type`/`account_codes`/`applies_when`）+ 反向自检。同 `stripComments()` 一类坑。**且 sheet 名纠正要同时改 `block.sheet` 与公式实参**（`PREV('E1','审定表E1-1',…)`，首版只改前者，靠守卫抓出）。
- **🔴 `prefill_formula_mapping.json` 的字段名是 `sheet` 不是 `sheet_name`**（2026-08-01 探针查错字段导致误判「全部块 sheet_name=None」）。另 `applies_when` 在该文件里**无任何消费方 = 死字段**（`chain_orchestrator` 的同名字段读的是 `project_flags` 里的 flag 名，属 B60 平台字段机制）——`tb_account_exists:CODE` 形态所声称的「无该科目则隐藏整 sheet」**从未实现**，只存在于 JSON 与归档 spec 文档里。
- **🔴 全零账户过滤会削弱完整性程序（2026-08-01 E1 实证）**：E1 原实现把四项金额全零的叶子一律过滤，连**银行账户清单**（供 E1-10「已开立银行账户清单核对」）也过滤 → 「本年新开立但期末为 0」的账户被抹掉，而体外账户/未入账账户正是货币资金舞弊常见切入点。正解 = 金额明细过滤、**账户清单不过滤**（活体 `df5b8403` 的 `1002` 有 50+ 个零余额账户）。但「待归类科目」面板要过滤全零叶子（否则被空壳分支户淹没），金额为 0 不破坏求和恒等式。
- **🔴 第四种「只有浏览器挂载才暴露」：`<script setup>` 里 `watch(...)` 引用后面才声明的 `const` = TDZ ReferenceError，整个组件挂不上（2026-08-01 E1 实证）**：`E1TabDisclosure.vue` 的 `watch([disclosureRows,restrictedRows,noteText,variant])` 在 L62，四个 const 分别在 L83/167/452/493 → setup 期直接抛错，**手动同步按钮与自动同步一起废掉**，而 `get_diagnostics` **零诊断**、Vite transform 200、vitest 不覆盖该分支。比既有「immediate watch 求值触发 TDZ」（`drValues` 那条）更强：**根本不需要 immediate，watch 的依赖数组本身就在 setup 期求值**。→ 守卫范式：源码级断言「每个 `watch(` 引用的顶层 const 声明行号 < watch 行号」+ 反向自检。**凡在文件顶部区域看到 `watch(` 就要核对被监听标识符的声明位置**。
- **🔴 `buildXColumns` 必须零入参可调**：`disclosureColumnsCoverage.spec.ts` 的 sweep 用**空入参**调用所有 `build*Columns`，参数化 builder 缺省返回不完整列集（如只剩「项目 + 合计」两列且都无 group）会被判「flat/group 未表态」→ 给默认入参（H7 `buildH7ListedColumns(cats = createDefaultH7Categories())`），或把参数化版本改名为 `xColumnsFor(...)` 只对外导出零参包装。
- **🔴 `npx vitest run -t ""` 会把全部用例判 skipped**（2026-08-01 实测：9004 skipped / 0 passed，JSON 里 `numPassedTests:0` 但 `numTotalTests:9004`，看着像跑通实为零断言执行）；且**位置参数是子串过滤不是 glob** —— 传 `"src/**/*d1*.spec.ts"` 匹配 0 文件并 exit 1。正确写法 `npx vitest run d1 D1`（多个子串取并集）。判「是否真跑了」看 JSON 的 `status` 分布，不看文件数。
- **🔴 「预设/配置里的科目码」是全平台守卫盲区**（2026-08-01 D 类实证）：既有测试只校验「预设能加载 / 锚点合法 / 函数受支持」，**从不校验科目码是不是真科目、是不是该循环的科目** → D6 把 `1402 在途物资` 当合同资产、D5 引不存在的 `1124` 都长期静默。守卫范式 `test_d_cycle_account_codes.py`：①码 ∈ 标准科目表（`data/*account_chart*.json`，不连库故可进 CI）②码 ∈ **本循环报表行**（`report_config`）引用的科目集合 —— 第②条才是抓 D6 的那条（码是真科目但属别的循环）。**改预设必然打红一批钉死旧表达式的既有测试**（D1 3 条 / D 类 10 条），那是「测试镜像 bug」不是回归。
- **🔴 render 的 seed 回退标量必须与 Tier A 预设同口径**（D1 实测）：主路径是 Tier A 公式求值 transient seed 到锚点，`project_context.tb_amount` 只是前端回退；只改预设不改回退 → 用户在公式管理**停用**该公式后假差异复活。修法 `_net_tb_amount()`：三口径（`''`/`_unadjusted`/`_audited`）统一减备抵、原值移 `tb_amount_gross*`、**无备抵数据时完全空操作**（否则灰度开/关逐字节等价被打破）。**且备抵标量必须有前端消费方**（审定表溯源条），否则又是 dead output。
- **🔴 测试替身要按 SQL/params 区分「同一张表的多次查询」**（D1 实测 2 个 fake session 同时中招）：D1 render 查两次 `trial_balance`（原值 1121 前缀**内联在 SQL**、备抵 1231-01 走**绑定参数** `:c0`），fake 不区分则两次返回同一行 → 备抵 == 原值、净额恒为 0，把新守卫变成噪声（断言看着红其实是替身缺陷）。判据用 `any(str(v).startswith('1231') for v in (params or {}).values())`。
- **🔴 循环级幂等脚本与平台级幂等脚本会互相打架**：`fix_note_bold_markers.py`（附注模板剥 markdown 粗体）会把循环脚本写的 `**加粗**` 剥掉，循环脚本下次再写回 → 同一 guidance 一天内被改两次，表现为 `test_apply_plan_is_idempotent` 莫名打红（HEAD 有 `**`、工作树无）。**guidance 一律纯文本**（TAB 提示与 Word 导出都不解析 markdown），并加守卫 `test_guidance_has_no_markdown_bold`。判定「是不是我改的」用 `git show HEAD:<path>` 比对工作树，不要只看 `git status`。
- **🔴 Playwright MCP 断连（`Not connected`）时的替代方案**：用 **chrome-devtools MCP**（`list_pages`/`new_page`/`evaluate_script`/`fill_form`/`click`/`navigate_page`）驱动浏览器 + **postgres MCP** 只读比对落库结果。这套比截图更硬（直接验 `_last_sync_at`/字段值），2026-07-30 的自动同步实测就是这么做的（登录 `admin`/`admin123`，底稿 URL = `/projects/{pid}/workpapers/{wpId}/edit`；HMR 旧错误覆盖层会残留，判真实状态先 `navigate_page reload`）；缺点是要自己写 `dispatchEvent('input'/'change'/'blur')` 模拟录入
- **🔴 长命令会打崩 PSReadLine**（`SetCursorPosition ... top 为负` 后终端持续吐异常，输出不可读）→ 长/多参命令走 `control_pwsh_process` + `> file 2>&1` 再 `read_file`；**别用 PS 重定向存 JSON**（会按控制台宽度折行导致 JSON 损坏），用 `curl.exe -o` 或 python 落盘。**🔴 `vue-tsc --noEmit` 全项目其实能跑通**（2026-07-30 推翻旧结论）：`NODE_OPTIONS=--max-old-space-size=32768 npx vue-tsc --noEmit -p tsconfig.json`，约 5~6 分钟；8 GB / 12 GB 都 OOM，机器本身 189 GB 不是瓶颈。**12 GB 那次"看起来成功"是在语法错误处提前 bail**，别当通过。基线 **3380 errors / 881 files**（多为 `el-input-number @change` 签名，TS2322 1779 条）。**它能查出 Volar 逐文件诊断 + vitest 全查不出的三类问题**：SFC 语法级损坏（`{{ x }.` 少括号 / 多余 `}` → Vite 实为 500）、共享类型不兼容波及多循环（helper 的 `[k: string]: unknown` 索引签名让 8 个循环的契约 spec 全报 TS2322 —— **带索引签名的类型不能从无索引签名的 interface 赋值**）、引用不存在的字段（11 个宿主读 `runtime.applicableStandards`，`WorkpaperRuntimeContext` 里没这字段 = 死 fallback，正是「变体门恒开」的类型层证据）→ **日常仍用 `get_diagnostics` 逐文件，收口/验收跑一次全项目**
- **🔴🔴 负债类叶子预填一律「整族统一取向」，禁逐行 `abs()`（2026-08-01 J2 真实数据证伪，凡负债/权益循环通用）**：`2705` 叶子**带混合符号** —— `.99 初始入账 -729,000` / `.03 过去服务成本 **+375,000**` / `.04 结算利得 -11,000` / `.05 利息净额 -116,000` / `.06 重新计量 -276,000` / `.01 离退休人员费用 **+362,720.20**`，**签名和 -394,279.80 == 父科目期末** ✅ 而**逐行 abs 之和 1,831,000 与父额差 4.6 倍** ✗。正解 = `liability_orientation(all_rows, prefixes)` 取父科目余额符号，**整族**乘同一系数（父额为负即 `-1`），保住行间相对关系；实测 `sign=-1` 后行级期末和分文不差等于父额，借方性质叶子如实显示为负。`aggregate_leaves(absolute=True)` 取 `|Σ|` 是对的（作用于**聚合结果**），错的是**逐行** abs。**自造 fixture 与错误假设同构 → 单测全绿也查不出，只有真实数据能证伪**（同族：K1「原值保留符号+只对备抵聚合结果 abs」、G7「备抵增减方向与原值相反」）。另：变动表行取的是**变动额**不是余额 → prefill 要同时给 `opening`/`closing`/`change`。
- **🔴 备抵科目的「增加」在贷方，与原值侧相反（2026-08-01 G7 实测挖出，凡有备抵段的循环通用）**：原值（借方）`debit_amount`=增加 / `credit_amount`=减少；**备抵（贷方）`credit_amount`=计提（增加）/ `debit_amount`=转回核销（减少）**。照原值侧口径写会让 roll-forward 恒不平（活体 `1512` 期初 2,840,032.97 + 计提 1,950,000.00 = 期末 4,790,032.97 被算成 decrease）。**自造 fixture 与自己的错误假设同构 → 单测全绿也查不出，只有真实数据能证伪** → 审定表/明细表预填涉及增减列时必须真实 DB 直跑一遍。
- **🔴 `ReportLineAccountSpec` 支持备抵独立报表行（2026-08-01 G7 新增 `provision_row_code`）**：适用「原值行公式不引用备抵、备抵自成一行」的循环（G7 = `BS-024` + `IMP-009`；H/I 类的 `IMP-xxx` 同形）。仅当 `row_code` 公式没解析出备抵码才去解析它；默认 `None` = 引入前逐字等价。**这是避免把备抵科目码写成字面量兜底的正解**。
- **🔴 名称分类必须有否决词 `exclude_keywords`（G7 实证）**：`其他权益变动_不属于其他综合收益` 同时含「其他综合收益」→ 无否决词会被判成 OCI，「其他权益变动」列恒 0。凡按名称归类都要检查「A 的关键字是否是 B 名称的子串」。
- **🔴 四表库取数三层链路禁硬编码前缀（K1 实证，各循环通用）**：备抵科目必须由**报表行公式**解析到细分标准码（`1231-03` 而非 `1231`），再经 `account_mapping` **反解**回客户原始码（`1231.03`）才能前缀匹配 `tb_balance`；聚合必须**叶子**（无 `code + '.'` 子行）而非「最深层级」—— 客户科目树参差，取 max_depth 会整段丢一级叶子。共享件 = `app/services/four_table/{report_line_accounts,leaf_aggregation}.py`（`ReportLineAccountSpec` 声明 row_code + 兜底码 + `extra_standard_codes`），**新循环直接复用，别再抄一份**。自检不变量：**叶子和 == 父科目行金额**。
- **🔴 `resolve_report_line_account_codes` 必须传 `applicable_standards`**：同一 row_code 在不同准则下公式**语义不同**（`BS-009` soe_standalone 含 `− TB('1231-03') + TB('1131')`，listed_* 只有 `TB('1221')`），不传则 `LIMIT 1` 无 `ORDER BY` 任取一条 → 备抵科目随行序丢失。
- **🔴 备抵侧 `use_provision_name_filter` 有两种成因，需要精确判定时读 `provision_exact`**：`provision_resolved_from=='fallback'` 既可能是「报表公式没引用备抵」（listed 侧正常情形），也可能是「`account_mapping` 反解退化为宽前缀」；只有后者才真需要名称过滤。共享件保留保守口径属性保 D1 零回归，新增 `provision_exact` 供精确判定。
- **🔴 `trial_balance` 里父码与子码并存必须按最长前缀归属**：`1231` 与 `1231-01..05` 同时存在，`LIKE '1231%'` 全加 = 父子双计（K1 前端兜底请求原犯此错）。前端共享 `sumLongestPrefixOnly(rows, wanted)`。
- **🔴 `trial_balance_service` 的 `debit → +ABS()` 方向归一不可无脑套用**：实测存在 `direction='debit'` 且余额合法为负的叶子（`1221.98.07 = -227,132.40`），翻正会破坏「叶子和 == 父额」勾稽 → K1 侧改为**原值保留符号 + 只对备抵的聚合结果取 `abs()`**（两种存储约定 abs 同解）。
- **🔴 补 `text_sections` 缺段用 `ensure_text_sections`（追加缺的）而非 `run_section(text_sections=...)`（整表替换）**：后者要手抄整份 47 段，抄错会被脚本**写回模板**，风险远大于收益。共享 kit 已加 `require_text_sections` 参数 + `missing_text_sections()` 供 `--check`。
- **🔴 `PresetEntry` 字段是 `page_key`（`workpaper:K1`）+ `expression`，不是 `scope`/`formula`** —— 写公式预设守卫前先 probe，否则过滤恒空、断言空转。
- **🔴 `readFile` 对「本会话已修改 / 并发会话在改」的文件会返回陈旧版本**（实测 3 次：`d2NoteSectionMap.ts` 返回 HEAD 版、`useD2DisclosureNote.ts` 显示已删除的旧函数、测试文件断言与实跑结果相反）→ 判定落盘真相一律 `python -c "open(p,encoding='utf-8').read()"`；`read_file` 还按路径缓存，同名临时文件会读到上一次内容 → 落盘用**每次不同的文件名**
- **🔴 改前先确认函数是否已存在**（本次给 `disclosure_engine` 加列元数据透传，实为重复造 `_carry_seed_column_meta`，靠 `inspect.getsource` 显示的实现与"我写的"不一致才发现）→ 加公共 helper 前先 `grep def <name>` + 看是否已有姊妹 spec 的未提交测试在引用
- **🔴 Playwright 认证 token 在 sessionStorage（不跨 page 共享）**→ `page.context().newPage()` 开的新页面必被重定向到 `/login`，**无法用开新页面规避并发会话抢占**。只能复用已登录 tab，并把「goto + 点 tab + 等选择器 + 读取」全部压进**单个 `run_code_unsafe` 原子脚本**（分步调用之间会被别的会话导航走，实测 3 次）。读多变体 tab 时选择器必须带组件根作用域（`.h1-tab-disclosure-soe .xxx`），否则 `querySelector` 取到的是另一个 tab 已挂载的同名节点
- **🔴 前端全量失败判定只能用 JSON reporter**：`npx vitest run src/components/workpaper --reporter=json --outputFile=<abs>.json`（约 5~6 分钟）。`--reporter=dot/basic` 经 cmd 重定向后**中文路径全乱码 + 二进制垃圾字符**，无法定位失败文件；`--silent` 必须写 `--silent=true`（否则被当值解析报错）。**2026-07-30 基线 = 18940 例 / 84 失败 / 13 文件**：b23ProcessControl(.spec 42 + .pbt 29)、GtG0Confirmation 2、a173 1、useI6 1、k7NoteSectionMap 1、kLiabilityNoteSubtableContract 2、l4-bonds-payable 2、useF3/useF5/useH4 各 1、j2Runtime 1（K7 两条属并发会话在飞的 K 系 spec，两 spec 断言互相矛盾）
- **🔴 `gen_note_wp_sync_registry.py` 的两条硬约束（2026-07-31 H10 实测各踩一次）**：①**章节号必须是内联字符串字面量** —— 生成器用 `listed\s*:\s*'…'` 从对象体抽值，写成 `listed: H10_LISTED_NOTE_SECTION` 标识符引用会让**整条 wp_code 从 registry 消失**（判据：`entries=61`→`60`）；②**对象体内不得写注释** —— 注释里若含 `listed: '…'` 字样会被优先抓到（抓到 `…` 后 `_is_section_code` 判否 → 同样整条消失）。另 `_SECTION_BLOCK` 原正则 `_NOTE_SECTION[^=]*=` 会让 `X_NOTE_SECTION_DISPLAY` 命中并**覆盖**真定位常量（已加 `const/let/var` 锚定 + `(?![\w])` 收尾）。**「定位常量 vs 展示常量」分离是必要的**（md 截断的 `三、资产处置收益（损` 直接显示给用户不可读），但展示常量的命名要避开生成器扫描的名字空间。
- **🔴 `gen_note_wp_sync_registry.py --write` 会顺带带入并发会话的 map 改动**（本次除新增 N2/N4/N5 外还追上了 K8~K13 半角→全角、K11~K13 章节号改截断值）→ 重跑后须查 diff 确认范围，并跑 registry 消费方测试（`test_note_wp_mapping_registry` / `test_note_k_sheet_names` / `test_disclosure_stale_marker`，59 例）
- **🔴 宿主漏传 `projectId` = 披露同步永久静默失败**（2026-07-30 浏览器实测，N2/N4/N5 三个宿主全中招）：`syncToDisclosureNotes` 首行 `if (!props.projectId) return`，组件不崩、只在控制台留一条 `Missing required prop` → vitest 与 `get_diagnostics` 全查不出，手动按钮与自动同步双双无效。已加平台守卫（`disclosureAutoSyncCoverage.spec.ts` 扫全部 `.vue` 的 `<XTabDisclosure*>` 使用点，须有 `:project-id` 或 `v-bind="$props"`；现存 126 处全合规）
- **🔴 AI 文本生成唯一正解端点 = `POST /api/workpapers/{wpId}/ai/generate-text`**，body `{section, prompt, context: dict[str,str], existingContent}`（**驼峰**！`existing_content` 会被忽略；`context` 值必须全字符串否则 422），读 `data.data.content`。收敛在 `composables/shared/wpAiText.ts`（`useN1AiText` re-export）。**没有 `/ai-generate` 这个端点**（本会话首版误用，写错就被 `catch` 吞成「AI 生成失败」= D1 那 7 个空转按钮同源）
- **🔴 源模板没有披露 sheet 的循环，代码里也不许有披露 Tab**（2026-07-30 复核 N 类完整性时抓到 `N3TabDisclosure.vue`）：N3 递延所得税负债源 xlsx 只有 底稿目录/N3A/N3-1/N3-2/N3-3/GT_Custom，`workpaper_sheet_classification` 附注 sheet 0 条 → 该组件是自造三小节（概述/应纳税暂时性差异明细/余额变动表）且 `currentSheet === '附注'` 永不命中 = **死代码 + 污染源**（N3 披露与 N1 共节 五、30/八、31，N1 表(1) 已含负债段，一旦接上同步链路就写进 N1 章节）。已删组件 + 宿主 import/分发 + `components.d.ts` 残留条目（库里 `N3-disclosure-%` 0 行无数据可丢）。守卫 = `disclosureAutoSyncCoverage.spec.ts` 的 `CYCLES_WITHOUT_DISCLOSURE`（每条须写源模板依据 + 反向自检防空转）。**盘查循环时「无独立披露 sheet 故不涉及」不等于代码里没有 Tab，必须 grep 组件**
- **🔴 sheet 分发判定收敛到 `composables/shared/cycleSheetRouting.ts`**（`makeCycleSheetRouter({codeRe, htmlCodeRe, bareCodes})`）：披露判定**前置**于 wp_code 正则 + 国企 `国企/国有/國企` 三写法全认。N2/N4/N5 已接（N2 原写繁体 `國企` → 国企 Tab 从未渲染过）
- **🔴 N5 国企披露 sheet tab 名缺右括号 = `附注披露信息（国企`**（源模板如此，A2 单元格才完整），`workpaper_sheet_classification` 记的是 tab 名 → 同步 `sheet_name` 逐字用它，禁"修正"
- **披露内部勾稽校验范式**（H1 首建，可复用到各循环）：纯函数引擎 `h1DisclosureConsistency.ts`（`eqCheck` 相等类容差 0.01 元 / `subsetCheck` 子集类，返回 `{label, rule, left, right, diff, level, detail, refs}`）+ 展示组件 `H1DisclosureConsistencyPanel.vue`（紧凑单行 bar + 折叠明细表 + 规则 tooltip + `GtIndexChip` 追溯）。校验项只取**源模板可判定**的勾稽：汇总表↔变动表账面价值、子表对主表的子集约束、模板「—」列示约定（如土地不提折旧/减值）、源模板红字要求的联动（如政府补助须在「其他减少」列示）
- **🔴 崩溃类 bug 以 Vite transform 为权威**：`curl.exe http://localhost:3030/src/.../X.vue` 看 200/500。`get_diagnostics`(Volar) 查不出 SFC 结构损坏/import 解析失败/未声明 binding/`export` in script-setup；HMR 长开页面会累积旧态，判真实状态必全新导航
- **🔴 `note_template_*.json` 是 md 重建产物**（`scripts/fix/rebuild_note_from_md.py` 会压扁多级表头、把双期两张表并成一张）→ 结构修订必须做成**幂等脚本**（`scripts/fix/fix_note_ar_listed_structure.py` / `fix_note_inventory_structure.py` 范式，带 `--dry-run` / `--check` + `_aligned_by` 标记）+ 契约测试兜底，禁止直接手改 JSON；压扁的第二行表头会残留成 `row_type: header_label` **假数据行**，修订时必删
- **🔴 附注两级表头唯一机制**：`ColumnDef.group` →（后端 `note_sub_table_projector._extract_column_groups`）→ `_column_groups`，消费方 `DisclosureEditor.activeTableColumns`（嵌套 el-table-column）+ `note_word_exporter._build_two_level_header_rows`。**不要新建机制**；同步载荷别把两级压平成「期末账面余额」，用 `label` 子列名 + `group` 父表头。seed 路径另需 `disclosure_engine._carry_seed_column_meta` 透传（`_build_table_data` 只返回 `{headers, rows}` 会丢弃 `columns`/`_column_groups`）
- **`_extract_column_groups` 三态**：`None`=未声明（回退 `_infer_groups_from_headers` 前缀推断）/ `[]`=任一列带 `ColumnDef.flat` 即显式单级（禁推断）/ 非空=显式分组。**源模板单行表头的表必须标 `flat`**，否则 `本期增加`/`本期减少` 会被反猜出凭空的「本期」父表头（F2 房企 3 表 + 数据资源表已标）
- **🔴 `_source=workpaper` 时底稿推送是唯一权威**：投影器只渲染推过来的 `sub_table_data`，**不与模板 `_tables` 合并** → 模板 seed 的示例组合/账龄档位一旦同步就被完全覆盖，其定位只是「骨架 + 示例」（给从未同步过的项目看）。所以「结构要按实际项目走」靠推送侧解决，不是改模板
- **🔴 披露自动同步机制早已存在 = 前端 `useDisclosureAutoSync`**（防抖 800ms + 复用各 Tab `syncToDisclosureNotes` → 与手动按钮同源幂等）。**后端做不了自动同步**：`sub_table_data`/`columns` 由前端 `buildXSyncPayload` 算出，`WORKPAPER_SAVED` 的 extra 只有 `{wp_id,wp_code,trigger,item_ids,atomic}`（无 sheet_name/表结构），后端重建会把每个循环载荷逻辑双写。后端只做兜底 `disclosure_stale_marker`（标 `is_stale`，覆盖导入/API 直写/后台重算等绕过前端的路径）
- **🔴 披露 Tab 同步链路实测（154 个 `*TabDisclosure*.vue`，2026-07-30 定稿）**：**90 有链路**（65 自有 `syncToDisclosureNotes` + 25 用别的 syncFn 走 autoSync）/ **64 无链路**（三个标记全无 → 披露数据只停在 `checklist_responses`，附注**永远拿不到**；抽查 N2/L2 确认 `disclosure-notes` 端点 0 命中）。「有同步能力却未接自动同步」实测为 **0** → 缺口不是"没接自动同步"而是**压根没有同步入口**，这是 572 个 legacy 章节的根因之一。收口 spec = `disclosure-sync-path-buildout`（按循环分 6 批），清单固化在 `disclosureAutoSyncCoverage.spec.ts` 的 `MISSING_SYNC_PATH`（只允许变短）
- **🔴 变体薄壳（`<Base variant="x" v-bind="$props" />`）两个坑**：①**守卫要做委托解析**，否则虚报缺口（G10/G11 的 Listed/SOE 各 15~21 行薄壳，链路在 Base 里 → 缺口从 64 修正为 60；`disclosureAutoSyncCoverage.spec.ts` 已加 `resolveDelegate`，反向自检用**替身**不绑真实循环）；②**薄壳漏声明 prop = 静默锁死**（`v-bind="$props"` 只转发**已声明**的 prop，G9 两壳原无 `projectId` → Base 接了同步按钮也永久 disabled）
- **🔴 `sync_from_workpaper` 定位键只有 `(project_id, year, note_section)`，`current_standard` 不参与匹配**：而国企项目的「五、xx」是另一套压缩编号（实测项目 2aa00f57：`五、19`=应付职工薪酬 / `五、20`=应交税费）→ 在国企项目上编辑**上市**披露 TAB 会把数据写进错误章节。本应由 `isXDisclosureApplicable` 拦，但 `applicableStandards` 前端全链缺失（恒 `[]` → 门恒开）。约 90 个已接链路 Tab **共有**此风险，根治须单独立 spec
- **🔴 新 `build*Columns` 必须登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`**，且**变体入参型 builder 不能叫 `buildXColumns`**（会被 sweep 用空入参调用 → 列头为空触发 Property 6）→ 参数化的命名 `gXColumnsFor(variant)`，对外只导出零参 `buildXListedColumns` / `buildXSoeColumns`
- **🔴 `gen_note_wp_sync_registry.py` 曾有跨语句正则 bug**：`_DISCLOSURE_SHEET_(...)[^=]*=` 会让**文档注释里提到的常量名**咬到下一条语句的等号（实测把 G12 两个变体都写成 `listed`）→ 已锚定 `const/let/var` 声明；写映射文件的注释时也别原样写常量名
- **🔴 seed 常量可能本来就是错的（零消费方的死常量）**：`G8_MAIN_SUBTABLE`/`G9_MAIN_SUBTABLE` 原值指向不存在的表 / 第 2 张表 → 接同步前必须逐字核对模板 `tables[].name`，别信既有常量
- **🔴 `emit` 不算同步链路**（曾据此把缺口低估为 27）：37 个 emit 型披露 Tab 的事件只有 `navigate`(27) / `imported`(7) / `disclosure:note-text-updated`(5)。前两者与同步无关；后者消费方 `useNoteRefresh.onDisclosureNoteTextUpdated` 仅 `fetchDetail` 刷新界面且首行 `if (!currentNote.value) return`（附注页未打开直接返回）→ **不推数据落库**。判断"有没有同步链路"只认 `syncToDisclosureNotes` / `sync-from-workpaper` / `scheduleAutoSync`
- **🔴 F2 曾是"假接入"**：只 `watch(dataUpdatedVisible)`（上游更新提示横幅的可见性），用户自己改数据一律不触发 → 接自动同步必须监听**实际数据**（与 `syncToDisclosureNotes` 构建载荷所用字段一致）
- **🔴 `_xxxMounted` 一次性防护会吞掉编辑（L1/L3 等在用，是 bug，勿照抄）**：防护消耗时机取决于「数据是否已加载」—— 首次挂载时 `allResponses` 异步填充让 computed 变化并消耗掉防护；但**切走再切回**时数据已在、computed 不变、watch 不触发、防护未消耗 → 吞掉回到本页后的**第一次真实编辑**（浏览器实测：`checklist_responses` 已存但附注 `_last_sync_at` 不变，同一挂载内再改一次才同步）。Vue `watch` 默认 `immediate:false` 挂载本身不触发，**无需防护**；数据加载引起的那次同步反而是有益的（幂等 + 空载荷 no-op）
- **🔴 附注 legacy 快照全库规模（2026-07-29 dry-run）**：**572 个章节**仍是生成时快照（`sub_table_data` 空 + 有 `rows`/`_tables`），占有差异章节的 **98.9%**；共 982 张待迁移表里 **950 张（97%）在模板里也没有 `columns`** → **直接迁移比现状更糟**（投影降级为只显示行名，legacy 至少有 headers）。脏数据：58 章节有重名表（按 name 建键会覆盖丢表）、79 章节表名是表头首格「项  目」。→ **跨 spec 依赖：`disclosure-columns-coverage-rollout` 补完 `columns` 才能做 legacy 迁移**
- **🔴 附注根本不跟随底稿内容（2026-07-29 实证，6 条 `note_section IN ('五、9','八、10')` 记录）**：只有人工点过「同步到附注」的那 1 个项目 `sub_table_data` 有 9 张表，其余 5 个项目**全是 0 张**，界面显示的是生成时持久化的旧 `rows`/`_tables` 快照（3 张表 + 已从模板删掉的 `header_label` 假数据行）→ 底稿保存未接 `WORKPAPER_SAVED` 自动同步、模板升级不回流既有项目、脏快照与 `sub_table_data` 双真源。收口 spec：`disclosure-note-follow-actual-content`
- **🔴 改模板 JSON / 改前端载荷代码对既有项目一律不生效**（实测：F2 存货 14 张表补 `guidance` + 5 张补 `flat` 后，拉真实后端投影仍 guidance 全 0 字、`（续）`表 `_column_groups=None`）→ `guidance` 只经 `disclosure_engine._carry_seed_table_guidance` 在 **seed 路径**生效；`_sub_table_columns` 是上次同步写入的旧值。交付说明必须写清「新建项目/重新生成才可见」，别把"模板改了"当成"用户看到了"
- **🔴 `flat` 必须同时加在「同步载荷」与「模板 JSON 的 `columns`」两处**（**双向都踩过**：F2 只加载荷漏了模板 seed；**H8 只加模板漏了载荷** → 推送路径即真实用户路径，实测国企投影出 `_column_groups=[{group:'本期',start:2,span:2}]` 把「本期增加/本期减少」并组。守卫要同时断言两侧 `flat` 表态且不得声明 `group`）：只加前者会让 **seed 路径**（新建项目/重新生成附注）继续被 `_infer_groups_from_headers` 塞凭空父表头。**另注意 `disclosureColumnsCoverage.spec.ts` allowlist 里「推断结果为空 → 现状无害」的旧判断可能只对其中一个变体成立**（H8 上市类别名无共享前缀确实无害，国企侧却被并组）。实测模板 columns 无 flat 时：开发产品→凭空「本期」+「期末」、周转房→「本期」、开发成本→**「预计」**（把「预计竣工时间」与「预计总投资」凑成一组）。守卫必须覆盖 seed 路径，只测同步载荷会漏
- **🔴 `disclosure_notes.table_data._tables` 是生成时快照**：改 `note_template_*.json` 只对**新建项目 / 重新生成附注**生效，既有项目 TAB 数不变；「🔄 恢复模板结构」只重置当前单表（`templateStructure` 返回单个 `{headers,rows}`），**不新增表**。改完模板须在交付说明里写清此点。**存量修复范式** = `backend/scripts/fix/backfill_note_prepayment_snapshots.py`（默认 dry-run / `--apply` / `--check`；安全门：`_tables`+顶层 rows+`sub_table_data` 任一格有值即跳过，改由底稿「同步到附注」整表覆盖）
- **🔴 附注 `tables[].guidance` = TAB 页签编制提示**（K1 §五、8 / §八、9 共 37 张表首次启用；H1 §五、22 6 表 + §八、22 5 表已跟进）：内容只许取源模板红字 / 附注模版括注 / 15号文条款，或以「勾稽：」前缀标注的工具提示。seed 显式 guidance 经 `disclosure_engine._carry_seed_table_guidance` **优先于** `per_table_guidance` 段落游标推断（仅已声明的表受影响 → 其余 300+ 章节零回归）。
- **🔴 模板 `rows` 里的占位说明是假数据行**：源模板「可无限量添加行」（H1 上市 A65 闲置表 / A74 租出表）被 md 重建脚本当数据行落进 `rows`，会渲染成一行空披露数据 → 必删，语义移入 `guidance`。同类还有压扁的第二行表头残留成 `row_type: header_label`
- **🔴 `……` 占位列头必须展开成实际类别**：H1 上市「固定资产情况」headers 原样保留源模板 E13 的 `……`，而底稿 `buildH1ListedColumns` 按 `H1_LISTED_DEFAULT_CATEGORIES` 推 5 类 → 附注侧「办公设备/其他设备」两列无落点（孤儿列 + 数据丢失）。展开依据 = 源模板红字「此处分类应与固定资产项目注释的分类保持一致」+ 平台共用口径 `H1_FA_CATEGORIES`（**电子设备归一到办公设备**，`normalizeFaCategory` 显式约定，不要按会计政策表的「电子设备」去改底稿默认类别）
- **🔴 一份列头常量给两个变体共用 = 国企表头错位**：F3 的 `F3_YFPJ_COLUMNS`（种类/期末余额/上年年末余额）被 listed+soe 共用，而源 xlsx 国企是 类别/期末余额/**期初余额** → 3 列错 2 列。凡「上市/国企同形但用语不同」的表，列头必须按 variant 拆常量（字段 `key` 不变、只有 `label` 分变体），并加反向断言「两版表头必须不同」。**没有 `fXNoteSubtableContract.spec.ts` 的循环等于 P1~P6 全不设防**（F3 曾是 F 类唯一缺此守卫者）
- **🔴 模板 `headers` 的 HTML 是全库欠账，非个例**：共享契约 helper 原 P4 只校验同步 `columns` 的 label/group，模板 `tables[].headers` 是盲区 → 补 **P6** 后立刻打红 K1，全库扫出 **133 处 `<br/>`**（listed 63 / soe 70，横跨 A·B·D·G·K·L）。平台级修订入口 = `backend/scripts/fix/fix_note_headers_plaintext.py`（剥离 headers/columns[].label/group 的 HTML，带 `--dry-run`/`--check`）
- **🔴 探测「有没有接 AI 辅助」不能只 grep `runAi(`**：各循环命名不统一（F2 用 `runAi`，F3 用 `generateListedNote`，F4 用 `generateDisclosure`）→ 复盘时误判 F3/F4 缺 AI，实际都已接且后端 section 在册。正确信号 = `useXAiGenerate` 的 import + `generateAndConfirm(` 调用
- **🔴🔴🔴 附注模板的源 docx 在 `docs/模版/`（2026-08-05 用户指路后确认，**纠正此前「附注模版不存在」的错误记载**）**：`docs/模版/1.上市公司年审报表及附注-2026.01/1.上市公司年审报表及附注-2026.01/3.2025年度上市公司财务报表附注模板-2026.01.15.docx`（726 KB，listed）+ `docs/模版/1、2025年度财务决算审计报告-2026.01.06/1、2025年度财务决算审计报告-国企/1.1-2025国企财务报表附注20260119.docx`（466 KB，soe），另有配套报表 `2.股份年审－经审计的财务报表-202601.xls` / `1.1-2025国企财务报表20260106.xlsx` 与审计报告 docx。**这是两份 `note_template_*.json` 的重建源头，附注结构裁决一律以它为准**。🔴 **两个搜索陷阱**：①按文件名 grep「附注/模版」搜不到 —— 目录名才含「模版」，文件名是「…财务报表附注模板…」；②**docx 章号是 Word 自动编号，段落文本不含「十二、」** → 定位章节必须按 `paragraph.style.name == 'Heading N'`，用 `^N、标题` 正则会 0 命中。~~`附注模版/*.md` 在本仓库不存在~~（`基础数据/` 确实不存在，但结论「无附注源模板」是错的）。F2 存货第一轮据此写下的「行不动原则」（附注不引入「委托加工物资」「发出商品」）**已推翻**（源 xlsx 上市 r12/r14、国企 r12/r16 明确有这两行，底稿常量也一致，只有附注 seed 少行）
- **🔴 `_note_texts` 必须带中文 `title`**：后端 `_format_note_texts` 缺 title 时用 `section` 兜底 → 附注 `text_content` 渲染成 `【listed-note-category】` 等英文键（违反 UI 全中文化）。F2 两版曾整批缺失，已改经 `buildF2NoteTexts([section,title,text])` 构建（同 D1/D2/K10 范式）+ 空文本过滤。**新循环接同步时逐条核 title**
- **🔴 「有输入框 + 有 AI 辅助」≠「会回流附注」**：F2 国企「土地储备说明」有 `landNote` ref、有 `soe-note-land` AI target，但 `F2SoeSyncSnapshot` 没这字段 → 填了永远进不了附注。查同步完整性要比对「文本域清单 ↔ snapshot 字段 ↔ `_note_texts` 条目」三者，只看 UI 会漏
- **🔴 源模板「或：」= 二选一表组，需 mode 开关 + `_removed_table_keys`**：F2 上市「按组合计提」与「按库龄组合计提」各 2 表列结构完全相同，模板 4 张都在但底稿只有前者入口 → 后两张在附注永空。修法 = 一个 `s3Mode` 持久化项 + **共用同一套行 state**（列同构，避免双真源）+ 推送时只发选中组、另一组进 `_removed_table_keys`；`buildXColumns(mode = 默认值)` 保证覆盖率 sweep 空入参调用仍返回非空列头
- **🔴 披露列结构三源裁决**：底稿源 xlsx / `附注模版/*.md` / `note_check_preset_formulas.json`（`{循环}{节号}-n` 如 F7-1~F7-14，按 `listed`/`soe` 两份）三者冲突时，**校验预设是裁决者**（它直接写明「上市版②表无『账龄』『未结算的原因』列」「③表无减值准备列，跳过」「合计行 = 小计行 − 减值准备行」）。`consol_note_sections_{listed,soe}.json` 可作第 4 方印证。**附注是交付物 → 列结构随附注模版 + 校验预设；底稿可多留审计列，但同步时必须投影成附注形状**（F1 国企逐段减值准备列 → 聚合为「减：减值准备」行）
- **🔴 行型判定必须先去空白**：源模板写的是「小 计」「合 计」（中间带空格），`startsWith('小计')` 会漏判 → 小计/合计行被当普通数据行推给附注，丢 `is_total`、加粗与勾稽（G4 载荷曾中招）。同理阶段表的「其中：」结构行不能省（附注是交付物，缺了看不出明细归属），空值列写 `null` 保列键齐备。**但结构标签不能同时当明细行默认名**：`emptyDetail('其中：')` + 载荷单独发 `whichRow()` → 附注出现两行「其中：」（一行全零幽灵数据行，G4/G6 共有，浏览器实测才发现）→ 默认名留空 + 共享谓词 `isPlaceholderStageDetail()`（无名或名=结构标签 且 金额全零）在载荷侧跳过空白骨架行
- **🔴🔴 两类"只有浏览器实测才暴露"的接线缺陷，已全平台清零 + 双守卫**（守卫 = `backend/scripts/check/check_setup_scoped_composables.py --path .` 两规则 + `fix_disclosure_self_schedule.py --check` + 前端 `disclosureAutoSyncCoverage.spec.ts` 新增 2 断言；CI job `disclosure-sync-wiring`）：①**setup 作用域 composable（`useAuditContext`/`useRoute`/`useRouter`/`useDisplayPrefsStore`）写进函数体 = 该功能静默全废** —— 内部依赖 inject/effect scope，运行时拿不到 route → TypeError → **在发请求之前就抛错**（零网络请求），vitest 与 `get_diagnostics` 全绿。J1 两披露 Tab 同步按钮+自动同步**一直是死的**（`_last_sync_at` 恒 NULL）、H8 两 Tab「校对附注」永报错、`ColumnMappingEditor.getCurrentProjectId` 路由回退是死的；扫全 2346 个 `.vue` 共 3 处，已清零。②**`scheduleAutoSync(syncToDisclosureNotes)` 写在同步函数内 = 调度自己** → 800ms 周期重复 POST，**且骗过覆盖率守卫**（只看有没有该调用）→ 12 个 Tab 的自动同步实为假接入（从未接数据变更）。共 16 处横跨 G1/G2/G3/G6/H3/I4/I5/I6/K1，已全部改为 watch 实际数据（无独立 ref 的直接 watch**构建载荷的表达式**，最贴合"监听字段须与载荷一致"铁律）。**12 个 Tab 已全部浏览器活测通过**（K1Soe/K1Listed/G1SOE/G6SOE/H3×2/I4×2/I5×2/I6×2）：每个都「静置期 0 次 POST + 数据变更 1 次 POST」，13 个附注章节 `_last_sync_at` 全部由 NULL 前移（八、2/八、3/八、16/五、21/八、22/五、29/八、30/五、31/八、32/五、66/八、67/五、8/八、9），测试数据已全部改回原值。明细与实测手法见 `#conventions` §J1 披露 wave 3~6 沉淀
- **🔴🔴 损益类「Σ借−Σ贷」在含年末结转损益的全年账上结构性恒为 0（2026-07-31 N4/N5 实证，9 个项目全中）**：序时账必有「结转损益」分录（贷记 6xxx 结转到本年利润），故 `tb_ledger` 与 `tb_balance` 的借贷两侧金额**恒相等**（活体 `6801.01` dr=cr=24,891,157.62；凭证 0409 计提借 110,445.40 / 凭证 0410 结转损益贷 110,445.40）。**平台权威口径 = `trial_balance`**（recalc 已按发生额写好，`TB()` 的 `_handle_tb` 读的就是 `ctx.tb_data` ← `trial_balance`；`report_config` 的 `IS-003 税金及附加=TB('6403','本期发生额')` / `IS-023 减：所得税费用=TB('6801','本期发生额')` 四准则一致）；兜底取 `tb_balance.debit_amount`（**仅借方**，逐分实证 trial_balance 6801=21,151,383.26 = tb_balance 6801 debit = 叶子 .01 24,891,157.62 + .02 −3,739,774.36；负借方语义即"贷方性质"，直取可保留符号）。→ **凡损益循环（N4/N5/H10/I6/K8~K13/L8 等）若写了 `debit - credit` 都要复核**
- **🔴 `IS-022 三、利润总额 = ROW('IS-019')+ROW('IS-020')-ROW('IS-021')` 是派生行不是科目**（`6001` 是营业收入）→ 预设里 `利润总额=TB('6001',...)` 全错；prefill 引擎无 `REPORT`/`ROW` 解析器故只能降级 `PLACEHOLDER` + 描述写明来源（同 N1-1 `税会差异汇总` 范式）
- **🔴 `1812` 是不存在的科目码**（活体 `tb_balance` 0 命中）；递延所得税负债 = **`2901`**。N3「明细表N3-2」块与 N5-8 块都在用它 → 取数恒空
- **🔴 6403 子科目编码语义在客户间冲突，只能按名称归类**（活体 `6403.01` 某客户是「印花税」；`6403.02` 既是「税金及附加_城市维护建设税」也是「车船税」）→ N4 按税种拆分必须用 `_classify_n4_subaccount(name)`，禁按编码
- **🔴🔴🔴 科目定位必须「语义驱动 + 逐项目动态」，写死标准码在部分项目必错（2026-08-01 用户明确要求 + DB 铁证，全平台适用）**：① **`account_mapping` 同一原始码在不同项目映射到不同标准码** —— `1532 未实现融资收益`→`1532`(3 项目) vs →**`1541`**(2 项目)；`1525 投资性房地产累计折旧`→`1521`(1 项目**并入母科目**) vs →`1525`(4 项目独立)；`1527`→`1521`(1) vs →`1527`(3)。② **平台标准科目表本身各项目不一致** —— 10 项目里 4 个有 `1519`、2 个只到 `1507`、4 个完全没这一族（`2aa00f57` 只有 58 个标准科目）。③ **客户科目表（`source='client'`）里压根没有 1504~1507/1519**，唯一有投资类科目的项目用的是**旧准则 `1501 持有至到期投资`/`1503 可供出售金融资产`**。→ 故 `report_config` 的标准码只能当**提示**，实际定位链必须是「报表行 → 科目**名称**语义 → 本项目 `account_chart`（client 优先、standard 兜底）实际存在的码 → `account_mapping` → `tb_balance` 原始码前缀」，名称归一（空格/下划线/全半角）+ 否决词（不含「减值准备/累计折旧/累计摊销」）+ **只在一级科目（4 位码）层匹配、子科目靠点号前缀继承**（子科目名很随意：实测 `1531.01 押金`/`1531.02 借款`/`6701.01 坏账`）；本项目无该科目时**返空而不是取错**。这是「按名称归类」铁律的第四例（前三：存货 14xx / 6403 税种 / 1123 性质），且最严重 —— **新旧准则两套编码并存**。**⚠️ 不可自动化的点**：客户用旧准则 `1503 可供出售金融资产` 时，新准则下按业务模式与 SPPI 特征拆到「交易性金融资产/其他债权投资/其他权益工具投资」三处 = 会计判断（G6-7/G6-8 底稿在做），**必须留人工映射入口，代码不得猜**。
- **🔴🔴 存货科目（14xx）编码语义在**项目间**冲突 —— `account_chart` 里并存两版标准科目表（2026-08-01 实测 9 项目 `source='standard'`）**：`1405` A=自制半成品/B=**库存商品**；`1406` A=**库存商品**/B=发出商品；`1407` A=发出商品/B=**商品进销差价**；`1408` A=商品进销差价/B=委托加工物资；`1409` A=周转材料/B=无；`1411` A=委托加工物资/B=**周转材料**；`1451` A=包装物/B=损余物资；`1416` A 侧 5 项目=存货跌价准备 / `1461` B 侧 6 项目=存货跌价准备。变体 B 是 CAS 2006 官方口径，A 是本地化改编。→ **不存在一组写死就对的存货编码**，F2 分类必须按**科目名称**归类（单一真源 `app/services/f2_extraction/category_rules.py`，与 N4 `6403`/F1 `1123` 同款铁律）。改造前 `F2_CATEGORIES`/`f2_extraction.build_default_bindings`/前端 `f2AccountModel` 三处都写死 `1401..1412`+`1471`，且与两个变体**都不一致**（`原材料→1401` 而 1401 两版都是「材料采购」全库期末 0.00；`周转材料→1403` 而 1403 两版都是原材料；`跌价准备→1471` 而 6 项目该码是**合同取得成本**，真跌价在 `1416`）。**归类顺序铁律**：`跌价准备/减值准备` 必须最先（客户子科目 `存货跌价准备_库存商品` 若先命中「库存商品」会让 −324.9 万备抵反向抵减原值）；`合同履约/取得成本` 先于泛「成本」；`材料采购/在途物资` 先于 `原材料`（「材料采购」含「材料」）；`库存商品` 组作宽兜底放最后。**F3~F5 及任何涉存货/多变体科目的循环同款处理**
- **🔴🔴 `sa.table()` + 裸 `sa.column()` 的列**没有类型**，UUID 比较必炸（2026-08-04 实测，`get_diagnostics` 与单测替身都查不出）**：`sa.column("project_id")` 被当 VARCHAR 传参 → PG 报 `operator does not exist: uuid = character varying`，且被 fail-open 吞成 WARNING（表现为「补全静默不生效」）。正解 = `sa.column("project_id", PGUUID(as_uuid=True))` / `sa.column("voucher_date", sa.Date)` / `sa.column("debit_amount", sa.Numeric)` 显式声明。**凡用轻量 `sa.table()` 绕开 ORM 的查询都要逐列声明类型**，且必须真实库直跑验证（替身不做参数编码）。
- **🔴🔴 抽凭「客户名称/对方科目/对方明细」三列空是**三种不同成因**，禁一刀切当 bug 修（2026-08-04 真实库实证，项目 `2aa00f57`）**：①**对方科目** —— 前端映射已正确接线，但 `tb_ledger.counterpart_account` **全库 111.8 万行 0 填充** = 数据层缺失非代码缺陷；「按同凭证其它分录派生」不可行（`voucher_no+date` 分组平均 94.8 行、63 组里 40 组有多条对方分录 → 必然算错）②**对方明细** —— 全库无任何对应列 ③**客户名称** —— **真缺陷，有来源却没接**：`tb_aux_ledger`（该项目 273 万行，含 `voucher_no`/`voucher_date`/`account_code`/`aux_name`/借贷金额）可按**五元组**（凭证号+日期+科目+借方+贷方）精确匹配。**必须带金额进键**：只用「凭证号+日期+科目」时 53 个键组里 19 个歧义，加金额后 170/170 全唯一。实测命中率 2203=100% / 2202=100% / 1122=93%（19 条歧义**正确地不猜**）/ 1002=0%（该科目本无客户维度，是正确行为）。落法 = `ledger_sampling_service.enrich_items_with_aux_party`（在 `_ledger_row_to_item` 下游做加法式补全，不动 canonical 查询；歧义只标 `party_ambiguous` 不写值；fail-open + WARNING）。
- **🔴 门控提示指向「下方某区域」时，必须先关掉盖住它的弹窗，否则提示是死信（2026-08-04 抽凭实测）**：R18.7 结论确认门禁在**预览弹窗背后**触发 → 用户看到提示却既看不到也点不到「错报推断与总体结论」区。正解三件套：①弹窗底部按钮**前置** disabled + tooltip 说明原因（与同文件「年审阶段不可覆盖」范式一致）②命中门控时**先关弹窗**再提示 ③**必须补重开入口**（否则用户只能重抽 → 换 seed 破坏可复算留痕）。守卫 `samplingConfirmFillReachability.spec.ts`（16 例含 6 条反向自检）。
- **🔴🔴 `sa.type_coerce(td, sa.JSON)` 配 `sa.text()` 写 JSONB 在 asyncpg 下 100% 失败（2026-08-01 实测，全平台通用）**：抛 `Neither 'TypeCoerce' object nor 'Comparator' object has an attribute 'encode'` —— `type_coerce` 是 SQL 表达式构造器、不是可绑定值，asyncpg 直接拿它去 encode。正解 = `UPDATE ... SET col = CAST(:td AS jsonb)` + `json.dumps(td, ensure_ascii=False, default=str)`。**替身 session 单测查不出**（替身不做真实参数编码），只有真实库能暴露 → `note_template_reflow_service.apply_reflow_section` 带着这个缺陷被标记「完成」且 21 测试全绿，写路径其实从未成功过。守卫范式：源码级断言 `CAST(:td AS jsonb)` 存在 + `type_coerce` 不存在 + `json.dumps` 存在（配 `_strip_comments()` 反向自检，因为踩坑说明注释里会写 `type_coerce`）。**凡「单测全绿但从未对真实库跑过」的写库代码都要按此复核**。
- **🔴 破坏性迁移的安全闸三件套（2026-08-01 legacy 附注迁移实证有效）**：① `--confirm` 二次确认 ② **per-note savepoint**（`async with db.begin_nested()` 逐条 + per-note `try/except` 记 failures 后继续，最外层一次 commit）—— 首次执行 38/38 失败时**0 行写入、无部分状态**，隔离完全生效 ③ **内容闸**：只迁「模板列头齐备」的章节（缺 columns 迁过去投影降级成 `_needs_columns` 只显示行名，**比 legacy 快照更糟**）+ 按序对齐类须显式 opt-in。**备份落 `table_data._template_lineage._legacy_backup` 不落 `template_lineage` 列**（该列已被 `group_note_baseline_service` 当 list 用、`note_auto_trim` 当 dict 用，会冲突）+ 配套 `--rollback`（备份没有还原路径等于没备份）。
- **🔴 「行数守恒被违反」先查是不是冗余副本**（legacy 迁移实测）：113 个章节同时有顶层 `rows` 与 `_tables`，只迁 `_tables` 看似丢 769 行 —— SQL 逐条比对证明 **113/113 顶层 `rows` 与 `_tables[0].rows` 逐字节相同**（legacy 单表表示的冗余副本），丢弃正确。**判「是否丢数据」要比对内容不能只比行数**。
- **🔴 `MagicMock()` 当 `get_active_filter` 返回值 = 潜在假绿**：一旦取数改成 `sa.and_(active_filter, …)`，`sa.and_` 会拒绝非 SA 表达式（"SQL expression for WHERE/HAVING role expected"）→ 被 fail-open 吞成空结果 → 测试「通过」却什么都没测到（F2 gray 测试实测中招）。mock 过滤器一律返回真实 `sa.true()`
- **🔴 「28 个测试全绿」不等于取数能跑**（N5 实证）：`get_active_filter(ctx.project_id)` 单参调用（真实签名 `(db, table, project_id, year)`）→ `TypeError` 被 `except Exception` 吞成 warning → `trial_balance` 恒 0 / `adjudication_prefill` 恒 `None`，而既有测试只测导入可用性/DISPATCH 指向/`_parse_num` 单测，**从不真实调用取数函数**。→ 守卫必须**以真实签名 + 真实 await 调用被测函数并断言返回非零**；另加源码级断言禁单参调用（记得 `stripComments()`，否则修复说明注释里引用的反例会被数成真实调用）
- **🔴 「二选一 / 不适用则删」类披露分支必须做成三态，缺省 = 未判断（2026-07-31 N1 定论）**：源模板的「或：」「不适用的删除」看似布尔，但「审计师还没答」与「答了不适用」是两种状态。缺省直接取某一分支 → 存量项目下一次同步就把另一分支已披露的表**静默删掉**（`_removed_table_keys`）。做法：`'undecided' | 'gross' | 'net'` 持久化三态（上市侧用 `boolean | null`），`undecided` 时全推不删 = 零回归；**不要用「是否被改动过」的启发式**（宿主保存后重挂 Tab、实例级标记归零，K6 已两轮实测失败）。另配 `resolveXBranchTables` 返回 `{pushed, removed}` 且断言两者无交集 ∪ 覆盖全部分支表键
- **🔴 `_removed_table_keys` 只删「上次由本底稿推过」的表**：与 `previouslySyncedTables` 求交集后再发。从未推过的同名表可能由别的底稿承载，越权删会打断对方
- **🔴 前端 radio/按钮选择器的子串陷阱**（2026-07-31 实测踩中）：`'不以抵销后净额列示'` **包含** `'以抵销后净额列示'` → `innerText.includes()` 会命中错误按钮且看起来"点了没反应"。一律用 `innerText.trim().startsWith(...)` 或全等
- **🔴 `validate_formula` 返回的是「错误列表」（空=合法）不是 bool**；且 `prefill_formula_mapping.json` 用的是 **prefill 引擎词汇表**，`ADJ()` 未注册进 `formula_engine._REGISTRY` → 会被报「未知函数」。守卫须按 prefill 词汇表放行并配反向自检（若某天注册了就要求移除豁免）
- **🔴 `preset_library.convert_prefill_presets` 的 `page_key = f"workpaper:{wp_code}"` **忽略 sheet**** → 同一 wp_code 下多个块的同名 `cell_ref` 互相遮蔽，`seed_formula_presets --check` 输出的 `Skipped (duplicate page_key+target_cell): 64` 就是被吞掉的条数。`上年审定数` 在 **25+ 循环**内撞键（D1~D7/E1/F2/G1/G4/G6~G8/G13/H1/H3/I1/J1/J2/K8/L1/L3/M1/N3/N4），属平台级待办
- **🔴 `formula_presets/inventory.json` 是物化产物且已预存在漂移**（2026-07-31 实测 232 页 vs 运行时 255 页，差 23 页来自并发会话）→ 自己的改动若不新增页就**不要重生成**，否则把别人未验证的成品一并提交；用 `convert_prefill_presets()` 运行态输出做守卫，不依赖 inventory
- **🔴 「我的改动从 `git status` 里消失了」≠ 被回退**（2026-07-31 F1 实证）：并发会话的**分层批量 commit 会把本会话的成品一起扫进去并 push**（本次 F1 的 27 个产物分散进 `89c19ea6`/`b8de21e0`/`088dc038`/`11222948`/`bd1f9d26`/`cbafa86d`/`35f728d5` 等 H7/H8/K2 名义的 commit）。判定方法：① 先用 `python -c "open(p,encoding='utf-8').read()"` 确认磁盘内容还在（别用 `read_file`，它对并发改动的文件返回陈旧版本）；② 再 `git log --oneline -1 -- <path>` 看是哪个 commit 收的；③ `git rev-list --count @{u}..HEAD` 确认是否已 push。**不要看到 `git status` 干净就以为丢了改动而重做**
- **🔴 `1401` 是「材料采购」不是存货合计**（2026-07-31 F1 实证）：标准科目表 `1401 材料采购 / 1403 原材料 / 1406 库存商品 / 1416 存货跌价准备`，存货报表行是 `BS-010 = SUM_TB('1401~1499','期末余额')`。用前缀 `1401` 取存货的地方会**恒为 0**（实测两个真实项目该科目均空）→ F1-4「存货余额」与「占存货比重」这项分析从来算不出。**应付账款报表行是 `BS-045`**（`note_template` 里写的 `BS-033` 是陈旧值）。区间口径的叶子求和天然抵减 `1416`（借正贷负下为负），故**不要照抄** `listed_standalone` 公式里的 `- TB('1416')`（会二次扣减）
- **🔴 「只覆盖出现的类别、不清零未出现的类别」在有第二数据源时会让合计翻倍**（2026-07-31 F1 浏览器实测）：F1-1 未录入的性质桶显示的是 **F1-2 明细聚合**值，而 aux 自动归集的行款项性质是占位「其他」→「从四表库带入未审数」只写四表命中的桶时，「其他」继续显示明细**全额**，合计 1,301,918.43 → **2,603,836.86（2 倍）**且性质合计≠账龄合计。修法：对「四表无数据 **且** 无手工值」的桶显式写 0（不销毁手工数据，只清掉同一笔钱的另一种口径），并在 toast 里说明清零了几个桶
- **🔴 `note_check_preset_formulas.json` 的 `note_section` 有陈旧值**（2026-07-31 实证）：`五、7` 下混入 `F65-*`（其他收益，应为 五、65）与 `F82-*`（筹资活动产生的各项负债的变动，应为 五、82）。凡「按 `note_section` 取某章节校验预设」的守卫必须**同时按 `section_title` 过滤**，否则完备性断言会要求实现别的章节的规则
- **🔴 读 SFC 源码的守卫用「固定字符窗口」截函数体必误报**（2026-07-31 实证）：`/function fmtAmount[\s\S]{0,240}?toLocaleString/` 会溢出到下一个函数（`fmtPct` 里合法使用 `toLocaleString`）→ 必须用 `\{([^}]*)\}` 截真实函数体再断言，且对「未匹配到函数体」加反向自检。同族：`stripComments()` 自检不要依赖「某真实文件的注释里恰好有反例」（改造后注释可能已被清掉 → 自检空转），改用**内联 fixture**
- **🔴🔴 `useXFormData` 的 `saveField(itemId, {conclusion})` 与 `setField(sheet, field, value)` 签名完全不同，混传 = 该底稿录入静默永不落库**（2026-07-31 N2 实证，**运行时已验证**）：把 `formData.saveField` 传给期望 `(sheet,field,value)` 的 composable → `item_id` 被写成 `'6'`/`'9'`/`'10'`（sheet 号）、`value` 收到字符串 `'vat-rows'` 故 `conclusion` 为 `undefined`、**真实数据（第三参）整体丢弃**；且这些 Tab 的 `getField` 传的是**正确**的 `formData.getField`（读 `N2-6-xxx`）→ **读写不对称，写错键读对键 = 数据永远读不回来**。`get_diagnostics`/Vite/vitest 全查不出（TS 结构类型对 `(a,b)=>` vs `(a,b,c)=>` 兼容）。已修 3 处：`N2TabVatCalc`(useN2VatCalc) / `N2TabLvt`(useN2Lvt) / `N2TabPropertyTax`(useN2PropertyTax) + `N2TabVatCalc.handleDeclaredChange` 的三参错调。**排查法**：逐个比对「composable 的 `saveField:` 入参签名」vs「组件传入的是 saveField 还是 setField」—— 期望 `(sheet,field,value)` 必传 `setField`，期望 `(itemId,{conclusion})` 才传 `saveField`。**注意别误判**：`useL2/L3/L7VoucherCheck`、`useN2ExportRefund`、`useN2OtherTaxCalc` 的签名本就是 `(itemId,{conclusion})`，传 `saveField` 是**对的**（我曾一度误判为 8 处全错，实为 3 处）。
- **🔴🔴 「四表入库后底稿有数据」这条链路可以被**四层独立缺陷**串联卡死，逐层修完才通（2026-08-01 N2 实测，真实项目 `14fb8c10`，每层单独都足以让链路 100% 失效且四层验证全绿）**：①**契约层** —— 后端 render 返回 `dict[str,float]`，前端消费方写 `Array.isArray(pf) ? pf : null` → dict 恒得 null（`props.htmlData` 是 `any` 故 TS 不报错）；②**取数层** —— `get_active_filter(ctx.project_id)` 单参调用，真实签名是 **async** `(db, table, project_id, year)` → `TypeError` 被 `except Exception` 吞成 warning → 取数恒空且**无任何报错线索**（与 N5 同款，本次 N2 两处都中）；③**归类层** —— `简易计税` 不含「增值税」子串 → `if "增值税" in name` 抓不到 → 落 `other`，增值税少算 74%（源模板附注提示明确要求增值税含「未交增值税/简易计税/转让金融商品应交增值税/代扣代缴增值税」）；④**传参层** —— 宿主漏传 `:html-data` 给子组件 → `props.htmlData` 恒 undefined（同「漏传 projectId」范式）。**外加第五处**：披露表只读 `checklist_responses` 的审定行，而审定表的 render 种子值在用户保存前**并不落库** → 须加 `renderPrefill` 兜底（审定数==未审数，无 AJE/RJE 时成立）。**排查顺序（经验）**：先用 `fetch render-config` 看下发值的**真实容器类型与是否为空**（一步区分①②），再逐个比对宿主模板传参（④），最后拿真实科目名跑 classify（③）。守卫范式：`backend/tests/test_n2_prefill_contract.py`（返回类型/字段名镜像/get_active_filter 全签名/禁手写 project_id 重复过滤）+ `n2HostPropWiring.spec.ts`（扫宿主模板断言 `:html-data` 已传）。
- **🟡 N2 双归一函数互为逆映射但无守卫**（2026-08-01，已加守卫 `n2TaxNormalizeCrossContract.spec.ts` 22 例）：`normalizeTaxLabel`（披露方向→源模板全称 `城市维护建设税`/`车船牌照税`）与 `_normalizeTaxNameForN4`（N4 联动方向→简称 `城建税`/`车船税`）。**有意分叉一处**：`地方教育附加` 披露侧合并进「教育费附加」（源模板只有一行 + 「小税（费）种可合并反映」），N4 侧是独立税种（`TAX_CALC_TABLE_MAP` 有该键、N2-8 三档分别测算）→ 守卫里显式登记为例外并写明依据。**归一函数一律用 `includes` 不用 `===`**：真实 `tb_balance` 科目名带前缀（`应交税费_应交个人所得税`），精确匹配全部落空。
- **🟡 N2 双归一函数互为逆映射但无守卫**（2026-08-01）：`normalizeTaxLabel`（披露方向→源模板全称`城市维护建设税`/`车船牌照税`）与 `_normalizeTaxNameForN4`（N4 联动方向→简称 `城建税`/`车船税`）。**有意分叉一处**：`地方教育附加` 披露侧合并进「教育费附加」（源模板只有一行），N4 侧是独立税种（`TAX_CALC_TABLE_MAP` 有该键）→ 同一笔余额两侧归属不同，属正确但须守卫锁定，否则改一侧另一侧不红。
- **🔴 同一 item_id 被两套口径同写 = 双真源静默漂移**：修上条后 `N2-6-vat-payable` 出现附加分析区（按月/季矩阵）与源模板（一）段同写 → 违反 spec R6.2/R6.3（该键是 N2-8 城建税计税依据唯一真源，口径必须取源模板 C17−C18）。修法 = 附加区改写独立键 `N2-6-analysis-vat-payable` 仅供自身展示，不参与跨底稿联动。
- **🟡 `g7AuxExtraction.pbt.spec.ts` 是随机种子脆弱测试**（2026-07-31）：全量跑偶发失败（反例 = 同名投资方 `"己"` 重复条目 + 浮点 `0.010000000000000002`），单独复跑 2/2 绿。判"是否我引入的回归"先看该文件 `git status` 是否干净 + 单独复跑，别当基线外新增失败。
- **🔴 composable 的 computed 内必须直读 `allResponses.value.get(itemId)`，不能用 `getField(sheet,field)`**（2026-07-31 N2-6 实证）：`useN2FormData.getField` 是普通函数，在 computed 里调用**不保证依赖被追踪** → 写入后 computed 不更新（实测 5 个用例全败）。平台既有范式（`useN2Detail16.rows` / `useN2Adjudication14`）都是 computed 内直读 `allResponses.value.get(...)`，`getField` 只用于**非响应式**路径（`_currentRaw()` 取落库快照）。修法 = 封一个 `readField(sheet,field)` 走 `allResponses.value`。
- **🔴 `ref(new Map())` 会把 Map 包成响应式代理，持有原始 Map 引用直接 `.set()` 会绕过代理**（2026-07-31 实证，**这是测试桩的坑不是实现的坑**，极易误判为实现不响应式）：`const store=new Map(); const r=ref(store); store.set(k,v)` → `computed(()=>r.value.get(k))` **不更新**；改成 `r.value.set(k,v)` 或整体替换 `r.value=next` 才更新。真实 `useN2FormData` 是经 `allResponses.value.set` 写入故无此问题。**写 composable 单测桩时必须让读写都走 `ref.value`**；同类症状（写入后 computed 读不到）先用 3 行探针区分「实现」vs「桩」，别急着改实现（我曾因此白改一轮）。
- **🔴 组件解构 composable「不存在的返回值」= 运行时崩溃，四层验证全查不出**（2026-07-31 N2 实证）：`N2TabDetail.vue` 写 `const { rows, seedDefaultRows, ... } = useN2Detail16(...)` 而该 composable 从未返回 `seedDefaultRows`（解构得 `undefined`），下一行还调用了**全文件未声明**的 `syncSummary()` → 点按钮必 `TypeError: xxx is not a function`。**`get_diagnostics`(Volar) 零诊断 / Vite transform 返回 200（`<script setup>` 里未声明标识符不阻断编译，只在运行时炸）/ vitest 全绿（该分支无测试）/ 全量 8092 例也照过**。检测手法 = **写脚本比对「composable 最外层 `return {}` 键集」vs「组件 `const {...} = useXxx(` 解构键集」**，差集即缺口；重构精简 composable 后必须跑一遍。修法：缺的能力若确有价值就在 composable 补实现（本例补幂等 `seedDefaultRows`），纯冗余调用直接删
- **🔴 并发会话会在同一文件里写出重复 `export function` → 整文件 transform 失败、连带多个测试文件全红**（2026-07-31 实证）：`views/composables/noteDisclosureJump.ts` 出现两个同名 `isN2TaxesPayableNoteSection`（L578 旧 / L781 新）→ esbuild `Multiple exports with the same name` → g13/g14/h1/h8/h9/i1 六个 spec 文件全部 `failed`（不是断言失败而是加载失败）。**`get_diagnostics` 当时查不出，vitest 报的是 Transform failed 而非测试红**。判重复导出的裁决**必须查权威真源 `backend/data/note_template_variant_matrix.json`**（按科目名索引）：本例旧版认 `五、42/八、42`（实为**其他应付款**）、`八、43`（实为**持有待售负债**）且用 `includes('应交税费')` 宽匹配 → 一旦生效会把这两科目附注误判成 N2；新版 `五、41/八、41` 精确 `===` 才对 → 删旧留新。**排查手法**：全量 vitest JSON reporter 里看 `testResults[].status=='failed'` 且 `message` 含 `Transform failed`，再 grep 该符号定位
- **🔴 源码型守卫正则必须覆盖 `as any` 强转绕过**（2026-07-31 实证）：`hostApplicableStandards.spec.ts` 原断言 `/runtime\?\.applicableStandards/`，而 I3/I5/I6 写的是 `(runtime as any)?.applicableStandards?.value` → **三个宿主的死 fallback 一直留着且守卫全绿**。正则要写成 `(?:runtime|runtimeCtx)(?:\s+as\s+any)?\)?\??\.xxx`；另配一条"凡 computed 出该值的宿主必须接共享 composable"的正向断言，防新宿主又抄一份取值链
- **🔴 披露同步定位键不含 `current_standard`，服务端已自守（只拦 entity 维度）**：`sync_from_workpaper` 按 `(project_id, year, note_section)` 定位，跨主体类型推送会静默写进另一变体章节。守卫 = `standard_unification_service.detect_standard_conflict`，冲突抛 `StandardMismatchError`（继承 `ValueError` 故未捕获也被既有 422 兜底）→ 路由 409。**scope 差异（standalone vs consolidated）与 `general`/`default` 等非准则字面量一律放行**，项目查不到准则时 fail-open —— 拦真实污染 + 零误杀。前端 `catch` 静默吞 409 是有意为之（宁可不写也不写错章节）
- **🔴 本机 uvicorn `--reload` 实测「有时生效」**（2026-07-31 改 router+service 后未重启，`/openapi.json` 已含新 schema、409 直接生效；与旧结论"reload 不生效"相反）→ 验后端改动先探 `/openapi.json` 或打一个只读探针确认，别默认要重启也别默认已生效
- **🔴 源码型守卫判「A 在 B 之前」不能用 `indexOf(函数名)` 定位起点**（2026-08-02 G11 踩中）：函数名在**模板里也出现**（`@click="onFallbackToOther"`），从那处起找会命中**别的函数**里的调用 → 断言变成假红/假绿。正解 = `src.indexOf('function onFallbackToOther')` 取声明处再 `slice` 出函数体，并断言「找到了声明」（`toBeGreaterThan(0)`）防正则失效空转。
- **🔴 `report_config` 优先级会让「按名称定位」在个别项目撞码（2026-08-02 G 循环 6 项目实测，非 bug 但需告警）**：`4f6dbc36` 项目 **G8 与 G9 都解析到 `1507`**（该项目把 1507 命名成「其他非流动金融资产」而非「其他权益工具投资」）→ 两循环取同一科目有**双算风险**；`b39809ed`/`4f6dbc36` 的 G11 解析到 **`['5111','6111']`**（客户表旧编码 `5111` 也叫「投资收益」），两码同时有余额时会双算。溯源面板应加**跨循环撞码**告警（现有 `conflicts` 只查 report_config 不一致）。
- **🔴 后端临时探针的两个正确写法**（2026-08-02 踩）：session 工厂是 `from app.core.database import async_session`（**没有** `AsyncSessionLocal`）；`working_paper` 表**无 `name` 列**（查底稿名要 JOIN `wp_index`）。查库优先用 postgres MCP（只读，省一轮写脚本）。
- **🔴 读源码型契约测试必须先 `stripComments()`**：守卫注释里通常会写"为什么不能这么写 xxx()"，被守卫源码里也有同款解释注释 → 正则会把说明文字数成真实调用（J1 接线守卫首版即因此误报 4 例）。**且 `stripComments()` 本身要加反向自检**（断言原始源码里确实含被禁字样），否则计数恒 0 = 断言空转；**范围要覆盖整份 SFC**（`<style>` 里的死选择器同样是漏替换证据，只扫 `<script>` 查不出）
- **🔴 守卫「某控件已全量替换」时断言要容忍多种写法**：同一组件里同类控件有单行属性 / 多行属性 / `v-for` 遍历字段定义等多种形态（J1 上市 3 处单行 textarea vs 国企 1 处多行 + v-for），按"出现次数 == N"写死必在另一变体误红 → 按**渲染点**而非段数断言，正则容忍换行
- **披露同步载荷极易漏合计行**（J1 实证，**其他循环须横向核**）：各循环 composable 普遍把合计/小计做成 `computed`（`summaryTotal` / `xxxSubtotal`），持久化的 `xxxData` 数组**不含合计行** → 组件把 `xxxData` 直接交给 `buildXSyncPayload` 就会让附注每张表**全缺合计行**（交付物缺合计 = 表没编完，而 `columns` 类守卫查不出）。**修法放载荷层不放组件层**（`withTotalRow()` 复用同一 `buildDisclosureSubtotal`，与 UI 合计同源 + 对已带合计行幂等），组件才不会漏。**合计行字面双口径**：底稿 UI 用源模板字面（J1 是「合 计」「合  计」带空格），附注模板是「合计」→ 载荷必须走 `X_NOTE_TOTAL_LABEL` 常量按**本章节实证**取字面（同 D3 `DISCLOSURE_TOTAL_LABEL` 不可全局硬套）
- **J1 复盘四项明细见 `#conventions` §J1 披露复盘沉淀**：明细底稿→披露表按行名带入范式（两趟匹配 / 包含聚合双向 / `absorb` 别名 / 子项跳过）、抽零依赖 leaf 模块消除循环依赖、**spec 三件套格式校验必需章节清单**（`get_diagnostics` 对 `.kiro/specs/**/*.md` 生效）、**PowerShell `>` 重定向会把 UTF-8 中文腌成乱码并落盘**（诊断脚本一律用 `--out` 自己写盘）、`composables/__tests__` 全量 5 例预存在失败基线（L4/D1/F3/F5/H4）
- **🔴 披露子表名契约**：`X_*_SUBTABLE` 每个值必须与 note_template `tables[].name` **逐字一致**，且同步 `columns` 的标签列头 = 该表 `headers[0]`，否则同步出**孤儿子表**（附注 TAB 永空 + 底稿数据丢失）。范式：`k1NoteSubtableContract.spec.ts`（含 headers 无空串 / `_column_groups` 齐备 / 全表 guidance 断言）。K1 曾一次性踩中 5 处错位。
- **🔴 披露同步 `sheet_name` = 源 xlsx 中文 tab 名**（如 `附注披露信息（上市公司）`），非 `F2-note-listed` 式 wp_code、也非 `附注上市` 短名 —— 匹配不上会让附注「打开同步底稿」落到底稿首个 sheet；全平台 N1/K1~K13/J1/I3~I6 统一。**8 种括号写法并存**（F1/F3 半角 / G 系全角 / H·I·J·K·M 系 8 处「国有企业」/ D6 混括号）→ **测试断言必须引用 `X_DISCLOSURE_SHEET_NAME` 常量，写死字面量必再分叉**；守卫 = `disclosureSheetNameRegistry.spec.ts`（常量 ↔ `note_workpaper_sync_registry.json` 逐字 + 禁合成标识/短名，`import.meta.glob` 自动纳新循环）。`X-note-listed` 作 **wp_code**（`_WP_CODE_OVERRIDE` / registry 契约 / sheet 归一化输入样本）是合法用法，别一起改
- **🔴 「有 AI 按钮」≠「AI 能用」，三种静默失效形态（2026-07-31 K 系实证，其他循环须横向核）**：①**marker stub 空转** —— `handleAiGenerate` 只 `emit('save', 'X-ai-trigger', ...)` 写个 checklist marker、从不调端点（K5×2 + K7×2 共 4 个函数），按钮可见可点、**零网络请求**，`get_diagnostics` 与 vitest 全绿；②**`context` 传字符串 → 422** —— `/ai/generate-text` 的 `AiGenerateTextRequest.context` 是 `dict[str,str]`，K3 两版传模板字符串 → 必然 422 且被 `catch {}` 静默吞（同族坑：所有 context 值必须 `String()` 转字符串）；③**prompt 18~22 字无约束** → 诱导自造披露内容。**探测信号**：`ai-trigger` marker 正则 + `context:\s*[`'"]`（后跟引号即字符串）+ `不得虚构` 计数 ≥ `prompt:` 计数。守卫范式 `composables/__tests__/kDisclosureAiWiring.spec.ts`（读源码必先 `stripComments()`，否则守卫注释里的反例会被数成真实调用）。响应体解析统一 `(res.data?.data ?? res.data)?.content`
- **🔴 「该区块是否被改动过」这类启发式在真实宿主里不可靠（2026-07-31 K6 实测两轮均失败）**：宿主保存 checklist 后会**重建 `allResponses` 并可能重挂 Tab 组件** → setup 重跑、实例级标记归零；改成模块级 `Map<wpId, Set<block>>` 后仍出现「同一会话里 add 能识别、delete 识别不到」。→ **条件表清理一律无条件发送 `_removed_table_keys`**，不要用「是否 touched」门控。代价（从未填过的项目该节显示「无数据」而非模板骨架）在「该节只承载本底稿一张表」时可接受
- **🔴 条件表「不推空表」有两种相反语义，判据 = 底稿有没有录入区块（2026-07-31 K7 实测）**：①**无录入区块**（K3 应付利息/应付股利）→ 只跳过、**不进** `_removed_table_keys`（表不属本载荷所有，同章节可能被别的底稿推送）；②**有录入区块的条件表**（K7 国企政府补助明细）→ 无行时不推空表**且必须进** `_removed_table_keys`，否则用户填过再删空，附注**永久残留上次推送的过时明细**（浏览器实测复现：2 表 → 删行后仍 2 表）。修好后实测 2→1 且 `last_sync_at` 二次前移
- **🔴 同一科目两版章节结构可能不对称（2026-07-31 K6 实证）**：持有待售在**上市是一节合并**（`五、11` 资产+负债+减值准备+非流动资产+处置组），**国企拆成两节**（`八、12` 资产 / `八、43` 负债）→ 国企侧必须**发两个 payload**（`sync_from_workpaper` 定位键 `(project_id, year, note_section)` 一次只写一节）。查章节号只认 `note_template_variant_matrix.json`（按**科目名**索引，同一循环可能命中多条），别假设两版一一对应
- **🔴 三级表头的落法 = 把顶层维度提到表名（D1/D6/K1 三处同款）**：`ColumnDef.group` 只支持一层（`group` 含 `/` 会让前端 `activeTableColumns` 渲染崩），源模板三级（如 K1 国企 `期末余额 > 账面余额/坏账准备/账面价值 > 金额/比例/损失率`）拆成「主表 + 续表」两张表承载顶层期别，剩两级用 group；rowspan=2 的独立列**不给 group**（混合分组，前后端都支持，`validate_section` 也认）
- **🔴 压扁的两级表头修复：改 `label` + `group`，绝不改 `key`**（2026-07-31 K1 27 表实操）：md 重建会把两级压成带期别前缀的单级（`期末账面余额`/`上年年末坏账准备`），而同步载荷的行对象**就是用这些中文键**。修法 = `{ key: '期末账面余额', label: '账面余额', group: '期末金额' }` —— 数据键不动、只改显示。改 key 会让整表数据丢落点
- **🔴 `columnsPending` 逃逸阀补齐后必须清空**：`_disclosureSubtableContract.helper` 的「不得残留已补齐的表」断言就是为此设计的 —— K1 27 张表原本全挂豁免名单，columns 一补上该断言立刻转红提醒移出（清空后才真正跑 P1~P6）。看到这条红不是回退，是设计意图
- **🔴 只在单一变体存在的子表不能让两变体共用一份 `X_SUBTABLE`**：K7「其中：递延收益-政府补助情况」只在国企 八、56，共用清单会让**上市侧契约 P1**（子表名须存在于模板）直接红 → 拆 `X_LISTED_SUBTABLE` / `X_SOE_SUBTABLE`，`X_SUBTABLE` 保留作全集；参数化的 `buildXSoeColumns(opts)` 默认必须返回**完整列集**（覆盖率 sweep 空入参调用 + 契约要求每张表都有列定义），载荷侧再按实际推送剔除
- **🔴 批量把 `el-input-number` 换 `WpAmountInput` 后必须 grep 确认归零**（2026-07-30 K3 实测）：同一组件里金额控件有多种写法（单行 vs 多行属性、`v-model` vs `:model-value`+`@change`），正则只命中一部分 → 漏掉的那些**实测录入完全无反应且不触发自动同步**（浏览器录入后 `_last_sync_at` 仍为 null 才发现）。`get_diagnostics` 与 vitest 都查不出
- **🔴 改模板表名/列键前先查前端 map 是否已在消费**（2026-07-30 K 系批 2 三条实证）：①模板表名改名**必须同步 `X_SUBTABLE` 常量**，否则该表下一次同步立刻变孤儿表（K4 `债券名称`→「短期应付债券（续）」中招）；②**模板列键要对齐既有 map，不是反过来** —— K4/K5/K7 的 map 是 `disclosure-columns-coverage-rollout` 批 2 已验证的真源（`bond_name`/`reason`/`begin_amount`），反向改 map 会连带打断其 per-cycle spec；③**底稿尚无录入区块的表不要推空表** —— `_source=workpaper` 下投影器只渲染推来的 `sub_table_data`、不与模板 `_tables` 合并，推一张只有合计 0 的表会把模板骨架整表覆盖，比不推更糟（K3 应付利息/应付股利按此处理，且**不进** `_removed_table_keys`，它们是模板正式表只是暂未接线）
- **🔴 listed 模板 `三、` 章的 `section_number` 被 md 重建截断为 10 字符，是既有真源形态，不要"修正"**（2026-07-30 实证 70+ 条：`三、重要性标准确定方` / `三、投资性房地产【不` / `三、资产减值损失（损` / `三、营业外收入（注：` / `三、营业外支出（注：`）。K11/K12/K13 的常量原写 `资产减值损失` 等 → `sync_from_workpaper` 按 `(project_id, year, note_section)` 定位落空、上市侧新建垃圾章节。**修法是改常量对齐模板**，不是改模板编号（会波及整章 + 并发 spec）。`note_template_variant_matrix.json` 里这三个的 `listed_standalone` 是 `null`，也不能当真源
- **🔴 `X_DISCLOSURE_SHEET_NAME` 半角括号漂移（2026-07-30 openpyxl 逐个核 K 系源 xlsx tab 名实证）**：K2 原写半角 `附注披露信息(上市公司)`/`(国企)` 而源 xlsx 是**全角**（平台 `workpaper_sheet_classification` 亦为全角）→ 附注「打开同步底稿」的 `?sheet=` 精确匹配落空。**K8/K9/K10/K11/K12/K13 六个循环同样是半角**（未修，需另立 spec）；**K1 上市**源 tab 名实为**前半角后全角** `附注披露信息(上市公司）`，常量写的全角全角，也是错的。`disclosureSheetNameRegistry.spec.ts` 只比对「常量 ↔ registry（registry 由常量生成）」，**查不出与 xlsx 的漂移** → 核对必须直接 openpyxl 读 `wb.sheetnames`
- **🔴 `?sheet=` 深链失效 = render-config 的 `sheet_name` 带科目前缀，而调用方传源 xlsx tab 名**（2026-07-30 D6 实证）：附注「打开同步底稿」传 `附注披露信息(上市公司）`，render-config 下发的是 `合同资产附注披露信息（上市公司）` —— 既差科目前缀又差括号宽度。`GtWpRenderer` 的第 3 级兜底原用**未归一**原串做 `endsWith/includes` → 必然落空 → 深链静默回退「底稿目录」（看起来像"披露 Tab 打不开"）。修法 = 纯函数 `utils/normalizeSheetName.resolveSheetNameByDeepLink`（三级：原样 → 归一相等 → **归一后**后缀/包含），`GtWpRenderer` 三处 sheet 定位统一走它。**`X_DISCLOSURE_SHEET_NAME` 常量仍取源 xlsx tab 名不要改**（两者本是不同层）
- **🔴 披露 sheet 分发会被 wp_code 后缀抢占**（2026-07-30 Playwright 实测，D2 中招）：`workpaper_sheet_classification` 里 D2-1 的披露 tab 名是 `附注披露信息（国企）D2-1` / `附注披露信息(上市公司）D2-1` —— **尾部带 wp_code**。`GtD2AccountsReceivable.currentSheet` 先跑 `/D2(?:-\d+)?[A-Z]?$/` → 判成 `D2-1` → 渲染「应收账款审定表」，**披露组件永远挂不上**；`get_diagnostics` 与 vitest 均查不出。修法：抽纯函数 `d2Constants.normalizeD2SheetName()`，「附注」判定**前置**于 wp_code 正则 + 「国企」「国有」都认；守卫 `composables/__tests__/d2SheetRouting.spec.ts`。**其他循环若源模板 tab 名也带 wp_code 后缀，同样中招，须逐个核**
- **🔴 sheet 名「国有企业」≠「国企」→ 国企 TAB 渲染上市组件**：**24 份源模板**（H1~H7 / I1~I6 / J1 J2 / K7 / M1~M9）用的是「附注披露信息（**国有企业**）」，而 `Gt*.vue` 的 `currentSheet` 分发普遍只写 `/附注.*国企/` → 不命中后落到末尾 fallback `name.includes('国企') ? soe : listed` → 同样不命中 → **误判成上市**。H1 实测踩中（`.h1-disc-listed` 挂载、`.h1-tab-disclosure-soe` 完全不挂载），`get_diagnostics` 与 vitest 全绿查不出，**只有 Playwright 实测能发现**。已修 H1/H2/H5/H7/I1/I2（H3/H4/H6/H8/H9/I3 早前已修，I4/I5/I6 用 `/附注.*国/` 本就安全）；守卫 = `__tests__/disclosureSheetDispatch.spec.ts`（重放各组件真实正则 + 自检替身）。**新增循环组件必须两种写法都认**
- **🔴 `text_sections` 的 `#### ` 标题行会被丢弃**（`_is_table_title_paragraph` 认 `#` 即标题，标题本身不进任何输出）→ 把实质披露正文写成 `#### xxx` 会**静默丢失**（H1 上市 R84「政府补助金额为XXX元」曾中招，改为无前缀纯文本后才进 `text_content`）。且 `_match_title_to_table_idx` 第 3 级**包含匹配**会把含表名子串的非标题段吞成表标题 → 游标跳位、后续括注错落到别的表（H1 上市 R85 落到表 4 未办证表）。**结论：多表章节的 TAB 提示不要依赖段落游标，一律 seed 显式声明 `tables[].guidance`**（推断为空的表也才有提示 —— H1 国企 5 表推断结果全空、上市汇总表与经营租出表推断为空）
- **`validate_note_docx_placeholders.py`**（2026-07-29 由 `validate_note_template.py` 更名，旧名曾被误当 JSON 守卫）**只校验 docx 模板的 `【`/使用说明/XXXX 占位符**，其 29/103 失败为既有基线 → **附注 JSON 结构守卫**用 `fix_note_*_structure.py --check` + `test_note_*_structure.py`（前者已挂 `governance-checks.yml` 的 `note-inventory-structure` job）
- **🔴 traceback 出现 `D:\GT_workplan\` = `__pycache__` 跨 checkout 残留**（仓库从 GT_workplan 复制而来，pyc 的 `co_filename` 仍指旧路径，pytest 显示 `???` 行）→ 清 `__pycache__` + `.pytest_cache` 即恢复；**清完仍红的是真 bug，不得当"别的 checkout 问题"忽略**（曾据此误判 8 个失败）
- **🔴 AI section prompt 过短会诱导自造披露内容**：`_SECTION_PROMPTS` 里 18~19 字的笼统 prompt（如「请撰写存货附注「分类说明」披露文字。」）等于放任模型自由发挥 → 每条须 ≥20 字且写明源模板/15 号文口径 + 「不得虚构」约束，并用参数化测试守住（范式：`test_f2_ai_generate.py::test_disclosure_section_supported_and_has_prompt`）。新增 section 必须同时登记 `_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS` + 前端 `F2AiSection` 联合类型 + Tab 内 `AI_TARGETS`，四处缺一即空转
- **🔴 披露页多区块导入导出范式（F2 已落地，其它循环照抄）**：`_f2_disclosure_import_export.py` = 一张 `_Block` 表驱动三形态（`rows` 数组 / `override` 按类别名匹配的覆盖 map / `dr` 三来源列），**一区块一 sheet + 文本域集中「文本说明」sheet**，分发接在既有循环三路由里（沿用 F2-1 模式，不新建 router）。披露 item 全部读写 **`remark`**（`conclusion` 为 null）。两条硬约束：①**行标签重复的表只能按 rowKey 匹配**（数据资源 21 行三段里「1.期初余额」等同名，按标签匹配会静默覆盖 → 首列放「行标识(勿改)」）；②**override/dr 是整表覆盖**（清空某行=撤销覆盖），但整表全空须跳过写库防"拿空模板只导文本"误清。后端镜像前端常量必须用**读 `.ts` 源码的正则契约测试**逐条守（防双真源漂移）
- **🔴 同一批次不得重复提交相同 item_id**：重复会让后端**整批拒绝**、该批全部数据丢失（不是只丢那一条）。**已全量收口**：共享 `useChecklistPersistence` 用 `Set` 天然去重；legacy `useXFormData.debouncedSave` 是单 item 保存无风险；真正暴露点是 `saveBatch(items)` 调用方传重复 id（联动回写「先写整表 JSON、再写汇总字段」最易触发）→ **36 份同形状 `saveBatch` 已统一加按 itemId 去重（后写覆盖先写）**，脚本 `fix_save_batch_dedup.py --check` + CI job `disclosure-sync-hardening`。其它形状（`ChecklistResponse[]` / `{itemId,value}`）语义不同未动
- **🔴 同 item_id 的第二种形状 = 防抖累积器（2026-07-30 浏览器实测中招，`fix_save_batch_dedup.py` 覆盖不到）**：`const pendingItems = ref<any[]>([])` 先 `push` 累积、2s 后整批 PUT。披露表每张动态表整表存成**一个** JSON item，防抖窗口内改同一张表两个格子就必然产生两条同 id → 整批被拒 + `catch {}` 静默吞掉 → **界面有值但库里根本没这个键**（实测连改 4 格后 `D1-disc-soe-class-end-rows` 完全缺失，同步却把界面值推进了附注）。已修 `D1TabDisclosure` + 守卫抓出的 `D4TabDisclosureListed/Soe`；守卫 = `__tests__/disclosureSaveBatchDedupe.spec.ts`（扫 `components/workpaper` 全量源码的 `pending*Items/Payload` 累积器，无去重痕迹即红）。**保存失败必须给用户提示**，纯 `catch {}` 会让数据丢了没人发现
- **🔴 派生列（比例/损失率/账面价值）禁止持久化，必须读时推导**：D1 旧实现把 `ratio` 存进行对象、编辑时用**编辑前**的合计做分母且只重算被编辑行，组件层又把银承+商承的 `ratio` 相加 → 实测「按组合计提坏账准备」显示 **162.50%**（应 100.00%）且错值随同步进了附注；同行 `lossRate` 还被硬编码 0 → 附注显示 `-`。范式：纯函数 `deriveClassRow(s)` / `ratioOf(part, whole)`（`useD1FormulaEngine`）+ 拆 `*RowsRaw` 内部 ref（只持久化录入列）+ 对外 computed 推导（导入路径写入的旧派生值也会被覆盖）
- **🔴 `review-dialog/ai-generate` 请求体是 `{section_id, related_data, existing_content}`、响应是 `generated_text`**：D1 两处写成 `{section, context}` + 读 `.text` → 必然 422 且取不到文本，被 `catch` 吞成「AI生成失败」，**7 个按钮长期空转**（披露 5 + 审定表 2）。平台正解见 `useReviewDialog.ts`。该端点已加 `_SECTION_PROMPTS` + `resolve_review_ai_prompt`（按 `section_id` 精确命中专属 prompt，未登记回退通用 → 存量零回归）；守卫 `test_review_dialog_section_prompts.py` 从前端源码抽 `section_id` 并按 `NOTE_SECTION_KEYS` 自动展开
- **🔴 说明文本域键集必须覆盖 `sectionOrder` 全部子节**（已在 D2 `portfolio`、J1 两 Tab、D1 `transfer`+`badDebtMovement` 三处踩中）：漏一个子节 = 该段说明**无处录入、AI 无处落笔、附注 `text_content` 永远缺这一节**，且不报错、测试不红、只有逐段点开界面才发现。守卫范式 = `d1NoteTextSections.spec.ts`：从源码正则抽三处键集交叉校验（`sectionOrder` ⊆ 文本域键集 / 键集 ≡ `X_NOTE_TEXT_ORDER` / `NOTE_TITLES` 无缺无余 / 每键都有 `onNoteChange` 绑定与 AI 按钮），并断言抽取结果非空防正则失效空转
- **🔴 `text_sections` 里的裸表名会被当披露正文渲染**（D1 实测 6 条：上市 3 + 国企 3）：后端 `disclosure_engine._is_table_title_paragraph` 只认 ① `#` 开头（任意长度）② 非 `#` 时须 **≤20 字且匹配 `（N）xxx` / `N. xxx` 编号**。写成裸表名（`组合计提项目：银行承兑汇票`）既不是标题也没有 `提示/【` 等 guidance 关键词 → 落进 `text_content`，附注正文与 Word 导出凭空多出「只有一个表名」的段落。**正确范式见 `fix_note_ar_soe_structure.TEXT_SECTIONS`**：`#### xxx` 或 `（N）xxx`。各循环补 `text_sections` 时逐条过一遍 `_is_table_title_paragraph` 自检
- **🔴 「校对附注」类只读比对必须按表名定位**：D1 旧 `pickNoteTotal` 遍历所有表取第一个非零数 → 实测抓到「期末已质押的应收票据」合计 80000 与本页主表（0）比较，误报「差异 80000」。改为按 `X_MAIN_SUBTABLE` 表名 + 列元数据里 `end_book_value` 的下标定位；本页主表未取数时提示「未取数」而非报不一致
- **🔴 openpyxl `merge_cells("A1:A2")` 会清空 A2** → 导入导出模板若把末级表头读第 2 行，纵向合并的标签列必然「缺少列」，即**导入自家导出的模板必然失败**（D1 实测）。修法：读表头时第 2 行为空回退同列第 1 行；并加「导出模板 → 立刻用导入校验器验一遍」的往返自检测试。多层表头的第 2 行应由列定义**派生**，不要手写（否则改列名忘改表头）
- **🔴 `_xxxMounted` 一次性防护已全平台清除**（10 处：D3×2/D5/D6/D7/E1/L1×2/L3×2，F2 早前已修）：防护消耗时机取决于「数据是否已加载」→ 切走再切回时吞掉第一次真实编辑（浏览器实测）。Vue `watch` 默认 `immediate:false` 本不需要。脚本 `fix_disclosure_mounted_guard.py --check` + 守卫 `disclosureAutoSyncCoverage.spec.ts`（含自检替身）+ CI job
- **🔴 `el-input` 只绑 `@change` 会抹掉用户键入**（EP 在 nextTick 把 DOM 值重置回 `modelValue`）→ **文本列一律 `@input` 回写**，金额列走 `WpAmountInput`；`<script setup>` 禁 `export interface`（Volar 查不出，只 Vite 500）。详见 `#conventions` §前端 UI 踩坑铁律
- **🔴 附注 `guidance` 只在 seed 路径生效**，`_source=workpaper` 读时投影完全不带它 → 已建读时回填 `note_table_guidance.py`；同块内禁从 ORM 取属性（MissingGreenlet 被吞后 `_tables` 整体丢失）。详见 `#conventions` §后端踩坑
- **🔴 本机 uvicorn `--reload` 实测不生效**（9980 上两个 uvicorn 进程）→ 要 live 验后端改动先重启；**空结果先看 HTTP status**（401 会被 `?.` 吞成 `[]`）。详见 `#conventions`
- **🔴 `tmp_*` 临时文件会被并发会话批量清掉** → 落盘用唯一名、用完即读，别跨多轮依赖同一临时文件，也别在交付文档里引用临时脚本名
- **spec 三件套有硬 schema 校验**（`get_diagnostics` 对 `.kiro/specs/**/*.md` 生效）：requirements 需 `# Requirements Document`+`## Introduction`/`## Requirements`；design 需 `## Overview`/`## Architecture`/`## Components and Interfaces`/`## Data Models`，`## Correctness Properties` 下每条须是 `### Property N: xxx` **标题** + 紧跟 `**Validates: Requirements 1.1, 2.2**`（只认 `X.Y`，写 `R1.1` 不认）；tasks 需 `# Implementation Plan:` + `## Task Dependency Graph` 且该节**必须含 waves JSON 代码块**
- **🔴 改后端 `.json`/`.sql` 配置不触发 `--reload`**（`wp_code_overrides.json`/`prefill_formula_mapping` 等模块级 `load()` 只加载一次）→ 须改一个 `.py` 触发重载或手动重启

## 披露链路脚手架（2026-07-30 新建，做任何循环的披露→附注对接都先用）

- **开工第一步跑诊断**：`python backend/scripts/diagnose/diagnose_disclosure_sheet_vs_template.py --cycle G4`（只读）→ 一次产出①源 xlsx 披露 sheet 的小节切分 + 推测表头（含两行表头）②模板 JSON 该章节的表名/列数/`group`·`flat` 表态/guidance/headers 含 HTML ③比对提示。参数 `--list-cycles` / `--section-listed|soe`（章节号歧义时指定）/ `--account` / `--out`
- **契约测试用 helper**：`composables/__tests__/_disclosureSubtableContract.helper.ts` 的 `runDisclosureSubtableContract({cycle, variants})`，一次跑 5 条 Property（子表名逐字一致 / 章节号存在 / `group`·`flat` 必表态 / 标签纯文本 / 标签列头对齐 `headers[0]`），各循环接入 ~20 行；`columnsPending` 是逃逸阀（强制写理由 + 已补齐必须移出）。自检 spec 用 K1 真实数据反验 helper
- **🔴 `note_template_variant_matrix.json` 按科目名索引、不含 wp_code**：结构是 `accounts[] = {account_key, section_title, variants:{listed_standalone, soe_standalone, …}}` → 查章节号只能用科目名匹配，「债权投资」vs「其他债权投资」这类会歧义，须人工确认
- **源 xlsx 路径规律**：`基础数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/**/{CODE} {科目名}.xlsx`，每循环恰好 1 个，共 349 个
- **模板欠账普遍存在**：G4「五、14」13 张表实测**全部 `columns=0` + 全部无 guidance + 裸 `续：` 表名 + headers 被压扁**（「期末重要的债权投资」模板 2 列 vs 源 xlsx 6 列）→ 补同步链路前先修模板，与 `disclosure-columns-coverage-rollout` 工作重叠
- **K1 同步载荷 columns 也全未表态**（`flat:`/`group:` 各 0 次），两级表头靠模板 `_column_groups` + 后端前缀推断兜住，与 F2 问题镜像

## §变异检验的并发与恢复（2026-08-12 K 循环 Task 25 沉淀）

> 本轮代价：两个变异脚本并行 20 分钟，9 个文件停在变异态、守卫从全绿掉到 21 failed。

- **🔴🔴🔴 「被 stop 的终端」≠「被杀的进程」，后台变异脚本会活着继续改文件**：`control_pwsh_process stop` 只关 shell，`cmd /c python x.py` 的 python 子进程仍在跑（实测存活 20 分钟）。于是两个变异脚本对同一批文件交替「备份 → 改 → 还原」，`.bak` 互相覆盖 ⇒ 谁都还原不回去。**判「后台任务是否结束」一律 `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where CommandLine -like '*脚本名*'`，不看终端状态**；`stop` 之后必须复查并 `Stop-Process -Force` 兜底。
- **🔴🔴 并行变异的四种伪装，单看任一种都会误判**：`GREEN`（取基线时文件已被对方改坏 ⇒ 差集恒空）· `ANCHOR-MISS`（对方正把锚点改掉，我这边读到中间态）· `WRONG-TEST`（对方的变异让别的测试先红）· `restored_clean: false`。**「多条变异同时报 ANCHOR-MISS 且锚点在不同文件」几乎一定是并发污染，不是脚本缺陷** —— 判据 = 用 python 直读磁盘看锚点在不在（跑完之后往往又回来了）。
- **🔴🔴 起变异脚本前先扫「谁还在改文件」**：并发会话的 `mutate_*.py` / `fix_*.py --apply` 同样会污染（本轮另一个干扰源是 `mutate_guard_attribution.py --all`）。**同一时刻只允许一个变异脚本在跑**。
- **🔴 变异被中断后判「有没有留下变异态」不能只看 `--restore` 报「还原 0 个文件」**（`.bak` 可能已被对方清掉）→ **一律跑守卫**，红了再走两级恢复：①写反向还原脚本枚举 `MUTATIONS`，凡「`repl` 命中且 `anchor` 缺失」即判未还原并自动修回（纯文本锚点适用，正则/JSON 补丁跳过）②数据文件跑对应幂等脚本 `--apply`（**注意多数脚本默认 dry-run，必须显式 `--apply`**；`fix_note_k_liability_structure.py` 是例外，无参即写盘）③剩余 JSON 补丁/`.vue` 按守卫失败消息精确定位单修。
- **🔴🔴 删除类修复必须「双重定位」，只按 label 全局匹配会拿正确数据当垃圾清**：修「给 K4 塞了一行账龄」时按 `label == '1至2年'` 全库匹配 → dry-run 报**命中 13 处**，而 `1至2年` 是真实账龄档（应收账款按账龄披露 / 预付款项 / 应付账款 / 十二、母公司各表都合法拥有），只有 §八、48「其他流动负债」那一处是变异塞的。**幸好先跑了 dry-run。** 判据一律「章节号 + 表名 + label」三段定位。
- **🔴 变异脚本的 stdout 才是本次判定的权威，报告 JSON 可能是上一次的残留**：本轮 `_k_cycle_mutation_report.json` 停在被污染那次（`90/1/13/6`, `restored_clean: false`），而干净重跑的 stdout 是 `110/110 RED`。**看报告前先核 mtime**；污染态报告要删掉，留着会误导下一轮。
- **🔴 `cmd /c "python x.py > f 2>&1"` 的输出在进程结束前不落盘**（python 非 tty 下块缓冲）→ 想实时看进度加 `python -u`；`Get-Content` 返回 0 行不代表卡住，查进程与文件 mtime。
