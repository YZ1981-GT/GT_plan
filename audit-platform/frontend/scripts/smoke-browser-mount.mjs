// 构建产物冒烟的浏览器步骤：真实执行 JS，断言根组件挂载且没有未捕获异常。
// 静态 HTTP 冒烟看不到 chunk 循环初始化（TDZ）造成的白屏
// （spec frontend-prod-build-white-screen-closure）。
import { chromium } from '@playwright/test'

const MOUNT_TIMEOUT_MS = 15_000

/** 后端是假的，接口 404 / 502 产生的资源加载报错不算产物缺陷。 */
export function isIgnorableConsoleError(text) {
  return /Failed to load resource/i.test(text)
}

/**
 * @param {string} url 要打开的页面
 * @returns {Promise<{ children: number, errors: string[] }>}
 */
export async function probeMount(url) {
  const browser = await chromium.launch({ headless: true })
  const errors = []
  try {
    const page = await browser.newPage()
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`))
    page.on('console', (message) => {
      if (message.type() === 'error' && !isIgnorableConsoleError(message.text())) {
        errors.push(`console.error: ${message.text()}`)
      }
    })
    await page.goto(url, { waitUntil: 'load', timeout: MOUNT_TIMEOUT_MS })
    let children = 0
    try {
      await page.waitForFunction(
        () => (document.querySelector('#app')?.children.length ?? 0) > 0,
        undefined,
        { timeout: MOUNT_TIMEOUT_MS },
      )
    } catch {
      // 超时即未挂载，下面按 children 判定
    }
    children = await page.evaluate(() => document.querySelector('#app')?.children.length ?? 0)
    return { children, errors }
  } finally {
    await browser.close()
  }
}

export async function assertAppMounts(url) {
  const { children, errors } = await probeMount(url)
  if (children === 0 || errors.length) {
    const detail = errors.length ? errors.join('；') : '无报错但 #app 为空'
    throw new Error(`浏览器首屏未挂载或有运行时错误（${url}）：${detail}`)
  }
}
