import json
import os
from pathlib import Path
from pypdl import Pypdl,pypdl
import logging
logging.basicConfig(level=logging.DEBUG)
class GameUpdater:
    def __init__(self, download_root, concurrent_files=2):
        self.root = Path(download_root)
        # 1. 实例化官方 pypdl 对象
        # allow_reuse=True 允许在多次 start 之间复用 session
        print(Pypdl,pypdl)
        self.dl = Pypdl(allow_reuse=True, max_concurrent=concurrent_files)
        
        # 用于存储 {文件路径: 期望MD5} 的映射表，供回调使用
        self.md5_lookup = {}

    def _prepare_directories(self, directories):
        """预先创建目录"""
        print(">>> 正在构建目录结构...")
        for d in directories:
            dir_path = self.root / d['path']
            dir_path.mkdir(parents=True, exist_ok=True)

    def _on_download_complete(self, status, result):
        """
        符合 pypdl API 的回调函数
        status: bool
        result: FileValidator 对象 (官方自带)
        """
        # result.path 是 pypdl FileValidator 对象的属性，存储了下载文件的绝对路径
        file_path_str = str(Path(result.path).resolve())
        if status:
            # 从查找表中获取该文件的原始 MD5
            expected_md5 = self.md5_lookup.get(file_path_str)
            
            if expected_md5:
                # 2. 调用官方 result 对象的 validate_hash 方法
                # 注意：官方 validate_hash 返回的是 bool
                is_valid = result.validate_hash(correct_hash=expected_md5, algorithm='md5')
                
                if is_valid:
                    print(f"✅ [校验通过] {Path(result.path).name}")
                else:
                    print(f"❌ [校验失败] {Path(result.path).name} MD5不匹配")
            else:
                print(f"⚠️ [未知文件] {Path(result.path).name} 下载成功但未找到校验信息")
        else:
            # 下载失败时 result 为 None 或包含错误信息
            print(f"⛔ [下载失败] 任务出错")

    def process_json(self, json_data):
        main_content = json_data.get('data', {}).get('main_content', {})
        
        # --- A. 创建目录 ---
        self._prepare_directories(main_content.get('directories', []))
        
        # --- B. 构建任务列表 ---
        tasks = []
        self.md5_lookup.clear() # 清空旧数据
        
        print(">>> 正在生成任务队列...")
        for file_info in main_content.get('files', []):
            # 构造绝对路径
            abs_path = (self.root / file_info['path']).resolve()
            
            # 记录 MD5 到查找表，Key 是绝对路径字符串
            self.md5_lookup[str(abs_path)] = file_info['md5']
            
            # 添加到 pypdl 任务列表
            tasks.append({
                'url': file_info['url'],
                'file_path': str(abs_path)
            })

        # start 会阻塞直到所有任务完成
        # hash_algorithms='md5' 告诉 pypdl 在下载过程中预计算 MD5
        self.dl.start(
            tasks=tasks, 
            hash_algorithms='md5', 
            display=True,  # 开启自带进度条
            callback=self._on_download_complete,
            headers={
                "user-agent":"aria2/1.36.0FeverGame"
            }
        )

# ==========================================
# 调用示例
# ==========================================
if __name__ == "__main__":
    # 模拟你的 JSON
    input_json = {
      "data": {
        "main_content": {
          "files": [
            {
              "path": "res/chr.npk",
              "md5": "ecded174daa290ad1dbe247fb4f06c11", 
              "size": 5670060528, 
              # 请替换为有效 URL 进行测试
              "url": "https://h55-h.gdl.netease.com/a50_package__v1_i_73_2547/376f65bd575ad7e1a4ccae2ccf6c6356/chr.npk",
              "op": 1
            }
          ],
          "directories": [
            {"path": "res", "op": 1},
            {"path": "ccmini", "op": 1}
          ]
        }
      }
    }

    # 1. 初始化更新器
    updater = GameUpdater(download_root="./GameClient", concurrent_files=2)
    
    # 2. 传入 JSON 开始工作
    updater.process_json(input_json)