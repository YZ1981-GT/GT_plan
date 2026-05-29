# ADR-013: 附注 auto_trim v2 三级裁剪

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: A.3

## 背景

原 v1 auto_trim 仅章节级（is_deleted=True），无法处理：
- 章节非空但表格为空（如「应收账款」章节有但前 5 名表全空）
- 文字段落空但章节有其他内容

## 决策

三级裁剪互斥（CI-8）：

| 级别 | 触发条件 | 行为 |
|------|----------|------|
| 章节级 | 全章节空 | `status='not_applicable'` |
| 段落级 | text_content 空 + 全表空 | `is_deleted=True` + `template_lineage.deletion_reason='auto_trim_v2_empty'` |
| 表格级 | 单表 rows 全空 | `table_data._render_as='no_business_paragraph'`（替换为「本期无此项业务」段落） |

互斥语义：每个章节最多被 1 级触发。优先级 章节 > 段落 > 表格。

## 备选方案

- ❌ 永远全章节裁剪：误杀有局部数据的章节
- ❌ 行级裁剪：粒度过细，UI 难表达

## 后果

正面：
- 与致同 PDF「不适用项目请删除」语义一致
- 用户友好（替换段落 vs 突然消失）
- CI-8 互斥保证测试可靠

负面：
- 三级判定逻辑复杂
- 需配合 UI 提示「已自动裁剪 N 章节」

## 相关 CI

- CI-8: auto_trim v2 三级互斥
