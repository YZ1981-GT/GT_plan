# ADR-CONSOL-105: minority_share_ratio 字段语义统一为"少数股东持股比例"

## 状态
已接受（待审计专业确认）(2026-05-31)

## 背景

同一 `minority_share_ratio` 字段两处语义不一致：

- `minority_interest_service.calculate_mi`：当少数股东持股比例直接用（`ratio = minority_share_ratio / 100` → `minority_equity = net_assets × ratio`），**正确**。
- `consol_disclosure_service` + `consol_report_service`：当母公司比例求补数 `(1 - minority_share_ratio) * 100`，**错误**（既求补数又混淆百分比/小数标度）。

后果：附注少数股东持股比例可能算反（母 80%/子 20% 显示 80%）。

## 决策

- 统一语义为"少数股东持股比例"（百分比，如 20 表示 20%）。
- 修 `consol_disclosure_service._generate_minority_interest_section`：`minority_ratio = float(mi.minority_share_ratio or 0)`，不再求补数。
- 触类旁通修 `consol_report_service._generate_minority_interest_section` 同款 `(1 - ratio) * 100` 模式。
- 加单测锁口径（test_minority_interest.py `TestB7MinorityRatioSemantics`）：母 80%/子 20% → 附注 20.00%（非 80%）。

## 后果

- 口径一致 + 单测守门防回归（Q7）。
- 代价：字段语义最终口径需审计专业确认（任务 6B.4 标 `[ ]* 待审计专业确认`）。
