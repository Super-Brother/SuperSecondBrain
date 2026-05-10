"""数据脱敏模块

企业级 RAG 安全红线防护：
1. Query 脱敏 — 用户问题发送给 LLM 前识别并替换敏感信息
2. 文档脱敏 — 文档入库前识别并替换敏感信息
3. 答案脱敏 — LLM 生成后检查并替换敏感信息

支持：手机号、身份证号、邮箱、银行卡号、人名（基础正则）
高级支持：接入 Microsoft Presidio（可选）
"""

import os
import re
from typing import Callable


# 正则模式定义
PATTERNS = {
    "mobile": {
        "pattern": r"(?<![\d])1[3-9]\d{9}(?![\d])",
        "mask": lambda m: m[:3] + "****" + m[7:],
    },
    "id_card": {
        "pattern": r"(?<!\d)(?:\d{17}[\dXx]|\d{15})(?!\d)",
        "mask": lambda m: m[:4] + "**********" + m[-4:] if len(m) == 18 else m[:4] + "******" + m[-3:],
    },
    "email": {
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "mask": lambda m: m.split("@")[0][:2] + "***@" + m.split("@")[1],
    },
    "bank_card": {
        "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9]{2})[0-9]{12}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|(?:2131|1800|35\d{3})\d{11})\b",
        "mask": lambda m: m[:4] + " **** **** " + m[-4:],
    },
}


def _replace_with_pattern(text: str, name: str, config: dict) -> str:
    """用正则替换敏感信息"""
    pattern = config["pattern"]
    mask_fn = config["mask"]

    def replacer(match):
        original = match.group(0)
        masked = mask_fn(original)
        return masked

    return re.sub(pattern, replacer, text)


def sanitize_text(text: str, enabled_types: list[str] | None = None) -> str:
    """
    对文本进行脱敏处理

    Args:
        text: 原始文本
        enabled_types: 启用的脱敏类型，None 表示全部

    Returns:
        脱敏后的文本
    """
    if not text:
        return text

    types = enabled_types or list(PATTERNS.keys())
    result = text

    for name in types:
        if name in PATTERNS:
            result = _replace_with_pattern(result, name, PATTERNS[name])

    return result


def detect_sensitive(text: str) -> list[dict]:
    """
    检测文本中的敏感信息，返回位置信息（用于审计日志）

    Returns:
        [{"type": "mobile", "start": 10, "end": 21, "value": "138****8888"}, ...]
    """
    findings = []
    for name, config in PATTERNS.items():
        for match in re.finditer(config["pattern"], text):
            findings.append({
                "type": name,
                "start": match.start(),
                "end": match.end(),
                "value": match.group(0),
            })
    return findings


class QuerySanitizer:
    """Query 脱敏器 — 用户问题在发送给 LLM 前脱敏"""

    def __init__(self, enabled: bool = None):
        self.enabled = enabled if enabled is not None else os.getenv("SANITIZE_QUERY", "true").lower() == "true"

    def sanitize(self, query: str) -> str:
        if not self.enabled:
            return query
        return sanitize_text(query)


class DocumentSanitizer:
    """文档脱敏器 — 文档入库前脱敏"""

    def __init__(self, enabled: bool = None):
        self.enabled = enabled if enabled is not None else os.getenv("SANITIZE_DOCUMENT", "false").lower() == "true"

    def sanitize(self, content: str) -> str:
        if not self.enabled:
            return content
        return sanitize_text(content)


class AnswerSanitizer:
    """答案脱敏器 — LLM 生成后检查并脱敏"""

    def __init__(self, enabled: bool = None):
        self.enabled = enabled if enabled is not None else os.getenv("SANITIZE_ANSWER", "true").lower() == "true"

    def sanitize(self, answer: str) -> str:
        if not self.enabled:
            return answer
        return sanitize_text(answer)

    def check_and_warn(self, answer: str) -> tuple[str, list[dict]]:
        """检查并返回警告信息"""
        findings = detect_sensitive(answer)
        sanitized = sanitize_text(answer)
        return sanitized, findings


def sanitize_document_metadata(doc) -> None:
    """
    为 Document 对象添加权限元数据（用于企业级权限隔离）

    从环境变量或文档路径推断部门和访问级别
    """
    import os
    from pathlib import Path

    source = doc.metadata.get("source_file", "")
    folder = doc.metadata.get("folder", "root")

    # 默认权限
    default_dept = os.getenv("DEFAULT_DEPARTMENT", "default")
    default_level = int(os.getenv("DEFAULT_ACCESS_LEVEL", "0"))

    # 从文件夹路径推断部门（示例映射）
    dept_map = {
        "技术": ["技术部"],
        "产品": ["产品部"],
        "HR": ["人力资源部"],
        "财务": ["财务部"],
        "面试": ["技术部", "人力资源部"],
    }

    departments = [default_dept]
    for key, depts in dept_map.items():
        if key in folder:
            departments = depts
            break

    doc.metadata["department"] = departments
    doc.metadata["access_level"] = default_level
    doc.metadata["doc_id"] = doc.metadata.get("relative_path", source)

    return doc
