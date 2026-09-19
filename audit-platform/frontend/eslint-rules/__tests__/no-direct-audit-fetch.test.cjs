// Feature: platform-global-hardening
// Validates: Requirements 5.7
//
// ESLint RuleTester 例集 — no-direct-audit-fetch 规则
// 检测底稿内直接调用取数 URL（trial-balance/tb-balance/ledger/entries/aging-config），
// 建议使用 useAuditData SDK 的语义方法。
//
// 运行：node eslint-rules/__tests__/no-direct-audit-fetch.test.cjs

'use strict'

const { RuleTester } = require('eslint')
const rule = require('../no-direct-audit-fetch.cjs')

const ruleTester = new RuleTester({
  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'module',
  },
})

// 底稿路径（触发规则）
const WP_FILE = 'src/components/workpaper/d2/core/D2TabDetail.vue'
// 非底稿路径（不触发规则）
const NON_WP_FILE = 'src/views/Dashboard.vue'

ruleTester.run('no-direct-audit-fetch', rule, {
  valid: [
    // ─── Valid 1: 使用 useAuditData SDK 的语义方法（正确用法）───
    {
      code: `const { getTbAmount } = useAuditData(projectId); getTbAmount('1122')`,
      filename: WP_FILE,
    },
    // ─── Valid 2: 非取数 URL 的 http.get 调用 ───
    {
      code: `http.get('/api/workpapers/123/render-config')`,
      filename: WP_FILE,
    },
    // ─── Valid 3: 非底稿路径中的取数 URL 调用（不触发）───
    {
      code: `http.get('/api/projects/1/trial-balance')`,
      filename: NON_WP_FILE,
    },
    // ─── Valid 4: 使用 getLedgerEntries 语义方法 ───
    {
      code: `const { getLedgerEntries } = useAuditData(projectId); getLedgerEntries({ accountCode: '1122' })`,
      filename: WP_FILE,
    },
    // ─── Valid 5: http.get 调用普通 API 路径 ───
    {
      code: `http.get('/api/workpapers/456/checklist-responses')`,
      filename: WP_FILE,
    },
    // ─── Valid 6: 调用非 HTTP 方法的对象方法 ───
    {
      code: `store.get('/api/projects/1/trial-balance')`,
      filename: WP_FILE,
    },
    // ─── Valid 7: 模板字面量但无取数 URL 片段 ───
    {
      code: "http.get(`/api/workpapers/${wpId}/versions`)",
      filename: WP_FILE,
    },
  ],

  invalid: [
    // ─── Invalid 1: http.get 调用 trial-balance URL ───
    {
      code: `http.get('/api/projects/1/trial-balance')`,
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 2: api.get 调用 ledger/entries URL ───
    {
      code: `api.get('/api/projects/1/ledger/entries')`,
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 3: http.get 调用 tb-balance URL ───
    {
      code: `http.get('/api/projects/1/tb-balance')`,
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 4: http.get 调用 aging-config URL ───
    {
      code: `http.get('/api/projects/1/aging-config')`,
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 5: 模板字面量中的取数 URL ───
    {
      code: "http.get(`/api/projects/${projectId}/trial-balance`)",
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 6: axios.get 调用取数 URL ───
    {
      code: `axios.get('/api/projects/1/ledger/entries')`,
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 7: http.post 调用取数 URL ───
    {
      code: `http.post('/api/projects/1/trial-balance')`,
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 8: fetch 调用取数 URL ───
    {
      code: `fetch('/api/projects/1/ledger/entries')`,
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
    // ─── Invalid 9: 模板字面量中的 aging-config URL ───
    {
      code: "api.get(`/api/projects/${id}/aging-config`)",
      filename: WP_FILE,
      errors: [{ messageId: 'useAuditDataSdk' }],
    },
  ],
})

console.log('\nno-direct-audit-fetch RuleTester 例集全部通过 ✓')
