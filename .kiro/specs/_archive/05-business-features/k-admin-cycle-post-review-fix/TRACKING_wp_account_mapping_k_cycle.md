# Tracking Issue: wp_account_mapping.json K 循环编号双轨修正

## 问题描述

`backend/data/wp_account_mapping.json` 中 K 循环编号存在"科目表顺序编号"与"模板文件编号"双轨并存问题：

- **wp_account_mapping 编号**（按科目表顺序）：K2=6601 销售费用 / K3=6603 财务费用 / K8=2241 其他应付款
- **模板文件编号**（按底稿业务分类）：K2=其他流动资产 / K3=其他应付款 / K8=销售费用

运行时以模板文件 sheet 名为准（`审定表K8-1` = 销售费用），wp_account_mapping 的 K 循环编号是历史遗留数据质量问题。

## 影响范围

- **一致的编号（4 个）**：K0 / K1 / K6 / K9
- **需修正的编号（10 个）**：K2 / K3 / K4 / K5 / K7 / K8 / K10 / K11 / K12 / K13

## 上线阻断性

**不阻断当前 spec 上线**。运行时以模板文件 sheet 名为准，prefill_formula_mapping 中两套编号混用但功能正常。

## 修正计划

1. 确认模板文件编号为权威来源
2. 逐条修正 wp_account_mapping.json 中 K 循环 10 个不一致条目
3. 同步更新依赖 wp_account_mapping K 循环编号的下游逻辑（如有）
4. 回归测试确认 prefill / cross_wp_ref / VR 不受影响

## 优先级

P2 — 可延后，不影响功能正确性，仅影响数据一致性和可维护性。
