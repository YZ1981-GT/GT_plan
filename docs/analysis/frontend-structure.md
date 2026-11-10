# 前端结构分析报告（模块拆分依据）

> 分析对象：`audit-platform/frontend/`（Vue3 + Vite + Pinia + Element Plus + Univer）
> 分析日期：2026-11-09 · 分析方式：只读代码扫描
> 用途：为「模块拆分 / monorepo 化 / 按域分包」提供决策依据

---

## 1. 总体规模

| 指标 | 数值 |
|---|---|
| src 下 `.vue` 文件 | 2,523 |
| src 下 `.ts` 文件 | 6,175 |
| src 文件总数 | ~8,700 |
| 全局自动注册组件（components.d.ts） | 2,447 个 |
| Pinia store | 11 个（全部集中在 stores/） |
| 路由域文件 | 11 个（router/domains/） |
| services API 文件 | ~55 个扁平文件 + 3 个域化子目录 |
| 最大单域 | components/workpaper/ 6,545 文件（占 components 87%） |

### src/ 各目录文件数

| 目录 | 文件数 | 说明 |
|---|---:|---|
| components/ | 7,480 | 组件层，87% 集中在 workpaper 巨域 |
| composables/ | 529 | 顶层共享组合式函数（286 个顶层条目） |
| views/ | 357 | 页面层，98 个顶层 .vue + 若干子目录 |
| utils/ | 135 | 基础设施 + 业务工具混合 |
| services/ | 111 | API 封装层 |
| shell/ | 50 | 底稿能力外壳（formula / guidance） |
| stores/ | 25 | Pinia store（11 个）+ 测试 |
| __tests__/ | 104 | 根级测试 |
| router/ | 16 | index.ts + domains/ 11 个域文件 |
| styles/、layouts/、types/、stories/ | 18/9/15/33 | 常规 |
| i18n/ | 3 | zh-CN / en-US 两份 JSON，体量小 |
| shared/ | 5 | 仅 contracts/gc0 跨模块契约 |
| permissions/ | 1 | permission-matrix.ts |
| config/constants/directives/generated/data | 2/7/2/5/1 | 微量 |

---

## 2. 目录结构说明

```
src/
├── main.ts                  # 启动：Pinia、VueQuery、路由、大量全局副作用安装
│                            #（installCrossWpEventBridge、startSessionHandoff、
│                            #  claimClientInstanceId、clearOnUpgrade 等）
├── router/
│   ├── index.ts             # 162 行，只做装配 + 统一守卫（认证/权限/角色/EQCR/项目上下文）
│   └── domains/             # ★ 11 个业务域路由文件（唯一真源，有 spec 锁定）
├── stores/                  # ★ 11 个 Pinia store，全部集中于此
├── services/                # API 封装层：~55 个扁平文件 + apiPaths/(域化) + acnr/ + sse/
├── composables/             # 顶层共享组合式函数（286 条目，含 47 个底稿科目专用）
├── utils/                   # http/eventBus/sse 等基础设施 + 部分业务工具
├── components/
│   ├── workpaper/           # ★★ 巨域：6,545 文件，511 个子目录
│   ├── formula/             # 126 文件，公式引擎 UI（跨域共享）
│   ├── consolidation/       # 114 文件
│   ├── common/              # 67 文件，Gt* 通用 UI 套件
│   ├── attachment/          # 59 文件（跨域共享）
│   └── …（40+ 个 1~50 文件的功能目录）
├── views/                   # 98 个顶层页面 .vue（薄层）+ 9 个子目录
├── shell/                   # WorkpaperCapabilityShell + formula/guidance
├── shared/contracts/gc0/    # 跨模块契约（workpaper-route-baseline、compatibility）
├── layouts/                 # DefaultLayout、ThreeColumnLayout
└── i18n/ styles/ types/ ...
```

### 关于根目录 tsconfig._*.json（重要澄清）

