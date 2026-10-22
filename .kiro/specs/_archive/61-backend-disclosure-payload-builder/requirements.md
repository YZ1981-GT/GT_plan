# 后端披露表 payload builder — 需求文档

## 背景

当前附注的行结构（动态行）完全由前端 69 个 `buildXSyncPayload` 函数构建。审计师必须打开底稿的披露表 Tab、做编辑、点保存，前端才会把动态行推到附注。

如果审计师只导入了四表 + 审批了调整分录，但从未打开过某个底稿的披露表，附注里该章节的行就只有模板骨架的固定行（或空），公式推送只能写合计行兜底。

**目标**：在后端实现核心科目的 `sub_table_data` 构建逻辑，不依赖前端就能生成附注的完整行结构。

## 需求

### R1：后端 payload builder 服务

- R1.1：新建 `disclosure_payload_builder_service.py`，按 wp_code 从 `checklist_responses` 读取底稿数据，构建 `sub_table_data`
- R1.2：构建结果与前端 `buildXSyncPayload` 逐字段一致（同一份底稿数据，后端和前端产出的 `sub_table_data` 应相同）
- R1.3：调用入口：`WORKPAPER_SAVED` 事件 handler / 手动「刷新附注」/ 定时批量

### R2：分批实现

69 个科目按优先级分批实现：

- R2.1：**第一批（核心 8 科目）**：E1 货币资金 / D1 应收票据 / D2 应收账款 / F2 存货 / H1 固定资产 / I1 无形资产 / G7 长期股权投资 / K1 其他应收款
- R2.2：**第二批（次核心 15 科目）**：D3~D7 / F1 F3~F5 / H2~H5 / I2~I3
- R2.3：**第三批（剩余 46 科目）**：G 循环其余 / J K L M N 循环全部
- R2.4：每批交付后有独立的端到端测试（checklist_responses → sub_table_data → 附注比对）

### R3：与前端同步的一致性保证

- R3.1：后端 builder 产出的 `sub_table_data` 必须能被 `sync_from_workpaper` 接受（格式一致）
- R3.2：每个 builder 有对应的一致性测试：给定相同的 `checklist_responses` 数据，后端和前端产出的行数 / 标签 / 值必须一致
- R3.3：后端 builder 不替代前端 builder——两者并存，前端同步仍是主路径，后端 builder 是兜底

### R4：性能

- R4.1：单科目 builder < 500ms（主要是读 checklist_responses 的 I/O）
- R4.2：全量 69 科目 builder < 15s（并发执行）
- R4.3：后端 builder 只读 DB，不写 DB（写入由调用方统一走 `sync_from_workpaper`）

## 约束

- C1：不改前端 69 个 `buildXSyncPayload`——它们继续作为前端同步路径
- C2：后端 builder 只从 `checklist_responses` 和 `trial_balance` 读数据，不从 `working_paper.parsed_data` 读
- C3：每个 builder 的分类逻辑（账龄分段、计提方法分类等）从前端 TypeScript 翻译到 Python，不自创
- C4：`checklist_responses` 表无 `is_deleted` 列，查询不加软删除过滤
- C5：`disclosure_payload_builder_service.py` 基础设施已就绪（Phase 1 Task 1~3 完成），实施从 Task 4 + Phase 2 开始
