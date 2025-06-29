# coding=UTF-8
"""
证书管理工具模块
提供证书检查、安装状态验证等功能
"""

import os
import subprocess
from logutil import setup_logger

logger = setup_logger()


def is_certificate_installed_in_store(cert_name_patterns=None, cert_file_path=None, store_name="ROOT"):
    """
    检查证书是否已安装在指定的Windows证书存储中
    
    Args:
        cert_name_patterns (list): 证书名称模式列表，用于在存储中搜索
        cert_file_path (str): 本地证书文件路径，用于指纹比对
        store_name (str): 证书存储名称，默认为"ROOT"
        
    Returns:
        bool: 如果证书已安装返回True，否则返回False
    """
    try:
        # 使用certutil查询指定证书存储
        result = subprocess.run(
            ["certutil", "-store", store_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.debug(f"无法查询{store_name}证书存储")
            return False
        
        output = result.stdout.lower()
        
        # 如果提供了证书名称模式，先进行模式匹配
        if cert_name_patterns:
            for pattern in cert_name_patterns:
                if pattern.lower() in output:
                    logger.debug(f"在{store_name}证书存储中发现匹配证书: {pattern}")
                    return True
        
        # 如果提供了本地证书文件路径，进行指纹比对
        if cert_file_path and os.path.exists(cert_file_path):
            return check_certificate_fingerprint_in_store(cert_file_path, store_name)
        
        return False
        
    except subprocess.TimeoutExpired:
        logger.warning(f"查询{store_name}证书存储超时")
        return False
    except Exception as e:
        logger.debug(f"检查证书安装状态时出错: {e}")
        return False


def check_certificate_fingerprint_in_store(cert_file_path, store_name="ROOT"):
    """
    通过证书指纹检查证书是否在指定存储中
    
    Args:
        cert_file_path (str): 证书文件路径
        store_name (str): 证书存储名称，默认为"ROOT"
        
    Returns:
        bool: 如果证书存在返回True，否则返回False
    """
    try:
        if not os.path.exists(cert_file_path):
            logger.debug(f"证书文件不存在: {cert_file_path}")
            return False
        
        # 获取证书的SHA1指纹
        result = subprocess.run(
            ["certutil", "-hashfile", cert_file_path, "SHA1"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.debug(f"无法获取证书指纹: {cert_file_path}")
            return False
        
        # 提取SHA1哈希值
        lines = result.stdout.strip().split('\n')
        sha1_hash = None
        for line in lines:
            line = line.strip()
            # 查找包含哈希值的行（40个字符的十六进制字符串）
            if len(line) == 40 and all(c in '0123456789abcdefABCDEF' for c in line):
                sha1_hash = line.lower()
                break
        
        if not sha1_hash:
            logger.debug("无法提取证书SHA1哈希值")
            return False
        
        # 在指定证书存储中查找该指纹
        result = subprocess.run(
            ["certutil", "-store", store_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            store_output = result.stdout.lower()
            fingerprint_found = sha1_hash in store_output
            if fingerprint_found:
                logger.debug(f"在{store_name}存储中找到匹配的证书指纹: {sha1_hash}")
            return fingerprint_found
        
        return False
        
    except subprocess.TimeoutExpired:
        logger.warning(f"检查证书指纹超时: {cert_file_path}")
        return False
    except Exception as e:
        logger.debug(f"检查证书指纹时出错: {e}")
        return False


def is_mitmproxy_certificate_installed():
    """
    检查mitmproxy证书是否已安装在系统根证书存储中
    
    Returns:
        bool: 如果mitmproxy证书已安装返回True，否则返回False
    """
    # mitmproxy证书的常见标识符
    mitmproxy_patterns = [
        "mitmproxy",
        "mitmproxy ca",
        "mitmproxy certificate authority"
    ]
    
    # mitmproxy证书的标准路径
    cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.cer")
    
    return is_certificate_installed_in_store(
        cert_name_patterns=mitmproxy_patterns,
        cert_file_path=cert_path,
        store_name="ROOT"
    )


def install_certificate_to_store(cert_file_path, store_name="ROOT"):
    """
    将证书安装到指定的Windows证书存储中
    
    Args:
        cert_file_path (str): 证书文件路径
        store_name (str): 目标证书存储名称，默认为"ROOT"
        
    Returns:
        bool: 安装成功返回True，否则返回False
    """
    try:
        if not os.path.exists(cert_file_path):
            logger.error(f"证书文件不存在: {cert_file_path}")
            return False
        
        # 使用certutil安装证书
        logger.info(f"正在将证书安装到{store_name}存储: {cert_file_path}")
        result = subprocess.run(
            ["certutil", "-addstore", store_name, cert_file_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"安装证书失败: {result.stderr}")
            return False
        
        logger.info(f"证书安装成功: {cert_file_path} -> {store_name}")
        return True
        
    except Exception as e:
        logger.error(f"安装证书时出错: {e}")
        return False


def get_certificate_info(cert_file_path):
    """
    获取证书文件的详细信息
    
    Args:
        cert_file_path (str): 证书文件路径
        
    Returns:
        dict: 包含证书信息的字典，如果获取失败返回None
    """
    try:
        if not os.path.exists(cert_file_path):
            return None
        
        # 使用certutil获取证书详细信息
        result = subprocess.run(
            ["certutil", "-dump", cert_file_path],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode != 0:
            return None
        
        # 解析证书信息（这里可以根据需要扩展解析逻辑）
        cert_info = {
            "file_path": cert_file_path,
            "raw_output": result.stdout,
            "exists": True
        }
        
        return cert_info
        
    except Exception as e:
        logger.debug(f"获取证书信息时出错: {e}")
        return None
