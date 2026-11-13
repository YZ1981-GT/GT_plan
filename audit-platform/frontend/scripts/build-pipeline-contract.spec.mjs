import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const read = (path) => readFileSync(resolve(ROOT, path), 'utf8')

/** 每个 `watch(...)` 调用的完整源码（括号配平；源码里不靠注释原文定位，注释改字不影响判据）。 */
function watchCalls(source) {
  const calls = []
  for (const match of source.matchAll(/\bwatch\(/g)) {
    let depth = 0
    for (let index = match.index + 'watch'.length; index < source.length; index += 1) {
      const char = source[index]
      if (char === '(') depth += 1
      else if (char === ')' && --depth === 0) {
        calls.push({ index: match.index, text: source.slice(match.index, index + 1) })
        break
      }
    }
  }
  return calls
}

const isImmediate = (call) => /\{\s*immediate:\s*true\s*\}\s*\)$/.test(call.text)

describe('正式前端构建契约', () => {
  it('typecheck、build、verify、preview 各自职责分离', () => {
    const pkg = JSON.parse(read('package.json'))
    expect(pkg.scripts.typecheck).toContain('vue-tsc')
    expect(pkg.scripts.build).toContain('vite.js build')
    expect(pkg.scripts.build).not.toContain('vue-tsc')
    expect(pkg.scripts['build:verify']).toContain('build-verified-dist.mjs')
    expect(pkg.scripts['preview:stable']).toContain('preview-verified-dist.mjs')
  })

  it('Vite 显式输出 manifest 且关闭 production sourcemap', () => {
    const source = read('vite.config.ts')
    expect(source).toMatch(/manifest:\s*true/)
    expect(source).toMatch(/sourcemap:\s*false/)
    for (const name of ['heavy-univer', 'heavy-office', 'heavy-excel']) {
      expect(source).toContain(name)
    }
  })

  it('stable 只调用验证快照流程，不直接覆盖 dist', () => {
    const launcher = read('../../start-dev.bat')
    expect(launcher).toContain('run build:verify')
    expect(launcher).not.toMatch(/GT_RUNTIME_MODE%"=="stable"[\s\S]{0,500}run build:runtime/)
  })

  it('verified snapshot 仅在预算和 smoke 都通过后原子切换', () => {
    const source = read('scripts/build-verified-dist.mjs')
    expect(source).toContain("resolve(ROOT, 'scripts/check-bundle-budget.mjs')")
    expect(source).toContain("resolve(ROOT, 'scripts/smoke-built-artifact.mjs')")
    expect(source).toContain("resolve(ROOT, 'scripts/bundle-budget.json')")
    // 顺序：预算 → smoke → 切换指针；三处都按调用点定位，不按常量声明位置。
    const budget = source.indexOf('run(BUDGET')
    const smoke = source.indexOf('run(SMOKE')
    const select = source.indexOf('await selectSnapshot(artifactId, fullDigest)')
    expect(budget).toBeGreaterThan(0)
    expect(smoke).toBeGreaterThan(budget)
    expect(select).toBeGreaterThan(smoke)
    expect(source).toContain('artifactValid')
    expect(source).toContain('await rename(temporary, CURRENT_FILE)')
    expect(source).toContain('当前快照指针未改变')
  })

  it('全局重组件和 Office 预览器只从动态边界进入', () => {
    const layout = read('src/layouts/ThreeColumnLayout.vue')
    for (const moduleName of ['FormulaManagerDialog.vue', 'CustomQueryDialog.vue', 'DshPanel.vue']) {
      expect(layout).toContain(`import('@/${moduleName === 'DshPanel.vue' ? 'components/ai' : moduleName === 'CustomQueryDialog.vue' ? 'components/query' : 'components/formula'}/${moduleName}')`)
      expect(layout).not.toMatch(new RegExp(`import\\s+\\w+\\s+from\\s+['\"][^'\"]*${moduleName}`))
    }
    for (const file of [
      'src/components/attachment/preview/AttachmentPreviewCore.vue',
      'src/components/deliverable/DeliverablePreview.vue',
    ]) {
      const source = read(file)
      expect(source).toContain("import('@vue-office/docx')")
      expect(source).toContain("import('@vue-office/excel')")
      expect(source).toContain("import('@vue-office/pdf')")
      expect(source).not.toMatch(/import\s+\w+\s+from\s+['"]@vue-office\//)
    }
  })

  it('异步弹窗支持以打开态首次挂载，避免首次事件丢失', () => {
    // 按监听调用本身判，不靠注释原文切片：注释改一个字，切片就变空串（2026-11 两个弹窗都因此恒红）。
    const formula = read('src/components/formula/FormulaManagerDialog.vue')
    const scriptStart = formula.indexOf('<script setup')
    const formulaScript = formula.slice(scriptStart, formula.indexOf('</script>', scriptStart))
    const openWatcher = watchCalls(formulaScript).find(
      (call) => call.text.startsWith('watch([visible') && call.text.includes('onOpenContextChange'),
    )
    expect(openWatcher, '公式管理弹窗必须监听打开上下文').toBeDefined()
    expect(isImmediate(openWatcher), '挂载即打开时首轮必须同步加载').toBe(true)
    // immediate 首轮同步执行：必须注册在全部顶层声明之后，否则读到暂时性死区里的 ref。
    const declarations = [...formulaScript.matchAll(/^(?:const|let)\s+\w+/gm)]
    expect(declarations.length).toBeGreaterThan(0)
    expect(openWatcher.index).toBeGreaterThan(declarations.at(-1).index)

    const dsh = read('src/components/ai/DshPanel.vue')
    const dshWatcher = watchCalls(dsh).find((call) => call.text.startsWith('watch(() => props.modelValue'))
    expect(dshWatcher, 'DSH 面板必须监听打开状态').toBeDefined()
    expect(isImmediate(dshWatcher), '按需下载后可能已是打开态，必须 immediate').toBe(true)
    expect(dshWatcher.text).toContain('if (!props.modelValue) return')

    const customQuery = read('src/components/query/CustomQueryDialog.vue')
    const customWatchers = watchCalls(customQuery)
    // 已挂载时的新入口靠 openRevision 重走一次；挂载即打开靠 immediate。
    expect(customWatchers.some(
      (call) => call.text.startsWith('watch([visible, () => props.openRevision]') && isImmediate(call),
    )).toBe(true)
    // 业务页入口（entry）首次打开就要执行，不能只套上下文。
    expect(customWatchers.some(
      (call) => call.text.startsWith('watch([visible, () => props.entry]') && isImmediate(call),
    )).toBe(true)
    // 换项目 / 年度后晚到的指标树响应必须丢弃。
    expect(customQuery).toMatch(/generation\s*===\s*indicatorGeneration/)
    // 查询结果同理：响应和异常都先比代际，旧请求不能覆盖新查询的结果或 loading 状态。
    expect(customQuery).toContain('const generation = ++queryGeneration')
    expect(customQuery.match(/if \(generation !== queryGeneration\) return/g)?.length).toBeGreaterThanOrEqual(2)
    expect(customQuery).toContain('function invalidateQueryResult()')
  })

  it('Nginx 提供 SPA 回退、缓存策略和 API/WOPI 代理', () => {
    const source = read('docker/nginx.conf')
    expect(source).toContain('try_files $uri $uri/ /index.html;')
    expect(source).toContain('max-age=31536000, immutable')
    expect(source).toContain('location = /index.html')
    expect(source).toContain('location = /sw.js')
    expect(source).toContain('location /api/')
    expect(source).toContain('location /wopi/')
    expect(source).toContain('proxy_buffering off;')
    expect(source).toContain('proxy_request_buffering off;')
    expect(source).toContain('client_max_body_size 850m;')
  })
})
