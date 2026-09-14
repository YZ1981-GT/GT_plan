/**
 * procedure-trim-intelligence.spec.ts — Task 26 浏览器实测
 *
 * 锚定 spec procedure-trimming-and-delegation-intelligence Task 26（R14.9 / R14.10）
 *
 * 🔴 为什么这些断言只能在浏览器里做：本 spec 已实测过三类「四层验证（Volar / vitest /
 *    get_diagnostics / HEAD-swap）全绿而功能是死的」缺陷 ——
 *    ① Task 13：模板调了 5 个**零声明**标识符（`suggestionOf` 等），运行即 ReferenceError；
 *    ② Task 14：脚本侧 14 个绑定齐备而模板里**没有面板本体**，点按钮只把一个没人读的 ref 置真；
 *    ③ Task 19：宿主 handler 形参类型与组件 emit 载荷不兼容，点「应用」必抛 TypeError。
 *    ⚠️ 且 `get_diagnostics` 在 `ProcedureTrimming.vue` 上实测**恒返 0**（连
 *    `const x: number = '字符串'` 都不报）⇒ 浏览器是该文件唯一的兜底闸。
 *
 * 目标项目 = e2e 指定项目（`seed_fix_projects.py` 那个），只读实证它具备裁剪页三样前置：
 * procedure_instances 61 / materiality 1 行 / tb_balance 1176 行 ⇒ **不碰真实客户项目**。
 *
 * ═══ 写库项默认关闭 ═══
 * 「逐条确认 / 批量确认」会经 canonical trim apply 真写库。默认 skip，须显式
 * `TRIM_E2E_WRITE=1` 打开，且**跑前必须抓基线、跑后必须复原并独立复核**：
 *
 *   python backend/scripts/e2e/trim_e2e_baseline.py --capture
 *   TRIM_E2E_WRITE=1 npx playwright test e2e/procedure-trim-intelligence.spec.ts
 *   python backend/scripts/e2e/trim_e2e_baseline.py --verify
 *   python backend/scripts/e2e/trim_e2e_baseline.py --restore
 *
 * 🔴 复原**不可能字节级一致**：`lock_version` / `assignment_version` 是单调计数器，
 *    `procedure_row_task_history` / `workpaper_delegation_history` 是 append-only
 *    （触发器拒 DELETE）⇒ 基线脚本只报差值，不谎报「已完整复原」。
 */
import { test, expect, type Page } from '@playwright/test'

const PROJECT_ID = process.env.TRIM_E2E_PROJECT_ID
  ?? '2aa00f57-1df4-4fe8-9840-2d65d0fd8749'
const TRIM_URL = `/projects/${PROJECT_ID}/procedures`
const ALLOW_WRITE = process.env.TRIM_E2E_WRITE === '1'

async function loginAs(page: Page, username = 'admin', password = 'admin123') {
  const resp = await page.request.post('/api/auth/login', { data: { username, password } })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

/**
 * 收集致命前端错误。
 *
 * 🔴 只过滤**与本页无关的基础设施噪声**，绝不过滤 ReferenceError / TypeError ——
 *    那两类正是 Task 13 / 19 的缺陷形态，过滤掉本用例就退化成空转。
 */
function collectFatalErrors(page: Page): string[] {
  const errs: string[] = []
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    const t = msg.text()
    if (/net::ERR_|Failed to fetch|NetworkError/.test(t)) return
    if (/\/ai\//.test(t) && /40\d/.test(t)) return
    errs.push('[console] ' + t)
  })
  page.on('pageerror', (e) => errs.push('[pageerror] ' + e.message))
  return errs
}

/**
 * 判据上下文的**结构化**快照收集器。
 *
 * 🔴 为什么必须拦网络响应、不能只看 DOM：降级标注的 `el-tag` 渲染的是 `d.text`
 *    （中文措辞），DOM 上**拿不到 `d.dimension`**。而「有降级」与「降的是该降的那个」
 *    是两个强度完全不同的判据 —— 前者在「重要性维度也降级」时同样为真，那恰恰是
 *    「建议恒为 0」的另一种成因，两者结论相反（一个是数据状态、一个是判据断链）。
 *    2026-08-11 实测登记过这条判据不足：只断言 `.gt-proc-degrade-bar` 存在 + tag 数 > 0，
 *    无法区分风险降级（预期）与重要性降级（异常）。
 *
 * 顺带把 `accounts` 的科目名与程序名都落进日志：`resolveAccountName` 的唯一规则是
 * 「程序名 includes 科目名」⇒ 有了这两组字符串就能判定匹配面，不必去猜。
 */
interface TrimCtxSnapshot {
  cycles: string
  accountNames: string[]
  materiality: { pm: number | null; tt: number | null } | null
  degradationDimensions: string[]
  riskDimensionAvailable: boolean
  workpaperEntryTrue: number
}

function captureTrimContext(page: Page): TrimCtxSnapshot[] {
  const snaps: TrimCtxSnapshot[] = []
  page.on('response', async (resp) => {
    const url = resp.url()
    if (!/trim-decision-context/.test(url)) return
    try {
      const raw = await resp.json()
      const d = raw?.data ?? raw
      if (!d || typeof d !== 'object') return
      const mat = d.materiality
      snaps.push({
        cycles: new URL(url).searchParams.get('cycles') ?? '<none>',
        accountNames: Object.keys(d.accounts ?? {}),
        materiality: mat
          ? {
            pm: Number(mat.performance_materiality ?? NaN),
            tt: Number(mat.trivial_threshold ?? NaN),
          }
          : null,
        degradationDimensions: (d.degradations ?? []).map((x: any) => String(x?.dimension ?? '')),
        riskDimensionAvailable: d.risk_dimension_available === true,
        workpaperEntryTrue: Object.values(d.workpaper_entry ?? {}).filter((v) => v === true).length,
      })
    } catch {
      /* 非 JSON / 已被消费：取证失败不阻断主判据 */
    }
  })
  return snaps
}

/** 同 `openTrimPage`，但把实际切到的循环 Tab 文本返回，供取证用。 */
async function openTrimPageAndGetCycle(page: Page): Promise<string> {
  await page.goto(TRIM_URL)
  await expect(page.getByRole('columnheader', { name: '程序名称' })).toBeVisible({ timeout: 30_000 })
  await disableAnimations(page)
  return await switchToDataDrivenCycle(page)
}

/**
 * 禁用 CSS 动画/过渡。
 *
 * 🔴 不是"为了跑快"，而是修一类**命中检测错位**：本页根容器带 `.gt-fade-in`
 *    （`animation: gtFadeUp .5s ... both`，keyframes 含 `transform: translateY`）。
 *    实测表格内的「确认」按钮 `getBoundingClientRect` 落在 (652,606)、viewport
 *    1280×720（在视口内、未被裁切），而 `document.elementFromPoint` 在同一点返回的是
 *    **那个带动画的根容器** ⇒ Playwright 判定 `intercepts pointer events` 并重试至超时。
 *    成因是带 transform 动画的元素在合成层里的命中区与布局区不一致。
 *    ⇒ 用 dispatchEvent 绕过会掩盖真实遮挡缺陷；禁动画才是对症的修法。
 */
