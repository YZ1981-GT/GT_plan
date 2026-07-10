# Implementation Plan: K 循环总调度（k-cycle-orchestration）

## Overview

K 循环含 14 个子 spec（K0 函证 + K1–K13 科目底稿）。本 spec **不实现业务代码**，只定义跨 spec 的 wave 编排、子代理并行策略、共享文件冲突规避与验收闸门。

子 spec 三件套路径：

| Spec | 目录 | 类型 | 复杂度 |
|------|------|------|--------|
| K0 | `k0-confirmation` | 函证 hub（复用 D0） | 低 |
| K1 | `k1-other-receivables` | 资产 + ECL | **最高** |
| K2 | `k2-other-current-assets` | 资产 + 摊销 | 高 |
| K3 | `k3-other-payables` | 负债 | 中 |
| K4 | `k4-other-current-liabilities` | 负债 | **最低（锚定模板）** |
| K5 | `k5-provisions` | 负债 + 或有事项 | 高 |
| K6 | `k6-held-for-sale` | CAS42 混合 | 高 |
| K7 | `k7-deferred-income` | 负债 + 分摊 | 中 |
| K8 | `k8-selling-expenses` | 损益 + 分析 + 截止 | 高 |
| K9 | `k9-admin-expenses` | 损益 + 分析 + 截止 | 高 |
| K10 | `k10-other-income` | 损益 + K7 联动 | 中 |
| K11 | `k11-asset-impairment-loss` | 损益 + 跨循环汇总 | 高 |
| K12 | `k12-non-operating-income` | 损益简化 | 低 |
| K13 | `k13-non-operating-expense` | 损益简化 | 低 |

**开发优先级（memory）**：先 K1–K13 科目底稿；K0 函证可后置（与 K3/K1 往来科目无代码冲突）。

## Meta Task Dependency Graph

```json
{
  "max_parallel_subagents": 4,
  "waves": [
    {
      "id": "meta-wave-0",
      "name": "全循环 Phase0 双源输入",
      "parallel": true,
      "specs": [
        "k1-other-receivables", "k2-other-current-assets", "k3-other-payables",
        "k4-other-current-liabilities", "k5-provisions", "k6-held-for-sale",
        "k7-deferred-income", "k8-selling-expenses", "k9-admin-expenses",
        "k10-other-income", "k11-asset-impairment-loss", "k12-non-operating-income",
        "k13-non-operating-expense"
      ],
      "per_spec_waves": ["wave-0"],
      "notes": "13 子代理各跑 openpyxl + md 交叉验证；无共享文件冲突"
    },
    {
      "id": "meta-wave-1",
      "name": "锚定模板 K4 单 spec 全流程",
      "parallel": false,
      "specs": ["k4-other-current-liabilities"],
      "per_spec_waves": ["wave-1", "wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "notes": "最简负债类；验证 wave JSON 与子代理分工可行"
    },
    {
      "id": "meta-wave-2",
      "name": "共享注册批量（串行）",
      "parallel": false,
      "specs": ["_batch_k_registration"],
      "tasks": ["M.2.1"],
      "notes": "🔴 禁止多子代理并行写 htmlRendererRegistry / wp_code_overrides / VALID_COMPONENT_TYPES / router_registry"
    },
    {
      "id": "meta-wave-3",
      "name": "负债类并行开发",
      "parallel": true,
      "max_agents": 3,
      "specs": ["k3-other-payables", "k7-deferred-income", "k4-other-current-liabilities"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "skip_specs": ["k4-other-current-liabilities"],
      "notes": "K4 已在 meta-wave-1 完成则跳过"
    },
    {
      "id": "meta-wave-4",
      "name": "损益+截止模板（K8 锚定）",
      "parallel": false,
      "specs": ["k8-selling-expenses"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"]
    },
    {
      "id": "meta-wave-5",
      "name": "损益类并行（K9 克隆 K8）",
      "parallel": true,
      "max_agents": 4,
      "specs": ["k9-admin-expenses", "k10-other-income", "k12-non-operating-income", "k13-non-operating-expense"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"]
    },
    {
      "id": "meta-wave-6",
      "name": "特殊引擎并行",
      "parallel": true,
      "max_agents": 3,
      "specs": ["k2-other-current-assets", "k5-provisions", "k6-held-for-sale"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"]
    },
    {
      "id": "meta-wave-7",
      "name": "K1 ECL 重型（单路）",
      "parallel": false,
      "specs": ["k1-other-receivables"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"]
    },
    {
      "id": "meta-wave-8",
      "name": "K11 跨循环汇总（单路）",
      "parallel": false,
      "specs": ["k11-asset-impairment-loss"],
      "per_spec_waves": ["wave-2", "wave-3", "wave-4", "wave-5", "wave-6", "wave-7", "wave-8", "wave-9"],
      "depends_on_specs": ["f2", "h1", "i1"],
      "notes": "源底稿 GtIndexChip 依赖 F2/H1/I 至少 skeleton 存在"
    },
    {
      "id": "meta-wave-9",
      "name": "K10↔K7 联动验收",
      "parallel": false,
      "specs": ["k10-other-income", "k7-deferred-income"],
      "per_spec_waves": ["wave-8", "wave-9"],
      "tasks": ["M.9.1"]
    },
    {
      "id": "meta-wave-10",
      "name": "全循环集成闸门",
      "parallel": false,
      "specs": ["_k_cycle_integration"],
      "tasks": ["M.10.1", "M.10.2", "M.10.3"]
    },
    {
      "id": "meta-wave-11",
      "name": "K0 函证（可选后置）",
      "parallel": false,
      "specs": ["k0-confirmation"],
      "per_spec_waves": ["wave0", "wave1", "wave2", "wave3", "wave4", "wave5", "wave6", "wave7"],
      "notes": "沿用 k0-confirmation 既有 wave 命名；与 K1–K13 无 registry 批次冲突"
    }
  ]
}
```

