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
  // 🔴 真双向载体。spec: sync-editor-host-discovery-contract-closure
  //
  // 它此前**不在**白名单里，后果是：宿主一旦完成双向迁移、删掉 legacy 标签，
  // 它在 manifest 里的 entry 就直接不存在（entry 只能由发现到的挂点派生）。
  // 迁移越彻底越早消失 —— 34 个 `d4/**` tab 已真实消失过，17 个 A 类随后消失。
  //
  // `documentType: null` 是**刻意的**：本组件的 props 只有 `descriptor`/`bridge`，
  // 不带 wp-id / sheet-name / 文档类型，且它同时服务 Excel 与 Word
  // （见 WorkpaperSyncEditorHost.vue 首行注释）⇒ 文档类型无法从挂点自身推出，
  // 必须由 `resolveSyncHostIdentity()` 的 L1/L2 或后端 overlay 的 L3 规则给出。
  // **禁止**在这里填一个默认值（例如 'xlsx'）：现算 96/96 确实都是 xlsx，
  // 但默认值会让第一个 docx 迁移宿主**静默**落到错误的 document_type。
  ['workpapersynceditorhost', {
    component: 'WorkpaperSyncEditorHost',
    canonicalFile: 'audit-platform/frontend/src/components/workpaper/sync/WorkpaperSyncEditorHost.vue',
    documentType: null,
  }],
])

/** 文档类型固定的组件（= 可作为 L1 兄弟信号的来源）。 */
const FIXED_DOCUMENT_TYPE_COMPONENTS = new Set(
  [...TARGETS.values()].filter((item) => item.documentType !== null).map((item) => item.component),
)

/** 需要靠解析链给出文档类型的组件。 */
const DEFERRED_DOCUMENT_TYPE_COMPONENTS = new Set(
  [...TARGETS.values()].filter((item) => item.documentType === null).map((item) => item.component),
)

/** L2 信号的取值形态：`{xlsx|docx}/…`（与后端 `_entry_id` 的产出同形）。 */
const SYNC_ENTRY_ID_LITERAL = /^(?:xlsx|docx)\/[A-Za-z0-9][A-Za-z0-9/_-]*$/

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
  //: L2 信号：模板里 `entry-id="{xlsx|docx}/…"` 的**静态字面量**。
  //  读的是 AST 的属性节点（与读 `sheet-name` 完全同构）⇒ 注释里的同形文字不进 AST，
  //  天然排除；也**不做跨文件闭包扫描** —— 实测有宿主 import 的共享模块里列了 51 个
  //  entry_id 字面量，按「任意字符串字面量」取会得到无法判定的集合。
  const entryIdDeclarations = []
  let ordinal = 0

  function visitElement(element) {
    if (!element || element.type !== 'VElement') return
    ordinal += 1
    const rawName = element.rawName || element.name || ''
    const normalized = normalizeComponentName(rawName)
    for (const attribute of element.startTag?.attributes || []) {
      // 静态属性：key.name 是字符串 'entry-id'，value 是 VLiteral
      const key = attribute.key
      const isStatic = attribute.directive !== true && String(key?.name || '') === 'entry-id'
      const literal = attribute.value
      if (isStatic && literal && typeof literal.value === 'string'
          && SYNC_ENTRY_ID_LITERAL.test(literal.value)) {
        entryIdDeclarations.push(literal.value)
      }
    }
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
  resolveSyncHostIdentity(relative, mounts, entryIdDeclarations)
  return mounts
}

/**
 * 给文档类型待定的挂点（`WorkpaperSyncEditorHost`）解析身份。
 * spec: sync-editor-host-discovery-contract-closure · Requirement 2
 *
 * 必须在**同一文件的全部挂点收集完之后**调用 —— L1 依赖兄弟挂点。
 *
 * 层级严格 L1 → L2，**没有第四层兜底**：两层都不成立就把 documentType 留 null 并标
 * `needsOverlayRule`，交后端 overlay 的 L3 reviewed 规则裁决；仍无规则则生成器 fail closed。
 *
 * 🔴 为什么不兜底成 'xlsx'：现算 96/96 都是 xlsx，所以兜底"今天是对的"。但第一个 docx
 * 宿主迁移时会**静默**落到 xlsx ⇒ entry_id 前缀错、与已交付契约失配，且无判据能看见。
 */