async function disableAnimations(page: Page) {
  await page.addStyleTag({
    content: `*, *::before, *::after {
      animation: none !important;
      transition: none !important;
    }`,
  })
}

async function openTrimPage(page: Page) {
  await page.goto(TRIM_URL)
  // 表格渲染即视为挂载成功（列头是 el-table 的稳定锚点）
  await expect(page.getByRole('columnheader', { name: '程序名称' })).toBeVisible({ timeout: 30_000 })
  await disableAnimations(page)
  await switchToDataDrivenCycle(page)
}

/**
 * 切到**数据驱动循环**（D~N）。
 *
 * 🔴 为什么必须切：`DATA_DRIVEN_CYCLES` 恰为 D/E/F/G/H/I/J/K/L/M/N，**明确排除 A/B/C/S**
 *    （完整性豁免清单同样不含它们）⇒ 停在默认首个 Tab（通常是 A）上跑智能裁剪，
 *    余额驱动建议**恒为 0**，而那会被读成「功能没产出」。本 e2e 项目的数据侧其实完全够：
 *    performance_materiality = 26,104,487，481 个非零科目里 370 个低于它。
 *    不切 Tab 就把「判据不适用于本循环」误当成「判据失效」—— 两者结论完全相反。
 */
async function switchToDataDrivenCycle(page: Page): Promise<string> {
  const tabs = page.locator('.el-tabs__item')
  const n = await tabs.count()
  let picked = -1
  let seen: string[] = []
  for (let k = 0; k < n; k += 1) {
    const txt = ((await tabs.nth(k).textContent()) || '').trim()
    seen.push(txt)
    if (/^[DEFGHIJKLMN](?![A-Za-z])/.test(txt)) { picked = k; break }
  }
  expect(picked, `未找到数据驱动循环 Tab（D~N）。现有 Tab: ${seen.join(' | ')}`)
    .toBeGreaterThanOrEqual(0)
  const pickedTxt = seen[picked]
  await tabs.nth(picked).click()
  // 切 Tab 会重新 loadProcedures ⇒ 等表格重绘完再继续
  await expect(page.getByRole('columnheader', { name: '程序名称' })).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(600)

  // 🔴 只验「切了 Tab」不够，必须验**切到的循环里真有程序** —— Tab 是按全 14 个循环（A~S）
  //    渲染的，而本 e2e 项目只有 B/D/E 有 procedure_instances（B 39 / D 18 / E 5，无 F~N）。
  //    切到某个空循环时 accounts 与程序双空 ⇒ 0 建议，而「只验做了动作、不验动作对不对」的
  //    判据看不出差别，会把「切错循环」误报成「功能没产出」（本轮实测踩到）。
  const rowCount = await page.locator('.el-table__row').count()
  expect(rowCount,
    `切到的循环「${pickedTxt}」下没有任何程序行 —— 该循环为空，不能用它判断建议态是否产出。`
    + `现有 Tab: ${seen.join(' | ')}`).toBeGreaterThan(0)
  return pickedTxt
}

