# 实施计划：底稿功能行为联动（wp-functional-actions）

## 概述

分 3 阶段：分类基础设施 → L1 取数填充动作 → L2 文档识别动作。约 3-4 周。

## 任务

- [ ] 1. functional_type 分类基础设施
  - [ ] 1.1 迁移：workpaper_sheet_classification 加 functional_type 列
  - [ ] 1.2 半自动推断工具（sheet 名关键词→functional_type 映射脚本）
  - [ ] 1.3 对现有 3867 行分类数据批量填充 functional_type
  - [ ] 1.4 后端 ACTION_REGISTRY 注册表（functional_type→动作配置）
  - [ ] 1.5 前端 useWpFunctionalActions composable（读 functional_type → 挂动作按钮）
  - [ ] 1.6 render_schema 覆盖率 55%→80%（proposal 第十二章 P2 补漏：批量生成 yaml，利用 workpaper_template_analysis.json 全量输入源）
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 2. L1 截止测试动作
  - [ ] 2.1 参数弹窗组件（设 N 天 + 日期范围）
  - [ ] 2.2 调 CutoffTestService.run_cutoff_test → 结果填回 parsed_data
  - [ ] 2.3 填充后 useCellLocate 定位到新数据行

- [ ] 3. L1 月度分析动作
  - [ ] 3.1 参数弹窗（选末级明细科目 + 月份范围）
  - [ ] 3.2 调 MonthlyDetailService → 填回分析底稿

- [ ] 4. L1 账龄分析动作
  - [ ] 4.1 参数弹窗（账龄区间配置）
  - [ ] 4.2 调 AgingAnalysisService → 填回账龄表

- [ ] 5. L1 抽凭动作
  - [ ] 5.1 参数弹窗（选方式：分层/随机/大额/MUS + 参数）
  - [ ] 5.2 新建"从 tb_ledger 按方式抽样"端点（扩展 wp_sampling_engine）
  - [ ] 5.3 抽样结果填回抽凭表 + 关联 OCR 照片（复用 wp_ocr_fill）

- [ ] 6. L2 合同台账动作（依赖 LLM）
  - [ ] 6.1 上传合同 → LLM 多单据识别（替换正则 _extract_contract_fields）
  - [ ] 6.2 逐份确认 UI（复用 V3 Req6 AiContent 确认流）
  - [ ] 6.3 确认后填回台账 parsed_data

- [ ] 7. L2 凭证 OCR + evidence_group
  - [ ] 7.1 attachment_id 单值 → evidence_group[]（schema 迁移）
  - [ ] 7.2 上传凭证 → OCR + LLM 识别 → 填入 evidence_group
  - [ ] 7.3 逐份确认 + 证据链交叉核对

- [ ] 8. 测试
  - [ ]* 8.1 ACTION_REGISTRY 可扩展性测试（新增类型只配置不改框架）
  - [ ]* 8.2 各动作填充正确性单测
  - [ ]* 8.3 Playwright：打开截止测试底稿 → 点动作按钮 → 弹窗 → 确认 → 数据填入

## 说明

- Task 1 是框架，Task 2-5 是 L1（后端已就绪，补弹窗+填充），Task 6-7 是 L2（依赖 LLM）
- L1 可独立交付（后端 CutoffTest/Monthly/Aging 已有 service+router）
- L2 依赖 vllm-httpx-bugfix + wp-tsj-llm-review 的 LLM 链路
- 依赖 wp-locate-foundation（填充后定位）
