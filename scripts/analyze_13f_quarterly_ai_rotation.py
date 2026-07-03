#!/usr/bin/env python3
"""Summarize recent quarterly 13F rebalance files with an AI sub-industry focus."""

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from monitor_13f_ai import (
    AI_INFRA_FLOW_BUCKETS,
    business_profile,
    classify_ai_holding,
    classify_holding_context,
    matches_fragment,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO_ROOT / "reports" / "13_following" / "data"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "reports" / "13_following" / "13f_ai_subindustry_rotation_4q.md"
CSV_NAME_PATTERN = re.compile(
    r"(?P<report_date>\d{4}-\d{2}-\d{2})_13f_quarterly_rebalance_"
    r"(?P<security_type>stock|etf)_top(?P<top_limit>\d+)\.csv$"
)
AI_PROXY_ETF_RULES = (
    ("QQQ", "纳指/大型科技"),
    ("XLK", "科技板块"),
    ("VGT", "科技板块"),
    ("FTEC", "科技板块"),
    ("SOXX", "半导体"),
    ("SMH", "半导体"),
    ("XSD", "半导体"),
    ("IGV", "软件"),
    ("BOTZ", "机器人"),
    ("ROBO", "机器人"),
    ("AIQ", "AI主题"),
    ("ARKQ", "自动化/机器人"),
    ("CIBR", "网络安全"),
    ("BUG", "网络安全"),
)


@dataclass(frozen=True)
class QuarterCsvFile:
    report_date: str
    security_type: str
    top_limit: int
    path: Path


@dataclass(frozen=True)
class LeaderboardRow:
    report_date: str
    security_type: str
    ranking_type: str
    rank: int
    issuer: str
    issuer_base: str
    cusip: str
    ticker: str
    business_summary: str
    new_manager_count: int
    new_entry_total_value_usd: int
    reduced_manager_count: int
    reduced_total_value_usd: int
    holder_manager_count: int
    total_holding_value_usd: int


@dataclass(frozen=True)
class AiTaggedRow:
    row: LeaderboardRow
    ai_bucket: str
    ai_theme: str
    industry: str
    ai_relationship: str
    ai_connection: str
    ai_detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze quarterly 13F rebalance CSVs with an AI focus.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--quarters", type=int, default=4)
    return parser.parse_args()


def parse_csv_file(path: Path) -> QuarterCsvFile | None:
    match = CSV_NAME_PATTERN.match(path.name)
    if match is None:
        return None
    return QuarterCsvFile(
        report_date=match.group("report_date"),
        security_type=match.group("security_type"),
        top_limit=int(match.group("top_limit")),
        path=path,
    )


def latest_csv_files(input_dir: Path, quarter_count: int) -> list[QuarterCsvFile]:
    best_files: dict[tuple[str, str], QuarterCsvFile] = {}
    for path in sorted(input_dir.glob("*_13f_quarterly_rebalance_*_top*.csv")):
        parsed = parse_csv_file(path)
        if parsed is None:
            continue
        key = (parsed.report_date, parsed.security_type)
        existing = best_files.get(key)
        if existing is None or parsed.top_limit > existing.top_limit:
            best_files[key] = parsed

    report_dates = sorted(
        {report_date for report_date, security_type in best_files if security_type == "stock"},
        reverse=True,
    )[:quarter_count]
    selected_files: list[QuarterCsvFile] = []
    for report_date in report_dates:
        for security_type in ("stock", "etf"):
            parsed = best_files.get((report_date, security_type))
            if parsed is not None:
                selected_files.append(parsed)
    return selected_files


def parse_int(value: str) -> int:
    cleaned = value.strip()
    if not cleaned:
        return 0
    return int(cleaned)


def issuer_base_name(issuer: str) -> str:
    return re.sub(r" \([A-Z][A-Z0-9.\-]*\)$", "", issuer).strip()


def load_rows(csv_file: QuarterCsvFile) -> list[LeaderboardRow]:
    rows: list[LeaderboardRow] = []
    with csv_file.path.open("r", encoding="utf-8-sig", newline="") as input_file:
        for row in csv.DictReader(input_file):
            rows.append(
                LeaderboardRow(
                    report_date=row["report_date"],
                    security_type=row["security_type"],
                    ranking_type=row["ranking_type"],
                    rank=parse_int(row["rank"]),
                    issuer=row["issuer"],
                    issuer_base=issuer_base_name(row["issuer"]),
                    cusip=row["cusip"],
                    ticker=row.get("ticker", "").strip().upper(),
                    business_summary=row.get("business_summary", "").strip(),
                    new_manager_count=parse_int(row["new_manager_count"]),
                    new_entry_total_value_usd=parse_int(row["new_entry_total_value_usd"]),
                    reduced_manager_count=parse_int(row.get("reduced_manager_count", "0")),
                    reduced_total_value_usd=parse_int(row.get("reduced_total_value_usd", "0")),
                    holder_manager_count=parse_int(row["holder_manager_count"]),
                    total_holding_value_usd=parse_int(row["total_holding_value_usd"]),
                )
            )
    return rows


def classify_ai_bucket(issuer_name: str) -> str:
    upper_name = issuer_name.upper()
    for bucket in AI_INFRA_FLOW_BUCKETS:
        if any(matches_fragment(upper_name, fragment) for fragment in bucket.fragments):
            return bucket.name

    industry, ai_relationship, _ = classify_holding_context(issuer_name)
    ai_theme, _ = classify_ai_holding(issuer_name)

    if industry in {"Semiconductors", "Semiconductor foundry", "Semiconductor equipment", "Semiconductor IP", "EDA software"}:
        return "AI芯片/设备"
    if industry in {"AI servers", "Cloud AI infrastructure"}:
        return "AI云/算力"
    if industry in {"Data centers", "Data center power/cooling", "Power infrastructure", "Digital infrastructure"}:
        return "数据中心/电力"
    if industry == "Optical networking":
        return "光通信/网络"
    if industry in {
        "Cloud and software",
        "Internet platforms and cloud",
        "E-commerce and cloud",
        "Enterprise software",
        "Data and analytics software",
        "Data infrastructure software",
        "Edge infrastructure",
        "Observability software",
        "Cybersecurity software",
    }:
        return "AI平台/软件"
    if industry in {"Consumer electronics", "Automotive and autonomy"}:
        return "AI终端/自动驾驶"
    if "AI平台/应用" in ai_relationship:
        return "AI平台/软件"
    if "核心AI基础设施" in ai_relationship:
        return "AI芯片/设备"
    if ai_theme:
        return ai_theme
    return ""


def tag_ai_rows(rows: list[LeaderboardRow]) -> list[AiTaggedRow]:
    tagged_rows: list[AiTaggedRow] = []
    for row in rows:
        ai_bucket = classify_ai_bucket(row.issuer_base)
        if not ai_bucket:
            continue
        ai_theme, _ = classify_ai_holding(row.issuer_base)
        industry, ai_relationship, ai_connection = classify_holding_context(row.issuer_base)
        business, ai_detail = business_profile(row.issuer_base)
        tagged_rows.append(
            AiTaggedRow(
                row=row,
                ai_bucket=ai_bucket,
                ai_theme=ai_theme,
                industry=industry,
                ai_relationship=ai_relationship,
                ai_connection=ai_connection,
                ai_detail=ai_detail if ai_detail else business,
            )
        )
    return tagged_rows


def classify_ai_proxy_etf(row: LeaderboardRow) -> str:
    for fragment, label in AI_PROXY_ETF_RULES:
        if row.ticker == fragment or matches_fragment(row.issuer_base.upper(), fragment):
            return label
    upper_issuer = row.issuer_base.upper()
    if "SEMICONDUCTOR" in upper_issuer:
        return "半导体"
    if "TECH" in upper_issuer:
        return "科技板块"
    if "CYBER" in upper_issuer:
        return "网络安全"
    return ""


def format_usd(value: int) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,}"


