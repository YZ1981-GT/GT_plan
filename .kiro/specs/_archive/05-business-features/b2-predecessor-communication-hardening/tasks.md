# Implementation Plan: B2 前任沟通模块加固

## Overview

逐一修复 B2 前任/后任 CPA 沟通模块的 7 项复盘缺口：信函中文占位符自动填充、前任基础信息录入、Bundle 流程台账 + 适用性、B2-12 评价底稿结构化、B2-5 决策向导、沟通问题→B50 联动。零 DB 迁移，数据全部存 `checklist_responses`。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": [1, 2] },
    { "wave": 1, "tasks": [3, 4, 5] },
    { "wave": 2, "tasks": [6, 7] },
    { "wave": 3, "tasks": [8, 9] },
    { "wave": 4, "tasks": [10, 11, 12, 13, 14, 15, 16, 17] }
  ]
}
```

## Tasks

- [x] 1. 后端 `_prefill_word_template` 支持中文【】占位符
  - wp_editor_router.py 新增中文占位符替换：【被审计单位名称】/【20××】/【前任会计师事务所的名称】/【前任会计师事务所名称】
  - B2 系列 wp_code 时查询项目级 `B2-predecessor-info`（JSON）填前任所名称 + 联系方式区
  - 空值保留占位符；幂等；原模板不变
  - _Requirements: R1.1, R1.2, R1.3, R1.4_

- [x] 2. checklist_responses 白名单加 `B2-` 前缀（freeform pass）+ Wave0 PBT
  - checklist_responses.py 新增 `elif item.item_id.startswith("B2-"): pass`
  - PBT：P1 幂等 / P2 空值保留 / P4 中文占位符替换正确
  - _Requirements: R1, R4.4, R5_

- [x] 3. `GtB2PredecessorInfo.vue` 前任沟通基础信息录入
  - 表单：前任所名称/联系人/电话/传真/地址/邮编 → 存 `B2-predecessor-info`
  - el-alert 提示先录入再开信函
  - _Requirements: R2.1, R2.2, R2.3_

- [x] 4. `GtB2Bundle.vue` 扩 tab + 流程总览 `GtB2FlowOverview.vue`
  - tabs：基础信息/程序表/流程总览/B2-5 + 动态子底稿
  - 复用 GtBArchitectureTree 三场景泳道 + 状态 tag + 跳转
  - _Requirements: R3.1, R3.2_

- [x] 5. B2 适用性判断（`B2-applicability`）
  - 三开关 firstEngagement/reviewPredecessorWp/ipoReaudit，缺省 true
  - 据此过滤泳道卡片与子底稿 tab（不误删程序表）
  - _Requirements: R3.3_

- [x] 6. `GtB212Evaluation.vue` + componentType `b2-12-evaluation`
  - 9 步了解程序表（第 8 步 5 子项）+ 7 点结论判断矩阵（"是"高亮）
  - AI 辅助 + 复核；持久化 B2-12-steps/conclusions/note
  - wp_code_overrides B2-12 → b2-12-evaluation
  - _Requirements: R4.1, R4.2, R4.3, R4.4_

- [x] 7. 后端 `_b2_12_evaluation.py` render 策略 + 注册
  - 输出 client_name/audit_year + responses_snapshot
  - RENDERER_DISPATCH + dedicated 注册；htmlRendererRegistry 前端映射
  - Wave2 PBT：P5 矩阵高亮契约 / render 冒烟
  - _Requirements: R4_

- [x]* 8. `GtB25Evaluation.vue` 决策向导（替换 bundle 内 GtDForm）
  - 答复三选一互斥 + 未答复催函联动 + 接受决策点选 + 理由
  - 持久化 B2-5-evaluation
  - _Requirements: R5.1, R5.2, R5.3_

- [x]* 9. 沟通问题→B50-1 联动
  - B2-3/B2-11 答复结构化 + pushToB50（eventBus b50:push-risk-factor）
  - 若 B50 无消费入口则记待接线
  - _Requirements: R6.1_

## Wave 4 — 二次复盘补强（A–H）

- [x] 10. (A) B2-12 + Bundle 版本链 + 复核对话（对齐 B60 范式）
  - `useWorkpaperVersionToolbar`+`GtWpVersionTrail`+`useWorkpaperReviewProvide`+`GtWpReviewDialogHost`+`provide('scheduleAutoSnapshot')`
  - B2-12 各 section 加 💬 复核触发 + 版本历史按钮；保存后 scheduleAutoSnapshot
  - _Requirements: 范式对齐_

- [x] 11. (B) B2-12 docx 导出（防归档回归）
  - 后端 `GET /workpapers/{wp_id}/b2-12/export-docx`（python-docx 构建 9 步+7 点+说明+抬头，RFC5987 文件名）
  - 前端 B2-12 导出按钮
  - _Requirements: 归档_

- [x] 12. (C) 信函联系方式填充覆盖合并行
  - `_prefill_word_template` `_fill_contacts` 改段落内按标签定位追加（覆盖 联系电话/传真/地址/邮编 合并行）
  - _Requirements: R1.3_

- [x] 13. (D+E) 函件往来状态追踪 + B2-3 两封区分
  - flow overview 每信函状态（未发/已发函/已回函）+ 发函日/回函日；B2-3 第一封 + 催函日
  - 催函提示（B2-3 已发函 >14 天无回函）；存 `B2-letter-status` JSON
  - _Requirements: 原诊断 #7_

- [x] 14. (F) B2-5 → B1 承接决策软链接
  - B2-5 加 GtIndexChip(B1) + 提示"本评价结论应纳入 B1 业务承接决策"（无 B1 消费者故不发死事件）
  - _Requirements: R5.3_

- [x] 15. (G) B2-12 九步记录附件上传
  - 9 步表加 📎 上传（uploadAttachment），存 attachmentId/name 到 step 模型 + 预览链接
  - _Requirements: 证据留痕_

- [x] 16. (H) flow overview 未生成底稿生成入口提示
  - 点击"未生成"卡片 → ElMessage.info 指引（无 wp 生成 API，作提示）
  - _Requirements: 可用性_

- [x] 17. Wave4 验证（vitest/pytest/get_diagnostics/Vite/Playwright）

## Notes

- 零 DB 迁移：预填信息与结构化数据存 `checklist_responses`（项目级 project_id + item_id）。
- 正确性属性 P1-P8 见 design.md。
- 每波完成后 get_diagnostics 全清 + 相关 vitest/pytest 通过。