根目录的 `tsconfig._consol-lifecycle.json`、`tsconfig._writer-ownership.json` 等 **不是功能分域配置**。经查 `scripts/typecheck-region.mjs` 注释确认：全量 `vue-tsc --noEmit` 在 4GB/8GB 堆下 OOM（typecheck 脚本需 `--max-old-space-size=40960`），历史上每次改动只能手工建单区域 tsconfig 验证，用完未删、残留十余份。该脚本正是为收敛这一痛点而生。**结论：这些文件是"体量超出工具链承受力"的证据，而非分域架构的存在。**

---

## 3. 功能模块清单

### 3.1 components/ 聚类（按文件数排序）

| 功能模块 | 目录 | 文件数 | 备注 |
|---|---|---:|---|
| **底稿编辑器（巨域）** | components/workpaper/ | **6,545** | 见 3.2 细分 |
| 公式引擎 UI | components/formula/ | 126 | FormulaManagerDialog 4,192 行；被 workpaper/notes/consol 共用 |
| 合并报表 | components/consolidation/ | 114 | ConsolNoteTab 3,439 行、worksheets/ 8 张合并表 |
| 通用 UI 套件 | components/common/ | 67 | Gt* 系列（AmountCell、EditableTable、PageShell、OCR 面板等） |
| 附件 | components/attachment/ | 59 | 被 workpaper 引用 270 次（最重的跨域依赖） |
| 自定义查询 | components/query/ + custom-query/ | 60 | |
| 交付中心 | components/deliverable/ | 48 | |
| AI 对话 | components/ai/ + ai-chat/ | 49 | |
| 附注 | components/notes/ | 29 | |
| 扩展能力 | components/extension/ | 28 | |
| 协作/复核 | components/collaboration/ + review/ | 35 | |
| 网格基础设施 | components/grid/ | 27 | 被 workpaper 引用 67 次 |
| 披露 | components/disclosure/ | 26 | |
| 调整分录 | components/adjustment/ | 24 | 被 workpaper 引用 163 次 |
| 向导 | components/wizard/ | 20 | |
| 账套导入 | components/ledger-import/ + trial-balance/ + ledger/ | 26 | |
| 模板库 | components/template-library/ | 19 | |
| EQCR | components/eqcr/ | 17 | |
| 布局 | components/layout/ | 16 | DetailProjectPanel 1,755 行 |
| 仪表盘 | components/dashboard/ | 16 | |
| 工时 | components/workhour/ | 13 | |
| 报表 | components/report/ | 13 | |
| 系统管理 | components/system/ | 11 | |
| 质控/信任/复核 | qc/ + trust/ + evidence-governance/ | 23 | |
| 其余小目录 | gate、conflict、acnr、diagnostics、panorama、trace、import、pm、partner、signature、status_machine、time_machine、version、consistency、integrity… | 各 1~8 | **40+ 个碎目录**，均需归属决策 |

### 3.2 workpaper 巨域内部结构（components/workpaper/）

| 子目录 | 文件数 | 内容 |
|---|---:|---|
| composables/ | **3,222** | 2,120 个顶层条目：底稿域全局逻辑（cycleCrossRef、cutoff*、d1Disclosure* 等） |
| __tests__/ | 625 | |
| confirmation/ | 295 | 函证 |
| sync/ | 111 | 循环同步 |
| **110 个科目/循环编号目录** | 各 13~72 | a1/a17、b22/b23、c*、d1~d7、e1、f1~f4、g0~g12（含 g7-long-term-equity-main 等命名）、h1~h9、i1~i6、j1~j3、k1~k10、l1~l8、m1~m2、n1~n5、s*；多数自包含组件+逻辑 |
| shared/、kit/、headless/、GtDForm/ | ~80 | 共享件、Wp* 基础组件、headless 框架 |
| f2/、d4/、e1/、voucher-sampling/、s-checklist/、s34-ipo-bundle/、g0-confirmation/ | 各 20~72 | |
| 顶层 Gt*.vue | 372 | GtC1EntityControl 3,168 行、GtB50RiskAssessment 2,826 行等 |

