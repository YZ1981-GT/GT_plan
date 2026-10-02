/**
 * utils/authToken —— 原生请求 token 单一读取入口
 *
 * 回归背景：知识库上传等原生请求自己读 localStorage 的 token，而 auth store 早已把
 * token 迁到 sessionStorage 并删除 localStorage 副本 ⇒ 恒 401（2026-09-29 实测）。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { getAuthToken, getAuthHeaders } from '@/utils/authToken'

function clearStorages() {
  sessionStorage.clear()
  localStorage.clear()
}

describe('getAuthToken / getAuthHeaders', () => {
  beforeEach(() => {
    clearStorages()
    setActivePinia(createPinia())
  })
  afterEach(clearStorages)

  it('已登录：返回 auth store 的 token，并生成 Bearer 头', () => {
    sessionStorage.setItem('token', 'tok-session')
    expect(getAuthToken()).toBe('tok-session')
    expect(getAuthHeaders()).toEqual({ Authorization: 'Bearer tok-session' })
  })

  it('store 刷新 token 后立即生效（不读存储里的旧值）', () => {
    sessionStorage.setItem('token', 'tok-old')
    const store = useAuthStore()
    store.token = 'tok-refreshed'
    expect(getAuthToken()).toBe('tok-refreshed')
  })

  it('未登录：返回空串与空对象（不发送 "Bearer " 空凭据）', () => {
    expect(getAuthToken()).toBe('')
    expect(getAuthHeaders()).toEqual({})
  })

  it('只有迁移前遗留的 localStorage token：经 auth store 迁移后可读到，且 localStorage 被清掉', () => {
    localStorage.setItem('token', 'tok-legacy')
    expect(getAuthToken()).toBe('tok-legacy')
    expect(localStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('token')).toBe('tok-legacy')
  })

  it('Pinia 尚未激活（应用挂载前调用）：回退 sessionStorage 而不是抛错', () => {
    sessionStorage.setItem('token', 'tok-early')
    setActivePinia(undefined as any)
    expect(getAuthToken()).toBe('tok-early')
  })
})
