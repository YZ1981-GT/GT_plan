# Tasks — M 循环键名统一（占位，未开工）

> **状态：占位（2026-11-16 立项）**。等用户拍板 design §2 的路径 A / B 后再展开。
> 来源：`oo-writeback-template-parity-closure` 任务 9.2 的键名层（该 spec 已归档，
> 投影层已修完）。

- [ ] 1. 开工前置现算（不改代码）
  - [ ] 1.1 现算 M 循环 10 张表在真库的行数（`checklist_responses` 按 `wp_id` + `item_id` 前缀），判定「`placeholder` store item 是否意味着从未写入」
  - [ ] 1.2 现读 10 个 `useM{n}Detail.ts` 的存储形态（flat / 整表 JSON / 并存），逐表登记
  - [ ] 1.3 现读契约 `m*.json` 的 `review.html_store.shape` / `store_item_id` / `row_identity_kind`，逐表登记
  - [ ] 1.4 现读 `test_m_detail_keys_match_provider.py` 当前基线（M1 / M2 条数可能已被其他会话改动）
  - [ ] 1.5 现算扫描器 `contract_field_names_scan.py` 对 `{sheet}` 参数拼键的识别缺口（原 spec design §14.3 备查记录）

- [ ] 2. 用户拍板 design §2 的路径（A 统一 flat / B 按 sheet 分级声明）

- [ ] 3. 按拍板结果写完整 requirements / design / tasks（替换本占位）

- [ ] 4. 实施（按路径展开，逐表推进 + 每表真实 OO 往返验证）

- [ ] 5. 棘轮逐条偿还：每偿还一条删一条基线，守卫断言「已对齐却没删条目会红」

- [ ] 6. 收尾：干净 worktree 跑守卫、推送、登记 INDEX