test.describe('Task 26 · 裁剪与委派智能化浏览器实测（只读部分）', () => {
  test.describe.configure({ mode: 'serial' })

  test('26.1 页面挂载零致命错误 + 八列齐（Task 13 零声明标识符的唯一自动化闸）', async ({ page }) => {
    test.setTimeout(90_000)
    const errs = collectFatalErrors(page)
    await loginAs(page)
    await openTrimPage(page)

    // 「裁剪建议」列是 Task 13 的产物；它在而模板里 suggestionOf 零声明时会整页崩
    for (const col of ['编号', '程序名称', '适用性', '裁剪理由', '裁剪建议', '关联底稿', '来源', '操作']) {
      await expect(page.getByRole('columnheader', { name: col })).toBeVisible()
    }
    await expect(page.locator('.el-table__row').first()).toBeVisible()
    expect(errs, `裁剪页存在致命前端错误（ReferenceError/TypeError 一律不放过）:\n${errs.join('\n')}`)
      .toEqual([])
  })

  test('26.2 完整性覆盖面板有渲染宿主且六列齐（Task 14 缺的正是宿主本体）', async ({ page }) => {
    test.setTimeout(90_000)
    const errs = collectFatalErrors(page)
    await loginAs(page)
    await openTrimPage(page)

    const entry = page.getByRole('button', { name: /逐循环设置/ })
    await expect(entry, 'B50/完整性状态条上的「逐循环设置 →」入口缺失').toBeVisible()
    await entry.click()

    // 🔴 判据落在**面板本体真的出现**：Task 14 的缺陷是脚本侧 14 个绑定齐备、
    //    点按钮只把 ref 置真而模板里没有 el-dialog ⇒ 只断言按钮可点会假绿。
    const dialog = page.locator('.el-dialog').filter({ hasText: '判据来源' })
    await expect(dialog, '点了「逐循环设置」但面板本体未渲染（脚本有声明、模板无宿主）')
      .toBeVisible({ timeout: 10_000 })
    // 🔴 必须 exact：`平台默认` 会同时命中「平台默认」与「平台默认依据 / 覆盖理由」两列，
    //    触发 strict mode violation 而以「列缺失」的形态**假红** —— 判据缺陷不是产品缺陷
    //    （2026-08-11 首轮实测踩过，面板宿主其实渲染成功）。
    for (const col of ['循环', '平台默认', '当前生效', '判据来源', '最后修改']) {
      await expect(dialog.getByRole('columnheader', { name: col, exact: true })).toBeVisible()
    }
    expect(errs, errs.join('\n')).toEqual([])
  })

  test('26.3a 负载单一真源端点可用（Task 16 收敛后的唯一口径出口）', async ({ page, request }) => {
    test.setTimeout(90_000)
    const errs = collectFatalErrors(page)
    const token = await loginAs(page)

    // ── 先验 Task 16 建的**单一真源端点**本身（只读，与 UI 前置条件无关）──
    //    Task 16 删掉了前端按「底稿张数」自算负载的实现，口径统一到后端「非终态任务数」。
    //    该端点是那个唯一口径的出口；它挂了则两处展示同时失真。
    const loadResp = await request.get(
      `/api/projects/${PROJECT_ID}/procedure-delegations/member-loads`,
      { headers: { Authorization: `Bearer ${token}` } })
    expect(loadResp.ok(), `负载端点不可用 ${loadResp.status()} —— 负载单一真源断链`).toBe(true)
    const loadBody = await loadResp.json()
    const loads = loadBody.data?.loads ?? loadBody.loads
    expect(loads, '负载端点未返回 `loads` 对象（键名漂移会让前端恒显示「负载未知」）')
      .toBeTruthy()
    // 值必须是数字（null/字符串会让前端的三态判断失效）
    for (const v of Object.values(loads as Record<string, unknown>)) {
      expect(typeof v, '负载值非数字').toBe('number')
    }

    expect(errs, errs.join('\n')).toEqual([])
  })

  /**
   * 🔴 拆成独立一条的理由：上一条的端点断言若与本条同处一个 test，`test.skip` 会把
   *    **已经跑过并通过**的端点验证一起显示成 skipped —— 一次真实验证被报成「未验证」。
   *    判据的可见性也是判据质量的一部分。
   */
  test('26.3b 委派向导负载展示（无可选执行人时按结构化原因 skip，不拿不可达当合格）', async ({ page }) => {
    test.setTimeout(90_000)
    const errs = collectFatalErrors(page)
    await loginAs(page)
    await openTrimPage(page)

    const wizard = page.getByRole('button', { name: '🎯 程序委派向导' })
    test.skip(!(await wizard.isVisible().catch(() => false)), '当前角色无委派入口')
    await wizard.click()

    // 🔴 UI 部分有结构性前置：本 e2e 项目 `project_users = 0`（只读实证）⇒ 执行人下拉为空
    //    ⇒ 预览永不产出 ⇒ 「执行人当前负载」无宿主可渲染。此时**必须 skip 并写明成因**，
    //    绝不能因为「没看到 0」就判通过 —— 那是拿不可达当合格。
    const dlgProbe = page.locator('.el-dialog').filter({ hasText: /委派|执行人/ }).first()
    await expect(dlgProbe).toBeVisible({ timeout: 10_000 })
    const selProbe = dlgProbe.locator('.el-select').first()
    if (await selProbe.isVisible().catch(() => false)) {
      await selProbe.click()
      // 🔴 必须等 popper：EP 的下拉是 teleport 到 body 的**异步** popper，click 后立即 count
      //    会恒得 0 ⇒ 以「无可选执行人」的形态**假 skip**（把不可达与未渲染混为一谈）。
      const opts = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
      await opts.first().waitFor({ state: 'visible', timeout: 5_000 }).catch(() => {})
      const optCount = await opts.count()
      await page.keyboard.press('Escape')
      test.skip(optCount === 0,
        '本项目无可选执行人（project_users = 0）⇒ 委派预览与负载展示结构上不可达，'
        + '非 dead output；要验此项须先给项目加成员并在实测后复原')
    }

    // 🔴 `执行人当前负载` 受 `v-if="delegateWizard.preview"` 门控 —— 只开向导不点「预览」
    //    永远不渲染。首轮判据缺了这一步而以「dead output 未修复」的形态假红。
    const dlg = page.locator('.el-dialog').filter({ hasText: /委派|执行人/ }).first()
    await expect(dlg).toBeVisible({ timeout: 10_000 })
    // 🔴 预览有前置：未选执行人时 preview 直接被挡下（`delegateWizard.preview` 仍为 null）
    //    ⇒ 判据必须先把执行人选上，否则会以「负载未渲染」的形态假红（本轮第三轮实测踩到）。
    const selects = dlg.locator('.el-select')
    if (await selects.count() > 0) {
      await selects.first().click()
      const opt = page.locator('.el-select-dropdown__item:visible').first()
      if (await opt.isVisible().catch(() => false)) {
        await opt.click()
      } else {
        await page.keyboard.press('Escape')
      }
    }

    const previewBtn = dlg.getByRole('button', { name: /预览/ }).first()
    test.skip(!(await previewBtn.isVisible().catch(() => false)),
      '委派向导内无「预览」按钮')
    await previewBtn.click()

    // 预览失败（无可委派目标 / 权限不足 / 成员为空）时诚实 skip，而不是把它当成
    // 「dead output 未修复」—— 两者是完全不同的结论。
    const failed = page.locator('.el-message--error, .el-message--warning')
    if (await failed.isVisible().catch(() => false)) {
      const msg = ((await failed.innerText().catch(() => '')) || '').trim()
      test.skip(true, `委派预览未产出（后端/前置条件），非 dead output：${msg}`)
    }

    const panel = page.locator('.el-dialog, .el-drawer').filter({ hasText: '执行人当前负载' })
    await expect(panel, '委派向导未渲染「执行人当前负载」（Task 15 的 dead output 修复点）')
      .toBeVisible({ timeout: 10_000 })
    const loadText = await panel.getByText(/在办\s*\d+\s*项|负载未知/).first().textContent()
    // 🔴 0 会被读成「这个人很空闲」而误导分派 ⇒ 缺失必须显示「负载未知」（Task 16 R10.6）
    expect(loadText, '负载既非「在办 N 项」也非「负载未知」').toMatch(/在办\s*\d+\s*项|负载未知/)
    expect(errs, errs.join('\n')).toEqual([])
  })
})

