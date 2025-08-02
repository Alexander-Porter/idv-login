# -*- coding: utf-8 -*-
# ============================================================
#  QuarkUp.py
#  Author: Coke
#  Date:   2025-04-28
#  Introduce:   夸克网盘自动上传与分享脚本
#     支持大文件上传、自动生成分享链接、自动输出最终可用短链。
#     兼容 Windows、macOS、Linux 系统，适合自动化备份、批量分发等场景。
#
#  pdir_fid 获取方法：
#    1. 在 https://pan.quark.cn 新建或进入目标文件夹
#
#    2. 浏览器地址栏URL形如：
#         https://pan.quark.cn/list#/list/all/47643a1fd06c449372498374242874-my*101update

#    3. 其中 47643a1fd06c449372498374242874 即为 pdir_fid
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

# 夸克上传接口
url = "http://api.quark.cn/file/upload"

# 必要 Cookie，从环境变量中读取
cookies = {}

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

# 需要上传的文件路径和目录ID，从命令行参数获取
file_path = ""
pdir_fid = ""

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
    """
    计算文件的MD5和SHA1哈希值
    :param file_path: 文件路径
    :return: (md5, sha1)
    """
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

def get_pdir_fid():
    """
    获取网盘根目录的pdir_fid
    :return: pdir_fid字符串
    """
    url = "https://drive-pc.quark.cn/1/clouddrive/file/system_path?pr=ucpro&fr=pc&uc_param_str="
    payload = {"scene": "manual_upload", "init": True}
    log_step("请求系统路径", url)
    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)
    log_step("system_path返回", resp.text)
    data = resp.json()["data"]
    if "pdir_fid" in data:
        return data["pdir_fid"]
    elif "path_files" in data and data["path_files"]:
        return data["path_files"][0]["fid"]
    else:
        raise Exception("未找到pdir_fid")

def pre_upload(file_path, pdir_fid):
    """
    预上传，获取上传任务信息
    :param file_path: 文件路径
    :param pdir_fid: 目标目录fid
    :return: 预上传接口返回内容
    """
    url = "https://drive-pc.quark.cn/1/clouddrive/file/upload/pre?pr=ucpro&fr=pc&uc_param_str="
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    md5, sha1 = get_file_hash(file_path)
    now = int(time.time() * 1000)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    payload = {
        "ccp_hash_update": True,
        "parallel_upload": True,
        "pdir_fid": pdir_fid,
        "dir_name": "",
        "size": file_size,
        "file_name": file_name,
        "format_type": mime_type,
        "l_updated_at": now,
        "l_created_at": now
    }
    log_step("预上传", url)
    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)
    log_step("pre_upload返回", resp.text)
    return resp.json()

def upload_part_to_oss(oss_url, part_data, oss_headers):
    """
    上传分片到OSS
    :param oss_url: OSS上传地址
    :param part_data: 分片数据
    :param oss_headers: OSS请求头
    :return: 响应对象
    """
    log_step("分片上传到OSS", oss_url)
    resp = requests.put(oss_url, data=part_data, headers=oss_headers)
    log_step("oss put状态", resp.status_code)
    return resp

def upload_auth(task_id, auth_info, auth_meta):
    """
    上传认证
    :param task_id: 上传任务ID
    :param auth_info: 认证信息
    :param auth_meta: 认证元数据
    :return: 接口返回内容
    """
    url = "https://drive-pc.quark.cn/1/clouddrive/file/upload/auth?pr=ucpro&fr=pc&uc_param_str="
    payload = {
        "task_id": task_id,
        "auth_info": auth_info,
        "auth_meta": auth_meta
    }
    log_step("上传认证", url)
    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)
    log_step("upload_auth返回", resp.text)
    return resp.json()

