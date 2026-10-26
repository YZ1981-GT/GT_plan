/**
 * N1 递延所得税资产底稿 sheet 分发（纯函数，可单测）
 *
 * spec: `.kiro/specs/n1-n3-host-inline-router-and-shared-adoption` Task 2（BP-10 收口）
 *
 * 🔴 原宿主内联实现把 wp_code 正则 `/N1-[1-5]/` **前置于**披露判定 —— 与
 * `shared/cycleSheetRouting.ts` 存在的理由（D2 实测：披露 tab 名尾部带 wp_code 时
 * 披露组件永远挂不上）同形。现状披露 tab 名不带后缀故**暂未**中招，但一旦源模板给
 * 披露 tab 加编码后缀，披露组件会静默挂不上。改用共享路由（披露判定前置 + 国企多写法全认）。
 *
 * 分发键保持宿主模板既有的取值（`index` / `procedure` / `disclosure-*` / `N1-x` / `skip`），
 * 宿主 `v-if` 一行不改 —— 只换判定实现，不换分发契约。
 */
import {
  SHEET_DISCLOSURE_LISTED,
  SHEET_DISCLOSURE_SOE,
  SHEET_INDEX,
  makeCycleSheetRouter,
} from './shared/cycleSheetRouting'

export const N1_SHEET_INDEX = 'index'
export const N1_SHEET_PROCEDURE = 'procedure'
export const N1_SHEET_DISCLOSURE_LISTED = 'disclosure-listed'
export const N1_SHEET_DISCLOSURE_SOE = 'disclosure-soe'
export const N1_SHEET_SKIP = 'skip'

const router = makeCycleSheetRouter({
  codeRe: /(N1A|N1-[1-5]|N1)/,
  htmlCodeRe: /^N1-[1-5]$/,
  bareCodes: ['N1'],
})

/** 共享路由分发键 → N1 宿主模板既有分发键 */
const TO_HOST_KEY: Record<string, string> = {
  [SHEET_DISCLOSURE_LISTED]: N1_SHEET_DISCLOSURE_LISTED,
  [SHEET_DISCLOSURE_SOE]: N1_SHEET_DISCLOSURE_SOE,
  [SHEET_INDEX]: N1_SHEET_INDEX,
  N1: N1_SHEET_INDEX,
  N1A: N1_SHEET_PROCEDURE,
}

/**
 * 原始 tab 名 → N1 分发键。
 *
 * 🔴 sheet 名按原始字面量比对，禁 strip / 归一化（本 spec 有「表的{码}」形态：
 * `递延所得税资产审计程序表的N1A`、`…亏损检查表的N1-5`）。
 */
export function normalizeN1SheetName(sheetName: string | null | undefined): string {
  const name = String(sheetName ?? '')
  if (name === 'GT_Custom') return N1_SHEET_SKIP
  if (name === '') return N1_SHEET_INDEX
  const key = router.normalize(name)
  if (key in TO_HOST_KEY) return TO_HOST_KEY[key]
  // 程序表名未带码时的兜底（与原实现一致）
  if (name.includes('程序表')) return N1_SHEET_PROCEDURE
  return key
}

/** N1-1~N1-5 + 目录 + 两张附注为 HTML 专属组件；N1A 走程序表路由、GT_Custom 走 OO */
export function isN1HtmlSheet(key: string): boolean {
  return /^N1-[1-5]$/.test(key)
    || key === N1_SHEET_INDEX
    || key === N1_SHEET_DISCLOSURE_LISTED
    || key === N1_SHEET_DISCLOSURE_SOE
}
