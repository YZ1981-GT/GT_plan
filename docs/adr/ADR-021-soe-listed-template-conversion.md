# ADR-021: 国企↔上市附注模板丝滑切换

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28（v0.6 新增）
**Sprint**: A.5

## 背景

集团内子公司可能 SOE 准则、合并版可能 Listed 准则，原 `note_conversion_service` 仅支持单项目年内切换且不集成 D13 section_id，互转易丢用户编辑。

## 决策

新建 `note_conversion_service` V2 + `consol_cross_template_service.py`：

### 1. 同项目年内切换（基础功能）
- `preview_v2`: 影响章节数 + 用户编辑保留情况 + 字段级 diff
- `execute_v2`: 互转无丢失（CI-20 PBT round-trip 验证）
- 章节差异表 P-7：~150 共有 / ~13 SOE 独有 / ~14 Listed 独有 / ~10 格式略不同

### 2. 集团内子公司不同模板共存
- `Project.template_type` 独立存储
- 合并项目模板由 partner 锁定（不跟随子公司）
- 集团基线按 template_type 区分

### 3. 跨模板合并汇总（B.2）
- `translate_child_section`: 4 类分类处理 common/format_diff/source_only/target_only
- `aggregate_cross_template`: 混合模板汇总
- `build_cross_template_provenance`: cell 标识 `has_cross_template`

### 4. 关键设计
- 章节级映射：基于 D13 section_id 而非 section_number 字符串
- 互转无丢失：用户编辑过的 cells（`_cell_modes[i]==manual`）必须保留
- SOE 独有 → Listed 时数据归档（30 天保留期）
- 格式略不同章节字段映射（如固定资产 movement↔category_sum）

## 备选方案

- ❌ 重新生成全部章节：用户编辑全丢
- ❌ 字符串 section_number 匹配：D13 重排后失效

## 后果

正面：
- 业主中途切换准则零丢失
- 集团内多模板共存（partner 锁合并版）
- CI-20 PBT 验证可靠

负面：
- 模板差异清单（P-7）需审计师维护
- 跨模板汇总 fallback 复杂

## 相关 CI

- CI-20: 国企↔上市互转 round-trip 无丢失 PBT
