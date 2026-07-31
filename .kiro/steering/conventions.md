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
