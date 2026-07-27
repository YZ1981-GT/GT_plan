# D0 关注点

## 1. 状态不可撤回（已识别缺口，未修）

`_ALLOWED_TRANSITIONS` 严格单向，`matched`/`discrepancy` 是终态（空集）。审计师点错想退（`sent → pending`、相符改差异）只能删除整条重建。已起 spec `confirmation-attachment-ocr-linkage` 规划一步退到底 + 审计留痕，尚未实现。

## 2. 附件 / OCR 零件全有但未串成证据链

- 附件模块已支持 `attachment_type='confirmation'` + `reference_type='confirmation_list'`
- OCR 有 `extract_confirmation_reply`（正则抽回函金额/日期/主体，标 `governed=False` / `requires_human_confirmation=True`）
- **但**：OCR 结果不自动回写台账 `confirmed_amount`、不与账面数自动比对、无"上传回函 → OCR → 自动匹配到发函记录"一体流程，附件页与函证中心割裂
- 发函件 / 回函件未区分未配对；台账里看不到回函影像

## 3. 覆盖率的真·科目总体分母未全面接入

`confirmation-summary` 里"函证覆盖率 = 发函总额 ÷ 科目账面余额"这一行曾是幻影（从不计算），现已标注"（科目总体）需接入试算表审定总额，暂未计算"。真正的 per-account TB population 接线跨 D/E/F/G/H/K/L 各科目类，属 spec 级。

## 4. 停滞 / 舞弊信号是纯前端内存态

`useFraudSignalCollector` 的停滞预警与舞弊信号刷新即丢，未落 `confirmation` 表也未发事件。
