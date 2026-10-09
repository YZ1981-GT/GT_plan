# Task 25 — 交接清单核验

**日期**：2026-09-27

```
地基 IC 定义集合: ['1', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '2', '20', '3', '4', '5', '6', '7', '8', '9'] (20 条)
三份 spec 全部 IC 引用: ['1', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '2', '20', '3', '4', '5', '6', '7', '8', '9'] (20 条)
悬空引用: None
未引用: None
✅ lane1 design 未复述 IC 正文
✅ lane2 design 未复述 IC 正文
foundation 覆盖 entry (6): ['xlsx/gt-i1-intangible-assets', 'xlsx/gt-i2-development-expenditure', 'xlsx/gt-i3-goodwill', 'xlsx/gt-i4-long-term-prepaid', 'xlsx/gt-i5-other-noncurrent-assets', 'xlsx/gt-i6-research-development-expense']
lane1 覆盖 entry (2): ['xlsx/gt-i1-intangible-assets', 'xlsx/gt-i3-goodwill']
lane2 覆盖 entry (3): ['xlsx/gt-i2-development-expenditure', 'xlsx/gt-i4-long-term-prepaid', 'xlsx/gt-i5-other-noncurrent-assets']
✅ 三份 spec 全文无 U+FFFD

--- 归属对照 ---
lane 1 (i1-i3): BP-6(8 sites I1+I3) / BP-7(I1 SOE) / IC-14(I3-2 覆盖层) / I1 双区 / I3 mount=4
lane 2 (i2-i4-i5): BP-5(I4 孤儿) / BP-8②(I4 分类) / IC-16(I2 门控) / I2 第二写路径 / I5 三区+内置行
foundation (canary I6): BP-9(IC-1) / BP-10(notice) / BP-8①(I6 后置) / TB 发布链首例
```

## 结论

- IC-1~IC-20 全部有 design 正文 + 判据
- 两份 lane spec 无一条复述 IC 正文
- 6 条 entry 在三份 spec 中无重无漏
- 全文无 U+FFFD
