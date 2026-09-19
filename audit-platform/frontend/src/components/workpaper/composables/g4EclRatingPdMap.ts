/**
 * G4-11 外部评级 → 一年期边际 PD 参考映射（示例，仅供底稿测试参考）
 *
 * 口径说明（对齐 G4EclPdGuidance）：
 * - 国内评级需审慎映射至国际评级后再取违约率；本表直接给出国内常用档位参考值
 * - 设置 0.03%（0.0003）下限；实际项目须替换为当期违约率数据版本
 * - 不得将资本风险权重误作会计 PD
 */
export interface G4EclRatingPdEntry {
  rating: string
  /** 一年期边际 PD（小数，如 0.0003 = 0.03%） */
  annualPd: number
  note?: string
}

/** 参考映射表（平滑后的示意值，须在底稿中注明数据来源与版本） */
export const G4_ECL_RATING_PD_MAP: G4EclRatingPdEntry[] = [
  { rating: 'AAA', annualPd: 0.0003, note: '下限 0.03%' },
  { rating: 'AA+', annualPd: 0.0005 },
  { rating: 'AA', annualPd: 0.0008 },
  { rating: 'AA-', annualPd: 0.0012 },
  { rating: 'A+', annualPd: 0.002 },
  { rating: 'A', annualPd: 0.0035 },
  { rating: 'A-', annualPd: 0.005 },
  { rating: 'BBB+', annualPd: 0.008 },
  { rating: 'BBB', annualPd: 0.012 },
  { rating: 'BBB-', annualPd: 0.02 },
  { rating: 'BB+', annualPd: 0.04 },
  { rating: 'BB', annualPd: 0.06 },
  { rating: 'BB-', annualPd: 0.08 },
  { rating: 'B+', annualPd: 0.1 },
  { rating: 'B', annualPd: 0.12 },
  { rating: 'B-', annualPd: 0.15 },
  { rating: 'CCC/C', annualPd: 0.2 },
  { rating: 'D', annualPd: 1, note: '已违约' },
]

export const G4_ECL_RATING_OPTIONS = G4_ECL_RATING_PD_MAP.map((e) => e.rating)

/** 按评级查一年期 PD；未命中返回 null */
export function lookupAnnualPdByRating(rating: string): number | null {
  const key = String(rating || '').trim().toUpperCase()
  if (!key) return null
  const hit = G4_ECL_RATING_PD_MAP.find((e) => e.rating.toUpperCase() === key)
  return hit ? hit.annualPd : null
}
