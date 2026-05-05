# Refinement 迭代打磨机制（多角色视角 PDCA）

## 目的

系统进入"打磨期"后，按**角色视角**轮转复盘，每轮由一个特定角色（合伙人 / 项目经理 / 质控人员 / 审计助理 / 独立复核）独立走一遍系统，找出该角色在"前后端联动 + 实际使用效果"上的断层点，再成稿、再实施、再换下一个角色复盘。

每一轮固定产出 `requirements.md / design.md / tasks.md` 三件套。

## 核心原则

同一个系统，不同角色看到的痛点完全不同：

- 合伙人：签字链条是否闭环、归档包是否合规、风险是否可见
- 项目经理：跨项目多线作战是否顺手、委派/催办/进度汇总是否高效
- 质控人员：规则覆盖、抽查手段、质量评级体系
- 审计助理：新人上手成本、单页面自洽性、AI 助手就位
- 独立复核（EQCR）：独立取证、反向检查、报告前一锤定音

单视角必然有盲区，5 轮轮转才能把盲区叉叉覆盖。

## 轮次节奏

| 轮次 | 角色 | 目录 | 状态 |
|------|------|------|------|
| Round 1 | 合伙人（签字 + 归档 + 合规文档） | `refinement-round1-review-closure/` | ✅ requirements 已起草 |
| Round 2 | 项目经理（多项目作战 + 委派催办 + 简报） | `refinement-round2-project-manager/` | ✅ requirements 已起草 |
| Round 3 | 质控人员（规则覆盖 + 抽查手段 + 质量评级） | `refinement-round3-quality-control/` | ✅ requirements 已起草 |
| Round 4 | 审计助理（新人上手 + 单页自洽 + AI 就位） | `refinement-round4-audit-assistant/` | ✅ requirements 已起草 |
| Round 5 | 独立复核 EQCR（独立取证 + 反向检查） | `refinement-round5-independent-review/` | ✅ requirements 已起草 |
| Round 6+ | 5 轮完成后总复盘，若仍有断层继续补 | 开放 | 待定 |

## 每轮三件套生成规则

1. **单角色视角**：开头写清楚本轮是哪个角色在"走一遍系统"，所有需求以第一人称 "作为 XXX，我希望..." 陈述，不要混入别的角色关切
2. **代码锚定**：每个断层点必须列证据（文件路径+行号/函数名/grep 结果），禁止空讲体验
3. **不许溢出**：一轮 ≤ 20 个可编码任务；超过就拆 Sprint（每 Sprint ≤ 10 任务 + 回归测试 + UAT 才进下一 Sprint）
4. **手动验证单独列**：需要浏览器人工确认的放 spec 末尾"UAT 验收清单"，不占 taskStatus 工作流
5. **不许重复**：Round N 如果重新发现 Round N-1 已列但未修复的问题，补到本轮 tasks.md（说明上一轮漏做），不新建 Round
6. **失败回填**：任务描述中引用的依赖包、类名、API 路径，如与实际不符，起草 design.md 时必须更新 requirements.md 并记录变更日志

## 跨轮依赖矩阵

5 轮需求之间有前置依赖，实施必须按依赖顺序（起草顺序不受限，但实施顺序受限）。

| 后续轮次 | 前置轮次 | 前置条件 | 影响说明 |
|----------|----------|----------|----------|
| R2 需求 5 客户承诺联动 | R1 需求 2 | `IssueTicket.source` 扩展为 enum | R2 新 source `client_commitment` 必须加在 R1 扩展之后，否则枚举表要迁移两次 |
| R2 需求 4 逾期催办 | R1 需求 2 | `IssueTicket.source='reminder'` 复用 | 同上 |
| R3 需求 5 质控整改单 SLA | R1 需求 2 | `IssueTicket.source='Q'` 的 SLA 工作流 | R1 扩展枚举时要预留 Q 的 SLA 覆盖 |
| R5 需求 5 EQCR 门禁 | R1 需求 4 | `SignatureRecord.required_order + prerequisite_signature_ids` | R5 只是把 order 从 3 扩到 5（加 EQCR + 归档），不再动 schema |
| R5 需求 6 审计意见锁定 | R1 需求 4 + R5 需求 5 | `opinion_type` 锁与 `sign_off` gate 联动 | 意见锁定本质是一个状态机新态，见跨轮约束第 3 条 |
| R4 需求 2 AI 侧栏 | R1 需求 2 | AI 发现问题→自动生成 review_comment 工单 | AI 侧栏"一键创建工单"按钮依赖 R1 新枚举值 |
| R3 需求 3 质量评级 | R1 全部 + R2 需求 7 | 工时审批数据、错报关闭率、gate 失败次数作为评级维度 | 评级在 R1/R2 数据齐全后才能有意义输出 |
| R5 EQCR 指标 | R2 需求 7 工时审批 | EQCR 工时 purpose='eqcr' 走工时审批链 | 无审批链则 EQCR 工时无权威数字 |

**实施顺序建议**：R1 → R2 → R3 + R4（并行，相互独立）→ R5。R6+ 做跨轮综合复盘。

## 数据库迁移约定（全轮共享）

按 ADR：baseline=`_init_tables.py` create_all，增量=Alembic autogenerate 补丁。5 轮合计新增约 10 张表 + 20+ 字段，所有迁移遵循：

