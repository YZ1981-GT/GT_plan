# 附注模块 v2 Backlog

> 当前 v0.6.2 完成后的待开发项，待优先级评估后启动。
> 创建日期：2026-05-28（Sprint C.5.4）

## 高优先级

### 1. 跨章节联动

**场景**: 章节 A 添加客户后章节 B 自动同步（如「应收账款前 5 名」加 X 后「关联方交易」自动增加 X 的相关条目）。

**实现思路**:
- 模板新增 `_cross_section_refs` 字段
- 触发器：`NOTE_SECTION_DYNAMIC_ROW_ADDED` 事件 → 联动章节 stale
- UI: 「联动章节」标识 + 一键同步按钮

**估时**: 2 人天

### 2. 集团基线 fork & merge

**场景**: 多 partner 并行修改基线，最后合并冲突。

**实现思路**:
- 复用 D11 `note_section_version_tree` 机制扩展到基线级
- `fork_baseline(parent_id, branch_name)` / `merge_baselines(branch_a, branch_b, strategy)`
- 三向 merge 算法（base/ours/theirs）

**估时**: 3 人天

### 3. AI 全自动撰写整章节

**场景**: AI 不只「建议」，而是直接生成整章节（如「重大会计判断」从 H 减值评估底稿 + 上年附注完整生成）。

**实现思路**:
- 多轮对话式生成：先大纲、再各段落、最后表格
- 用户审核+修改+确认
- 培训样本：从过往审计报告反向提取章节 ↔ 底稿映射

**估时**: 5 人天 + LLM 调优

## 中优先级

### 4. 多语言序号

**场景**: 跨境集团需要英文/日文/俄文等附注，序号格式不同（如「I.」「(1)」「①」）。

**实现思路**:
- LEVEL_FORMATS 注册器扩展 locale
- `note_section_numbering_service.render_all(scope, locale)` 加 locale 参数

**估时**: 1 人天

### 5. 多版本图形化合并工具

**场景**: 跨年版本图（D11）当前只有时间线，需要 git-like 分支可视化。

**实现思路**:
- 引入 d3.js / vue-flow 库
- 节点拖拽排版 + 边样式（实线=parent / 虚线=merge）

**估时**: 2 人天

### 6. 离线分发批量打包

**场景**: 集团下 50 子公司一键打包成 zip，含每个子公司专属离线编辑包 + 总指南文件。

**实现思路**:
- 扩展 `note_offline_export_service.export_zip_for_group(parent_project_id)`
- zip 内含 N 个 xlsx + README.md（partner 指引）

**估时**: 1 人天

## 低优先级 / 探索性

### 7. 实时协作（基于 CRDT）

**场景**: 多人同时编辑同一章节（类 Google Docs），不依赖锁。

**估时**: 8 人天 + 架构调研

### 8. 区块链审计追溯

**场景**: 关键章节修改记录上链，不可篡改。

**估时**: 不评估，需可行性研究

## 已确认不做

- ❌ 全自动审计意见生成（AI 责任风险高）
- ❌ 替代 partner 决策的自动 merge（合规要求人工签字）

## 完成度参考

- v1 = v0.6.2，**151 项验收 / 38.5 人天 + 外部 5 人天 / 17 Sprint**
- v2 总估时（不含探索性）: 14 人天
