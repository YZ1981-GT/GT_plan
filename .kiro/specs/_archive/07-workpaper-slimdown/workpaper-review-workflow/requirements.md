# Requirements: 复核流程 HTML 化与签署工作流

## Introduction

A21~A25 复核表覆盖 5 个层级（现场负责人/经理/合伙人/质量复核/EQCR），A17-5 完成核对表作为复核前置关卡，A17-7/7A 独立性声明书需推送到每位成员签署。当前这些都是独立 Excel 底稿，需整合到审计生命周期流程中，实现结构化复核+电子签署+自动归档。

## ⚠️ START GATE（实施前必须确认）

系统已有 review_status / review_comment 机制（WorkpaperEditor）和 editing_lock v2（管附注/报告复核）。**本 spec 实施前必须先确认现有复核机制的边界**，避免造第二套复核系统：
- 现有 review_status 是底稿级"待复核/通过/退回"状态机
- 本 spec 的 A21~A25 是"复核人填写的结构化复核记录底稿"（不同层次）
- 设计原则：A21~A25 复核记录**引用**现有 review_status 数据，不替代它

## Requirements

### Requirement 1: 分级复核 HTML 面板

**User Story:** 作为复核人，我在"复核"阶段点击"开始复核"后，系统应展示结构化的复核面板（而非打开 Excel 文件）。

#### Acceptance Criteria
1. EACH 复核级别（A21~A25）SHALL 对应一个 HTML 结构化复核面板
2. THE 面板 SHALL 包含：检查要点列表（逐项勾选是/否/不适用）+ 关联底稿清单（自动列出本人负责范围底稿及状态）+ 复核意见文本区
3. THE 系统 SHALL 按角色自动匹配面板版本：现场负责人→A21、经理→A22、合伙人→A23、质量复核→A24、EQCR→A25
4. THE 系统 SHALL 同时按业务类型匹配子版本（财报审计/内控审计）
5. THE 复核要点 SHALL 从模板 Excel 中提取（可配置，非硬编码）

### Requirement 2: A17-5 完成核对表前置关卡

**User Story:** 作为合伙人，我在点击"完成复核/签发"时，系统应自动弹出完成核对表确认。

#### Acceptance Criteria
1. WHEN 合伙人级别复核人点击"完成复核"时，THE 系统 SHALL 弹出对应 A17-5 核对表
2. THE 核对表版本 SHALL 按项目类型自动选择（一般→5-1、内控→5-2、IPO→5-3、新三板→5-4）
3. THE 核对表中可自动校验的项 SHALL 从系统状态取数（如"所有底稿是否已复核"→从 review_status 统计）
4. THE 用户 SHALL 逐项确认通过（全部通过才放行签发）
5. IF 有未通过项，THE 系统 SHALL 阻止签发并提示原因

### Requirement 3: A17-7 独立性声明书电子签署

**User Story:** 作为项目经理，我需要系统自动推送独立性声明书给每位团队成员签署，并追踪签署进度。

#### Acceptance Criteria
1. THE 系统 SHALL 从 project_assignments 自动识别需签署的成员列表
2. EACH 成员登录后 SHALL 在"我的待办"看到"独立性声明待签署"任务
3. THE 成员点击后 SHALL 看到声明条款 + 电子确认按钮（相当于签字）
4. THE 系统 SHALL 记录签署时间戳 + 签署人 ID
5. THE 项目经理/合伙人 SHALL 可查看签署进度面板（谁签了/谁没签/催办）
6. A17-7A 版本 SHALL 按角色推送给专委会审核委员（而非项目团队成员）
7. WHEN 全员签署完成，THE A17-7 底稿 SHALL 自动标记为"完成"

### Requirement 4: 复核记录归档与导出

**User Story:** 归档时需要将复核记录导出为致同标准格式。

#### Acceptance Criteria
1. WHEN 复核完成后，THE 系统 SHALL 自动生成只读归档文件（PDF 或 Excel）按 A21~A25 格式
2. THE 归档文件 SHALL 包含：逐项勾选记录 + 复核意见 + 复核人姓名 + 日期 + 电子签名标识
3. THE 系统 SHALL 支持导出空白模板（Excel）供线下填写
4. THE 系统 SHALL 支持导入已填模板（解析勾选+意见回写系统）
5. THE 系统 SHALL 支持将系统内记录再次导出为标准 Excel

### Requirement 5: 复核流程与审计生命周期联动

#### Acceptance Criteria
1. THE 审计生命周期"复核"阶段进度 SHALL 从各级复核完成状态计算
2. WHEN 所有级别复核+A17-5核对+A17-7签署全部完成，THE "复核"阶段 SHALL 自动标100%
3. THE 生命周期"委派执行"阶段进度 SHALL 从底稿编制完成率计算
4. THE A1 程序表相关项 SHALL 联动复核完成状态
