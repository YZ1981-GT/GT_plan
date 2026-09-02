#!/usr/bin/env node
/**
 * 发现生产源码中的底稿 OnlyOffice 挂载点。
 *
 * 只输出源码事实，不推断业务 capability、持久化通道或 adapter。业务裁决由
 * `backend/data/workpaper_sync_entry_overlay.json` 提供，Python 生成器负责合并。
 *
 * 用法：
 *   node scripts/discover-workpaper-sync-mounts.mjs --json
 *   node scripts/discover-workpaper-sync-mounts.mjs --summary
 */
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import * as tsParser from '@typescript-eslint/parser'
import * as vueParser from 'vue-eslint-parser'

const TARGETS = new Map([
  ['gtonlyofficesheet', {
    component: 'GtOnlyOfficeSheet',
    canonicalFile: 'audit-platform/frontend/src/components/workpaper/GtOnlyOfficeSheet.vue',
    documentType: 'xlsx',
  }],
  ['onlyofficeworddialog', {
    component: 'OnlyOfficeWordDialog',
    canonicalFile: 'audit-platform/frontend/src/components/workpaper/OnlyOfficeWordDialog.vue',
    documentType: 'docx',
  }],
  ['workpaperwordeditor', {
    component: 'WorkpaperWordEditor',
    canonicalFile: 'audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue',
    documentType: 'docx',
  }],
])

const EXCLUDED_SEGMENTS = new Set([
  '__tests__',
  '__fixtures__',
  'fixtures',
  'test',
  'tests',
  'e2e',
  'stories',
  'archive',
  '_archive',
  'node_modules',
])

function findRepoRoot() {
  let current = path.resolve(process.cwd())
  for (let i = 0; i < 12; i += 1) {
    if (fs.existsSync(path.join(current, 'audit-platform', 'frontend', 'package.json'))) return current
    const parent = path.dirname(current)
    if (parent === current) break
    current = parent
  }
  throw new Error('repo root not found')
}

function toPosix(value) {
  return value.split(path.sep).join('/')
}

function normalizeComponentName(value) {
  return String(value || '').replace(/[-_:]/g, '').toLowerCase()
}

function isExcluded(relativePath) {
  const segments = toPosix(relativePath).split('/')
  const base = segments.at(-1) || ''
  return segments.some((segment) => EXCLUDED_SEGMENTS.has(segment.toLowerCase()))
    || /\.(spec|test|stories)\.(vue|ts|tsx|js|jsx)$/i.test(base)
    || base.startsWith('~$')
}

function walkFiles(root, extension) {
  const found = []
  const stack = [root]
  while (stack.length) {
    const current = stack.pop()
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const absolute = path.join(current, entry.name)
      const relative = path.relative(root, absolute)
      if (isExcluded(relative)) continue
      if (entry.isDirectory()) stack.push(absolute)
      else if (entry.isFile() && entry.name.endsWith(extension)) found.push(absolute)
    }
  }
  return found.sort((a, b) => toPosix(a).localeCompare(toPosix(b), 'en'))
}

function resolveLocalImport(repoRoot, importer, source) {
  if (typeof source !== 'string') return null
  let candidate
  if (source.startsWith('@/')) {
    candidate = path.join(repoRoot, 'audit-platform', 'frontend', 'src', source.slice(2))
  } else if (source.startsWith('.')) {
    candidate = path.resolve(path.dirname(importer), source)
  } else {
    return null
  }
  const candidates = [
    candidate,
    `${candidate}.vue`,
    `${candidate}.ts`,
    `${candidate}.tsx`,
    path.join(candidate, 'index.vue'),
    path.join(candidate, 'index.ts'),
  ]
  const hit = candidates.find((item) => fs.existsSync(item) && fs.statSync(item).isFile())
  return hit ? toPosix(path.relative(repoRoot, hit)) : toPosix(path.relative(repoRoot, candidate))
}

function traverseAst(node, visitor, seen = new Set()) {
  if (!node || typeof node !== 'object' || seen.has(node)) return
  seen.add(node)
  visitor(node)
  for (const [key, value] of Object.entries(node)) {
    if (key === 'parent' || key === 'tokens' || key === 'comments') continue
    if (Array.isArray(value)) {
      for (const child of value) traverseAst(child, visitor, seen)
    } else if (value && typeof value === 'object' && typeof value.type === 'string') {
      traverseAst(value, visitor, seen)
    }
  }
}

function importSourceFromNode(node) {
  let source = null
  traverseAst(node, (candidate) => {
    if (source !== null) return
    if (candidate.type === 'ImportExpression' && typeof candidate.source?.value === 'string') {
      source = candidate.source.value
    } else if (
      candidate.type === 'CallExpression'
      && candidate.callee?.type === 'Import'
      && typeof candidate.arguments?.[0]?.value === 'string'
    ) {
      source = candidate.arguments[0].value
    }
  })
  return source
}

