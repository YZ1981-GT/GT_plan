# 需求文档：底稿功能行为联动（wp-functional-actions）

## 引言

底稿有 3 个正交维度：渲染形态（componentType）✅ / 审计循环（audit_cycle）✅ / **功能行为（functional_type）🔴 完全缺失**。一张"应收账款账龄表"= d-form-table + D + aging，系统不知第三维无法自动挂"FIFO 账龄计算"动作。

后端取数能力 80% 已就绪（CutoffTest/Monthly/Aging/Sampling 都有 service+router），缺的是"参数弹窗→填回底稿"这一跳。本 spec 建 functional_type 分类 + 动作面板框架。

## 需求

### 需求 1：functional_type 分类维度
1. THE system SHALL 在 `workpaper_sheet_classification` 表新增 `functional_type` 字段（VARCHAR）
2. WHEN 底稿 sheet 被分类，THEN SHALL 同时标注 functional_type（sampling/cutoff/aging/monthly_analysis/contract_ledger/reconciliation/...）
3. THE system SHALL 提供半自动推断工具（sheet 名关键词→functional_type 映射）

### 需求 2：底稿动作面板框架
1. WHEN 底稿渲染时检测到 functional_type，THEN 工具栏 SHALL 显示对应"动作按钮"
2. WHEN 用户点击动作按钮，THEN SHALL 弹出参数配置弹窗
3. WHEN 用户确认参数，THEN SHALL 调用对应后端取数端点 → 结果填回底稿 parsed_data

### 需求 3：L1 取数填充动作（优先，后端已就绪）
1. **截止测试**：弹窗设 N 天 → 调 CutoffTestService → 填回截止测试底稿
2. **月度分析**：弹窗选末级明细 → 调 MonthlyDetailService → 填回分析底稿
3. **账龄分析**：弹窗设账龄区间 → 调 AgingAnalysisService → 填回账龄表
4. **抽凭**：弹窗选方式(分层/随机/大额) + 参数 → 从 tb_ledger 抽样 → 填回抽凭表

### 需求 4：L2 文档识别动作（依赖 LLM）
1. **合同台账**：上传合同 → LLM 识别（替换正则）→ 逐份确认 → 填回台账
2. **凭证 OCR**：上传凭证照片 → OCR+LLM → 填回抽凭表 evidence_group

### 需求 5：动作注册机制（可扩展）
1. THE system SHALL 提供动作注册表（functional_type → 动作配置：按钮文案/弹窗组件/后端端点/填充逻辑）
2. WHEN 新增 functional_type，THEN 只需配置注册表（不改框架代码）

### 需求 6：render_schema 覆盖率提升
1. THE system SHALL 把 render_schema 覆盖率从当前 ~55% 提升到 ≥80%
2. WHEN 批量生成 yaml render_schema，THEN SHALL 利用 `workpaper_template_analysis.json`（349 模板/2602 sheet 全量输入源）
3. WHEN 新增 functional_type 分类，THEN 对应 sheet 的 render_schema SHALL 同步生成

## 范围边界
- L3 测算型（减值/折旧/计提）并入 6 stub 对话框治理，不在本 spec
- L4 文档型多数已有渲染，按需补联动
- 依赖 wp-locate-foundation（填充后定位到新数据）
- L2 依赖 vllm-httpx-bugfix + wp-tsj-llm-review 的 LLM 链路
