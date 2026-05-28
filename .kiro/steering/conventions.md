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

- `workpaper:{wp_code}|{sheet_name}|{cell_range}` — 底稿 cell 级查询
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
