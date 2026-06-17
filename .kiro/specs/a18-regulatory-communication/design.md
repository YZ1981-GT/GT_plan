# A18 监管沟通函 — 设计文档

## 架构决策

### 双模式处理
- A18-1 → `WpPopupDocxEditor` 弹窗（纯信函，预填充下载）
- A18-2 → `GtRegulatoryLetter` 专用组件（结构化表单）

### componentType: `regulatory-letter`
仅 A18-2 使用。在 htmlRendererRegistry 注册，`_WP_CODE_OVERRIDE` 只加 A18-2。

### 前端组件：GtRegulatoryLetter.vue
三段式布局：
1. **表头区**：监管机构名称（输入框/下拉：证监会XX局/银监会/其他）+ 公司名（自动）+ 年度
2. **议题卡片区**：4 个可折叠卡片
   - 适用性开关（Y/N toggle）
   - 议题 3 额外：三选一 radio（不一致/错报/两者）
   - 描述输入框（textarea，纯文本+换行）
   - 手动引用按钮（选择关联底稿 wp_code，如"引用 A13 #3"）
3. **签名区**：事务所名称（固定"致同"）+ 合伙人（从项目人员自动带入）+ 日期
4. **工具栏**：导出 Word 按钮 + "未完成项检查"按钮

### 数据存储
复用 `checklist_responses` 表：
- item_id: `A18-2-001`~`A18-2-004` 对应 4 个议题
- conclusion: `Y`/`N`（是否适用）
- remark: 描述内容（纯文本，`\n` 换行）
- wp_ref: 手动引用的关联底稿编码（如 `A13,A14-1`）

表头信息额外存储：
- item_id: `A18-2-header`
- remark: JSON 字符串 `{"regulator":"证监会XX局","sub_choice_3":"inconsistency"}`

### Word 导出引擎

**颜色语义处理流程**：
1. 复制模板到临时文件
2. 扫描全部段落：
   - 红色段落 → 替换占位符（`XX` → 实际值，`201X` → 年度）
   - 蓝色段落 → 检查对应议题是否适用：
     - 适用且用户填了描述 → 替换蓝色文字为描述内容（字体改黑色）
     - 适用但未填 → 保留占位符（警告未完成）
     - 不适用 → 删除整段
3. 不适用议题：从标题（"N、xxx"加粗行）到下一个标题之间的所有段落删除
4. 注释表格（doc.tables 中的 1x1 表格）→ 全部删除
5. 签名区：替换 `XX` 为合伙人姓名 + 日期
6. "未完成项"检测：扫描最终文档，仍含 `XX`/`201X`/`×` 的段落列表→返回给前端弹窗

### 联动取数（P1）
- `fraud_issue_count`：`SELECT count(*) FROM issue_tickets WHERE category='fraud' AND project_id=?`
- `legal_violation_count`：`SELECT count(*) FROM issue_tickets WHERE category='legal' AND project_id=?`
- `other_info_status`：读 A8 程序表 step 3/4/5 的 status（completed/in_progress/pending）

### 不做
- 不做富文本编辑（纯文本满足监管函需求）
- 不为 A18-1 新建组件（弹窗够用）
- P0 不做自动联动取数

## 技术方案

### 后端
- `backend/app/services/regulatory_letter_service.py`：Word 导出 + 未完成项检测
- 复用 `checklist_responses` 端点存取议题数据
- 新增 `GET /api/projects/{pid}/working-papers/{wp_id}/regulatory-letter/export`
- 新增 `GET /api/projects/{pid}/working-papers/{wp_id}/regulatory-letter/check-incomplete`

### 前端
- `GtRegulatoryLetter.vue`：主组件
- 注册到 htmlRendererRegistry（componentType = `regulatory-letter`）
- `_WP_CODE_OVERRIDE['A18-2'] = 'regulatory-letter'`（仅 A18-2）
