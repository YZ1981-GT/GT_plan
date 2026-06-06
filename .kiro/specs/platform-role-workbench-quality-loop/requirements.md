# 需求文档：五类角色作业台与质量闭环

## 需求

### 需求 1：审计助理作业台
1. WHEN 审计助理进入系统，THE system SHALL 展示我的作业台，聚合今日待办、被退回复核、即将截止、资料缺口、AI 建议。
2. WHEN 助理点击待办，THE system SHALL 直接定位到底稿、附件、复核意见或任务节点。
3. THE workbench SHALL 显示每项任务的来源、截止日、责任人、状态和下一步动作。

### 需求 2：项目经理经营驾驶舱
1. WHEN 项目经理进入项目，THE system SHALL 展示进度、质量、预算、风险四象限。
2. THE dashboard SHALL 显示底稿完成率、复核 Aging、工时预算消耗率、人员负荷、关键风险。
3. WHEN 指标异常，THE system SHALL 支持一键下钻到责任底稿、责任人或复核意见。

### 需求 3：质控闭环工作台
1. WHEN 质控人员查看项目，THE system SHALL 聚合 QC 规则命中、抽查任务、问题整改、质量趋势。
2. WHEN QC 发现问题，THE system SHALL 关联到底稿、单元格、附件、复核记录和责任人。
3. WHEN QC 问题关闭，THE system SHALL 要求填写关闭依据并保留证据链。

### 需求 4：项目合伙人签发风险雷达
1. WHEN 项目合伙人进入签发页，THE system SHALL 仅展示重大事项、未解决复核、关键调整、报告意见、签发阻断项。
2. WHEN 存在 stale、conflict、未确认 AI 内容或未关闭重大复核意见，THE system SHALL 显示签发风险。
3. THE radar SHALL 支持跳转到问题来源并记录合伙人确认。

### 需求 5：EQCR 独立复核工作台
1. WHEN EQCR 进入项目，THE system SHALL 展示重大判断、KAM、持续经营、关联方、集团审计范围、重大调整。
2. THE system SHALL 区分项目组复核意见与 EQCR 独立复核意见。
3. WHEN EQCR 签出，THE system SHALL 要求完成独立复核 checklist。

### 需求 6：质量问题沉淀
1. WHEN 复核或 QC 问题重复出现，THE system SHALL 支持沉淀为问题类型库。
2. WHEN 问题类型被归类，THE system SHALL 支持用于培训、规则优化和项目风险提示。

## 范围边界
- 不重做所有 dashboard，先做统一角色入口 facade。
- 不改变现有复核/QC/EQCR 基础数据模型，必要时增量补字段。
- 不替代人工专业判断。

## 实施批次

- **P0 前置依赖**：等待 ProjectContext、PermissionMatrix、LinkageContract P0 完成后启动。
- **P1 试点增强**：审计助理作业台、项目经理驾驶舱、合伙人签发风险雷达。
- **P2 规模化质量闭环**：QC 闭环工作台、EQCR checklist、问题类型库与培训沉淀。

## Properties / 验收不变量

1. **Property 1：角色区块隔离性**  
   不同角色只看到其职责范围内的 workbench 区块。
2. **Property 2：待办可定位性**  
   每个待办项必须有可跳转目标或明确 missing reason。
3. **Property 3：异常指标可下钻性**  
   任一红色指标必须可下钻到责任对象。
4. **Property 4：重大问题不可无依据关闭**  
   重大复核/QC 问题关闭必须有关联证据或关闭说明。
5. **Property 5：EQCR 独立性**  
   EQCR 批注和结论不得混入普通项目经理复核流。

## 依赖关系

- 依赖 `platform-context-permission-foundation`：角色、职责、权限。
- 依赖 `platform-linkage-contract-stale`：风险雷达和下钻跳转。
- 依赖 `platform-evidence-knowledge-ai-governance`：证据引用和问题关闭依据。

## UAT 场景

1. 审计助理从作业台进入被退回底稿并回复复核意见。
2. 项目经理从驾驶舱发现复核 Aging 逾期并下钻到责任人。
3. QC 从质量问题进入底稿证据并关闭问题。
4. 合伙人从签发风险雷达定位未确认 AI 内容。
5. EQCR 完成独立 checklist 并签出。
