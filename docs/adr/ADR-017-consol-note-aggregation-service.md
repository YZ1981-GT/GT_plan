# ADR-017: 合并附注汇总服务

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: B.0

## 背景

合并附注原仅 7 个合并专用章节（`consol_disclosure_service.py`），不消费子公司单体附注的 173 个共有章节，导致用户在合并附注里手填数字。

## 决策

新建 `consol_note_aggregation_service.py`：

5 种 aggregation_method：
- `simple_sum`: 简单求和
- `sum_after_elimination`: 抵销后求和
- `top_n_after_elimination`: 抵销后取 top N（如前 5 名客户）
- `weighted_avg`: 加权平均
- `first_n_concat`: 前 N 个文字章节拼接

辅助功能：
- `fuzzy_merge_same_label`: 模糊合并同名（difflib.SequenceMatcher 阈值 0.85）
  - 不同子公司与同一外部客户场景
- `validate_lineage_dag`: DAG 无环校验（CI-16）
- `get_lineage_chain`: 多层递归（孙→子→总）

binding 新 source 类型：`consol_aggregation`

```json
{
  "primary": {
    "source": "consol_aggregation",
    "child_section_id": "section_ar_top5",
    "aggregation_method": "top_n_after_elimination",
    "child_filter": {"scope": "all"},
    "elimination_rules": [...]
  }
}
```

## 备选方案

- ❌ 手填合并附注：用户体验差、易错
- ❌ 简单求和不抵销：合并金额错

## 后果

正面：
- 合并附注 173 + 7 = 180 章节完整（B.1）
- 子公司更新 → 合并自动 stale
- 多层合并 lineage 链可追溯

负面：
- 抵销规则配置复杂（partner 维护）
- 跨模板汇总需特殊处理（B.2 解决）

## 相关 CI

- CI-15: `consol_aggregation` source 必有 child_section_id
- CI-16: 多层合并 lineage 链无环
- CI-17: elimination_rules 引用的 wp_code 必存在
