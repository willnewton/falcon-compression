import falcon
from falcon import testing
import pytest

from falcon_compression.middleware import CompressionMiddleware, parse_q_list

from .data import large_data, large_data_bytes

def test_parse_q_list():
    s = "br"
    assert parse_q_list(s) == ["br"]
    s = " br, gzip "
    assert parse_q_list(s) == ["br", "gzip"]
    s = " br, gzip;q=0.8,zstd;q=0.9 "
    assert parse_q_list(s) == ["br", "zstd", "gzip"]
    s = "gzip;q=0.0 , zstd"
    assert parse_q_list(s) == ["zstd"]


class LargeDataResource:
    def on_get(self, req, resp):
        resp.text = large_data

@pytest.fixture
def client():
    app = falcon.App(middleware=[CompressionMiddleware()])
    app.add_route('/large_data', LargeDataResource())
    return testing.TestClient(app)

class TestCompressionMiddleware:
    def test_no_accept_encoding(self, client):
        result = client.simulate_get('/large_data')
        assert len(result.content) == large_data_bytes
        assert not 'Content-Encoding' in result.headers

    def test_unsupported_encoding(self, client):
        headers = {
            'Accept-Encoding': 'deflate',
        }
        result = client.simulate_get('/large_data', headers=headers)
        assert len(result.content) == large_data_bytes
        assert not 'Content-Encoding' in result.headers

    def test_gzip_compression(self, client):
        headers = {
            'Accept-Encoding': 'deflate,gzip;q=0.8',
        }
        result = client.simulate_get('/large_data', headers=headers)
        assert len(result.content) < large_data_bytes
        assert result.headers['Content-Encoding'] == 'gzip' 
    
    def test_brotli_compression(self, client):
        headers = {
            'Accept-Encoding': 'br,gzip',
        }
        result = client.simulate_get('/large_data', headers=headers)
        assert len(result.content) < large_data_bytes
        assert result.headers['Content-Encoding'] == 'br' 
