# Implementation Plan: J 循环总调度（j-cycle-orchestration）

## Overview

J 循环（职工薪酬循环）含 **3 个子 spec**（J1–J3），无独立 J0 函证 spec。本 spec **不实现业务代码**，只定义跨 spec 的 wave 编排、子代理并行策略、跨循环依赖与验收闸门。

| Spec | 目录 | 科目/特征 | 复杂度 | 跨循环联动 |
|------|------|-----------|--------|------------|
| J1 | `j1-employee-compensation` | 2211 负债贷方 + 月度12列 + 5类检查 + 薪酬测算 | **最高** | → K8/K9 |
| J2 | `j2-defined-benefit-plan` | 2221 负债 + DBO 精算 + ISA620 | 高 | → B51 |
| J3 | `j3-share-based-payment` | **无独立科目** BS 定价 + 等待期分摊 | 中（Vue 最简） | → M4 / J1 |

**锚定顺序**：J3（3 Tab、跨科目模式）→ J2（精算引擎）→ J1（全循环最大、依赖 K8/K9 skeleton）。

**前置依赖（跨循环）**：
- J1 `wave-8` 前：K8/K9 至少完成 `wave-1`（registry + GtIndexChip 目标存在）
- J2 `wave-8` 前：B51 会计估计底稿 skeleton
- J3 `wave-8` 前：M4 资本公积 + J1 skeleton（权益/现金分流）

## Meta Task Dependency Graph

```json
{
  "max_parallel_subagents": 3,
  "waves": [
    {
      "id": "meta-wave-0",
      "name": "全循环 Phase0 双源输入",
      "parallel": true,
      "max_agents": 3,
      "specs": [
        "j1-employee-compensation",
        "j2-defined-benefit-plan",
        "j3-share-based-payment"
      ],
      "per_spec_waves": ["wave-0"],
      "notes": "3 子代理各跑 openpyxl + md；无共享文件冲突"
    },
    {
      "id": "meta-wave-1",
      "name": "共享注册批量（串行）",
      "parallel": false,
      "specs": ["_batch_j_registration"],
      "tasks": ["M.1.1"],
      "notes": "🔴 禁止多子代理并行写 htmlRendererRegistry / wp_code_overrides / VALID_COMPONENT_TYPES / router_registry"
    },
    {
      "id": "meta-wave-2",
      "name": "锚定模板 J3 单 spec 全流程",
      "parallel": false,
      "specs": ["j3-share-based-payment"],
      "per_spec_waves": ["wave-1", "wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "notes": "Vue 仅 3 Tab；验证跨科目 EventBus（无 writebackTB）模式"
    },
    {
      "id": "meta-wave-3",
      "name": "J2 精算单路",
      "parallel": false,
      "specs": ["j2-defined-benefit-plan"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "depends_on_specs": ["b51"],
      "notes": "精算假设面板 + B51 GtIndexChip；可与 meta-wave-2 的 wave-7 后端并行准备 B51 stub"
    },
    {
      "id": "meta-wave-4",
      "name": "J1 重型单路",
      "parallel": false,
      "specs": ["j1-employee-compensation"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "depends_on_specs": ["k8-selling-expenses", "k9-admin-expenses"],
      "notes": "wave-6 可拆最多 4 子代理（4.1–4.12）；分配检查 J1-7 依赖 K8/K9"
    },
    {
      "id": "meta-wave-5",
      "name": "跨循环联动验收",
      "parallel": true,
      "max_agents": 3,
      "specs": ["j1-employee-compensation", "j2-defined-benefit-plan", "j3-share-based-payment"],
      "per_spec_waves": ["wave-8", "wave-9"],
      "tasks": ["M.5.1", "M.5.2", "M.5.3"],
      "notes": "J1↔K8/K9、J2↔B51、J3↔M4/J1 双向 GtIndexChip + EventBus"
    },
    {
      "id": "meta-wave-6",
      "name": "全循环集成闸门",
      "parallel": false,
      "specs": ["_j_cycle_integration"],
      "tasks": ["M.6.1", "M.6.2", "M.6.3"]
    }
  ]
}
```

## 子代理铁律

1. **共享注册串行**：`meta-wave-1` 单 agent 批量追加 J1/J2/J3 全部 `componentType`。
2. **J1 wave-6 拆分**：4.1 Index 先行；4.2–4.4 核心表并行；4.5–4.11 五类检查表可 2–3 路并行；4.12 附注最后。
3. **J3 无 TB 回写**：子代理禁止在 `useJ3FormData` 调用 `writebackTB`；费用确认走 EventBus → M4/J1。
4. **负债方向守卫**：J1/J2 所有 `calcLiabilityEndBalance` 与 TB 回写必须为 **贷方负债**（与 H9/J 循环 memory 一致）。
5. **子代理沙箱伪绿**：各 spec `wave-9` 后主 agent 重跑 `7.1`–`7.x` + registry 契约测试。

## 共享文件冲突矩阵

| 文件 | 冲突级别 | 策略 |
|------|----------|------|
| `wp_code_overrides.json` | 🔴 高 | meta-wave-1 批量 |
| `htmlRendererRegistry.ts` | 🔴 高 | meta-wave-1 批量 |
| `wp_classification_service.py` VALID_COMPONENT_TYPES | 🔴 高 | meta-wave-1 批量 |
| `router_registry/workpaper.py` | 🔴 高 | 各 spec wave-7 后主 agent 统一挂载 |
| `wp_render_schema/j*.yaml` | 🟢 无 | 各 spec 独立文件 |
| composable / vue 按 spec 目录 | 🟢 无 | 子代理完全并行 |

