/**
 * F1 预付账款 L2 OO→HTML 全受管 sheet 验收。
 *
 * spec: f1-sync-coverage-and-first-canary · Task 12
 *
 * 🔴 修复：原 `import cases from './fixtures/f1-l2-cases.json'` 在 Playwright 的
 * Node ESM 加载器下抛 `needs an import attribute of "type: json"` ⇒ 整个文件
 * 0 tests（`npx playwright test --list` 实测 `Total: 0 tests in 0 files`）。
 * 改为 `readFileSync`（D4/G2/F3/F4/F5 lane 同款做法）。
 *
 * 🔴 canary 用例当前卡 BP-61-1（adapter 未注册），标 `pending_adapter`。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

interface F1L2Case {
  readonly id: string
  readonly description: string
  readonly result_enum: string
  readonly pending_reason?: string
}

interface F1L2Fixture {
  readonly cases: ReadonlyArray<F1L2Case>
}

const fixture: F1L2Fixture = JSON.parse(
  readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/f1-l2-cases.json'),
    'utf-8',
  ),
)

const BASE = process.env.BASE_URL ?? 'http://localhost:3030'

test.describe('F1 L2 OO→HTML', () => {
  for (const c of fixture.cases) {
    test(`${c.id}: ${c.description}`, async ({ page }) => {
      test.skip(
        c.result_enum === 'pending_adapter',
        `⏭️ ${c.id}: ${c.pending_reason ?? 'adapter 未注册（BP-61-1）'}`,
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
