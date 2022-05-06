
import gzip

import brotli

MIN_SIZE = 200

def parse_q_list(s):
    values = []
    for name in s.split(","):
        q = 1.0
        if ';q=' in name:
            name, q = name.split(';q=')[:2]
            try:
                q = float(q)
            except ValueError:
                q = 0.0
            if q == 0.0:
                continue
        values.append((name.strip().lower(), q))
    values.sort(key=lambda v: v[1], reverse=True)
    return [v[0] for v in values] 


class BrotliCompressor:
    encoding = "br"
    compression_level = 4

    def compress(self, data):
        return brotli.compress(data, quality=self.compression_level)


class GzipCompressor:
    encoding = "gzip"
    compression_level = 6

    def compress(self, data):
        return gzip.compress(data, compresslevel=self.compression_level,
                             mtime=0)        


class CompressionMiddleware:
    def __init__(self):
        self._compressors = [
            GzipCompressor(),
            BrotliCompressor(),
        ]

    def _get_compressor(self, accept_encoding):
        for encoding in parse_q_list(accept_encoding):
            for compressor in self._compressors:
                if encoding == compressor.encoding:
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
        # If content-encoding is already set or it's a stream don't compress.
        if resp.get_header('Content-Encoding') or resp.stream: 
            return

        data = resp.render_body()

        # If there is no content or it is very short then don't compress.
        if data is None or len(data) < MIN_SIZE:
            return

        accept_encoding = req.get_header('Accept-Encoding')
        if accept_encoding is None:
            return

        compressor = self._get_compressor(accept_encoding)
        if compressor is None:
            return

        resp.set_header('Content-Encoding', compressor.encoding)
        resp.append_header('Vary', 'Accept-Encoding')

        compressed = compressor.compress(data)
        resp.data = compressed
        resp.text = None
