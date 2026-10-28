/**
 * 附注编辑器的本地偏好（localStorage）。
 *
 * 「保存后跳到下一未编制章节」默认关闭：原先未设置即开启，手工保存一次就跳走，用户以为章节丢了
 * （spec note-pull-followup-closure R19）。只有用户在工具栏显式打开（存了 'true'）才跳。
 */
export const AUTO_ADVANCE_KEY = 'gt_note_auto_advance'

export function readAutoAdvance(storage: Pick<Storage, 'getItem'> | null | undefined): boolean {
  try {
    return storage?.getItem(AUTO_ADVANCE_KEY) === 'true'
  } catch {
    return false // 隐私模式等读不到：按默认关闭
  }
}

export function writeAutoAdvance(storage: Pick<Storage, 'setItem'> | null | undefined, value: boolean): void {
  try {
    storage?.setItem(AUTO_ADVANCE_KEY, String(value))
  } catch {
    // 配额满 / 隐私模式：只影响下次打开时的默认值，本次开关照常生效
  }
}
