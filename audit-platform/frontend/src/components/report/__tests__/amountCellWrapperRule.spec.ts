/**
 * ESLint 规则 gt-audit/no-bare-amount-cell 的「金额格包装组件」登记（spec excel-style-table-editing 5.4 收尾）。
 *
 * 原状（可打红）：权益变动表 / 资产减值准备表的金额格从 `<GtAmountCell>` 改成 `<ReportMatrixCell>`（平时显示
 * GtAmountCell、可编辑时格内编辑）后，规则在列模板里看不到 GtAmountCell，报 22 条「金额列裸用」——
 * CI「V3 GtAmountCell coverage guard」按只减不增卡这个数。规则现在认登记的包装组件；登记是可伪证声明：
 * 每个登记的组件模板里必须真有 `<GtAmountCell>`，否则本守卫打红。
 */
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

const FRONT = resolve(__dirname, '../../../..')
const nodeRequire = createRequire(resolve(FRONT, 'package.json'))
const rule = nodeRequire('./eslint-rules/no-bare-amount-cell.cjs')
const { Linter } = nodeRequire('eslint')
const vueParser = nodeRequire('vue-eslint-parser')
const tsParser = nodeRequire('@typescript-eslint/parser')

const RULE_ID = 'gt-audit/no-bare-amount-cell'

function lint(code: string, filename = 'X.vue'): number {
  const linter = new Linter()
  linter.defineParser('vue-eslint-parser', vueParser)
  linter.defineRule(RULE_ID, rule)
  // 与 .eslintrc.cjs 同口径：<script setup lang="ts"> 交给 @typescript-eslint/parser
  const messages = linter.verify(code, {
    parser: 'vue-eslint-parser',
    parserOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module' },
    rules: { [RULE_ID]: 'error' },
  }, { filename })
  const fatal = messages.filter((m: { fatal?: boolean }) => m.fatal)
  if (fatal.length) throw new Error(`解析失败：${fatal.map((m: { message: string }) => m.message).join('; ')}`)
  return messages.filter((m: { ruleId: string | null }) => m.ruleId === RULE_ID).length
}

const src = (rel: string) => readFileSync(resolve(FRONT, 'src', rel), 'utf-8')

const column = (inner: string) => `<template><el-table :data="rows">
  <el-table-column prop="closing_balance" label="期末余额" align="right">
    <template #default="{ row }">${inner}</template>
  </el-table-column>
</el-table></template>`

describe('no-bare-amount-cell：金额格包装组件', () => {
  it('登记的包装组件模板里确有 <GtAmountCell>（登记是可伪证声明）', () => {
    const wrappers = Object.entries(rule.AMOUNT_CELL_WRAPPERS as Record<string, string>)
    expect(wrappers.length).toBeGreaterThan(0)
    for (const [name, file] of wrappers) {
      const { descriptor } = parse(src(file), { filename: file })
      expect(descriptor.template, `${name}（${file}）没有模板`).toBeTruthy()
      expect(descriptor.template!.content, `${name} 的模板里没有 <GtAmountCell>`).toMatch(/<GtAmountCell[\s/>]/)
    }
  })

  it('列里用包装组件不报，裸文字照报（PascalCase 与 kebab-case 同样认）', () => {
    expect(lint(column('<ReportMatrixCell :value="row.closing_balance" />'))).toBe(0)
    expect(lint(column('<report-matrix-cell :value="row.closing_balance" />'))).toBe(0)
    expect(lint(column('<GtAmountCell :value="row.closing_balance" />'))).toBe(0)
    expect(lint(column('<span>{{ row.closing_balance }}</span>'))).toBe(1)
    expect(lint(column('<OtherMatrixCell :value="row.closing_balance" />'))).toBe(1)
  })

  it('权益变动表 / 资产减值准备表 0 条；把包装组件换个名字，同一文件即报（守卫不空转）', () => {
    for (const [file, expected] of [['components/report/ReportEquityTable.vue', 20], ['components/report/ReportImpairmentTable.vue', 2]] as const) {
      const text = src(file)
      expect(lint(text, file), file).toBe(0)
      expect(text).toContain('<ReportMatrixCell')
      expect(lint(text.replace(/<ReportMatrixCell\b/g, '<UnregisteredMatrixCell'), file), `${file} 换名后`).toBe(expected)
    }
  })
})