function collectBindings(repoRoot, file, scriptAst) {
  const bindings = new Map()
  for (const statement of scriptAst?.body || []) {
    if (statement.type === 'ImportDeclaration' && typeof statement.source?.value === 'string') {
      const resolved = resolveLocalImport(repoRoot, file, statement.source.value)
      const target = [...TARGETS.values()].find((item) => item.canonicalFile === resolved)
      if (!target) continue
      for (const specifier of statement.specifiers || []) {
        if (specifier.local?.name) bindings.set(normalizeComponentName(specifier.local.name), {
          ...target,
          importKind: 'static',
          localName: specifier.local.name,
        })
      }
    }
  }

  traverseAst(scriptAst, (node) => {
    if (node.type !== 'VariableDeclarator' || node.id?.type !== 'Identifier' || !node.init) return
    const source = importSourceFromNode(node.init)
    if (!source) return
    const resolved = resolveLocalImport(repoRoot, file, source)
    const target = [...TARGETS.values()].find((item) => item.canonicalFile === resolved)
    if (!target) return
    bindings.set(normalizeComponentName(node.id.name), {
      ...target,
      importKind: 'dynamic',
      localName: node.id.name,
    })
  })
  return bindings
}

function attributeFact(attribute, sourceText) {
  const raw = sourceText.slice(attribute.range[0], attribute.range[1])
  if (!attribute.directive) {
    return {
      kind: 'attribute',
      name: attribute.key?.name || '',
      argument: null,
      expression: attribute.value?.value ?? null,
      raw,
    }
  }
  const directiveName = attribute.key?.name?.name || ''
  const argument = attribute.key?.argument?.name
    || attribute.key?.argument?.value
    || null
  const expression = attribute.value?.expression?.range
    ? sourceText.slice(attribute.value.expression.range[0], attribute.value.expression.range[1])
    : attribute.value?.value ?? null
  return {
    kind: 'directive',
    name: directiveName,
    argument,
    expression,
    raw,
  }
}

function findAttribute(attributes, predicate) {
  return attributes.find(predicate) || null
}

function mountId(fact) {
  const identity = [
    fact.file,
    fact.component,
    fact.templateNodeOrdinal,
    fact.sheetExpression || '',
    fact.wpExpression || '',
  ].join('|')
  return `mount_${crypto.createHash('sha256').update(identity).digest('hex').slice(0, 20)}`
}

function discoverVueFile(repoRoot, file) {
  const sourceText = fs.readFileSync(file, 'utf8')
  let parsed
  try {
    parsed = vueParser.parseForESLint(sourceText, {
      filePath: file,
      parser: tsParser,
      sourceType: 'module',
      ecmaVersion: 'latest',
      loc: true,
      range: true,
      comment: true,
    })
  } catch (error) {
    throw new Error(`${toPosix(path.relative(repoRoot, file))}: Vue AST parse failed: ${error.message}`)
  }

  const relative = toPosix(path.relative(repoRoot, file))
  const bindings = collectBindings(repoRoot, file, parsed.ast)
  const mounts = []
  let ordinal = 0

  function visitElement(element) {
    if (!element || element.type !== 'VElement') return
    ordinal += 1
    const rawName = element.rawName || element.name || ''
    const normalized = normalizeComponentName(rawName)
    const binding = bindings.get(normalized)
    const directTarget = TARGETS.get(normalized)
    const target = binding || (directTarget ? { ...directTarget, importKind: 'global-auto', localName: rawName } : null)
    if (target) {
      const attributes = (element.startTag?.attributes || []).map((item) => attributeFact(item, sourceText))
      const condition = findAttribute(attributes, (item) => item.kind === 'directive' && ['if', 'else-if', 'else'].includes(item.name))
      const loop = findAttribute(attributes, (item) => item.kind === 'directive' && item.name === 'for')
      const sheet = findAttribute(attributes, (item) => {
        const name = String(item.argument || item.name || '').toLowerCase()
        return name === 'sheet-name' || name === 'sheetname'
      })
      const wp = findAttribute(attributes, (item) => {
        const name = String(item.argument || item.name || '').toLowerCase()
        return name === 'wp-id' || name === 'wpid'
      })
      const fact = {
        mountId: '',
        file: relative,
        component: target.component,
        canonicalComponentFile: target.canonicalFile,
        documentType: target.documentType,
        localName: target.localName,
        importKind: target.importKind,
        templateNodeOrdinal: ordinal,
        sourceSpan: {
          startLine: element.loc.start.line,
          startColumn: element.loc.start.column + 1,
          endLine: element.loc.end.line,
          endColumn: element.loc.end.column + 1,
        },
        condition: condition?.raw || null,
        loop: loop?.raw || null,
        wpExpression: wp?.raw || null,
        sheetExpression: sheet?.raw || null,
        attributes,
        runtimeCardinality: loop ? 'dynamic' : 'single',
        sourceKind: 'template_ast',
      }
      fact.mountId = mountId(fact)
      mounts.push(fact)
    }
    for (const child of element.children || []) {
      if (child.type === 'VElement') visitElement(child)
      else if (child.type === 'VForExpression') {
        for (const nested of child.children || []) if (nested.type === 'VElement') visitElement(nested)
      }
    }
  }

  for (const child of parsed.services?.getTemplateBodyTokenStore && parsed.ast.templateBody?.children || []) {
    if (child.type === 'VElement') visitElement(child)
  }
  return mounts
}

