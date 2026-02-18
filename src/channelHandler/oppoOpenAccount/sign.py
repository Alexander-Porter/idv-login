#仅供技术交流，请下载后24小时内删除，禁止商用！如有侵权请联系仓库维护者删除！谢谢！
import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

BIZK_SECRET_KEY = "6CyfIPKEDKF0RIR3fdtFsQ=="


def _iter_fields(obj: Any) -> Iterable[Tuple[str, Any]]:
    if is_dataclass(obj):
        for k, v in asdict(obj).items():
            yield k, v
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
        return
    # fallback: __dict__
    if hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            yield k, v


def _java_value_to_string(value: Any) -> str:
    """尽量模拟 Java 的 Object.toString() 输出形态（用于签名源串）。"""

    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, dict):
        # Java Map.toString: {k1=v1, k2=v2}
        items = []
        for k in sorted(value.keys(), key=lambda x: str(x)):
            v = value[k]
            items.append(f"{_java_value_to_string(k)}={_java_value_to_string(v)}")
        return "{" + ", ".join(items) + "}"
    if isinstance(value, (list, tuple)):
        # Java Arrays.toString: [a, b]
        return "[" + ", ".join(_java_value_to_string(v) for v in value) + "]"
    return str(value)


def build_sign_source(obj: Any, exclude_field: Optional[str] = None) -> Optional[str]:
    """复刻 AcSignHelper.signWithAnnotation

    - 过滤：None / '' / 空白字符串
    - 过滤：sign 字段（以及可选 exclude_field）
    - 生成：name=value&
    - 排序：case-insensitive
    - 拼接：直接串联
    """

    parts: List[str] = []
    for name, value in _iter_fields(obj):
        if name == "sign":
            continue
        if exclude_field and name == exclude_field:
            continue

        if value is None:
            continue
        if isinstance(value, str):
            if value == "" or value.strip() == "":
                continue
        if isinstance(value, (list, tuple)) and len(value) == 0:
            continue
        if isinstance(value, dict) and len(value) == 0:
            continue

        parts.append(f"{name}={_java_value_to_string(value)}&")

    if not parts:
        return None

    parts.sort(key=lambda s: s.lower())
    return "".join(parts)


def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def sign_add_key(source: str) -> str:
    if source and not source.endswith("&"):
        source = source + "&"
    return source + f"key={BIZK_SECRET_KEY}"


def sign_request(obj: Any, exclude_field: Optional[str] = None) -> str:
    src = build_sign_source(obj, exclude_field=exclude_field) or ""
    return md5_hex(sign_add_key(src))
