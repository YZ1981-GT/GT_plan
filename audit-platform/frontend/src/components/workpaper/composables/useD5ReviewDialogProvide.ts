/**
 * useD5ReviewDialogProvide — 兼容层，委托至 useWorkpaperReviewProvide
 */
export {
  useWorkpaperReviewProvide as useD5ReviewDialogProvide,
  type WorkpaperOpenReviewParams as D5OpenReviewParams,
  type WorkpaperOpenReviewFn as D5OpenReviewFn,
} from './useWorkpaperReviewProvide'
