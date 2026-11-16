// 悬空引用门禁专用 ESLint 配置（no-undef 单规则）。
//
// 为什么单独一份而不是往 .eslintrc.cjs 里加规则：
//   ① .eslintrc.cjs 会加载 gt-audit 的 14 条自定义规则，全量跑要半小时；
//      本门只需要 no-undef，去掉插件后快一个量级。
//   ② no-undef 在 TS 类型位置会误报（EventListener 这类 lib.dom 类型不是运行时
//      全局），直接开进主配置会让 npm run lint 常态红。本门用显式豁免表处理，
//      主配置保持不变。
//
// 它抓的缺陷类：引用了既未声明也未导入的名字。这类在构建期不报（esbuild 与浏览器
// 一样把未解析标识符当全局），只有运行时才抛 "X is not a function" —— 2026-09 一次
// 普查抓到 13 处，其中 PrefillDiffPanel.vue 是模板渲染即崩。
//
// 自动导入的全局（ref / watch / computed …）不手抄：由门禁脚本现读
// src/auto-imports.d.ts（unplugin-auto-import 生成物）注入，保持单一真源。
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  rules: { 'no-undef': 'error' },
  overrides: [
    { files: ['**/*.d.ts'], rules: { 'no-undef': 'off' } },
    {
      // vitest.config.ts 里 `globals: true`：describe / it / expect / vi /
      // beforeEach 都是运行时注入的全局，eslint 的 env 不认识它们。
      // 只在测试文件上声明，生产代码的 no-undef 判据不变。
      files: ['**/*.spec.ts', '**/*.spec.tsx', '**/*.test.ts', '**/*.test.tsx',
              '**/__tests__/**/*.ts', '**/__tests__/**/*.tsx'],
      globals: {
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        vi: 'readonly',
        vitest: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
        suite: 'readonly',
        bench: 'readonly',
      },
    },
  ],
}