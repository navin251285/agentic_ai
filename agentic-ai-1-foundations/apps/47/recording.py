"""Cassette settings shared by the tests and the notebook."""
import os
from pathlib import Path
import vcr

CASSETTES = Path(__file__).parent / "cassettes"
SECRET_HEADERS = ["x-goog-api-key", "authorization", "x-api-key", "cookie", "set-cookie"]
SECRET_QUERY = ["key", "api_key"]

def drop_secret_headers(response: dict) -> dict:
    """Responses can carry cookies too; drop them before saving."""
    for name in list(response["headers"]):
        if name.lower() in SECRET_HEADERS:
            response["headers"].pop(name)
    return response

def make_vcr(record_mode: str | None = None) -> vcr.VCR:
    return vcr.VCR(
        cassette_library_dir=str(CASSETTES),
        record_mode=record_mode or os.environ.get("SCOUT_RECORD", "none"),   # CI default: replay only
        match_on=["method", "host", "path", "body"],
        filter_headers=SECRET_HEADERS,              # removed from every recorded request
        filter_query_parameters=SECRET_QUERY,       # ...and from the URL
        before_record_response=drop_secret_headers,
        decode_compressed_response=True,            # readable JSON in the file, not gzip bytes
    )
