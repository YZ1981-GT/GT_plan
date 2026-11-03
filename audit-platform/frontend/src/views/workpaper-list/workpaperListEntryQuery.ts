/**
 * 底稿列表页的入口参数（spec wp-deeplink-locate-residual-closure 需求 2）。
 *
 * 跳到列表页的入口带的参数：`highlight` / `wp_code` / `search` = 定位某张底稿（编码解析不到底稿时的兜底跳转、复核层级徽标、
 * 程序表交叉引用、联动全景图、索引 chip 降级等）；`account` = 定位科目关联的底稿（试算表右键「查看关联底稿」）；
 * `cycle` = 按循环筛选（循环进度环）；`assigned=me|unassigned` = 按编制人筛选（待办通知 / 经理看板「待分配」）；
 * `upload` = 打开导入（编辑器「上传新版本」）；另有页面自己的 `view` / `filter` 与审计年度 `year`。
 * 守卫 `__tests__/workpaperListEntryQuery.spec.ts` 扫全仓跳列表页的参数，都须在 `WORKPAPER_LIST_QUERY_KEYS` 里。
 */

/** 列表页读的全部参数 */
export const WORKPAPER_LIST_QUERY_KEYS = [
  'view', 'filter', 'year', 'highlight', 'wp_code', 'search', 'account', 'cycle', 'assigned', 'upload',
] as const

/** 编制人筛选「未分配」（不是用户 id：不传给后端，列表里按 assigned_to 为空筛） */
export const UNASSIGNED_FILTER = '__unassigned__'

export interface ListEntryQuery {
  /** 要定位的底稿编码（highlight > wp_code > search） */
  code: string
  /** 要定位其关联底稿的科目编码 */
  account: string
  /** 按循环筛选（单个字母 A~S） */
  cycle: string
  /** 按编制人筛选：me（当前用户）/ unassigned（未分配） */
  assigned: '' | 'me' | 'unassigned'
  /** 打开导入（值为来源底稿 id，导入按文件认底稿，只作触发） */
  upload: string
  /** 入口参数签名：变了才按「新进入」处理（为空 = 没有入口参数） */
  signature: string
}

function first(v: unknown): string {
  const x = Array.isArray(v) ? v[0] : v
  return typeof x === 'string' ? x.trim() : ''
}

/** 编码取第一个词：入口里有「D2-1 应收账款」「D2-1，D2-2」这类带名称 / 多个的写法 */
export function entryCode(v: unknown): string {
  return first(v).split(/[\s,，]/)[0] ?? ''
}

export function readListEntryQuery(query: Record<string, unknown>): ListEntryQuery {
  const code = entryCode(query.highlight) || entryCode(query.wp_code) || entryCode(query.search)
  const account = entryCode(query.account)
  const letter = first(query.cycle).toUpperCase()
  const cycle = /^[A-S]$/.test(letter) ? letter : ''
  const who = first(query.assigned)
  const assigned = who === 'me' || who === 'unassigned' ? who : ''
  const upload = first(query.upload)
  const parts = [code, account, cycle, assigned, upload]
  return { code, account, cycle, assigned, upload, signature: parts.some(Boolean) ? parts.join('|') : '' }
}
