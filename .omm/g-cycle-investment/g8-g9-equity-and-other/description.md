# G8 其他权益工具投资 / G9 其他非流动金融资产

两者结构同构（都是 `core/` + `valuation/` + `voucher/` + `handbooks/` + 四件套），
差别在**公允变动去处**与科目性质。

## G8 其他权益工具投资（`G8_ACCOUNT_CODE='1503'` ⚠ 与 G6 同码）

| 目录 | 内容 |
|---|---|
| `core/` | 审定 / 明细 / 调整 / 披露 |
| `valuation/` | 公允价值估值（非上市股权多为 Level 3） |
| `voucher/` | 凭证检查（`useG8VoucherCheck`，金额类异常可推 A13，科目 `G8_ACCOUNT_CODE`） |
| `reference/` | 参考资料 / 内嵌示例 |

- **公允变动进 OCI（4002）**，且**处置时 OCI 累计额不得转入损益**（转留存收益）——与 G6 相反，是最易做错处
- 股利收入进 **G11 投资收益（6111）**
- TB 取数用 `account_prefix` + `startsWith` 前缀匹配；回写后另存 `G8-adj-tb-writeback` 与 `G8-1-adjudicated-amount`
- 附注 **五、19**（`g8NoteSectionMap`，soe 见 `G8_SOE_NOTE_SECTION`）
- 审定完成发 `substantive:adjudicated`（带 `accountCode`），披露侧 `onAdjudicated` 按 accountCode 过滤后同步

## G9 其他非流动金融资产（1519）

| 目录 | 内容 |
|---|---|
| `core/` | 审定 / 明细 / 调整 / 披露 |
| `valuation/` | 公允价值估值 |
| `voucher/` | 凭证检查（异常推 A13，科目 1519） |

- **科目码解析最健壮**：`g9Constants` 注释明写"历史项目可能仍用 1510/1504"，
  `g9TbResolve`（`resolveG9TbRow` / `g9TbRowBalance` / `g9TbResolvedCode`）按码找不到时**按科目名称回退**
- 调整分录对方科目白名单 `G9_ADJ_ACCOUNT_OPTIONS`（1519 / 6101 公允变动损益 / 4002 OCI），
  `G9_RELATED_PREFIXES = [1519, 1510, 1504, 6101, 4002, 6111, 6701]` 用于**从集中登记反向导入时过滤本科目相关分录**
- 变动率超阈值必填原因（`G9_CHANGE_RATE_THRESHOLD`）；`missingReasonCount` / `hasMissingReasons` 做完整性门禁
- 附注 **五、20**；审定发 `substantive:adjudicated` + `g9:writeback-trial-balance`（window 事件，`forceToast`）

## 与其他元素的关系

- G8/G9 的公允变动：G9 可进 6101（损益）或 4002（OCI）视分类；G8 固定进 4002
- OCI 累计 → M9 其他综合收益
- 估值层次披露与 G1 的 CAS39 公允层次同口径
