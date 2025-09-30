import asyncio
import json
import logging
import time
import requests
from typing import Dict, Any
import signal
import sys
from dotenv import load_dotenv
import os

load_dotenv('../.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CentrifugoMonitor:
    def __init__(self, centrifugo_url: str = "http://localhost:8000",
                 api_key: str = None):
        self.centrifugo_url = centrifugo_url
        self.api_key = api_key or self.get_api_key()
        self.running = True
        self.metrics_history = []

    def get_api_key(self) -> str:
        try:
            with open('../config.json', 'r') as f:
                config = json.load(f)
                return config['api_key']
        except Exception as e:
            logger.error(f"Failed to get API key: {e}")
            return ""

    def get_centrifugo_stats(self) -> Dict[str, Any]:
        try:
            headers = {
                "Authorization": f"apikey {self.api_key}",
                "Content-Type": "application/json"
            }
            response = requests.post(
                f"{self.centrifugo_url}/api/info",
                headers=headers,
                json={}
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get stats: {response.status_code}")
                return {}
        except Exception as e:
            logger.error(f"Error getting Centrifugo stats: {e}")
            return {}

    def get_channels_info(self) -> Dict[str, Any]:
        try:
            headers = {
                "Authorization": f"apikey {self.api_key}",
                "Content-Type": "application/json"
            }
            response = requests.post(
                f"{self.centrifugo_url}/api/channels",
                headers=headers,
                json={}
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get channels: {response.status_code}")
                return {}
        except Exception as e:
            logger.error(f"Error getting channels info: {e}")
            return {}

    async def monitor_loop(self, interval: int = 5):
        logger.info("Starting Centrifugo monitoring...")
        while self.running:
            try:
                timestamp = time.time()
                stats = self.get_centrifugo_stats()
                channels = self.get_channels_info()
                metrics = {
                    'timestamp': timestamp,
                    'stats': stats,
                    'channels': channels,
                    'channel_count': len(channels.get('result', {}).get('channels', [])),
                    'total_connections': stats.get('result', {}).get('nodes', [{}])[0].get('num_clients', 0) if stats.get('result', {}).get('nodes') else 0
                }
                self.metrics_history.append(metrics)
                logger.info(f"Connections: {metrics['total_connections']}, "
                           f"Channels: {metrics['channel_count']}")
                if len(self.metrics_history) % 6 == 0:
                    self.print_detailed_stats(metrics)
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)

    def print_detailed_stats(self, metrics: Dict[str, Any]):
        logger.info("=== Detailed Centrifugo Stats ===")
        stats = metrics.get('stats', {}).get('result', {})
        if stats:
            nodes = stats.get('nodes', [])
            if nodes:
                node = nodes[0]
                logger.info(f"Node ID: {node.get('uid', 'unknown')}")
                logger.info(f"Clients: {node.get('num_clients', 0)}")
                logger.info(f"Channels: {node.get('num_channels', 0)}")
                logger.info(f"Subscriptions: {node.get('num_subscriptions', 0)}")
        channels = metrics.get('channels', {}).get('result', {}).get('channels', [])
        if channels:
            logger.info(f"Active channels: {len(channels)}")
            for channel in channels[:5]:
                logger.info(f"  - {channel}")

    def save_metrics(self, filename: str = None):
        if not filename:
            timestamp = int(time.time())
            filename = f"centrifugo_metrics_{timestamp}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(self.metrics_history, f, indent=2)
            logger.info(f"Metrics saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def stop(self):
        self.running = False
        logger.info("Stopping monitor...")

def signal_handler(signum, frame):
    logger.info("Received interrupt signal")
    sys.exit(0)

async def main():
    signal.signal(signal.SIGINT, signal_handler)
    monitor = CentrifugoMonitor()
    try:
        await monitor.monitor_loop()
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted")
    finally:
        monitor.save_metrics()

if __name__ == "__main__":
    asyncio.run(main())
