#!/usr/bin/env node
/**
 * ElMessage.error 分层审计脚本
 *
 * 用 @typescript-eslint/parser AST 判断每处 ElMessage.error 是否在 CatchClause 祖先链内。
 * 输出两类清单：
 *   Category 1 (catch 块内裸用 — 待替换为 handleApiError)
 *   Category 2 (业务校验 — 保留)
 *
 * 检测模式：
 *   - ElMessage.error('...')
 *   - ElMessage.error({ message: '...' })
 *   - ElMessage({ type: 'error', message: '...' })
 *   - .catch(err => { ElMessage.error(...) })
 *
 * Requirements: 4.1, 4.3
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'
import { glob } from 'glob'

const require = createRequire(import.meta.url)
const tsParser = require('@typescript-eslint/parser')

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const ROOT = path.resolve(__dirname, '..')
const SRC = path.join(ROOT, 'src')

// ─── Helpers ───────────────────────────────────────────────────────────────

/**
 * Extract <script> or <script setup> content from a .vue file.
 * Returns { code, startLine } where startLine is the 1-based line offset.
 */
function extractScriptBlock(content) {
  // Match <script ...> or <script setup ...>
  const re = /<script\b[^>]*>([\s\S]*?)<\/script>/gi
  let match
  let best = null
  while ((match = re.exec(content)) !== null) {
    const tag = match[0].slice(0, match[0].indexOf('>') + 1)
    // Prefer <script setup> over plain <script>
    const isSetup = /\bsetup\b/.test(tag)
    const code = match[1]
    const startLine = content.slice(0, match.index + tag.length).split('\n').length
    if (!best || isSetup) {
      best = { code, startLine, isSetup }
    }
  }
  // If we found a setup script, also check for a plain script block (both can coexist)
  // We want to scan BOTH blocks
  const blocks = []
  re.lastIndex = 0
  while ((match = re.exec(content)) !== null) {
    const tag = match[0].slice(0, match[0].indexOf('>') + 1)
    const code = match[1]
    const startLine = content.slice(0, match.index + tag.length).split('\n').length
    blocks.push({ code, startLine })
  }
  return blocks
}

/**
 * Parse TypeScript/JavaScript code using @typescript-eslint/parser.
 * Returns the AST or null on parse failure.
 */
function parseCode(code, filePath) {
  try {
    return tsParser.parse(code, {
      loc: true,
      range: true,
      jsx: true,
      ecmaFeatures: { jsx: true },
      sourceType: 'module',
    })
  } catch (e) {
    // Silently skip unparseable files
    return null
  }
}

/**
 * Walk AST nodes depth-first, calling visitor(node, ancestors).
 */
function walkAST(node, visitor, ancestors = []) {
  if (!node || typeof node !== 'object') return
  if (node.type) {
    visitor(node, ancestors)
    ancestors = [...ancestors, node]
  }
  for (const key of Object.keys(node)) {
    if (key === 'parent' || key === 'loc' || key === 'range') continue
    const child = node[key]
    if (Array.isArray(child)) {
      for (const item of child) {
        if (item && typeof item === 'object' && item.type) {
          walkAST(item, visitor, ancestors)
        }
      }
    } else if (child && typeof child === 'object' && child.type) {
      walkAST(child, visitor, ancestors)
    }
  }
}

/**
 * Check if a CallExpression node is an ElMessage.error call.
 * Patterns:
 *   - ElMessage.error(...)
 *   - ElMessage({ type: 'error', ... })
 */
function isElMessageErrorCall(node) {
  if (node.type !== 'CallExpression') return false

  const callee = node.callee

  // Pattern 1: ElMessage.error(...)
  if (
    callee.type === 'MemberExpression' &&
    callee.object.type === 'Identifier' &&
    callee.object.name === 'ElMessage' &&
    callee.property.type === 'Identifier' &&
    callee.property.name === 'error'
  ) {
    return true
  }

  // Pattern 2: ElMessage({ type: 'error', ... })
  if (
    callee.type === 'Identifier' &&
    callee.name === 'ElMessage' &&
    node.arguments.length > 0
  ) {
    const arg = node.arguments[0]
    if (arg.type === 'ObjectExpression') {
      for (const prop of arg.properties) {
        if (
          prop.type === 'Property' &&
          prop.key.type === 'Identifier' &&
          prop.key.name === 'type' &&
          prop.value.type === 'Literal' &&
          prop.value.value === 'error'
        ) {
          return true
        }
      }
    }
  }

  return false
}

