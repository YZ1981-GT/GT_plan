/**
 * 程序裁剪页「进入程序表」的编辑器路由：带程序表别名，编辑器直接落到程序表页签
 * （原先不带 sheet ⇒ 多页底稿落到「底稿目录」，spec procedure-chain-hardening-and-java-contracts R5）。
 */
import { PROGRAM_SHEET_ALIAS } from '@/utils/normalizeSheetName'

export function programConsoleRoute(projectId: string, wpId: string): { path: string; query: { sheet: string } } {
  return {
    path: `/projects/${projectId}/workpapers/${wpId}/edit`,
    query: { sheet: PROGRAM_SHEET_ALIAS },
  }
}
