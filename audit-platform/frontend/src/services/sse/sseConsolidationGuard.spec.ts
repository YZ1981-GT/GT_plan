/**
 * SSE 连接去重守卫（frontend-sse-connection-consolidation R6.3 / Task 7.2）
 *
 * 断言：除单例总线 `services/sse/projectEventStream.ts` 与工具 `utils/sse.ts` 外，
 * `src/` 下无对 `/events/stream` 的直连——即：
 *  1. 除总线/工具外无 `createSSE(` 调用（一律经总线订阅）；
 *  2. 无 `new EventSource(...)` 连 `/events/stream`（AttachmentManagement 连
 *     `/api/sse/projects/` 属不同端点，不受此约束）。
 *
 * 防止连接去重被回归（新消费者又各自开连接）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const SRC = resolve(process.cwd(), 'src')

/** 允许对 /events/stream 建连的文件：单例总线（唯一连接持有者）+ createSSE 定义所在工具。 */
const ALLOW_CREATESSE = new Set([
  resolve(SRC, 'services/sse/projectEventStream.ts'),
  resolve(SRC, 'utils/sse.ts'),
])

/** 判断文件是否引用「项目事件流」端点 /events/stream（区别于 bulk 进度 /progress 等其它 SSE）。 */
function _refsProjectEventStream(content: string): boolean {
  return (
    /events\/stream/.test(content) ||
    /eventPaths\.stream\s*\(/.test(content) ||
    /P_events\.stream\s*\(/.test(content) ||
    /P_evt\.stream\s*\(/.test(content)
  )
}

function walk(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) {
      if (name === 'node_modules' || name === 'dist' || name === '__tests__') continue
      out.push(...walk(p))
    } else if (/\.(ts|vue)$/.test(name) && !/\.spec\.ts$/.test(name) && !/\.d\.ts$/.test(name)) {
      out.push(p)
    }
  }
  return out
}

describe('SSE 连接去重守卫（R6.3）', () => {
  const files = walk(SRC)

  it('除单例总线/工具外，无文件用 createSSE 直连 /events/stream', () => {
    const offenders: string[] = []
    for (const f of files) {
      if (ALLOW_CREATESSE.has(resolve(f))) continue
      const content = readFileSync(f, 'utf-8')
      // 仅当 createSSE 且引用 /events/stream 才违规（bulk /progress 等其它 SSE 端点不受约束，R5.6）
      if (/\bcreateSSE\s*\(/.test(content) && _refsProjectEventStream(content)) {
        offenders.push(f.replace(SRC, 'src'))
      }
    }
    expect(
      offenders,
      `以下文件用 createSSE 直连 /events/stream（应改为经 projectEventStream 总线订阅）:\n${offenders.join('\n')}`,
    ).toEqual([])
  })

  it('无文件用 native EventSource 连 /events/stream', () => {
    const offenders: string[] = []
    for (const f of files) {
      const content = readFileSync(f, 'utf-8')
      if (/new\s+EventSource\s*\(/.test(content) && /events\/stream/.test(content)) {
        offenders.push(f.replace(SRC, 'src'))
      }
    }
    expect(
      offenders,
      `以下文件用 native EventSource 连 /events/stream（应改为经总线）:\n${offenders.join('\n')}`,
    ).toEqual([])
  })
})
