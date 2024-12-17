import asyncio
import websockets
from websockets.asyncio.server import ServerConnection
import redis.asyncio as redis
import ssl
import os
import json

HOST = "0.0.0.0"
PORT = 80

CONNECTIONS = set()


async def register(websocket: ServerConnection):
	credentials_valid = await check_credentials(websocket=websocket)
	if credentials_valid:
		CONNECTIONS.add(websocket)
		try:
			async def test_send_loop():
				while True:
					await websocket.send("Ping!")
					await asyncio.sleep(10)
			looping_task = asyncio.create_task(test_send_loop())
			await websocket.wait_closed()
			looping_task.cancel()
		except websockets.ConnectionClosed:
			pass
		finally:
			CONNECTIONS.remove(websocket)
	else:
		await websocket.close()


async def check_credentials(websocket: ServerConnection) -> bool:
	"""
	Intercepts the first message from a new connection,
	and checks for a specified token / password.
	"""
	try:
		async with asyncio.timeout(10):
			first_message = await websocket.recv()
		json_message = json.loads(first_message)
	except asyncio.TimeoutError:
		return False
	except json.decoder.JSONDecodeError:
		return False
	else:
		if json_message.get("operation") == "UPDATE":
			if json_message.get("data", {}).get("token") == "Hello!":
				return True
		return False


async def forward_redis_messages(pubsub: redis.client.PubSub):
	"""
	Forwards all JSON messages from the PubSub connection to all connected clients.
	"""
	async for message in pubsub.listen():
		if message is not None:
			try:
				json_message = json.loads(message.get("data", ""))
			except json.JSONDecodeError:
				pass
			else:
				websockets.broadcast(
					connections=CONNECTIONS,
					message=json_message
				)


async def main():
	ssl_context = ssl.create_default_context()
	redis_host = os.environ.get("REDIS_HOST", "localhost")
	redis_connection = await redis.Redis(host=redis_host, port=6379, decode_responses=True)
	async with redis_connection.pubsub() as pubsub:
		await pubsub.subscribe("telepathy:json")
		async with websockets.serve(
			handler=register,
			host=HOST,
			port=PORT,
			ssl=ssl_context,
		):
			await forward_redis_messages(pubsub=pubsub)

if __name__ == "__main__":
	asyncio.run(main())
