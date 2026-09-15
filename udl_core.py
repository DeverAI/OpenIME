"""
MS Pinyin UDL 文件解析与构建模块

文件格式 (逆向自 nopdan/rose 项目):
- 文件头: 0x0-0x2400 (9216 bytes)
- 数据区: 0x2400+, 每词条 60 字节固定
"""

import struct
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


# UDL 文件常量
UDL_MAGIC = b'\x55\xAA\x88\x81'
UDL_HEADER_SIZE = 0x2400  # 9216
UDL_ENTRY_SIZE = 60
UDL_SEPARATOR = 0x5A
UDL_SIZE_SETTINGS = b'\x02\x00\x60\x00'
UDL_VALIDATION = b'\x55\xAA\x55\xAA'
UDL_RESERVED = b'\x00\x00\x04'
# 60 字节结构：12 头 + 12*2 词 + 12*2 拼音
MAX_WORD_LEN = 12
# 无有效拼音时写入的哨兵（避免误写成 0 = 音节 a）
UNKNOWN_PY_INDEX = 0xFFFF


@dataclass
class UdlEntry:
    """UDL 词条"""
    word: str                                   # 中文词
    pinyin: List[str] = field(default_factory=list)  # 拼音列表
    insert_timestamp: int = 0                   # 插入时间戳
    jianpin: bytes = b'\x00\x00\x00'            # 简拼 (3 bytes)

    @property
    def jianpin_str(self) -> str:
        """简拼字符串：优先用文件里的 3 字节，否则从拼音推导"""
        raw = self.jianpin
        if raw and len(raw) == 3 and any(b != 0 for b in raw):
            return ''.join(chr(b) if 32 <= b < 127 else '' for b in raw)[:3].ljust(3)
        result = ''
        for py in self.pinyin:
            if py:
                result += py[0].lower()
        if not result:
            for ch in self.word:
                if ch.isascii() and ch.isalpha():
                    result += ch.lower()
                if len(result) >= 3:
                    break
        return result[:3].ljust(3)


# 拼音表 (全局)
PINYIN_TABLE: List[str] = []
PINYIN_TABLE_INDEX: dict = {}


def load_pinyin_table(path: str = None):
    """加载拼音表"""
    global PINYIN_TABLE, PINYIN_TABLE_INDEX
    if path is None:
        try:
            from paths import resource_path
            path = resource_path('pinyin_table.json')
        except Exception:
            path = os.path.join(os.path.dirname(__file__), 'pinyin_table.json')
    with open(path, 'r', encoding='utf-8') as f:
        PINYIN_TABLE = json.load(f)
    PINYIN_TABLE_INDEX = {py: idx for idx, py in enumerate(PINYIN_TABLE)}
    return PINYIN_TABLE


def get_pinyin_by_index(index: int) -> str:
    """通过索引获取拼音"""
    if 0 <= index < len(PINYIN_TABLE):
        return PINYIN_TABLE[index]
    return ''


def get_index_by_pinyin(pinyin: str) -> int:
    """通过拼音获取索引；空/未知返回哨兵，而不是 0（0=音节 a）"""
    if not pinyin:
        return UNKNOWN_PY_INDEX
    idx = PINYIN_TABLE_INDEX.get(pinyin.lower())
    if idx is None:
        return UNKNOWN_PY_INDEX
    return idx


