# Implementation Plan: F 循环复核提示词拆分

## Overview

为 F 循环 5 科目创建 ~85 个 sheet-level 复核提示词 Markdown 文件 + 1 个验证脚本。纯数据工作，零代码变更。按科目分组批量创建文件，各科目间完全独立可并行。

## Tasks

- [x] 1. F1 预付账款全部提示词（9 files）
  - [x] 1.1 创建 F1 全部 9 个提示词文件
    - 文件命名对齐线上：`F1-1.md` … `F1-7.md`、`F1-note-listed.md`、`F1-note-soe.md`（非带英文后缀的草稿名）
    - 已按 HTML 现网角色高质量重写：F1-1 审定 / F1-2 明细 / F1-3 调整 / F1-4 实质性分析 / F1-5 长期挂款 / F1-6 关联方 / F1-7 凭证检查 / 附注上市·国企
    - 已去除存货 CAS1 / 1471·1412 串话骨架
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 6. F3 应付票据全部提示词（9 files）
  - [x] 6.1 创建/重写 F3 全部 9 个提示词文件（对齐 HTML：调整/利息/逾期/关联方/凭证检查）
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 7. F4 应付账款全部提示词（11 files）
  - [x] 7.1 创建/重写 F4 全部 11 个提示词文件（含未入账 F4-7、供应商融资 F4-9）
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 8. F5 营业成本全部提示词（10 files）
  - [x] 8.1 创建/重写 F5 全部 10 个提示词文件（含倒轧 F5-7、比较分析 F5-5）
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 9. 验证脚本 + 运行 lint
  - [x] 9.1 验证脚本 `backend/scripts/check/check_f_review_prompts.py` 已存在
  - [x] 9.2 运行验证脚本确认全部 PASS（102 F*.md OK）
    - _Requirements: 13.5, 12.1_

- [ ] 2. F2 核心（审定/明细/调整/分析）— 骨架已生成，待按 F1 标准质量重写
  - [ ] 2.1 创建 F2 核心文件（对齐线上编码）
    - F2-1-adjudication.md, F2-2-detail-summary.md
    - F2-3~F2-13 分类明细各 1 文件（勿把 F2-3 写成调整——调整是 F2-14）
    - F2-14-adjustment.md, F2-16-policy.md, F2-18~F2-20 分析类
    - 科目约定：进销差价=1412，跌价准备=1471
    - _Requirements: 3.x_

- [ ] 3. F2 盘点（F2-21~26，勿用 F2-4~12 旧错误映射）
  - [ ] 3.1 创建 F2-21A/21~26 共 7 文件
    - F2-21A-stocktake-procedure, F2-21-questionnaire, F2-22-plan, F2-23-summary, F2-24-reconcile, F2-25-sample, F2-26-rollforward
    - _Requirements: 4.x_

- [ ] 4. F2 计价+截止（仅已实现 sheet）
  - [ ] 4.1 计价：F2-33/34/35/38/39/40/41~44/52（**不写** F2-36/37/45/46/50/51）
  - [ ] 4.2 截止：F2-29~32（账↔单四象限）
    - _Requirements: 5.x, 6.x_

- [ ] 5. F2 减值+合同成本+IPO+附注
  - [ ] 5.1 减值 F2-47/48/49；合同 F2-55A/55~58；IPO F2-61A/61~72；附注 listed/soe
    - _Requirements: 7.x, 8.x_

- [ ] 10. Checkpoint
  - Ensure all files pass lint, ask the user if questions arise. F2 质量重写仍为后续项。

## Notes

- 纯数据文件创建，零后端/前端代码变更
- ReviewPromptService 通过目录扫描自动发现新文件（Requirement 12）
- 各科目（F1/F2/F3/F4/F5）完全独立，可并行创建
- F2 按**线上** `wp_code_overrides.json` 编码拆分；保留未实现号段 F2-15/17/27/28/36/37/45/46/50/51 不写 prompt
- 验证脚本依赖所有文件就绪，放在最后执行
- 每文件最低 5 个 checklist item，平均目标 ≥8 个
- 科目约定：商品进销差价=1412，存货跌价准备=1471（勿混用）

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1", "5.1", "6.1", "7.1", "8.1"] },
    { "id": 1, "tasks": ["9.1"] },
    { "id": 2, "tasks": ["9.2"] }
  ]
}
```
