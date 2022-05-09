import gzip
import os

import brotli
import falcon
import pytest
from falcon import testing

from falcon_compression.middleware import CompressionMiddleware, parse_q_list

from .data import large_data, large_data_bytes, small_data, small_data_bytes


def test_parse_q_list():
    priorities = {
        "br": 1,
        "gzip": 2,
    }
    s = "br"
    assert parse_q_list(s, priorities) == ["br"]
    s = " br, gzip "
    assert parse_q_list(s, priorities) == ["br", "gzip"]
    s = " br, gzip;q=0.8,zstd;q=0.9 "
    assert parse_q_list(s, priorities) == ["br", "gzip"]
    s = "gzip;q=0.0 , br"
    assert parse_q_list(s, priorities) == ["br"]
    s = "gzip,br"
    assert parse_q_list(s, priorities) == ["br", "gzip"]
    s = "gzip,br;q=0.9"
    assert parse_q_list(s, priorities) == ["gzip", "br"]


class LargeDataResource:
    def on_get(self, req, resp):
        resp.text = large_data


class SmallDataResource:
    def on_get(self, req, resp):
        resp.text = small_data


test_data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.py")


class StreamResource:
    def on_get(self, req, resp):
        resp.stream = open(test_data_file, "rb")


@pytest.fixture
def client():
    app = falcon.App(middleware=[CompressionMiddleware()])
    app.add_route("/large_data", LargeDataResource())
    app.add_route("/small_data", SmallDataResource())
    app.add_route("/stream", StreamResource())
    return testing.TestClient(app)


@pytest.fixture
def baseline_client():
    app = falcon.App()
    app.add_route("/large_data", LargeDataResource())
    app.add_route("/small_data", SmallDataResource())
    app.add_route("/stream", StreamResource())
    return testing.TestClient(app)


class TestCompressionMiddleware:
    def test_no_accept_encoding(self, client):
        result = client.simulate_get("/large_data")
        assert len(result.content) == large_data_bytes
        assert "Content-Encoding" not in result.headers

    def test_unsupported_encoding(self, client):
        headers = {
            "Accept-Encoding": "deflate",
        }
        result = client.simulate_get("/large_data", headers=headers)
        assert len(result.content) == large_data_bytes
        assert "Content-Encoding" not in result.headers

    def test_gzip_compression(self, client):
        headers = {
            "Accept-Encoding": "deflate,gzip;q=0.8",
        }
        result = client.simulate_get("/large_data", headers=headers)
        uncompressed = gzip.decompress(result.content).decode("utf-8")
        assert len(result.content) < large_data_bytes
        assert result.headers["Content-Encoding"] == "gzip"
        assert uncompressed == large_data

    def test_small_data(self, client):
        headers = {
            "Accept-Encoding": "gzip",
        }
        result = client.simulate_get("/small_data", headers=headers)
        assert len(result.content) == small_data_bytes
        assert "Content-Encoding" not in result.headers

    def test_brotli_compression(self, client):
        headers = {
            "Accept-Encoding": "br,gzip",
        }
        result = client.simulate_get("/large_data", headers=headers)
        uncompressed = brotli.decompress(result.content).decode("utf-8")
        assert len(result.content) < large_data_bytes
        assert result.headers["Content-Encoding"] == "br"
        assert uncompressed == large_data

    def test_prefer_brotli(self, client):
        headers = {
            "Accept-Encoding": "gzip,deflate,br",
        }
        result = client.simulate_get("/large_data", headers=headers)
        assert result.headers["Content-Encoding"] == "br"

    def test_gzip_stream(self, client):
        headers = {
            "Accept-Encoding": "gzip",
        }
        result = client.simulate_get("/stream", headers=headers)
        test_data = open(test_data_file, "rb").read().decode("utf-8")
        assert len(result.content) < len(test_data)
        assert result.headers["Content-Encoding"] == "gzip"
        uncompressed = gzip.decompress(result.content).decode("utf-8")
        assert uncompressed == test_data

    def test_brotli_stream(self, client):
        headers = {
            "Accept-Encoding": "br",
        }
        result = client.simulate_get("/stream", headers=headers)
        test_data = open(test_data_file, "rb").read().decode("utf-8")
        assert len(result.content) < len(test_data)
        assert result.headers["Content-Encoding"] == "br"
        uncompressed = brotli.decompress(result.content).decode("utf-8")
        assert uncompressed == test_data

    def test_baseline_performance(self, baseline_client, benchmark):
        def do_request():
            baseline_client.simulate_get("/large_data")

        benchmark(do_request)

    def test_no_accept_encoding_performance(self, client, benchmark):
        def do_request():
            client.simulate_get("/large_data")

        benchmark(do_request)

    def test_gzip_performance(self, client, benchmark):
        headers = {
            "Accept-Encoding": "gzip",
        }

        def do_request():
            client.simulate_get("/large_data", headers=headers)

        benchmark(do_request)

    def test_brotli_performance(self, client, benchmark):
        headers = {
            "Accept-Encoding": "brotli",
        }

        def do_request():
            client.simulate_get("/large_data", headers=headers)

        benchmark(do_request)
