/** @deprecated 使用 useG14FormulaEngine */
export {
  parseNum,
  calcAdjustedAmount,
  calcNetImpairmentLoss,
  calcProvisionRollForward,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  isChangeRateExceeding,
  isDebitCreditBalanced,
  calcVariance,
} from './useG14FormulaEngine'

/** 兼容旧名 */
export { calcAdjustedAmount as calcAuditedAmount } from './useG14FormulaEngine'
