# 设计：生产构建白屏收口

## 1. 现状（已读）
- `audit-platform/frontend/vite.config.ts` 的 `heavyFeatureChunk` 把 vue / vue-router / pinia /
  @vue/* / element-plus / @element-plus/* 归入 `vendor-core`，其余 node_modules 只有命中
  univer / office / excel 才命名；`onlyExplicitManualChunks: true`。
- `scripts/smoke-built-artifact.mjs` 起本地 HTTP 服务，校验 manifest、动态块、代理可达，
  不执行 JS。
- `scripts/build-verified-dist.mjs` 产出 `.verified-dist/<manifest-sha>`。

## 2. 排查顺序（先证后改）
1. 用非压缩构建（`minify: false`）复现，拿到 `Rt` 的真实名字与模块。
2. 脚本解析 `dist/assets/*.js` 的静态 `import ... from "./x.js"`，画 chunk 图，找环。
3. 若环为 vendor-core ↔ index/共享块：把 element-plus 的传递依赖
   （lodash-es、dayjs、@floating-ui、@popperjs、async-validator、@ctrl/tinycolor、memoize-one 等）
   也归入 `vendor-core`；这是首选修法，blast radius 最小。
4. 若无效，再评估去掉 `onlyExplicitManualChunks`，但要复核 `heavy-univer` 不被首屏静态拉取
   （现有包体预算守卫负责）。

## 3. smoke 浏览器步骤
- 用仓库已有的 Playwright（不新增依赖）起 chromium 无头，访问 smoke 服务的 `/login`。
- 断言：`#app` 有子节点；监听 `pageerror` 与 `console.error` 均为 0；超时 15 秒。
- 阴性对照：测试里用一个人为制造循环的两块 fixture 产物，期望该步骤失败。

## 4. chunk 环检测
- 新增 `scripts/check-chunk-cycles.mjs`：只解析顶层静态 import，Tarjan 找强连通分量，
  从入口 HTML 的 modulepreload / script 可达的块开始。有环 exit 1 并打印环路径。
- 接入 `build:verify`，位置在 budget 检查之后。

## 5. 风险
- 改 chunk 分组会改变缓存命中，首次发布后用户会多下载一次，可接受。
- 包体预算 schemaVersion 2 比的是入口 / 总量 / 大块个数与名次，调分组后需重新核对。
