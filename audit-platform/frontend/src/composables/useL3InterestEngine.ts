/**
 * useL3InterestEngine — re-export barrel
 *
 * Re-exports from the canonical location at @/components/workpaper/composables/
 * to maintain consistent import paths from @/composables/useL3InterestEngine
 */
export {
  calcInterest,
  calcOverdueDays,
  calcInterestDiff,
  calcInterestDays,
} from '@/components/workpaper/composables/useL3InterestEngine'
