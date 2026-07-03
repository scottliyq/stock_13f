import csv
import sys
from datetime import date
from pathlib import Path
from zipfile import ZipFile


sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from export_13f_quarterly_rebalance_csv import (  # noqa: E402
    ManagerHolding,
    QuarterData,
    classify_security_type,
    dataset_url_for_report_date,
    export_quarterly_rebalance_csvs,
    quarter_csv_path,
    latest_available_report_date,
    load_quarter_data,
    recent_report_dates,
    refresh_report_csvs,
    select_latest_filings,
    ticker_for_security,
    summarize_quarter,
)


def write_dataset_zip(
    path: Path,
    submission_rows: list[dict[str, str]],
    coverpage_rows: list[dict[str, str]],
    infotable_rows: list[dict[str, str]],
    prefix: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_prefix = f"{prefix.rstrip('/')}/" if prefix else ""
    with ZipFile(path, "w") as archive:
        archive.writestr(
            f"{normalized_prefix}SUBMISSION.tsv",
            to_tsv(
                ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"],
                submission_rows,
            ),
        )
        archive.writestr(
            f"{normalized_prefix}COVERPAGE.tsv",
            to_tsv(
                [
                    "ACCESSION_NUMBER",
                    "REPORTCALENDARORQUARTER",
                    "ISAMENDMENT",
                    "AMENDMENTNO",
                    "AMENDMENTTYPE",
                    "CONFDENIEDEXPIRED",
                    "DATEDENIEDEXPIRED",
                    "DATEREPORTED",
                    "REASONFORNONCONFIDENTIALITY",
                    "FILINGMANAGER_NAME",
                    "FILINGMANAGER_STREET1",
                    "FILINGMANAGER_STREET2",
                    "FILINGMANAGER_CITY",
                    "FILINGMANAGER_STATEORCOUNTRY",
                    "FILINGMANAGER_ZIPCODE",
                    "REPORTTYPE",
                    "FORM13FFILENUMBER",
                    "CRDNUMBER",
                    "SECFILENUMBER",
                    "PROVIDEINFOFORINSTRUCTION5",
                    "ADDITIONALINFORMATION",
                ],
                coverpage_rows,
            ),
        )
        archive.writestr(
            f"{normalized_prefix}INFOTABLE.tsv",
            to_tsv(
                [
                    "ACCESSION_NUMBER",
                    "INFOTABLE_SK",
                    "NAMEOFISSUER",
                    "TITLEOFCLASS",
                    "CUSIP",
                    "FIGI",
                    "VALUE",
                    "SSHPRNAMT",
                    "SSHPRNAMTTYPE",
                    "PUTCALL",
                    "INVESTMENTDISCRETION",
                    "OTHERMANAGER",
                    "VOTING_AUTH_SOLE",
                    "VOTING_AUTH_SHARED",
                    "VOTING_AUTH_NONE",
                ],
                infotable_rows,
            ),
        )


def to_tsv(fieldnames: list[str], rows: list[dict[str, str]]) -> str:
    output_lines = ["\t".join(fieldnames)]
    for row in rows:
        output_lines.append("\t".join(row.get(field, "") for field in fieldnames))
    return "\n".join(output_lines) + "\n"


def test_dataset_url_for_report_date_handles_recent_quarters() -> None:
    assert dataset_url_for_report_date("2026-03-31").endswith("01mar2026-31may2026_form13f.zip")
    assert dataset_url_for_report_date("2025-12-31").endswith("01dec2025-28feb2026_form13f.zip")


def test_latest_available_report_date_uses_45_day_lag() -> None:
    assert latest_available_report_date(date(2026, 7, 1)) == "2026-03-31"
    assert latest_available_report_date(date(2026, 8, 20)) == "2026-06-30"


def test_recent_report_dates_counts_back_by_quarter() -> None:
    assert recent_report_dates("2026-03-31", 4) == [
        "2026-03-31",
        "2025-12-31",
        "2025-09-30",
        "2025-06-30",
    ]


def test_classify_security_type_distinguishes_stock_and_etf() -> None:
    assert classify_security_type("APPLE INC", "COM") == "stock"
    assert classify_security_type("SCHWAB CHARLES CORP", "COM") == "stock"
    assert classify_security_type("ISHARES TR", "CORE S&P 500 ETF") == "etf"
    assert classify_security_type("SPDR S&P 500 ETF TR", "TR UNIT") == "etf"


def test_ticker_for_security_prefers_cusip_map_before_name_fallback() -> None:
    assert ticker_for_security("037833100", "UNKNOWN ISSUER NAME") == "AAPL"
    assert ticker_for_security("037833100", "MICROSOFT CORP") == "AAPL"
    assert ticker_for_security("", "APPLE INC") == "AAPL"


def test_quarter_csv_path_uses_requested_top_limit(tmp_path: Path) -> None:
    assert quarter_csv_path(
        output_dir=tmp_path,
        report_date="2026-03-31",
        security_type="stock",
        top_limit=100,
    ) == (tmp_path / "2026-03-31_13f_quarterly_rebalance_stock_top100.csv")


def test_refresh_report_csvs_backfills_ticker_from_latest_map(tmp_path: Path) -> None:
    report_path = tmp_path / "2026-03-31_13f_quarterly_rebalance_stock_top100.csv"
    with report_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "report_date",
                "security_type",
                "ranking_type",
                "rank",
                "issuer",
                "cusip",
                "ticker",
                "business_summary",
                "new_manager_count",
                "new_entry_total_value_usd",
                "reduced_manager_count",
                "reduced_total_value_usd",
                "holder_manager_count",
                "total_holding_value_usd",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_new_manager_count",
                "rank": "1",
                "issuer": "APPLE INC",
                "cusip": "037833100",
                "ticker": "",
                "business_summary": "",
                "new_manager_count": "1",
                "new_entry_total_value_usd": "100",
                "reduced_manager_count": "0",
                "reduced_total_value_usd": "0",
                "holder_manager_count": "1",
                "total_holding_value_usd": "100",
            }
        )

    refreshed_paths = refresh_report_csvs(tmp_path)

    assert refreshed_paths == [report_path]
    with report_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        row = next(csv.DictReader(input_file))
    assert row["ticker"] == "AAPL"
    assert row["issuer"] == "APPLE INC (AAPL)"
    assert row["business_summary"] == "消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。"


