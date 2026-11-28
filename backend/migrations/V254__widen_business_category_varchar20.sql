-- V209: 加宽 projects.business_category 从 VARCHAR(10) 到 VARCHAR(20)
-- 背景：refinancing 为 11 字符，超出 String(10) 限制
-- spec: s-cycle-linkage-trimming-and-component-wiring §0.1 切换点路径 A
-- 风险：当前最长值为 'IPO'(3 字符)，无数据截断风险
ALTER TABLE projects
    ALTER COLUMN business_category TYPE VARCHAR(20);