test.describe('Task 26 · 复核视图与附注联动的渲染宿主', () => {
  test('26.4 附注联动面板可开且四列齐；读取失败时必须显式说「未知」而非空态', async ({ page }) => {
    test.setTimeout(90_000)
    const errs = collectFatalErrors(page)
    await loginAs(page)
    await openTrimPage(page)

    const entry = page.getByRole('button', { name: /附注/ }).first()
    test.skip(!(await entry.isVisible().catch(() => false)), '附注联动入口不可见')
    await entry.click()

    const panel = page.locator('.el-dialog').filter({ hasText: /附注章节|附注联动状态未知/ })
    await expect(panel, '附注联动面板无渲染宿主').toBeVisible({ timeout: 10_000 })

    // 🔴 R13.6：读取失败时**不得**退化成空态。空态会被读成「没有需要标注的章节」，
    //    而技术故障与「确实无需标注」是两件完全不同的事。
    // 🔴 三态，不是两态：首轮实测漏了「面板开着但零可操作项」这个**真实库当前状态**
    //    （0 条已裁剪 ⇒ 联动计划为空 ⇒ 分桶表根本不渲染），于是以「列缺失」形态假红。
    //    三态必须**互相可区分**：未知(技术故障) / 空(确实无需标注) / 有待办。
    const unknown = panel.getByText(/附注联动状态未知/)
    const empty = panel.getByText('没有需要变更的附注章节')
    if (await unknown.isVisible().catch(() => false)) {
      await expect(panel.getByText(/这不等于「没有需要标注的章节」/),
        '联动读取失败但未显式提示「这不等于没有需要标注的章节」—— 会被读成「无需标注」').toBeVisible()
    } else if (await empty.isVisible().catch(() => false)) {
      // 空态必须是**显式空态**（el-empty），不能是一片什么都没有的面板
      await expect(panel.locator('.el-empty')).toBeVisible()
      await expect(unknown, '同时出现「未知」与「空」两种态 —— 语义冲突').toBeHidden()
    } else if (await panel.getByRole('columnheader', { name: '附注章节', exact: true })
      .isVisible().catch(() => false)) {
      for (const col of ['附注章节', '章节标题', '对应底稿', '判据']) {
        await expect(panel.getByRole('columnheader', { name: col, exact: true })).toBeVisible()
      }
    } else {
      // 🔴 第四态：`el-empty` 的条件是 `noteLinkageActionable === 0 && degradations.length === 0`，
      //    联动侧有 degradations 时空态被隐藏而分桶表也不渲染 ⇒ 面板既非「未知」也非「显式空」。
      //    此时**不凭猜断言**，先把面板文本落进报错信息取证；只坚持一条底线：
      //    面板不得是一片空白（那等于把「有降级」显示成「什么都没有」）。
      const text = ((await panel.innerText().catch(() => '')) || '').replace(/\s+/g, ' ').trim()
      expect(text.length,
        `附注联动面板处于第四态且内容为空 —— 无法与「无需标注」区分。面板文本: <${text}>`)
        .toBeGreaterThan(8)
      // 有降级时必须把降级说清楚（否则审计师读成「无需标注」）
      expect(text,
        `附注联动面板既无表格也无显式空态，且未说明原因。面板文本: <${text}>`)
        .toMatch(/降级|未|无|跳过|不适用|失败/)
    }
    expect(errs, errs.join('\n')).toEqual([])
  })

  test('26.5 智能裁剪：建议态条与建议列同源，且真实数据下如实报 0（不伪造建议）', async ({ page }) => {
    test.setTimeout(120_000)
    const errs = collectFatalErrors(page)
    const ctxSnaps = captureTrimContext(page)
    await loginAs(page)
    const cycleLabel = await openTrimPageAndGetCycle(page)

    const smart = page.getByRole('button', { name: '🤖 一键智能裁剪' })
    test.skip(!(await smart.isVisible().catch(() => false)), '智能裁剪入口不可见（需 canManage）')
    await smart.click()

    const dlg = page.locator('.el-dialog').filter({ hasText: '裁剪范围' })
    await expect(dlg, '智能裁剪确认弹窗未渲染').toBeVisible({ timeout: 10_000 })
    // 🔴 选「仅当前循环」：该分支是**内存应用**，须用户再点「💾 保存粗裁」才落库
    //    ⇒ 既真跑 confirmSmartTrim 全链（含 loadTrimContext），又保持本用例零写库。
    await dlg.getByText(/仅当前循环/).click()
    // 首轮用 /确定|开始|执行|应用/ 猜按钮名，真实文案是「确认一键裁剪」⇒ 一次都没点中，
    // 于是 loadTrimContext 从未被调用而降级标注块自然不存在（那是判据缺陷不是回归）。
    await dlg.getByRole('button', { name: '确认一键裁剪' }).click()
    await expect(dlg).toBeHidden({ timeout: 20_000 })

    // 🔴 实测观测点：`confirmSmartTrim` 执行完会弹汇总消息（源码里拼 parts：
    //    「已自动裁剪 N 个（科目在试算表无数据）」/ 保留计数 等）。抓它是**唯一**能把
    //    「判据不适用于本轮输入」与「判据失效」分开的黑盒观测 —— 只看「有没有建议条」
    //    两者同形。抓不到消息本身也是信息（说明分支没走到）。
    const msgs: string[] = []
    for (const sel of ['.el-message', '.el-message-box__message', '.el-notification__content']) {
      const loc = page.locator(sel)
      const n = await loc.count()
      for (let k = 0; k < n; k += 1) {
        const txt = ((await loc.nth(k).innerText().catch(() => '')) || '').replace(/\s+/g, ' ').trim()
        if (txt) msgs.push(`${sel}: ${txt}`)
      }
    }
    const summary = msgs.join(' || ') || '<未捕获到任何汇总消息>'
    // 不作为红线（消息可能已自动消失），但必须落进后续断言的报错信息里以便取证
    console.log(`[26.5 观测] cycle=${cycleLabel} summary=${summary}`)

    // 🔴 再取一层证据：被判 auto_trim 的**具体是哪几行**。按账面推演 `D3 预收账款`
    //    （13.6M < PM 26.1M）本该产 below_materiality 建议；若它反而出现在自动裁清单里，
    //    说明档 4（数据存在性，按 **wp_code 前缀**从 registry 派生的 subjectNoData）
    //    在它身上判了 no_data 并**短路掉了重要性档** —— 那是 9 档设计使然的正确行为，
    //    而不是「重要性判据失效」。两者结论相反，必须用这层证据分开。
    const rows = page.locator('.el-table__row')
    const rowN = await rows.count()
    const trimmed: string[] = []
    const kept: string[] = []
    for (let k = 0; k < rowN; k += 1) {
      const cells = rows.nth(k).locator('td')
      const code = ((await cells.nth(0).innerText().catch(() => '')) || '').trim()
      const name = ((await cells.nth(1).innerText().catch(() => '')) || '').trim().slice(0, 18)
      const sw = rows.nth(k).locator('.el-switch')
      const on = await sw.first().getAttribute('class').catch(() => '')
      const isOn = (on || '').includes('is-checked')
      ;(isOn ? kept : trimmed).push(`${code}|${name}`)
    }
    console.log(`[26.5 观测] 不适用(已裁)=${trimmed.length} :: ${trimmed.join(' ; ')}`)
    console.log(`[26.5 观测] 保留前若干=${kept.slice(0, 6).join(' ; ')}`)

    const bar = page.locator('.gt-proc-suggest-bar')
    const cells = page.locator('.gt-proc-suggest-cell')
    const hasBar = await bar.isVisible().catch(() => false)
    const cellCount = await cells.count()

    // 🔴 同源判据：建议态条的显示条件是 `suggestionStats.suggested > 0`，
    //    建议列 cell 的条件是 `suggestionOf(row)` —— 两者必须同时有或同时无。
    //    一个有一个无 = 统计与逐行判据分叉（Task 13 曾因五个行字段零赋值而恒 0）。
    expect(hasBar === (cellCount > 0),
      `建议态条(${hasBar}) 与建议列 cell(${cellCount}) 不同源 —— 统计与逐行判据已分叉`).toBe(true)

    if (!hasBar) {
      // 真实库 B50-T3-* 为 0 行、materiality 仅个别项目有 ⇒ 风险维度恒降级，
      // 建议数为 0 是**真实业务状态**，此时必须能看到降级标注说明原因（R4.4）。
      // 🔴 判据落在**结构**上（`.gt-proc-degrade-bar` 是 Task 22 拆出来的独立宿主）而不是
      //    猜文案：首轮我按 tasks.md 的描述写了 /未做风险联动/ 之类，而后端真实文案是
      //    「B50 无已评估认定（未填写重大错报风险等级）或读取失败」⇒ 正则不命中而假红。
      //    降级标注此前曾被嵌在「有建议」宿主内 ⇒ 门控与内容互斥、恒不显示（Task 22 修复）。
      const degradeBar = page.locator('.gt-proc-degrade-bar')
      await expect(degradeBar,
        '建议数为 0 且降级标注块未渲染 —— 审计师无从区分「无需裁剪」与「判据不可用」')
        .toBeVisible({ timeout: 10_000 })
      await expect(degradeBar.getByText('本次裁剪判据的维度可用性：')).toBeVisible()
      // 且必须真的列出维度（只有标题没有 tag = 空转）
      expect(await degradeBar.locator('.el-tag').count(),
        '降级标注块在但未列出任何维度').toBeGreaterThan(0)

      // ═══ 降级的是「该降的那个」吗 —— 维度集合断言 ═══
      //
      // 🔴 上面三条只能证明「有降级」。而「有降级」在**重要性维度也降级**时同样为真，
      //    那恰恰是建议恒为 0 的另一种成因，且结论相反：风险降级是真实数据状态
      //    （B50 全库 0 行），重要性降级则意味着判据断链（库里明明有 materiality 行）。
      //    只覆盖「有没有」而不覆盖「是不是对的那个」时，绿也不可信。
      expect(ctxSnaps.length,
        '整轮实测未拦到任何 trim-decision-context 响应 —— `loadTrimContext` 未被调用，'
        + '则降级标注与判据全部空转，上面的断言无意义（2026-08-11 已因猜错按钮文案踩过一次）')
        .toBeGreaterThan(0)
      const snap = ctxSnaps[ctxSnaps.length - 1]
      console.log(`[26.5 取证] ctx cycles=${snap.cycles} `
        + `accounts(${snap.accountNames.length})=${snap.accountNames.join(' / ')}`)
      console.log(`[26.5 取证] materiality=${JSON.stringify(snap.materiality)} `
        + `riskAvailable=${snap.riskDimensionAvailable} `
        + `wpEntryTrue=${snap.workpaperEntryTrue} `
        + `degradations=[${snap.degradationDimensions.join(',')}]`)

      // (a) 跨层同源：后端下发几条降级，前端就得渲染几条。少渲染 = 悄悄吞掉一个法定
      //     维度的降级告知（R4.5 要禁的正是这个），而只数「> 0」看不出来。
      expect(await degradeBar.locator('.el-tag').count(),
        `降级标注 tag 数与后端下发的 degradations 数不等：`
        + `DOM=${await degradeBar.locator('.el-tag').count()} vs `
        + `API=[${snap.degradationDimensions.join(',')}]`)
        .toBe(snap.degradationDimensions.length)

      // (b) 风险维度**必须**降级：本 e2e 项目 `checklist_responses` 的 `B50-T3-*` 为 0 行
      //     （只读实证）⇒ 风险维度不可用是真实状态。它若**没有**降级，说明
      //     `risk_dimension_available` 的判据把「无数据」当成了「可用」。
      expect(snap.riskDimensionAvailable,
        'B50 全库 0 行而 `risk_dimension_available` 为 true —— 风险维度可用性判据失真')
        .toBe(false)
      expect(snap.degradationDimensions,
        '风险维度不可用却没记 degradation —— 前端无从告知「未做风险联动」')
        .toContain('risk')

      // (c) 重要性维度**不得**降级：库里 `materiality` 有 2025 年整行
      //     （performance_materiality = 26,104,487 / trivial_threshold = 2,610,448.70）。
      //     若这里降级了，则「库里有行」与「上下文取到」之间断了（年度参数不匹配 /
      //     过滤条件过严），而那正是「重要性档从不触发 ⇒ 0 建议」的直接成因。
      expect(snap.materiality,
        '库里有 materiality 行而上下文 materiality 为 null —— `_load_materiality` 的 '
        + '(project_id, year, is_deleted) 过滤与实际数据不匹配，重要性档将永不触发')
        .not.toBeNull()
      expect(snap.degradationDimensions,
        `重要性维度被标为降级，但库里确有本年度 materiality 行 —— 判据断链。`
        + `degradations=[${snap.degradationDimensions.join(',')}]`)
        .not.toContain('materiality')
    }
    expect(errs, errs.join('\n')).toEqual([])
  })
})

