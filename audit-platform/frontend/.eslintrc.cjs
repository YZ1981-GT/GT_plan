// ESLint 配置 - 审计平台前端
// 使用 legacy config 格式（.eslintrc.cjs）
//
// 本地插件通过在 node_modules 中创建符号链接解析，
// 或通过下方 settings 中的路径配置加载。
//
// 依赖：eslint@8 eslint-plugin-vue @typescript-eslint/parser vue-eslint-parser

module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  plugins: ['vue', 'gt-audit'],
  rules: {
    // V3 Req 12.4.2: no-console 设为 error（允许 warn/error 保留用于生产排查）
    'no-console': ['error', { allow: ['warn', 'error'] }],
    // V3 新增 7 条规则（骨架阶段设为 warn）
    'gt-audit/no-amount-without-decimal': 'warn',
    'gt-audit/el-form-must-have-rules': 'warn',
    'gt-audit/no-delete-without-confirm': 'warn',
    'gt-audit/must-watch-route-or-context': 'warn',
    'gt-audit/no-bare-amount-cell': 'warn',
    'gt-audit/no-status-string-literal': 'warn',
    'gt-audit/no-english-ui-text': 'warn',
    // 既有规则
    'gt-audit/no-amount-arithmetic': 'warn',
    'gt-audit/no-amount-toFixed': 'warn',
    'gt-audit/no-amount-unit-in-script': 'warn',
    'gt-audit/no-dialog-without-append': 'warn',
  },
  overrides: [
    {
      files: ['*.vue'],
      rules: {
        'gt-audit/el-form-must-have-rules': 'warn',
        'gt-audit/no-bare-amount-cell': 'warn',
        'gt-audit/no-status-string-literal': 'warn',
        'gt-audit/no-english-ui-text': 'warn',
        'gt-audit/no-dialog-without-append': 'warn',
      },
    },
    {
      // V3 Req 12.4.2: 测试文件和一次性脚本豁免 no-console
      files: ['**/*.spec.ts', '**/*.test.ts', 'scripts/**/*.{js,mjs,ts}'],
      rules: { 'no-console': 'off' },
    },
  ],
}