def test_summarize_quarter_tracks_reductions_and_full_exits() -> None:
    previous_data = QuarterData(
        report_date="2025-06-30",
        manager_names_by_cik={"0001": "Manager One", "0002": "Manager Two"},
        holdings_by_cik={
            "0001": {
                "037833100|COMMON|COM": ManagerHolding(
                    name_of_issuer="APPLE INC",
                    title_of_class="COM",
                    cusip="037833100",
                    put_call="",
                    value_usd=100,
                )
            },
            "0002": {
                "037833100|COMMON|COM": ManagerHolding(
                    name_of_issuer="APPLE INC",
                    title_of_class="COM",
                    cusip="037833100",
                    put_call="",
                    value_usd=90,
                )
            },
        },
    )
    current_data = QuarterData(
        report_date="2025-09-30",
        manager_names_by_cik={"0001": "Manager One"},
        holdings_by_cik={
            "0001": {
                "037833100|COMMON|COM": ManagerHolding(
                    name_of_issuer="APPLE INC",
                    title_of_class="COM",
                    cusip="037833100",
                    put_call="",
                    value_usd=70,
                )
            }
        },
    )

    summaries = summarize_quarter(current_data=current_data, previous_data=previous_data)

    apple_summary = next(summary for summary in summaries if summary.cusip == "037833100")
    assert apple_summary.new_manager_count == 0
    assert apple_summary.reduced_manager_count == 2
    assert apple_summary.reduced_total_value_usd == 120
    assert apple_summary.holder_manager_count == 1
    assert apple_summary.total_holding_value_usd == 70


