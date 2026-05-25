# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workpaper-editor-loading.spec.ts >> WorkpaperEditor 加载流程回归测试 >> 5.2.1 — 打开底稿无 ReferenceError + 无死锁
- Location: e2e\workpaper-editor-loading.spec.ts:49:3

# Error details

```
TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('.gt-wp-editor-univer, .gt-wp-editor-loading') to be visible

```

# Page snapshot

```yaml
- generic [ref=e4]:
  - banner [ref=e5]:
    - generic "折叠/展开导航" [ref=e7] [cursor=pointer]:
      - img "Grant Thornton 致同" [ref=e8]
      - generic [ref=e9]: 审计平台
    - navigation "Breadcrumb" [ref=e11]:
      - generic [ref=e12]:
        - link "首页" [ref=e13]
        - text: /
      - link "项目" [ref=e15]
    - generic [ref=e16]:
      - img [ref=e19] [cursor=pointer]
      - img [ref=e24] [cursor=pointer]
      - generic "显示设置" [ref=e28] [cursor=pointer]:
        - generic [ref=e29]: Aa
      - img [ref=e33] [cursor=pointer]
      - img [ref=e37] [cursor=pointer]
      - img [ref=e41] [cursor=pointer]
      - link "复核收件箱" [ref=e44] [cursor=pointer]:
        - /url: /review-inbox
        - generic [ref=e46]:
          - img [ref=e48]
          - generic [ref=e52]: 复核收件箱
      - button "EQCR" [ref=e54] [cursor=pointer]:
        - img [ref=e56]
        - generic [ref=e58]: EQCR
        - img [ref=e60]
      - generic [ref=e63] [cursor=pointer]: 🌙
      - button "A admin" [ref=e65] [cursor=pointer]:
        - generic [ref=e66]: A
        - generic [ref=e67]: admin
        - img [ref=e69]
  - generic [ref=e71]:
    - navigation [ref=e72]:
      - navigation [ref=e73]:
        - generic "仪表盘" [ref=e74] [cursor=pointer]:
          - img [ref=e76]
        - generic "项目" [ref=e80] [cursor=pointer]:
          - img [ref=e82]
        - generic "人员档案" [ref=e84] [cursor=pointer]:
          - img [ref=e86]
        - generic "工时" [ref=e88] [cursor=pointer]:
          - img [ref=e90]
        - generic "看板" [ref=e94] [cursor=pointer]:
          - img [ref=e96]
        - generic "合并" [ref=e98] [cursor=pointer]:
          - img [ref=e100]
        - generic "函证" [ref=e103] [cursor=pointer]:
          - img [ref=e105]
        - generic "归档" [ref=e107] [cursor=pointer]:
          - img [ref=e109]
        - generic "附件" [ref=e113] [cursor=pointer]:
          - img [ref=e115]
        - generic "模板库" [ref=e117] [cursor=pointer]:
          - img [ref=e119]
        - generic "账号权限" [ref=e121] [cursor=pointer]:
          - img [ref=e123]
      - generic [ref=e125]:
        - generic [ref=e126]: 📚 知识
        - generic "知识库" [ref=e127] [cursor=pointer]:
          - img [ref=e129]
        - generic "私人库" [ref=e132] [cursor=pointer]:
          - img [ref=e134]
        - generic "排版模板" [ref=e137] [cursor=pointer]:
          - img [ref=e139]
        - generic [ref=e141]: 🤖 AI
        - generic "AI 模型" [ref=e142] [cursor=pointer]:
          - img [ref=e144]
        - generic "公式管理" [ref=e147] [cursor=pointer]:
          - generic [ref=e148]: ƒx
        - generic [ref=e149]: 🔎 查询
        - generic "高级查询" [ref=e150] [cursor=pointer]:
          - img [ref=e152]
        - generic [ref=e154]: 💬 反馈
        - generic "吐槽求助" [ref=e155] [cursor=pointer]:
          - img [ref=e157]
        - generic "折叠" [ref=e160] [cursor=pointer]:
          - img [ref=e162]
    - main [ref=e165]:
      - generic [ref=e166]:
        - generic [ref=e167]:
          - generic [ref=e168]: ⚠️
          - generic "账套数据更新后，依赖该数据的试算表、报表或附注尚未同步更新" [ref=e169]:
            - text: 当前项目有
            - strong [ref=e170]: "104"
            - text: 处数据过期
          - button "一键重算" [ref=e171] [cursor=pointer]:
            - generic [ref=e172]: 一键重算
          - button "查看详情" [ref=e173] [cursor=pointer]:
            - generic [ref=e174]: 查看详情
          - button "×" [ref=e175] [cursor=pointer]:
            - generic [ref=e176]: ×
        - generic [ref=e177]:
          - generic [ref=e178]: ⚠️
          - heading "页面渲染出错" [level=3] [ref=e179]
          - paragraph [ref=e180]: Cannot read properties of undefined (reading 'data')
          - generic [ref=e181]:
            - button "重试" [ref=e182] [cursor=pointer]:
              - generic [ref=e183]: 重试
            - button "返回首页" [ref=e184] [cursor=pointer]:
              - generic [ref=e185]: 返回首页
```