/**
 * Check if any ancestor is a CatchClause or a .catch() callback.
 */
function isInCatchContext(ancestors) {
  for (let i = ancestors.length - 1; i >= 0; i--) {
    const anc = ancestors[i]

    // Direct CatchClause (try/catch)
    if (anc.type === 'CatchClause') {
      return true
    }

    // .catch(callback) pattern:
    // The ancestor chain would have a CallExpression whose callee is a MemberExpression
    // with property.name === 'catch', and the current node is inside the callback argument.
    if (anc.type === 'CallExpression') {
      const callee = anc.callee
      if (
        callee &&
        callee.type === 'MemberExpression' &&
        callee.property &&
        callee.property.type === 'Identifier' &&
        callee.property.name === 'catch'
      ) {
        // Check that we're inside one of the arguments (the callback)
        // Since we're walking ancestors, if we're inside the .catch() call's arguments,
        // the next ancestors after this CallExpression would be the callback function body
        return true
      }
    }
  }
  return false
}

// ─── Main ──────────────────────────────────────────────────────────────────

async function main() {
  const patterns = ['src/**/*.vue', 'src/**/*.ts']
  const excludeRe = /(__tests__|\.test\.|\.spec\.|\.stories\.|node_modules|\.storybook|\.d\.ts$)/

  const files = []
  for (const p of patterns) {
    const matches = await glob(p, { cwd: ROOT, absolute: true })
    files.push(...matches.filter((f) => !excludeRe.test(f)))
  }

  const category1 = [] // catch 块内裸用
  const category2 = [] // 业务校验

  let filesScanned = 0
  let parseErrors = 0

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8')
    const rel = path.relative(SRC, file).replace(/\\/g, '/')

    // Quick check: does file contain ElMessage?
    if (!content.includes('ElMessage')) continue

    filesScanned++

    const isVue = file.endsWith('.vue')
    let blocks

    if (isVue) {
      blocks = extractScriptBlock(content)
      if (blocks.length === 0) continue
    } else {
      blocks = [{ code: content, startLine: 1 }]
    }

    for (const block of blocks) {
      const ast = parseCode(block.code, file)
      if (!ast) {
        parseErrors++
        continue
      }

      walkAST(ast, (node, ancestors) => {
        if (!isElMessageErrorCall(node)) return

        const line = (node.loc?.start?.line || 0) + block.startLine - 1
        const entry = { file: `src/${rel}`, line }

        if (isInCatchContext(ancestors)) {
          category1.push(entry)
        } else {
          category2.push(entry)
        }
      })
    }
  }

  // ─── Output ────────────────────────────────────────────────────────────────

  console.log('')
  console.log('=== ElMessage.error 分层审计结果 ===')
  console.log(`Category 1 (catch 块内裸用 — 待替换): ${category1.length} 处`)
  console.log(`Category 2 (业务校验 — 保留): ${category2.length} 处`)
  console.log(`Total: ${category1.length + category2.length} 处`)
  console.log('')
  console.log(`扫描文件数: ${filesScanned}，解析失败: ${parseErrors}`)
  console.log('')

  if (category1.length > 0) {
    console.log('--- Category 1 详细清单 (catch 块内裸用 — 待替换) ---')
    for (const entry of category1.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line)) {
      console.log(`${entry.file}:${entry.line}`)
    }
    console.log('')
  }

  if (category2.length > 0) {
    console.log('--- Category 2 详细清单 (业务校验 — 保留) ---')
    for (const entry of category2.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line)) {
      console.log(`${entry.file}:${entry.line}`)
    }
    console.log('')
  }

  // Summary for CI
  console.log(`CATCH_BARE_COUNT=${category1.length}`)
  console.log(`BUSINESS_VALIDATION_COUNT=${category2.length}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