function registryWordMount(repoRoot) {
  const registryRelative = 'audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts'
  const rendererRelative = 'audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue'
  const registryFile = path.join(repoRoot, ...registryRelative.split('/'))
  const rendererFile = path.join(repoRoot, ...rendererRelative.split('/'))
  const registry = fs.readFileSync(registryFile, 'utf8')
  const renderer = fs.readFileSync(rendererFile, 'utf8')
  const importMatch = /const\s+(\w+)\s*=\s*defineAsyncComponent\(\(\)\s*=>\s*import\(['"]\.\/WorkpaperWordEditor\.vue['"]\)\)/.exec(registry)
  if (!importMatch) throw new Error('htmlRendererRegistry.ts 未找到 WorkpaperWordEditor lazy import')
  const localName = importMatch[1]
  const registration = new RegExp(`componentType:\\s*['"]word-template['"][\\s\\S]{0,500}?component:\\s*${localName}\\b`).exec(registry)
  if (!registration) throw new Error('word-template 未绑定 WorkpaperWordEditor')
  const dynamicMount = /<component\b[\s\S]*?:is=["']rendererEntry\.component["'][\s\S]*?>/.exec(renderer)
  if (!dynamicMount) throw new Error('GtWpRenderer.vue 未找到 rendererEntry.component 动态挂载')
  const registryLine = registry.slice(0, importMatch.index).split(/\r?\n/).length
  const rendererLine = renderer.slice(0, dynamicMount.index).split(/\r?\n/).length
  const fact = {
    mountId: '',
    file: rendererRelative,
    component: 'WorkpaperWordEditor',
    canonicalComponentFile: 'audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue',
    documentType: 'docx',
    localName,
    importKind: 'registry-dynamic',
    templateNodeOrdinal: 0,
    sourceSpan: {
      startLine: rendererLine,
      startColumn: 1,
      endLine: rendererLine,
      endColumn: 1,
    },
    condition: "componentType === 'word-template' via HTML_RENDERER_REGISTRY",
    loop: null,
    wpExpression: ':wp-id="wpId"',
    sheetExpression: ':sheet-name="activeSheetName"',
    attributes: [],
    runtimeCardinality: 'dynamic',
    sourceKind: 'registry_ast',
    registryEvidence: {
      file: registryRelative,
      line: registryLine,
      componentType: 'word-template',
    },
  }
  fact.mountId = mountId(fact)
  return fact
}

function discover() {
  const repoRoot = findRepoRoot()
  const srcRoot = path.join(repoRoot, 'audit-platform', 'frontend', 'src')
  const mounts = []
  for (const file of walkFiles(srcRoot, '.vue')) mounts.push(...discoverVueFile(repoRoot, file))
  const dispatchers = [registryWordMount(repoRoot)]
  mounts.sort((a, b) => (
    a.file.localeCompare(b.file, 'en')
    || a.sourceSpan.startLine - b.sourceSpan.startLine
    || a.component.localeCompare(b.component, 'en')
  ))
  const duplicateIds = mounts.filter((item, index) => mounts.findIndex((candidate) => candidate.mountId === item.mountId) !== index)
  if (duplicateIds.length) throw new Error(`mount_id collision: ${duplicateIds.map((item) => item.mountId).join(', ')}`)
  const sourceDigest = crypto.createHash('sha256').update(JSON.stringify({ mounts, dispatchers })).digest('hex')
  return {
    schemaVersion: 1,
    sourceDigest,
    mounts,
    dispatchers,
    stats: {
      hostCount: new Set(mounts.map((item) => item.file)).size,
      mountCount: mounts.length,
      byComponent: Object.fromEntries(
        [...TARGETS.values()].map((target) => [
          target.component,
          mounts.filter((item) => item.component === target.component).length,
        ]),
      ),
    },
  }
}

function main() {
  const args = new Set(process.argv.slice(2))
  if (!args.has('--json') && !args.has('--summary')) {
    console.error('usage: discover-workpaper-sync-mounts.mjs --json | --summary')
    return 2
  }
  const result = discover()
  if (args.has('--summary')) {
    console.log(JSON.stringify({ sourceDigest: result.sourceDigest, ...result.stats }, null, 2))
  } else {
    process.stdout.write(`${JSON.stringify(result)}\n`)
  }
  return 0
}

try {
  process.exitCode = main()
} catch (error) {
  console.error(`[FAIL] ${error.stack || error.message}`)
  process.exitCode = 1
}
