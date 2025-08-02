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
    
    def get_status(self):
        """获取HTTPDNS屏蔽状态"""
        return {
            "enabled": len(self.blocked) > 0,
            "blocked_count": len(self.blocked),
            "blocked_ips": self.blocked.copy(),
            "to_be_blocked_count": len(self.to_be_blocked)
        }
    
    def toggle_blocking(self, enable=None):
        """切换HTTPDNS屏蔽状态
        Args:
            enable: True启用，False禁用，None切换当前状态
        Returns:
            dict: 操作结果和状态信息
        """
        current_enabled = len(self.blocked) > 0
        
        if enable is None:
            enable = not current_enabled
        
        try:
            if enable and not current_enabled:
                # 启用屏蔽
                self.apply_blocking()
                success = len(self.blocked) > 0
                message = f"HTTPDNS屏蔽已启用，共屏蔽{len(self.blocked)}个IP" if success else "HTTPDNS屏蔽启用失败"
            elif not enable and current_enabled:
                # 禁用屏蔽
                old_count = len(self.blocked)
                self.unblock_all()
                success = len(self.blocked) == 0
                message = f"HTTPDNS屏蔽已禁用，已解除{old_count}个IP的屏蔽" if success else "HTTPDNS屏蔽禁用失败"
            else:
                # 状态未改变
                success = True
                message = f"HTTPDNS屏蔽状态未改变（当前：{'启用' if current_enabled else '禁用'}）"
            
            return {
                "success": success,
                "message": message,
                "enabled": len(self.blocked) > 0,
                "blocked_count": len(self.blocked),
                "unblocked_count": len(self.to_be_blocked) - len(self.blocked)
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"操作失败：{str(e)}",
                "enabled": len(self.blocked) > 0,
                "blocked_count": len(self.blocked),
                "unblocked_count": len(self.to_be_blocked) - len(self.blocked)
            }
if __name__=='__main__':
    HttpDNSBlocker().apply_blocking()