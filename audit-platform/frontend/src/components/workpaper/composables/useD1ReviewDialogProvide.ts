/**
 * useD1ReviewDialogProvide — 兼容层，委托至 useWorkpaperReviewProvide
 */
export {
  useWorkpaperReviewProvide as useD1ReviewDialogProvide,
  type WorkpaperOpenReviewParams as D1OpenReviewParams,
  type WorkpaperOpenReviewFn as D1OpenReviewFn,
} from './useWorkpaperReviewProvide'
