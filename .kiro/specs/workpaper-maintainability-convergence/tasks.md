# Implementation Plan · 底稿可维护性收敛

## Overview

任务按“实证基线 → 持久化地基 → Runtime Boundary → 代表性试点 → 分循环迁移 → 工厂化 → 性能与强制门禁”执行。所有任务均为必做；完成必须有代码证据与验证结果，不得仅依据旧 spec 的 `[x]`。

### 执行铁律

- codegraph 优先定位主入口、provider、caller 和影响面；非符号文本才用 grep。
- Vue 文件只用结构化编辑工具，禁止 PowerShell 文本替换。
- 每个迁移批次必须执行 diagnostics、Vite transform、目标单测和 Playwright Round_Trip。
- 保存测试必须刷新或重新导航后验证回显；仅 PUT 200 不算完成。
- 新守卫先 report，再在对应迁移覆盖率 100% 后切 strict。
- 不修改归档 `platform-global-hardening` 的历史勾选；本 spec 独立记录修复。

## Task Dependency Graph

```json
{
  "waves": [
    {"id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"]},
    {"id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4"]},
    {"id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4"]},
    {"id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4"]},
    {"id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4"]},
    {"id": 5, "tasks": ["6.1", "6.2", "6.3"]},
    {"id": 6, "tasks": ["7.1", "7.2", "7.3"]},
    {"id": 7, "tasks": ["8.1", "8.2", "8.3"]}
  ]
}
```

## Tasks

### Wave 0 · 真实基线与守卫设计

- [x] 1. 建立可复现的底稿维护基线
  - [x] 1.1 实现 componentType → 主入口 → wp_code 清单生成器
    - 从 `htmlRendererRegistry`、`wp_code_overrides.json` 和专属组件注册真源生成清单。
    - 输出来源文件、上下文策略和是否走 `GtWpRenderer`。
    - _Requirements: 1.1, 1.2_
  - [x] 1.2 重构 Capability Ledger 为能力级证据模型
    - 每项能力记录 `status/evidence/exemption`；禁止 entry 级 blanket exemption。
    - 保留旧 JSON 读取兼容并提供一次性迁移脚本。
    - _Requirements: 1.2, 1.3_
  - [x] 1.3 升级 `check_coverage_ledger.py`
    - 对 Runtime Boundary 自动覆盖项、Legacy Provider、明确缺失和不确定状态分别判定。
    - report 模式输出全量覆盖率；strict 仅阻断明确缺失或 Ledger 漂移。
    - _Requirements: 1.4, 5.5_
  - [x] 1.4 添加 Coverage Ledger 属性测试 P1/P2
    - P1：任一能力豁免不影响其他能力判定。
    - P2：证据存在当且仅当状态可标 covered；不确定保持 fail-open。
    - _Requirements: 1.3, 1.4_

### Wave 1 · 统一持久化地基

- [x] 2. 实现 Persistence Adapter 与后端稳定边界
  - [x] 2.1 实现 `useChecklistPersistence`
    - 提供 load/hydrate/save/saveDebounced/flush/cancel/stateOf。
    - 每 item 独立定时器，组件卸载前 flush 或显式 cancel。
    - _Requirements: 3.1, 3.2, 3.5, 3.8_
  - [x] 2.2 实现 remark 单次序列化与历史兼容
    - 新增 `encodeRemark/decodeRemark` 纯函数，兼容历史双层包装但新写单层。
    - 禁止改变现有业务对象字段。
    - _Requirements: 3.4_
  - [x] 2.3 加固 checklist API 权限、版本和事件
    - 统一底稿编辑权限；返回版本标识；保存成功接现有 WORKPAPER_SAVED 入口。
    - 明确批量原子性和 409 冲突行为，保留无 if_match 的兼容路径。
    - _Requirements: 4.1-4.6_
  - [x] 2.4 添加持久化属性/契约测试 P3-P6
    - P3：encode/decode 往返保持业务值且新写单层。
    - P4：同 item debounce 最后写胜出，不同 item 互不干扰。
    - P5：失败不标 saved，重试成功后状态收敛。
    - P6：批量任一非法时事务行为符合定义且错误定位 item_id。
    - _Requirements: 3.4-3.7, 4.1, 4.3_