def test_export_quarterly_rebalance_csvs_removes_stale_top_limit_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "reports"
    stale_path = output_dir / "2025-09-30_13f_quarterly_rebalance_stock_top20.csv"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text("placeholder\n", encoding="utf-8")

    cache_dir = tmp_path / "cache"
    write_dataset_zip(
        cache_dir / "zip" / "2025-06-30_form13f.zip",
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "FILING_DATE": "14-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-JUN-2025",
            }
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            }
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "APPLE INC",
                "TITLEOFCLASS": "COM",
                "CUSIP": "037833100",
                "FIGI": "",
                "VALUE": "100",
                "SSHPRNAMT": "1",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "1",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            }
        ],
    )
    write_dataset_zip(
        cache_dir / "zip" / "2025-09-30_form13f.zip",
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000020",
                "FILING_DATE": "14-NOV-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-SEP-2025",
            }
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000020",
                "REPORTCALENDARORQUARTER": "30-SEP-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            }
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000020",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "MICROSOFT CORP",
                "TITLEOFCLASS": "COM",
                "CUSIP": "594918104",
                "FIGI": "",
                "VALUE": "200",
                "SSHPRNAMT": "2",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "2",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            }
        ],
    )

    output_paths = export_quarterly_rebalance_csvs(
        dataset_cache_dir=cache_dir,
        output_dir=output_dir,
        user_agent="test-agent",
        quarter_count=1,
        top_limit=100,
        latest_report_date="2025-09-30",
        skip_download=True,
    )

    assert output_paths[0].name == "2025-09-30_13f_quarterly_rebalance_stock_top100.csv"
    assert not stale_path.exists()


def test_select_latest_filings_prefers_latest_accession_for_same_cik(tmp_path: Path) -> None:
    zip_path = tmp_path / "2025-06-30_form13f.zip"
    write_dataset_zip(
        zip_path,
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000001",
                "FILING_DATE": "14-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-JUN-2025",
            },
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "FILING_DATE": "16-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR/A",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-JUN-2025",
            },
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000001",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "Y",
                "AMENDMENTNO": "1",
                "AMENDMENTTYPE": "RESTATEMENT",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
        ],
        infotable_rows=[],
    )

    selected = select_latest_filings(zip_path, "2025-06-30")

    assert selected["0000000001"].accession_number == "0001-25-000002"


def test_load_quarter_data_aggregates_duplicate_security_rows(tmp_path: Path) -> None:
    zip_path = tmp_path / "2025-06-30_form13f.zip"
    write_dataset_zip(
        zip_path,
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "FILING_DATE": "16-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR/A",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-JUN-2025",
            }
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "Y",
                "AMENDMENTNO": "1",
                "AMENDMENTTYPE": "RESTATEMENT",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            }
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "APPLE INC",
                "TITLEOFCLASS": "COM",
                "CUSIP": "037833100",
                "FIGI": "",
                "VALUE": "100",
                "SSHPRNAMT": "1",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "1",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "INFOTABLE_SK": "2",
                "NAMEOFISSUER": "APPLE INC",
                "TITLEOFCLASS": "COM",
                "CUSIP": "037833100",
                "FIGI": "",
                "VALUE": "150",
                "SSHPRNAMT": "2",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "2",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
        ],
    )

    quarter_data = load_quarter_data(zip_path, "2025-06-30")

    assert quarter_data.manager_names_by_cik["0000000001"] == "Manager One"
    assert len(quarter_data.holdings_by_cik["0000000001"]) == 1
    aggregated_holding = next(iter(quarter_data.holdings_by_cik["0000000001"].values()))
    assert aggregated_holding.value_usd == 250


def test_load_quarter_data_supports_prefixed_zip_members(tmp_path: Path) -> None:
    zip_path = tmp_path / "2025-06-30_form13f.zip"
    write_dataset_zip(
        zip_path,
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "FILING_DATE": "16-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR/A",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-JUN-2025",
            }
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "Y",
                "AMENDMENTNO": "1",
                "AMENDMENTTYPE": "RESTATEMENT",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            }
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000002",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "APPLE INC",
                "TITLEOFCLASS": "COM",
                "CUSIP": "037833100",
                "FIGI": "",
                "VALUE": "100",
                "SSHPRNAMT": "1",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "1",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            }
        ],
        prefix="01JUN2025-31AUG2025_form13f",
    )

    quarter_data = load_quarter_data(zip_path, "2025-06-30")

    assert quarter_data.manager_names_by_cik["0000000001"] == "Manager One"


