# 任务：抽凭证据绑定（attachment-voucher-evidence-binding）

实施在远端线候选树（远端分支头 + 本 spec 改动）上做；每个任务的测试写在任务里，标完成须有测试通过的证据。
后端用例在 `backend/tests/attachment_voucher_evidence/`（下称 `AVE/`），命令 `python -m pytest -p no:playwright <文件>`（cwd `backend`）；前端命令 `npx vitest run <文件>`（cwd `audit-platform/frontend`）。变异编号见 design §8.3。

- [x] 1. 迁移 V230 / R230 + ORM `voucher_key`；`EvidencePosition` / `build_position` / `create_evidence` / `WpEvidenceService.create_link` / 链接列表带凭证键；凭证键校验；带凭证键缺省证据类型 voucher；按唯一索引幂等；上传、建链接、批量链接、识别依赖收字段（需求 1.1~1.4，ADR-AVE-01/05）
  - 证据：`AVE/test_voucher_key_position.py` 6 例、`AVE/test_voucher_evidence_pg.py::test_unique_index_allows_other_position_only` 全过；变异 D1~D4、D28 红；共享开发库已执行 V230
- [x] 2. `services/voucher_evidence.py`：他稿查询端点（序时账路由组）与引用端点（底稿证据路由）；可见性、同凭证、归档 423、统一门、500 上限（需求 2，ADR-AVE-02/07）
  - 收尾补端点级鉴权用例：非成员 / 只读成员、真 PG 角色矩阵（design §8.2-10）
  - 证据：`AVE/test_voucher_reuse.py` 6 例、`AVE/test_voucher_evidence_pg.py` 可见性与角色矩阵 4 例全过；变异 D5~D8、D25、D26、D29~D31 红；走查引用 200、附件 id 与源底稿相同
- [x] 3. 证据声明：行级链接类型参与判定；「凭证」类声明逐笔样本统计 `samples`（需求 5，ADR-AVE-06）
  - 证据：`AVE/test_voucher_samples.py` 前两例全过；变异 D9、D10、D27 红
- [x] 4. 归档：「06-抽样记录汇总」追加抽凭样本证据；完整性「证据缺口」列缺证据样本（需求 6）
  - 证据：`AVE/test_voucher_samples.py` 后两例全过；变异 D11、D11b 红；走查完整性与章节只读生成（design §8.5-6）
- [x] 5. 前端基础：链接类型、`voucherEvidenceOf`（设计名 `linksOfVoucher`，design §8.2-2）、上传带凭证键、位置标签、`rowVoucherKey`、`appendRowEvidence` 第四参数、`buildLinkedOcrFormData` 透传、`shiftIndexedRowEvidence` 保留凭证键、他稿证据仓（需求 1.4、1.5、3.4）
  - 证据：`rowEvidence.spec.ts`、`workpaperEvidence.spec.ts`、`useWpEvidenceLinks.spec.ts`、`useVoucherEvidenceIndex.spec.ts`（5 例）全过；变异 D12、D13、D15 红
- [x] 6. 「来源」列凭证证据组件 `VoucherEvidenceTag`：份数、预览、移除、上传、他稿提示与引用、只读与锁定行（需求 3）
  - 年度取凭证键自带的年度，不收宿主传的年度（design §8.2-1）
  - 证据：`VoucherEvidenceTag.spec.ts` 9 例全过；变异 D14、D17 红；走查上传 / 引用 / 只读 / 移除（design §8.5）
- [x] 7. 行内识别 / 附件槽位带凭证键：凭证检查宿主调用处传行，`ItemAttachment` 新 prop 与 F1 / F3 / F4 弹窗；守卫与豁免清单（需求 4.1、4.3、4.5）
  - 守卫范围加宿主父组件以 `:row=` 渲染的弹窗，抓到并修 F3 / F4 凭证检查弹窗漏传行（design §8.2-5）；豁免 3 条
  - 证据：`VoucherEvidenceKeyGuard.spec.ts` 14 例全过（宿主 80 / 文件 361 / 含调用 47）；变异 D16、D18~D21 红
- [x] 8. 就地预览留下的 6 个文件接行内位置、小眼睛与凭证键并删豁免；H1 盘点汇总照片列改小眼睛（需求 4.2、4.4）
  - E1 两个文件用表页级位置、不带凭证键（design §8.2-7）；`attachmentEyeExemptions.json` 11 → 5；`NativeLoadBearerGuard` 删 H1 失效登记
  - 证据：`AttachmentEyeCoverageGuard.spec.ts` 14 例、`NativeLoadBearerGuard.spec.ts` 全过
- [x] 9. 抽屉逐笔统计；序时账凭证层带证据，明细层照旧（需求 5.2、7.1，ADR-AVE-08；原写「凭证层与明细层」，design §8.2-9）
  - 证据：`WorkpaperAttachmentsDrawer.spec.ts` 24 例、`useVoucherLinkTags.spec.ts` 全过；变异 D22~D24 红；走查抽屉与凭证层（design §8.5-4、8.5-7）
- [x] 10. 回归：相关后端 / 前端用例在候选树与基线对比；磁盘变异；单区域 vue-tsc；行数门（需求 8.1）
  - 证据：design §8.3、§8.4（变异 32 / 32；相关后端 49 个文件、前端 141 个 spec 候选对基线；vue-tsc / ESLint 0 新增；行数门 exit 0）
- [x] 11. 浏览器走查（【测试】项目，独立前后端与无头浏览器），数据经平台路径清理并对账（需求 8.2）
  - 证据：design §8.5、§8.6
- [x] 12. 实施记录（design §8）、INDEX、memory、评估报告追加一节；提交并推送（带版本标签）
  - 证据：本提交；推送后 `git ls-remote` 核对远端分支头
