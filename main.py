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


class ConnectionManager:
	def __init__(self):
		self.HOST = "0.0.0.0"
		self.PORT = 80
		self.connections = set()
		self.redis_connection: redis.client.Redis | None = None
		self.token = "Hello!"

	async def run(self):
		ssl_context = ssl.create_default_context()
		redis_host = os.environ.get("REDIS_HOST", "localhost")
		self.redis_connection = await redis.Redis(host=redis_host, port=6379, decode_responses=True)
		async with self.redis_connection.pubsub() as pubsub:
			await pubsub.subscribe("telepathy:json")
			async with websockets.serve(
					handler=register,
					host=HOST,
					port=PORT,
					ssl=ssl_context,
			):
				await forward_redis_messages(pubsub=pubsub)

	async def handle_connection(self, websocket: ServerConnection):
		# Register
		pass

	async def check_credentials(self, websocket: ServerConnection) -> bool:
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
			if json_message.get("operation") == "AUTHENTICATE":
				if json_message.get("data", {}).get("token") == self.token:
					return True
			return False

	async def parse_received_json_message(self):
		pass

	async def forward_redis_messages(self, pubsub: redis.client.PubSub):
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
						connections=self.connections,
						message=json_message
					)


async def register(websocket: ServerConnection):
	credentials_valid = await check_credentials(websocket=websocket)
	if credentials_valid:
		CONNECTIONS.add(websocket)
		try:
			async for message in websocket:
				try:
					json_message = json.loads(message)
				except json.JSONDecodeError:
					pass
				else:
					pass
		except websockets.ConnectionClosed:
			pass
		finally:
			CONNECTIONS.remove(websocket)
	else:
		await websocket.close()





async def parse_received_json_message(json_message):
	operation = json_message.get("operation", "")
	data = json_message.get("data", {})
	match operation:
		case "UPDATE":
			# Update the status of the door.
			pass





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