1. 每个 Round 的 design.md 必须列**新增表清单**与**字段变更清单**，作为该轮 Alembic 迁移脚本的权威来源
2. Alembic 迁移脚本命名：`round{N}_{domain}_{date}.py`（如 `round1_signature_workflow_20260508.py`）
3. 新表 autogenerate 后必须手工 review：外键 on_delete 策略、索引命名、枚举 native 类型
4. 枚举扩展（如 `IssueTicket.source`、`ProjectAssignment.role`）**只能追加新值，禁止删除/重命名**；R1 起草时必须预留所有 5 轮要用到的 source 值，避免多轮迁移
5. 软删除 mixin 与 TimestampMixin 新表必须继承（参考 `ProjectAssignment` 基类）

**R1 起草时预留枚举清单**（避免后续轮迁移两次）：

```
IssueTicket.source: 'L2' | 'L3' | 'Q' | 'review_comment' | 'consistency' | 'ai' | 'reminder' | 'client_commitment' | 'pbc' | 'confirmation' | 'qc_inspection'
ProjectAssignment.role: 'signing_partner' | 'manager' | 'auditor' | 'qc' | 'eqcr'
```

## 跨轮约束（统一约定）

以下约束对 5 轮 requirements 都生效，design.md 必须遵守，否则要求打回：

1. **Notification type 统一字典**：新增通知类型时，同步更新 `backend/app/services/notification_service.py` 的 `NOTIFICATION_TYPES` 常量（如不存在则创建）和前端 `src/services/notificationTypes.ts` 映射表，保持中文 label + 跳转规则两头对齐
2. **权限矩阵双点更新**：新增 role 或动作，同步更新 `backend/app/services/assignment_service.ROLE_MAP`、`role_context_service._ROLE_PRIORITY`、前端 `composables/usePermission.ts::ROLE_PERMISSIONS`，三处缺一即认为权限未完成
3. **状态机不重叠**：审计报告意见类型锁定（R5 需求 6）不新增 `opinion_locked_at` 字段，改为 `ReportStatus` 状态扩展 `draft→review→eqcr_approved→final`，EQCR 签字即切状态；`final` 状态下意见类型不可改是状态机既有语义的延伸
4. **SOD 职责分离**：R5 EQCR 注册到 `sod_guard_service`：同项目内 EQCR 不能同时担任 signing_partner / manager / auditor；违规在 `ProjectAssignment` 创建时立即拒绝
5. **节假日与 SLA**：全系统 SLA 按**自然日**计算，不引入节假日日历服务；跨春节等长假时，质控人工 override 催办次数或延长 due_at，不做自动延期
6. **归档包章节化**：归档包 ZIP 采用数字前缀顺序拼装：`00-项目封面.pdf / 01-签字流水.pdf / 02-EQCR备忘录.pdf / 03-质控抽查报告.pdf / 10-底稿/ / 20-报表/ / 99-审计日志.jsonl`；各 Round 各自定义自己的章节前缀，不挤占 00/01 范围
7. **i18n 角色中文**：新增 role 时同步更新前端 `ROLE_MAP` 字典：`signing_partner=签字合伙人 / manager=项目经理 / auditor=审计员 / qc=质控人员 / eqcr=独立复核合伙人`
8. **焦点时长隐私**：R4 需求 10 的焦点时长**不落数据库**，改为 localStorage + sessionStorage（参考 useAutoSave 模式），每周清零；需要分析时由用户主动导出

## 单轮推进流程

```
1. 读 memory.md + 目标角色关注模块 → 做代码锚定
2. 起草 requirements.md（本文件）
3. 起草 design.md（每个修改点文件+行号锚定，依赖包 npm view 核对）
4. 起草 tasks.md（≤ 20 个任务，Sprint 化）
5. 实施 → 单元测试 + 回归测试 + 属性测试
6. UAT 清单（浏览器手动）走完
7. 本轮关闭，进入下一轮全量复盘（不只看本轮修的东西）
```

## 终止条件

5 轮全部完成后做一次跨角色综合复盘。如果合伙人、项目经理、质控、助理、EQCR 对系统"前后端联动 + 实际使用效果"打分均 ≥ 4.5/5，且剩余改进项都属"锦上添花"（对核心业务流无影响），则终止轮转，转入按需维护模式。否则继续 Round 6+。

## 索引

- Round 1（合伙人）：[`../refinement-round1-review-closure/requirements.md`](./requirements.md)
- Round 2（项目经理）：`../refinement-round2-project-manager/requirements.md`
- Round 3（质控）：`../refinement-round3-quality-control/requirements.md`
- Round 4（审计助理）：`../refinement-round4-audit-assistant/requirements.md`
- Round 5（独立复核 EQCR）：`../refinement-round5-independent-review/requirements.md`

## 变更日志

- v2.2 (2026-05-05) 交叉核验后新增"跨轮依赖矩阵"、"数据库迁移约定"、"跨轮约束"三节；5 份 requirements 对应做硬错修正（见各自 v1.1 日志）
- v2.1 (2026-05-05) Round 2~5 的 requirements.md 全部起草完毕；状态栏更新
- v2.0 (2026-05-05) 重构为"5 角色轮转"模型；原 v1.0 的"四轮主题"（复核/压测/新人/协作）改为角色驱动
- v1.0 (2026-05-05) 初版"四轮主题"规则
