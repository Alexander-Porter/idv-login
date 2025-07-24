import subprocess
import requests
import base64
import json
import sys

class HttpDNSBlocker:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self.__initialized:
            return
        self.to_be_blocked = ["103.71.201.4","13.248.222.62","76.223.88.1"]
        self.blocked = []
        self.dns_url = "https://dns.update.netease.com/hdserver"
        self.timeout = 2  # 2 seconds timeout
        self.update_dns_ips()
        self.__initialized = True
        
    def block_ip(self, target_ip):
        if sys.platform!='win32':
            return False
        try:
            # Block outbound communication
            result = subprocess.run([
                'netsh', 'advfirewall', 'firewall', 'add', 'rule',
                'name=Block_Outbound_IP', 'dir=out', 'action=block',
                'remoteip={}'.format(target_ip), 'enable=yes'
            ], shell=True,capture_output=True)
            
            if result.returncode != 0:
                return False
                
            # Block inbound communication
            result = subprocess.run([
                'netsh', 'advfirewall', 'firewall', 'add', 'rule',
                'name=Block_Inbound_IP', 'dir=in', 'action=block',
                'remoteip={}'.format(target_ip), 'enable=yes'
            ], shell=True,capture_output=True)
            
            if result.returncode != 0:
                return False
                
            return True
        except Exception:
            return False

    def unblock_ip(self, target_ip):
        try:
            # Remove outbound rule
            result = subprocess.run([
                'netsh', 'advfirewall', 'firewall', 'delete', 'rule',
                'name=Block_Outbound_IP', 'dir=out', 'remoteip={}'.format(target_ip)
            ], shell=True,capture_output=True)
            
            if result.returncode != 0:
                return False
                
            # Remove inbound rule
            result = subprocess.run([
                'netsh', 'advfirewall', 'firewall', 'delete', 'rule',
                'name=Block_Inbound_IP', 'dir=in', 'remoteip={}'.format(target_ip)
            ], shell=True,capture_output=True)
            
            if result.returncode != 0:
                return False

            return True
        except Exception:
            return False

    def update_dns_ips(self):
        try:
            # Get the latest DNS IPs without proxy
            response = requests.get(self.dns_url, timeout=self.timeout)
            if response.status_code == 200:
                # Decode the base64 content
                decoded_content = base64.b64decode(response.text).decode('utf-8')
                dns_data = json.loads(decoded_content)
                
                # Update the IPs to be blocked
                self.to_be_blocked = dns_data.get("mainland", []) + dns_data.get("oversea", [])
                return True
        except Exception as e:
            print(f"Error updating DNS IPs: {e}")
        return False

    def apply_blocking(self):
        # First unblock any previously blocked IPs that are no longer in the list
        for ip in list(self.blocked):
            if ip not in self.to_be_blocked:
                if self.unblock_ip(ip):
                    self.blocked.remove(ip)
        
        # Then block any new IPs that haven't been blocked yet
        for ip in self.to_be_blocked:
            if ip not in self.blocked:
                if self.block_ip(ip):
                    self.blocked.append(ip)

    def unblock_all(self):
        for ip in self.blocked:
            self.unblock_ip(ip)
        self.blocked = []
if __name__=='__main__':
    HttpDNSBlocker().apply_blocking()