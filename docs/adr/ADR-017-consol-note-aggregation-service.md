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

## 勘误（2026-10-13，spec: consol-note-detail-template-and-mapping）

### `fuzzy_merge_same_label` 定位变更

原决策将 `fuzzy_merge_same_label`（SequenceMatcher 阈值 0.85）作为合并附注行级汇总的自动合并算法。经实际业务验证，该算法存在以下风险：

1. **审计口径不可靠**：0.85 阈值无法区分"管理人员薪酬"与"销售人员薪酬"（相似度 ≥0.85），可能导致不同科目金额静默归入错误目标行。
2. **来源行名变更无感知**：子企业将"工资及奖金"改为"员工成本"后，模糊匹配可能仍命中旧目标行，用户无机会审核映射正确性。
3. **无版本化与审计追溯**：自动合并结果不记录映射关系，无法回答"这行金额是哪家企业的哪条来源行贡献的"。

### 新定位

`fuzzy_merge_same_label` **仅用于映射建议的候选排序**，不得作为未经用户确认的权威映射依据。

合并附注的行级汇总须经 `consol-note-detail-template-and-mapping` spec 定义的流程：

1. 用户创建可版本化的合并附注明细模板（目标行有稳定 UUID）；
2. 系统扫描来源行并按结构指纹分组，建议映射（此处复用 `fuzzy_merge_same_label` 排序）；
3. 用户在批量映射弹窗中逐条确认或修改；
4. 确认后的映射规则按 `(project_id, section_id, template_version_id, source_structure_hash)` 持久化；
5. 来源行名变化时映射绑定自动失效（`stale`），系统阻止使用旧规则直到用户重新确认。

### 向后兼容

现有 `aggregate_section` 及其 `fuzzy_merge_same_label` 路径保留，作为：
- 无映射规则时的**降级建议来源**（仅展示，不写入 `consol_note_data`）；
- `generate_full_consol_notes` V2 的 provenance 生成仍走此路径（不影响附注表格渲染数据）。

### 相关 CI 补充

- CI-18: 映射规则的 `target_row_id` 必须存在于绑定的模板版本行列表中
- CI-19: 已确认映射绑定的 `bound_source_hash` 必须与当前来源结构指纹一致，不一致即 `stale`
