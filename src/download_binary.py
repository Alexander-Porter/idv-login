import os
import re
import requests
# -*- coding: utf-8 -*-
import zipfile
import zmq
import time
import json
import sys
import argparse

# --- UI Server 配置 ---
# 防止防火墙问题
BIND_HOST = "127.0.0.1"

# 端口定义
# 1740: UI 在这里 LISTEN (SUB)，接收 Worker 发来的进度
PORT_RECEIVE_PROGRESS = 1740
# 1737: UI 在这里 LISTEN (PUB)，向 Worker 发送心跳/指令
PORT_SEND_HEARTBEAT = 1737

# 协议常量
TOPIC = b"434"
# UI 发送的心跳内容，告诉 Worker "我准备好接收状态 4 的数据了"
UI_HEARTBEAT_PAYLOAD = b"4"
# UI 发送心跳的频率
UI_HEARTBEAT_INTERVAL_S = 1.0

def main_ui_server(topic=None, sub_port=None, pub_port=None, stop_event=None):
    if topic is None:
        topic = TOPIC
    if sub_port is None:
        sub_port = PORT_SEND_HEARTBEAT
    if pub_port is None:
        pub_port = PORT_RECEIVE_PROGRESS
    print(f"正在启动 UI Server (模拟器)...")
    print(f"模式: BIND (服务端)")
    
    context = zmq.Context()

    # 1. 创建 SUB 套接字 (用于接收 Worker 的进度)
    # 注意：在 ZMQ 中，Server 也可以是 SUB，只要它 Bind 即可。
    receiver = context.socket(zmq.SUB)
    
    # 启用 TCP Keepalive (可选，但在 Server 端是好习惯)
    receiver.setsockopt(zmq.TCP_KEEPALIVE, 1)
    
    # 关键：订阅主题
    receiver.setsockopt(zmq.SUBSCRIBE, topic)
    
    # 绑定端口 1740
    addr_recv = f"tcp://{BIND_HOST}:{pub_port}"
    try:
        receiver.bind(addr_recv)
        print(f"[*] [SUB] 已绑定于 {addr_recv} (等待 Worker 连接并汇报进度)")
    except zmq.ZMQError as e:
        print(f"[!] 无法绑定端口 {pub_port}: {e}")
        return

    # 2. 创建 PUB 套接字 (用于向 Worker 发送心跳)
    sender = context.socket(zmq.PUB)
    
    # 绑定端口 1737
    addr_send = f"tcp://{BIND_HOST}:{sub_port}"
    try:
        sender.bind(addr_send)
        print(f"[*] [PUB] 已绑定于 {addr_send} (向 Worker 广播 UI 心跳)")
    except zmq.ZMQError as e:
        print(f"[!] 无法绑定端口 {sub_port}: {e}")
        return

    print("\nUI Server 已就绪。等待 Worker 启动并连接...")
    
    last_heartbeat_time = 0
    
    # 使用 Poller 实现高效的 I/O 多路复用
    poller = zmq.Poller()
    poller.register(receiver, zmq.POLLIN)

    try:
        while True:
            if stop_event and stop_event.is_set():
                break
            # 1. 处理接收 (非阻塞)
            # poll 等待时间设为 10ms，保证循环能及时处理发送逻辑
            socks = dict(poller.poll(timeout=10))
            
            if receiver in socks:
                try:
                    message_parts = receiver.recv_multipart()
                    
                    if len(message_parts) == 3:
                        topic, msg_type, payload = message_parts
                        # 仅打印非心跳消息，或者特定的进度消息
                        if msg_type == b"4": 
                            try:
                                data = json.loads(payload.decode('utf-8'))
                                # 提取一些关键信息打印，避免刷屏
                                percent = data.get("ShowDownloadPercent", 0) * 100
                                rate = data.get("ShowDownloadRateStr", "N/A")
                                print(f"<-- [进度]  {percent:.2f}% ({rate})")
                            except:
                                print(f"<-- [数据] 类型: {msg_type}, 长度: {len(payload)}")

                except zmq.ZMQError as e:
                    print(f"接收错误: {e}")

            # 2. 处理发送 (UI 心跳)
            # Worker 需要不断收到这个消息，才会认为 UI 在线，并继续发送数据
            current_time = time.time()
            if current_time - last_heartbeat_time > UI_HEARTBEAT_INTERVAL_S:
                # 构造消息: [topic, payload] -> [b"434", b"4"]
                # 注意：Worker (Client) 那边接收的是 2-part message
                sender.send_multipart([topic, UI_HEARTBEAT_PAYLOAD])
                # print(f"--> [UI心跳] 发送 '{UI_HEARTBEAT_PAYLOAD.decode()}' 到端口 1737")
                last_heartbeat_time = current_time

    except KeyboardInterrupt:
        print("\nUI Server 正在停止...")
    except Exception as e:
        import traceback
        print(f"\nUI Server 发生异常: {e}")
        traceback.print_exc()
    finally:
        print("正在关闭 UI Server 资源...")
        try:
            receiver.setsockopt(zmq.LINGER, 0)
            sender.setsockopt(zmq.LINGER, 0)
            receiver.close()
            sender.close()
            context.term()
        except Exception as e:
            print(f"关闭资源时出错: {e}")
        print("已关闭。")
        

