/**
 * 🔴 本文件由脚本生成，请勿手工编辑。
 *
 * 生成器：`backend/scripts/fix/gen_cycle_import_export_registry.py`
 * 真源  ：ACNR catalog（`backend/data/acnr/global_catalog.json`）的
 *         `sheets[].import_export` 段 —— 也是 `bulk_tab` 全链的路由真源。
 *
 * ## 这里为什么不含 f1 / f2 系列 / f3 / f4 / f5 / g0 / h0
 *
 * 🔴 注意：本段文字不得出现 `f2` 后紧跟星号加斜杠的写法 —— 那会提前闭合
 * 块注释，导致生成文件语法错误（本生成器初版即踩此坑，esbuild 报
 * `Unexpected "*"`）。
 *
 * 那 10 个前缀由 `cycleImportExportRegistry.ts` 的 `MANUAL_OVERRIDES` 接管，
 * 因为它们的 `sheets[]` 含 **catalog 表达不了的传输层键**：
 *   · `G0-3S` 是后端 `_SHEET_NAME_MAP` 的键，不是 `sheet_code`
 *   · `F3-7-debit` / `F4-8-credit` 等复合变体键存在于后端 specs，catalog 只登记基础码
 * 纯 catalog 生成会丢掉它们（实测 f3 catalog 5 键 vs 后端 16 键）⇒ 下拉少掉一半区段。
 *
 * 重新生成：
 *   python backend/scripts/fix/gen_cycle_import_export_registry.py --apply
 */
import type { CycleImportExportEntry } from './cycleImportExportRegistry'

