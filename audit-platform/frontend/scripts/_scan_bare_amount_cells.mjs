#!/usr/bin/env node
/**
 * 一次性扫描脚本：找出所有「裸金额单元格」 el-table-column 命中
 *
 * V3 Spec Req 8.1.1
 *
 * 检测规则：
 *   命中条件 = align="right" + (prop 命中金额关键字 OR label 含中文金额关键字)
 *              + 子树内未使用 GtAmountCell / gt-amount-cell / g-t-amount-cell
 *
 * 输出：
 *   - bare_amount_cells.report.txt（按文件聚合 + 总数 + Top 命中视图）
 *   - 终端打印总数 + Top 10 视图
 *
 * 实现策略：纯正则扫描（不依赖 vue-eslint-parser AST 复杂度），
 *   只为 baseline 出数 + 视图清单，不追求 100% 准确率。
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { glob } from 'glob'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const ROOT = path.resolve(__dirname, '..')
const REPORT_FILE = path.join(ROOT, 'bare_amount_cells.report.txt')

// 金额关键字（prop / label 任一命中即视为金额列）
// 收紧策略：剔除 number/value/num/qty 等过于宽泛的关键字（容易把"总数/行数"等计数误判为金额）
const AMOUNT_PROP_RE = /(amount|balance|debit|credit|tax|cost|price|principal|interest|payable|receivable|salary|fund|equity|capital|fee|charge|discount|profit|loss|revenue|expense|income|net_asset|netasset)/i
const AMOUNT_LABEL_RE = /(金额|余额|借方|贷方|税金|税额|成本|价格|合计|小计|总计|总额|本金|利息|应付|应收|薪资|工资|股本|权益|费用|费率|折扣|损益|利润|亏损|收入|支出|资产|负债|净资产|股东|未分配|盈余)/

const GT_AMOUNT_RE = /(GtAmountCell|gt-amount-cell|g-t-amount-cell)/

// 排除路径（测试 / 内部 dev 工具）
const EXCLUDE_RE = /(__tests__|\.test\.|\.spec\.|\.stories\.|node_modules|\.storybook)/

/**
 * 提取一个 el-table-column 块的开始位置 + 结束位置 + 内部内容
 * 简化策略：通过括号嵌套深度找到匹配的关闭标签
 *
 * 返回: { start, end, openTag, body, isSelfClose }
 */
function findColumnBlocks(content) {
  const blocks = []
  // 匹配开标签
  const openRe = /<el-table-column\b([^>]*?)(\/?)>/g
  let m
  while ((m = openRe.exec(content)) !== null) {
    const start = m.index
    const openTag = m[0]
    const attrs = m[1]
    const isSelfClose = m[2] === '/'

    if (isSelfClose) {
      blocks.push({ start, end: openRe.lastIndex, openTag, body: '', attrs, isSelfClose })
      continue
    }

    // 找匹配的 </el-table-column>，需处理嵌套
    let depth = 1
    let i = openRe.lastIndex
    while (i < content.length && depth > 0) {
      const nextOpen = content.indexOf('<el-table-column', i)
      const nextClose = content.indexOf('</el-table-column>', i)
      if (nextClose === -1) break
      if (nextOpen !== -1 && nextOpen < nextClose) {
        // 内部还有嵌套，找其结束（粗略：匹配它的 > 然后判断是否 self-close）
        const innerOpenEnd = content.indexOf('>', nextOpen)
        if (innerOpenEnd === -1) break
        const innerOpenTag = content.slice(nextOpen, innerOpenEnd + 1)
        if (!innerOpenTag.endsWith('/>')) {
          depth++
        }
        i = innerOpenEnd + 1
      } else {
        depth--
        if (depth === 0) {
          const body = content.slice(openRe.lastIndex, nextClose)
          const end = nextClose + '</el-table-column>'.length
          blocks.push({ start, end, openTag, body, attrs, isSelfClose: false })
          i = end
          break
        }
        i = nextClose + '</el-table-column>'.length
      }
    }
  }
  return blocks
}

/**
 * 从开标签 attrs 字符串中提取 align / prop / label 的值
 * 支持 align="right" / :align="'right'" / label="金额"
 */