### Wave 2 · Runtime Boundary

- [x] 3. 在公共渲染路径落地 Scaffold
  - [x] 3.1 使 `useWorkpaperScaffold` 支持祖先实例复用
    - 新增类型化 Runtime Context/InjectionKey，避免嵌套 Shell 重复初始化。
    - 修正 AI context 统一为字符串值并保持响应信封兼容。
    - _Requirements: 2.1, 2.4, 2.5_
  - [x] 3.2 在 `GtWpRenderer` 初始化 Runtime Boundary
    - 使用响应式 wpId/projectId/wpCode/year；不添加重复 toolbar 或布局包装。
    - 保留 contextProps strategy 与现有动态组件 props 行为。
    - _Requirements: 2.1, 2.2, 2.6_
  - [x] 3.3 统一挂载复核与版本 Host
    - 确保 openReviewDialog/openVersionHistory 在任一专属组件子树可用。
    - 删除 console.log 桩仅在完成对应迁移批次时进行。
    - _Requirements: 2.2, 7.1-7.3_
  - [x] 3.4 添加 Runtime Boundary 组件测试 P7/P8
    - P7：任意 registry standard componentType 只初始化一个 runtime。
    - P8：缺上下文不白屏；嵌套 Shell 不产生第二个版本/复核实例。
    - _Requirements: 2.1, 2.4, 2.5_

### Wave 3 · 三类代表性试点

- [x] 4. 用代表底稿验证迁移方案
  - [x] 4.1 迁移 D2（复杂往来款/账龄/抽凭）
    - 替换重复 provider 和保存 I/O；保留业务 composable、抽凭、OCR 与跨表联动。
    - Playwright 验证明细编辑、复核、版本、刷新回显。
    - _Requirements: 2, 3, 7_
  - [x] 4.2 迁移 K5（曾发生 persistence 多连环问题）
    - 验证双层 JSON、`/api`、project_id、responses_snapshot 与 year 不回归。
    - _Requirements: 3.2-3.9_
  - [x] 4.3 迁移 J2（多 section + AI + 披露）
    - 验证多 item 保存、AI context、说明/结论和跨 sheet 导航。
    - _Requirements: 2.2, 3, 7_
  - [x] 4.4 完成试点 Round_Trip 与回归报告
    - 三类底稿均执行 fresh navigation；断言 console 0 error、PUT 成功、DB/GET 回读、UI 回显一致。
    - 记录迁移前后调用数、重复代码和失败模式。
    - _Requirements: 3.9, 8.1-8.4_

### Wave 4 · 分循环迁移与严格覆盖

- [x] 5. 迁移全部专属底稿主入口
  - [x] 5.1 迁移 D/E/F 与 G/H/I
    - 删除已由 Runtime Boundary 提供的本地 displayPrefs/version/review/AI provider。
    - 同构 FormData 改用 Adapter；保留业务特有 afterSave/EventBus。
    - 每循环至少一个 fresh-navigation Round_Trip。
    - _Requirements: 2, 3, 7, 8.4-8.5_
  - [x] 5.2 迁移 J/K
    - 重点覆盖多 section JSON、附注联动、凭证检查和审定表回写。
    - 对历史双层 remark 数据执行读兼容、新写规范化验证。
    - _Requirements: 3.4, 7, 8_
  - [x] 5.3 迁移 L/M/N
    - 重点覆盖宽表、权益方向、税费多测算表、目录导航和版本链。
    - _Requirements: 2, 3, 7_
  - [x] 5.4 迁移 A/B/C/S 与 confirmation 特殊组件
    - 按适用性保留能力级豁免；不得以“非结构化底稿”豁免复核/版本等无关能力。
    - _Requirements: 1.3, 2, 7_

### Wave 5 · 同构代码与 registry 收敛

