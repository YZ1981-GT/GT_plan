/**
 * resolveProcedureSheetKey vitest
 *
 * spec workpaper-g-investment-cycle G-F12（Task 3.6）
 * 原始测试覆盖 D/E/F/H 循环（前序 spec 已实施）
 *
 * Validates: Requirements G-F12.1 — sheetKey 路由 G1→g1a / G4→g4a / G7→g7a
 *
 * 测试覆盖：
 * 1. G 循环路由（含 G10/G11/G12/G13/G14 多位编号优先匹配验证）
 * 2. H 循环路由保留（H10 优先匹配）
 * 3. F 循环路由保留
 * 4. D 循环路由保留
 * 5. 默认 fallback 到 e1a
 */
import { describe, it, expect } from 'vitest'
import { resolveProcedureSheetKey } from '../resolveProcedureSheetKey'

describe('resolveProcedureSheetKey - G 循环路由 (G-F12 Task 3.6)', () => {
  it('G1 系列底稿（G1 / G1-2 / G1-6 等）→ g1a', () => {
    expect(resolveProcedureSheetKey('G1')).toBe('g1a')
    expect(resolveProcedureSheetKey('G1-2')).toBe('g1a')
    expect(resolveProcedureSheetKey('G1-6')).toBe('g1a')
    expect(resolveProcedureSheetKey('G1-8')).toBe('g1a')
    expect(resolveProcedureSheetKey('G1-10')).toBe('g1a')
    expect(resolveProcedureSheetKey('G1-14')).toBe('g1a')
  })

  it('G4 系列底稿（G4 / G4-2 / G4-7 等）→ g4a', () => {
    expect(resolveProcedureSheetKey('G4')).toBe('g4a')
    expect(resolveProcedureSheetKey('G4-2')).toBe('g4a')
    expect(resolveProcedureSheetKey('G4-7')).toBe('g4a')
  })

  it('G6 系列底稿（G6 / G6-2 等）→ g6a', () => {
    expect(resolveProcedureSheetKey('G6')).toBe('g6a')
    expect(resolveProcedureSheetKey('G6-2')).toBe('g6a')
  })

  it('G7 系列底稿（G7 / G7-2 / G7-3 等）→ g7a', () => {
    expect(resolveProcedureSheetKey('G7')).toBe('g7a')
    expect(resolveProcedureSheetKey('G7-2')).toBe('g7a')
    expect(resolveProcedureSheetKey('G7-3')).toBe('g7a')
  })

  it('G8 系列底稿（G8 / G8-2 等）→ g8a', () => {
    expect(resolveProcedureSheetKey('G8')).toBe('g8a')
    expect(resolveProcedureSheetKey('G8-2')).toBe('g8a')
  })

  // ─── 多位编号优先匹配（避免 startsWith('G1') 误匹配 G10~G14）─────────────
  it('G10 → e1a (无专属程序表 fallback)', () => {
    expect(resolveProcedureSheetKey('G10')).toBe('e1a')
    expect(resolveProcedureSheetKey('G10-1')).toBe('e1a')
  })

  it('G11 → g11a (投资收益汇总专属)', () => {
    expect(resolveProcedureSheetKey('G11')).toBe('g11a')
    expect(resolveProcedureSheetKey('G11-1')).toBe('g11a')
  })

  it('G12 → e1a (净敞口套期 fallback)', () => {
    expect(resolveProcedureSheetKey('G12')).toBe('e1a')
  })

  it('G13 → e1a (公允价值变动收益 fallback)', () => {
    expect(resolveProcedureSheetKey('G13')).toBe('e1a')
  })

  it('G14 → e1a (信用减值损失 fallback)', () => {
    expect(resolveProcedureSheetKey('G14')).toBe('e1a')
  })

  it('小写 wp_code 也能正确路由（uppercase 标准化）', () => {
    expect(resolveProcedureSheetKey('g1')).toBe('g1a')
    expect(resolveProcedureSheetKey('g7')).toBe('g7a')
    expect(resolveProcedureSheetKey('g11')).toBe('g11a')
  })
})

describe('resolveProcedureSheetKey - H 循环路由保留（回归测试）', () => {
  it('H1 → h1a / H10 → e1a (H10 优先于 H1)', () => {
    expect(resolveProcedureSheetKey('H1')).toBe('h1a')
    expect(resolveProcedureSheetKey('H10')).toBe('e1a')
    expect(resolveProcedureSheetKey('H10-1')).toBe('e1a')
  })

  it('H2/H3/H8/H9 → 各自专属', () => {
    expect(resolveProcedureSheetKey('H2')).toBe('h2a')
    expect(resolveProcedureSheetKey('H3')).toBe('h3a')
    expect(resolveProcedureSheetKey('H8')).toBe('h8a')
    expect(resolveProcedureSheetKey('H9')).toBe('h9a')
  })
})

describe('resolveProcedureSheetKey - F 循环路由保留（回归测试）', () => {
  it('F2/F1/F3/F4/F5 → 各自专属', () => {
    expect(resolveProcedureSheetKey('F1')).toBe('f1a')
    expect(resolveProcedureSheetKey('F2')).toBe('f2a')
    expect(resolveProcedureSheetKey('F2-21A')).toBe('f2a')
    expect(resolveProcedureSheetKey('F3')).toBe('f3a')
    expect(resolveProcedureSheetKey('F4')).toBe('f4a')
    expect(resolveProcedureSheetKey('F5')).toBe('f5a')
  })
})

