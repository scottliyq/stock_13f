# 2026-07-03 sync-13f 四季度 Supabase 直写重跑记录

## 目标

- 将 `sync-13f` 从“生成本地 CSV 再衍生 mart”改为“直接写入 Supabase”。
- 执行真实的 4 个季度 13F 重跑。
- 保持 `sync-13dg` 默认滚动窗口为 30 天。

## 本次改动

- `sync-13f` 改为通过结构化 13F ZIP 在内存中构建 quarterly movers rows，直接 upsert 到 `mart_13f_quarterly_movers`。
- `sync-13f` 不再把本地 CSV 作为主产物，执行结果中的 `output_paths` 为空数组。
- `8-K` / `13D-G` 的证券 universe 改为直接读取 Supabase 中的 `mart_13f_quarterly_movers`。
- `rebuild-marts` 改为从 Supabase mart 读取数据重建快照，不再依赖 `reports/13_following/data/*.csv`。
- 修复了 `sync-13f` 在批量 upsert 时的重复 `row_key` 问题。

## 验证

### 测试

- `python -m pytest -q`
- 结果：`35 passed`

### dry-run

- `python scripts/backend_sync.py --dry-run sync-13f --quarters 4 --top-limit 100`
- 返回季度：
  - `2026-03-31`
  - `2025-12-31`
  - `2025-09-30`
  - `2025-06-30`

### 真实重跑

- `python scripts/backend_sync.py sync-13f --quarters 4 --top-limit 100`
- 最终结果：
  - `status=success`
  - `rows_written=2299`
  - `report_dates=["2026-03-31","2025-12-31","2025-09-30","2025-06-30"]`
  - `output_paths=[]`

### mart 重建

- `python scripts/backend_sync.py rebuild-marts`
- 最终结果：
  - `status=success`
  - `rows_written=26`
  - `mover_row_count=2299`
  - `source_table=mart_13f_quarterly_movers`

### Supabase 核验

- `mart_13f_quarterly_movers` 总行数：`2299`
- 分季度行数：
  - `2026-03-31`: `575`
  - `2025-12-31`: `574`
  - `2025-09-30`: `574`
  - `2025-06-30`: `576`

### 本地 CSV 核验

- 执行：
  - `find reports/13_following/data -type f -name '*13f_quarterly_rebalance*csv' -mmin -15 | sort`
- 结果为空，说明本次重跑未改写本地 13F leaderboard CSV。

## 13D/G 默认窗口

- `src/stock_13f/domain/sync_requests.py` 中 `Sync13DGRequest.days_back` 默认值仍为 `30`。
- 结论：后续滚动 30 天窗口无需额外改动。

## 相关文件

- `src/stock_13f/core/supabase.py`
- `src/stock_13f/adapters/structured_13f_dataset.py`
- `src/stock_13f/repositories/marts.py`
- `src/stock_13f/repositories/security_universe.py`
- `src/stock_13f/services/thirteenf_sync_service.py`
- `src/stock_13f/services/eightk_sync_service.py`
- `src/stock_13f/services/thirteendg_sync_service.py`
- `src/stock_13f/services/marts_service.py`
- `tests/test_supabase.py`
- `tests/test_security_universe.py`
- `tests/test_thirteenf_sync_service.py`
