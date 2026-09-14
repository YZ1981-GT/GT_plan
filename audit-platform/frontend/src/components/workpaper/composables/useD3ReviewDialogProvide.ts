/**
 * useD3ReviewDialogProvide — 兼容层，委托至 useWorkpaperReviewProvide
 */
export {
  useWorkpaperReviewProvide as useD3ReviewDialogProvide,
  type WorkpaperOpenReviewParams as D3OpenReviewParams,
  type WorkpaperOpenReviewFn as D3OpenReviewFn,
} from './useWorkpaperReviewProvide'
