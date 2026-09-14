/**
 * blockNumberFormat.ts — 替代程序区块「非金额数值列」只读态格式化（七枢纽共享）
 *
 * ## 为什么单独成模块
 *
 * `CheckBlock.vue` 是 `<script setup>`，其中**禁止运行时 `export`**（只允许 type-only），
 * 否则 Vite 直接 500 而 `get_diagnostics` 查不出。而本函数需要被守卫当纯函数逐条断言
 * （空值语义 / 非数值透传 / 不做金额单位换算），故抽到同目录小模块
 * （范式同 `crossWorkpaperNavLocator.ts`）。
 *
 * ## 与金额格式的分工
 *
 * - 金额列（`BlockColumnDef.render === 'amount'`）→ 平台金额格式单一真源
 *   `stores/displayPrefs` 的 store 成员 `fmt`（千分符 + 单位偏好 + 小数位 + showZero）；
 * - 非金额数值列（数量 / 单价 / 每股指标，见 `blockColumnAmountRegistry.ts`）→ 本函数：
 *   只加千分位分组，**不做金额单位换算、不强制小数位**。
 *
 * ## 空值返回空串而非 `—`
 *
 * 数量为空与金额为空语义不同：金额的 `—` 由 `prefs.fmt` 按 `showZero` 偏好统一决定，
 * 而「未填数量」在检查表里就是空格。
 */

/**
 * 普通数值只读态格式化（千分位分组，无单位换算、无强制小数位）。
 *
 * - `null` / `undefined` / `''` → `''`
 * - 非数值（含 `NaN` / `Infinity`）→ 原样字符串透传（与既有 `formatNumber` 的兜底一致，
 *   避免把用户键入的异常内容显示成 `NaN`）
 * - 其余 → `Number(val).toLocaleString('zh-CN')`
 */
export function formatPlainNumber(val: unknown): string {
  if (val === null || val === undefined || val === '') return ''
  const num = Number(val)
  if (!Number.isFinite(num)) return String(val)
  return num.toLocaleString('zh-CN')
}
