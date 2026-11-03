import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const read = (path) => readFileSync(resolve(ROOT, path), 'utf8')

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
    const budget = source.indexOf("check-bundle-budget.mjs")
    const smoke = source.indexOf("smoke-built-artifact.mjs")
    const select = source.indexOf('await selectSnapshot(artifactId, fullDigest)')
    expect(budget).toBeGreaterThan(0)
    expect(smoke).toBeGreaterThan(budget)
    expect(select).toBeGreaterThan(smoke)
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
    const formula = read('src/components/formula/FormulaManagerDialog.vue')
    const formulaWatcher = formula.slice(
      formula.indexOf('// 初始加载当前报表的数据。'),
      formula.indexOf('function onTreeNodeClick'),
    )
    expect(formulaWatcher).toContain('}, { immediate: true })')

    const dsh = read('src/components/ai/DshPanel.vue')
    const dshWatcher = dsh.slice(
      dsh.indexOf('// 打开时：锁定背景滚动'),
      dsh.indexOf('// layoutMode 变化时'),
    )
    expect(dshWatcher).toContain('}, { immediate: true })')
    expect(dshWatcher).toContain('if (!props.modelValue) return')

    const customQuery = read('src/components/query/CustomQueryDialog.vue')
    expect(customQuery).toContain('props.openRevision')
    expect(customQuery).toContain('request === indicatorRequest')
    expect(customQuery).toContain('clearPendingReveal()')
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
