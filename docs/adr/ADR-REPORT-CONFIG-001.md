# ADR-REPORT-CONFIG-001: 报表配置主模板回填 + 联动设计

**状态**：已采纳  
**日期**：2026-06-01  
**关联 spec**：`.kiro/specs/report-config-baseline/`  
**关联需求**：Requirements 1.1~1.4, 2.1~2.5, 3.1~3.3, 4.1~4.2

---

## Context（背景）

报表配置 `clone_report_config` 把 standard 级配置克隆为项目级 `project:{pid}`，存在两个缺口：

1. **项目优化无法回流主模板**（§12.3）：某项目修对了一个公式，只留在 `project:{pid}`，其他项目不受益
2. **主模板更新不通知克隆项目**（§21.3.3 联动断裂）：standard 主模板升版后，已克隆项目继续用旧公式，审计师不知道

附注侧已有成熟的 `GroupNoteTemplateBaseline` 范式（apply/diff/upgrade/feedback 双向机制），报表侧缺等价物。

---

## Decision（决策）

仿附注 `GroupNoteTemplateBaseline` 范式，实现**受控双向传播**（非自动双写）：

### 回填通道（项目→主模板，受控）

- `suggest_to_master`：项目级优化提交为主模板候选（写 `ReportConfigBaseline` status=pending）
- `review_candidate`：admin 审核门禁（通过才合并回 standard 级 + 版本号 + `append_audit_log` 哈希链留痕）
- 候选未审核不自动合并（E1 受控传播属性）

### 主模板→克隆项目联动（单向派生）

- `update_config` 改 standard 级（非 `project:*`）→ 发 EventBus `REPORT_CONFIG_MASTER_UPDATED`
- handler `_mark_cloned_configs_stale`：标记引用该行的克隆项目 `is_stale=True`（E3 不误标）
- 前端 banner 提示 N 行 diff + 选择性同步
- `apply_master_update(keep_local=True)`：保留项目本地覆盖（E2 属性）

### 覆盖率 CI 校验

- `validate_report_config_coverage.py`：soe/listed × consolidated/standalone 四组合对四表行次无缺漏

### 数据模型

- 新表 `report_config_baseline`（候选表：standard/report_type/row_code/candidate_formula/source_project_id/status/version）
- `report_config` 加 `is_stale` 列（主模板更新→克隆项目标脏）
- 审计留痕用独立 `event_type='report_config_changed'`（非 formula-engine 的 `formula_changed`）

---

## Consequences（后果）

### 正面

- **回填通道**：项目优化可回流主模板，其他项目受益（解决 §12.3）
- **stale 通知**：主模板更新后克隆项目收到提示，避免继续用旧公式（解决 §21.3.3）
- **覆盖率 CI**：四组合 standard 行次无缺漏，防止配置遗漏
- **本地覆盖保留**：同步不覆盖项目已自定义行，尊重项目级定制
- **仿成熟范式**：复用附注 GroupNoteTemplateBaseline 设计模式，不重新发明

### 负面

- **admin 审核增加工作量**：每个候选需 admin 人工审核（受控传播的代价）
- **stale 标记可能累积**：若项目长期不同步，stale 行会持续增长（需前端引导用户处理）
- **EventBus 依赖**：handler 依赖 EventBus 异步分发，极端情况下可能延迟标记

---

## 范式映射（附注侧 → 报表侧）

| 附注侧（已有） | 报表侧（本 ADR） |
|---------------|-----------------|
| GroupNoteTemplateBaseline 表 | ReportConfigBaseline 表 |
| apply_baseline | apply_master_update |
| diff_baseline | diff_vs_master |
| suggest_feedback | suggest_to_master |
| upgrade_baseline | EventBus stale 通知 |

---

## 回滚影响（R040）

执行 `R040__report_config_baseline_rollback.sql` 后：

| 影响 | 说明 | 缓解措施 |
|------|------|---------|
| `report_config_baseline` 表被删除 | 所有候选记录丢失（pending/approved/rejected） | 回滚前导出候选数据 |
| `report_config.is_stale` 列被删除 | ORM 模型引用该列会报 `NoSuchColumnError` | 回滚前需同步注释/删除 ORM 字段 + 相关 service 方法 |
| 前端 ReportConfigBaselineTab 页面 | API 端点 404（router 仍注册但 service 报错） | 回滚前需禁用前端路由或移除 router 注册 |
| EventBus handler | `_mark_cloned_configs_stale` 写 is_stale 列失败 | handler 内已有 try/except，不阻断其他事件处理 |

**建议回滚顺序**：① 移除 router_registry 注册 → ② 注释 ORM is_stale 字段 → ③ 执行 R040 SQL → ④ 重启服务