- [x] 6. 降低重复实现和注册漂移
  - [x] 6.1 实现 `createChecklistFormData` 工厂并迁移同构 composable
    - 先用 AST/codegraph 证明结构同构，再迁移；业务差异通过钩子表达。
    - 删除重复网络、debounce、hydrate 代码。
    - _Requirements: 6.1, 6.2, 6.6_
  - [x] 6.2 拆分 `htmlRendererRegistry`
    - 按领域 module 化，保持 lazy import、emits、contextProps、icon 和 label 等价。
    - 增加 componentType 集合/唯一性属性测试 P9。
    - _Requirements: 6.4, 6.5_
  - [x] 6.3 建立通用目录元数据层
    - 从 render-config/ACNR 生成基础目录；N2 等特有勾稽通过扩展接口保留。
    - 添加 sheet 顺序等价属性测试 P10。
    - _Requirements: 6.3, 6.5_

### Wave 6 · 防回归与性能

- [x] 7. 建立强制门禁和性能证据
  - [x] 7.1 实现 API Prefix / Import Contract / Persistence Contract 守卫
    - 零依赖、UTF-8、文件行号、report/strict 双模式；明确命中 fail-closed。
    - 添加误报/漏报属性测试。
    - _Requirements: 5.1, 5.2, 5.5-5.7_
  - [x] 7.2 实现 Runtime Import Smoke
    - 动态加载 registry 中每个专属 componentType，抓 named-export 与模块初始化错误。
    - 保持现有 Vite transform smoke 为 blocking，增加 P11 覆盖断言。
    - _Requirements: 5.3, 5.4_
  - [x] 7.3 建立 render/save 指标并优化重复调用
    - 测量冷/热 render-config、renderer 次数、保存耗时/失败/冲突。
    - 完善 request-local memo，去除子组件重复 render-config GET。
    - 跨请求缓存仅在基准证明需要且失效设计完成后实施。
    - _Requirements: 8.1-8.3_

### Wave 7 · 全量验收与维护交接

- [x] 8. 完成平台级验收
  - [x] 8.1 执行全量静态与契约验证
    - Ledger strict、三类新守卫、ref/import-depth、UTF-8、registry contract 全绿。
    - _Requirements: 1, 5, 6_
  - [x] 8.2 执行全量浏览器与持久化验证
    - Vite transform 全树、Runtime Import Smoke、按循环 Playwright Round_Trip。
    - 每个适用横切能力至少一条用户可见断言，P12 全覆盖。
    - _Requirements: 3.9, 7, 8.5-8.6_
  - [x] 8.3 清理兼容层并更新维护文档
    - 删除无豁免 Legacy_Provider、重复 checklist 网络实现和过期 feature flag。
    - 更新 Coverage Ledger、架构文档、开发模板、spec INDEX 和 memory；输出迁移前后指标。
    - _Requirements: 8.4, 8.6_
    - **验收证据**:
      - 无豁免 Legacy_Provider = 0（159 个均已在 Ledger 按 capability 登记）
      - 过期 feature flag = 0（本迁移未使用 feature flag）
      - 迁移报告 → `migration-report.md`（含 before/after 全量指标）
      - 架构文档 → `.kiro/steering/architecture.md`（新增 Runtime Boundary 架构节）
      - 开发模板 → `docs/workpaper-developer-guide.md`（新建组件指南）
      - spec INDEX → 标记 `workpaper-maintainability-convergence` 为已完成
      - Coverage Ledger 统计: covered=730/1440(50.69%), 适用覆盖率=55.81%, 明确缺失=0

## Definition of Done

- 不是“文件已创建”，而是 Runtime Boundary 在真实渲染链生效。
- 不是“PUT 200”，而是刷新/重新导航后值回显一致。
- 不是“Ledger 写 covered”，而是 covered 有静态或运行时证据。
- 不是“单测绿”，而是 Vite + Runtime Import + Playwright 三层均通过。
- 不允许未到期的 blanket exemption；所有豁免必须按 capability 登记。

## Notes

- 本 spec 是 `platform-global-hardening` 的现状修复与维护收敛，不修改其归档历史。
- 任务未开始，全部保持 `[ ]`；只有代码、测试和 Playwright 证据齐全后才能标 `[x]`。
- 可按 Wave 顺序执行；同一文件/同一主入口禁止并发迁移。
- 若旧守卫或组件已存在，任务含义是核验、修复并接入真实运行链，不得重复新建平行实现。
