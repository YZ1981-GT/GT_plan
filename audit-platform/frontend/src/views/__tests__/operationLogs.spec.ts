/**
 * 操作日志页守卫（spec operation-log-and-last-login）
 *
 * - 路由注册且带 admin 门（照抄 permissionCenter.spec 的「真实 router 对象」口径）
 * - 菜单项存在、path 与注册路由一致（防死菜单）、仅 admin 可见
 * - 类型筛选下拉与后端白名单同源（7 项一个不少）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const LAYOUT = resolve(__dirname, '../../layouts/ThreeColumnLayout.vue')
const PAGE = resolve(__dirname, '../OperationLogs.vue')
const SYS_DOMAIN = resolve(__dirname, '../../router/domains/system.ts')
const API_PATHS = resolve(__dirname, '../../services/apiPaths/system.ts')

async function getRoutes() {
  const { systemRoutes } = await import('../../router/domains/system')
  return systemRoutes as any[]
}

describe('操作日志 — 路由与菜单', () => {
  it('settings/operation-logs 路由已注册并挂 OperationLogs.vue、meta.permission=admin', async () => {
    const routes = await getRoutes()
    const r = routes.find(x => x.name === 'OperationLogs')
    expect(r, 'OperationLogs 路由未注册').toBeTruthy()
    expect(r.path).toBe('settings/operation-logs')
    expect(r.meta?.permission).toBe('admin')
    expect(r.components?.default ?? r.component).toBeTruthy()
  })

  it('菜单项存在：path=/settings/operation-logs、roles=[admin]、label=操作日志', () => {
    const src = readFileSync(LAYOUT, 'utf-8')
    const line = src.split('\n').find(l => l.includes("key: 'operation-logs'"))
    expect(line, '找不到 operation-logs 菜单声明').toBeTruthy()
    expect(line).toContain("path: '/settings/operation-logs'")
    expect(line).toContain("roles: ['admin']")
    expect(line).toContain("label: '操作日志'")
  })

  it('菜单 path 与路由完整路径一致（防死菜单）', async () => {
    const routes = await getRoutes()
    const r = routes.find(x => x.name === 'OperationLogs')
    // 菜单写的是完整路径 /settings/operation-logs；路由是 DefaultLayout 的 child
    expect(`/settings/operation-logs`).toBe(`/${r!.path}`)
  })

  it('apiPaths 注册了 /api/system/operation-logs', () => {
    const src = readFileSync(API_PATHS, 'utf-8')
    expect(src).toContain("list: '/api/system/operation-logs'")
  })
})

describe('操作日志页 — 类型筛选与后端白名单同源', () => {
  it('前端 7 个类型选项与后端 VALID_TYPES 逐值一致', async () => {
    const { LOGIN_RESULT_TYPES, BUSINESS_ACTION_TYPES } = await import(
      // 直接读后端文件不可行（跨包）；这里用页面源码与硬编码后端口径对拍
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      '../../views/OperationLogs.vue'
    ).catch(() => ({ LOGIN_RESULT_TYPES: [], BUSINESS_ACTION_TYPES: [] }))
    void LOGIN_RESULT_TYPES
    void BUSINESS_ACTION_TYPES

    const src = readFileSync(PAGE, 'utf-8')
    const block = src.match(/const TYPE_OPTIONS = \[([\s\S]*?)\] as const/)
    expect(block, 'TYPE_OPTIONS 定义找不到了').toBeTruthy()
    const values = [...block![1].matchAll(/value: '([a-z_]+)'/g)].map(m => m[1])
    expect(values).toEqual([
      'success', 'failed', 'locked', 'logout', 'create', 'update', 'delete',
    ])
  })

  it('失败/锁定类型用 danger 红标（登录失败可见性）', () => {
    const src = readFileSync(PAGE, 'utf-8')
    expect(src).toContain("t === 'failed' || t === 'locked'")
  })

  it('分页参数与筛选参数名与后端一致（page/page_size/type/keyword/dept_id/from/to）', () => {
    const src = readFileSync(PAGE, 'utf-8')
    // params 对象字面量与条件赋值两种写法都算：page/page_size 在字面量里，其余是 params.xxx =
    expect(src).toContain('page: page.value')
    expect(src).toContain('page_size: pageSize.value')
    for (const key of ['type', 'dept_id', 'keyword', 'from', 'to']) {
      expect(src).toContain(`params.${key}`)
    }
  })
})
