from io import BytesIO
from pathlib import Path
import json
import sys
from urllib.request import Request


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import enrich_cusip_ticker_map_openfigi as enrich_module


class FakeHttpResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


def test_query_openfigi_batch_falls_back_without_exchange_code(monkeypatch) -> None:
    batch = [
        enrich_module.MissingCusip(
            cusip="01626W101",
            issuer="ALIGHT INC - COM CL A",
            security_type="stock",
        )
    ]
    responses = [
        [{}],
        [
            {
                "data": [
                    {"ticker": "ALITUSD", "name": "ALIGHT INC - CLASS A", "exchCode": "X1"},
                    {"ticker": "ALITEUR", "name": "ALIGHT INC - CLASS A", "exchCode": "X2"},
                ]
            }
        ],
    ]

    def fake_urlopen(request: Request, timeout: int = 30):
        del request, timeout
        return FakeHttpResponse(responses.pop(0))

    monkeypatch.setattr(enrich_module.urllib.request, "urlopen", fake_urlopen)

    rows = enrich_module.query_openfigi_batch(batch)

    assert rows == [{"cusip": "01626W101", "ticker": "ALIT", "issuer": "ALIGHT INC - CLASS A"}]


def test_query_openfigi_batch_prefers_plain_symbol(monkeypatch) -> None:
    batch = [
        enrich_module.MissingCusip(
            cusip="254709108",
            issuer="DISCOVER FINL SVCS",
            security_type="stock",
        )
    ]
    responses = [
        [
            {
                "data": [
                    {"ticker": "DFSUSD", "name": "DISCOVER FINANCIAL SERVICES", "exchCode": "XS"},
                    {"ticker": "DFS*", "name": "DISCOVER FINANCIAL SERVICES", "exchCode": "MF"},
                    {"ticker": "DFS", "name": "DISCOVER FINANCIAL SERVICES", "exchCode": "AV"},
                ]
            }
        ]
    ]

    def fake_urlopen(request: Request, timeout: int = 30):
        del request, timeout
        return FakeHttpResponse(responses.pop(0))

    monkeypatch.setattr(enrich_module.urllib.request, "urlopen", fake_urlopen)

    rows = enrich_module.query_openfigi_batch(batch)

    assert rows == [{"cusip": "254709108", "ticker": "DFS", "issuer": "DISCOVER FINANCIAL SERVICES"}]
