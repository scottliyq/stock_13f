# stock_13f

独立的 13F 全市场季度调仓项目。

项目目标：

- 下载并缓存 SEC 结构化 13F 数据集
- 生成每个季度的全市场 `stock` / `etf` 调仓 CSV
- 统计新进机构最多、总持仓市值最高、减仓机构最多三类榜单
- 维护 `cusip -> ticker` 对照表，并用 OpenFIGI 补全缺失 ticker
- 输出 AI 相关的逐季度加仓/减仓分析报告

## 项目结构

```text
stock_13f/
├── .gitignore
├── README.md
├── pyproject.toml
├── data/
│   ├── cusip_ticker_map.csv
│   └── 13f_universe/zip/
│       ├── 2025-03-31_form13f.zip
│       ├── 2025-06-30_form13f.zip
│       ├── 2025-09-30_form13f.zip
│       ├── 2025-12-31_form13f.zip
│       └── 2026-03-31_form13f.zip
├── reports/
│   └── 13_following/
│       ├── data/
│       │   ├── 2025-06-30_13f_quarterly_rebalance_stock_top100.csv
│       │   ├── 2025-06-30_13f_quarterly_rebalance_etf_top100.csv
│       │   ├── 2025-09-30_13f_quarterly_rebalance_stock_top100.csv
│       │   ├── 2025-09-30_13f_quarterly_rebalance_etf_top100.csv
│       │   ├── 2025-12-31_13f_quarterly_rebalance_stock_top100.csv
│       │   ├── 2025-12-31_13f_quarterly_rebalance_etf_top100.csv
│       │   ├── 2026-03-31_13f_quarterly_rebalance_stock_top100.csv
│       │   └── 2026-03-31_13f_quarterly_rebalance_etf_top100.csv
│       ├── 13f_ai_subindustry_rotation_4q.md
│       └── 13f_quarterly_allocation_shift_4q.md
├── scripts/
│   ├── monitor_13f_ai.py
│   ├── export_13f_quarterly_rebalance_csv.py
│   ├── enrich_cusip_ticker_map_openfigi.py
│   └── analyze_13f_quarterly_ai_rotation.py
├── src/
│   └── stock_13f/
│       └── __init__.py
├── tests/
│   ├── test_export_13f_quarterly_rebalance_csv.py
│   └── test_enrich_cusip_ticker_map_openfigi.py
```

## 目录说明

`data/`

- `cusip_ticker_map.csv`：CUSIP 到 ticker 的本地对照表
- `13f_universe/zip/`：SEC 结构化 13F 数据集缓存 ZIP

`reports/13_following/data/`

- 每个季度生成 2 个 CSV：`stock` 和 `etf`
- 每个 CSV 同时包含 3 类 `ranking_type`
- `top_new_manager_count`：当季新进机构最多
- `top_total_holding_value`：当季总持仓市值最高
- `top_reduced_manager_count`：当季减仓/退出机构最多

`reports/13_following/`

- `13f_ai_subindustry_rotation_4q.md`：AI 相关逐季度加仓/减仓分析
- `13f_quarterly_allocation_shift_4q.md`：过去 4 个季度的配置迁移摘要

`scripts/`

- `monitor_13f_ai.py`：基础规则库，包含 ticker 规则、业务描述、AI 分类规则和 SEC 请求辅助函数
- `export_13f_quarterly_rebalance_csv.py`：主导出脚本，负责读取 SEC 结构化 13F、比较相邻季度并生成 CSV
- `enrich_cusip_ticker_map_openfigi.py`：使用 OpenFIGI 补全缺失 ticker
- `analyze_13f_quarterly_ai_rotation.py`：读取 CSV，输出 AI 逐季度加仓/减仓分析报告

`tests/`

- 覆盖 CSV 导出、ticker enrichment、文件命名与刷新逻辑

## 数据流

1. `export_13f_quarterly_rebalance_csv.py` 读取 `data/13f_universe/zip/*.zip`
2. 计算季度间的新增、持仓、减仓变化
3. 生成 `reports/13_following/data/*.csv`
4. `enrich_cusip_ticker_map_openfigi.py` 识别 CSV 里缺失 ticker 的 CUSIP，并更新 `data/cusip_ticker_map.csv`
5. `analyze_13f_quarterly_ai_rotation.py` 读取 CSV，生成 Markdown 报告

## 环境

项目脚本基于 Python 3.12，当前版本只依赖标准库。

推荐运行方式：

```bash
source $(conda info --base)/etc/profile.d/conda.sh
conda activate py312aiproxy
cd /Users/scottliyq/go/codex_space/stock_13f
```

## 常用命令

定时调度后台任务（按 `config/backend_schedule.toml`，时间全部按美东 ET 解释）：

```bash
python scripts/backend_schedule.py --list-jobs
python scripts/backend_schedule.py
```

导出最近 1 个季度的 `top100` 股票/ETF 调仓 CSV：

```bash
python scripts/export_13f_quarterly_rebalance_csv.py \
  --quarters 1 \
  --top-limit 100 \
  --enrich-openfigi \
  --openfigi-batch-size 5 \
  --openfigi-sleep-seconds 2
```

固定导出某一期，例如 `2026-06-30`：

```bash
python scripts/export_13f_quarterly_rebalance_csv.py \
  --quarters 1 \
  --latest-report-date 2026-06-30 \
  --top-limit 100 \
  --enrich-openfigi \
  --openfigi-batch-size 5 \
  --openfigi-sleep-seconds 2
```

重新生成 AI 逐季度调仓报告：

```bash
python scripts/analyze_13f_quarterly_ai_rotation.py
```

## 主要产物

最新 CSV 目录：

- [reports/13_following/data](/Users/scottliyq/go/codex_space/stock_13f/reports/13_following/data)

最新 AI 报告：

- [reports/13_following/13f_ai_subindustry_rotation_4q.md](/Users/scottliyq/go/codex_space/stock_13f/reports/13_following/13f_ai_subindustry_rotation_4q.md)

## 增量刷新最新一期 13F

脚本会根据当前日期和 13F 的 45 天滞后规则自动选择“最新可用季度”。

如果你在同一个披露窗口内想反复刷新最新一期，推荐先删除“最新季度 + 上一季度”的缓存 ZIP，再重新导出：

```bash
PYTHONPATH=scripts python - <<'PY'
from datetime import date
from export_13f_quarterly_rebalance_csv import (
    latest_available_report_date,
    previous_quarter_end,
    dataset_zip_path,
    REPO_ROOT,
)

cache_dir = REPO_ROOT / "data" / "13f_universe"
latest = latest_available_report_date(date.today())
prev = previous_quarter_end(date.fromisoformat(latest)).isoformat()

for report_date in (latest, prev):
    zip_path = dataset_zip_path(cache_dir, report_date)
    if zip_path.exists():
        zip_path.unlink()
        print(f"removed {zip_path}")
PY

python scripts/export_13f_quarterly_rebalance_csv.py \
  --quarters 1 \
  --top-limit 100 \
  --enrich-openfigi \
  --openfigi-batch-size 5 \
  --openfigi-sleep-seconds 2
```

## 测试

```bash
pytest tests/test_export_13f_quarterly_rebalance_csv.py tests/test_enrich_cusip_ticker_map_openfigi.py -q
```
