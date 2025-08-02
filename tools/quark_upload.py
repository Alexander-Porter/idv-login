# -*- coding: utf-8 -*-
# ============================================================
#  QuarkUp.py
#  Author: Coke/Alist
#  Date:   2025-04-28
#  Introduce:   夸克网盘自动上传与分享脚本
#     支持大文件上传、自动生成分享链接、自动输出最终可用短链。
#     兼容 Windows、macOS、Linux 系统，适合自动化备份、批量分发等场景。
#
#  基于Go版本driver.go和util.go的逻辑重写
# ============================================================

import requests
import hashlib
import time
import json
import os
import mimetypes
import sys
import base64
import argparse
from datetime import datetime
from urllib.parse import urlencode

# 必要 Cookie，从环境变量中读取
cookies = {}
pdir_fid = ""
file_path = ""

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "dnt": "1",
    "origin": "https://pan.quark.cn",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://pan.quark.cn/",
    "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (iPod; U; CPU iPhone OS 3_3 like Mac OS X; an-ES) AppleWebKit/534.37.3 (KHTML, like Gecko) Version/4.0.5 Mobile/8B114 Safari/6534.37.3"
}

def log_step(step, detail=""):
    """日志输出每个步骤"""
    print(f"=== {step} === {detail}")

def load_config_from_env():
    """从环境变量加载配置"""
    global cookies, pdir_fid
    
    # 从环境变量读取base64编码的cookies
    cookies_b64 = os.environ.get('QUARK_COOKIES_B64')
    if cookies_b64:
        try:
            cookies_json = base64.b64decode(cookies_b64).decode('utf-8')
            cookies = json.loads(cookies_json)
            log_step("从环境变量加载Cookies成功")
        except Exception as e:
            log_step("加载Cookies失败", str(e))
            sys.exit(1)
    else:
        log_step("未找到QUARK_COOKIES_B64环境变量")
        sys.exit(1)
    
    # 从环境变量读取pdir_fid
    pdir_fid = os.environ.get('QUARK_PDIR_FID')
    if not pdir_fid:
        log_step("未找到QUARK_PDIR_FID环境变量")
        sys.exit(1)
    
    log_step("配置加载完成", f"pdir_fid: {pdir_fid}")

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='夸克网盘文件上传工具')
    parser.add_argument('file_path', help='要上传的文件路径')
    return parser.parse_args()

def get_file_hash(file_path):
    """计算文件的MD5和SHA1哈希值"""
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(8192)
            if not data:
                break
            md5.update(data)
            sha1.update(data)
    return md5.hexdigest(), sha1.hexdigest()

def make_request(url, method="POST", data=None, extra_headers=None):
    """统一的请求方法"""
    req_headers = headers.copy()
    if extra_headers:
        req_headers.update(extra_headers)
    
    params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
    
    if method == "GET":
        response = requests.get(url, headers=req_headers, cookies=cookies, params=params)
    else:
        response = requests.post(url, headers=req_headers, cookies=cookies, params=params, json=data)
    
    if response.status_code != 200:
        raise Exception(f"请求失败: {response.status_code}, {response.text}")
    
    result = response.json()
    if result.get('code', 0) != 0:
        raise Exception(f"API错误: {result.get('message', '未知错误')}")
    
    return result

def up_pre(file_path, parent_id):
    """预上传，获取上传任务信息"""
    url = "https://drive-pc.quark.cn/1/clouddrive/file/upload/pre"
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    now = int(time.time() * 1000)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    
    data = {
        "ccp_hash_update": True,
        "parallel_upload": True,
        "dir_name": "",
        "file_name": file_name,
        "format_type": mime_type,
        "l_created_at": now,
        "l_updated_at": now,
        "pdir_fid": parent_id,
        "size": file_size
    }
    
    log_step("预上传", f"文件: {file_name}, 大小: {file_size}")
    result = make_request(url, "POST", data)
    return result

def up_hash(md5_str, sha1_str, task_id):
    """更新文件哈希"""
    url = "https://drive-pc.quark.cn/1/clouddrive/file/update/hash"
    data = {
        "md5": md5_str,
        "sha1": sha1_str,
        "task_id": task_id
    }
    
    log_step("更新哈希", f"MD5: {md5_str[:8]}..., SHA1: {sha1_str[:8]}...")
    result = make_request(url, "POST", data)
    return result.get('data', {}).get('finish', False)

