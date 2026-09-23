/**
 * D2 宿主接线守卫 —— 锁死「bridge 有能力但宿主不接」这类静默失效。
 *
 * ═══ 为什么必须单独一个文件 ═══
 *
 * 桥自己的行为测试（`d2SyncDurableGate.spec.ts` 等）**自己**构造 options，
 * 所以宿主漏传钩子时它照样全绿 —— 2026-09-06 变异检验实测：把宿主里的 flush /
 * forcesave 接线整行删掉，那 10 条测试无一变红（M06/M07 判 GREEN）。
 * 而漏传恰恰就是原始缺陷 A/B 的根因。
 *
 * 故这里的判据落在**宿主源码的真实形态**：宿主必须把钩子接到桥上，
 * 且钩子指向真实存在的实现（不是 `undefined`、不是空函数）。
 *
 * ═══ 2026-06-01 重新指向：D2 已迁到统一路径 ═══
 *
 * 本文件上一版锚在 `useD2SyncBridge(` / `const ooSheetRef` / `ref="ooSheetRef"` /
 * `flushBeforeOo` / `requestForceSave` 这五个名字上。`42d2f6e6f` 之后 D2 宿主换成了
 * **统一路径**：`useWorkpaperSyncBridge` + `<WorkpaperSyncEditorHost>`，
 * 强制保存走 `syncEditorHostRef.value.forceSave()`（内部是 room forcesave）。
 *
 * 逐锚点核对（`git show HEAD:` 与工作树都查过）：五个旧名字在**两侧都不存在** ⇒
 * 这是判据陈旧，不是宿主回退。所以把判据重新钉到**当前**接线上：
 *
 * | 旧锚点              | 当前等价物                                        |
 * |---------------------|---------------------------------------------------|
 * | `useD2SyncBridge(`  | `useWorkpaperSyncBridge(`                          |
 * | `flushBeforeOo`     | `flushHtml`（内部必须先 `formData.flushPendingSave()`）|
 * | `requestForceSave`  | 宿主自己 `await syncEditorHostRef.value.forceSave()` |
 * | `const ooSheetRef`  | `const syncEditorHostRef`                          |
 * | `ref="ooSheetRef"`  | `ref="syncEditorHostRef"`（绑在 WorkpaperSyncEditorHost 上）|
 *
 * 语义一字不改：**宿主必须真的把 flush/reload 接进桥，并真的持有编辑器实例去
 * forcesave**。变异检验（删掉统一接线 ⇒ 必须红）见同名证据文档。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(
  __dirname,
  '..',
  'GtD2AccountsReceivable.vue',
)
/** 统一桥 —— 宿主现在消费的就是它。 */
const BRIDGE = resolve(
  __dirname,
  '..',
  'sync',
  'useWorkpaperSyncBridge.ts',
)
/** 统一编辑器宿主 —— `forceSave()` 的真实实现方。 */
const EDITOR_HOST = resolve(
  __dirname,
  '..',
  'sync',
  'WorkpaperSyncEditorHost.vue',
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

/** 截出 `fn(` 的实参对象（括号配对，不用固定字符窗口）。 */
function extractCallArgs(src: string, fnName: string): string {
  const marker = `${fnName}(`
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

describe('D2 宿主必须把同步钩子真正接到统一桥上', () => {
  const hostSrc = stripComments(read(HOST))
  const args = extractCallArgs(hostSrc, 'useWorkpaperSyncBridge')

  it('宿主确实调用了 useWorkpaperSyncBridge 并能截出实参', () => {
    expect(args.length).toBeGreaterThan(0)
  })

  it('flushHtml 必须传，且真的先 flush 掉 HTML 侧未落库的编辑（缺陷 A 反向锁）', () => {
    expect(args).toContain('flushHtml')
    // 🔴 关键不是「传了个 flushHtml」，而是它**第一步**就把 debounce 中的保存落库。
    //    漏掉这一步，服务端 store-projection 读到的还是旧 store —— 那就是缺陷 A 原型。
    expect(args).toMatch(/flushHtml\s*:\s*async\s*\(\s*\)\s*=>\s*\{\s*await\s+formData\.flushPendingSave\(\)/)
    // 落库之后才允许去读投影（顺序反了等于没 flush）
    const flushBody = args.slice(args.indexOf('flushHtml'))
    expect(flushBody.indexOf('formData.flushPendingSave()')).toBeLessThan(
      flushBody.indexOf('readStoreProjection'),
    )
  })

  it('reloadHtml 仍在传，且真的重查库（回归保护，切回后要重载）', () => {
    expect(args).toMatch(/reloadHtml\s*:/)
    expect(args).toMatch(/reloadHtml\s*:[\s\S]*?formData\.loadAll\(\)/)
  })

  it('capability 必须从 manifest 现算，不得内联字面量（谓词 8 反向锁）', () => {
    expect(args).toMatch(/capability\s*:\s*capabilityForEntry\(/)
    expect(args).not.toMatch(/capability\s*:\s*['"]/)
  })
})

describe('宿主必须持有统一编辑器宿主的实例引用，否则 forceSave 无从调用', () => {
  const hostSrc = stripComments(read(HOST))

  it('声明了 syncEditorHostRef', () => {
    expect(hostSrc).toMatch(/const\s+syncEditorHostRef\s*=\s*ref/)
  })

  it('模板上把 ref 绑到了 WorkpaperSyncEditorHost', () => {
    // 三要素：组件标签 + ref 绑定 + 该 ref 名字一致
    const mountIdx = hostSrc.indexOf('<WorkpaperSyncEditorHost')
    expect(mountIdx).toBeGreaterThan(-1)
    const mount = hostSrc.slice(mountIdx, mountIdx + 400)
    expect(mount).toContain('ref="syncEditorHostRef"')
    // 桥必须真的喂进去 —— 不喂就是「挂了个壳，同步全走不通」
    expect(mount).toMatch(/:bridge\s*=\s*"syncBridge"/)
  })

  it('切回结构化视图时真的 await 了实例的 forceSave（缺陷 B 反向锁）', () => {
    // 必须真的去调编辑器宿主的 forceSave，而不是恒返 durable 的假实现
    expect(hostSrc).toMatch(/await\s+syncEditorHostRef\.value\.forceSave\(\)/)
    expect(hostSrc).not.toMatch(/durable\s*:\s*true/)
    // 且必须被 canForcesave 门控（没确认过就发 forcesave 是 AC 违背）
    expect(hostSrc).toMatch(/syncBridge\.canForcesave\.value\s*&&\s*syncEditorHostRef\.value/)
  })
})

describe('统一桥必须真的消费宿主传入的钩子', () => {
  const bridgeSrc = stripComments(read(BRIDGE))

  it('switchToOnlyOffice 前真的 await 了 flushHtml（漏调会静默推旧 store）', () => {
    expect(bridgeSrc).toMatch(/await\s+options\.flushHtml\(\)/)
  })

  it('reload 时真的 await 了 reloadHtml，并把 minimumRevision 传下去', () => {
    expect(bridgeSrc).toMatch(/await\s+options\.reloadHtml\(\s*revision\s*\)/)
  })

  it('reloadHtml 的契约里写明「不得低于 minimumRevision」', () => {
    expect(bridgeSrc).toMatch(/reloadHtml\s*:\s*\(\s*minimumRevision\s*:\s*number\s*\)\s*=>\s*Promise<void>/)
  })

  it('capability 不支持 oo 时拒绝进入（不得降级为照样开编辑器）', () => {
    expect(bridgeSrc).toMatch(/supportedModesForCapability\(\s*options\.capability\s*\)/)
    expect(bridgeSrc).toContain('bridge_mode_not_supported')
  })
})

describe('统一编辑器宿主必须暴露可 await 的 forceSave', () => {
  const editorSrc = stripComments(read(EDITOR_HOST))

  it('defineExpose 暴露了 forceSave', () => {
    expect(editorSrc).toMatch(/defineExpose\(\{[^}]*forceSave/)
  })

  it('forceSave 是 async 且交回 operationId（宿主要靠它推进终态）', () => {
    expect(editorSrc).toMatch(/async\s+function\s+forceSave\s*\(/)
    expect(editorSrc).toMatch(/Promise<\{\s*operationId\s*:\s*string\s*\}>/)
  })

  it('未确认就调 forceSave 必须拒绝，且不得静默返回（fail visible 反向锁）', () => {
    const body = editorSrc.slice(
      editorSrc.indexOf('async function forceSave'),
      editorSrc.indexOf('defineExpose'),
    )
    expect(body).toMatch(/if\s*\(\s*!props\.bridge\.canForcesave\.value\s*\)/)
    expect(body).toContain('editor_host_forcesave_before_confirmation')
    // 拒绝必须抛，不能 return undefined 让调用方以为成功了
    expect(body).toMatch(/throw\s+refusal/)
  })

  it('拿不到 operation 时也必须抛，不谎报成功', () => {
    const body = editorSrc.slice(
      editorSrc.indexOf('async function forceSave'),
      editorSrc.indexOf('defineExpose'),
    )
    expect(body).toContain('editor_host_forcesave_without_operation')
  })
})
