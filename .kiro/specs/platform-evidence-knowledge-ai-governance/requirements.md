# 需求文档：附件证据、知识库与 AI 治理闭环

## 需求

### 需求 1：附件证据属性统一
1. WHEN 用户上传附件，THE system SHALL 记录来源、取得日期、提供方、关联底稿、是否关键证据、是否被引用。
2. WHEN 用户删除或替换附件，THE system SHALL 显示影响范围并要求确认。
3. WHEN 附件被底稿、复核、附注、报告引用，THE system SHALL 建立可追溯引用关系。

### 需求 2：附件预览与编辑入口统一
1. THE system SHALL 对用户统一展示预览、编辑、下载、引用四类动作。
2. WHEN 文件可用 OnlyOffice/WOPI 编辑，THE system SHALL 展示在线编辑状态和健康检查结果。
3. WHEN 文件仅可预览，THE system SHALL 使用 vue-office 或后端预览服务并明确只读状态。

### 需求 3：复核意见证据链
1. WHEN 用户提出复核意见，THE system SHALL 支持关联底稿单元格、附件、报告段落、附注表格。
2. WHEN 用户关闭复核意见，THE system SHALL 要求填写关闭依据或关联整改证据。
3. THE system SHALL 统计复核 Aging、重复问题和逾期未回复。

### 需求 4：交付件中心统一真源
1. WHEN 报告、附注、PDF、签发文件、归档文件生成，THE system SHALL 进入交付件中心版本链。
2. WHEN 用户下载或预览交付件，THE system SHALL 使用交付件中心记录的文件与版本。
3. WHEN 终态交付件再次导出，THE system SHALL 新建独立交付物或版本，不能覆盖历史文件。

### 需求 5：知识库真源收口
1. THE system SHALL 明确知识库中文档 DB、文件系统、向量索引之间的主从关系。
2. WHEN 文档被 AI 引用，THE system SHALL 返回来源文档、版本、段落和引用位置。
3. WHEN 知识库文档更新，THE system SHALL 触发索引更新并标记旧索引 stale。

### 需求 6：AI 内容治理
1. THE system SHALL 将 AI 输出分为 suggestion、draft、confirmed、rejected。
2. WHEN AI 内容进入底稿、附注、报告、签发或 EQCR 链路，THE system SHALL 要求人工确认。
3. THE system SHALL 记录 prompt、模型、上下文来源、输出、确认人、确认时间。
4. WHEN AI 服务不可用或返回 stub，THE system SHALL 明确显示降级状态。

## 范围边界
- 不替换现有附件存储后端。
- 不要求所有历史附件补齐证据属性。
- 不让 AI 直接形成审计结论。

## 实施批次

- **P0 核心闭环**：AI 内容确认、附件影响范围、OnlyOffice/WOPI 状态展示、EvidenceRef schema。
- **P1 试点增强**：复核意见证据链、交付件中心统一真源对齐。
- **P2 规模化治理**：知识库真源收口、向量索引 stale、质量问题与培训沉淀。

## Properties / 验收不变量

1. **Property 1：关键证据不可无提示删除**  
   被引用附件删除或替换前必须展示影响范围并要求确认。
2. **Property 2：AI 未确认不可入结论**  
   suggestion/draft 状态 AI 内容不得进入签发、报告、附注正式输出。
3. **Property 3：交付件历史不可覆盖**  
   终态交付件再次导出不得覆盖历史版本。
4. **Property 4：知识引用可追溯**  
   AI 引用知识库内容必须返回文档、版本、段落位置。
5. **Property 5：复核关闭有依据**  
   重大复核意见关闭必须包含关闭说明或 EvidenceRef。

## 依赖关系

- 依赖 `audit-report-deliverable-center` 的版本链与交付件模型。
- 依赖 `platform-linkage-contract-stale` 的 route resolver 和影响范围。
- 被 `platform-role-workbench-quality-loop` 的 QC/EQCR/合伙人工作台依赖。

## UAT 场景

1. 助理上传附件并关联到底稿，删除时看到影响范围。
2. 复核人提出意见并关联附件，关闭时补充整改证据。
3. AI 生成附注草稿，未经确认不可进入正式导出。
4. 用户预览历史交付件版本，确认文件未被覆盖。
