/**
 * I1 无形资产类别配置测试。
 *
 * 覆盖 i1CategoryScope.ts 的所有纯函数：
 * resolveI1Categories / addI1Category / renameI1Category /
 * removeI1Category / i1CategoryColumnKey / defaultI1CategoryKeys
 */
import { describe, it, expect } from 'vitest'

import {
  resolveI1Categories,
  addI1Category,
  renameI1Category,
  removeI1Category,
  i1CategoryColumnKey,
  defaultI1CategoryKeys,
  I1_DEFAULT_CATEGORIES,
} from '../i1CategoryScope'

describe('resolveI1Categories', () => {
  it('null → 返回 11 项默认列表', () => {
    const result = resolveI1Categories(null)
    expect(result).toHaveLength(11)
    expect(result[0].key).toBe('land_use_right')
    expect(result[10].key).toBe('other')
  })

  it('自定义列表 → 返回自定义列表', () => {
    const custom = [{ key: 'a', label: 'A', seq: 1 }]
    const result = resolveI1Categories(custom)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({ key: 'a', label: 'A', seq: 1, removable: true })
  })
})

describe('addI1Category', () => {
  const list = resolveI1Categories(null)

  it('撞名返回 null', () => {
    const result = addI1Category(list, '土地使用权')
    expect(result).toBeNull()
  })

  it('成功新增，长度 +1', () => {
    const result = addI1Category(list, '新类别')
    expect(result).not.toBeNull()
    expect(result!).toHaveLength(list.length + 1)
    expect(result![result!.length - 1].label).toBe('新类别')
    expect(result![result!.length - 1].removable).toBe(true)
  })
})

describe('renameI1Category', () => {
  const list = resolveI1Categories(null)

  it('成功改名', () => {
    const result = renameI1Category(list, 'software', '软件V2')
    expect(result).not.toBeNull()
    const target = result!.find((c) => c.key === 'software')
    expect(target!.label).toBe('软件V2')
  })

  it('撞名返回 null', () => {
    // '软件' 已存在，试图把 patent 改成 '软件'
    const result = renameI1Category(list, 'patent', '软件')
    expect(result).toBeNull()
  })
})

describe('removeI1Category', () => {
  const list = resolveI1Categories(null)

  it('other 不可删返回 null', () => {
    const result = removeI1Category(list, 'other')
    expect(result).toBeNull()
  })

  it('成功删除，长度 -1', () => {
    const result = removeI1Category(list, 'software')
    expect(result).not.toBeNull()
    expect(result!).toHaveLength(list.length - 1)
    expect(result!.find((c) => c.key === 'software')).toBeUndefined()
  })
})

describe('i1CategoryColumnKey', () => {
  it('生成稳定 key = "{slot.key}_{slot.seq}"', () => {
    const slot = { key: 'land_use_right', label: '土地使用权', seq: 1, removable: true }
    expect(i1CategoryColumnKey(slot)).toBe('land_use_right_1')
  })
})

describe('defaultI1CategoryKeys', () => {
  it('最后一项是 "other"', () => {
    const keys = defaultI1CategoryKeys()
    expect(keys[keys.length - 1]).toBe('other')
    expect(keys).toHaveLength(I1_DEFAULT_CATEGORIES.length)
  })
})
