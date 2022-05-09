from .brotli import BrotliCompressor
from .gzip import GzipCompressor

MIN_SIZE = 200


def parse_q_list(s, priorities):
    values = []
    for name in s.split(","):
        q = 1.0
        if ";q=" in name:
            name, q = name.split(";q=")[:2]
            try:
                q = float(q)
            except ValueError:
                q = 0.0
            if q == 0.0:
                continue
        encoding = name.strip().lower()
        if encoding in priorities:
            values.append((encoding, priorities[encoding], q))
    values.sort(key=lambda v: v[1])
    values.sort(key=lambda v: v[2], reverse=True)
    return [v[0] for v in values]


class CompressionMiddleware:
    def __init__(self):
        self._compressors = {}
        self._priorities = {}
        self._add_compressor(GzipCompressor())
        self._add_compressor(BrotliCompressor())

    def _add_compressor(self, compressor):
        self._priorities[compressor.encoding] = compressor.priority
        self._compressors[compressor.encoding] = compressor

    def _get_compressor(self, accept_encoding):
        for encoding in parse_q_list(accept_encoding, self._priorities):
            compressor = self._compressors.get(encoding)
            if compressor:
                return compressor
        return None

    def process_response(self, req, resp, resource, req_succeeded):
        """Post-processing of the response (after routing).

        Args:
            req: Request object.
            resp: Response object.
            resource: Resource object to which the request was
                routed. May be None if no route was found
                for the request.
            req_succeeded: True if no exceptions were raised while
                the framework processed and routed the request;
                otherwise False.
        """
        accept_encoding = req.get_header("Accept-Encoding")
        if accept_encoding is None:
            return

        # If content-encoding is already set don't compress.
        if resp.get_header("Content-Encoding"):
            return

        compressor = self._get_compressor(accept_encoding)
        if compressor is None:
            return

        if resp.stream:
            resp.stream = compressor.compress_stream(resp.stream)
            resp.content_length = None
        else:
            data = resp.render_body()
            # If there is no content or it is very short then don't compress.
            if data is None or len(data) < MIN_SIZE:
                return
            compressed = compressor.compress(data)
            resp.data = compressed
            resp.text = None

        resp.set_header("Content-Encoding", compressor.encoding)
        resp.append_header("Vary", "Accept-Encoding")