## 子代理铁律

1. **共享注册串行**：`meta-wave-2` 必须由单 agent 完成，或按 spec 分批 merge（每批后跑 `test_router_registry_completeness`）。
2. **子代理沙箱伪绿**：每个子 spec 的 wave-9 完成后，主 agent 重跑该 spec 的 `7.1`–`7.3` 与 registry 契约测试（`conventions.md`）。
3. **单 spec 内并行上限**：wave-3（PBT）、wave-6（Vue Tab）、wave-7（后端三件套）可多子代理；wave-5（`3.4` sheet composables）必须等 wave-4 完成。
4. **跨 spec 并行上限**：`max_parallel_subagents: 4`，避免同时改同一共享文件。
5. **克隆顺序**：K4（负债）→ K8（损益+截止）→ K1（ECL）；禁止未读锚定 spec 就并行写同族 composable。

## 共享文件冲突矩阵

| 文件 | 冲突级别 | 策略 |
|------|----------|------|
| `wp_code_overrides.json` | 🔴 高 | meta-wave-2 批量 |
| `htmlRendererRegistry.ts` | 🔴 高 | meta-wave-2 批量 |
| `wp_classification_service.py` VALID_COMPONENT_TYPES | 🔴 高 | meta-wave-2 批量 |
| `router_registry/workpaper.py` | 🔴 高 | 各 spec wave-7 后由主 agent 统一挂载 |
| `account_package_registry.json` | 🟡 中 | 随 meta-wave-2 或 per-spec 串行 append |
| 各 spec composable/vue | 🟢 无 | 子代理完全并行 |

## Tasks

### Meta Phase 0: 编排准备

- [x] M.0.1 校验 K1–K13 `tasks.md` 均已含 JSON `waves` 块（本任务交付物）
  - 脚本或 grep：`"waves":` 在 13 个 k*-*/tasks.md 均存在
  - _Requirements: 编排可执行性_

- [ ] M.0.2 建立 K 循环进度看板（可选 JSON）
  - 路径：`.kiro/specs/k-cycle-orchestration/k_cycle_progress.json`
  - 字段：`spec_id`, `current_wave`, `status`, `last_verified_tests`
  - _Requirements: 多子代理状态同步_

### Meta Phase 1: 全循环 Phase0

- [ ] M.1.1 启动 **meta-wave-0**：13 子代理并行执行各 spec `wave-0`
  - 产出：`k*_structure_summary.json` + `k*_conflict_resolution.md`（如有）
  - 门禁：主 agent spot-check K4/K8/K1 三份 summary 列头与公式计数
  - _Requirements: 双源输入_

### Meta Phase 2: 锚定与批量注册