def up_part_auth(pre_data, mime_type, part_number):
    """获取分片上传授权"""
    url = "https://drive-pc.quark.cn/1/clouddrive/file/upload/auth"
    time_str = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    auth_meta = f"""PUT

{mime_type}
{time_str}
x-oss-date:{time_str}
x-oss-user-agent:aliyun-sdk-js/6.6.1 Chrome 98.0.4758.80 on Windows 10 64-bit
/{pre_data['bucket']}/{pre_data['obj_key']}?partNumber={part_number}&uploadId={pre_data['upload_id']}"""
    
    data = {
        "auth_info": pre_data['auth_info'],
        "auth_meta": auth_meta,
        "task_id": pre_data['task_id']
    }
    
    result = make_request(url, "POST", data)
    return result.get('data', {}), time_str

def up_part(pre_data, mime_type, part_number, part_data):
    """上传分片到OSS"""
    auth_data, time_str = up_part_auth(pre_data, mime_type, part_number)
    
    # 构建OSS上传URL
    upload_url = pre_data['upload_url']
    if upload_url.startswith('https://'):
        upload_url = upload_url[8:]  # 移除 https://
    if upload_url.startswith('http://'):
        upload_url = upload_url[7:]  # 移除 http://
    
    oss_url = f"https://{pre_data['bucket']}.{upload_url}/{pre_data['obj_key']}"
    
    oss_headers = {
        "Authorization": auth_data['auth_key'],
        "Content-Type": mime_type,
        "Referer": "https://pan.quark.cn/",
        "x-oss-date": time_str,
        "x-oss-user-agent": "aliyun-sdk-js/6.6.1 Chrome 98.0.4758.80 on Windows 10 64-bit"
    }
    
    params = {
        "partNumber": str(part_number),
        "uploadId": pre_data['upload_id']
    }
    
    log_step(f"上传分片 {part_number}", f"大小: {len(part_data)} bytes")
    response = requests.put(oss_url, data=part_data, headers=oss_headers, params=params)
    
    if response.status_code != 200:
        raise Exception(f"分片上传失败: {response.status_code}, {response.text}")
    
    etag = response.headers.get('ETag', '')
    return etag

def up_commit_auth(pre_data, content_md5, callback_base64):
    """获取提交授权"""
    url = "https://drive-pc.quark.cn/1/clouddrive/file/upload/auth"
    time_str = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    auth_meta = f"""POST
{content_md5}
application/xml
{time_str}
x-oss-callback:{callback_base64}
x-oss-date:{time_str}
x-oss-user-agent:aliyun-sdk-js/6.6.1 Chrome 98.0.4758.80 on Windows 10 64-bit
/{pre_data['bucket']}/{pre_data['obj_key']}?uploadId={pre_data['upload_id']}"""
    
    data = {
        "auth_info": pre_data['auth_info'],
        "auth_meta": auth_meta,
        "task_id": pre_data['task_id']
    }
    
    result = make_request(url, "POST", data)
    return result.get('data', {}), time_str

def up_commit(pre_data, etags):
    """提交分片信息"""
    # 构建XML body
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<CompleteMultipartUpload>']
    for i, etag in enumerate(etags, 1):
        xml_parts.extend([
            '<Part>',
            f'<PartNumber>{i}</PartNumber>',
            f'<ETag>{etag}</ETag>',
            '</Part>'
        ])
    xml_parts.append('</CompleteMultipartUpload>')
    xml_body = '\n'.join(xml_parts)
    
    # 计算Content-MD5
    content_md5 = base64.b64encode(hashlib.md5(xml_body.encode()).digest()).decode()
    
    # 准备callback
    callback_data = json.dumps(pre_data['callback'])
    callback_base64 = base64.b64encode(callback_data.encode()).decode()
    
    # 获取授权
    auth_data, time_str = up_commit_auth(pre_data, content_md5, callback_base64)
    
    # 构建OSS提交URL
    upload_url = pre_data['upload_url']
    if upload_url.startswith('https://'):
        upload_url = upload_url[8:]
    
    oss_url = f"https://{pre_data['bucket']}.{upload_url}/{pre_data['obj_key']}"
    
    oss_headers = {
        "Authorization": auth_data['auth_key'],
        "Content-MD5": content_md5,
        "Content-Type": "application/xml",
        "Referer": "https://pan.quark.cn/",
        "x-oss-callback": callback_base64,
        "x-oss-date": time_str,
        "x-oss-user-agent": "aliyun-sdk-js/6.6.1 Chrome 98.0.4758.80 on Windows 10 64-bit"
    }
    
    params = {"uploadId": pre_data['upload_id']}
    
    log_step("提交分片信息", f"共 {len(etags)} 个分片")
    response = requests.post(oss_url, data=xml_body, headers=oss_headers, params=params)
    
    if response.status_code != 200:
        raise Exception(f"提交失败: {response.status_code}, {response.text}")
    
    return True

