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


## Spec 目标设定规约（2026-05-11 沉淀）

- 性能目标必须基于实测基线设定，不能凭直觉
- 设定前先跑一次真实样本拿基线数据（如 YG2101 128MB → pipeline ~660s）
- 目标分两层：架构收益目标（如 activate <1s）+ 端到端目标（如 total <Xs）
- 端到端目标受 IO/网络/PG 物理限制，不能无限压缩
- 目标超标时区分"架构问题"和"物理限制"：前者必须修，后者记录为已知限制
- 示例：YG2101 activate 从 127s→<1s 是架构收益；total 660s 是 PG COPY 物理限制（~5000 rows/s）


## Subagent 调用约束（spec 工作流，三轮复盘 2026-05-16 沉淀）

每次 invokeSubAgent 的 prompt 必须包含以下 4 类边界子句，避免 subagent 自作主张越权：

1. **范围锁定**：明确列出"本任务做什么"和"本任务不做什么"。如果发现 spec 范围扩张需求（如测试期望反推 production 加权限守卫），**只报告不实施**——由 orchestrator 决定是否在新任务里处理。

2. **Bug 处理边界**：如发现 production bug 阻碍当前任务推进：
   - **必须独立报告**（在返回值的 "production_bugs_found" 字段列出）
   - **不在当前 commit 修复**（避免 git log 看不到独立事件 + 测试改动与 bug 修复混淆）
   - 由 orchestrator 决定是否在新任务里修

3. **状态变更可审计**：TD 项 / UAT 状态 / spec 章节措辞变更必须附 commit-style note：日期 / 触发任务编号 / 测试结果摘要。禁止单方面声明"已重新完成"而无审计痕迹。

4. **结构化返回**：禁止大段总结，强制返回 JSON-style 字段：
   ```
   {
     "files_created": [...],
     "files_modified": [...],
     "tests_run": "X passed / Y failed",
     "vue_tsc_status": "exit 0 / errors",
     "production_bugs_found": [...],   // 不修，仅列出
     "scope_expansion_requests": [...], // 测试中发现的 spec 扩张需求
     "td_status_changes": [...]        // 含 commit-style note
   }
   ```

**反例**（template-library-coordination 三轮复盘踩坑）：
- subagent 给 `gt_coding.py` mutation 端点加 `require_role` 守卫（任务只要求"核实端点存在性"，是范围扩张）
- subagent 修复 `gt_coding_service.delete_custom_coding` 的 `soft_delete()` bug 与测试改动混在同一 commit
- subagent 划掉 tasks.md 的 TD 项 + 改 UAT-9 措辞，无审计痕迹

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