def download_file(filename):
    """
    下载文件到当前目录
    """
    url = f"https://gitee.com/opguess/idv-login/raw/main/binaries/{filename}"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"下载文件 {filename} 失败，状态码：{response.status_code}")
        print(response.text)
        #fallback
        url = f"https://raw.githubusercontent.com/Alexander-Porter/idv-login/refs/heads/main/binaries/{filename}"
        response = requests.get(url)
        if response.status_code != 200:
            print(f"下载文件 {filename} 失败，状态码：{response.status_code}")
            return False
    with open(filename, "wb") as f:
        f.write(response.content)
    #如果文件名以.zip结尾，原地解压
    if filename.endswith(".zip"):
        with zipfile.ZipFile(filename, 'r') as zip_ref:
            zip_ref.extractall(".")
        #删除压缩包
        os.remove(filename)
    return True
def ensure_binary():
    """
    确保二进制文件存在：binaries\downloadIPC.exe,binaries\OrbitSDK.dll
    """
    #https://gitee.com/opguess/idv-login/raw/main/binaries/aria2c.exe
    #https://gitee.com/opguess/idv-login/raw/main/binaries/downloadIPC.exe
    #https://gitee.com/opguess/idv-login/raw/main/binaries/OrbitSDK.dll
    #直接下载的工作目录
    #fallback:https://cdn.jsdelivr.net/gh/Alexander-Porter/idv-login@main/
    print("正在检查并下载依赖...")
    if os.path.exists("downloadIPC.exe") and os.path.exists("OrbitSDK.dll") and os.path.exists("aria2c.exe"):
        return True
    if not os.path.exists("downloadIPC.exe"):
        res=download_file("downloadIPC.zip")
        if not res:
            return False
    if not os.path.exists("OrbitSDK.dll"):
        res=download_file("OrbitSDK.dll")
        if not res:
            return False
    if not os.path.exists("aria2c.exe"):
        res=download_file("aria2c.exe")
        if not res:
            return False
    return True

def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-server", action="store_true")
    parser.add_argument("--topic", type=str, default="")
    parser.add_argument("--sub-port", type=int, default=PORT_SEND_HEARTBEAT)
    parser.add_argument("--pub-port", type=int, default=PORT_RECEIVE_PROGRESS)
    return parser.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    if args.ui_server:
        topic = args.topic.encode("utf-8") if args.topic else TOPIC
        main_ui_server(topic=topic, sub_port=args.sub_port, pub_port=args.pub_port)
    else:
        ensure_binary()
