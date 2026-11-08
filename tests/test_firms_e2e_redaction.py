"""End-to-end redaction test: real client, real raw writer, fake MAP_KEY.

The API key travels in the request URL by design, so the outgoing request does
contain it. Everything that leaves the client (logs, exception messages,
quarantine payloads, S3 metadata) must not.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import responses

from ingestion.core.s3_writer import RawS3WriterConfig
from ingestion.firms.client import FirmsClient, FirmsCredentials
from ingestion.firms.ingest import run_ingestion
from ingestion.firms.raw_writer import RAW_PREFIX, RAW_SOURCE_SYSTEM, FirmsRawWriter

FIXTURES = Path(__file__).parent / "fixtures" / "nasa_firms_fires"
FAKE_KEY = "e2e-fake-map-key-98765"
BUCKET = "test-raw-bucket"


@pytest.fixture
def resps():
    with responses.RequestsMock() as rsps:
        yield rsps


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _register(resps, data_id, availability_fixture, body, *, status=200):
    for endpoint, payload in (
        (
            f"https://example.com/api/data_availability/csv/{FAKE_KEY}/{data_id}",
            _fixture(availability_fixture),
        ),
        (
            f"https://example.com/api/area/csv/{FAKE_KEY}/{data_id}/world/1/2026-11-07",
            body,
        ),
    ):
        resps.add(
            responses.GET,
            endpoint,
            body=payload,
            status=status,
            content_type="text/csv",
        )


def test_map_key_never_leaves_the_client(resps, caplog):
    # SNPP availability caps at 2026-11-02, the other two at 2026-11-07.
    resps.add(
        responses.GET,
        f"https://example.com/api/data_availability/csv/{FAKE_KEY}/VIIRS_SNPP_NRT",
        body=_fixture("availability_snpp.csv"),
        content_type="text/csv",
    )
    resps.add(
        responses.GET,
        f"https://example.com/api/area/csv/{FAKE_KEY}/VIIRS_SNPP_NRT/world/1/2026-11-02",
        body=_fixture("world_1_snpp.csv"),
        content_type="text/csv",
    )
    # NOAA20 returns a structurally invalid payload -> quarantine path.
    _register(resps, "VIIRS_NOAA20_NRT", "availability_noaa20.csv", b"wrong,header\n")
    # NOAA21 returns a valid CSV -> raw path.
    _register(
        resps,
        "VIIRS_NOAA21_NRT",
        "availability_noaa21.csv",
        _fixture("world_5_noaa21_head.csv"),
    )

    s3 = MagicMock()
    s3.put_object.return_value = {"ETag": '"etag"'}
    s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
    writer = FirmsRawWriter(
        RawS3WriterConfig(
            raw_bucket=BUCKET,
            raw_prefix=RAW_PREFIX,
            quarantine_prefix="quarantine/stream/nasa_firms_fires",
            source_system=RAW_SOURCE_SYSTEM,
        ),
        s3_client=s3,
    )
    client = FirmsClient(FirmsCredentials(map_key=FAKE_KEY, base_url="https://example.com"))

    with caplog.at_level(logging.DEBUG):
        summary = run_ingestion(client=client, raw_writer=writer, backfill_days=0)

    # The request URL legitimately carries the key: prove the test is not vacuous.
    assert any(FAKE_KEY in call.request.url for call in resps.calls)

    # Both the raw object and the quarantine object were written.
    assert summary["written_count"] == 1
    assert summary["quarantined_count"] == 1
    assert s3.put_object.call_count == 2

    for call in s3.put_object.call_args_list:
        assert FAKE_KEY not in json.dumps(call.kwargs, default=str)

    assert FAKE_KEY not in caplog.text
    assert FAKE_KEY not in json.dumps(summary, default=str)
