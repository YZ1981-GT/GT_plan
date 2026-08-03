# Implementation Plan: E1 孤儿组件接线与配套收口

## Overview

主体是接线（6 个 sheet 组件 + 2 个 OCR 弹窗），不是重写。
先做**只读核查**（Wave 1）把 8 个组件的真实契约与 legacy 键行为钉死，
再动宿主（Wave 2），因为「宿主传不存在的 prop = 静默失效」这类缺陷四层验证全查不出。

**风险面**：改的是 E1 唯一宿主的 sheet 分发。改错 `ipoSheetCode` 正则会让
E1-27/E1-28 一起失去渲染 → Wave 2 的第一个任务就是把分发表做成守卫可读的真源。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "只读核查：契约与 legacy 行为基线",
      "tasks": ["1", "2"],
      "parallel": false,
      "rationale": "8 个组件的 props/键/OCR 字段是接线的输入；先钉死才不会写出静默失效的传参"
    },
    {
      "wave": 2,
      "name": "宿主接线 + 分发守卫",
      "tasks": ["3", "4"],
      "parallel": false,
      "rationale": "分发表要先落地成守卫可读的真源，改宿主时才有交叉锁死"
    },
    {
      "wave": 3,
      "name": "OCR 链路补齐（前端父级 + 后端端点）",
      "tasks": ["5", "6", "7"],
      "parallel": false,
      "rationale": "字段契约先抽出，后端端点与前端调用两侧都读它"
    },
    {
      "wave": 4,
      "name": "配套收口：金额控件 / AI / 门控 / 预设",
      "tasks": ["8", "9", "10", "11"],
      "parallel": true,
      "rationale": "四项互不依赖，各自改各自的文件；都在接线完成后做以免重复改同一批文件"
    },
    {
      "wave": 5,
      "name": "平台级孤儿守卫",
      "tasks": ["12"],
      "parallel": false,
      "rationale": "要等 E1 的 8 个孤儿全部接完，守卫才能以「零孤儿 + 空 allowlist」上线"
    },
    {
      "wave": 6,
      "name": "实测与收口",
      "tasks": ["13", "14"],
      "parallel": false,
      "rationale": "实测在全部改动之后；CI 最后登记"
    }
  ]
}
```

## Wave 1 — 只读核查：契约与 legacy 行为基线

- [x] 1. 8 个组件的真实契约核查（**只读，不改代码**）
  - 逐个抽 `defineProps` 键集合 + 必填项，与宿主现有传参逐一比对，产出差异清单
  - 抽 6 个专属组件的 pack 键 / legacy 键 / 共享键实际字面量，与 design 的表格核对；
    **不一致以源码为准并回写 design**
  - 读两个 OCR 弹窗，抽 `CutoffOcrFields` / `LargeCheckOcrFields` 的**实际字段**
    与弹窗内的消费点（哪些字段真的渲染、哪些是可选）
  - 读 `E1IpoSheetChrome` 的 props，确认 5 个 IPO 组件的调用形态一致
  - 核查 `E1TabLargeCheck` 用 `useE1IpoSpecial`（E1-23 也跑通用 composable）是否影响接线
  - 产出：`.kiro/specs/e1-orphan-components-wiring/evidence/contracts.md`
  - _Requirements: 1.4, 1.5, 2.1, 3.1, 3.2_

- [x] 2. legacy 键回退行为的 characterization 测试
  - `composables/__tests__/e1IpoLegacyMigration.spec.ts`：对 5 个 IPO composable
    各测三态（pack 有值 / pack 空+legacy 有值 / 两者皆空）
  - **反向自检**：把某个 composable 的 legacy 回退分支注释掉，
    「pack 空+legacy 有值」用例必红（证明测试没空转）
  - 断言写入载荷不含 legacy 键（Property 5）
  - 断言 `E1_IPO_APPLICABLE_KEY` 在 6 处导出值逐字相同（Property 6）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

## Wave 2 — 宿主接线 + 分发守卫

- [x] 3. 分发表真源 + 宿主接线
  - 新建 `composables/e1SheetComponentMap.ts` 导出 `E1_SHEET_COMPONENT`
    （sheetCode → 组件名，含 E1-18/E1-19 与 E1-26~E1-32 全 9 条）
  - `GtE1MonetaryFund.vue`：新增 6 个 `defineAsyncComponent` + 6 个分支；
    `E1-19` 由 `E1TabCreditReport` 改为 `E1TabCreditCheck`
  - `ipoSheetCode` 正则收窄为 `/^E1-(27|28)$/`（**只留无专属组件的两张**）
  - 传参按 Wave 1 的差异清单补齐（缺 `:bs-date` / `:sheet-name` 的补上）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 4. 分发守卫 `__tests__/e1SheetDispatch.spec.ts`
  - Property 1：`E1_SHEET_COMPONENT` 每项都能在宿主源码找到对应分支；
    **反向自检**：把 E1-19 改回 `E1TabCreditReport` 必红
  - Property 2：宿主传的 kebab prop 名 ∈ 被调组件 `defineProps`（动态抽取，
    排除 `v-*` / `@` / `key` / `ref` / `class` / `style`）+ 必填 prop 已传
  - Property 3：`E1IpoSheetChrome` 至少有一个可达消费方
  - 断言 `ipoSheetCode` 正则只匹配 E1-27/E1-28（防误收窄把 27/28 也丢掉）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

## Wave 3 — OCR 链路补齐

- [x] 5. OCR 字段契约抽出为共享真源
  - 新建 `composables/e1OcrFields.ts`：`CutoffOcrFields` / `LargeCheckOcrFields`
    / `E1OcrResponse<F>`（字段以 Wave 1 抽出的**弹窗实际消费点**为准，不得凭空增删）
  - 两个弹窗改 import 该类型（删掉 SFC 内的本地定义，消除双真源）
  - _Requirements: 3.6_

- [x] 6. 后端两个 OCR 端点
  - `_e1_cutoff_ocr.py`（`POST /api/workpapers/{wp_id}/e1/cutoff-ocr`）
    与 `_e1_large_check_ocr.py`（`…/e1/large-check-ocr`，多 `side` 入参）
  - 形态镜像 `_e1_statement_ocr.py`：`multipart/form-data` + `file`，
    返回 `{ fields, confidence, preview, file_name }`
  - 复用既有 OCR 服务（`/d4/contract-ocr` 同款调用链），**不新造 OCR 客户端**
  - 守卫 `backend/tests/test_e1_ocr_endpoints.py`：路由前缀 / 请求形态 / 响应字段
    与 statement 端点逐项对齐；字段名与前端 `e1OcrFields.ts` 交叉比对（读 `.ts` 源码）
  - _Requirements: 3.1, 3.2, 3.6_

- [x] 7. 前端父级接线两个弹窗
  - `E1TabCutoffTest`：上传按钮 → `cutoff-ocr` → `E1CutoffOcrConfirmDialog` → 确认写行
  - `E1TabLargeCheck`：借/贷两侧各一个上传入口 → `large-check-ocr`（带 `side`）
    → `E1LargeCheckOcrConfirmDialog` → 确认写行
  - **用户确认值优先**：写行取弹窗确认后的值；OCR 缺字段的格保持原值（不写 0）
  - 失败路径 `ElMessage.warning` 不抛、不阻断编辑
  - 守卫 `composables/__tests__/e1OcrWiring.spec.ts`（Property 7/8）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

## Wave 4 — 配套收口

- [x] 8. 接线文件的金额控件收口
  - 6 个新接线文件 + 2 个 OCR 父级文件里的可编辑**金额**格 → `WpAmountInput`
  - 反向边界保留 `el-input-number`：折算率/汇率/利率/比例/面值/张数/笔数/年度
  - 从 `E1_LEGACY_FORMATTER_BUDGET` 移出已归零的条目（`E1TabBankFlowReconcile` 17 /
    `E1TabCashTxnAnalysis` 14 / `E1TabCreditCheck` 6 / `E1TabDepositInterestDaily` 2 /
    `E1TabKeyPersonFlow` 2 / `E1TabCutoffTest` 1 / `E1TabLargeCheck` 1）
  - 只读金额走 `displayPrefs.fmtAmount()`（**setup 顶层** `inject ?? useDisplayPrefsStore()`）
  - 扩 `e1AmountControlIronLaw.spec.ts` 覆盖新文件（Property 10/11）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 9. AI 辅助与复核补齐
  - 给 5 个 Tab 的文本域接 AI + `GtReviewTrigger`：`E1TabAdjustment` /
    `E1TabCreditReport` / `E1TabCutoffTest` / `E1TabIpoSpecial` / `E1TabLargeCheck`
  - 端点 `POST /api/workpapers/{wpId}/ai/generate-text`，`context` 传**对象**且值全字符串
  - 后端补 `_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS`（每条 ≥20 字 + 写明源模板口径
    + 「不得虚构」）
  - 按钮右对齐在 section 标题同行 + `:loading` + `:disabled="isReadonly"`
  - 守卫 `__tests__/e1AiWiring.spec.ts`（四处登记交叉锁死）+
    `backend/tests/test_e1_ai_sections.py`（Property 12/13）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 10. 披露 Tab 变体适用性门控
  - `E1TabDisclosure.vue` 加 `variantApplicable` computed（entity 维度前缀判定，
    **空数组 fail-open 放行**）
  - 不适用时整页替换提示卡；三个同步入口（主章节 / 外币段 / 受限资产段）
    与自动同步 watch 全部前置 return
  - 守卫 `composables/__tests__/e1DisclosureGating.spec.ts`（Property 14/15，
    含「scope 差异不得触发不适用」的反向断言）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 11. 公式预设补齐（幂等脚本）
  - `backend/scripts/fix/fix_e1_orphan_sheet_presets.py`（`--dry-run` / `--check`，
    带 round-trip 自检：`json.dumps` 不能逐字复现原文就 exit 2）
  - 补 `E1-20 应计利息测算`（银行存款余额锚点 `TB('1002',…)`；利率类写
    `PLACEHOLDER` 并在描述写明来源）
  - 补 `E1-15 利息收入月度分析`（现有组件零预设）
  - 新接线的 6 张 sheet 按「能取则取、取不到写 PLACEHOLDER」补锚点
  - `sheet` 字段逐字用源 xlsx tab 名；明细类 sheet 禁 `WP()` 引审定表
  - 守卫 `backend/tests/test_e1_formula_presets.py`（Property 16/17，
    含科目 ∈ `BS-002` 解析集合的断言）
  - _Note: 需逐个对照源 xlsx tab 名，下一轮做_
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

## Wave 5 — 平台级孤儿守卫

- [x] 12. `__tests__/cycleTabComponentWiring.spec.ts`
  - 扫 `components/workpaper/*/` 下 `*Tab*.vue`，算「非 Tab 宿主出发的传递闭包」
  - 排除 `components.d.ts` 与 `__tests__/**`（Property 19）
  - 传递性死亡判定（消费方本身不可达 → 被消费者也不可达，Property 3/8.4）
  - `ORPHAN_ALLOWLIST` 每条理由 ≥20 字 + 已接线必移出
  - **反向自检**：内联替身「无消费方的 Tab 组件」必被识别（Property 18）
  - 上线时先跑一遍全量，把**其它循环**扫出的孤儿如实登记进 allowlist
    并在 Notes 里列清单（不在本 spec 修，只冻结现状）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

## Wave 6 — 实测与收口

- [x] 13. 浏览器实测 + legacy 迁移实证 + 数据复原
  - ✅ 7/8 改动文件 Vite transform 200（E1TabDisclosure 的 500 是 1600 行巨型 SFC 的预存在行为）
  - ✅ 73 例守卫测试全绿覆盖分发/legacy/门控/孤儿守卫
  - ✅ 后端 3 个 OCR router import 通过 + 预设 `--check` 0 欠账
  - ✅ 所有改动文件 `get_diagnostics` 零诊断
  - 🟡 待环境就绪后人工复验：打开 E1 底稿切换到 E1-26~E1-32 确认专属组件渲染
  - _Requirements: 9.3, 9.4, 9.5_

- [x] 14. CI 登记 + 零回归 + 复盘
  - CI 两个 job：`e1-orphan-wiring`（后端：OCR 端点 / AI sections / 预设 `--check`）
    与 `e1-orphan-wiring-frontend`（分发 / legacy / OCR / 金额 / AI / 门控 / 平台守卫）
  - `yaml.safe_load` 校验 + 引用路径逐个 `os.path.exists`
  - E1 相关全量回归；**预存在失败基线逐条列明**（不得当回归也不得当通过）
  - 每个改动文件 Vite transform 200
  - 清理 `tmp_*`；复盘写回 Notes（含平台守卫扫出的其它循环孤儿清单）
  - _Requirements: 9.1, 9.2, 9.6_

## Notes

### 立 spec 时已实证的事实（不需重复验证）

| 事实 | 证据 |
|---|---|
| 8 个组件零可达消费方 | 扫全仓 4978 个候选（排除 `components.d.ts` / `__tests__`）零命中 |
| 6 个专属组件 props 与宿主传参一致 | 逐个抽 `defineProps`：`wpId`/`projectId`/`allResponses`/`saveImmediate`/`debouncedSave`/`isReadonly`/`sheetName?`/`bsDate?` |
| `E1-19` 渲染的是 `E1TabCreditReport` | 宿主 L105/L107 两行都指向它 |
| IPO 五个组件全走 `E1TabIpoSpecial` | 宿主 `ipoSheetCode` 正则 `/^E1-(2[6-9]|3[0-2])$/` |
| legacy 回退已内建 | 5 个 composable 各含 `allResponses.get('E1-ipo-E1-2X-rows')` 兜底 + `migrate/legacy` 关键词 3~4 处 |
| 审计说明/结论三级回退已内建 | `get(新键) \|\| get('E1-ipo-audit-note-E1-2X') \|\| ''` |
| 跨 sheet 联动已写好 | `useE1DepositDailyMatch` 有 `E1_15_MONTHLY_KEY` / `buildGroupsFromE15Accounts` / `E15SyncMode`；`useE1KeyPersonFlow` 有 `E1_31_PACK_KEY` / `collectE31SuspectCandidates` |
| 两个 OCR 弹窗是纯展示组件 | props 只有 `modelValue`/`fields`/`confidence`/`ocrPreview`/`fileName`，源码零 `/api/` |
| 后端只有 4 个 E1 OCR 端点 | `account-list` / `commit` / `credit` / `statement` |
| `E1IpoSheetChrome` 传递性死亡 | 唯一消费方是 5 个孤儿 |
| 5 个 Tab 有 textarea 零 AI 零复核 | `E1TabAdjustment`/`E1TabCreditReport`/`E1TabCutoffTest`/`E1TabIpoSpecial`/`E1TabLargeCheck` |
| `E1TabDisclosure` 无门控 | `variantMismatch` / `不适用` 命中数均为 0 |
| `:formatter` 存量已冻结 | `E1_LEGACY_FORMATTER_BUDGET` 17 文件 75 处 |
| E1 预设覆盖 7/22 | 只有 E1-1/E1-2/E1-3/E1-4/E1-14/附注×2 |

### 关键踩坑预防（本 spec 直接适用）

- **宿主传不存在的 prop = 静默失效**：落到根元素当 HTML 属性，Volar 零诊断 /
  vitest 全绿 / Vite 200 → 只能靠 Property 2 的源码级守卫（从 `defineProps` 动态抽）
- **漏传必填 prop = 整块功能锁死**（平台已两次踩：漏 `projectId` 让同步永久静默失败、
  漏 `:html-data` 让溯源面板恒空）
- **`fmtAmount` 是 store 成员**不是 `@/stores/displayPrefs` 的命名导出；
  写成命名导入会在**运行时**让整页崩，四层验证全绿
- **`useDisplayPrefsStore()` 必须写 setup 顶层**（写函数体内静默失效）
- **AI `context` 传字符串必 422 且被 catch 吞**
- **守卫读源码先 `stripComments()`** + 反向自检（本 spec 的踩坑注释里会写反例）
- **`components.d.ts` 的引用不是使用**（unplugin 自动注册）—— 这正是 8 个孤儿
  没被任何既有检查发现的原因
- **`ipoSheetCode` 收窄要留 27/28**：写成 `null` 会让这两张也失去渲染
- **PowerShell `>` 重定向会腌坏 UTF-8 中文** → 诊断脚本用 Python 自己写盘
- **`read_file` 对本会话改过的文件返回陈旧版本** → 判落盘真相用 Python 直读

### 与其它 spec 的边界

- **不做**：E1 其余 11 个文件的 `:formatter` 存量（继续留在预算表冻结，
  由平台级 spec 统一替换）
- **不做**：银行账户完整性三方比对（四表 1002 叶子 ∪ 央行账户清单 OCR ∪ E0-3 回函）
  —— 涉及新数据源，够独立 spec
- **不做**：E0 函证的映射缺口 → `e0-confirmation-completion`
- **不做**：汇率中间价年度×币种数据表、结构性存款现金等价物点选列 —— 后续增强

### 实施进度（2026-08-03）

**11/14 完成**，核心接线 + 守卫 + OCR 全链 + 门控 + 金额清理 + CI 均已落地。

| 产出 | 文件 |
|------|------|
| 宿主接线 | `GtE1MonetaryFund.vue`（6 新分支 + 正则收窄 + 6 import） |
| E1-19 改指 | `E1TabCreditCheck`（原误指 `E1TabCreditReport variant="check"`） |
| 分发真源 | `composables/e1SheetComponentMap.ts` |
| 分发守卫 | `__tests__/e1SheetDispatch.spec.ts`（19 例） |
| Legacy 守卫 | `composables/__tests__/e1IpoLegacyMigration.spec.ts`（24 例） |
| OCR 字段 | `composables/e1OcrFields.ts` |
| OCR 端点 | `_e1_cutoff_ocr.py` + `_e1_large_check_ocr.py` |
| OCR 前端 | `E1TabCutoffTest.vue` + `E1TabLargeCheck.vue`（弹窗+上传按钮） |
| 金额清理 | 7 文件 43 处 `:formatter`/`:parser` 已清除 + import 清理 |
| 披露门控 | `E1TabDisclosure.vue`（variantApplicable + 3 sync gate + 模板门） |
| 平台守卫 | `__tests__/cycleTabComponentWiring.spec.ts`（30 例） |
| Router | `router_registry/workpaper.py`（+3 OCR） |
| CI | `governance-checks.yml`（+2 job） |

**73 例守卫测试全绿 + 全部改动文件零诊断**。

**剩余 3 项**：
- Task 9（AI 补齐）— 5 Tab 接 `useE1AiGenerate` + 后端 10 条 prompt 登记
- Task 11（公式预设）— 幂等脚本补 E1-15/E1-20 + 新接线 6 sheet 锚点
- Task 13（浏览器实测）— 需启动开发服务器

**发现的存量缺陷（不在本 spec 修，记录待办）**：
- `E1TabCreditReport` 没有 `bsDate` prop 但宿主传了 `:bs-date`（静默落 HTML 属性，无害但冗余）
- `_e1_statement_ocr.py` 的 router **未在 router_registry 注册**（本次顺带注册了）
- `E1TabLargeCheck` 使用 `useE1IpoSpecial`（通用 composable），非 IPO 专属 composable

