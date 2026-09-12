"""验证：合并写入保留真机文件头 0x470+ 区域。"""
import os
import tempfile
import shutil
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="openime_hdr_")
os.environ["APPDATA"] = TMP

from udl_core import UdlFile, load_pinyin_table, get_default_udl_path, UDL_HEADER_SIZE
import app_core

load_pinyin_table()
path = Path(get_default_udl_path())
os.makedirs(path.parent, exist_ok=True)

# 造一个带“索引区”的假真机文件头
header = bytearray(UDL_HEADER_SIZE)
header[0:4] = b"\x55\xAA\x88\x81"
header[4:8] = b"\x02\x00\x60\x00"
header[8:12] = b"\x55\xAA\x55\xAA"
header[0x470:0x480] = b"\x01\x00\x00\x00" + b"\x02\x00\x00\x00" * 3
udl = UdlFile()
udl.entries = []
udl.add_entry("甲乙丙丁")
# 写最小头
raw = bytes(header)  # will write with preserve from empty raw
udl.raw_header = bytes(header)
udl.write(str(path), preserve_header=True)

data = path.read_bytes()
assert data[0x470:0x480] == header[0x470:0x480], "initial write should keep 0x470"

# 合并导入
app_core.ensure_ready()
r = app_core.add_words(["戊己庚辛", "产品原型"])
assert r.ok, r.message

data2 = path.read_bytes()
assert data2[0x470:0x480] == header[0x470:0x480], (
    f"header index wiped!\n got {data2[0x470:0x480].hex()}"
)
# magic 与 count 正确
assert data2[0:4] == b"\x55\xAA\x88\x81"
import struct
assert struct.unpack_from("<I", data2, 0xC)[0] == 3

# 删除也保留
r = app_core.delete_entries(["甲乙丙丁"])
assert r.ok
data3 = path.read_bytes()
assert data3[0x470:0x480] == header[0x470:0x480]

print("HEADER PRESERVE TEST PASSED")
shutil.rmtree(TMP, ignore_errors=True)