def summarize_quarter_buckets(
    rows: list[AiTaggedRow],
    direction: str,
) -> list[tuple[str, int, int, int, str]]:
    bucket_stats: dict[str, dict[str, int | set[str]]] = defaultdict(
        lambda: {
            "manager_count": 0,
            "value_change_usd": 0,
            "total_holding_value_usd": 0,
            "issuers": set(),
        }
    )
    for tagged in rows:
        stats = bucket_stats[tagged.ai_bucket]
        if direction == "new":
            stats["manager_count"] += tagged.row.new_manager_count
            stats["value_change_usd"] += tagged.row.new_entry_total_value_usd
        else:
            stats["manager_count"] += tagged.row.reduced_manager_count
            stats["value_change_usd"] += tagged.row.reduced_total_value_usd
        stats["total_holding_value_usd"] += tagged.row.total_holding_value_usd
        issuers = stats["issuers"]
        assert isinstance(issuers, set)
        issuers.add(tagged.row.issuer_base)

    summaries: list[tuple[str, int, int, int, str]] = []
    for bucket, stats in bucket_stats.items():
        issuers = stats["issuers"]
        assert isinstance(issuers, set)
        summaries.append(
            (
                bucket,
                int(stats["manager_count"]),
                int(stats["value_change_usd"]),
                int(stats["total_holding_value_usd"]),
                "、".join(sorted(issuers)[:4]),
            )
        )
    return sorted(
        summaries,
        key=lambda item: (-item[1], -item[2], -item[3], item[0]),
    )


