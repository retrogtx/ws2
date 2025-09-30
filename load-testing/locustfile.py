import json
import random
import time
import uuid
from typing import Dict, List, Optional
import asyncio
import websockets
import requests
from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser
from locust.exception import RescheduleTask
import logging
from dotenv import load_dotenv
import os

load_dotenv('../.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CentrifugoWebSocketClient:
    def __init__(self, ws_url: str, token: str):
        self.ws_url = ws_url
        self.token = token
        self.websocket = None
        self.connected = False
        self.subscriptions = {}
        self.message_count = 0

    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.ws_url)
            self.connected = True
            logger.info("WebSocket connected successfully")
            connect_msg = {
                "id": 1,
                "connect": {
                    "token": self.token,
                    "name": "loadtest"
                }
            }
            await self.websocket.send(json.dumps(connect_msg))
            response = await self.websocket.recv()
            logger.info(f"Connect response: {response}")
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self.connected = False
            raise

    async def subscribe(self, channel: str):
        if not self.connected:
            raise Exception("Not connected to WebSocket")
        sub_id = len(self.subscriptions) + 2
        subscribe_msg = {
            "id": sub_id,
            "subscribe": {
                "channel": channel
            }
        }
        await self.websocket.send(json.dumps(subscribe_msg))
        response = await self.websocket.recv()
        self.subscriptions[channel] = sub_id
        logger.info(f"Subscribed to {channel}: {response}")

    async def listen_for_messages(self, timeout: float = 30.0):
        start_time = time.time()
        messages_received = 0
        try:
            while time.time() - start_time < timeout:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    messages_received += 1
                    self.message_count += 1
                    logger.debug(f"Received message: {message}")
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    break
        except Exception as e:
            logger.error(f"Error in listen_for_messages: {e}")
        return messages_received

    async def disconnect(self):
        if self.websocket:
            await self.websocket.close()
            self.connected = False

class ChatLoadTestUser(FastHttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.chat_id = str(uuid.uuid4())
        self.user_id = f"user_{random.randint(1000, 9999)}"
        self.token = None
        self.ws_client = None
        self.messages_sent = 0
        self.messages_received = 0
        self.get_centrifugo_token()

    def get_centrifugo_token(self):
        try:
            with self.client.get("/api/centrifugo-token", catch_response=True) as response:
                if response.status_code == 200:
                    self.token = response.json()["token"]
                    logger.info(f"Got token for user {self.user_id}")
                    response.success()
                else:
                    logger.error(f"Failed to get token: {response.status_code}")
                    response.failure(f"Token request failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Error getting token: {e}")
            self.client.get("/api/centrifugo-token", catch_response=True).failure(f"Exception: {str(e)}")

    @task(3)
    def send_chat_message(self):
        if not self.token:
            self.get_centrifugo_token()
            return
        messages = [
            {
                "role": "user",
                "parts": [{"type": "text", "text": self.generate_test_message()}]
            }
        ]
        payload = {
            "id": self.chat_id,
            "messages": messages
        }
        try:
            with self.client.post("/api/chat", json=payload, catch_response=True) as response:
                if response.status_code == 200:
                    data = response.json()
                    channel = data.get("channel")
                    message_id = data.get("messageId")
                    self.messages_sent += 1
                    logger.info(f"Sent message to channel {channel}, messageId: {message_id}")
                    response.success()
                else:
                    logger.error(f"Chat request failed: {response.status_code}")
                    response.failure(f"Status code: {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending chat message: {e}")

    # WebSocket testing is handled by websocket_stress.py 
    # to avoid asyncio event loop conflicts with Locust

    def generate_test_message(self) -> str:
        messages = [
            "Hello, how are you?",
            "Can you explain quantum computing?",
            "What's the weather like today?",
            "Tell me a joke",
            "How do I cook pasta?",
            "What's the meaning of life?",
            "Explain machine learning in simple terms",
            "What are the benefits of exercise?",
            "How does photosynthesis work?",
            "What's your favorite color?",
            "Can you write a detailed explanation about the history of artificial intelligence, including major milestones, key researchers, and how it has evolved over the decades?",
            "Please provide a comprehensive guide on how to build a web application from scratch, including frontend, backend, database design, and deployment strategies.",
        ]
        return random.choice(messages)

class ReconnectionTestUser(FastHttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        self.chat_id = str(uuid.uuid4())
        self.user_id = f"reconnect_user_{random.randint(1000, 9999)}"
        self.connection_attempts = 0

    @task
    def simulate_connection_drops(self):
        scenarios = [
            self.simulate_network_switch,
            self.simulate_page_reload,
            self.simulate_tab_switch,
            self.simulate_mobile_background
        ]
        scenario = random.choice(scenarios)
        scenario()

    def simulate_network_switch(self):
        logger.info(f"Simulating network switch for user {self.user_id}")
        self.send_message("Testing network switch scenario")
        time.sleep(random.uniform(2, 5))
        self.send_message("Message after network switch")

    def simulate_page_reload(self):
        logger.info(f"Simulating page reload for user {self.user_id}")
        self.send_message("Before page reload")
        response = self.client.get("/api/centrifugo-token")
        if response.status_code == 200:
            new_token = response.json()["token"]
            logger.info(f"Got new token after reload: {new_token[:20]}...")
        self.send_message("After page reload")

    def simulate_tab_switch(self):
        logger.info(f"Simulating multiple tabs for chat {self.chat_id}")
        self.send_message("Message from tab 1")
        time.sleep(0.5)
        self.send_message("Message from tab 2")

    def simulate_mobile_background(self):
        logger.info(f"Simulating mobile background for user {self.user_id}")
        self.send_message("Before going to background")
        time.sleep(random.uniform(10, 20))
        self.send_message("After returning from background")

    def send_message(self, text: str):
        messages = [{"role": "user", "parts": [{"type": "text", "text": text}]}]
        payload = {"id": self.chat_id, "messages": messages}
        try:
            response = self.client.post("/api/chat", json=payload)
            if response.status_code == 200:
                logger.info(f"Sent message: {text[:50]}...")
            else:
                logger.error(f"Failed to send message: {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    logger.info("Load test started")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    logger.info("Load test stopped")
