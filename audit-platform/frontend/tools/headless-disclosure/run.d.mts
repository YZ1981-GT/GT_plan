/** run.mjs 的类型声明（命令行用 .mjs 直接跑，测试从 TS 调 `runCommand`）。 */
import type { BuildCheckResult } from './buildCheck.mjs'

export declare const EXIT_OK: 0
export declare const EXIT_ERROR: 1
export declare const EXIT_USAGE: 2
export declare const EXIT_BUILD: 3

export interface RunCommandDeps {
  env?: Record<string, string | undefined>
  verifyBuild?: () => BuildCheckResult
  loadEntry?: () => Promise<any>
  stdout?: (text: string) => void
  stderr?: (text: string) => void
}

export declare function runCommand(argv: string[], deps?: RunCommandDeps): Promise<number>
