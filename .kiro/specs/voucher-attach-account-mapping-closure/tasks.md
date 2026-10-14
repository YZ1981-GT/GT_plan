# voucher-attach-account-mapping-closure — 任务清单

## 批次 1：D 循环

- [ ] 1. GtD3.vue / GtD4.vue / GtD5.vue / GtD6.vue / GtD7.vue 加 `provide('tbSourceCodes', ...)`
- [ ] 2. D3TabVoucherCheck ~ D7TabVoucherCheck 的 `importFromAttached` 改用 `inject('tbSourceCodes')` + `dSlotQueryCodes('Dx', src)`
- [ ] 3. 验证 D 循环凭证检查在有映射码时用映射码、无映射码时退兜底码

## 批次 2：E 循环

- [ ] 4. GtE1.vue 加 provide
- [ ] 5. E1TabLargeCheck 改用 inject + `e1QueryCodes(src)`

## 批次 3：F 循环

- [ ] 6. GtF1.vue / GtF3.vue / GtF4.vue 加 provide
- [ ] 7. F1TabComprehensiveCheck / F3TabVoucherCheck / F4TabVoucherCheck 改用 inject

## 批次 4：G 循环

- [ ] 8. G1~G12 底稿主组件加 provide
- [ ] 9. G1~G12 凭证检查子组件改用 inject

## 批次 5：H 循环

- [ ] 10. H1~H10 底稿主组件加 provide
- [ ] 11. H1~H10 凭证检查子组件改用 inject

## 批次 6：I/J/K/M/N 循环

- [ ] 12. I/J/K/M/N 底稿主组件加 provide
- [ ] 13. I/J/K/M/N 凭证检查子组件改用 inject

## 守卫

- [ ] 14. AccountScope 口径一致性守卫：扫描 importFromAttached 的 accountPrefixes 参数来源
- [ ] 15. 映射码优先级守卫：每个 AccountScope 的 queryCodes(src) 三层降级测试

## 验证

- [ ] 16. 真实 PG 数据验证：选一个自定义编码项目，确认挂凭导入用映射码匹配成功
