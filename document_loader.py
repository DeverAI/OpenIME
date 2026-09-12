"""
文档加载：把 PDF / DOCX / TXT / MD / CSV 等变成纯文本
"""

from __future__ import annotations

import os
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Tuple


SUPPORTED_EXT = {".txt", ".md", ".csv", ".tsv", ".log", ".pdf", ".docx", ".json"}


@dataclass
class LoadedDoc:
    path: str
    text: str
    kind: str
    pages_or_lines: int = 0
    warning: str = ""


def _read_text_file(path: str) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "utf-16"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def load_txt(path: str) -> LoadedDoc:
    text = _read_text_file(path)
    lines = text.count("\n") + 1 if text else 0
    return LoadedDoc(path=path, text=text, kind="txt", pages_or_lines=lines)


def load_docx(path: str) -> LoadedDoc:
    """用标准库解析 docx（不强制依赖 python-docx）"""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        import docx as python_docx  # type: ignore
        d = python_docx.Document(path)
        paras = [p.text for p in d.paragraphs if p.text and p.text.strip()]
        # 表格也收
        for table in getattr(d, "tables", []) or []:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                if cells:
                    paras.append(" ".join(cells))
        return LoadedDoc(path=path, text="\n".join(paras), kind="docx", pages_or_lines=len(paras))
    except Exception:
        pass

    # fallback: 直接读 document.xml
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        paras = []
        for p in root.iter(f"{{{ns['w']}}}p"):
            texts = [t.text or "" for t in p.iter(f"{{{ns['w']}}}t")]
            line = "".join(texts).strip()
            if line:
                paras.append(line)
        return LoadedDoc(path=path, text="\n".join(paras), kind="docx", pages_or_lines=len(paras))
    except Exception as e:
        raise RuntimeError(f"无法解析 Word 文档：{e}") from e


def load_pdf(path: str) -> LoadedDoc:
    # 优先 PyMuPDF（抽取质量更好），其次 pypdf
    try:
        import fitz  # type: ignore
        doc = fitz.open(path)
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))
        doc.close()
        text = "\n".join(parts)
        return LoadedDoc(path=path, text=text, kind="pdf", pages_or_lines=len(parts))
    except ImportError:
        pass
    except Exception as e:
        warn = f"PyMuPDF 读取异常，尝试 pypdf：{e}"
    else:
        warn = ""

    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts)
        return LoadedDoc(path=path, text=text, kind="pdf", pages_or_lines=len(parts), warning=warn)
    except ImportError:
        raise RuntimeError(
            "本机缺少 PDF 解析库。请安装：pip install pypdf\n"
            "或先把 PDF 另存/复制为 .txt 再导入。"
        )
    except Exception as e:
        raise RuntimeError(f"无法解析 PDF：{e}") from e


def load_document(path: str) -> LoadedDoc:
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到文件：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return load_pdf(path)
    if ext == ".docx":
        return load_docx(path)
    if ext == ".doc":
        raise RuntimeError(
            "暂不支持旧版 .doc。\n请用 Word 打开后另存为 .docx，或导出为 .txt 再导入。"
        )
    if ext in SUPPORTED_EXT or ext == "":
        doc = load_txt(path)
        doc.kind = ext.lstrip(".") or "txt"
        return doc
    # 未知扩展名仍按文本试读
    doc = load_txt(path)
    doc.kind = ext.lstrip(".") or "txt"
    doc.warning = f"未知格式 {ext or '(无扩展名)'}，已按纯文本读取"
    return doc


def load_many(paths: List[str]) -> Tuple[List[LoadedDoc], List[str]]:
    docs: List[LoadedDoc] = []
    errors: List[str] = []
    for p in paths:
        try:
            docs.append(load_document(p))
        except Exception as e:
            errors.append(f"{os.path.basename(p)}：{e}")
    return docs, errors
