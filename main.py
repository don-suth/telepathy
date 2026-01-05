import asyncio
import websockets
from websockets.asyncio.server import ServerConnection
import redis.asyncio as redis
import ssl
import os
import json
from ritual_events.from_phantasm import (
	OpenDoorEvent,
	CloseDoorEvent,
	AuthenticateEvent,
	validate_from_phantasm_json
)
from pydantic import ValidationError


class ConnectionManager:
	def __init__(self):
		self.HOST = "0.0.0.0"
		self.PORT = 80
		self.connections = set()
		self.redis_connection: redis.client.Redis | None = None
		self.token = "Hello!"

	async def run(self):
		redis_host = os.environ.get("REDIS_HOST", "localhost")
		self.redis_connection = await redis.Redis(host=redis_host, port=6379, decode_responses=True)
		async with self.redis_connection.pubsub() as pubsub:
			await pubsub.subscribe("telepathy:json")
			async with websockets.serve(
					handler=self.handle_connection,
					host=self.HOST,
					port=self.PORT,
			):
				print(f"Running on {self.HOST}:{self.PORT}")
				await self.forward_redis_messages(pubsub=pubsub)

	async def handle_connection(self, websocket: ServerConnection):
		# Handles messages received from connections
		credentials_valid = await self.check_credentials(websocket=websocket)
		if credentials_valid:
			self.connections.add(websocket)
			try:
				async for message in websocket:
					await self.parse_received_json_message(json_message=message)
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
			event = validate_from_phantasm_json(first_message)
			match event:
				case AuthenticateEvent(token=self.token):
					return True
				case _:
					return False
		except asyncio.TimeoutError:
			return False
		else:
			return False

	async def parse_received_json_message(self, json_message):
		event = validate_from_phantasm_json(json_event=json_message)
		match event:
			# Door Events currently won't be coming from Phantasm
			# case OpenDoorEvent():
			# 	await self.set_door_open()
			# case CloseDoorEvent():
			# 	await self.set_door_closed()
			case _:
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
				except TypeError:
					pass
				else:
					websockets.broadcast(
						connections=self.connections,
						message=json.dumps(json_message)
					)

	async def set_door_open(self):
		# Currently unused
		pass

	async def set_door_closed(self):
		# Currently unused
		pass


if __name__ == "__main__":
	manager = ConnectionManager()
	asyncio.run(manager.run())
