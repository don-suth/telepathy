import asyncio
import websockets
from websockets.asyncio.server import ServerConnection
import redis.asyncio as redis
import ssl
import os
import json


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
					handler=self.handle_connection,
					host=self.HOST,
					port=self.PORT,
					ssl=ssl_context,
			):
				await self.forward_redis_messages(pubsub=pubsub)

	async def handle_connection(self, websocket: ServerConnection):
		# Handles messages received from connections
		credentials_valid = await self.check_credentials(websocket=websocket)
		if credentials_valid:
			self.connections.add(websocket)
			try:
				async for message in websocket:
					try:
						json_message = json.loads(message)
					except json.JSONDecodeError:
						pass
					else:
						await self.parse_received_json_message(json_message=json_message)
			except websockets.ConnectionClosed:
				pass
			finally:
				self.connections.remove(websocket)
		else:
			await websocket.close()

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

	async def parse_received_json_message(self, json_message):
		operation = json_message.get("operation", "")
		data = json_message.get("data", {})
		match operation:
			case "UPDATE":
				# Update the status of the door.
				door_status = data.get("door_status")
				match door_status:
					case "OPEN":
						await self.set_door_open()
					case "CLOSED":
						await self.set_door_closed()

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
				except TypeError:
					pass
				else:
					websockets.broadcast(
						connections=self.connections,
						message=json_message
					)

	async def set_door_open(self):
		# Sets the door status to open in Redis, for other applications to pick up on.
		await self.redis_connection.set(name="door:status", value="OPEN")
		await self.redis_connection.publish(channel="door:updates", message="OPEN")

	async def set_door_closed(self):
		# Sets the door status to closed in Redis, for other applications to pick up on.
		await self.redis_connection.set(name="door:status", value="CLOSED")
		await self.redis_connection.publish(channel="door:updates", message="CLOSED")


if __name__ == "__main__":
	manager = ConnectionManager()
	asyncio.run(manager.run())
