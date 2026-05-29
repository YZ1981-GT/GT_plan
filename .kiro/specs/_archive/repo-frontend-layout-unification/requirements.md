---
spec: repo-frontend-layout-unification
status: draft
version: v0.1
created: 2026-05-29
owner: 全局改进 #2（memory 记录）
priority: P1（每次 grep / IDE / CI 都受影响）
---

# 需求文档：仓库前端路径二义性消除

## 一、问题陈述

仓库根目录有两个前端目录，造成持续误导：

```
GT_workplan/
├── frontend/                              ← 空壳（仅 5 个 .vue / 0 个 .ts）
│   └── src/
│       └── components/
│           ├── custom-query/   (2 文件)
│           └── eqcr/           (3 文件)
└── audit-platform/
    └── frontend/                          ← 真前端（498 .vue / 379 .ts）
        └── src/
            ├── components/  (大量)
            ├── views/       (99 个)
            ├── composables/ (81 个)
            ├── stores/      (9 个)
            ├── ...
```

**实测影响**（grep 统计）：
- `audit-platform/frontend` 字符串硬编码：~120 处（包括 vite 配置、Storybook、Playwright config、test runner 配置、import alias）
- `frontend/src` 字符串硬编码：~30 处（少数遗留引用空壳）
- `start-dev.bat` / `package.json` / 文档中的 `cd audit-platform/frontend` ≥40 处

### 衍生问题

1. **grep 噪音**：搜任何前端组件名都返回两份（`frontend/src/components/eqcr/X.vue` + `audit-platform/frontend/src/components/eqcr/X.vue`）
2. **新人困惑**：第一次接触 README 看到 `cd audit-platform/frontend` 不直觉
3. **IDE 智能提示混乱**：跨文件跳转可能跳到空壳 `frontend/src/`
4. **build 输出二义**：`frontend/dist/` 与 `audit-platform/frontend/dist/` 谁是真产物
5. **历史档案铁律冲突**：grep 指南里写"判断前端模块存在性必须同时检查 `views/` 根目录 + `components/` 子目录"实际是为这个二义性兜底的产物

### 根因（为什么会出现两个 frontend）

git log 推测：早期 `frontend/` 是单仓项目，后来加入 `audit-platform/` 多包结构（含 backend + frontend），但 `frontend/` 没及时清理，5 个空壳组件还残留在原位置。

## 二、范围

### 必做（P0，本 spec 闭环）

- R1 **路径单一化**：仓库根仅保留一个前端目录，不再有"哪个是真的"的歧义
- R2 **5 空壳组件迁移或删除**：`frontend/src/components/{custom-query,eqcr}/` 5 个 .vue 文件要么并入 `audit-platform/frontend/`，要么确认已死代码删除
- R3 **所有硬编码路径改写**：vite / Storybook / Playwright / package.json / start-dev.bat / README / docs / CI 全部统一
- R4 **memory 铁律更新**：删除「判断前端模块存在性必须同时检查 `views/` 根目录 + `components/` 子目录」这条历史铁律（已无意义）
- R5 **回归验证**：start-dev.bat 启动后端 + 前端正常 / vue-tsc 0 报错 / vitest 全绿 / Storybook 启动正常

### 不做（明确划出）

- ❌ 改 backend 目录结构（仅前端）
- ❌ 改 git 仓库历史（不 rebase）
- ❌ 移到不同的 monorepo 工具（不引入 pnpm / nx / lerna）
- ❌ 拆 `audit-platform/` 多包（保留 backend + frontend 同根）

## 三、方案选择

### 方案 A：保留 `audit-platform/frontend/`（推荐 ✅）

**步骤**：
1. 将 `frontend/src/components/{custom-query,eqcr}/` 5 个文件 git mv 到 `audit-platform/frontend/src/components/`
2. 检查每个文件是否真在用（grep 进口/路由/调用），无引用直接删
3. `git rm -r frontend/`（仓库根的空壳）
4. `start-dev.bat` 中 `cd audit-platform/frontend` 不变（保持现有路径）
5. README / 文档保持不变

**优点**：改动量最小（仅 5 文件迁移 + 30 处遗留硬编码改）
**缺点**：仓库根仍有 `audit-platform/` 一层（但比当前清晰）