def test_summarize_quarter_keeps_same_issuer_different_cusips_separate(tmp_path: Path) -> None:
    previous_zip_path = tmp_path / "2025-03-31_form13f.zip"
    current_zip_path = tmp_path / "2025-06-30_form13f.zip"
    write_dataset_zip(
        previous_zip_path,
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000001",
                "FILING_DATE": "15-MAY-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "31-MAR-2025",
            }
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000001",
                "REPORTCALENDARORQUARTER": "31-MAR-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            }
        ],
        infotable_rows=[],
    )
    write_dataset_zip(
        current_zip_path,
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "FILING_DATE": "14-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-JUN-2025",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000010",
                "FILING_DATE": "14-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000002",
                "PERIODOFREPORT": "30-JUN-2025",
            },
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000010",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager Two",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "ISHARES TR",
                "TITLEOFCLASS": "CORE S&P 500 ETF",
                "CUSIP": "464287200",
                "FIGI": "",
                "VALUE": "110",
                "SSHPRNAMT": "1",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "1",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000010",
                "INFOTABLE_SK": "2",
                "NAMEOFISSUER": "ISHARES TR",
                "TITLEOFCLASS": "RUSSELL 1000 ETF",
                "CUSIP": "464287622",
                "FIGI": "",
                "VALUE": "120",
                "SSHPRNAMT": "1",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "1",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
        ],
    )

    previous_data = load_quarter_data(previous_zip_path, "2025-03-31")
    current_data = load_quarter_data(current_zip_path, "2025-06-30")

    summaries = summarize_quarter(current_data=current_data, previous_data=previous_data)

    assert len(summaries) == 2
    assert {summary.cusip for summary in summaries} == {"464287200", "464287622"}
    assert {summary.security_type for summary in summaries} == {"etf"}
    assert {summary.issuer_name for summary in summaries} == {
        "ISHARES TR - CORE S&P 500 ETF (IVV)",
        "ISHARES TR - RUSSELL 1000 ETF (IWB)",
    }


