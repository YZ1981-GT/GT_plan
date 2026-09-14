/**
 * crossWorkpaperNavLocator — 跨表导航「定位值」纯函数（七枢纽共享）
 *
 * spec: confirmation-orphan-and-amount-format-closure，Task 5（Requirement 1.3/1.4）
 *
 * 抽成独立模块而不是留在 `CrossWorkpaperNav.vue` 里的原因：`<script setup>` 不允许
 * 运行时 `export`（写了会让 Vite 直接 500，`get_diagnostics` 查不出），而守卫要把它
 * 当纯函数直接断言输入输出，不能只做源码字符串匹配。
 *
 * ── 三条设计依据（实证，勿凭直觉改） ──────────────────────────────────────────
 *
 * 🔴 1. 为什么统一 emit `navigate-sheet`、不再走 `navigate`
 *    `workpaper_sheet_classification` 实测：**七枢纽全部是单 `wp_code` 多 sheet 工作簿**
 *    （D0 11 / E0 20 / F0 10 / G0 10 / H0 10 / K0 11 / L0 10 条 sheet 记录各自挂在
 *    同一个 wp_code 下）→ 「跨工作簿跳转」在函证域**永远不会命中**。
 *    而宿主 `GtWpRenderer` 只监听 `@navigate-sheet`（`onChildNavigateSheet`），
 *    **没有 `@navigate` 监听器** → 旧的 `emit('navigate', ...)` 落地即静默丢弃。
 *
 * 🔴 2. 为什么 wp_code 也能当定位值（六枢纽没有真实 tab 名真源）
 *    `resolveSheetNameByDeepLink` 的第 3 级是**归一后 includes 匹配**，
 *    而六枢纽每张 sheet 名都以自己的编码收尾（`函证结果汇总表D0-1` ⊃ `D0-1`）
 *    → 传编码可命中中文 tab 名。G0 有真实 tab 名（`函证差异核对表G0-3（证券投资）`）
 *    则优先用它 —— 因为 G0 的**展示索引号与 tab 名不一致**（源模板笔误，展示 G0-4），
 *    拿展示值 `G0-4` 去 includes 会命中另一张 sheet（`函证差异核对表G0-4(非证券投资)`）。
 *
 * 🔴 3. 为什么取斜杠首段
 *    组合替代程序的 wpCode 是 `D0-5/D0-6` 形态（两张 sheet 合并成一个导航槽），
 *    整串不可能命中任何 sheet 名 → 取首段 `D0-5` 落到「合同负债及销售替代程序D0-5」。
 */

/** 导航项里参与定位的最小形状（与 `NavItem` 结构兼容，便于守卫构造替身） */
export interface NavLocatorInput {
  /** 底稿编码；组合替代程序为 `X0-5/X0-6` 形态 */
  wpCode: string
  /** 同工作簿定位值（源模板真实 tab 名）；null = 无 tab 名真源 */
  sheetName: string | null
  /** 是否走同工作簿 `?sheet=` 切页（由 `isSameWorkbookNavTarget` 判定） */
  sameWorkbook: boolean
}

/**
 * 定位值：同工作簿且有真实 tab 名 → 取 tab 名；否则取 wp_code 首段。
 *
 * 返回值交给 `GtWpRenderer.onChildNavigateSheet` → `resolveSheetNameByDeepLink`
 * 做三级匹配（原样 → 归一 → 归一后后缀/包含）。
 */
export function locatorOf(item: NavLocatorInput): string {
  if (item.sameWorkbook && item.sheetName) return item.sheetName
  return item.wpCode.split('/')[0]
}