function extractAttr(attrs, name) {
  // 静态：name="value"
  let re = new RegExp(`(?:^|\\s)${name}\\s*=\\s*"([^"]*)"`, 'i')
  let m = attrs.match(re)
  if (m) return m[1]
  // 静态单引号
  re = new RegExp(`(?:^|\\s)${name}\\s*=\\s*'([^']*)'`, 'i')
  m = attrs.match(re)
  if (m) return m[1]
  // 动态：:name="'value'" — 仅取常量字符串
  re = new RegExp(`(?:^|\\s):${name}\\s*=\\s*"['\`]([^'\`]*)['\`]"`, 'i')
  m = attrs.match(re)
  if (m) return m[1]
  return null
}

/**
 * 检查 column 块是否命中"裸金额单元格"
 */
function isBareAmountColumn(block) {
  const align = extractAttr(block.attrs, 'align')
  const prop = extractAttr(block.attrs, 'prop')
  const label = extractAttr(block.attrs, 'label')

  // 必须 align="right"
  if (align !== 'right') return null

  // prop 或 label 命中金额关键字
  const propHit = prop && AMOUNT_PROP_RE.test(prop)
  const labelHit = label && AMOUNT_LABEL_RE.test(label)
  if (!propHit && !labelHit) return null

  // 已使用 GtAmountCell 子组件 → 跳过
  if (block.body && GT_AMOUNT_RE.test(block.body)) return null
  // 子组件命中其他金额展示组件（兜底）
  if (block.body && /(formatAmount|displayAmount|amountFormatter)/.test(block.body)) return null

  return { prop: prop || '(no-prop)', label: label || '(no-label)' }
}

async function main() {
  // 使用 glob v13 API（async）
  const patterns = ['src/views/**/*.vue', 'src/components/**/*.vue']
  const files = []
  for (const p of patterns) {
    const matches = await glob(p, { cwd: ROOT, absolute: true })
    files.push(...matches.filter((f) => !EXCLUDE_RE.test(f)))
  }

  const fileHits = new Map()  // file -> [{prop, label, line}]
  let totalHits = 0

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8')
    if (!/<el-table-column/.test(content)) continue

    const blocks = findColumnBlocks(content)
    for (const block of blocks) {
      const hit = isBareAmountColumn(block)
      if (!hit) continue

      // 行号
      const beforeStart = content.slice(0, block.start)
      const line = beforeStart.split('\n').length

      const rel = path.relative(ROOT, file).replace(/\\/g, '/')
      if (!fileHits.has(rel)) fileHits.set(rel, [])
      fileHits.get(rel).push({ ...hit, line })
      totalHits++
    }
  }

  // 排序：命中数倒序
  const sortedFiles = [...fileHits.entries()].sort((a, b) => b[1].length - a[1].length)

  // 写报告
  const lines = []
  lines.push('# 裸金额单元格扫描报告（V3 Req 8.1.1）')
  lines.push(`# 生成时间：${new Date().toISOString()}`)
  lines.push(`# 扫描范围：src/views/**/*.vue + src/components/**/*.vue`)
  lines.push(`# 排除：__tests__ / *.spec.* / *.test.* / *.stories.*`)
  lines.push('')
  lines.push(`总命中：${totalHits} 处`)
  lines.push(`命中文件数：${sortedFiles.length}`)
  lines.push('')
  lines.push('## Top 命中视图（命中数倒序）')
  lines.push('')
  for (const [rel, hits] of sortedFiles) {
    lines.push(`### ${rel}（${hits.length} 处）`)
    for (const h of hits) {
      lines.push(`  L${h.line}: prop=${h.prop}, label=${h.label}`)
    }
    lines.push('')
  }

  fs.writeFileSync(REPORT_FILE, lines.join('\n'), 'utf-8')

  // 终端输出
  console.log('')
  console.log(`[scan_bare_amount_cells] 总命中：${totalHits} 处，文件数：${sortedFiles.length}`)
  console.log('')
  console.log('Top 10 视图：')
  for (const [rel, hits] of sortedFiles.slice(0, 10)) {
    console.log(`  ${hits.length.toString().padStart(3)}  ${rel}`)
  }
  console.log('')
  console.log(`详细报告已写入：${path.relative(ROOT, REPORT_FILE)}`)
  console.log('')

  // 输出 baseline 数字给 CI 调用
  process.stdout.write(`BASELINE_NUM=${totalHits}\n`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
