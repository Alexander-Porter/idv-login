import sys

def should_verify_ssl():
    """根据操作系统平台决定是否进行SSL验证
    
    Returns:
        bool: 如果需要SSL验证返回True，否则返回False
    """
    # MacOS系统禁用SSL验证以避免证书问题
    if sys.platform == 'darwin':
        return False
    return True