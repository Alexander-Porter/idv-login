import os
import json
import requests
from datetime import datetime
from envmgr import genv
from const import manual_login_channels
from logutil import setup_logger

logger = setup_logger(__name__)

class CloudRes:
    def __init__(self, url, cache_dir):
        self.url = url
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, 'cache.json')
        self.local_data = self.load_local_cache()

    def fetch_json_from_url(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch JSON from URL: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            return None

    def load_local_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def update_cache_if_needed(self):
        cloud_data = self.fetch_json_from_url()
        if cloud_data:
            cloud_last_modified = cloud_data.get('lastModified', 0)
            local_last_modified = self.local_data.get('lastModified', 0)
            if cloud_last_modified > local_last_modified:
                self.local_data = cloud_data
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cloud_data, f, ensure_ascii=False, indent=4)
                logger.info("Cache updated with new data from cloud.")
            else:
                logger.info("Local cache is up-to-date.")
        else:
            logger.warning("Using local cache due to invalid cloud data.")

    def get_channelData(self, channelName,shortGameId):
        data=self.local_data.get('data', [])
        for item in data:
            if item.get('app_channel') == channelName and item.get('game_id') == shortGameId:
                return item
