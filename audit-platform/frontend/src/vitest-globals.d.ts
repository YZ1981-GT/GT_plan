/// <reference types="vitest/globals" />
// vitest.config.ts 里 `globals: true`：测试文件可不 import 直接用 vi / describe / it / expect / beforeEach 等。
// 这里补上对应的类型声明，类型检查才与运行时一致（不改 tsconfig 的 `types`，避免收窄其他自动引入的 @types）。
