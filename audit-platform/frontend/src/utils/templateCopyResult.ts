/**
 * 模板复制回执 → 一条提示（spec procedure-chain-hardening-and-java-contracts R3）。
 *
 * 🔴 原先不论结果都提示「模板复制完成」：全部跳过（已裁剪 / 在回收站 / 目标已有 / 无权查看）时用户以为复制成功了。
 */
export interface TemplateCopyItem {
  source_wp_code?: string | null
  status?: string | null
  message?: string | null
}

export interface TemplateCopySummary {
  level: 'success' | 'warning' | 'error'
  message: string
}

export function summarizeTemplateCopy(items: TemplateCopyItem[]): TemplateCopySummary {
  const count = (s: string) => items.filter((it) => it?.status === s).length
  const copied = count('copied')
  const skipped = count('skipped')
  const failed = count('failed')
  const rest: string[] = []
  if (skipped) rest.push(`跳过 ${skipped} 份`)
  if (failed) rest.push(`失败 ${failed} 份`)
  if (copied && !rest.length) return { level: 'success', message: `已复制 ${copied} 份底稿` }
  if (copied) return { level: 'warning', message: `已复制 ${copied} 份底稿，${rest.join('，')}（原因见下表）` }
  if (failed) return { level: 'error', message: `没有复制任何底稿：${rest.join('，')}（原因见下表）` }
  return { level: 'warning', message: `没有复制任何底稿：${rest.join('，') || '没有可复制的底稿'}（原因见下表）` }
}