def test_export_quarterly_rebalance_csvs_uses_full_dataset_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "data" / "13f_universe"
    output_dir = tmp_path / "13f" / "data"

    write_dataset_zip(
        cache_dir / "zip" / "2025-03-31_form13f.zip",
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000001",
                "FILING_DATE": "15-MAY-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "31-MAR-2025",
            }
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000001",
                "REPORTCALENDARORQUARTER": "31-MAR-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            }
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000001",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "APPLE INC",
                "TITLEOFCLASS": "COM",
                "CUSIP": "037833100",
                "FIGI": "",
                "VALUE": "100",
                "SSHPRNAMT": "1",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "1",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            }
        ],
    )
    write_dataset_zip(
        cache_dir / "zip" / "2025-06-30_form13f.zip",
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "FILING_DATE": "14-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-JUN-2025",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000010",
                "FILING_DATE": "14-AUG-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000002",
                "PERIODOFREPORT": "30-JUN-2025",
            },
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000010",
                "REPORTCALENDARORQUARTER": "30-JUN-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager Two",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "APPLE INC",
                "TITLEOFCLASS": "COM",
                "CUSIP": "037833100",
                "FIGI": "",
                "VALUE": "110",
                "SSHPRNAMT": "1",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "1",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
            {
                "ACCESSION_NUMBER": "0001-25-000010",
                "INFOTABLE_SK": "2",
                "NAMEOFISSUER": "NVIDIA CORP",
                "TITLEOFCLASS": "COM",
                "CUSIP": "67066G104",
                "FIGI": "",
                "VALUE": "200",
                "SSHPRNAMT": "2",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "2",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000010",
                "INFOTABLE_SK": "3",
                "NAMEOFISSUER": "NVIDIA CORP",
                "TITLEOFCLASS": "COM",
                "CUSIP": "67066G104",
                "FIGI": "",
                "VALUE": "300",
                "SSHPRNAMT": "3",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "3",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
        ],
    )
    write_dataset_zip(
        cache_dir / "zip" / "2025-09-30_form13f.zip",
        submission_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000020",
                "FILING_DATE": "14-NOV-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000001",
                "PERIODOFREPORT": "30-SEP-2025",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000020",
                "FILING_DATE": "14-NOV-2025",
                "SUBMISSIONTYPE": "13F-HR",
                "CIK": "0000000002",
                "PERIODOFREPORT": "30-SEP-2025",
            },
        ],
        coverpage_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000020",
                "REPORTCALENDARORQUARTER": "30-SEP-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager One",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000020",
                "REPORTCALENDARORQUARTER": "30-SEP-2025",
                "ISAMENDMENT": "",
                "AMENDMENTNO": "",
                "AMENDMENTTYPE": "",
                "CONFDENIEDEXPIRED": "",
                "DATEDENIEDEXPIRED": "",
                "DATEREPORTED": "",
                "REASONFORNONCONFIDENTIALITY": "",
                "FILINGMANAGER_NAME": "Manager Two",
                "FILINGMANAGER_STREET1": "",
                "FILINGMANAGER_STREET2": "",
                "FILINGMANAGER_CITY": "",
                "FILINGMANAGER_STATEORCOUNTRY": "",
                "FILINGMANAGER_ZIPCODE": "",
                "REPORTTYPE": "13F HOLDINGS REPORT",
                "FORM13FFILENUMBER": "",
                "CRDNUMBER": "",
                "SECFILENUMBER": "",
                "PROVIDEINFOFORINSTRUCTION5": "N",
                "ADDITIONALINFORMATION": "",
            },
        ],
        infotable_rows=[
            {
                "ACCESSION_NUMBER": "0001-25-000020",
                "INFOTABLE_SK": "1",
                "NAMEOFISSUER": "NVIDIA CORP",
                "TITLEOFCLASS": "COM",
                "CUSIP": "67066G104",
                "FIGI": "",
                "VALUE": "250",
                "SSHPRNAMT": "2",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "2",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
            {
                "ACCESSION_NUMBER": "0001-25-000020",
                "INFOTABLE_SK": "2",
                "NAMEOFISSUER": "MICROSOFT CORP",
                "TITLEOFCLASS": "COM",
                "CUSIP": "594918104",
                "FIGI": "",
                "VALUE": "400",
                "SSHPRNAMT": "4",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "4",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
            {
                "ACCESSION_NUMBER": "0002-25-000020",
                "INFOTABLE_SK": "3",
                "NAMEOFISSUER": "NVIDIA CORP",
                "TITLEOFCLASS": "COM",
                "CUSIP": "67066G104",
                "FIGI": "",
                "VALUE": "320",
                "SSHPRNAMT": "3",
                "SSHPRNAMTTYPE": "SH",
                "PUTCALL": "",
                "INVESTMENTDISCRETION": "SOLE",
                "OTHERMANAGER": "",
                "VOTING_AUTH_SOLE": "3",
                "VOTING_AUTH_SHARED": "0",
                "VOTING_AUTH_NONE": "0",
            },
        ],
    )

    output_paths = export_quarterly_rebalance_csvs(
        dataset_cache_dir=cache_dir,
        output_dir=output_dir,
        user_agent="test-agent",
        quarter_count=2,
        top_limit=20,
        latest_report_date="2025-09-30",
        skip_download=True,
    )

    assert [path.name for path in output_paths] == [
        "2025-09-30_13f_quarterly_rebalance_stock_top20.csv",
        "2025-09-30_13f_quarterly_rebalance_etf_top20.csv",
        "2025-06-30_13f_quarterly_rebalance_stock_top20.csv",
        "2025-06-30_13f_quarterly_rebalance_etf_top20.csv",
    ]

    with output_paths[0].open("r", encoding="utf-8-sig", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    with output_paths[1].open("r", encoding="utf-8-sig", newline="") as input_file:
        etf_rows = list(csv.DictReader(input_file))

    first_new_row = next(row for row in rows if row["ranking_type"] == "top_new_manager_count")
    first_value_row = next(row for row in rows if row["ranking_type"] == "top_total_holding_value")
    first_reduced_row = next(row for row in rows if row["ranking_type"] == "top_reduced_manager_count")

    assert first_new_row["security_type"] == "stock"
    assert first_new_row["ticker"] == "MSFT"
    assert first_new_row["cusip"] == "594918104"
    assert first_new_row["business_summary"] == "企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。"
    assert first_new_row["new_manager_count"] == "1"
    assert first_value_row["ticker"] == "NVDA"
    assert first_value_row["cusip"] == "67066G104"
    assert first_value_row["total_holding_value_usd"] == "570"
    assert first_reduced_row["ticker"] == "AAPL"
    assert first_reduced_row["reduced_manager_count"] == "1"
    assert first_reduced_row["reduced_total_value_usd"] == "110"
    assert etf_rows == []
