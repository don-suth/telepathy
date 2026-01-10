import asyncio
import websockets
from websockets.asyncio.server import ServerConnection
import redis.asyncio as redis
import ssl
import os
import json
from ritual_events.from_phantasm import (
	AuthenticateEvent,
	validate_from_phantasm_json
)
from ritual_events.to_phantasm import (
	UpdateClockSettingsEvent,
	OpenDoorEvent,
	CloseDoorEvent,
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
			# Subscribe to clock settings updates and door status updates
			await pubsub.subscribe("clock:updates")
			await pubsub.subscribe("door:updates")
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
			# Send the current clock settings and Door status immediately.
			await self.send_clock_settings_update()
			door_status = await self.redis_connection.get("door:status")
			if door_status != "OPEN":
				await self.send_door_closed_update()
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
			match message:
				case {"type": "message", "channel": "clock:updates", "data": "UPDATED"}:
					await self.send_clock_settings_update()
				case {"type": "message", "channel": "door:updates", "data": "OPEN"}:
					await self.send_door_open_update()
				case {"type": "message", "channel": "door:updates", "data": "CLOSED"}:
					await self.send_door_closed_update()
				case _:
					pass

	async def send_clock_settings_update(self):
		new_brightness, new_colour, new_seconds = await self.redis_connection.mget(
			["clock:brightness", "clock:colour", "clock:seconds"]
		)
		new_event = UpdateClockSettingsEvent(
			new_brightness=new_brightness,
			new_text_colour=new_colour,
			alternate_seconds=new_seconds
		)
		websockets.broadcast(
			connections=self.connections,
			message=new_event.model_dump_json()
		)

	async def send_door_open_update(self):
		new_event = OpenDoorEvent()
		websockets.broadcast(
			connections=self.connections,
			message=new_event.model_dump_json()
		)

	async def send_door_closed_update(self):
		new_event = CloseDoorEvent()
		websockets.broadcast(
			connections=self.connections,
			message=new_event.model_dump_json()
		)


if __name__ == "__main__":
	manager = ConnectionManager()
	asyncio.run(manager.run())
