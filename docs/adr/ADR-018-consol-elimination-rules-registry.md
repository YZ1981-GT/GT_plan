# ADR-018: 合并附注内部抵销规则注册器

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: B.0

## 背景

合并附注内部往来抵销规则原写死在代码中，无法按业务定制（如不同集团的内部债权债务定义不同）。

## 决策

新建 `consol_elimination_rules.py`，4 种预设规则：
- `internal_ar`: 内部应收账款抵销（按公司对匹配）
- `internal_revenue`: 内部营业收入抵销
- `internal_inventory_unrealized`: 内部存货未实现损益
- `internal_dividend`: 内部分红抵销

规则注册器 API：
- `register_rule(rule_def)`: 动态注册
- `get_rule(rule_type)`: 查询
- `validate_wp_code_exists`: CI-17 校验抵销规则引用的 wp_code 实际存在

规则结构：
```json
{
  "type": "internal_ar",
  "name": "内部应收账款抵销",
  "wp_code": "consol_internal_ar",
  "match_logic": "by_company_pair"
}
```

## 备选方案

- ❌ 写死在代码：不灵活
- ❌ 完全用户配置：规则太复杂用户难维护

## 后果

正面：
- 4 种核心规则覆盖 80% 场景
- 自定义规则可注册（v2 backlog）
- CI-17 防错配（wp_code 不存在 → 拒绝）

负面：
- 跨子公司模糊匹配（label_fuzzy 阈值 0.85）需调优
- 依赖底稿数据完整性

## 相关 CI

- CI-17: elimination_rules 引用 wp_code 必存在
