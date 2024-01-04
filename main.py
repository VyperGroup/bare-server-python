import aiohttp
import asyncio
import json
import os

PORT = os.environ.get("PORT", 3000)

async def websocket_handler(req):
    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(req)

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == 'close':
                await ws.close()
            else:
                try:
                    message = json.loads(msg.data)
                    if message['type'] != 'connect':
                        raise ValueError('Invalid message type')

                    remote = message['remote']
                    headers = message['headers']
                    forward_headers = message['forwardHeaders']

                    # Add forwarded headers to the headers
                    for header in forward_headers:
                        if header in req.headers:
                            headers[header] = req.headers[header]

                    # Connect to the remote server
                    session = aiohttp.ClientSession()
                    remote_ws = await session.ws_connect(remote, headers=headers)

                    # Send the open message back to the client
                    open_message = json.dumps({
                        'type': 'open',
                        'protocol': '',
                        'setCookies': []
                    })
                    await ws.send_str(open_message)

                    # Start forwarding messages
                    await forward_messages(ws, remote_ws)

                except json.JSONDecodeError:
                    print('Invalid JSON received, closing connection')
                    await ws.close()
                except ValueError as e:
                    print(f'Error: {str(e)}, closing connection')
                    await ws.close()
                except Exception as e:
                    print(f'Error: {str(e)}')
                    await ws.close()

        elif msg.type == aiohttp.WSMsgType.ERROR:
            print('ws connection closed with exception %s' % ws.exception())

    print('websocket connection closed')
    return ws

async def forward_messages(client, remote):
    client_to_remote = asyncio.ensure_future(
        forward(client, remote))
    remote_to_client = asyncio.ensure_future(
        forward(remote, client))
    done, pending = await asyncio.wait(
        [client_to_remote, remote_to_client],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

async def forward(source, destination):
    async for msg in source:
        if msg.type == aiohttp.WSMsgType.TEXT:
            await destination.send_str(msg.data)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            await destination.send_bytes(msg.data)
        elif msg.type == aiohttp.WSMsgType.CLOSE:
            await destination.close()
        elif msg.type == aiohttp.WSMsgType.ERROR:
            raise source.exception()

async def http_handler(req):
    if req.path == "/":
        with open(os.path.join(os.path.dirname(__file__), "bare-server.json"), "r") as f:
            data = f.read()
        return aiohttp.web.Response(text=data, content_type='application/json')
    elif req.path.startswith("/v3"):
        if "x-bare-url" in req.headers:
            url = req.headers["x-bare-url"]
            headers = json.loads(req.headers.get("x-bare-headers", "{}"))
            forward_headers = json.loads(req.headers.get("x-bare-forward-headers", "[]"))
            for header in forward_headers:
                if header in req.headers:
                    headers[header] = req.headers[header]
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    content = await resp.text()
                    headers = resp.headers
                    status = resp.status
                    reason = resp.reason
            if "x-bare-pass-status" in req.headers:
                pass_status = json.loads(req.headers["x-bare-pass-status"])
                if status in pass_status:
                    status = status
                else:
                    status = 200
            else:
                status = 200
            if "x-bare-pass-headers" in req.headers:
                pass_headers = json.loads(req.headers["x-bare-pass-headers"])
                headers = {header: headers[header] for header in pass_headers if header in headers}
            headers.update({
                "Cache-Control": "no-cache",
                "ETag": headers.get("ETag", ""),
                "Content-Encoding": headers.get("Content-Encoding", ""),
                "Content-Length": headers.get("Content-Length", ""),
                "X-Bare-Status": status,
                "X-Bare-Status-Text": reason,
                "X-Bare-Headers": json.dumps(headers)
            })
            return aiohttp.web.Response(text=content, headers=headers)
        else:
            return aiohttp.web.Response(status=400, text="Missing x-bare-url header")
    else:
        return aiohttp.web.Response(status=404, text="404")

app = aiohttp.web.Application()
app.router.add_get("/", http_handler)
app.router.add_get("/", websocket_handler)
aiohttp.web.run_app(app, port=PORT)