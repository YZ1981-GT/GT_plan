/**
 * @deprecated 类型已提升为平台共用 `composables/shared/disclosureSegmentTypes.ts`
 * （spec `n-cycle-tax-disclosure-alignment` Task 2.1）。
 *
 * 本文件仅作 re-export 保持 N1 既有引用零回归；新代码请直接引用 shared 版本。
 */
export type {
  N1SegCellPayload,
  N1SegColumn,
  N1SegLabelPayload,
  N1SegRow,
  N1SegRowPayload,
  N1Segment,
  WpSegCellPayload,
  WpSegColumn,
  WpSegLabelPayload,
  WpSegRow,
  WpSegRowPayload,
  WpSegment,
} from './shared/disclosureSegmentTypes'
