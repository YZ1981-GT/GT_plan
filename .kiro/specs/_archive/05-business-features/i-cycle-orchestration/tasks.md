# Implementation Plan: I 循环总调度（i-cycle-orchestration）

## Overview

I 循环（无形资产循环）含 **6 个子 spec**（I1–I6），无独立 I0 函证 spec。本 spec **不实现业务代码**，只定义跨 spec 的 wave 编排、子代理并行策略、研发联动与验收闸门。

| Spec | 目录 | 科目/特征 | 复杂度 | 跨循环联动 |
|------|------|-----------|--------|------------|
| I1 | `i1-intangible-assets` | 1701/1702/1703 资产+摊销+减值+DCF | **最高** | ← I2；→ K8/K9/I6 |
| I2 | `i2-development-expenditure` | 1717 开发支出 + CAS6 资本化 | **高** | ↔ I6；→ I1 |
| I3 | `i3-goodwill` | 1711 商誉不摊销 + DCF/CGU | 高 | → K11 减值汇总 |
| I4 | `i4-long-term-prepaid` | 1801 长期待摊 + 双摊销分支 | 中 | — |
| I5 | `i5-other-noncurrent-assets` | 1911 其他非流动资产 | **最低（锚定）** | — |
| I6 | `i6-research-development-expense` | 6602 损益类 + 月度12列 | 高 | ↔ I2 |

**锚定顺序**：I5（最简资产）→ I4（摊销分支）→ **I6∥I2 双路**（研发对）→ I3（商誉 DCF）→ I1（全循环最大）。

**前置依赖（跨循环）**：
- I1 `wave-8` 前：I2 `wave-1` skeleton（资本化转入 I1-5）
- I2↔I6 `wave-8`：两 spec 均完成 `wave-4` 后 EventBus 契约可联调
- I1 `6.4`：K8/K9 registry 条目存在（摊销分配联动）
- I3 `wave-9`：K11 可选 skeleton（减值汇总 GtIndexChip）

## Meta Task Dependency Graph

```json
{
  "max_parallel_subagents": 4,
  "waves": [
    {
      "id": "meta-wave-0",
      "name": "全循环 Phase0 双源输入",
      "parallel": true,
      "max_agents": 4,
      "specs": [
        "i1-intangible-assets", "i2-development-expenditure", "i3-goodwill",
        "i4-long-term-prepaid", "i5-other-noncurrent-assets", "i6-research-development-expense"
      ],
      "per_spec_waves": ["wave-0"],
      "notes": "6 spec 分两批（4+2）或一次 4 路；无共享文件冲突"
    },
    {
      "id": "meta-wave-1",
      "name": "共享注册批量（串行）",
      "parallel": false,
      "specs": ["_batch_i_registration"],
      "tasks": ["M.1.1"],
      "notes": "🔴 禁止多子代理并行写 htmlRendererRegistry / wp_code_overrides / VALID_COMPONENT_TYPES / router_registry"
    },
    {
      "id": "meta-wave-2",
      "name": "锚定模板 I5 单 spec 全流程",
      "parallel": false,
      "specs": ["i5-other-noncurrent-assets"],
      "per_spec_waves": ["wave-1", "wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "notes": "单引擎最简资产类；验证 wave JSON 与子代理分工"
    },
    {
      "id": "meta-wave-3",
      "name": "I4 摊销分支单路",
      "parallel": false,
      "specs": ["i4-long-term-prepaid"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "notes": "直线法/工作量法双 Tab 分支模式，供 I1 摊销 Tab 参考"
    },
    {
      "id": "meta-wave-4",
      "name": "研发双路并行（I6 + I2）",
      "parallel": true,
      "max_agents": 2,
      "specs": ["i6-research-development-expense", "i2-development-expenditure"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7"],
      "notes": "wave-8 联动必须等两路均完成 wave-7；禁止单路先跑满 wave-9"
    },
    {
      "id": "meta-wave-5",
      "name": "I6↔I2 联动 wave",
      "parallel": false,
      "specs": ["i6-research-development-expense", "i2-development-expenditure"],
      "per_spec_waves": ["wave-8", "wave-9"],
      "tasks": ["M.5.1"],
      "notes": "VR-I6-01 + research:expense-updated / development:capitalized-updated 双向"
    },
    {
      "id": "meta-wave-6",
      "name": "I3 商誉 DCF 单路",
      "parallel": false,
      "specs": ["i3-goodwill"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "notes": "wave-6 可拆：4.8 DCF 表独立子代理（100×16 虚拟滚动）"
    },
    {
      "id": "meta-wave-7",
      "name": "I1 重型单路",
      "parallel": false,
      "specs": ["i1-intangible-assets"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "depends_on_specs": ["i2-development-expenditure", "k8-selling-expenses", "k9-admin-expenses"],
      "notes": "wave-6 建议拆 3 子代理：核心表 / 检查表组 / 摊销+减值+附注；I1 Phase0–2 已部分完成"
    },
    {
      "id": "meta-wave-8",
      "name": "I1↔I2 转入 + I1 分配联动",
      "parallel": false,
      "specs": ["i1-intangible-assets", "i2-development-expenditure"],
      "per_spec_waves": ["wave-8"],
      "tasks": ["M.8.1", "M.8.2"]
    },
    {
      "id": "meta-wave-9",
      "name": "全循环集成闸门",
      "parallel": false,
      "specs": ["_i_cycle_integration"],
      "tasks": ["M.9.1", "M.9.2", "M.9.3"]
    }
  ]
}
```

