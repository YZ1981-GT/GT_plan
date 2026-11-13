# 设计：公式管理残留安全与可用性收口

## 1. 现状证据

- AST 现算 `backend/app/routers/note_templates.py` 12 个路由均无 `Depends`；4 类写操作可匿名执行。
- `NoteTemplateService` 用 `_get_custom_dir() / f"{template_id}.json"`，未验证 UUID。
- `reportEffectiveRows.toRow()` 把 `_upstream` 设为 JSON 字符串，`formulaSuggestions` 却读 `_upstream.formula`。
- `editingId` 除初始化、清空、旧保存函数外从未赋非空；`FormulaInput` 与 `FormulaParamPicker` 所在模板分支不可达。
- `FormulaHistoryTab` catch 后清空列表，模板显示“暂无”；`useTbDetailFormulas` 接受所有 `<600` 状态并静默。
- `fill_all_formulas()` 返回 warnings；`/fill-formulas`、`_exec_seed(report_config)`、CLI 丢弃。

## 2. 安全设计

### ADR-FMRC-01：路由分读写鉴权

静态模板、预设、列表、详情、版本、校验使用 `Depends(get_current_user)`；全局自定义模板写操作使用 `Depends(require_role(["admin", "partner"]))`。路由覆盖身份字段为 `str(current_user.id)`。

### ADR-FMRC-02：模板路径只认 UUID

新增 `_template_path(template_id) -> Path | None`：先用 `UUID(str(template_id))` 解析并标准化，再拼接文件名。非法 ID 的 get 返回 `None`，update/delete/history/rollback 沿用“模板不存在”错误。合法 UUID 行为不变。

## 3. 前端设计

### ADR-FMRC-03：定义对象与摘要分离

`_upstream` 保存白名单字段对象；`_upstream_snapshot` 保存 canonical JSON。建议读取前者，层级判等读取后者。对象复制只保留执行字段，避免把展示字段带入相等判定。

### ADR-FMRC-04：一个真实编辑入口

`FormulaEditDialog` 以 `FormulaInput` 替换普通公式 textarea。`sourceRows` 映射成行次候选，当前行和来源行提取底稿编码。使用统一 L1 目录 `validate()` 计算是否可保存；`FormulaInput` 的校验 watch 设为 immediate，确保打开已有公式时也执行，并在卸载时清理 debounce timer。旧行内模板运行期不可达，删除其 UI 与参数选择器；既有编程式 `saveEdit` 兼容适配只委托同一 `saveReportRowDraft`，不形成第二写入路径。原 `FormulaParamPicker` 已无任何调用方，能力也被真实编辑器内置选择器覆盖，按零调用清单删除并同步组件声明。

### ADR-FMRC-05：读取三态

历史区状态为 loading / error / data-or-empty。每次加载分配递增序号并先清空旧数据；仅当前序号可写状态。取消或陈旧请求不显示错误。TB 明细加载同样先清空上一项目状态，移除宽 `validateStatus`，复用已有 `showFormulaError`。

## 4. 警告传递

`warnings: list[str]` 保持非阻断：
- `/fill-formulas` 原样返回；`/seed` 已位于 `formula_stats`，保持。
- `_exec_seed` 把 warnings 放结果，外层 `seed-all` 原样返回。
- `SeedLoaderPanel` 在结果表显示黄色提示标签，批量提示文案汇总数量；单独重载 report_config 时也展示。
- CLI 在统计后逐条打印 warnings。

## 5. 验证

验证首轮发现 `ThreeColumnLayout.vue` 重复导入 `useMountOnFirstOpen`，Babel 在解析期报重复声明，导致全站 Vite 构建停止。该文件在基线已存在同一缺陷且未被其他会话修改；删除重复导入，不改变首次挂载行为。

- 后端：合法用户、匿名、普通角色、admin/partner；伪造 actor；路径穿越；现有多准则附注测试。
- 前端：有效定义建议、编辑器错误门、历史 error/data/切项目竞态、TB 明细错误、seed warnings 展示；运行相关现有 Vitest。
- 静态：ESLint、单区域 vue-tsc、Python diagnostics/ruff；行数门不得提高。
- 浏览器：`127.0.0.1:3030` 的【测试】项目只读走查公式建议、编辑器语法错误、历史错误/正常态；不发布、不推送、不改共享库。

## 6. 风险控制

- 合法响应形状只增字段，不删字段。
- 不调用会读时种子化的合并附注公式面板。
- 当前三份 S5 未跟踪文件不读取后改写、不暂存、不提交。
- 变更前后按当前分支 HEAD 比较；若并发提交前移 HEAD，逐文件三方合并后复验。