- [ ] M.2.1 执行 **meta-wave-2** 共享注册批量
  - 单次 PR 式追加：K1–K13 全部 `componentType` + overrides + VALID_COMPONENT_TYPES + 主入口 skeleton import
  - 跑通：`test_router_registry_completeness` + `htmlRendererRegistry.spec.ts`
  - _Requirements: 1.x 注册（各子 spec）_

- [ ] M.2.2 执行 **meta-wave-1**（若 M.2.1 先于锚定：则先 K4 注册条目再批量其余）
  - K4 完整走完 wave-1～wave-9 作为负债类金样
  - _Requirements: k4-other-current-liabilities 全部_

### Meta Phase 3: 并行开发波次

- [ ] M.3.1 **meta-wave-3** 负债类三路并行（K3/K7，K4 已完成则跳过）
  - 每路按子 spec JSON waves 顺序；wave-6 可拆 4–6 子代理
  - _Requirements: k3, k7_

- [ ] M.3.2 **meta-wave-4 + meta-wave-5** 损益类（先 K8 锚定，再三路/四路并行）
  - K9 从 K8 克隆 `use*AnalysisEngine` / `use*CutoffEngine` 模式
  - K12/K13 从 K10 简化（无分析/截止 Tab）
  - _Requirements: k8, k9, k10, k12, k13_

- [ ] M.3.3 **meta-wave-6** 特殊引擎三路（K2/K5/K6）
  - _Requirements: k2, k5, k6_

- [ ] M.3.4 **meta-wave-7** K1 单路 ECL 全流程
  - _Requirements: k1-other-receivables 全部_

- [ ] M.3.5 **meta-wave-8** K11 单路（确认 F2/H1/I 源底稿链接可解析）
  - _Requirements: k11-asset-impairment-loss 全部_

### Meta Phase 4: 联动与总验收

- [ ] M.9.1 **meta-wave-9** K10↔K7 补助分摊联动集成测试
  - `useK10GrantReconcileEngine` vs K7 分摊去向 GtIndexChip 双向
  - _Requirements: k10 Req 联动, k7 Req 联动_

- [ ] M.10.1 **meta-wave-10** 全循环 router + registry 完整性
  - `test_router_registry_completeness` 零遗漏
  - 各 K spec 契约测试全绿
  - _Requirements: 基础设施_

- [ ] M.10.2 Playwright 冒烟：每循环至少 1 条 E2E（K4/K8/K1 必跑）
  - _Requirements: 各子 spec 7.3_

- [ ] M.10.3 更新 `.kiro/steering/memory.md` K 循环实现状态
  - _Requirements: 项目记忆_

### Meta Phase 5: K0 函证（可选）

- [ ] M.11.1 **meta-wave-11** 执行 `k0-confirmation` 全部 wave
  - 依赖 D0 共享组件已存在；仅新建 K05/K06
  - _Requirements: k0-confirmation 全部_

## 子 spec wave 标准（K1–K13 统一）

各子 spec `tasks.md` 内 JSON 遵循同一拓扑（任务编号因 spec 而异）：

| Wave | 内容 | 并行 |
|------|------|------|
| wave-0 | 0.1 + 0.2 双源输入 | ✅ |
| wave-1 | 1.1 注册 + 1.2 契约测试 | 串行 |
| wave-2 | 2.1（+2.2 副引擎若有） | 2.1/2.2 可并行 |
| wave-3 | 全部 PBT（2.x*） | ✅ |
| wave-4 | 3.1 + 3.2 + 3.3 基础 composable | ✅ |
| wave-5 | 3.4 sheet-specific composables | 串行 |
| wave-6 | 全部 4.x Vue Tab | ✅ |
| wave-7 | 5.1 + 5.2 + 5.3 后端三件套 | ✅ |
| wave-8 | 6.1 + 6.2 + 6.3 集成联动 | ✅ |
| wave-9 | 7.1 + 7.2 + 7.3 测试验收 | ✅（7.2/7.3 建议主 agent 终验） |

## Notes

- 编排器读取子 spec `tasks.md` 内 `"waves"` JSON，再套 `meta-wave-*` 的 `per_spec_waves` 过滤。
- K8/K9 完成后可抽取 `k-expense-analysis-template` Steering 片段，供 L/J 循环损益底稿复用。
- K0 与 K1/K3 业务上关联（其他应收/应付函证），但代码路径独立，可并行 meta-wave-11。