class UdlFile:
    """UDL 文件操作类"""

    def __init__(self):
        self.entries: List[UdlEntry] = []
        self.export_timestamp: int = 0
        # 原文件头（0x2400）：真机头 0x470 起有索引/统计区，合并写入必须保留
        self.raw_header: Optional[bytes] = None
        self._ensure_pinyin_table()

    def _ensure_pinyin_table(self):
        """确保拼音表已加载"""
        if not PINYIN_TABLE:
            load_pinyin_table()

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    def read(self, path: str) -> List[UdlEntry]:
        """读取 UDL 文件"""
        with open(path, 'rb') as f:
            data = f.read()

        if len(data) < UDL_HEADER_SIZE:
            raise ValueError(f"UDL 文件过短: {len(data)} bytes")

        # 验证文件头
        if data[0:4] != UDL_MAGIC:
            raise ValueError(f"无效的 UDL 文件: magic = {data[0:4].hex()}")

        self.raw_header = bytes(data[:UDL_HEADER_SIZE])

        # 读取词条数
        entry_count = struct.unpack_from('<I', data, 0xC)[0]

        # 读取导出时间戳
        self.export_timestamp = struct.unpack_from('<I', data, 0x14)[0]

        # 解析词条（按文件实际长度截断，防止坏 count 越界）
        max_by_size = max(0, (len(data) - UDL_HEADER_SIZE) // UDL_ENTRY_SIZE)
        parse_n = min(entry_count, max_by_size)

        self.entries = []
        for i in range(parse_n):
            offset = UDL_HEADER_SIZE + i * UDL_ENTRY_SIZE
            if offset + UDL_ENTRY_SIZE > len(data):
                break
            entry = self._parse_entry(data, offset)
            if entry:
                self.entries.append(entry)

        return self.entries

    def _parse_entry(self, data: bytes, offset: int) -> Optional[UdlEntry]:
        """解析单个词条"""
        # 读取字段
        insert_ts = struct.unpack_from('<I', data, offset)[0]
        jianpin = data[offset+4:offset+7]
        reserved = data[offset+7:offset+10]
        word_len = data[offset+10]
        separator = data[offset+11]

        # 验证
        if word_len == 0 or word_len > 12:
            return None
        if separator != UDL_SEPARATOR:
            return None

        # 读取词 (UTF-16LE)
        word_start = offset + 12
        word_data = data[word_start:word_start + word_len * 2]
        word = word_data.decode('utf-16-le', errors='replace')

        # 读取拼音索引
        py_start = word_start + word_len * 2
        pinyin = []
        for j in range(word_len):
            idx = struct.unpack_from('<H', data, py_start + j * 2)[0]
            py = get_pinyin_by_index(idx)
            # 即使未知也保留占位，保证与字数对齐
            pinyin.append(py)

        return UdlEntry(
            word=word,
            pinyin=pinyin,
            insert_timestamp=insert_ts,
            jianpin=jianpin,
        )

    def write(self, path: str, preserve_header: bool = True):
        """
        写入 UDL 文件。

        preserve_header=True（默认）：从已读过的原文件复制整块 0x2400 头，
        只更新词条数与时间戳。真机头在 0x470+ 有索引/统计，清零有风险。
        无原头时才生成最小合法头。
        """
        if preserve_header and self.raw_header and len(self.raw_header) >= UDL_HEADER_SIZE:
            header = bytearray(self.raw_header[:UDL_HEADER_SIZE])
            # 确保关键魔数仍在
            header[0:4] = UDL_MAGIC
            header[4:8] = UDL_SIZE_SETTINGS
            header[8:12] = UDL_VALIDATION
        else:
            header = bytearray(UDL_HEADER_SIZE)
            header[0:4] = UDL_MAGIC
            header[4:8] = UDL_SIZE_SETTINGS
            header[8:12] = UDL_VALIDATION

        # 写入词条数 (offset 0xC)。空词条/含基本平面外字符的词条不写入，也不计数（回读时读不到）。
        payload_entries = [
            e for e in self.entries
            if e and (e.word or '').strip() and not any(ord(ch) > 0xFFFF for ch in e.word or '')
        ]
        struct.pack_into('<I', header, 0xC, len(payload_entries))

        # 写入导出时间戳 (offset 0x14)
        export_ts = int(datetime.now().timestamp())
        struct.pack_into('<I', header, 0x14, export_ts)

        # 构建数据区
        data_area = bytearray()
        for entry in payload_entries:
            data_area.extend(self._build_entry(entry))

        # 原子写入：先写同目录临时文件 → 回读校验 → os.replace 替换。
        # 直接覆盖目标文件时，写一半崩溃会留下半个坏词库。
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{path}.{os.getpid()}.tmp_openime"
        try:
            with open(tmp_path, 'wb') as f:
                f.write(header)
                f.write(data_area)
                f.flush()
                os.fsync(f.fileno())

            # 回读校验：条数 + 逐条 word 一致才算写成功
            check = UdlFile()
            read_back = check.read(tmp_path)
            if len(read_back) != len(payload_entries):
                raise IOError(
                    f"回读校验失败：写入 {len(payload_entries)} 条，读回 {len(read_back)} 条"
                )
            for a, b in zip(payload_entries, read_back):
                # _build_entry 会把超长词截到 12 字，按截断后的形态对比
                if (a.word or '')[:MAX_WORD_LEN] != b.word:
                    raise IOError(f"回读校验失败：词条不一致（{a.word!r} ≠ {b.word!r}）")

            os.replace(tmp_path, path)
        finally:
            # 成功 replace 后 tmp 已不存在；失败时清理残留
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _build_entry(self, entry: UdlEntry) -> bytes:
        """构建单个词条 (60 bytes)。超长词会被截断，避免写坏相邻词条。"""
        buf = bytearray(UDL_ENTRY_SIZE)

        word = (entry.word or '')[:MAX_WORD_LEN]
        word_len = len(word)
        if word_len < 1:
            return bytes(buf)

        # 插入时间戳
        struct.pack_into('<I', buf, 0, entry.insert_timestamp or int(datetime.now().timestamp()))

        # 简拼：默认 0x00 填充视为“未计算”，必须从拼音/ASCII 推导
        # 真机词库里的简拼是前 3 个音节首字母（或英文词前 3 个字母）
        raw_jp = entry.jianpin
        if raw_jp and len(raw_jp) == 3 and any(raw_jp):
            jp = bytes(raw_jp[:3])
        else:
            jp = self._compute_jianpin(word, entry.pinyin)[:3]
            if len(jp) < 3:
                jp = jp + b'\x00' * (3 - len(jp))
        buf[4:7] = jp[:3]

        # 保留 (3 bytes)
        buf[7:10] = UDL_RESERVED

        # 词长度
        buf[10] = word_len

        # 分隔符
        buf[11] = UDL_SEPARATOR

        # 词数据 (UTF-16LE)
        word_data = word.encode('utf-16-le')
        if 12 + len(word_data) > UDL_ENTRY_SIZE:
            # 理论上不会发生（已截到 12 字），保险
            word_data = word_data[:UDL_ENTRY_SIZE - 12]
        buf[12:12 + len(word_data)] = word_data

        # 拼音索引
        pys = list(entry.pinyin or [])
        if len(pys) < word_len:
            pys = pys + [''] * (word_len - len(pys))
        py_start = 12 + word_len * 2
        for i in range(word_len):
            py = pys[i] if i < len(pys) else ''
            idx = get_index_by_pinyin(py) if py else UNKNOWN_PY_INDEX
            # 空拼音不要落到 0（0 是合法音节 a）
            if not py:
                idx = UNKNOWN_PY_INDEX
            struct.pack_into('<H', buf, py_start + i * 2, idx)

        return bytes(buf)

    def _compute_jianpin(self, word: str, pinyin: List[str]) -> bytes:
        letters = []
        # 优先用已有拼音
        for py in pinyin or []:
            if py:
                letters.append(py[0].lower())
            if len(letters) >= 3:
                break
        if len(letters) < 3:
            for ch in word:
                if ch.isascii() and ch.isalpha():
                    letters.append(ch.lower())
                elif not ch.isascii():
                    # 非 ASCII 且无拼音时跳过
                    pass
                if len(letters) >= 3:
                    break
        return ''.join(letters[:3]).encode('ascii', errors='ignore')

    def add_entry(self, word: str, pinyin: List[str] = None):
        """添加词条（自动限制在 2–12 字；拒绝基本平面外字符，那种词写不进 60 字节结构）"""
        word = (word or '').strip()
        if not word or len(word) < 2 or len(word) > MAX_WORD_LEN:
            return
        if any(ord(ch) > 0xFFFF for ch in word):
            return
        if pinyin is None:
            pinyin = self._guess_pinyin(word)
        # 拼音数量与字数对齐，避免越界写
        if len(pinyin) < len(word):
            pinyin = list(pinyin) + [''] * (len(word) - len(pinyin))
        else:
            pinyin = list(pinyin[:len(word)])
        entry = UdlEntry(word=word, pinyin=pinyin)
        self.entries.append(entry)

    def remove_entry(self, word: str):
        """删除词条"""
        self.entries = [e for e in self.entries if e.word != word]

    def find_entry(self, word: str) -> Optional[UdlEntry]:
        """查找词条"""
        for e in self.entries:
            if e.word == word:
                return e
        return None

    def _guess_pinyin(self, word: str) -> List[str]:
        """
        猜测拼音。
        - 汉字：pypinyin 逐字取音。pypinyin 会把连续非汉字并成一段返回，
          按段对齐会让后面的汉字错位（如 "AI助手" 的「助」会拿到「手」的音）。
        - 拉丁/数字：保留空字符串占位（写入时用哨兵索引，不伪装成 a）
        """
        try:
            from pypinyin import pinyin, Style
            out: List[str] = []
            for ch in word:
                if not ('一' <= ch <= '鿿' or '㐀' <= ch <= '䶿'):
                    # 非汉字不套拼音
                    out.append('')
                    continue
                py = pinyin(ch, style=Style.NORMAL, errors='default')
                out.append(py[0][0] if py and py[0] else '')
            return out
        except ImportError:
            return [''] * len(word)

    def to_dict_list(self) -> List[dict]:
        """导出为字典列表"""
        return [
            {
                'word': e.word,
                'pinyin': e.pinyin,
                'jianpin': e.jianpin_str,
                'timestamp': e.insert_timestamp,
            }
            for e in self.entries
        ]

    def from_dict_list(self, items: List[dict]):
        """从字典列表导入（跳过非法长度，避免写坏文件）"""
        self.entries = []
        for item in items:
            word = str(item.get('word') or item.get('text') or '').strip()
            if not word or len(word) < 2 or len(word) > MAX_WORD_LEN:
                continue
            if any(ord(ch) > 0xFFFF for ch in word):
                continue
            pinyin = item.get('pinyin') or []
            if isinstance(pinyin, str):
                pinyin = pinyin.split()
            entry = UdlEntry(
                word=word,
                pinyin=list(pinyin) if pinyin else [],
                insert_timestamp=int(item.get('timestamp') or 0),
            )
            if not entry.pinyin:
                entry.pinyin = self._guess_pinyin(entry.word)
            # 对齐长度
            if len(entry.pinyin) < len(word):
                entry.pinyin = list(entry.pinyin) + [''] * (len(word) - len(entry.pinyin))
            else:
                entry.pinyin = list(entry.pinyin[:len(word)])
            self.entries.append(entry)


def get_default_udl_path() -> str:
    """获取默认 UDL 文件路径；APPDATA 缺失时明确报错，避免写到相对路径。"""
    appdata = os.environ.get('APPDATA', '').strip()
    if not appdata:
        raise RuntimeError(
            "环境变量 APPDATA 为空，无法定位微软拼音用户词库。\n"
            "请在正常 Windows 用户会话中运行本程序。"
        )
    return os.path.join(
        appdata,
        'Microsoft', 'InputMethod', 'Chs', 'ChsPinyinUDL.dat'
    )
