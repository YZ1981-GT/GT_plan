/**
 * D3 预收账款 —— 真栈双向验收（切在线编辑 → OO canvas 逐值断言 → 改一格 → forcesave →
 * 回读结构化视图等值）。
 *
 * spec: d3-sync-coverage-via-row-table-engine · Task 16 · Requirements 8.3 / 8.4
 *
 * 🔴🔴🔴 本文件后缀 `.blocked.spec.ts` **不进** Playwright 默认 glob（`*.e2e.spec.ts` /
 * `*.spec.ts` 由 playwright.config 收集，`.blocked.spec.ts` 被排除），因此**不会被误跑成
 * 「真栈已过」**。它是 Task 16 真栈判据的**骨架**，登记「adapter 注册后应当怎么跑」，
 * 当前**不可执行**——原因如下。
 *
 * ═══ 为什么真栈整段标 [ ]*（裁决 F5，Task 5 实测复核不变）═══
 *
 * D3 的 `adapter_registered=False`，且有两道卡点（`evidence/task5-performance-baseline-and-
 * adapter-status.md` §二实测，本任务 2026 复核仍成立）：
 *   ① D3 的 manifest `capability="single_onlyoffice"`（非 `bidirectional`）——
 *      `attach_adapters()` 第一步 `manifest_capability_enabled()` 即短路返回 ()，adapter 不注册；
 *   ② 即便解除①，三端点/整册 materialize 唯一前置门 `_registration()` 调用的是**全量**
 *      `register_from_manifest()`，它会先在处理 **D2** 时因契约结构漂移抛 `ContractDriftError`，
 *      在到达 D3 之前就中断（→ 422）。
 * ⇒ 「切在线编辑 → materialize」在真库跑不起来。裁决 F5：真栈判据如实标 [ ]*，
 *    **不得**以合成测试冒充真栈。故本骨架保留可读、可复用，但不执行。
 *
 * ═══ adapter 注册后解锁本脚本的前置（provisioning，非本 spec 范围）═══
 *
 *   1. D3 overlay 裁决为 bidirectional + 重生 manifest（`capability` 改 `bidirectional`、
 *      `adapter_id` 写回 `d3.prepaid_receipts_detail`）；
 *   2. 发布链产出 approved bundle + current published representation + entry_state；
 *   3. 平台级供给缺口解除（D2 契约漂移修复，或 register_from_manifest 逐 entry 隔离，
 *      使 D3 不被 D2 连带阻塞）。
 *
 * ═══ 🔴 三陷阱（沿用上游结论，D3 侧须实测确认，不照抄 D4）═══
 *
 *   陷阱一：**不能用 `page.on('response')` 判 callback**。OO 容器**直接**把 callback POST
 *     给后端，浏览器网络里看不到；须轮询 operations 端点等后端权威 `state='applied'`
 *     （读 `application_bound_at`）。
 *   陷阱二：**不能用 `asc_*` API 写格**（未经协同通道 ⇒ `cs_error=4` no_changes）。只有真实
 *     键盘输入：名称框 `#ce-cell-name` → `keyboard.type` → Enter。
 *   陷阱三：**模式切换条选择器须实测确认，不照抄 D4**。D3 宿主实测：
 *     · 工具栏容器类名 = `.d3-mode-toolbar`（**不是** D4 的 MODE_BAR）；
 *     · 模式项文案 = 「在线编辑」/「结构化视图」（**不是** D4-1 的「表格视图」）；
 *     · 只有 **D3-2** 挂了 `WorkpaperSyncEditorHost`（`isD3OoWiredRowsSheet` 当前仅含 D3-2）——
 *       其余受管行表 D3-4/5/6/7 未接 OO 直写宿主，D3-1 审定表走第二套桥且暂禁用。
 *     真跑前须在真实页面用 snapshot 复核这三条，任一不符即修选择器、不硬套。
 *
 * `--workers=1` 强制（OnlyOffice 8080 单实例，并发 contention 会假失败）。
 */
import { test, expect, type Page } from '@playwright/test'

// 真跑前须填真实 project/wp（D3 预收账款底稿），当前留占位——本文件不执行。
const PROJECT_ID = '<D3_PROJECT_ID>'
const WP_ID = '<D3_WP_ID>'

// 🔴 实测 D3 宿主选择器（不照抄 D4）。
const D3_MODE_BAR = '.d3-mode-toolbar'
const OO_MODE_LABEL = '在线编辑'
const HTML_MODE_LABEL = '结构化视图'

test.describe.configure({ mode: 'serial' })

test.skip(
  true,
  'BLOCKED（裁决 F5）：D3 adapter_registered=False —— manifest capability=single_onlyoffice + ' +
    'D2 契约漂移连带阻塞 register_from_manifest。代码已改但未实测。adapter 注册后去掉 skip 再跑。',
)

test('D3-2 明细：切在线编辑 → 逐值断言 → 改一格 → forcesave → 回读等值', async ({ page }: { page: Page }) => {
  // ── 1. 打开 D3-2 明细底稿 ────────────────────────────────────────────────
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`, { waitUntil: 'domcontentloaded' })
  // 导航到 D3-2 sheet（宿主由 sheetName 控制），等结构化视图与模式条出现。
  await expect(page.locator(D3_MODE_BAR)).toBeVisible({ timeout: 30_000 })

  // ── 2. 切「在线编辑」（陷阱三：实测选择器） ────────────────────────────────
  const ooItem = page.locator(`${D3_MODE_BAR} .el-segmented__item`).filter({ hasText: OO_MODE_LABEL })
  await expect(ooItem).toBeVisible({ timeout: 15_000 })
  await ooItem.click()

  // ── 3. 逐值断言：六张 OO canvas 的受管值与结构化视图一致 ──────────────────────
  //    （骨架：真跑时对 D3-2 明细的每个受管单元格逐值比对 OO canvas ↔ store 投影）
  //    OO iframe 就绪后读 `#ce-cell-name` 定位每格、读值域断言。

  // ── 4. 改一格（陷阱二：真实键盘，不用 asc_*） ────────────────────────────────
  //    const f = ooFrame(page)!; const box = f.locator('#ce-cell-name').first()
  //    await box.click(); await box.fill('<CELL_REF>'); await box.press('Enter')
  //    await f.locator('#ce-cellname-input-or-canvas').type('<NEW_VALUE>'); Enter

  // ── 5. forcesave（切回结构化视图触发 room forcesave） ───────────────────────
  const htmlItem = page.locator(`${D3_MODE_BAR} .el-segmented__item`).filter({ hasText: HTML_MODE_LABEL })
  await htmlItem.click()

  // ── 6. 等后端权威 applied（陷阱一：不用 page.on('response')，轮询 operations 端点） ──
  //    轮询 GET .../sync/entries/{entryId}/operations/{opId} 等 state==='applied'
  //    （读 application_bound_at 非空），而不是监听浏览器网络。

  // ── 7. 回读结构化视图等值：第 4 步改的值应出现在回写后的结构化视图里 ──────────────
  //    await expect(page.locator('<D3-2 明细该格>')).toHaveText('<NEW_VALUE>')
  expect(true).toBe(true) // 占位：本文件被 test.skip 阻断，不执行到真实断言。
})
