/**
 * useD2ReviewDialogProvide — 兼容层，委托至 useWorkpaperReviewProvide
 */
export {
  useWorkpaperReviewProvide as useD2ReviewDialogProvide,
  type WorkpaperOpenReviewParams as D2OpenReviewParams,
  type WorkpaperOpenReviewFn as D2OpenReviewFn,
} from './useWorkpaperReviewProvide'