def update_hash(task_id, md5, sha1):
    """
    更新文件hash
    :param task_id: 上传任务ID
    :param md5: 文件MD5
    :param sha1: 文件SHA1
    :return: 接口返回内容
    """
    url = "https://drive-pc.quark.cn/1/clouddrive/file/update/hash?pr=ucpro&fr=pc&uc_param_str="
    payload = {
        "task_id": task_id,
        "md5": md5,
        "sha1": sha1
    }
    log_step("更新hash", url)
    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)
    log_step("update_hash返回", resp.text)
    return resp.json()

def finish_upload(obj_key, task_id):
    """
    完成上传
    :param obj_key: 对象key
    :param task_id: 上传任务ID
    :return: 接口返回内容
    """
    url = "https://drive-pc.quark.cn/1/clouddrive/file/upload/finish?pr=ucpro&fr=pc&uc_param_str="
    payload = {
        "obj_key": obj_key,
        "task_id": task_id
    }
    log_step("完成上传", url)
    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)
    log_step("finish_upload返回", resp.text)
    return resp.json()

def share_file(fid, title, url_type=1, expired_type=2):
    """
    创建分享链接（普通链接）
    :param fid: 文件fid（字符串，单个文件用一个fid，多个文件用fid列表）
    :param title: 分享标题
    :param url_type: 1=普通链接 2=短链
    :param expired_type: 2=永久 1=7天 0=24小时
    :return: 分享接口返回内容
    """
    url = "https://drive-pc.quark.cn/1/clouddrive/share?pr=ucpro&fr=pc&uc_param_str="
    if isinstance(fid, str):
        fid_list = [fid]
    else:
        fid_list = fid
    payload = {
        "fid_list": fid_list,
        "title": title,
        "url_type": url_type,
        "expired_type": expired_type
    }
    log_step("创建分享", url)
    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)
    log_step("share返回", resp.text)
    return resp.json()

def get_share_password_info(share_id):
    """
    查询分享口令和最终分享链接等信息
    :param share_id: 分享ID
    :return: 接口返回内容
    """
    url = "https://drive-pc.quark.cn/1/clouddrive/share/password?pr=ucpro&fr=pc&uc_param_str="
    payload = {"share_id": share_id}
    log_step("查询分享口令", url)
    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)
    log_step("share/password返回", resp.text)
    return resp.json()

def main(upload_file_path):
    """
    主流程：上传文件并生成分享链接
    """
    global file_path
    file_path = upload_file_path
    
    log_step("开始上传流程")
    log_step("指定pdir_fid", pdir_fid)
    log_step("上传文件", file_path)
    
    if not os.path.exists(file_path):
        log_step("文件不存在", file_path)
        sys.exit(1)
    
    pre_info = pre_upload(file_path, pdir_fid)
    task_id = pre_info["data"]["task_id"]
    obj_key = pre_info["data"]["obj_key"]
    log_step("获取task_id", task_id)
    log_step("获取obj_key", obj_key)
    md5, sha1 = get_file_hash(file_path)
    update_hash(task_id, md5, sha1)
    finish_info = finish_upload(obj_key, task_id)
    log_step("上传流程结束")
    fid = finish_info["data"]["fid"]
    title = os.path.basename(file_path)
    share_info = share_file(fid, title, url_type=1, expired_type=2)
    log_step("分享信息", share_info)

    # 提取share_id并查询最终分享信息
    try:
        share_data = share_info.get("data", {})
        if "task_resp" in share_data and "data" in share_data["task_resp"]:
            share_data = share_data["task_resp"]["data"]
        share_id = share_data.get("share_id")
        if not share_id:
            raise Exception("未获取到share_id")
        pwd_info = get_share_password_info(share_id)
        log_step("最终分享信息", pwd_info)
        if "data" in pwd_info:
            file_name = pwd_info["data"].get("title", title)
            share_url = pwd_info["data"].get("share_url")
            print(f"{file_name} 分享链接：{share_url}")
        else:
            raise Exception("未获取到最终分享链接")
    except Exception as e:
        log_step("输出链接失败", str(e))

if __name__ == "__main__":
    # 解析命令行参数
    args = parse_args()
    
    # 从环境变量加载配置
    load_config_from_env()
    
    # 执行上传
    main(args.file_path)