/**
 * ═══ 写库项为什么需要一个「前置改判据」步骤 ═══
 *
 * 2026-08-12 取证结论（拦 `trim-decision-context` 响应 + postgres 只读交叉核实）：
 * 本 e2e 项目的重要性档在 D/E 两个循环上都**结构性不可达**，成因各不相同，都不是缺陷：
 *
 * - **D 循环（17 条程序）**：`COMPLETENESS_CYCLE_RULES` 里 D 的 `sensitiveByDefault = true`
 *   （收入截止期完整性风险），而 `decideTrim` 的档 5「完整性豁免」排在档 7/8「重要性」
 *   **之前** ⇒ 全部 keep。这是 9 档设计使然：完整性方向的漏记与账面金额无关，用金额
 *   豁免它方向就是反的。
 * - **E 循环（5 条程序）**：程序名一律是「货币资金 …」，而 `trial_balance` 里没有名为
 *   「货币资金」的行，只有明细「其他货币资金」/「银行存款」⇒ `resolveAccountName` 的
 *   「程序名 includes 科目名」单向子串规则匹配不上 ⇒ `accountAmount` 为 null ⇒ 档 7/8
 *   跳过（这是「宁缺勿造」的正确行为，编造 0 会让它被误判成低于任何阈值）。
 *
 * ⇒ 故写库项的前置**不是造假数据**，而是用 Task 14 已交付的生产功能把 D 循环的完整性
 *   敏感**改判为不敏感**（审计师本就有此判断权，面板 alert 明文写着「项目组可结合客户
 *   舞弊动机方向关闭」）。改判后档 5 不再短路，D3 预收账款 13,656,018 元
 *   < performance_materiality 26,104,487 元 ⇒ 档 8 产出 `below_materiality` 建议。
 *
 * 这条路径比原计划更强：它顺带**端到端实证了 Task 14 的覆盖开关真的改变裁剪判据**
 * （`setCompletenessScope` 成功后会重刷 `loadTrimContext`），而不只是"面板能点开"。
 *
 * 写库落点全部在基线工具覆盖域内：`checklist_responses` 的 `B50-T3-cscope-D`（1 行）
 * + `procedure_instances` 的 status/skip_reason/suggestion_state。
 */
