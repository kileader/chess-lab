"""Bound upload bytes before multipart parsing, including chunked requests."""
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class RequestSizeLimit:
    def __init__(self, app, max_bytes=11 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        if size < 0 or size > self.max_bytes:
            return await JSONResponse({'detail': 'Request is too large. Choose a PGN smaller than 10 MB.'}, status_code=413)(scope, receive, send)
        received = 0
        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            if received > self.max_bytes:
                raise HTTPException(413, 'Request is too large. Choose a PGN smaller than 10 MB.')
            return message
        await self.app(scope, limited_receive, send)
