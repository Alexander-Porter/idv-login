import os
import json
import requests
from datetime import datetime
from envmgr import genv
from const import manual_login_channels
from logutil import setup_logger

logger = setup_logger()

class CloudRes:
    def __init__(self, urls, cache_dir):
        self.urls = urls
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, 'cache.json')
        self.local_data = self.load_local_cache()
        self.session = requests.Session()
        self.session.trust_env = False

    def fetch_json_from_url(self):
        for url in self.urls:
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
                return response.json()
            except requests.RequestException as e:
                logger.error(f"Failed to fetch JSON from URL {url}: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received from URL {url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error while fetching JSON from URL {url}: {e}")
        logger.error("Failed to fetch JSON from all provided URLs.")
        return None

    def load_local_cache(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse cache file: {e}")
            return {}
        except IOError as e:
            logger.error(f"Failed to read cache file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error while loading cache file: {e}")
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
                logger.info("云端配置有更新，应用成功")
            else:
                logger.info("本地配置已是最新")
        else:
            logger.warning("获取云端配置失败，将继续使用本地配置")

    def get_channelData(self, channelName,shortGameId):
        data=self.local_data.get('data', [])
        for item in data:
            if item.get('app_channel') == channelName and item.get('game_id') == shortGameId:
                return item
        return None

    def get_by_game_id(self,shortGameId):
        data=self.local_data.get('data', [])
        for item in data:
            if item.get('game_id') == shortGameId:
                return item
        return None
    def get_all_by_game_id(self,shortGameId):
        data=self.local_data.get('data', [])
        result = []
        for item in data:
            if item.get('game_id') == shortGameId:
                result.append(item)
        return result

    def get_by_game_id_and_key(self,shortGameId,key):
        data=self.local_data.get('data', [])
        for item in data:
            if item.get('game_id') == shortGameId and item.get(key) != "" and item.get(key) != None:
                return item.get(key)
        return None

    def get_version(self):
        return self.local_data.get('version', genv.get('VERSION'))

    def get_announcement(self):
        return self.local_data.get('announcement', '')

    def get_downloadUrl(self):
        return self.local_data.get('downloadUrl', '')
    
    def get_guideUrl(self):
        return self.local_data.get('guideUrl', '')
    
    def get_detail(self):
        return self.local_data.get('detail', '')
    
    def get_risk_wm(self):
        return self.local_data.get('risk_wm', '')
    
    def get_login_page(self):
        import base64
        return base64.b64decode(self.local_data.get('login_base64_page', '')).decode()