describe('resolveProcedureSheetKey - D 循环路由保留（回归测试）', () => {
  it('D2/D4 → 各自专属', () => {
    expect(resolveProcedureSheetKey('D2')).toBe('d2a')
    expect(resolveProcedureSheetKey('D2-1')).toBe('d2a')
    expect(resolveProcedureSheetKey('D4')).toBe('d4a')
    expect(resolveProcedureSheetKey('D4-22A')).toBe('d4a')
  })
})

describe('resolveProcedureSheetKey - 默认 fallback', () => {
  it('未知 wp_code → e1a 默认', () => {
    expect(resolveProcedureSheetKey('E1')).toBe('e1a')
    expect(resolveProcedureSheetKey('UNKNOWN')).toBe('e1a')
    expect(resolveProcedureSheetKey('')).toBe('e1a')
  })
})

describe('resolveProcedureSheetKey - K 循环路由 (K-F9 Task 2.8)', () => {
  it('K1 系列底稿（K1 / K1-2 / K1-12 等）→ k1a', () => {
    expect(resolveProcedureSheetKey('K1')).toBe('k1a')
    expect(resolveProcedureSheetKey('K1-1')).toBe('k1a')
    expect(resolveProcedureSheetKey('K1-2')).toBe('k1a')
    expect(resolveProcedureSheetKey('K1-12')).toBe('k1a')
  })

  it('K3 系列底稿（K3 / K3-1 / K3-2 等）→ k3a', () => {
    expect(resolveProcedureSheetKey('K3')).toBe('k3a')
    expect(resolveProcedureSheetKey('K3-1')).toBe('k3a')
    expect(resolveProcedureSheetKey('K3-2')).toBe('k3a')
  })

  it('K5 系列底稿（K5 / K5-1 / K5-2 等）→ k5a', () => {
    expect(resolveProcedureSheetKey('K5')).toBe('k5a')
    expect(resolveProcedureSheetKey('K5-1')).toBe('k5a')
    expect(resolveProcedureSheetKey('K5-2')).toBe('k5a')
  })

  it('K8 系列底稿（K8 / K8-1 / K8-2 等）→ k8a', () => {
    expect(resolveProcedureSheetKey('K8')).toBe('k8a')
    expect(resolveProcedureSheetKey('K8-1')).toBe('k8a')
    expect(resolveProcedureSheetKey('K8-2')).toBe('k8a')
    expect(resolveProcedureSheetKey('K8-4')).toBe('k8a')
  })

  it('K9 系列底稿（K9 / K9-1 / K9-2 等）→ k9a', () => {
    expect(resolveProcedureSheetKey('K9')).toBe('k9a')
    expect(resolveProcedureSheetKey('K9-1')).toBe('k9a')
    expect(resolveProcedureSheetKey('K9-2')).toBe('k9a')
  })

  // ─── 多位编号优先匹配（避免 startsWith('K1') 误匹配 K10~K13）─────────────
  it('K10 → e1a (营业外收入 fallback)', () => {
    expect(resolveProcedureSheetKey('K10')).toBe('e1a')
    expect(resolveProcedureSheetKey('K10-1')).toBe('e1a')
  })

  it('K11 → k11a (资产减值损失专属)', () => {
    expect(resolveProcedureSheetKey('K11')).toBe('k11a')
    expect(resolveProcedureSheetKey('K11-1')).toBe('k11a')
  })

  it('K12 → e1a (营业外支出 fallback)', () => {
    expect(resolveProcedureSheetKey('K12')).toBe('e1a')
  })

  it('K13 → e1a (资产处置收益 fallback)', () => {
    expect(resolveProcedureSheetKey('K13')).toBe('e1a')
  })

  it('K0/K2/K4/K6/K7 → e1a (无专属路由 fallback)', () => {
    expect(resolveProcedureSheetKey('K0')).toBe('e1a')
    expect(resolveProcedureSheetKey('K2')).toBe('e1a')
    expect(resolveProcedureSheetKey('K4')).toBe('e1a')
    expect(resolveProcedureSheetKey('K6')).toBe('e1a')
    expect(resolveProcedureSheetKey('K7')).toBe('e1a')
  })

  it('小写 wp_code 也能正确路由（uppercase 标准化）', () => {
    expect(resolveProcedureSheetKey('k8')).toBe('k8a')
    expect(resolveProcedureSheetKey('k9-2')).toBe('k9a')
    expect(resolveProcedureSheetKey('k11')).toBe('k11a')
  })
})

describe('resolveProcedureSheetKey - J 循环路由保留（回归测试）', () => {
  it('J1/J2/J3 → 各自专属', () => {
    expect(resolveProcedureSheetKey('J1')).toBe('j1a')
    expect(resolveProcedureSheetKey('J2')).toBe('j2a')
    expect(resolveProcedureSheetKey('J3')).toBe('j3a')
  })
})