/** 从 ACNR catalog 派生的 I/E 条目（不含 MANUAL_OVERRIDES 接管的前缀） */
export const GENERATED_IMPORT_EXPORT: Record<string, CycleImportExportEntry> = {
  d1: { apiPrefix: 'd1', sheets: ['D1-1', 'D1-10', 'D1-11', 'D1-12', 'D1-13', 'D1-14', 'D1-15', 'D1-16', 'D1-2', 'D1-3', 'D1-4', 'D1-5', 'D1-6', 'D1-7', 'D1-8', 'D1-9'] },
  d2: { apiPrefix: 'd2', sheets: ['D2-1', 'D2-10', 'D2-11', 'D2-12', 'D2-13', 'D2-2', 'D2-3', 'D2-4', 'D2-6', 'D2-7', 'D2-8', 'D2-9'] },
  d3: { apiPrefix: 'd3', sheets: ['D3-1', 'D3-2', 'D3-3', 'D3-5', 'D3-6', 'D3-7'] },
  d4: { apiPrefix: 'd4', sheets: ['D4-1', 'D4-10', 'D4-11', 'D4-12', 'D4-14', 'D4-15', 'D4-16', 'D4-17', 'D4-18', 'D4-19', 'D4-2', 'D4-20', 'D4-21', 'D4-22', 'D4-23', 'D4-24', 'D4-25', 'D4-26', 'D4-27', 'D4-28', 'D4-29', 'D4-3', 'D4-30', 'D4-31', 'D4-32', 'D4-33', 'D4-34', 'D4-35', 'D4-36', 'D4-4', 'D4-6', 'D4-7', 'D4-8', 'D4-9'] },
  d5: { apiPrefix: 'd5', sheets: ['D5-2', 'D5-3', 'D5-4'] },
  d6: { apiPrefix: 'd6', sheets: ['D6-2', 'D6-3', 'D6-5', 'D6-8'] },
  d7: { apiPrefix: 'd7', sheets: ['D7-1', 'D7-2', 'D7-3', 'D7-4', 'D7-5', 'D7-6'] },
  f0: { apiPrefix: 'f0', sheets: ['F0-6'] },
  g1: { apiPrefix: 'g1', sheets: ['G1-11', 'G1-12', 'G1-13', 'G1-14', 'G1-2', 'G1-3', 'G1-4', 'G1-5', 'G1-6', 'G1-7'] },
  g10: { apiPrefix: 'g10', sheets: ['G10-2'] },
  g11: { apiPrefix: 'g11', sheets: ['G11-1', 'G11-2', 'G11-3', 'G11-4', 'G11-5'] },
  g12: { apiPrefix: 'g12', sheets: ['G12-2', 'G12-3', 'G12-4', 'G12-5', 'G12-6'] },
  g13: { apiPrefix: 'g13', sheets: ['G13-2', 'G13-3'] },
  g14: { apiPrefix: 'g14', sheets: ['G14-2', 'G14-3'] },
  g2: { apiPrefix: 'g2', sheets: ['G2-2', 'G2-3'] },
  g3: { apiPrefix: 'g3', sheets: ['G3-1', 'G3-2'] },
  'g4-ecl': { apiPrefix: 'g4-ecl', sheets: ['G4-10', 'G4-11', 'G4-12', 'G4-13', 'G4-9'] },
  'g4-main': { apiPrefix: 'g4-main', sheets: ['G4-1', 'G4-2', 'G4-3'] },
  'g4-sppi': { apiPrefix: 'g4-sppi', sheets: ['G4-5', 'G4-6', 'G4-7'] },
  g5: { apiPrefix: 'g5', sheets: ['G5-2', 'G5-3', 'G5-4'] },
  'g6-ecl': { apiPrefix: 'g6-ecl', sheets: ['G6-12', 'G6-14'] },
  'g6-main': { apiPrefix: 'g6-main', sheets: ['G6-2', 'G6-3'] },
  'g6-sppi': { apiPrefix: 'g6-sppi', sheets: ['G6-5', 'G6-6'] },
  'g7-equity-method': { apiPrefix: 'g7-equity-method', sheets: ['G7-13', 'G7-14', 'G7-15', 'G7-16', 'G7-17', 'G7-4', 'G7-5'] },
  'g7-main': { apiPrefix: 'g7-main', sheets: ['G7-2', 'G7-3'] },
  'g7-sub': { apiPrefix: 'g7-sub', sheets: ['G7-10', 'G7-11', 'G7-12', 'G7-18', 'G7-8', 'G7-9'] },
  g8: { apiPrefix: 'g8', sheets: ['G8-2', 'G8-3', 'G8-4', 'G8-5', 'G8-6'] },
  g9: { apiPrefix: 'g9', sheets: ['G9-2', 'G9-3', 'G9-4', 'G9-5', 'G9-6'] },
  h1: { apiPrefix: 'h1', sheets: ['H1-10', 'H1-16', 'H1-19', 'H1-2', 'H1-3', 'H1-7', 'H1-8'] },
  h10: { apiPrefix: 'h10', sheets: ['H10-2', 'H10-3'] },
  h2: { apiPrefix: 'h2', sheets: ['H2-10', 'H2-2', 'H2-3', 'H2-7', 'H2-8'] },
  h3: { apiPrefix: 'h3', sheets: ['H3-2', 'H3-3', 'H3-6', 'H3-7', 'H3-9'] },
  h4: { apiPrefix: 'h4', sheets: ['H4-2', 'H4-3', 'H4-5', 'H4-6'] },
  h5: { apiPrefix: 'h5', sheets: ['H5-2', 'H5-3'] },
  h6: { apiPrefix: 'h6', sheets: ['H6-2', 'H6-3'] },
  h7: { apiPrefix: 'h7', sheets: ['H7-2', 'H7-3'] },
  h8: { apiPrefix: 'h8', sheets: ['H8-2', 'H8-3', 'H8-5', 'H8-6'] },
  i1: { apiPrefix: 'i1', sheets: ['I1', 'I1-3', 'I1-5', 'I1-6', 'I1-8', 'I1-9'] },
  i2: { apiPrefix: 'i2', sheets: ['I2-1', 'I2-13', 'I2-14', 'I2-7'] },
  i3: { apiPrefix: 'i3', sheets: ['I3-1', 'I3-2', 'I3-3', 'I3-4', 'I3-6', 'I3-7'] },
  i4: { apiPrefix: 'i4', sheets: ['I4-2', 'I4-6'] },
  i5: { apiPrefix: 'i5', sheets: ['I5-2', 'I5-3'] },
  i6: { apiPrefix: 'i6', sheets: ['I6-2', 'I6-3', 'I6-5', 'I6-6'] },
  k0: { apiPrefix: 'k0', sheets: ['K0-5', 'K0-6'] },
  k1: { apiPrefix: 'k1', sheets: ['K1-11', 'K1-2', 'K1-4', 'K1-5', 'K1-7', 'K1-8'] },
  k10: { apiPrefix: 'k10', sheets: ['K10-2', 'K10-4'] },
  k11: { apiPrefix: 'k11', sheets: ['K11-2', 'K11-3'] },
  k12: { apiPrefix: 'k12', sheets: ['K12-2', 'K12-3'] },
  k13: { apiPrefix: 'k13', sheets: ['K13-2', 'K13-3'] },
  k2: { apiPrefix: 'k2', sheets: ['K2-2', 'K2-4', 'K2-5'] },
  k3: { apiPrefix: 'k3', sheets: ['K3-2', 'K3-3'] },
  k4: { apiPrefix: 'k4', sheets: ['K4-2', 'K4-3'] },
  k5: { apiPrefix: 'k5', sheets: ['K5-2', 'K5-3'] },
  k6: { apiPrefix: 'k6', sheets: ['K6-2', 'K6-3', 'K6-6'] },
  k7: { apiPrefix: 'k7', sheets: ['K7-2', 'K7-3'] },
  k8: { apiPrefix: 'k8', sheets: ['K8-2', 'K8-3', 'K8-5', 'K8-6', 'K8-7', 'K8-8'] },
  k9: { apiPrefix: 'k9', sheets: ['K9-2', 'K9-3', 'K9-5', 'K9-6', 'K9-7', 'K9-8'] },
  l1: { apiPrefix: 'l1', sheets: ['L1-2', 'L1-3'] },
  l2: { apiPrefix: 'l2', sheets: ['L2-3'] },
  l3: { apiPrefix: 'l3', sheets: ['L3-2', 'L3-3'] },
  l4: { apiPrefix: 'l4', sheets: ['L4-2', 'L4-3'] },
  l5: { apiPrefix: 'l5', sheets: ['L5-2', 'L5-3'] },
  l6: { apiPrefix: 'l6', sheets: ['L6-3'] },
  m1: { apiPrefix: 'm1', sheets: ['M1-3'] },
  m10: { apiPrefix: 'm10', sheets: ['M10-3'] },
  m2: { apiPrefix: 'm2', sheets: ['M2-3'] },
  m3: { apiPrefix: 'm3', sheets: ['M3-3'] },
  m4: { apiPrefix: 'm4', sheets: ['M4-3'] },
  m5: { apiPrefix: 'm5', sheets: ['M5-3'] },
  m6: { apiPrefix: 'm6', sheets: ['M6-3'] },
  m7: { apiPrefix: 'm7', sheets: ['M7-3'] },
  m8: { apiPrefix: 'm8', sheets: ['M8-3'] },
  m9: { apiPrefix: 'm9', sheets: ['M9-3'] },
  n1: { apiPrefix: 'n1', sheets: ['N1-3'] },
  n2: { apiPrefix: 'n2', sheets: ['N2-3'] },
  n3: { apiPrefix: 'n3', sheets: ['N3-3'] },
  n4: { apiPrefix: 'n4', sheets: ['N4-2', 'N4-3'] },
  n5: { apiPrefix: 'n5', sheets: ['N5-3'] },
}

/** 生成时的 catalog 前缀总数（含 MANUAL 接管的），供守卫核对覆盖面 */
export const CATALOG_PREFIX_TOTAL = 88

/** 本文件登记的前缀数 */
export const GENERATED_PREFIX_COUNT = 78
