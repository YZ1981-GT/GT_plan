/**
 * emailDomainCheck.ts — 邮箱域名可靠性判断
 *
 * 用途：F0-7 邮件传真回函可靠性验证 —— 自动检测回函邮箱是否为公司域名。
 *
 * 设计约束（f0-confirmation-linkage-and-structural-enhancement, Property 5）：
 * - PERSONAL_DOMAINS 中的域名必判为 'personal'
 * - .com.cn / .cn / .com 等非个人域名必判为 'corp'
 * - 空/无@/无后缀必判为 'unknown'
 * - 不做 DNS 验证（纯字面判断，前端可用）
 *
 * 源模板依据（F0-7 注2）：
 * > 从私人电子信箱发送的回函不可靠。
 * > 邮箱验证方式：（1）验证回函邮箱是否为回函者所在单位的工作邮箱（如后缀）
 */

// ─── 私人邮箱域名列表（中国常用 + 国际主流） ──────────────────────────────────

export const PERSONAL_DOMAINS: readonly string[] = [
  // 中国主流
  'qq.com',
  '163.com',
  '126.com',
  'yeah.net',
  'sina.com',
  'sina.cn',
  'sohu.com',
  'foxmail.com',
  'aliyun.com',
  '139.com',
  '189.cn',
  '21cn.com',
  'tom.com',
  // 国际主流
  'gmail.com',
  'hotmail.com',
  'outlook.com',
  'yahoo.com',
  'yahoo.com.cn',
  'live.com',
  'msn.com',
  'icloud.com',
  'me.com',
  'mail.com',
  'aol.com',
  'protonmail.com',
  'proton.me',
  'yandex.com',
  'zoho.com',
]

/** 私人域名的 Set（查找 O(1)） */
const PERSONAL_SET = new Set(PERSONAL_DOMAINS.map(d => d.toLowerCase()))

// ─── 核心函数 ─────────────────────────────────────────────────────────────────

/**
 * 从邮箱地址提取域名部分。
 *
 * @returns 域名（小写），或 null（无效输入）
 *
 * 例：
 * - 'user@example.com.cn' → 'example.com.cn'
 * - 'User@QQ.COM' → 'qq.com'
 * - '' / 'no-at-sign' / '@' → null
 */
export function extractDomain(email: string | null | undefined): string | null {
  if (!email) return null
  const str = String(email).trim()
  if (!str) return null

  const atIdx = str.lastIndexOf('@')

  // 形态 A：完整邮箱 `user@domain.com`
  if (atIdx > 0 && atIdx < str.length - 1) {
    const domain = str.slice(atIdx + 1).toLowerCase().trim()
    return domain && domain.includes('.') ? domain : null
  }

  // 形态 B：裸域名 `@domain.com` 或 `domain.com`
  //   F0-7「邮箱域名」列的 placeholder 就是 `如 @company.com` → 必须兼容，
  //   否则该列填了值也永远判 unknown（灰色），等于没接上。
  if (atIdx === 0) {
    const domain = str.slice(1).toLowerCase().trim()
    return domain && domain.includes('.') ? domain : null
  }
  if (atIdx < 0) {
    const bare = str.toLowerCase()
    // 仅当形如域名（含点、无空格、无 @）才认；否则视为无法识别
    if (bare.includes('.') && !/\s/.test(bare)) return bare
    return null
  }

  return null
}

/**
 * 判断邮箱域名可靠性。
 *
 * @returns
 * - 'personal' — 私人邮箱（不可靠）
 * - 'corp' — 公司域名（可靠）
 * - 'unknown' — 无法判断（空输入/无@/无后缀）
 */
export function isCorpEmailDomain(email: string | null | undefined): 'corp' | 'personal' | 'unknown' {
  const domain = extractDomain(email)
  if (!domain) return 'unknown'

  // 精确匹配私人域名
  if (PERSONAL_SET.has(domain)) return 'personal'

  // 子域名匹配（如 mail.qq.com → qq.com）
  for (const personal of PERSONAL_SET) {
    if (domain.endsWith('.' + personal)) return 'personal'
  }

  // 有域名但不在私人列表 → 视为公司域名
  return 'corp'
}

/**
 * 获取可靠性展示标签和样式。
 */
export function emailReliabilityTag(email: string | null | undefined): {
  label: string
  type: 'success' | 'danger' | 'info'
  tooltip: string
} {
  const status = isCorpEmailDomain(email)
  const domain = extractDomain(email)

  switch (status) {
    case 'corp':
      return {
        label: '公司邮箱',
        type: 'success',
        tooltip: `域名 ${domain} 为公司邮箱，可靠性较高`,
      }
    case 'personal':
      return {
        label: '私人邮箱',
        type: 'danger',
        tooltip: `域名 ${domain} 为私人邮箱服务商，回函可靠性需进一步验证`,
      }
    case 'unknown':
    default:
      return {
        label: '未知',
        type: 'info',
        tooltip: '无法识别邮箱域名',
      }
  }
}