def up_finish(pre_data):
    """完成上传"""
    url = "https://drive-pc.quark.cn/1/clouddrive/file/upload/finish"
    data = {
        "obj_key": pre_data['obj_key'],
        "task_id": pre_data['task_id']
    }
    
    log_step("完成上传")
    result = make_request(url, "POST", data)
    time.sleep(1)  # 等待1秒
    return result

def share_file(fid, title, url_type=1, expired_type=2):
    """创建分享链接"""
    url = "https://drive-pc.quark.cn/1/clouddrive/share"
    data = {
        "fid_list": [fid],
        "title": title,
        "url_type": url_type,
        "expired_type": expired_type
    }
    
    log_step("创建分享链接")
    result = make_request(url, "POST", data)
    return result

def get_share_password_info(share_id):
    """查询分享口令和最终分享链接等信息"""
    url = "https://drive-pc.quark.cn/1/clouddrive/share/password"
    data = {"share_id": share_id}
    
    log_step("查询分享口令")
    result = make_request(url, "POST", data)
    return result

def upload_file(file_path, parent_id):
    """主上传流程"""
    log_step("开始上传流程", f"文件: {file_path}")
    
    if not os.path.exists(file_path):
        raise Exception(f"文件不存在: {file_path}")
    
    # 1. 预上传
    pre_result = up_pre(file_path, parent_id)
    pre_data = pre_result['data']
    
    task_id = pre_data['task_id']
    obj_key = pre_data['obj_key']
    part_size = pre_result.get('metadata', {}).get('part_size', 10 * 1024 * 1024)  # 默认10MB
    
    log_step("获取任务信息", f"task_id: {task_id}, part_size: {part_size}")
    
    # 2. 计算文件哈希
    md5_str, sha1_str = get_file_hash(file_path)
    
    # 3. 更新哈希
    finish = up_hash(md5_str, sha1_str, task_id)
    if finish:
        log_step("文件已存在，秒传成功")
        return pre_data
    
    # 4. 分片上传
    file_size = os.path.getsize(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    
    etags = []
    part_number = 1
    
    with open(file_path, 'rb') as f:
        while True:
            part_data = f.read(part_size)
            if not part_data:
                break
            
            etag = up_part(pre_data, mime_type, part_number, part_data)
            if etag == "finish":
                log_step("上传完成（提前结束）")
                return pre_data
            
            etags.append(etag)
            part_number += 1
            
            progress = (f.tell() / file_size) * 100
            log_step(f"上传进度", f"{progress:.1f}%")
    
    # 5. 提交分片
    up_commit(pre_data, etags)
    
    # 6. 完成上传
    finish_result = up_finish(pre_data)
    
    log_step("上传流程完成")
    return finish_result

def main(upload_file_path):
    """主流程：上传文件并生成分享链接"""
    try:
        # 上传文件
        result = upload_file(upload_file_path, pdir_fid)
        
        # 获取文件ID
        fid = result.get('data', {}).get('fid')
        if not fid:
            raise Exception("未获取到文件ID")
        
        # 创建分享链接
        title = os.path.basename(upload_file_path)
        share_result = share_file(fid, title, url_type=1, expired_type=2)
        
        # 获取分享信息
        share_data = share_result.get('data', {})
        if 'task_resp' in share_data and 'data' in share_data['task_resp']:
            share_data = share_data['task_resp']['data']
        
        share_id = share_data.get('share_id')
        if not share_id:
            raise Exception("未获取到share_id")
        
        # 查询最终分享信息
        pwd_info = get_share_password_info(share_id)
        
        if 'data' in pwd_info:
            file_name = pwd_info['data'].get('title', title)
            share_url = pwd_info['data'].get('share_url')
            print(f"{file_name} 分享链接：{share_url}")
        else:
            raise Exception("未获取到最终分享链接")
            
    except Exception as e:
        log_step("上传失败", str(e))
        sys.exit(1)

if __name__ == "__main__":
    # 解析命令行参数
    args = parse_args()
    
    # 从环境变量加载配置
    load_config_from_env()
    
    # 执行上传
    main(args.file_path)