## 子代理铁律

1. **共享注册串行**：`meta-wave-1` 单 agent 批量追加 I1–I6 全部 `componentType`。
2. **I6↔I2 成对推进**：`meta-wave-4` 两路并行至 wave-7；`meta-wave-5` 统一联调 wave-8/9，禁止一路 E2E 绿而另一路未注册。
3. **I1 进度接续**：I1 已完成 wave-0～wave-3（及 2.x PBT）；子代理从 **wave-4（3.1 composable）** 接续，勿重复 Phase0/引擎。
4. **损益 vs 资产守卫**：I6 全部 TB 回写与 render 必须为 **发生额（借-贷）**；I1/I2/I3/I4/I5 为 **期末余额**。
5. **I3 商誉不摊销**：子代理禁止在 I3 引入直线摊销公式；减值先冲商誉逻辑仅 `useI3Impairment`。
6. **子代理沙箱伪绿**：各 spec `wave-9` 后主 agent 重跑契约测试 + registry 完整性。

## 共享文件冲突矩阵

| 文件 | 冲突级别 | 策略 |
|------|----------|------|
| `wp_code_overrides.json` | 🔴 高 | meta-wave-1 批量 |
| `htmlRendererRegistry.ts` | 🔴 高 | meta-wave-1 批量 |
| `wp_classification_service.py` VALID_COMPONENT_TYPES | 🔴 高 | meta-wave-1 批量 |
| `router_registry/workpaper.py` | 🔴 高 | 各 spec wave-7 后主 agent 统一挂载 |
| `wp_render_schema/i*.yaml` | 🟢 无 | 各 spec 独立 |
| composable / vue 按 spec 目录 | 🟢 无 | 子代理完全并行 |

## Tasks

### Meta Phase 0: 编排准备

- [x] M.0.1 校验 I1–I6 `tasks.md` 均已含 JSON `waves` 块（本任务交付物）
  - grep：`"waves":` 在 6 个 `i*-*/tasks.md` 均存在
  - _Requirements: 编排可执行性_

- [ ] M.0.2 建立 I 循环进度看板（可选）
  - 路径：`.kiro/specs/i-cycle-orchestration/i_cycle_progress.json`
  - 字段：`spec_id`, `current_wave`, `status`, `i2_i6_pair_ready`
  - _Requirements: 多子代理状态同步_

### Meta Phase 1: Phase0 + 注册

- [ ] M.1.1 执行 **meta-wave-0**（未完成 Phase0 的 spec）+ **meta-wave-1** 注册批量
  - I1 0.1/0.2 已完成可跳过；I4 部分进行中需主 agent 判定
  - `test_router_registry_completeness` + `htmlRendererRegistry.spec.ts`
  - _Requirements: 各子 spec 1.x_

### Meta Phase 2: 锚定与分路

- [ ] M.2.1 **meta-wave-2** I5 锚定全流程
  - _Requirements: i5-other-noncurrent-assets 全部_

- [ ] M.2.2 **meta-wave-3** I4 摊销分支单路
  - _Requirements: i4-long-term-prepaid 全部_

