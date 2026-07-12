# Coatue Management LLC 补数记录

日期：2026-07-08

## 目标

- 确认并补全 `COATUE MANAGEMENT LLC`
- SEC CIK：`0001135730`
- 用户最新要求：`13D/13G` 只需要最近 3 个月

## 结果摘要

- `Coatue Management LLC / 1135730` 已经在默认机构名单和 `dim_manager_watchlist` 中，无需新增配置
- `13F` 已存在且当前研究视图口径完整：
  - 最新报告期：`2026-03-31`
  - 已覆盖最近 4 个季度
- `13D/13G` 最近 3 个月定向同步已执行：
  - 命令：`python scripts/backend_sync.py sync-13dg --mode manager --manager-ciks 1135730 --days-back 90 --max-filings 100 --form-scope all`
  - 结果：`rows_written = 0`
  - 结论：最近 3 个月没有新的 Coatue `13D/13G`

## 当前 13F 状态

- `2026-03-31` vs `2025-12-31`
  - current_holding_count = `62`
  - new_count = `26`
  - increased_count = `10`
  - decreased_count = `26`
  - exited_count = `16`
- `2025-12-31` vs `2025-09-30`
  - current_holding_count = `52`
- `2025-09-30` vs `2025-06-30`
  - current_holding_count = `74`
- `2025-06-30` vs `2025-03-31`
  - current_holding_count = `70`

## 当前 13D/G 状态

- 最近 3 个月窗口内：`0` 条
- 当前库里 Coatue 相关 `raw_13dg_sync_sources` 共 `57` 条
- 最新几条 filing：
  - `2026-02-17` `SCHEDULE 13G/A` `Hinge Health, Inc.`
  - `2026-02-17` `SCHEDULE 13G/A` `Chagee Holdings Limited`
  - `2025-08-14` `SCHEDULE 13G` `Chagee Holdings Ltd.`
  - `2025-08-14` `SCHEDULE 13G` `Hinge Health, Inc.`
  - `2025-05-15` `SCHEDULE 13G/A` `RDDT / Reddit, Inc.`

## 备注

- 在用户改口前，曾短暂启动一次全历史 `sync-13dg --mode manager --manager-ciks 1135730 --date-from 2010-01-01`
- 该任务已人工中断，但中断前已有部分历史 raw accession 写入 Supabase
- 这些历史 raw 数据不会影响“最近 3 个月”研究结论，只会让 Coatue 的底层原始库更完整
