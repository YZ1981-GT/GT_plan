/**
 * 循环宿主 sheet 分发 —— 平台共用纯函数工厂
 *
 * 🔴 收敛两类**已实测过的静默失真**（`get_diagnostics` 与 vitest 都查不出，只有浏览器能发现）：
 *
 * 1. **披露判定必须前置于 wp_code 正则**。`workpaper_sheet_classification` 里有些循环的
 *    披露 tab 名尾部带 wp_code（D2 实测：`附注披露信息（国企）D2-1`），宿主若先跑
 *    `/D2-\d+/` 就把披露 tab 判成明细表 → **披露组件永远挂不上**。
 * 2. **「国企」写法不唯一**。平台实测并存 `国企` / `国有企业`；N2 原实现还写成繁体
 *    `國企` → 国企披露 Tab 从来没渲染过（落到 OnlyOffice 兜底）。
 *
 * 各循环只需给出「wp_code 提取正则」与「走 HTML 组件的编码正则」，
 * 判定逻辑与常量全部共用，避免每个循环各写一份再各自漂移。
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`
 */

/** 归一后的披露/目录分发键（各宿主 `v-if` 比对用） */
export const SHEET_DISCLOSURE_LISTED = '附注(上市)'
export const SHEET_DISCLOSURE_SOE = '附注(国企)'
export const SHEET_INDEX = '底稿目录'

/** 国企 sheet 名的全部已知写法（简体 / 全称 / 繁体） */
const SOE_TOKENS = ['国企', '国有', '國企'] as const

export interface CycleSheetRouter {
  /** 原始 tab 名 → 分发键；`wpCode` 为 sheetName 缺失时的回退 */
  normalize(sheetName: string | null | undefined, wpCode?: string | null): string
  /** 是否走 HTML 专属组件（其余走 OnlyOffice 兜底） */
  isHtmlSheet(normalized: string): boolean
}

export interface CycleSheetRouterOptions {
  /** wp_code 提取正则（如 `/(N4A|O2A|N4-[1-3]|N4)/`），第 1 个捕获组为分发键 */
  codeRe: RegExp
  /** 走 HTML 组件的编码正则（如 `/^N4-[1-3]$/`） */
  htmlCodeRe: RegExp
  /** 走 HTML 组件的裸编码（通常是循环号本身，如 `'N4'`，对应底稿目录） */
  bareCodes?: readonly string[]
}

export function makeCycleSheetRouter(opts: CycleSheetRouterOptions): CycleSheetRouter {
  const bare = new Set(opts.bareCodes ?? [])

  function normalize(sheetName: string | null | undefined, wpCode?: string | null): string {
    const name = String(sheetName || wpCode || '')

    // ① 披露判定**前置**（防 wp_code 后缀抢占）
    if (name.includes('附注')) {
      if (name.includes('上市')) return SHEET_DISCLOSURE_LISTED
      if (SOE_TOKENS.some((t) => name.includes(t))) return SHEET_DISCLOSURE_SOE
    }

    if (name.includes('底稿目录')) return SHEET_INDEX

    const m = name.match(opts.codeRe)
    if (m) return m[1]

    return name
  }

  function isHtmlSheet(normalized: string): boolean {
    return (
      opts.htmlCodeRe.test(normalized)
      || bare.has(normalized)
      || normalized === SHEET_INDEX
      || normalized === SHEET_DISCLOSURE_LISTED
      || normalized === SHEET_DISCLOSURE_SOE
    )
  }

  return { normalize, isHtmlSheet }
}
