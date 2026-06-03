# 需求文档：report-config-baseline（报表配置主模板回填 + 联动）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§六/§12.3/§21.3.3）
> 工作流：Design-First（从 design.md 派生反推）
> 设计：#[[file:.kiro/specs/report-config-baseline/design.md]]

## 引言

报表配置 `clone_report_config` 把 standard 级配置克隆为项目级 `project:{pid}`，但①项目优化无法回流主模板②主模板更新不通知克隆项目（联动断裂）。本需求仿附注 `GroupNoteTemplateBaseline` 成熟范式，加回填评审通道 + 主模板→克隆项目 stale 通知 + 覆盖率 CI。

核心架构原则：standard 主模板=权威源（单向推送 diff 提示）；项目→主模板走评审门禁（admin 审核非自动双写）。即"双向受控传播"非"双向自动同步"。

## 需求

### 需求 1：项目优化回填主模板（受控）

**用户故事**：作为审计师，我在某项目修对了一个报表公式，希望能提交为主模板候选，admin 审核后让其他项目也受益。

#### 验收标准

1. WHEN 项目级 report_config 优化公式 THEN 可"提交为主模板候选"（写 ReportConfigBaseline status=pending）
2. WHEN admin 审核候选 THEN 通过则合并回 standard 级（带版本号 + append_audit_log 留痕）
3. WHEN 审核驳回 THEN 候选标 rejected，不影响 standard 主模板
4. IF 候选未审核 THEN 不自动合并（受控传播，无自动双写）

### 需求 2：主模板更新通知克隆项目（修 §21.3.3 联动断裂）

**用户故事**：作为审计师，主模板公式修正后，我的已克隆项目能收到提示，避免继续用旧公式。

#### 验收标准

1. WHEN `update_config` 改 standard 级配置（非 project:*）THEN 发 EventBus `REPORT_CONFIG_MASTER_UPDATED`
2. WHEN 事件触发 THEN handler 标记引用该行的已克隆项目 `report_config.is_stale=True`
3. WHEN 克隆项目 is_stale THEN 前端 banner 提示"主模板已更新 N 行，是否同步"
4. WHEN 用户选择同步 THEN apply_master_update 保留项目本地覆盖（keep_local）
5. WHEN 主模板某行更新 THEN 未引用该行的克隆项目不显示 stale 提示（用户可观测：无 banner）

### 需求 3：standard 覆盖率 CI 校验

**用户故事**：作为质控，我希望 CI 自动校验四组合 standard 对四表行次无缺漏。

#### 验收标准

1. WHEN CI 运行 THEN `validate_report_config_coverage` 校验 soe/listed × consolidated/standalone 四组合
2. WHEN 校验四表 THEN BS/IS/CFS/EQ 行次无缺漏（仅 enterprise 兜底除外）
3. IF 某组合缺行 THEN CI 报错（卡点）

### 需求 4：数据模型三层一致

**用户故事**：作为开发者，我要求 ReportConfigBaseline 表 + is_stale 列三层一致（迁移 + ORM + service）。

#### 验收标准

1. WHEN 建 ReportConfigBaseline THEN V0XX 迁移 + R0XX 回滚 + ORM Mapped + service 方法三层齐全
2. WHEN report_config 加 is_stale THEN 迁移 ALTER + ORM 同步（CREATE/ALTER 必 IF NOT EXISTS）
3. WHEN 审计留痕 THEN 复用哈希链**机制** `append_audit_log`（与 formula-engine spec 同一基建），但用**独立 event_type** `report_config_changed`（非 A 的 formula_changed，避免报表配置变更被误记为公式变更）；需在 EVENT_TYPE_SCHEMAS 加该 schema

### 非功能需求

- **NFR-1 仿成熟范式**：复用附注 GroupNoteTemplateBaseline 设计，不重新发明
- **NFR-2 受控非自动**：回填必经 admin 审核门禁
- **NFR-3 本地覆盖保留**：主模板同步不覆盖项目自定义
- **NFR-4 三层一致**：迁移 + ORM + service

## 正确性属性（PBT 守护）

- **E1 受控传播**：项目→主模板必经 admin 审核（pending→approved 才合并）
- **E2 本地覆盖保留**：apply_master_update(keep_local=True) 不覆盖项目已自定义行
- **E3 stale 准确**：主模板某行更新恰好标记引用该行的克隆项目（不误标）
- **E4 结构完整性**：四组合 standard × 四表 seed 数据结构完整（行号连续、row_code 非空唯一、16 组合全覆盖）；V2 对照 CAS 准则校验业务覆盖率
