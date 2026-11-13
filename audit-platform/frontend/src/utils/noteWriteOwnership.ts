/**
 * 附注写入归属 manual 策略（spec formula-writer-ownership-and-stale design §13）的原因代码与处理建议。
 *
 * 交接章节从未由底稿同步、已有人工填写 ⇒ 后端不用底稿披露表覆盖，`sync-from-workpaper` 回 `skipped` + 这个原因。
 * 处理建议与后端 `note_write_ownership.reason_text` 同一句（对拍守卫 `noteWriteOwnershipParity.spec.ts`）；离屏同步、
 * 附注页刷新提示与披露 Tab 的同步提示都用这一句。本模块不引界面库（离屏同步框架也引用它）。
 */
export const MANUAL_TAKEOVER_REASON = 'manual_values_never_synced'
export const MANUAL_TAKEOVER_ADVICE = '如需改用底稿数据，先在附注编辑器里把人工填写的格恢复为自动'
