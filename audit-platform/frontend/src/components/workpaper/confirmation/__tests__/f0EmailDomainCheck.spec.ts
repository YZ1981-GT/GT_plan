/**
 * f0EmailDomainCheck.spec.ts — 邮箱域名可靠性判断守卫
 *
 * Property 5: PERSONAL_DOMAINS 必判 personal / 非个人域名必判 corp / 无效必判 unknown
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  extractDomain,
  isCorpEmailDomain,
  emailReliabilityTag,
  PERSONAL_DOMAINS,
} from '@/utils/emailDomainCheck'

// ─── extractDomain ───────────────────────────────────────────────────────────

describe('extractDomain', () => {
  it('正常邮箱提取域名', () => {
    expect(extractDomain('user@example.com')).toBe('example.com')
  })

  it('中文邮箱前缀', () => {
    expect(extractDomain('张三@company.com.cn')).toBe('company.com.cn')
  })

  it('大写转小写', () => {
    expect(extractDomain('User@QQ.COM')).toBe('qq.com')
  })

  it('空字符串 → null', () => {
    expect(extractDomain('')).toBeNull()
  })

  it('null → null', () => {
    expect(extractDomain(null)).toBeNull()
  })

  it('undefined → null', () => {
    expect(extractDomain(undefined)).toBeNull()
  })

  it('无 @ → null', () => {
    expect(extractDomain('no-at-sign')).toBeNull()
  })

  it('@ 在末尾 → null', () => {
    expect(extractDomain('user@')).toBeNull()
  })

  it('域名无点 → null', () => {
    expect(extractDomain('user@localhost')).toBeNull()
  })

  it('多个 @ 取最后一个', () => {
    expect(extractDomain('a@b@company.com')).toBe('company.com')
  })

  // ── 形态 B：裸域名（Task 26 新增，F0-7「邮箱域名」列 placeholder 为 `如 @company.com`）──

  it('裸域名带 @ 前缀 → 去掉 @ 返回域名', () => {
    expect(extractDomain('@company.com')).toBe('company.com')
  })

  it('裸域名带 @ 前缀（私人）→ 正确识别', () => {
    expect(extractDomain('@qq.com')).toBe('qq.com')
  })

  it('裸域名无 @ 前缀 → 原样返回', () => {
    expect(extractDomain('company.com.cn')).toBe('company.com.cn')
  })

  it('裸域名大写转小写', () => {
    expect(extractDomain('@Company.COM')).toBe('company.com')
  })

  it('只有 @ 无域名 → null', () => {
    expect(extractDomain('@')).toBeNull()
  })

  it('@ 后无点 → null', () => {
    expect(extractDomain('@localhost')).toBeNull()
  })

  it('含空格的非域名文本 → null（防把说明文字当域名）', () => {
    expect(extractDomain('公司邮箱 待确认')).toBeNull()
  })

  it('无点无 @ 的纯文本 → null', () => {
    expect(extractDomain('待确认')).toBeNull()
  })
})

// ─── Task 26: 裸域名形态的可靠性判定 ────────────────────────────────────────

describe('裸域名形态的 isCorpEmailDomain（F0-7 邮箱域名列）', () => {
  it('@qq.com → personal', () => {
    expect(isCorpEmailDomain('@qq.com')).toBe('personal')
  })

  it('@163.com → personal', () => {
    expect(isCorpEmailDomain('@163.com')).toBe('personal')
  })

  it('@company.com.cn → corp', () => {
    expect(isCorpEmailDomain('@company.com.cn')).toBe('corp')
  })

  it('无 @ 的 gt-china.com → corp', () => {
    expect(isCorpEmailDomain('gt-china.com')).toBe('corp')
  })

  it('裸域名 tag 与完整邮箱 tag 一致', () => {
    expect(emailReliabilityTag('@qq.com').type).toBe(emailReliabilityTag('user@qq.com').type)
    expect(emailReliabilityTag('@corp.cn').type).toBe(emailReliabilityTag('user@corp.cn').type)
  })
})

// ─── isCorpEmailDomain ───────────────────────────────────────────────────────

describe('isCorpEmailDomain', () => {
  // Property 5.1: PERSONAL_DOMAINS 中的域名必判为 personal
  describe('私人邮箱域名 → personal', () => {
    const personalCases = [
      'user@qq.com',
      'user@163.com',
      'user@126.com',
      'user@gmail.com',
      'user@hotmail.com',
      'user@outlook.com',
      'user@yahoo.com',
      'user@sina.com',
      'user@foxmail.com',
      'user@icloud.com',
      'user@protonmail.com',
    ]

    it.each(personalCases)('%s → personal', (email) => {
      expect(isCorpEmailDomain(email)).toBe('personal')
    })
  })

  // Property 5.1b: 子域名也判 personal
  it('子域名 mail.qq.com → personal', () => {
    expect(isCorpEmailDomain('user@mail.qq.com')).toBe('personal')
  })

  it('子域名 vip.163.com → personal', () => {
    expect(isCorpEmailDomain('user@vip.163.com')).toBe('personal')
  })

  // Property 5.2: 非个人域名 → corp
  describe('公司域名 → corp', () => {
    const corpCases = [
      'user@company.com.cn',
      'user@baidu.com',
      'user@alibaba.com',
      'finance@gt-china.com',
      'audit@pwc.cn',
      'user@some-bank.com.cn',
    ]

    it.each(corpCases)('%s → corp', (email) => {
      expect(isCorpEmailDomain(email)).toBe('corp')
    })
  })

  // Property 5.3: 无效 → unknown
  describe('无效输入 → unknown', () => {
    const unknownCases = [
      '',
      null,
      undefined,
      'no-at-sign',
      'user@',
      '@',
      'user@localhost',
    ]

    it.each(unknownCases)('%s → unknown', (email) => {
      expect(isCorpEmailDomain(email as any)).toBe('unknown')
    })
  })
})

// ─── emailReliabilityTag ─────────────────────────────────────────────────────

describe('emailReliabilityTag', () => {
  it('公司邮箱 → success', () => {
    const tag = emailReliabilityTag('user@company.com.cn')
    expect(tag.type).toBe('success')
    expect(tag.label).toBe('公司邮箱')
  })

  it('私人邮箱 → danger', () => {
    const tag = emailReliabilityTag('user@qq.com')
    expect(tag.type).toBe('danger')
    expect(tag.label).toBe('私人邮箱')
  })

  it('未知 → info', () => {
    const tag = emailReliabilityTag('')
    expect(tag.type).toBe('info')
    expect(tag.label).toBe('未知')
  })
})

// ─── Task 26: 源码级接线断言（防再次变成零消费方） ──────────────────────────

describe('Property: emailDomainCheck 必须真的接进 ReliabilityGrid', () => {
  const GRID = 'audit-platform/frontend/src/components/workpaper/confirmation/reliability/ReliabilityGrid.vue'

  function readGrid(): string {
    const here = dirname(fileURLToPath(import.meta.url))
    return readFileSync(resolve(here, '../../../../../../..', GRID), 'utf-8')
  }

  it('反向自检：能读到 ReliabilityGrid 源码', () => {
    expect(readGrid().length).toBeGreaterThan(1000)
  })

  it('已 import emailReliabilityTag', () => {
    expect(readGrid()).toContain("from '@/utils/emailDomainCheck'")
  })

  it('回函邮箱列渲染可靠性 tag', () => {
    const src = readGrid()
    expect(src).toMatch(/reply_email[\s\S]{0,900}emailReliabilityTag\(row\.reply_email\)/)
  })

  it('邮箱域名列渲染可靠性 tag', () => {
    const src = readGrid()
    expect(src).toMatch(/email_domain[\s\S]{0,900}emailReliabilityTag\(row\.email_domain\)/)
  })

  it('tag 的 type/label/tooltip 三项都用上（不是只显示文字）', () => {
    const src = readGrid()
    expect(src).toContain('emailReliabilityTag(row.reply_email).type')
    expect(src).toContain('emailReliabilityTag(row.reply_email).label')
    expect(src).toContain('emailReliabilityTag(row.reply_email).tooltip')
  })
})

// ─── PERSONAL_DOMAINS 常量完整性 ─────────────────────────────────────────────

describe('PERSONAL_DOMAINS', () => {
  it('至少包含 20 个域名', () => {
    expect(PERSONAL_DOMAINS.length).toBeGreaterThanOrEqual(20)
  })

  it('全部小写', () => {
    for (const d of PERSONAL_DOMAINS) {
      expect(d).toBe(d.toLowerCase())
    }
  })

  it('无重复', () => {
    const set = new Set(PERSONAL_DOMAINS)
    expect(set.size).toBe(PERSONAL_DOMAINS.length)
  })

  it('包含中国主流和国际主流', () => {
    expect(PERSONAL_DOMAINS).toContain('qq.com')
    expect(PERSONAL_DOMAINS).toContain('163.com')
    expect(PERSONAL_DOMAINS).toContain('gmail.com')
    expect(PERSONAL_DOMAINS).toContain('hotmail.com')
  })
})