function resolveSyncHostIdentity(relative, mounts, entryIdDeclarations) {
  const deferred = mounts.filter((item) => DEFERRED_DOCUMENT_TYPE_COMPONENTS.has(item.component))
  if (!deferred.length) return

  // ── L1：同文件里文档类型固定的兄弟挂点
  const siblingTypes = [...new Set(
    mounts
      .filter((item) => FIXED_DOCUMENT_TYPE_COMPONENTS.has(item.component))
      .map((item) => item.documentType),
  )].sort()
  if (siblingTypes.length > 1) {
    throw new Error(
      `${relative}: sync host document type is ambiguous — sibling mounts declare ${JSON.stringify(siblingTypes)}; `
      + 'a reviewed overlay rule is required (Requirement 2.1)',
    )
  }

  // ── L2：同模板里 `entry-id` 的**静态字面量**（注释不进 AST，天然排除）
  const declared = [...new Set(entryIdDeclarations)].sort()
  if (declared.length > 1) {
    throw new Error(
      `${relative}: sync host identity is ambiguous — template declares ${JSON.stringify(declared)}; `
      + 'exactly one static entry-id literal is required (Requirement 2.2)',
    )
  }

  // ── 交叉校验：两层都有信号时文档类型必须一致（独立来源，互不依赖）
  if (siblingTypes.length === 1 && declared.length === 1) {
    const declaredType = declared[0].split('/')[0]
    if (declaredType !== siblingTypes[0]) {
      throw new Error(
        `${relative}: document type conflict — sibling mounts say '${siblingTypes[0]}' but the `
        + `entry-id declaration '${declared[0]}' says '${declaredType}' (Requirement 2.5)`,
      )
    }
  }

  for (const fact of deferred) {
    if (siblingTypes.length === 1) {
      fact.documentType = siblingTypes[0]
      fact.documentTypeSource = 'sibling_mount'
    } else if (declared.length === 1) {
      fact.documentType = declared[0].split('/')[0]
      fact.documentTypeSource = 'entry_id_declaration'
    } else {
      fact.documentType = null
      fact.documentTypeSource = null
    }
    fact.entryIdDeclaration = declared.length === 1 ? declared[0] : null
    fact.needsOverlayRule = fact.documentType === null
    // mountId 的输入里没有这些字段（见 mountId()），所以不必重算 —— 但显式记一笔：
    // 身份解析**不改变**挂点的 mount 身份，只补齐它的文档类型来源。
  }
}

function registryWordMount(repoRoot) {
  // htmlRendererRegistry.ts（commit 82f58ea44）已把集中式 defineAsyncComponent + 注册
  // 拆分到 registry/entries/*.ts 子模块。word-template 现以**内联**形态注册在其中一个子
  // 文件里：`componentType: 'word-template' … component: defineAsyncComponent(() =>
  //  import('…/WorkpaperWordEditor.vue'))`。扫全部 entries 子模块定位它，避免写死某一个
  // 子文件（未来再搬也不失配）。判据强度不弱化——仍三重校验：
  //   ① word-template 条目真实存在（内联 componentType）
  //   ② 该条目 component 绑定的正是 WorkpaperWordEditor.vue 的 lazy import
  //   ③ GtWpRenderer.vue 有 rendererEntry.component 动态挂载
  const entriesRelativeDir = 'audit-platform/frontend/src/components/workpaper/registry/entries'
  const rendererRelative = 'audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue'
  const entriesDir = path.join(repoRoot, ...entriesRelativeDir.split('/'))
  if (!fs.existsSync(entriesDir)) {
    throw new Error(`registry/entries 目录不存在（htmlRendererRegistry 拆分结构已变）: ${entriesRelativeDir}`)
  }
  // 内联注册块：componentType: 'word-template' 到其 component: defineAsyncComponent(import(...WorkpaperWordEditor.vue))
  const wordEntryRe = /componentType:\s*['"]word-template['"][\s\S]{0,300}?component:\s*defineAsyncComponent\(\(\)\s*=>\s*import\(['"][^'"]*\/WorkpaperWordEditor\.vue['"]\)\)/
  let registryRelative = null
  let registryLine = 0
  for (const name of fs.readdirSync(entriesDir).filter((f) => f.endsWith('.ts')).sort()) {
    const filePath = path.join(entriesDir, name)
    const text = fs.readFileSync(filePath, 'utf8')
    const hit = wordEntryRe.exec(text)
    if (hit) {
      registryRelative = `${entriesRelativeDir}/${name}`
      registryLine = text.slice(0, hit.index).split(/\r?\n/).length
      break
    }
  }
  if (!registryRelative) {
    throw new Error("registry/entries/*.ts 未找到 word-template 绑定 WorkpaperWordEditor 的内联注册")
  }
  const rendererFile = path.join(repoRoot, ...rendererRelative.split('/'))
  const renderer = fs.readFileSync(rendererFile, 'utf8')
  const dynamicMount = /<component\b[\s\S]*?:is=["']rendererEntry\.component["'][\s\S]*?>/.exec(renderer)
  if (!dynamicMount) throw new Error('GtWpRenderer.vue 未找到 rendererEntry.component 动态挂载')
  const localName = 'WorkpaperWordEditor'
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
