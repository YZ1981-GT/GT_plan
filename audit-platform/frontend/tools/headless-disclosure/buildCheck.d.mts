/** buildCheck.mjs 的类型声明（执行器命令行用 .mjs 直接跑，测试从 TS 引用）。 */
export declare const BUILD_HINT: string

export type BuildCheckResult =
  | { ok: true; files: number }
  | { ok: false; reason: string; changed: string[] }

export declare function checkBuild(distDir: string, frontendRoot: string): BuildCheckResult
