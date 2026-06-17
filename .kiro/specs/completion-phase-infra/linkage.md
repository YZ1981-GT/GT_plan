# 完成阶段跨模块联动矩阵（A7–A18）

> 权威联动定义。各 spec requirements 中的联动表须与本文件一致或引用本节。

## 原则

1. **P0/P1 不自动写正文**：仅 chip 引用、alert、toast「数据源未就绪」、计数提示
2. **摘要 API 统一前缀**：`GET /api/projects/{pid}/workpaper-summaries/{key}`（待建，plus 阶段）
3. **就绪状态**：✅ 可用 / ⚠️ 部分 / ❌ 未就绪

---

## 联动矩阵

| 消费方 | 数据来源 | 就绪 | 方式 | 阻塞 spec 任务 |
|--------|----------|------|------|----------------|
| A16 跳转页 alert | A13 未更正错报 | ⚠️ | 已有 `misstatements/for-letter` | A16-core |
| A16-7 推荐 | A7 关联交易计数 | ⚠️ | auto_data | A16-lite |
| A16 plus | A8-1 整合提示 | ⚠️ | relatedLinks 手动 | optional |
| A17-1 ch07 舞弊 | A13-4 + A14-1 + issue_tickets | ❌ | 拉取按钮 | A7–A15 core + infra issue API |
| A17-1 ch09 持续经营 | A15-1 调查结论 | ⚠️ | 拉取 | A7–A15 core A15-1 |
| A17-1 ch10 沟通 | A10-1/A10-2 | ⚠️ | 拉取 stub | A7–A15 lite/core |
| A17-1 ch08 KAM | A17-2-1 | ❌ | 引用 | A17-plus |
| A17-1 其他章 | B 系列底稿 | ❌ | 摘要 API | 循环底稿未就绪 |
| A18-2 议题 1/2 | A13/A14 + issue_hints | ⚠️ | 手动 chip + P1 计数 | A18-P1 |
| A18-2 议题 3 | A8 程序表 seq3/4/5 status | ⚠️ | radio 建议值 | A18-P1 + A7–A15 lite |
| A18-1 P2 审计小结 | A17-1 章节 + 审计意见 | ❌ | 生成框架 | **blocked A17-core** |
| A9 弹窗 guidance | A14-1 缺陷计数/等级 | ❌ | 弹窗提示 | A7–A15 core + plus |
| A17 EQCR | A15-1 结论 | ⚠️ | 只读引用 | A7–A15 core |
| A18 议题3 手动 | A8-2 完成状态 | ⚠️ | 状态提示 | A7–A15 lite |
| 审计报告 CW-76 | A16 sign_date | ❌ | push | A16-plus |
| 审计报告 KAM | A17-2-1 | ❌ | 单向 push | A17-plus |

---

## 摘要 API 契约（plus，待实现）

| key | 来源 | 响应要点 |
|-----|------|----------|
| `misstatement` | A13-1 / A13-4 | 错报计数、未更正列表 |
| `control_deficiency` | A14-1 | 缺陷数、重大/重要分级 |
| `going_concern` | A15-1 | 调查结论、疑虑项摘要 |
| `governance_communication` | A10-2 | 沟通事项条数（stub） |
| `related_party` | A7-1 | 交易/往来计数 |

未就绪时返回见 [design.md §摘要 API](../completion-phase-infra/design.md#摘要-api-响应占位plus)。

---

## 全局实施顺序

```
PRE-1（smoke 五件套）
    ├─ A16-lite ∥ A7–A15-lite ∥ A18-P0（程序表+A18-2表单）
    └─ A17-lite（可并行；A17-5 依赖 PRE-4 阶段 1）
         ↓
PRE-4 阶段 1→2（A17-5）→ 3→4（A7–A15 核对表）
         ↓
A7–A15-core（A13/A14/A15 数据源）∥ A16-core ∥ A18-P0 收尾
         ↓
PRE-2 filler
         ↓
A17-core ∥ A18-P1（export-word）
         ↓
A7–A15-plus ∥ A17-plus ∥ A18-P2 ∥ A16-plus（报告/CW-76）
```

---

## 可选子 spec 拆分

以下模块任务仍登记在 [a7-a15-completion-workpapers](../a7-a15-completion-workpapers/tasks.md)，可择机独立 PR 轨道：

| 子 spec | 范围 | tasks 编号 |
|---------|------|------------|
| [a13-misstatement-workpaper](../a13-misstatement-workpaper/requirements.md) | A13 8 sheet Tab 套件 | 17–22, 13 模块 |
| [a14-control-deficiency](../a14-control-deficiency/requirements.md) | A14 七文件缺陷族 | 33–38, 42–43, A14 模块 |

audit JSON 与程序表 JSON 仍以 A7–A15 / A17 为权威源，子 spec 不重复维护。

---

## wp_code 别名

完整表见 [persistence.md §别名](./persistence.md#wp_code-别名与虚拟码)。

---

## E2E

跨 spec 用例矩阵见 [e2e-matrix.md](./e2e-matrix.md)。
