import { describe, expect, it } from 'vitest'
import { buildUserUpdateBody } from '../userUpdateBody'

const ORIGINAL = { email: 'a@example.com', role: 'auditor' }

describe('buildUserUpdateBody — 编辑只发改了的字段', () => {
  it('没改 ⇒ 空对象（含只差首尾空白的邮箱）', () => {
    expect(buildUserUpdateBody(ORIGINAL, { ...ORIGINAL })).toEqual({})
    expect(buildUserUpdateBody(ORIGINAL, { ...ORIGINAL, email: ' a@example.com ' })).toEqual({})
  })

  it('只改角色 / 只改邮箱 / 都改', () => {
    expect(buildUserUpdateBody(ORIGINAL, { ...ORIGINAL, role: 'manager' })).toEqual({ role: 'manager' })
    expect(buildUserUpdateBody(ORIGINAL, { ...ORIGINAL, email: 'b@example.com ' })).toEqual({ email: 'b@example.com' })
    expect(buildUserUpdateBody(ORIGINAL, { email: 'b@example.com', role: 'readonly' }))
      .toEqual({ email: 'b@example.com', role: 'readonly' })
  })

  it('表单里的其他字段（用户名 / 密码）不会带出去', () => {
    const edited = { ...ORIGINAL, username: 'renamed', password: '' } as any
    expect(buildUserUpdateBody(ORIGINAL, edited)).toEqual({})
  })
})