**观察**：`shell/`（能力外壳）、`workpaper/kit/`（Wp* 基础组件）、`headless/`（headless 框架 + registry）已具备"框架 + 插件"雏形；110 个科目目录是天然的分包单位，但它们大量依赖 workpaper/composables/ 的 3,222 个共享文件，形成域内交叉。

### 3.3 views/ 聚类

views/ 是薄页面层（98 个顶层 .vue），真正的实现下沉到 components/。典型如 `views/WorkpaperEditor.vue` 仅 1,344 行，是编排层而非实现层。子目录：workpaper-editor/(13)、workpaper-list/(5)、qc/(6)、extension/(9)、ledger/(3)、eqcr/(3)、ai/(2)、adjustments/、admin/、independence/、handbooks/。

---

## 4. 路由组织方式

**已按业务域分文件，质量较高。**

- `router/index.ts`（162 行）：只做装配，注释明确"domains/*.ts 为唯一真源"；统一守卫负责认证、权限（meta.permission）、角色（meta.roles）、EQCR 年度独立性阻断、项目上下文同步。
- `router/domains/` 11 个域文件：auth、dashboard、projects（256 行，最大）、workpapers、reports、notes、confirmations、qc、extension、system、standalone（独立查账窗口等游离于 DefaultLayout 之外的页面）。
- 全部视图懒加载；存在 `routeDomainProjection.spec.ts` 断言域结构（跨域 name 不重复、域内 path 全部进入声明集合），以及 `backendRouteShapes.contract.spec.ts` 用同一张表核对后端跳转路由。

**结论：路由层是本次拆分可直接复用的域划分真源。**

## 5. stores（Pinia）组织

11 个 store 全部集中在 `stores/`，无散落定义（grep 确认 composables/ 下无 defineStore）。

| store | 行数 | 归属 |
|---|---:|---|
| auth | 198 | **全局**：token/user/角色 |
| project | 352 | **全局**：当前项目上下文（路由 :projectId 同步） |
| dict | 174 | **全局**：数据字典 |
| roleContext / displayPrefs | 157/306 | **全局**：角色视角、显示偏好 |
| addressRegistry | 512 | 底稿域：单元格地址注册表 |
| guidancePanelStore | 476 | 底稿域：引导面板 |
| chatRunState | 373 | AI 域：对话运行态 |
| wizard | 362 | 项目向导 |
| drilldown | 294 | 钻取 |
| collaboration | 75 | 协作 |

**观察**：状态面很小（3,279 行总量）——大量业务状态在组件内 / composable 内而非全局 store，这对拆分非常有利（跨域状态通道少）。当前全局 store 与业务 store 同层存放，拆分时按归属迁移即可。

## 6. services（API 层）组织

**是 API 封装层，且半域化、半扁平。**

- 扁平文件 ~55 个（13,069 行）：`commonApi.ts`（2,381 行，大杂烩）、`consolidationApi.ts`（1,627）、`auditPlatformApi.ts`（1,094）、`workpaperApi.ts`（853）、`aiApi.ts`（675）等；函数式封装，无类继承，依赖 `utils/http.ts`。
- **域化先例（较新）**：`services/apiPaths/` 已按域分文件（accounting、collaboration、formula、formulaSettings、project、report、system、workpaper）——这是 API 层域化的官方模板；另有 `acnr/`、`sse/` 子目录；qc* 5 个文件、consol* 4 个文件按前缀成组。
- workpaper 对 services 的依赖集中在 `apiProxy`（525 次）、`trialBalanceRows`、`cycleDirectory`、`workpaperApi`。

**结论：域边界在 apiPaths/ 已划好，把扁平 *Api.ts 迁到对应域即可完成 services 分域；commonApi.ts 是主要欠账。**

## 7. 共享层耦合度评估（shared/、composables/、utils/）

### 7.1 shared/ —— 形同虚设但方向正确

`shared/contracts/gc0/` 只有 5 个文件：workpaper 路由基线与兼容性契约 + spec。说明团队已有"跨模块契约用测试锁"的意识，但真正的公共代码并没有放进 shared/。

### 7.2 composables/ —— 名为共享，实为"共享 + 底稿域"混合层（主要耦合源）