# Test source

```ts
  1   | /**
  2   |  * UAT — WorkpaperEditor 加载流程回归测试
  3   |  *
  4   |  * 锚定 spec workpaper-editor-refactor Phase 5.2
  5   |  *
  6   |  * 验证三大反模式不复现：
  7   |  * 1. Vue setup ref 顺序错误（"Cannot access 'X' before initialization"）
  8   |  * 2. 顶层 v-if="loading" 守卫拦 init 死锁（永久"加载底稿中..."）
  9   |  * 3. GtLoadingOverlay 可见 + loadingHint 阶段提示
  10  |  *
  11  |  * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
  12  |  */
  13  | import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
  14  | 
  15  | const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'
  16  | 
  17  | async function loginAs(page: Page, username: string, password: string) {
  18  |   const resp = await page.request.post('/api/auth/login', {
  19  |     data: { username, password },
  20  |   })
  21  |   const body = await resp.json()
  22  |   const token = body.data?.access_token ?? body.access_token
  23  |   await page.addInitScript((t: string) => {
  24  |     window.sessionStorage.setItem('token', t)
  25  |     window.localStorage.setItem('token', t)
  26  |   }, token)
  27  |   return token
  28  | }
  29  | 
  30  | /** 找一个有效的底稿 ID（任意 wp_code，优先 D2 / E1） */
  31  | async function findAnyWpId(request: APIRequestContext, token: string): Promise<{ id: string; wpCode: string } | null> {
  32  |   const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
  33  |     headers: { Authorization: `Bearer ${token}` },
  34  |   })
  35  |   if (!resp.ok()) return null
  36  |   const body = await resp.json()
  37  |   const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  38  |   // 优先 D2 / E1
  39  |   for (const code of ['D2', 'E1', 'F2', 'A1']) {
  40  |     const wp = list.find((w: any) => (w.wp_code || '').toUpperCase() === code)
  41  |     if (wp?.id) return { id: wp.id, wpCode: code }
  42  |   }
  43  |   // 兜底任意一个
  44  |   if (list.length > 0) return { id: list[0].id, wpCode: list[0].wp_code || '?' }
  45  |   return null
  46  | }
  47  | 
  48  | test.describe('WorkpaperEditor 加载流程回归测试', () => {
  49  |   test('5.2.1 — 打开底稿无 ReferenceError + 无死锁', async ({ page, request }) => {
  50  |     test.setTimeout(60_000)
  51  |     const consoleErrors: string[] = []
  52  |     page.on('console', (msg) => {
  53  |       if (msg.type() === 'error') {
  54  |         const text = msg.text()
  55  |         // 过滤已知的网络错误（如 SSE 断连）
  56  |         if (/Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(text)) {
  57  |           consoleErrors.push(text)
  58  |         }
  59  |       }
  60  |     })
  61  |     page.on('pageerror', (err) => {
  62  |       consoleErrors.push(`pageerror: ${err.message}`)
  63  |     })
  64  | 
  65  |     const token = await loginAs(page, 'admin', 'admin123')
  66  |     const wp = await findAnyWpId(request, token)
  67  |     test.skip(!wp, '项目内无可用底稿')
  68  | 
  69  |     await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}/edit`)
  70  | 
  71  |     // 等待 Univer 容器渲染（关键：顶层 v-if 改 overlay 模式后，container 应一直存在）
