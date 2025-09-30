import asyncio
import json
import logging
import random
import time
import uuid
from typing import Dict, List, Optional
import websockets
import requests
from concurrent.futures import ThreadPoolExecutor
import signal
import sys
from dotenv import load_dotenv

load_dotenv('../.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CentrifugoStressTester:
    def __init__(self, backend_url: str = "http://localhost:8787",
                 ws_url: str = "ws://localhost:3000/centrifugo/connection/websocket"):
        self.backend_url = backend_url
        self.ws_url = ws_url
        self.clients = []
        self.stats = {
            'connections_created': 0,
            'connections_failed': 0,
            'messages_sent': 0,
            'messages_received': 0,
            'reconnections': 0,
            'errors': 0
        }
        self.running = True

    def get_token(self) -> str:
        try:
            response = requests.get(f"{self.backend_url}/api/centrifugo-token")
            if response.status_code == 200:
                return response.json()["token"]
            else:
                raise Exception(f"Failed to get token: {response.status_code}")
        except Exception as e:
            logger.error(f"Error getting token: {e}")
            raise

    async def create_websocket_client(self, client_id: str, chat_id: str):
        token = self.get_token()
        reconnect_attempts = 0
        max_reconnects = 5
        while self.running and reconnect_attempts < max_reconnects:
            try:
                logger.info(f"Client {client_id}: Connecting (attempt {reconnect_attempts + 1})")
                websocket = await websockets.connect(self.ws_url)
                self.stats['connections_created'] += 1
                connect_msg = {
                    "id": 1,
                    "connect": {"token": token, "name": f"stress_client_{client_id}"}
                }
                await websocket.send(json.dumps(connect_msg))
                response = await websocket.recv()
                logger.debug(f"Client {client_id}: Connect response: {response}")
                channel = f"chat:{chat_id}"
                subscribe_msg = {
                    "id": 2,
                    "subscribe": {"channel": channel}
                }
                await websocket.send(json.dumps(subscribe_msg))
                response = await websocket.recv()
                logger.debug(f"Client {client_id}: Subscribe response: {response}")
                await self.listen_for_messages(websocket, client_id, chat_id)
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Client {client_id}: Connection closed")
                reconnect_attempts += 1
                self.stats['reconnections'] += 1
                await asyncio.sleep(random.uniform(1, 3))
            except Exception as e:
                logger.error(f"Client {client_id}: Error: {e}")
                self.stats['errors'] += 1
                reconnect_attempts += 1
                await asyncio.sleep(random.uniform(1, 3))
        if reconnect_attempts >= max_reconnects:
            logger.error(f"Client {client_id}: Max reconnection attempts reached")
            self.stats['connections_failed'] += 1

    async def listen_for_messages(self, websocket, client_id: str, chat_id: str):
        message_count = 0
        last_message_time = time.time()
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    message_count += 1
                    self.stats['messages_received'] += 1
                    last_message_time = time.time()
                    logger.debug(f"Client {client_id}: Received message {message_count}")
                    if random.random() < 0.01:
                        await self.simulate_client_issue(websocket, client_id)
                except asyncio.TimeoutError:
                    if time.time() - last_message_time > 30:
                        logger.warning(f"Client {client_id}: No messages for 30s, sending ping")
                        await websocket.ping()
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(f"Client {client_id}: Connection closed during listen")
                    break
        except Exception as e:
            logger.error(f"Client {client_id}: Listen error: {e}")
            raise

    async def simulate_client_issue(self, websocket, client_id: str):
        issues = [
            self.simulate_network_lag,
            self.simulate_tab_switch,
            self.simulate_mobile_background
        ]
        issue = random.choice(issues)
        await issue(websocket, client_id)

    async def simulate_network_lag(self, websocket, client_id: str):
        logger.info(f"Client {client_id}: Simulating network lag")
        await asyncio.sleep(random.uniform(2, 8))

    async def simulate_tab_switch(self, websocket, client_id: str):
        logger.info(f"Client {client_id}: Simulating tab switch")
        await asyncio.sleep(random.uniform(0.5, 2))

    async def simulate_mobile_background(self, websocket, client_id: str):
        logger.info(f"Client {client_id}: Simulating mobile background")
        await asyncio.sleep(random.uniform(10, 30))

    async def send_chat_messages(self, chat_id: str, num_messages: int = 10):
        for i in range(num_messages):
            try:
                messages = [{
                    "role": "user",
                    "parts": [{"type": "text", "text": f"Stress test message {i + 1}"}]
                }]
                payload = {"id": chat_id, "messages": messages}
                response = requests.post(f"{self.backend_url}/api/chat", json=payload)
                if response.status_code == 200:
                    self.stats['messages_sent'] += 1
                    logger.info(f"Sent message {i + 1} to chat {chat_id}")
                else:
                    logger.error(f"Failed to send message: {response.status_code}")
                await asyncio.sleep(random.uniform(2, 5))
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                self.stats['errors'] += 1

    async def run_stress_test(self, num_clients: int = 10, num_chats: int = 3, duration: int = 300):
        logger.info(f"Starting stress test: {num_clients} clients, {num_chats} chats, {duration}s duration")
        chat_ids = [str(uuid.uuid4()) for _ in range(num_chats)]
        client_tasks = []
        for i in range(num_clients):
            chat_id = random.choice(chat_ids)
            task = asyncio.create_task(
                self.create_websocket_client(f"client_{i}", chat_id)
            )
            client_tasks.append(task)
        message_tasks = []
        for chat_id in chat_ids:
            task = asyncio.create_task(
                self.send_chat_messages(chat_id, num_messages=duration // 10)
            )
            message_tasks.append(task)
        await asyncio.sleep(duration)
        self.running = False
        await asyncio.gather(*client_tasks, *message_tasks, return_exceptions=True)
        self.print_stats()

    def print_stats(self):
        logger.info("=== Stress Test Results ===")
        for key, value in self.stats.items():
            logger.info(f"{key}: {value}")
        if self.stats['connections_created'] > 0:
            success_rate = (self.stats['connections_created'] - self.stats['connections_failed']) / self.stats['connections_created'] * 100
            logger.info(f"Connection success rate: {success_rate:.2f}%")
        if self.stats['messages_sent'] > 0:
            delivery_rate = self.stats['messages_received'] / self.stats['messages_sent'] * 100
            logger.info(f"Message delivery rate: {delivery_rate:.2f}%")

def signal_handler(signum, frame):
    logger.info("Received interrupt signal, stopping...")
    sys.exit(0)

async def main():
    signal.signal(signal.SIGINT, signal_handler)
    tester = CentrifugoStressTester()
    scenarios = [
        {"clients": 5, "chats": 2, "duration": 60, "name": "Light Load"},
        {"clients": 20, "chats": 5, "duration": 120, "name": "Medium Load"},
        {"clients": 50, "chats": 10, "duration": 180, "name": "Heavy Load"},
    ]
    for scenario in scenarios:
        logger.info(f"\n=== Running {scenario['name']} ===")
        tester.stats = {key: 0 for key in tester.stats}
        tester.running = True
        await tester.run_stress_test(
            num_clients=scenario["clients"],
            num_chats=scenario["chats"],
            duration=scenario["duration"]
        )
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
