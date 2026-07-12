// Feature: platform-global-hardening
// Validates: Requirements 4.6
//
// ESLint RuleTester 例集 — no-adhoc-wp-structure 规则
// 检测 3 种可用 Wp_Kit 组件的等价手写结构：
//   1. <el-input type="textarea" :autosize> → WpOpinionCard
//   2. <el-dropdown> 含"导入"+"导出" → WpImportExport
//   3. .toLocaleString() 模板表达式 → WpAmountCell
//
// 运行：node eslint-rules/__tests__/no-adhoc-wp-structure.test.cjs

'use strict'

const { RuleTester } = require('eslint')
const rule = require('../no-adhoc-wp-structure.cjs')

const ruleTester = new RuleTester({
  parser: require.resolve('vue-eslint-parser'),
  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'module',
  },
})

// 底稿路径（触发规则）
const WP_FILE = 'src/components/workpaper/d2/core/D2TabOpinion.vue'
// 非底稿路径（不触发规则）
const NON_WP_FILE = 'src/views/Settings.vue'

ruleTester.run('no-adhoc-wp-structure', rule, {
  valid: [
    // ─── Valid 1: 普通 el-input 无 autosize，不触发 ───
    {
      code: `<template><el-input type="textarea" placeholder="请输入"></el-input></template>`,
      filename: WP_FILE,
    },
    // ─── Valid 2: el-dropdown 不含导入/导出文案，不触发 ───
    {
      code: `<template><el-dropdown><el-dropdown-menu><el-dropdown-item>编辑</el-dropdown-item><el-dropdown-item>删除</el-dropdown-item></el-dropdown-menu></el-dropdown></template>`,
      filename: WP_FILE,
    },
    // ─── Valid 3: 使用 WpAmountCell 组件（正确用法），不触发 ───
    {
      code: `<template><WpAmountCell :value="amount" /></template>`,
      filename: WP_FILE,
    },
    // ─── Valid 4: 使用 WpOpinionCard 组件（正确用法），不触发 ───
    {
      code: `<template><WpOpinionCard v-model="opinion" /></template>`,
      filename: WP_FILE,
    },
    // ─── Valid 5: toLocaleString 在非底稿路径（规则不生效） ───
    {
      code: `<template><span>{{ value.toLocaleString() }}</span></template>`,
      filename: NON_WP_FILE,
    },
    // ─── Valid 6: el-dropdown 仅含"导出"（需同时含导入+导出才触发） ───
    {
      code: `<template><el-dropdown><el-dropdown-menu><el-dropdown-item>导出</el-dropdown-item><el-dropdown-item>删除</el-dropdown-item></el-dropdown-menu></el-dropdown></template>`,
      filename: WP_FILE,
    },
    // ─── Valid 7: el-input type="textarea" + autosize 在非底稿路径 ───
    {
      code: `<template><el-input type="textarea" :autosize="{minRows:3}"></el-input></template>`,
      filename: NON_WP_FILE,
    },
    // ─── Valid 8: el-dropdown 仅含"导入"（缺"导出"，不触发） ───
    {
      code: `<template><el-dropdown><el-dropdown-menu><el-dropdown-item>导入</el-dropdown-item><el-dropdown-item>编辑</el-dropdown-item></el-dropdown-menu></el-dropdown></template>`,
      filename: WP_FILE,
    },
  ],

  invalid: [
    // ─── Invalid 1: autosize textarea 在底稿路径 → useWpOpinionCard ───
    {
      code: `<template><el-input type="textarea" :autosize="{minRows:5}"></el-input></template>`,
      filename: WP_FILE,
      errors: [{ messageId: 'useWpOpinionCard' }],
    },
    // ─── Invalid 2: el-dropdown 含"导入"+"导出" → useWpImportExport ───
    {
      code: `<template><el-dropdown><el-dropdown-menu><el-dropdown-item>导入</el-dropdown-item><el-dropdown-item>导出</el-dropdown-item></el-dropdown-menu></el-dropdown></template>`,
      filename: WP_FILE,
      errors: [{ messageId: 'useWpImportExport' }],
    },
    // ─── Invalid 3: toLocaleString 在模板表达式中 → useWpAmountCell ───
    {
      code: `<template><span>{{ value.toLocaleString() }}</span></template>`,
      filename: WP_FILE,
      errors: [{ messageId: 'useWpAmountCell' }],
    },
  ],
})

console.log('\nno-adhoc-wp-structure RuleTester 例集全部通过 ✓')
