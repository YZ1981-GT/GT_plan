/**
 * H1 固定资产分类契约测试 — 确保前端 classifyFaCategory 与后端 _classify_fa_category 口径一致。
 *
 * 用例覆盖后端所有正则分支（含 P2-4 扩展关键词）。
 * 若前后端有任一改动破坏一致性，本测试会红。
 */
import { describe, it, expect } from 'vitest'
import { classifyFaCategory, normalizeFaCategory } from '../h1CategoryClassify'

/** 共享用例：[输入文本, 期望分类] */
const CONTRACT_CASES: Array<[string, string]> = [
  // 房屋及建筑物
  ['厂房', '房屋及建筑物'],
  ['办公楼房屋', '房屋及建筑物'],
  ['仓库', '房屋及建筑物'],
  ['构筑物-围墙', '房屋及建筑物'],
  ['不动产', '房屋及建筑物'],
  ['土地使用权', '房屋及建筑物'],

  // 运输设备
  ['运输设备', '运输设备'],
  ['小汽车', '运输设备'],
  ['货车', '运输设备'],
  ['客车', '运输设备'],
  ['专用车', '运输设备'],
  ['挂车', '运输设备'],
  ['叉车', '运输设备'],
  ['拖拉机', '运输设备'],
  ['船舶', '运输设备'],
  ['飞机', '运输设备'],
  ['机动车', '运输设备'],

  // 办公设备
  ['办公设备', '办公设备'],
  ['电脑', '办公设备'],
  ['计算机', '办公设备'],
  ['打印机', '办公设备'],
  ['复印机', '办公设备'],
  ['服务器', '办公设备'],
  ['网络设备', '办公设备'],
  ['监控设备', '办公设备'],
  ['摄像头', '办公设备'],
  ['空调', '办公设备'],
  ['家具', '办公设备'],
  ['器具', '办公设备'],

  // 机器设备
  ['机器设备', '机器设备'],
  ['机械', '机器设备'],
  ['生产线', '机器设备'],
  ['流水线', '机器设备'],
  ['专用设备', '机器设备'],
  ['通用设备', '机器设备'],
  ['锅炉', '机器设备'],
  ['电机', '机器设备'],
  ['装置', '机器设备'],
  ['仪器', '机器设备'],
  ['仪表', '机器设备'],
  ['机组', '机器设备'],
  ['机床', '机器设备'],
  ['工具', '机器设备'],

  // 其他设备
  ['其他', '其他设备'],
  ['未分类', '其他设备'],
  ['低值易耗品', '其他设备'],
]

describe('H1 分类器契约测试（前后端一致性）', () => {
  it.each(CONTRACT_CASES)(
    'classifyFaCategory("%s") → %s',
    (input, expected) => {
      const result = classifyFaCategory(input)
      expect(result).toBe(expected)
    },
  )

  it('normalizeFaCategory 对电子设备/其他/未分类归一化', () => {
    expect(normalizeFaCategory('电子设备')).toBe('办公设备')
    expect(normalizeFaCategory('其他')).toBe('其他设备')
    expect(normalizeFaCategory('未分类')).toBe('其他设备')
  })

  it('泛化"设备"无其他特征信号时 → 机器设备（与后端对齐）', () => {
    expect(classifyFaCategory('某某设备')).toBe('机器设备')
  })

  it('无任何匹配信号 → null（调用方兜底为其他设备）', () => {
    expect(classifyFaCategory('ABC')).toBeNull()
    expect(classifyFaCategory('')).toBeNull()
  })
})