| 检查项 | 结果 | 判定 |
|---|---|---|
| 顶层 286 条目中带底稿科目编号（useA13/useB60/useC24/useD1*…） | **47 个** | 底稿域逻辑泄漏进共享层 |
| composables → @/components 的文件 | 49 个（其中 88 处指向 components/workpaper，另 formula/collaboration/query/grid） | **共享层反向依赖组件层（上行依赖）** |
| composables → @/services | 146 个文件 | 正常（数据获取型 composable） |
| composables → @/stores | 27 个文件 | 正常 |
| components/workpaper → 顶层 composables | 大量（domain 外另有 composables/workpaper/ 桥接） | 巨域对共享层强依赖 |

### 7.3 utils/ —— 基础设施为主，少量上行依赖

- 核心基础设施：`http.ts`(807)、`eventBus.ts`(851，全局 mitt 总线 + 跨底稿事件桥)、`sse.ts`(590)、`confirm.ts`(407)、`crossWindowAuth.ts`(182)、`clientInstance.ts`(324)。
- **6 个 utils 文件 import 组件**（PasswordConfirmDialog、workpaper、query、grid、ai）——工具层不应依赖组件层，属欠账。
- `main.ts` 在挂载前安装多个全局副作用（installCrossWpEventBridge、installPushKeptNotice、clearOnUpgrade、startSessionHandoff、claimClientInstanceId），形成**运行时全局时序耦合**，拆分时必须显式化为初始化协议。

### 7.4 上行依赖全景（违规方向）

| 方向 | 位置数 | 说明 |
|---|---|---|
| components → views | ~10 处 | consolidation(2)、notes(1)、dashboard/gate/layout 测试(若干)——组件反向引用页面 |
| composables → components | 49 文件/100+ 处 | 88 处指向 workpaper |
| utils → components | 6 文件 | 对话框助手类 |
| 无 ESLint 边界规则 | — | 无 no-restricted-imports、无 dependency-cruiser；现有 13 条自定义规则均为业务约定（金额、对话框、UI 语言） |

### 7.5 巨域的对外依赖（双向）

- workpaper → 外部：attachment(270)、adjustment(163)、grid(67)、common(10)、formula(4)。
- 外部 → workpaper：views(41 个文件，多为编辑器编排页)、composables(22)、formula(2)、consolidation(2)、adjustment(4)、workpaper-list/editor 视图(8)。
- attachment 与 adjustment 已是"准共享域"，拆分时应先归位。

---

## 8. 打包与工具链现状

- **manualChunks 仅按重依赖分包**（vite.config.ts）：vendor-core（vue/element-plus 同块避免循环）、heavy-univer、heavy-office、heavy-excel + `onlyExplicitManualChunks: true`。**没有任何按业务域的 chunk 划分**，但整套"重块隔离 + 防循环 chunk"经验可直接映射到按域分包。
- **components.d.ts 自动注册 2,447 个组件**（unplugin-vue-components）：模板中可不写 import 直接使用组件 → 显式依赖声明缺失，grep import 统计会低估真实依赖；拆分前建议改为显式 import 或按域配置 resolver。
- **全量类型检查不可行**：`vue-tsc` 需 40GB 堆，root 下 10 份 `tsconfig._*.json` 残留 + `typecheck:region` 工具是痛点实证；monorepo + project references 反而是治本方案。
- 存在 `bundle:check` 预算脚本、`build:verify`、`smoke:built` 等质量门禁，拆分时可沿用。
- 测试基建充足：vitest 单测（大量 spec 与域契约测试）、Playwright 多套 e2e 配置、render-smoke。

---

## 9. 拆分友好度结论

### 总评：★★★☆☆（3/5，中等偏友好）——"骨架已就位，血肉未分离"

### 有利因素

