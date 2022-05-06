import gzip
from io import BytesIO

import brotli

MIN_SIZE = 200


def parse_q_list(s):
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
        values.append((name.strip().lower(), q))
    values.sort(key=lambda v: v[1], reverse=True)
    return [v[0] for v in values]


def wrap_file(file_stream, block_size=8192):
    while True:
        data = file_stream.read(block_size)
        if not data:
            break
        yield data


class BrotliCompressor:
    encoding = "br"
    compression_level = 4

    def compress(self, data):
        return brotli.compress(data, quality=self.compression_level)

    def compress_stream(self, stream):
        yield b""
        if hasattr(stream, "read"):
            stream = wrap_file(stream)
        compressor = brotli.Compressor(quality=self.compression_level)
        for block in stream:
            output = compressor.process(block)
            if output:
                yield output
        output = compressor.finish()
        if output:
            yield output


class StreamingBuffer(BytesIO):
    def read(self):
        ret = self.getvalue()
        self.seek(0)
        self.truncate()
        return ret


class GzipCompressor:
    encoding = "gzip"
    compression_level = 6

    def compress(self, data):
        return gzip.compress(data, compresslevel=self.compression_level, mtime=0)

    def compress_stream(self, stream):
        yield b""
        if not hasattr(stream, "read"):
            stream = wrap_file(stream)
        buf = StreamingBuffer()
        with gzip.GzipFile(
            mode="wb", compresslevel=self.compression_level, fileobj=buf, mtime=0
        ) as zfile:
            yield buf.read()
            for item in stream:
                zfile.write(item)
                data = buf.read()
                if data:
                    yield data
        yield buf.read()


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
