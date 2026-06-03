# 实施计划：report-config-baseline（报表配置主模板回填 + 联动）

> 设计：#[[file:.kiro/specs/report-config-baseline/design.md]]
> 需求：#[[file:.kiro/specs/report-config-baseline/requirements.md]]
> 工作流：Design-First | ~2 天 | 仿附注 GroupNoteTemplateBaseline 范式
> 铁律：三层一致（迁移+ORM+service）；回填必经 admin 审核；router_registry 注册防 404

## 阶段 1 — 数据模型 + service（~1 天）

- [x] 1. ReportConfigBaseline 表 + 迁移
  - V0XX__report_config_baseline.sql（standard/report_type/row_code/candidate_formula/source_project_id/status/version）+ R0XX 回滚
  - report_config 加 is_stale 列（ALTER ... IF NOT EXISTS）
  - CREATE/ALTER 必 IF NOT EXISTS（D6 幂等）
  - _需求: 4.1, 4.2_

- [x] 2. ORM 模型三层一致
  - ReportConfigBaseline ORM Mapped + report_config.is_stale 字段
  - _需求: 4.1, 4.2_

- [x] 3. report_config_service 回填方法
  - suggest_to_master（写候选 pending）
  - review_candidate（admin 审核：通过合并回 standard + 版本 + append_audit_log）
  - diff_vs_master（项目 vs 主模板差异）
  - apply_master_update（keep_local 保留本地覆盖）
  - _需求: 1.1, 1.2, 1.3, 2.4_ _属性: E1, E2_

- [x] 4. 阶段 1 PBT
  - E1 受控传播（pending→approved 才合并）+ E2 本地覆盖保留
  - hypothesis max_examples 10~15
  - _需求: 1.4, 2.4_ _属性: E1, E2_

## 阶段 2 — 主模板→克隆项目联动（~0.5 天）

- [x] 5. EventBus REPORT_CONFIG_MASTER_UPDATED
  - audit_platform_schemas.py 加 EventType
  - update_config 末尾：非 project:* 才发事件
  - _需求: 2.1_

- [x] 6. _mark_cloned_configs_stale handler
  - 订阅 REPORT_CONFIG_MASTER_UPDATED → 标记引用该行的克隆项目 is_stale
  - main 注册 handler
  - _需求: 2.2_ _属性: E3_

- [x] 7. 阶段 2 PBT
  - E3 stale 准确（只标引用该行的克隆项目，不误标无关）
  - _需求: 2.5_ _属性: E3_

## 阶段 3 — 覆盖率 CI + 前端（~0.5 天）

- [x] 8. 覆盖率校验脚本
  - backend/scripts/check/validate_report_config_coverage.py
  - soe/listed × consolidated/standalone 四组合对四表（BS/IS/CFS/EQ）行次无缺漏
  - 复用 report-module-enhancement formula_coverage 模式 + CI 卡点
  - _需求: 3.1, 3.2, 3.3_ _属性: E4_

- [x] 9a. 后端 router 端点 + router_registry 注册
  - POST suggest-to-master / review-candidate / apply-master-update
  - GET diff-vs-master/{project_id} / candidates / stale-status/{project_id}
  - router_registry/report.py 注册（防 404）
  - _需求: 1.1, 2.3, 2.4_

- [x] 9b. 前端 ReportConfigBaselineTab 组件
  - "提交主模板候选" 按钮（项目级配置行）
  - "同步主模板更新" 入口（is_stale banner 提示 N 行 diff + 选择性同步）
  - admin 审核候选列表
  - API 路径定义 + 路由注册
  - _需求: 1.1, 2.3, 2.4_

- [x] 10. 集成测试 + 收尾
  - 项目优化→提交候选→admin 审核→合并回主模板→其他项目受益 全链路
  - 主模板更新→克隆项目 is_stale→banner→选择性同步 全链路
  - ADR + 更新 INDEX.md + memory；单 commit（git status 确认无其他 staged）
  - _需求: 1.2, 2.2_ _属性: E1, E3_

- [x]* 11. 真实环境 UAT（待 start-dev.bat）
  - Playwright：报表配置回填 + 主模板同步提示 端到端
  - 显式标"待环境"不伪绿
  - _需求: 1.1, 2.3_
