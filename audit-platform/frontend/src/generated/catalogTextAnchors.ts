/**
 * ACNR 目录单元格 → 网页文字锚点（spec wp-deeplink-locate-coverage-closure 需求 2）。
 *
 * @generated 由 backend/scripts/acnr/generate_cell_text_anchors.py 从 backend/data/acnr/global_catalog.json 生成，勿手改；
 * 校验：python backend/scripts/acnr/generate_cell_text_anchors.py --check（目录里结论格变了须重新生成）
 */

export const CATALOG_TEXT_ANCHORS: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  'D2-5': { A53: '审计结论' },
  'D2-6': { A21: '审计结论' },
  'D4-22': { A28: '审计结论' },
  'D4-6': { A28: '审计结论' },
  'E1-14': { A50: '审计结论' },
  'E1-15': { A31: '审计结论' },
  'E1-19': { A54: '审计结论' },
  'E1-20': { A29: '审计结论' },
  'E1-21': { A51: '审计结论' },
  'E1-22': { A50: '审计结论' },
  'E1-23': { A66: '审计结论' },
  'E1-26': { A61: '审计结论' },
  'E1-27': { A47: '审计结论' },
  'E1-28': { A71: '审计结论' },
  'E1-29': { A35: '审计结论' },
  'E1-30': { A389: '审计结论' },
  'E1-31': { A87: '审计结论' },
  'E1-32': { A36: '审计结论' },
  'E1-9': { A26: '审计结论' },
  'F2-18': { A65: '审计结论' },
  'F2-19': { A80: '审计结论' },
  'F2-20': { A22: '审计结论' },
  'F2-24': { A29: '审计结论' },
  'F2-26': { A28: '审计结论' },
  'F2-29': { A46: '审计结论' },
  'F2-30': { A46: '审计结论' },
  'F2-31': { A44: '审计结论' },
  'F2-32': { A44: '审计结论' },
  'F2-35': { A39: '审计结论' },
  'F2-38': { A83: '审计结论' },
  'F2-39': { A68: '审计结论' },
  'F2-40': { A61: '审计结论' },
  'F2-41': { A21: '审计结论' },
  'F2-42': { A45: '审计结论' },
  'F2-43': { A29: '审计结论' },
  'F2-47': { A38: '审计结论' },
  'F2-56': { A37: '审计结论' },
  'F2-62': { A53: '审计结论' },
  'F2-63': { A44: '审计结论' },
  'F2-65': { A43: '审计结论' },
  'F2-66': { A43: '审计结论' },
  'F2-67': { A36: '审计结论' },
  'F2-69': { A30: '审计结论' },
  'F2-70': { A43: '审计结论' },
  'F5-3': { A28: '审计结论' },
  'G2-3': { A27: '审计结论' },
  'G4-4': { F46: '审计结论' },
  'G4-5': { A33: '审计结论' },
  'G5-3': { A27: '审计结论' },
  'G6-3': { A26: '审计结论' },
  'G7-4': { A42: '审计结论' },
  'G7-5': { A56: '审计结论' },
  'G8-4': { A24: '审计结论' },
  'H1-5': { A34: '审计结论' },
  'H3-4': { A27: '审计结论' },
  'H8-4': { A59: '审计结论' },
  'H9-3': { A19: '审计结论' },
  'I1-4': { A32: '审计结论' },
  'I1-5': { A29: '审计结论' },
  'I2-4': { A35: '审计结论' },
  'I3-4': { A22: '审计结论' },
  'I3-5': { A27: '审计结论' },
  'I4-2': { A32: '审计结论' },
  'I6-2': { A33: '审计结论' },
}

/** sheet 编码 + A1 → 锚点文字（编码与 A1 都去空白、不分大小写）；没有登记返回 null */
export function catalogTextAnchor(sheetCode: string | null | undefined, cellRef: string | null | undefined): string | null {
  if (!sheetCode || !cellRef) return null
  return CATALOG_TEXT_ANCHORS[sheetCode.trim().toUpperCase()]?.[cellRef.trim().toUpperCase()] ?? null
}
