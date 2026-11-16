/**
 * 正式导出单位边界守卫（platform-global-display-settings-closure 阶段 C）。
 *
 * 纯函数可以保留显式 divisor/unitSuffix 的兼容 API，但正式导出入口必须消费
 * 服务端按项目返回的只读 ExportUnitPolicy，不能把屏幕显示状态带进交付件。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  applyFormalExportUnit,
  formalExportUnitHeaderNote,
  type ExportUnitPolicy,
} from '@/utils/exportUnit'

const MODULE = resolve(__dirname, '..', 'exportUnit.ts')

function readModule(): string {
  return readFileSync(MODULE, 'utf-8')
}

describe('正式导出单位策略边界', () => {
  it('正式入口使用服务端项目策略中的 divisor 与 unitSuffix', () => {
    const policy: ExportUnitPolicy = {
      projectId: 'project-1',
      divisor: 10000,
      unitSuffix: '万元',
    }

    expect(applyFormalExportUnit(12000, policy)).toBe(1.2)
    expect(formalExportUnitHeaderNote(policy)).toBe('（单位：万元）')
  })

  it('exportUnit 模块不 import 或读取个人显示设置', () => {
    const source = readModule()

    expect(source).not.toMatch(/(?:from|import\s*\()[^\n]*displayPrefs/i)
    expect(source).not.toContain('useDisplayPrefsStore')
    expect(source).not.toMatch(/\bdisplayPrefs\b/)
  })

  it('正式导出说明的函数边界只接受 ExportUnitPolicy', () => {
    const source = readModule()

    expect(source).toMatch(
      /export function applyFormalExportUnit\(rawYuan: number, policy: ExportUnitPolicy\)/,
    )
    expect(source).toMatch(
      /export function formalExportUnitHeaderNote\(policy: ExportUnitPolicy\)/,
    )
    expect(source).toContain('readonly divisor: number')
    expect(source).toContain('readonly unitSuffix: ExportUnitSuffix')
  })
})
