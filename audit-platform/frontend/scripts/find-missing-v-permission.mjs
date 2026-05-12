/**
 * find-missing-v-permission.mjs — 盘点未加 v-permission 的危险操作按钮
 *
 * 扫描 src/{views,components}/**//*.vue 文件中 @click 指向危险动作
 * （删除/审批/签字/归档/催办/导出/转错报/撤销等）但未加 v-permission
 * 指令的按钮，输出警告列表。
 *
 * 用法：node scripts/find-missing-v-permission.mjs
 */
import { readFileSync } from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { globSync } from 'glob'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '../src')

// 危险动作关键词（处理函数名驼峰）
const DANGER_PATTERNS = [
  /@click[^>]*=['"][^'"]*on(Delete|Remove)\b/i,
  /@click[^>]*=['"][^'"]*on(Approve|Reject|Review)\b/i,
  /@click[^>]*=['"][^'"]*on(Sign|Archive|Unlock)\b/i,
  /@click[^>]*=['"][^'"]*on(Escalate|Remind)\b/i,
  /@click[^>]*=['"][^'"]*on(Export|Publish|Finalize)\b/i,
  /@click[^>]*=['"][^'"]*on(Convert|Revoke|Rollback)\b/i,
  /@click[^>]*=['"][^'"]*on(ForcePass|BatchAssign)\b/i,
  // R9 新增：直接函数名模式（不带 on 前缀）
  /@click[^>]*=['"]delete\b/i,
  /@click[^>]*=['"]archive\b/i,
  /@click[^>]*=['"]sign\b/i,
  /@click[^>]*=['"]export\b/i,
  // R9 新增：含 handleXxx 模式
  /@click[^>]*=['"][^'"]*handle(Delete|Archive|Sign|Export)\b/i,
  // R9 新增：含 doXxx 模式
  /@click[^>]*=['"][^'"]*do(Delete|Archive|Sign|Export)\b/i,
]

const files = globSync('{views,components}/**/*.vue', { cwd: ROOT, absolute: true })

const issues = []

for (const abs of files) {
  const content = readFileSync(abs, 'utf-8')
  const lines = content.split('\n')
  const rel = path.relative(ROOT, abs).replace(/\\/g, '/')

  // 找 <template> 段（可能在文件任意位置，但通常是开头）
  const tplStart = lines.findIndex((l) => l.trim().startsWith('<template'))
  const tplEnd = lines.findIndex((l) => l.trim().startsWith('</template>'))
  if (tplStart === -1 || tplEnd === -1) continue

  // 按 <el-button> 元素切分
  let inButton = false
  let buttonStart = -1
  let buttonLines = []

  for (let i = tplStart; i <= tplEnd; i++) {
    const line = lines[i]
    if (!inButton && line.match(/<el-button\b/)) {
      buttonStart = i
      inButton = true
      buttonLines = [line]
      if (line.match(/\/>/) || line.match(/<\/el-button>/)) {
        checkButton(rel, buttonStart, buttonLines)
        inButton = false
        buttonLines = []
      }
      continue
    }
    if (inButton) {
      buttonLines.push(line)
      if (line.match(/<\/el-button>/) || line.match(/\/>$/) || (!line.includes('=') && line.match(/>$/))) {
        checkButton(rel, buttonStart, buttonLines)
        inButton = false
        buttonLines = []
      }
    }
  }
}

function checkButton(file, startLine, buttonLines) {
  const buttonText = buttonLines.join(' ')
  const matched = DANGER_PATTERNS.find((p) => p.test(buttonText))
  if (!matched) return
  // 跳过已有权限控制的按钮
  if (buttonText.includes('v-permission')) return
  // 跳过模板中的 disabled 已间接控制的按钮（启发式：含 v-if 限制角色可忽略）
  const clickMatch = buttonText.match(/@click[^="]*=['"]([^'"]+)['"]/)
  const clickHandler = clickMatch ? clickMatch[1] : '?'
  issues.push({
    file,
    line: startLine + 1,
    handler: clickHandler,
  })
}

if (issues.length === 0) {
  console.log('OK: all dangerous action buttons have v-permission')
  process.exit(0)
}

console.log(`WARN: ${issues.length} dangerous action buttons missing v-permission:`)
console.log('')
const byFile = {}
for (const issue of issues) {
  if (!byFile[issue.file]) byFile[issue.file] = []
  byFile[issue.file].push(issue)
}
for (const [file, list] of Object.entries(byFile)) {
  console.log(`\n[${file}]`)
  for (const issue of list) {
    console.log(`   line ${issue.line}: @click="${issue.handler}"`)
  }
}
// 不 fail（仅警告），纳入基线后可在 CI 中收紧
process.exit(0)