## Tasks

### Meta Phase 0: 编排准备

- [x] M.0.1 校验 J1–J3 `tasks.md` 均已含 JSON `waves` 块（本任务交付物）
  - grep：`"waves":` 在 3 个 `j*-*/tasks.md` 均存在
  - _Requirements: 编排可执行性_

- [x] M.0.2 建立 J 循环进度看板（可选）
  - 路径：`.kiro/specs/j-cycle-orchestration/j_cycle_progress.json`
  - 字段：`spec_id`, `current_wave`, `status`, `cross_cycle_deps_ready`
  - _Requirements: 多子代理状态同步_

### Meta Phase 1: 全循环 Phase0 + 注册

- [x] M.1.1 执行 **meta-wave-0**：3 子代理并行各 spec `wave-0`
  - 产出：`j*_structure_summary.json` + `j*_conflict_resolution.md`
  - 门禁：主 agent 核对 J1 负债贷方公式方向、J3 BS 参数列
  - _Requirements: 双源输入_

- [x] M.1.2 执行 **meta-wave-1** 共享注册批量
  - J1/J2/J3 全部 wp_code + overrides + VALID_COMPONENT_TYPES + 主入口 skeleton
  - `test_router_registry_completeness` + `htmlRendererRegistry.spec.ts` 全绿
  - _Requirements: 各子 spec 1.x_

### Meta Phase 2: 锚定与分路开发

- [x] M.2.1 执行 **meta-wave-2** J3 锚定全流程
  - 重点验收：`useJ3OptionPricingEngine` PBT + 权益/现金分流 EventBus
  - _Requirements: j3-share-based-payment 全部_

- [x] M.2.2 执行 **meta-wave-3** J2 精算单路
  - `useJ2ActuarialEngine` + J2TabAccrualCheck ISA620 面板
  - _Requirements: j2-defined-benefit-plan 全部_

- [x] M.2.3 执行 **meta-wave-4** J1 重型单路
  - wave-6 建议拆 3 子代理：核心表 / 月度+行业 / 五类检查+附注
  - 前置确认 K8/K9 registry 条目存在
  - _Requirements: j1-employee-compensation 全部_

### Meta Phase 3: 联动与总验收

- [x] M.5.1 **meta-wave-5** J3↔M4/J1 联动
  - 权益结算 → M4；现金结算 → J1；Playwright `7.4` 全链路
  - _Requirements: j3 Req 联动_

- [x] M.5.2 **meta-wave-5** J2↔B51 精算假设联动
  - `actuarial:assumption-changed` → B51；Playwright `7.4`
  - _Requirements: j2 Req 联动_

- [x] M.5.3 **meta-wave-5** J1↔K8/K9 分配闭合联动
  - `compensation:adjusted` + J1-7 分配检查 ↔ K8/K9 交叉验证
  - Playwright `7.4` + `7.5` 月度12列
  - _Requirements: j1 Req 联动_

- [x] M.6.1 **meta-wave-6** registry + router 完整性
  - `test_router_registry_completeness` 含 J1/J2/J3 零遗漏
  - _Requirements: 基础设施_

- [x] M.6.2 Playwright 冒烟：J3 BS 定价 + J2 精算假设 + J1 月度分析各 1 条
  - _Requirements: 各子 spec 7.x E2E_

- [x] M.6.3 更新 `.kiro/steering/memory.md` J 循环实现状态
  - _Requirements: 项目记忆_

## 子 spec wave 标准（J1–J3）

| Wave | 内容 | 并行 | J1 | J2 | J3 |
|------|------|------|----|----|-----|
| wave-0 | 0.1 + 0.2 | ✅ | ✅ | ✅ | ✅ |
| wave-1 | 1.1 + 1.2 | 串行 | ✅ | ✅ | ✅ |
| wave-2 | 2.1 + 2.2 双引擎 | ✅ | ✅ | ✅ | ✅ |
| wave-3 | PBT 2.3+ | ✅ | 2.3–2.10 | 2.3–2.9 | 2.3–2.8 |
| wave-4 | 基础 composable | ✅ | 3.1–3.3 | 3.1–3.3 | 3.1–3.2 |
| wave-5 | sheet/check composable | ✅ | 3.4–3.7 | 3.4–3.5 | 3.3–3.5 |
| wave-6 | Vue Tab | ✅ | 4.1–4.12 | 4.1–4.6 | 4.1–4.3 |
| wave-7 | 后端四件套 | ✅ | 5.1–5.4 | 5.1–5.4 | 5.1–5.4 |
| wave-8 | 集成联动 | ✅ | 6.1–6.6 | 6.1–6.5 | 6.1–6.5 |
| wave-9 | 测试验收 | ✅ | 7.1–7.5 | 7.1–7.4 | 7.1–7.4 |

## Notes

- J 循环规模小（3 spec），`max_parallel_subagents: 3` 足够；不宜与 K 循环 meta-wave 混跑以免争抢 registry。
- 编排器读取子 spec `tasks.md` 内 `"waves"` JSON，再套 `meta-wave-*` 的 `per_spec_waves` 过滤。
- 归档底稿骨架（`j-cycle-workpapers`）已完成 d-form 层；本调度针对 **专属 HTML 精美组件** 三件套实现路径。
- J1 月度分析（4.5）与 K8/K9 损益分析 composable 可复用 `k-expense-analysis-template` 的图表/表格模式（只读参考，不阻塞 J wave）。