1. **路由已按域分文件且有契约测试锁**——域划分有官方真源，拆包时直接照 router/domains 映射。
2. **Pinia store 极少且集中**（11 个，3.3k 行）——跨域全局状态通道少，迁移成本低。
3. **services/apiPaths/ 已域化**——API 层域化模板现成。
4. **views 是薄页面层**，实现下沉 components——按域搬迁 views 摩擦小。
5. **workpaper 的 110 个科目目录天然自包含**，且 shell/kit/headless 已是"框架+能力插件"雏形。
6. **shared/contracts/gc0 证明团队会用契约测试锁边界**。
7. 路由全懒加载 + manualChunks 经验 + bundle 预算门禁——构建侧已具备分包意识。

### 障碍（按严重度）

1. **巨域失衡**：workpaper 6,545 文件占组件层 87%，域内 composables/ 3,222 文件被 110 个科目目录交叉引用——拆分的核心工作量在此，且它内部要先行"域内分层"才能对外包。
2. **顶层 composables/ 被底稿域渗透**：47 个科目专用 composable + 88 处对 workpaper 组件的引用——"共享层"必须先做搬移清洗，否则任何包都会被 workpaper 拖住。
3. **上行依赖无门禁**：composables→components(49)、components→views(~10)、utils→components(6)；无 import 边界 lint，目前靠约定自觉。
4. **components.d.ts 自动注册 2,447 组件**：显式 import 缺失，依赖分析失真，拆包统计会漏。
5. **运行时全局副作用**：main.ts 的事件桥/会话接力/客户端号认领等启动时序，是包间隐式协议。
6. **utils/eventBus(851 行) 全局事件总线**：跨域通信不走显式接口，拆包后需要替换为模块接口。
7. **services/commonApi.ts 2,381 行大杂烩**：拆域的最大单点欠账。
8. **40+ 个 1~8 文件的碎目录**（gate/conflict/acnr/diagnostics/trace…）：每个都需归属决策。
9. **attachment/adjustment 与 workpaper 双向强依赖**（270/163 次）：应先升格为共享域或回收到 workpaper。

### 建议拆分路径（与"微前端"对比）

**不推荐微前端**：单团队开发、共享 Univer 编辑器/公式引擎/事件总线太深、启动副作用交织，qiankun/module federation 收益小于成本。**推荐 monorepo 按域分包（pnpm workspace + tsconfig project references）**，天然解决全量 typecheck OOM 痛点。

分四步（可独立交付、每步有门禁）：

| 步骤 | 内容 | 依据 |
|---|---|---|
| ① 立边界（1~2 周） | 引入 eslint no-restricted-imports / dependency-cruiser：禁止 composables→components、components→views、utils→components；把 47 个科目 composable 移入 components/workpaper/composables | 现有上行依赖清单 |
| ② 拆无争议独立域 | auth、system、extension、workhour、eqcr、ledger-import、dashboard → packages/*，services 同步按 apiPaths 域化；拆 commonApi | 路由域文件现成 |
| ③ 拆中间域 | reports、notes、confirmations、qc、deliverable、ai、consolidation；attachment/adjustment/grid/formula 归入共享包（shared-ui），用契约测试锁接口 | gc0 契约先例 |
| ④ workpaper 内部分层后成包 | 域内拆 shell(框架)/kit(基础件)/headless(registry)/cycles(110 科目目录)/composables(域内共享)，之后整体成一个可独立构建的包 | shell/kit/headless 雏形已存在 |

配套：components.d.ts 按域收敛（或改显式 import）；main.ts 启动副作用改为各包显式 init() 协议；vite manualChunks 从"按 node_modules"改为"按包"，沿用 onlyExplicitManualChunks 防循环经验。

---

## 附：关键数字速查

- 全量 typecheck 需 `--max-old-space-size=40960`（40GB 堆），否则 OOM
- components.d.ts 注册 2,447 个自动导入组件
- 顶层 composables 中科目专用：47 个；引用 workpaper 组件：88 处
- workpaper → attachment 270 次 / adjustment 163 次 / grid 67 次 / apiProxy 525 次
- 最大文件：formula/FormulaManagerDialog.vue 4,192 行；workpaper/GtC1EntityControl.vue 3,168 行；services/commonApi.ts 2,381 行；utils/eventBus.ts 851 行