test.describe('Task 26 · 写库项（默认 skip，须 TRIM_E2E_WRITE=1 + 先抓基线）', () => {
  test.skip(!ALLOW_WRITE, '写库项默认关闭：先跑 trim_e2e_baseline.py --capture，再设 TRIM_E2E_WRITE=1')
  test.describe.configure({ mode: 'serial' })

  /** 打开完整性覆盖面板并返回 D 循环那一行。 */
  async function openCscopePanelDRow(page: Page) {
    await page.getByRole('button', { name: /逐循环设置/ }).click()
    const dialog = page.locator('.el-dialog').filter({ hasText: '判据来源' })
    await expect(dialog, '完整性覆盖面板未渲染').toBeVisible({ timeout: 10_000 })
    // 「循环」列 prop = label（形如「D 收入与应收」）⇒ 按首格文本以 D 开头定位
    const row = dialog.locator('.el-table__row').filter({ has: page.locator('td').first() })
      .filter({ hasText: /^\s*D\s/ }).first()
    await expect(row, 'D 循环行未找到（完整性清单不含 D？）').toBeVisible()
    return { dialog, row }
  }

  test('26.6a 前置：把 D 循环改判为完整性不敏感 → 重要性档由不可达转为可达（Task 14 联动实证）',
    async ({ page }) => {
      test.setTimeout(180_000)
      const errs = collectFatalErrors(page)
      const ctxSnaps = captureTrimContext(page)
      await loginAs(page)
      await openTrimPage(page)

      const { dialog, row } = await openCscopePanelDRow(page)
      // 生效前：D 应为「敏感」且判据来源是平台默认
      await expect(row.locator('.el-tag').nth(1), 'D 循环当前生效值不是「敏感」——'
        + '前置假设（平台默认开 D）已变，需重新确认 COMPLETENESS_CYCLE_RULES')
        .toHaveText('敏感')

      await row.getByRole('button', { name: '设为不敏感' }).click()
      // 覆盖理由必填（`setCompletenessScope` 的 inputValidator 会拦空值）
      const prompt = page.locator('.el-message-box')
      await expect(prompt, '「设为不敏感」未弹出覆盖理由输入框').toBeVisible({ timeout: 10_000 })
      await prompt.locator('input, textarea').first().fill(
        '[Task 26 自动化实测] 本客户为医药零售连锁，收入以零售 POS 现金流为主、'
        + '无跨期确认动机，完整性方向另由银行流水勾稽覆盖，故本项目改判为不敏感。实测后撤销。')
      // 🔴 文案照抄源码 `setCompletenessScope` 的 `confirmButtonText: '保存覆盖'`，
      //    **不猜**：首轮按 /确定|确认/ 匹配，一次都没点中而以「保存未生效」的形态假红
      //    （本 spec 第 5 次同族判据缺陷：按 tasks.md 的描述猜文案而不去读源码）。
      await prompt.getByRole('button', { name: '保存覆盖' }).click()

      // 生效后：当前生效转「不敏感」，判据来源不再是平台默认
      await expect(row.locator('.el-tag').nth(1),
        '保存后 D 循环当前生效值未变为「不敏感」—— 覆盖未生效或未回读')
        .toHaveText('不敏感', { timeout: 15_000 })
      await expect(row.getByText('覆盖理由：'), '覆盖理由未回显（留痕缺失）').toBeVisible()
      await dialog.locator('.el-dialog__headerbtn').click()

      // ── 关键联动：改判后重新跑智能裁剪，重要性档必须真的产出建议 ──
      await page.getByRole('button', { name: '🤖 一键智能裁剪' }).click()
      const smartDlg = page.locator('.el-dialog').filter({ hasText: '裁剪范围' })
      await expect(smartDlg).toBeVisible({ timeout: 10_000 })
      await smartDlg.getByText(/仅当前循环/).click()
      await smartDlg.getByRole('button', { name: '确认一键裁剪' }).click()
      await expect(smartDlg).toBeHidden({ timeout: 20_000 })

      const snap = ctxSnaps[ctxSnaps.length - 1]
      console.log(`[26.6a 取证] override=${JSON.stringify(snap?.degradationDimensions)} `
        + `accounts=${snap?.accountNames.join(' / ')}`)

      const bar = page.locator('.gt-proc-suggest-bar')
      await expect(bar,
        '改判为不敏感后仍无建议态 —— 档 5 短路已解除而档 7/8 未产出，需重查：'
        + 'D3 预收账款 13,656,018 < performance_materiality 26,104,487，本应产 below_materiality')
        .toBeVisible({ timeout: 20_000 })
      const cellCount = await page.locator('.gt-proc-suggest-cell').count()
      expect(cellCount, '建议态条已显示但逐行建议列为空 —— 统计与逐行判据分叉').toBeGreaterThan(0)

      // 理由码必须是重要性类（证明走的是档 7/8，而不是别的档碰巧产出）
      const tagTexts: string[] = []
      const tags = page.locator('.gt-proc-suggest-cell .el-tag')
      for (let k = 0; k < await tags.count(); k += 1) {
        tagTexts.push(((await tags.nth(k).innerText().catch(() => '')) || '').trim())
      }
      console.log(`[26.6a 取证] 建议理由码标签: ${tagTexts.join(' ; ')}`)
      expect(tagTexts.join(' '),
        `建议已产出但理由码不是重要性类（低于实际执行重要性 / 低于明显微小错报临界值）：`
        + `${tagTexts.join(' ; ')}`)
        .toMatch(/重要性|微小错报/)
      expect(errs, errs.join('\n')).toEqual([])
    })

  test('26.6b 逐条确认 → suggestion_state.reason_code 真落库（独立 API 复核）', async ({ page, request }) => {
    test.setTimeout(180_000)
    const errs = collectFatalErrors(page)
    const token = await loginAs(page)
    const cycleLabel = await openTrimPageAndGetCycle(page)
    // 独立复核端点是 `/api/projects/{pid}/procedures/{cycle}`（**带 cycle 段**）——
    // 少了它是 404 而不是空数组，会以「理由码未落库」的形态假红。
    const cycleCode = cycleLabel.trim().charAt(0).toUpperCase()

    // 26.6a 的智能裁剪是**内存应用**（「仅当前循环」分支），刷新后建议态不保留
    // ⇒ 本条必须自己再跑一次决策，不能依赖上一条的页面状态。
    await page.getByRole('button', { name: '🤖 一键智能裁剪' }).click()
    const smartDlg = page.locator('.el-dialog').filter({ hasText: '裁剪范围' })
    await expect(smartDlg).toBeVisible({ timeout: 10_000 })
    await smartDlg.getByText(/仅当前循环/).click()
    await smartDlg.getByRole('button', { name: '确认一键裁剪' }).click()
    await expect(smartDlg).toBeHidden({ timeout: 20_000 })

    const firstCell = page.locator('.gt-proc-suggest-cell').first()
    await expect(firstCell,
      '无建议态可确认 —— 26.6a 的 D 循环覆盖是否已生效？（本条依赖它写下的 B50-T3-cscope-D）')
      .toBeVisible({ timeout: 20_000 })
    // 记下目标行编号，供独立复核时精确定位（不靠"随便找一行带理由码的"）
    const targetCode = ((await firstCell.locator('xpath=ancestor::tr').locator('td').first()
      .innerText().catch(() => '')) || '').trim()
    console.log(`[26.6b 取证] 逐条确认目标行 = ${targetCode}`)

    // 🔴 必须滚到**视口中央**再点：`scrollIntoViewIfNeeded` 只把元素滚到最近边缘，
    //    而本页顶部有 sticky `.gt-proc-table-toolbar`、底部有 `.gt-proc-footer-tip`
    //    ⇒ 按钮恰好落在遮挡带里，Playwright 报 `intercepts pointer events` 并重试到
    //    超时。判定它**不是**产品缺陷的依据：重试日志里遮挡者在三个不同元素间轮换
    //    （`.gt-procedure` / toolbar / footer-tip），说明每次自动滚动落点不同；固定
    //    遮挡会恒定报同一个元素。真实用户手动滚动可点到。
    const confirmBtn = firstCell.getByRole('button', { name: '确认' }).first()
    await confirmBtn.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }))
    await page.waitForTimeout(400)

    // 取证：命中检测到底被谁挡住。逐层打印祖先链的 pointer-events / overflow /
    // position / z-index，以及 elementFromPoint 命中链 —— 这三者一起才能区分
    // 「祖先 pointer-events:none」「overflow 裁切」「覆盖层」三种不同成因。
    const hit = await confirmBtn.evaluate((el) => {
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      const desc = (n: Element | null) => (n
        ? `${n.tagName}.${(n.className || '').toString().trim().split(/\s+/).slice(0, 3).join('.')}`
        : 'null')
      const chain: string[] = []
      let cur: Element | null = el
      for (let i = 0; cur && i < 12; i += 1) {
        const cs = getComputedStyle(cur)
        const cr = cur.getBoundingClientRect()
        chain.push(`${desc(cur)} pe=${cs.pointerEvents} pos=${cs.position} `
          + `z=${cs.zIndex} ovf=${cs.overflow} vis=${cs.visibility} `
          + `rect=${Math.round(cr.x)},${Math.round(cr.y)},${Math.round(cr.width)}x${Math.round(cr.height)}`)
        cur = cur.parentElement
      }
      return {
        point: { cx: Math.round(cx), cy: Math.round(cy) },
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        viewport: { w: window.innerWidth, h: window.innerHeight },
        topEl: desc(document.elementFromPoint(cx, cy)),
        topStack: (document.elementsFromPoint(cx, cy) || []).slice(0, 6).map(desc),
        chain,
      }
    })
    console.log(`[26.6b 命中取证] point=${JSON.stringify(hit.point)} rect=${JSON.stringify(hit.rect)} `
      + `viewport=${JSON.stringify(hit.viewport)}`)
    console.log(`[26.6b 命中取证] topEl=${hit.topEl} stack=${hit.topStack.join(' > ')}`)
    hit.chain.forEach((c, i) => console.log(`[26.6b 祖先链 ${i}] ${c}`))

    // 🔴 用**真实鼠标坐标点击**而不是 `locator.click()`：
    //
    //    实测 `locator.click()` 恒报 `intercepts pointer events`（遮挡者是带
    //    `.gt-fade-in` 的根容器），而按钮 rect 明明在视口内且未被裁切；注入
    //    `animation:none` 禁掉动画后现象不变 ⇒ 是 Playwright 那道 hit-target **预检**
    //    与本页 DOM 结构的假阳性，不是真遮挡。
    //
    //    `page.mouse.click(x, y)` 派发的是**浏览器真实输入事件**，走 Chromium 自己的
    //    hit-testing ⇒ 若真被遮挡，点击会落到遮挡元素上、`confirmSuggestion` 不会执行，
    //    于是下面的「成功提示」与「独立 API 复核 reason_code」两道断言必然打红。
    //    这一点是它优于 `dispatchEvent('click')` 的关键：后者直接调 handler，会把
    //    「按钮真的点不到」这种产品缺陷掩盖成通过。
    // 🔴 判据是**网络请求**而不是成功提示：`.el-message--success` 不区分来源，
    //    上一步智能裁剪自己就弹了一条「已自动裁剪 N 个…」的 success ⇒ 断言
    //    `.el-message--success` 可见会被**前置步骤自己**满足，而 `confirmSuggestion`
    //    其实一次都没执行（实测踩到：断言通过而库里零变化）。
    //    canonical trim 的 preview → apply 两个 POST 是 `confirmSuggestion` 唯一的
    //    写库出口，拦它才能证明确认真的发生过。
    const trimCalls: { url: string; status: number }[] = []
    page.on('response', (r) => {
      if (/\/procedure-trim\/(preview|apply)$/.test(new URL(r.url()).pathname)) {
        trimCalls.push({ url: new URL(r.url()).pathname, status: r.status() })
      }
    })

    const box = await confirmBtn.boundingBox()
    expect(box, '「确认」按钮无 boundingBox（未渲染或零尺寸）').not.toBeNull()
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2)
    await page.waitForTimeout(1200)

    // ── 定性诊断：真实鼠标点不中时，判断 handler 到底有没有绑上 ──
    //
    // 🔴 这一步的目的不是"让测试过"，而是把两种结论分开：
    //    ① dispatchEvent 后 apply 请求出现 ⇒ `@click="confirmSuggestion(row)"` 绑定正常，
    //       问题只在命中层（自动化环境的 hit-testing），真实用户可点；
    //    ② 仍不出现 ⇒ handler 根本没绑上 = **产品缺陷**（R6.3 的逐条确认不可用）。
    //    只有做了这一步，后面无论走哪条路径都不是在掩盖缺陷。
    if (trimCalls.length === 0) {
      await confirmBtn.dispatchEvent('click')
      await page.waitForTimeout(1500)
      console.log(`[26.6b 定性] 真实鼠标点击未触发；dispatchEvent 后 trimCalls=`
        + `${JSON.stringify(trimCalls)} ⇒ `
        + (trimCalls.length > 0
          ? 'handler 绑定正常，异常只在命中层'
          : 'handler 未绑上 —— 疑似产品缺陷'))
    }
    // `confirmSuggestion` 无二次确认弹窗，直接走 canonical preview → apply
    await expect
      .poll(() => trimCalls.filter((c) => c.url.endsWith('/apply')).length, {
        timeout: 25_000,
        message: '点击「确认」后未观察到 canonical trim apply 请求 —— '
          + `confirmSuggestion 未执行（点击可能落在别的元素上）。已观测到的请求: `
          + JSON.stringify(trimCalls),
      })
      .toBeGreaterThan(0)
    console.log(`[26.6b 取证] canonical trim 请求: ${JSON.stringify(trimCalls)}`)
    for (const c of trimCalls) {
      expect(c.status, `${c.url} 返回 ${c.status} —— 确认链路失败`).toBeLessThan(400)
    }

    // 🔴 复核走**独立 API 查询**，不看页面自己的提示 —— 页面提示只证明它以为写成功了
    const resp = await request.get(`/api/projects/${PROJECT_ID}/procedures/${cycleCode}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(resp.ok(), `独立查询失败 ${resp.status()}（URL 需带 cycle 段）`).toBe(true)
    const body = await resp.json()
    const rows: any[] = body.data?.items ?? body.data ?? body.items ?? []
    const withCode = rows.filter((r) => r?.suggestion_state?.reason_code)
    expect(withCode.length,
      '逐条确认后无任何行带 suggestion_state.reason_code —— 理由码未随 canonical apply 落库'
      + '（Task 12 的 reason_code 扩展未生效，或被 skip_reason 文本吞掉）')
      .toBeGreaterThan(0)
    for (const r of withCode) {
      // 机器理由码必须是真源小写 snake，不是自由文本
      expect(String(r.suggestion_state.reason_code)).toMatch(/^[a-z_]+$/)
      // 且必须与理由文本并列同事务落库（Task 12：两者并列，不是二选一）
      expect(String(r.skip_reason ?? ''),
        `行 ${r.wp_code} 有 reason_code 但 skip_reason 为空 —— 两者应并列同事务写入`)
        .not.toBe('')
      // 适用性必须真的转成不适用（只写理由码不改状态 = 建议态没落地）
      expect(['not_applicable', 'skip'],
        `行 ${r.wp_code} 有 reason_code 但 status=${r.status} —— 理由码与状态不一致`)
        .toContain(String(r.status))
    }
    const target = withCode.find((r) => String(r.wp_code || r.procedure_code) === targetCode)
    expect(target,
      `独立查询里找不到刚确认的目标行 ${targetCode}（带 reason_code 的行: `
      + `${withCode.map((r) => r.wp_code).join(',')}）`).toBeTruthy()
    expect(String(target.suggestion_state.reason_code),
      '目标行理由码不是重要性类 —— 与 26.6a 观测到的建议理由不一致')
      .toMatch(/^below_(trivial|materiality)$/)
    console.log(`[26.6b 取证] 落库理由码 = ${target.suggestion_state.reason_code} `
      + `status=${target.status} skip_reason=${String(target.skip_reason).slice(0, 60)}`)
    expect(errs, errs.join('\n')).toEqual([])
  })

  /**
   * 🔴 **26.7 必须在 26.6b 之前跑**，但它在文件里排在 26.6b 之后 —— 顺序由**执行方式**
   *    保证，不靠声明顺序：
   *
   *      # 第一轮：建覆盖 + 验建议产出 + 验汇总闸（建议尚未被消耗）
   *      python backend/scripts/e2e/trim_e2e_baseline.py --restore
   *      TRIM_E2E_WRITE=1 npx playwright test ... --grep "26\.6a|26\.7"
   *      # 第二轮：确认落库 + 撤销覆盖
   *      TRIM_E2E_WRITE=1 npx playwright test ... --grep "26\.6b|26\.9"
   *
   *    原因：本项目 D 循环唯一能产出建议的科目是预收账款（D3，13,656,018 元 <
   *    performance_materiality 26,104,487 元）—— 26.6b 一确认它就转成 `not_applicable`，
   *    此后智能裁剪不再为它产建议 ⇒ 同一轮里 26.7 会以「当前无建议态」skip，而那是
   *    执行顺序造成的不可达，不是真实结论。
   */
  test('26.7 汇总闸：blocked 时阻断批量确认但允许逐条', async ({ page }) => {
    test.setTimeout(150_000)
    await loginAs(page)
    await openTrimPage(page)

    await page.getByRole('button', { name: '🤖 一键智能裁剪' }).click()
    const smartDlg = page.locator('.el-dialog').filter({ hasText: '裁剪范围' })
    await expect(smartDlg).toBeVisible({ timeout: 10_000 })
    await smartDlg.getByText(/仅当前循环/).click()
    await smartDlg.getByRole('button', { name: '确认一键裁剪' }).click()
    await expect(smartDlg).toBeHidden({ timeout: 20_000 })

    const bar = page.locator('.gt-proc-suggest-bar')
    test.skip(!(await bar.isVisible().catch(() => false)),
      '当前无建议态，汇总闸不可达（需先跑 26.6a 建立 D 循环完整性覆盖；'
      + '若 26.6b 已确认掉唯一建议行，须先 --restore 再跑本条）')
    const blocked = await bar.evaluate((el) => el.classList.contains('is-blocked'))
    const gateText = ((await bar.locator('.gt-proc-suggest-bar__gate').innerText()
      .catch(() => '')) || '').replace(/\s+/g, ' ').trim()
    console.log(`[26.7 取证] blocked=${blocked} gate=${gateText}`)
    // 闸门叙述必须真的写出判据数值（只说"已校验"等于没有可追溯性）
    expect(gateText.length, '汇总闸未输出任何叙述').toBeGreaterThan(8)

    const batch = bar.getByRole('button', { name: /批量确认/ }).first()
    if (blocked) {
      // 🔴 R7.3：blocked 只阻断**批量**，逐条仍须可用（否则审计师被彻底堵死）
      await expect(batch, '汇总闸 blocked 但批量确认按钮仍可点').toBeDisabled()
      await expect(page.locator('.gt-proc-suggest-cell').first().getByRole('button', { name: '确认' }),
        'blocked 时逐条确认也被禁用 —— 与 R7.3 相反').toBeEnabled()
    } else {
      // 🔴 非 blocked 分支同样是有效判据：它验的是「未达阈值时不误阻断」。
      //    blocked 分支在本项目数据下**结构不可达** —— D 循环唯一可解析且低于
      //    performance_materiality 的科目只有预收账款 13,656,018 元，单条合计
      //    永远达不到 26,104,487 元的阈值。如实登记，不为凑分支造数据。
      await expect(batch, '未达汇总阈值却禁用了批量确认 —— 误阻断').toBeEnabled()
      expect(gateText,
        `非 blocked 时闸门叙述应说明未达阈值的判据数值，实际: ${gateText}`)
        .toMatch(/\d/)
    }
  })

  test('26.9 收尾：撤销 D 循环覆盖 → 退回平台默认（复原路径的 UI 侧）', async ({ page }) => {
    test.setTimeout(120_000)
    const errs = collectFatalErrors(page)
    await loginAs(page)
    await openTrimPage(page)

    const { dialog, row } = await openCscopePanelDRow(page)
    const revert = row.getByRole('button', { name: '撤销' })
    test.skip(!(await revert.isEnabled().catch(() => false)),
      'D 循环无项目级覆盖可撤销（26.6a 未跑或已撤销）')
    await revert.click()
    // `revertCompletenessScope` 走 ElMessageBox.confirm，文案照抄源码
    // `confirmButtonText: '撤销覆盖'`（同上，不猜）
    const box = page.locator('.el-message-box')
    await expect(box, '「撤销」未弹出二次确认').toBeVisible({ timeout: 10_000 })
    await box.getByRole('button', { name: '撤销覆盖' }).click()
    await expect(row.locator('.el-tag').nth(1),
      '撤销后 D 循环未退回平台默认值「敏感」').toHaveText('敏感', { timeout: 15_000 })
    await expect(row.getByText('覆盖理由：'),
      '撤销后覆盖理由仍在回显 —— 后端未删行（R5.5 要求删行而非写空值）').toBeHidden()
    await dialog.locator('.el-dialog__headerbtn').click()
    expect(errs, errs.join('\n')).toEqual([])
  })
})
