/**
 * 全局组件接入率盘点脚本 [R7-S3-01 Task 8]
 * 一次性使用，输出 views/ 下每个 .vue 文件的组件接入情况。
 *
 * 用法：node scripts/audit-component-adoption.mjs
 */
import { readdirSync, readFileSync } from 'fs'
import { join } from 'path'

const VIEWS_DIR = 'audit-platform/frontend/src/views'
const COMPONENTS = ['GtPageHeader', 'GtToolbar', 'GtInfoBar', 'GtAmountCell', 'GtStatusTag', 'GtEditableTable']

function scanDir(dir) {
  const results = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      results.push(...scanDir(join(dir, entry.name)))
    } else if (entry.name.endsWith('.vue')) {
      results.push(join(dir, entry.name))
    }
  }
  return results
}

const files = scanDir(VIEWS_DIR)
const rows = []

for (const file of files) {
  const content = readFileSync(file, 'utf-8')
  const row = { file: file.replace(VIEWS_DIR + '/', '') }
  for (const comp of COMPONENTS) {
    row[comp] = content.includes(comp) ? '✅' : '—'
  }
  rows.push(row)
}

// 统计
const totals = {}
for (const comp of COMPONENTS) {
  totals[comp] = rows.filter(r => r[comp] === '✅').length
}

console.log(`\n📊 全局组件接入率盘点（${files.length} 个视图）\n`)
console.log('| 视图 | ' + COMPONENTS.join(' | ') + ' |')
console.log('|------|' + COMPONENTS.map(() => '---').join('|') + '|')
for (const row of rows) {
  console.log(`| ${row.file} | ${COMPONENTS.map(c => row[c]).join(' | ')} |`)
}
console.log('')
console.log('| **合计** | ' + COMPONENTS.map(c => `**${totals[c]}/${files.length}**`).join(' | ') + ' |')
console.log('')
