/**
 * componentType 前后端契约测试
 *
 * 验证 backend/app/data/wp_code_overrides.json 中的所有 componentType 值
 * 都能被前端 htmlRendererRegistry 接住（或属于已知的非 registry 类型）。
 *
 * CI 卡点：防止后端新增 componentType 而前端忘记注册组件。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import {
  HTML_COMPONENT_TYPE_SET,
  getContextPropsStrategy,
} from '../htmlRendererRegistry'

/** 非 registry 类型白名单（由 GtWpRenderer 内部逻辑处理，不需要在 registry 注册） */
const NON_REGISTRY_TYPES = new Set([
  'univer',           // Univer 表格兜底
  'skip',             // 跳过占位
  'redirect-materiality',  // B15 重定向标记，非渲染类型
  'confirmation-hub',      // 函证管理，走独立模块路由非底稿渲染
])

describe('componentType 前后端契约', () => {
  // vitest cwd = audit-platform/frontend/，仓库根在 ../../
  const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
  let overrides: Record<string, string>

  try {
    const content = readFileSync(overridesPath, 'utf-8')
    overrides = JSON.parse(content)
  } catch {
    overrides = {}
  }

  it('wp_code_overrides.json 应该存在且非空', () => {
    expect(Object.keys(overrides).length).toBeGreaterThan(0)
  })

  it('所有 componentType 值都应在前端 registry 或白名单中', () => {
    const uniqueTypes = new Set(Object.values(overrides))
    const unhandled: string[] = []

    for (const ct of uniqueTypes) {
      if (!HTML_COMPONENT_TYPE_SET.has(ct as any) && !NON_REGISTRY_TYPES.has(ct)) {
        unhandled.push(ct)
      }
    }

    expect(
      unhandled,
      `以下 componentType 在后端 wp_code_overrides.json 中存在但前端 htmlRendererRegistry 未注册：\n${unhandled.join('\n')}\n请在 htmlRendererRegistry.ts 添加对应条目。`,
    ).toHaveLength(0)
  })

  it('registry 注册的类型数量应 >= 30（防止注册表意外清空）', () => {
    expect(HTML_COMPONENT_TYPE_SET.size).toBeGreaterThanOrEqual(30)
  })

  it('每种 contextProps 策略至少有 1 个组件使用', () => {
    // 确保 contextProps 声明不是死代码
    const strategies = new Set<string>()
    for (const ct of HTML_COMPONENT_TYPE_SET) {
      strategies.add(getContextPropsStrategy(ct))
    }
    expect(strategies.has('standard')).toBe(true)
    expect(strategies.has('form-type')).toBe(true)
    expect(strategies.has('custom')).toBe(true)
  })
})
