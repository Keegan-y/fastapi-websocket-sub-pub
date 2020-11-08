from fastapi import FastAPI, WebSocket
import aioredis
import asyncio

redis = None
app = FastAPI(debug=True)

clientList = dict()


async def pubsub():
    pool = await aioredis.create_pool(
        'redis://localhost',
        minsize=5, maxsize=10)

    async def reader(channel):
        while (await channel.wait_message()):
            msg = await channel.get(encoding='utf-8')
            # ... process message ...
            print("message in {}: {}".format(channel.name, msg))

    with await pool as conn:
        await conn.execute_pubsub('subscribe', 'channel:1')
        channel = conn.pubsub_channels['channel:1']
        await reader(channel)  # wait for reader to complete
        await conn.execute_pubsub('unsubscribe', 'channel:1')
    pool.close()
    await pool.wait_closed() 


@app.on_event('startup')
async def on_startup():
    redis = await aioredis.create_pool(
        'redis://localhost', minsize=5, maxsize=50)
    loop = asyncio.get_event_loop()
    channel_task = loop.create_task(pubsub())
    pub = await aioredis.create_redis(
            'redis://localhost')
    setattr(app, 'pub', pub)
    setattr(app, 'task', channel_task)


@app.websocket("/ws/{ws_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    ws_id: str,
):
    client = str(websocket)[1:-1].split(' ')[3]

    await websocket.accept()
    if not clientList.get(ws_id, None):
        clientList[ws_id] = dict()
    clientList[ws_id][client] = {
        'ws': websocket
    }
    app.pub.publish('channel:1', len(clientList[ws_id].keys()))
    for c in clientList[ws_id]:
        await clientList[ws_id][c]['ws'].send_json({'len': len(clientList[ws_id].keys())})
    try:
        while True:
            recv = await websocket.receive_json()
            for c in clientList[ws_id]:
                await clientList[ws_id][c]['ws'].send_json(recv)
    except Exception:
        del clientList[ws_id][client]
        return

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app="main:app", reload=True, workers=4)