### 方案 B：把 `audit-platform/frontend/` 提到根（高侵入）

**步骤**：
1. `git mv audit-platform/frontend frontend.tmp`
2. `git rm -r frontend`（旧空壳）
3. `git mv frontend.tmp frontend`
4. 全仓 grep `audit-platform/frontend` → 替换为 `frontend`（~120 处）
5. 同步改 `audit-platform/backend` 是否也提（一致性问题）

**优点**：仓库根结构更扁平
**缺点**：120 处硬编码 + 高风险（CI / Storybook / Playwright config 改坏链路全断）

### 方案选择：**方案 A**

理由：
- ROI 高（5 文件 vs 120 文件）
- 风险低（不动现有真前端结构）
- 满足核心目标"消除二义性"（删除空壳 = 单一来源）

## 四、用户故事

### US-1（开发者 / grep 用户）

**作为**开发者，**我希望**搜组件名只返回一份结果，**以便**不被空壳干扰。

**验收**：
- AC-1.1 `git rm -r frontend/` 后仓库根无 `frontend/` 目录
- AC-1.2 grep `class\s+\w+\s+extends.*Vue` 在前端代码中只命中 `audit-platform/frontend/`
- AC-1.3 grep `frontend/src/` 0 业务匹配（除文档历史档案）

### US-2（新人接手）

**作为**新人，**我希望**README 看到一个明确的前端路径，**以便**不困惑。

**验收**：
- AC-2.1 README.md 启动指南明确写 `cd audit-platform/frontend`
- AC-2.2 `start-dev.bat` 启动正常（106 行不动）
- AC-2.3 不再出现「同时检查 `views/` 根目录 + `components/` 子目录」类的兜底文档

### US-3（CI / IDE）

**作为**CI / IDE 用户，**我希望**所有路径配置一致，**以便**vue-tsc / Storybook / Playwright 不混淆。

**验收**：
- AC-3.1 vue-tsc 0 报错（迁移后真 import 路径正确）
- AC-3.2 vitest 全绿（前端测试不破）
- AC-3.3 Storybook `npm run storybook -- --ci` 启动成功
- AC-3.4 Playwright config / e2e-uat 不变（已经在 `audit-platform/frontend/`）

### US-4（防回归）

**作为**质控，**我希望**新加 spec 不再制造同类二义性，**以便**未来不复发。

**验收**：
- AC-4.1 `.pre-commit-config.yaml` 加 hook 检测 `frontend/src/` 路径出现即拒
- AC-4.2 memory.md 删旧铁律，加新铁律「前端唯一路径 = audit-platform/frontend/」

## 五、卡点 CI

| 编号 | 描述 | 实施位置 |
|------|------|----------|
| CI-1 | 仓库根无 `frontend/` 目录 | `_verify_no_root_frontend.py` |
| CI-2 | 5 空壳组件全部迁移或删除（无遗漏） | grep 历史路径 0 命中 |
| CI-3 | start-dev.bat 启动 OK | smoke test |
| CI-4 | vue-tsc 0 报错 | `npm run type-check` |
| CI-5 | vitest 全绿（前端测试基线不破） | `npm run test` |
| CI-6 | pre-commit hook 检测 `frontend/src/` 阻止新增 | hook 单测 |

## 六、风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| 5 空壳组件实际有引用 | 中 | 迁移前 grep 引用确认，0 引用才删 |
| Storybook stories 引用空壳路径 | 低 | grep `frontend/src/` 全仓 |
| 历史 git blame 中断 | 低 | `git mv` 保留 history（git follow 选项） |
| 文档大量 `cd audit-platform/frontend` 改不完 | 低 | 方案 A 不需要改文档 |

## 七、验收数字

- 验收 AC：4 user stories × 平均 3 = **12 AC**
- CI 卡点：**6**
- 必做范围：**5 R**
- 测试：**1 smoke + 1 hook 单测 = 2 测试**
- 工作量：**0.5 人天**（grep 0.1 + 迁移 0.1 + 验证 0.2 + memory 同步 0.1）

## 八、版本

- v0.1（2026-05-29）：初版