def build_markdown(files: list[QuarterCsvFile]) -> str:
    report_rows_by_quarter: dict[str, dict[str, list[LeaderboardRow]]] = defaultdict(dict)
    top_limit_by_quarter: dict[str, int] = {}
    for csv_file in files:
        report_rows_by_quarter[csv_file.report_date][csv_file.security_type] = load_rows(csv_file)
        top_limit_by_quarter[csv_file.report_date] = max(
            top_limit_by_quarter.get(csv_file.report_date, 0),
            csv_file.top_limit,
        )

    report_dates = sorted(report_rows_by_quarter.keys(), reverse=True)
    if not report_dates:
        raise RuntimeError("未在输入目录中找到季度 13F 调仓 CSV 文件。")

    quarter_stock_ai_new_rows: dict[str, list[AiTaggedRow]] = {}
    quarter_stock_ai_reduced_rows: dict[str, list[AiTaggedRow]] = {}
    quarter_etf_ai_new_rows: dict[str, list[LeaderboardRow]] = {}
    quarter_etf_ai_reduced_rows: dict[str, list[LeaderboardRow]] = {}
    annual_new_bucket_rows: list[AiTaggedRow] = []
    annual_reduced_bucket_rows: list[AiTaggedRow] = []
    for report_date in report_dates:
        stock_new_rows = [
            row
            for row in report_rows_by_quarter[report_date].get("stock", [])
            if row.ranking_type == "top_new_manager_count"
        ]
        stock_reduced_rows = [
            row
            for row in report_rows_by_quarter[report_date].get("stock", [])
            if row.ranking_type == "top_reduced_manager_count"
        ]
        ai_new_rows = tag_ai_rows(stock_new_rows)
        ai_reduced_rows = tag_ai_rows(stock_reduced_rows)
        quarter_stock_ai_new_rows[report_date] = ai_new_rows
        quarter_stock_ai_reduced_rows[report_date] = ai_reduced_rows
        annual_new_bucket_rows.extend(ai_new_rows)
        annual_reduced_bucket_rows.extend(ai_reduced_rows)

        quarter_etf_ai_new_rows[report_date] = [
            row
            for row in report_rows_by_quarter[report_date].get("etf", [])
            if row.ranking_type == "top_new_manager_count" and classify_ai_proxy_etf(row)
        ]
        quarter_etf_ai_reduced_rows[report_date] = [
            row
            for row in report_rows_by_quarter[report_date].get("etf", [])
            if row.ranking_type == "top_reduced_manager_count" and classify_ai_proxy_etf(row)
        ]

    latest_report_date = report_dates[0]
    quarter_new_bucket_summary = {
        report_date: summarize_quarter_buckets(quarter_stock_ai_new_rows[report_date], direction="new")
        for report_date in report_dates
    }
    quarter_reduced_bucket_summary = {
        report_date: summarize_quarter_buckets(
            quarter_stock_ai_reduced_rows[report_date],
            direction="reduced",
        )
        for report_date in report_dates
    }
    latest_new_bucket_summary = quarter_new_bucket_summary[latest_report_date]
    latest_reduced_bucket_summary = quarter_reduced_bucket_summary[latest_report_date]

    lines = [
        "# 最近4个季度13F调仓中的AI细分行业资金迁移",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 数据目录：`{DEFAULT_INPUT_DIR}`",
        f"- 样本口径：每个季度优先选取同季度可用的最大 `topN` 股票/ETF 调仓榜，本次实际为最近 {len(report_dates)} 个季度。",
        (
            "- 观察重点：`top_new_manager_count` 反映“当季新进机构最多”的方向，"
            "`top_reduced_manager_count` 反映“当季减仓/退出机构最多”的方向，"
            "`top_total_holding_value` 作为存量拥挤度背景参考。"
        ),
        "- 分析方法：以下以“单季度截面”为主，不再把 4 个季度简单合并后作为主判断依据。",
        "",
        "## 重点结论",
        "",
    ]

    if latest_new_bucket_summary:
        quarterly_new_leaders = " -> ".join(
            summary[0][0] if summary else "未识别"
            for summary in (quarter_new_bucket_summary[report_date] for report_date in reversed(report_dates))
        )
        quarterly_reduced_leaders = " -> ".join(
            summary[0][0] if summary else "未识别"
            for summary in (quarter_reduced_bucket_summary[report_date] for report_date in reversed(report_dates))
        )
        lines.extend(
            [
                (
                    f"- 最新季度 `{latest_report_date}` 的AI加仓主线是 "
                    f"**{latest_new_bucket_summary[0][0] if latest_new_bucket_summary else '未识别'}**，"
                    f"减仓主线是 **{latest_reduced_bucket_summary[0][0] if latest_reduced_bucket_summary else '未识别'}**。"
                ),
                (
                    f"- 过去 4 个季度里，AI 加仓领先细分行业的季度路径大致是：`{quarterly_new_leaders}`。"
                ),
                (
                    f"- 同期 AI 减仓领先细分行业的季度路径大致是：`{quarterly_reduced_leaders}`。"
                ),
                (
                    "- 这说明资金并非统一增减 AI，而是按季度在平台软件、算力硬件、数据中心配套和科技 ETF 之间做结构性切换。"
                ),
            ]
        )
    latest_new_etf_labels = [
        f"{row.ticker or row.issuer_base}（{classify_ai_proxy_etf(row)}）"
        for row in quarter_etf_ai_new_rows[latest_report_date][:5]
    ]
    latest_reduced_etf_labels = [
        f"{row.ticker or row.issuer_base}（{classify_ai_proxy_etf(row)}）"
        for row in quarter_etf_ai_reduced_rows[latest_report_date][:5]
    ]
    if latest_new_etf_labels:
        lines.append(
            f"- ETF 加仓层面，最新季度高频出现的 AI 代理仓位包括 {'、'.join(latest_new_etf_labels)}，说明部分资金仍通过板块 ETF 而非单票来表达 AI 风险偏好。"
        )
    if latest_reduced_etf_labels:
        lines.append(
            f"- ETF 减仓层面，最新季度被明显调出的 AI 代理仓位包括 {'、'.join(latest_reduced_etf_labels)}，显示机构也在主动压缩部分宽基科技与 AI beta 敞口。"
        )
    lines.append("")
    lines.append("## 季度导航")
    lines.append("")
    lines.append("| 季度 | AI新增机构合计 | AI减仓机构合计 | 加仓领先细分行业 | 减仓领先细分行业 | 加仓代表股 | 减仓代表股 | 加仓ETF | 减仓ETF |")
    lines.append("| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |")
    for report_date in report_dates:
        ai_new_rows = quarter_stock_ai_new_rows[report_date]
        ai_reduced_rows = quarter_stock_ai_reduced_rows[report_date]
        new_bucket_summary = quarter_new_bucket_summary[report_date]
        reduced_bucket_summary = quarter_reduced_bucket_summary[report_date]
        leading_new_bucket = new_bucket_summary[0][0] if new_bucket_summary else "未识别"
        leading_reduced_bucket = reduced_bucket_summary[0][0] if reduced_bucket_summary else "未识别"
        leading_new_names = "、".join(tagged.row.ticker or tagged.row.issuer_base for tagged in ai_new_rows[:4]) or "-"
        leading_reduced_names = "、".join(tagged.row.ticker or tagged.row.issuer_base for tagged in ai_reduced_rows[:4]) or "-"
        leading_new_etfs = "、".join(
            row.ticker or row.issuer_base for row in quarter_etf_ai_new_rows[report_date][:3]
        ) or "-"
        leading_reduced_etfs = "、".join(
            row.ticker or row.issuer_base for row in quarter_etf_ai_reduced_rows[report_date][:3]
        ) or "-"
        lines.append(
            f"| {report_date} | {sum(tagged.row.new_manager_count for tagged in ai_new_rows)} | "
            f"{sum(tagged.row.reduced_manager_count for tagged in ai_reduced_rows)} | "
            f"{leading_new_bucket} | {leading_reduced_bucket} | {leading_new_names} | {leading_reduced_names} | "
            f"{leading_new_etfs} | {leading_reduced_etfs} |"
        )

    for report_date in report_dates:
        ai_new_rows = quarter_stock_ai_new_rows[report_date]
        ai_reduced_rows = quarter_stock_ai_reduced_rows[report_date]
        new_bucket_summary = quarter_new_bucket_summary[report_date]
        reduced_bucket_summary = quarter_reduced_bucket_summary[report_date]
        new_leader = new_bucket_summary[0][0] if new_bucket_summary else "未识别"
        reduced_leader = reduced_bucket_summary[0][0] if reduced_bucket_summary else "未识别"
        new_names = "、".join(tagged.row.ticker or tagged.row.issuer_base for tagged in ai_new_rows[:5]) or "-"
        reduced_names = "、".join(tagged.row.ticker or tagged.row.issuer_base for tagged in ai_reduced_rows[:5]) or "-"

        lines.extend(
            [
                "",
                f"## {report_date} 季度分析",
                "",
                (
                    f"- 当季 AI 加仓领先细分行业：**{new_leader}**；代表股票：{new_names}。"
                ),
                (
                    f"- 当季 AI 减仓领先细分行业：**{reduced_leader}**；代表股票：{reduced_names}。"
                ),
                (
                    f"- ETF 侧的 AI 代理仓位：加仓以 "
                    f"{'、'.join(row.ticker or row.issuer_base for row in quarter_etf_ai_new_rows[report_date][:4]) or '-'} "
                    f"为主，减仓以 {'、'.join(row.ticker or row.issuer_base for row in quarter_etf_ai_reduced_rows[report_date][:4]) or '-'} 为主。"
                ),
                "",
                "### AI细分行业加仓汇总",
                "",
                "| 细分行业 | 新增机构数 | 新进持仓金额 | 当前持仓市值 | 代表公司 |",
                "| --- | ---: | ---: | ---: | --- |",
            ]
        )
        for bucket, new_manager_count, new_entry_value, total_value, issuers in new_bucket_summary[:8]:
            lines.append(
                f"| {bucket} | {new_manager_count} | {format_usd(new_entry_value)} | {format_usd(total_value)} | {issuers or '-'} |"
            )

        lines.extend(
            [
                "",
                "### AI细分行业减仓汇总",
                "",
                "| 细分行业 | 减仓机构数 | 减仓金额 | 当前持仓市值 | 代表公司 |",
                "| --- | ---: | ---: | ---: | --- |",
            ]
        )
        for bucket, reduced_manager_count, reduced_value, total_value, issuers in reduced_bucket_summary[:8]:
            lines.append(
                f"| {bucket} | {reduced_manager_count} | {format_usd(reduced_value)} | {format_usd(total_value)} | {issuers or '-'} |"
            )

        lines.extend(
            [
                "",
                "### AI重点加仓名单",
                "",
                "| 排名 | 股票 | 细分行业 | 新增机构数 | 新进持仓金额 | 业务简述 |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        ranked_new_rows = sorted(
            ai_new_rows,
            key=lambda item: (
                -item.row.new_manager_count,
                -item.row.new_entry_total_value_usd,
                -item.row.total_holding_value_usd,
                item.row.issuer_base,
            ),
        )
        for index, tagged in enumerate(ranked_new_rows[:20], start=1):
            lines.append(
                f"| {index} | {tagged.row.issuer} | {tagged.ai_bucket} | {tagged.row.new_manager_count} | "
                f"{format_usd(tagged.row.new_entry_total_value_usd)} | {tagged.row.business_summary} |"
            )

        lines.extend(
            [
                "",
                "### AI重点减仓名单",
                "",
                "| 排名 | 股票 | 细分行业 | 减仓机构数 | 减仓金额 | 业务简述 |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        ranked_reduced_rows = sorted(
            ai_reduced_rows,
            key=lambda item: (
                -item.row.reduced_manager_count,
                -item.row.reduced_total_value_usd,
                -item.row.total_holding_value_usd,
                item.row.issuer_base,
            ),
        )
        for index, tagged in enumerate(ranked_reduced_rows[:20], start=1):
            lines.append(
                f"| {index} | {tagged.row.issuer} | {tagged.ai_bucket} | {tagged.row.reduced_manager_count} | "
                f"{format_usd(tagged.row.reduced_total_value_usd)} | {tagged.row.business_summary} |"
            )

        lines.extend(
            [
                "",
                "### AI代理ETF：加仓与减仓",
                "",
                "| 方向 | 代表ETF | 主题 | 机构数 | 变动金额 |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for row in quarter_etf_ai_new_rows[report_date][:6]:
            lines.append(
                f"| 加仓 | {row.issuer} | {classify_ai_proxy_etf(row)} | {row.new_manager_count} | {format_usd(row.new_entry_total_value_usd)} |"
            )
        for row in quarter_etf_ai_reduced_rows[report_date][:6]:
            lines.append(
                f"| 减仓 | {row.issuer} | {classify_ai_proxy_etf(row)} | {row.reduced_manager_count} | {format_usd(row.reduced_total_value_usd)} |"
            )

    lines.extend(
        [
            "",
            "## 跨季度观察",
            "",
            "- 这份报告的主口径是“逐季度看当期调仓”，所以更适合判断某个季度资金在 AI 链条里具体切向了哪里，而不是看 4 季累计后的平均结果。",
            "- 如果某一季度出现“软件平台继续被加仓、宽基科技 ETF 同时被减仓”，更应理解为 AI 暴露在从被动 beta 转向主动选股，而不是 AI 主线失效。",
            "- 如果某一季度加仓端转向 `设备/制造`、`光通信/网络` 或 `数据中心/电力`，通常意味着市场当期更重视 AI 的二阶瓶颈，而不只是软件叙事。",
            "- 连续两个季度都位于减仓前列的大型科技或主题 ETF，更值得视为阶段性获利了结与仓位重配信号。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    csv_files = latest_csv_files(args.input_dir, args.quarters)
    markdown = build_markdown(csv_files)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
