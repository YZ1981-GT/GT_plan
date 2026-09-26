/**
 * F1 预付账款 L2 OO→HTML 全受管 sheet 验收。
 *
 * spec: f1-sync-coverage-and-first-canary · Task 12
 *
 * 🔴 当前卡 BP-61-1 adapter 未注册：用例标 `pending_adapter`，
 *    供给就绪后改为 `pass` 并跑真栈三谓词。
 *
 * 结构照 D4 lane `d4-l2-oo-to-html-all.spec.ts`；
 * fixture = `fixtures/f1-l2-cases.json`；
 * 七态结果枚举沿用。
 */
import { test, expect } from '@playwright/test'
import cases from './fixtures/f1-l2-cases.json'

const BASE = process.env.BASE_URL ?? 'http://localhost:3030'

test.describe('F1 L2 OO→HTML', () => {
  for (const c of cases.cases) {
    test(`${c.id}: ${c.description}`, async ({ page }) => {
      test.skip(
        c.result_enum === 'pending_adapter',
        `⏭️ ${c.id}: adapter 未注册（BP-61-1），待供给就绪后跑真栈`,
      )
      // 真栈验收时补全：
      // 1. 导航到底稿编辑页
      // 2. 切到 OO 模式
      // 3. 写格 → Enter
      // 4. 等 forcesave callback
      // 5. 三谓词断言
    })
  }
})
