# 需求：生产构建白屏收口

来源：`platform-release-blocker-closure` design §9.6。`build:verify` 产物在浏览器报
`vendor-core-*.js:30:11317 Cannot access 'Rt' before initialization`，根组件未挂载；
干净 base worktree（远端 HEAD）重建同样复现，说明是既有缺陷。`smoke-built-artifact.mjs`
不执行 JS，所以漏检。

## R1 根因定位
- 用产物 sourcemap 或未压缩构建，还原 `Rt` 对应的模块，并给出 chunk 间 import 环的证据
  （每个 chunk 的静态 import 图，环的两端名字）。
- 假设（待证）：`onlyExplicitManualChunks: true` 使 element-plus 的传递依赖
  （lodash-es、dayjs、@floating-ui、@popperjs、async-validator 等）不在 vendor-core，
  落进入口或共享 chunk，而它们又反向 import vendor-core，形成循环。

## R2 修复
- 首屏必须能挂载，登录页表单可见，console error 为 0。
- 不得把 Vue 与 Element Plus 拆成 core/ui（`vite.config.ts` 已注明会形成循环）。
- 包体预算（`bundle-budget.json`）不得超过现有阈值。

## R3 smoke 增加浏览器执行步
- `build:verify` 在 smoke 阶段用无头浏览器加载产物登录页，断言：根节点有子元素、
  无 `pageerror`、无 console error。
- 白屏时该步骤必须失败（要有阴性对照：故意制造循环 chunk 时为红）。

## R4 守卫
- 构建后检查 chunk 静态 import 图无环（只检查入口可达的静态边，动态 import 不算）。

## 非目标
- 不改业务代码，不改 `heavy-univer` / `heavy-office` / `heavy-excel` 的拆分策略，除非根因在其中。
