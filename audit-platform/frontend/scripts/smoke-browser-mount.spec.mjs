import { createServer } from 'node:http'
import { afterAll, beforeAll, describe, expect, test } from 'vitest'
import { assertAppMounts, isIgnorableConsoleError } from './smoke-browser-mount.mjs'

// 阴性对照：vendor 与 index 互相静态 import，vendor 顶层读取 index 里尚未初始化的 const，
// 与生产白屏同形（Cannot access 'x' before initialization）。
const HTML = '<!doctype html><html><body><div id="app"></div><script type="module" src="/entry.js"></script></body></html>'
const FILES = {
  good: {
    '/entry.js': 'document.getElementById("app").appendChild(document.createElement("main"))',
  },
  circular: {
    '/entry.js': 'import { vendorValue } from "./vendor.js"\nexport const isClient = true\ndocument.getElementById("app").textContent = String(vendorValue)',
    '/vendor.js': 'import { isClient } from "./entry.js"\nexport const vendorValue = isClient',
  },
  silentBlank: {
    '/entry.js': '// 没有任何输出，也没有报错',
  },
}

let server
let port

beforeAll(async () => {
  server = createServer((request, response) => {
    const [, scenario, ...rest] = request.url.split('?')[0].split('/')
    const path = `/${rest.join('/')}`
    const files = FILES[scenario]
    if (files && files[path] !== undefined) {
      response.setHeader('content-type', 'text/javascript')
      response.end(files[path])
      return
    }
    if (files && (path === '/' || path === '/index.html')) {
      response.setHeader('content-type', 'text/html')
      // 模块路径带场景前缀，浏览器解析 /entry.js 会丢前缀，所以用 <base>
      response.end(HTML.replace('<body>', `<head><base href="/${scenario}/"></head><body>`)
        .replace('src="/entry.js"', 'src="entry.js"'))
      return
    }
    response.statusCode = 404
    response.end('not found')
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  port = server.address().port
})

afterAll(() => new Promise((resolve) => server.close(resolve)))

describe('浏览器首屏冒烟', () => {
  test('正常产物通过', async () => {
    await expect(assertAppMounts(`http://127.0.0.1:${port}/good/`)).resolves.toBeUndefined()
  }, 60_000)

  test('循环初始化（TDZ）白屏必须失败', async () => {
    await expect(assertAppMounts(`http://127.0.0.1:${port}/circular/`)).rejects.toThrow(/before initialization|未挂载/)
  }, 60_000)

  test('无报错但根节点为空也必须失败', async () => {
    await expect(assertAppMounts(`http://127.0.0.1:${port}/silentBlank/`)).rejects.toThrow(/#app 为空/)
  }, 60_000)

  test('资源加载 404 不算产物错误', () => {
    expect(isIgnorableConsoleError('Failed to load resource: the server responded with a status of 404')).toBe(true)
    expect(isIgnorableConsoleError('Uncaught ReferenceError: x is not defined')).toBe(false)
  })
})
