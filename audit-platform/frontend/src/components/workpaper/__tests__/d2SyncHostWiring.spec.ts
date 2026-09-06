/**
 * D2 宿主接线守卫 —— 锁死「bridge 有能力但宿主不接」这类静默失效。
 *
 * ═══ 为什么必须单独一个文件 ═══
 *
 * `d2SyncDurableGate.spec.ts` 测的是 bridge 本身的行为，它**自己**构造 options，
 * 所以宿主漏传钩子时它照样全绿 —— 2026-09-06 变异检验实测：把
 * `GtD2AccountsReceivable.vue` 里的 `flushBeforeOo` / `requestForceSave` 整行删掉，
 * 那 10 条测试无一变红（M06/M07 判 GREEN）。而漏传恰恰就是原始缺陷 A/B 的根因。
 *
 * 故这里的判据落在**宿主源码的真实形态**：宿主必须把钩子接到 bridge 上，
 * 且钩子指向真实存在的实现（不是 `undefined`、不是空函数）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(
  __dirname,
  '..',
  'GtD2AccountsReceivable.vue',
)
const BRIDGE = resolve(
  __dirname,
  '..',
  'sync',
  'useD2SyncBridge.ts',
)

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

/** 去掉注释，避免「注释里提到了这个名字」被当成真接线。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 截出 `useD2SyncBridge({ ... })` 的实参对象（括号配对，不用固定字符窗口）。 */
function extractBridgeCallArgs(src: string): string {
  const marker = 'useD2SyncBridge('
  const start = src.indexOf(marker)
  if (start < 0) return ''
  let depth = 0
  for (let i = start + marker.length - 1; i < src.length; i++) {
    const ch = src[i]
    if (ch === '(') depth++
    else if (ch === ')') {
      depth--
      if (depth === 0) return src.slice(start + marker.length, i)
    }
  }
  return ''
}

describe('D2 宿主必须把同步钩子真正接到 bridge 上', () => {
  const hostSrc = stripComments(read(HOST))
  const args = extractBridgeCallArgs(hostSrc)

  it('宿主确实调用了 useD2SyncBridge 并能截出实参', () => {
    expect(args.length).toBeGreaterThan(0)
  })

  it('flushBeforeOo 必须传，且指向真实的 flush 实现（缺陷 A 反向锁）', () => {
    expect(args).toContain('flushBeforeOo')
    // 必须落到 useD2FormData 暴露的那个 flush，不能是空函数糊过去
    expect(args).toMatch(/flushBeforeOo\s*:\s*\(\s*\)\s*=>\s*formData\.flushPendingSave\(\)/)
  })

  it('requestForceSave 必须传，且指向编辑器实例的 forceSave（缺陷 B 反向锁）', () => {
    expect(args).toContain('requestForceSave')
    expect(args).toMatch(/requestForceSave\s*:/)
    // 必须真的去调编辑器的 forceSave，而不是恒返 durable 的假实现
    expect(args).toContain('forceSave()')
    expect(args).not.toMatch(/durable\s*:\s*true/)
  })

  it('reloadHtml 仍在传（回归保护，切回后要重查库）', () => {
    expect(args).toMatch(/reloadHtml\s*:/)
  })
})

describe('宿主必须持有编辑器实例引用，否则 forceSave 无从调用', () => {
  const hostSrc = stripComments(read(HOST))

  it('声明了 ooSheetRef', () => {
    expect(hostSrc).toMatch(/const\s+ooSheetRef\s*=\s*ref/)
  })

  it('模板上把 ref 绑到了 GtOnlyOfficeSheet', () => {
    // 三要素：组件标签 + ref 绑定 + 该 ref 名字一致
    const mount = hostSrc.slice(hostSrc.indexOf('<GtOnlyOfficeSheet'))
    expect(mount).toContain('ref="ooSheetRef"')
  })
})

describe('bridge 必须真的解构并使用宿主传入的钩子', () => {
  const bridgeSrc = stripComments(read(BRIDGE))

  it('requestForceSave 被解构出来（漏解构会运行时炸，TS 查不出）', () => {
    expect(bridgeSrc).toMatch(/const\s*\{[^}]*requestForceSave[^}]*\}\s*=\s*options/)
  })

  it('flushBeforeOo 被解构出来', () => {
    expect(bridgeSrc).toMatch(/const\s*\{[^}]*flushBeforeOo[^}]*\}\s*=\s*options/)
  })

  it('pull 前真的 await 了 requestForceSave', () => {
    expect(bridgeSrc).toMatch(/await\s+requestForceSave\(\)/)
  })

  it('push 前真的 await 了 flushBeforeOo', () => {
    expect(bridgeSrc).toMatch(/await\s+flushBeforeOo\(\)/)
  })

  it('durable 不为真时抛 NotDurableError（不得降级为继续 pull）', () => {
    expect(bridgeSrc).toMatch(/!saved\.durable/)
    expect(bridgeSrc).toContain('throw new NotDurableError(')
  })
})

describe('编辑器组件必须暴露可 await 的 forceSave', () => {
  const editorSrc = stripComments(
    read(resolve(__dirname, '..', 'GtOnlyOfficeSheet.vue')),
  )

  it('defineExpose 暴露了 forceSave', () => {
    expect(editorSrc).toMatch(/defineExpose\(\{[^}]*forceSave/)
  })

  it('forceSave 是 async 且返回耐久语义', () => {
    expect(editorSrc).toMatch(/async\s+function\s+forceSave\s*\(/)
    expect(editorSrc).toContain('durable')
  })

  it('forceSave 必须把 artifact 指纹原样转发给调用方', () => {
    // 🔴 2026-09-06 浏览器复测踩到：只取 accepted/durable/detail 三个字段，
    // artifact 指纹被丢掉 ⇒ pull 请求体变成 `{}`，服务端第二道陈旧校验
    // 永远拿不到判据（而它是防「绕过前端直接打 API」的唯一手段）。
    const body = editorSrc.slice(
      editorSrc.indexOf('async function forceSave'),
      editorSrc.indexOf('defineExpose'),
    )
    expect(body).toMatch(/artifact\s*:\s*payload\??\.?artifact/)
  })

  it('失败时不谎报 durable:true（fail-open 反向锁）', () => {
    // catch 分支里必须 durable: false
    const catchIdx = editorSrc.indexOf('} catch (err: any) {', editorSrc.indexOf('async function forceSave'))
    expect(catchIdx).toBeGreaterThan(0)
    const catchBlock = editorSrc.slice(catchIdx, catchIdx + 700)
    expect(catchBlock).toContain('durable: false')
    expect(catchBlock).not.toContain('durable: true')
  })
})