- [ ] M.2.3 **meta-wave-4** I6∥I2 双路至 wave-7
  - 每路 wave-6 可拆多 Tab 子代理（I2 最多 4.1–4.12）
  - _Requirements: i6, i2_

### Meta Phase 3: 联动与重型

- [ ] M.5.1 **meta-wave-5** I6↔I2 联动验收
  - Playwright I2 `7.5` + I6 `7.4`/`7.5`；VR-I6-01 全绿
  - _Requirements: i6 Req 联动, i2 Req 联动_

- [ ] M.6.1 **meta-wave-6** I3 商誉 DCF 全流程
  - _Requirements: i3-goodwill 全部_

- [ ] M.7.1 **meta-wave-7** I1 从 wave-4 接续至 wave-9
  - 优先完成 3.x composable → 4.x Tab → 后端 → 集成
  - _Requirements: i1-intangible-assets 剩余任务_

### Meta Phase 4: 跨 spec 与总验收

- [ ] M.8.1 **meta-wave-8** I2→I1 资本化转入
  - `development:capitalized-to-intangible` → I1-5 增加检查
  - _Requirements: i1 6.3, i2 6.3_

- [ ] M.8.2 **meta-wave-8** I1 摊销分配 → K8/K9/I6
  - GtIndexChip + EventBus 双向可解析
  - _Requirements: i1 6.4-6.5_

- [ ] M.9.1 **meta-wave-9** registry + router 完整性
  - _Requirements: 基础设施_

- [ ] M.9.2 Playwright 冒烟：I5 审定 + I6↔I2 联动 + I1 摊销分支各 1 条
  - _Requirements: 各子 spec 7.x E2E_

- [ ] M.9.3 更新 `.kiro/steering/memory.md` I 循环实现状态
  - _Requirements: 项目记忆_

## 子 spec wave 标准（I1–I6）

| Wave | 内容 | 并行 |
|------|------|------|
| wave-0 | 0.1 + 0.2 | ✅ |
| wave-1 | 1.1 + 1.2 | 串行 |
| wave-2 | 2.1（+2.2 副引擎） | 双引擎可并行 |
| wave-3 | PBT | ✅ |
| wave-4 | 基础 composable | ✅ |
| wave-5 | sheet/domain composable | ✅ |
| wave-6 | Vue Tab | ✅ |
| wave-7 | 后端（含 yaml） | ✅ |
| wave-8 | 集成联动 | ✅ |
| wave-9 | 测试验收 | ✅ |

### 各 spec 任务编号速查

| Spec | wave-2 | wave-3 PBT | wave-5 | wave-6 Vue | wave-7 后端 | wave-8 | wave-9 |
|------|--------|------------|--------|------------|-------------|--------|--------|
| I1 | 2.1–2.2 | 2.3–2.14 | 3.4–3.7 | 4.1–4.15 | 5.1–5.5 | 6.1–6.7 | 7.1–7.6 |
| I2 | 2.1–2.2 | 2.3–2.10 | 3.4–3.7 | 4.1–4.12 | 5.1–5.5 | 6.1–6.7 | 7.1–7.5 |
| I3 | 2.1–2.2 | 2.3–2.10 | 3.4–3.6 | 4.1–4.10 | 5.1–5.5 | 6.1–6.5 | 7.1–7.4 |
| I4 | 2.1–2.2 | 2.3–2.8 | 3.4–3.5 | 4.1–4.9 | 5.1–5.4 | 6.1–6.4 | 7.1–7.4 |
| I5 | 2.1 | 2.2–2.6 | 3.3–3.4 | 4.1–4.6 | 5.1–5.4 | 6.1–6.4 | 7.1–7.4 |
| I6 | 2.1 | 2.2–2.8 | 3.4–3.6 | 4.1–4.7 | 5.1–5.4 | 6.1–6.6 | 7.1–7.5 |

## Notes

- I1 为唯一**部分实现** spec（Phase0–2 已勾选）；编排器应支持 `resume_from_wave: "wave-4"`。
- I6↔I2 与 K10↔K7 同为**双向联动对**，建议联调子代理同时打开两 spec 的 `cross_wp_references` 段落。
- I3 DCF 与 I1 `I1TabRecoverableTest` 可共享 DCF 纯函数测试夹具（只读复用，不合并引擎文件）。
- 不宜与 K/J 循环 meta-wave 混跑以免争抢 registry；I 循环可在 K meta-wave-2 注册批次后独立推进。