> 72  |     await page.waitForSelector('.gt-wp-editor-univer, .gt-wp-editor-loading', { timeout: 15_000 })
      |                ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  73  | 
  74  |     // 等待 5 秒让 init 跑完
  75  |     await page.waitForTimeout(5_000)
  76  | 
  77  |     // 验证 1：没有 setup ref ReferenceError
  78  |     expect(consoleErrors, `控制台 ReferenceError:\n${consoleErrors.join('\n')}`).toHaveLength(0)
  79  | 
  80  |     // 验证 2：loading overlay 已消失（无死锁）
  81  |     const overlay = page.locator('.gt-loading-overlay')
  82  |     const overlayCount = await overlay.count()
  83  |     if (overlayCount > 0) {
  84  |       // 给 10 秒兜底 wait（大文件加载可能慢）
  85  |       await expect(overlay).toBeHidden({ timeout: 10_000 }).catch(() => {
  86  |         throw new Error(`GtLoadingOverlay 在 15 秒后仍可见，疑似死锁；底稿: ${wp!.wpCode}`)
  87  |       })
  88  |     }
  89  |   })
  90  | 
  91  |   test('5.2.2 — GtLoadingOverlay 加载阶段提示出现', async ({ page, request }) => {
  92  |     test.setTimeout(45_000)
  93  |     const token = await loginAs(page, 'admin', 'admin123')
  94  |     const wp = await findAnyWpId(request, token)
  95  |     test.skip(!wp, '项目内无可用底稿')
  96  | 
  97  |     // 提前监听 overlay 出现（避免错过快速一闪）
  98  |     let overlaySeen = false
  99  |     let hintSeen = false
  100 |     page.on('framenavigated', async () => {
  101 |       try {
  102 |         const ov = page.locator('.gt-loading-overlay')
  103 |         if ((await ov.count()) > 0) overlaySeen = true
  104 |         const hint = page.locator('.gt-loading-overlay__hint')
  105 |         if ((await hint.count()) > 0) hintSeen = true
  106 |       } catch { /* 页面跳转中 dom 可能短暂不可达 */ }
  107 |     })
  108 | 
  109 |     await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}/edit`)
  110 | 
  111 |     // 在加载早期捕获 overlay 与 hint（轮询 200ms 一次，最多 5 秒）
  112 |     for (let i = 0; i < 25 && (!overlaySeen || !hintSeen); i++) {
  113 |       try {
  114 |         if (!overlaySeen && await page.locator('.gt-loading-overlay').count() > 0) overlaySeen = true
  115 |         if (!hintSeen && await page.locator('.gt-loading-overlay__hint').count() > 0) hintSeen = true
  116 |       } catch { /* */ }
  117 |       await page.waitForTimeout(200)
  118 |     }
  119 | 
  120 |     // overlay 至少出现过一次（除非加载极快 < 200ms，给个软 assertion）
  121 |     if (!overlaySeen) {
  122 |       console.warn('[5.2.2] GtLoadingOverlay 未捕获到，可能加载非常快（< 200ms）')
  123 |     }
  124 |     // 等待加载完成
  125 |     await page.waitForTimeout(3_000)
  126 |     // 验证 overlay 最终消失
  127 |     await expect(page.locator('.gt-loading-overlay')).toBeHidden({ timeout: 15_000 })
  128 |   })
  129 | 
  130 |   test('5.2.3 — 无效 wpId 不会卡死页面', async ({ page }) => {
  131 |     test.setTimeout(30_000)
  132 |     await loginAs(page, 'admin', 'admin123')
  133 | 
  134 |     const consoleErrors: string[] = []
  135 |     page.on('pageerror', (err) => {
  136 |       consoleErrors.push(`pageerror: ${err.message}`)
  137 |     })
  138 | 
  139 |     // 故意传非 UUID 的 wpId
  140 |     await page.goto(`/projects/${PROJECT_ID}/workpapers/not-a-real-id/edit`)
  141 |     await page.waitForTimeout(5_000)
  142 | 
  143 |     // 不应抛出 setup ref 类错误（可以有"底稿不存在"toast）
  144 |     const setupErrors = consoleErrors.filter((e) => /Cannot access|before initialization/.test(e))
  145 |     expect(setupErrors, `setup 阶段 ReferenceError:\n${setupErrors.join('\n')}`).toHaveLength(0)
  146 |   })
  147 | })
  148 | 
```