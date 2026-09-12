import struct

path = r'C:\Users\david\AppData\Roaming\Microsoft\InputMethod\Chs\ChsPinyinUDL.dat'
with open(path, 'rb') as f:
    data = f.read()

print(f"文件大小: {len(data)} bytes")

# 解析文件头
magic = data[0:4]
print(f"Magic: {magic.hex()} (应为 55aa8881)")

# 词条数在偏移 0xC
entry_count = struct.unpack_from('<I', data, 0xC)[0]
print(f"词条数 (offset 0xC): {entry_count}")

# 导出时间戳在偏移 0x14
export_ts = struct.unpack_from('<I', data, 0x14)[0]
print(f"导出时间戳 (offset 0x14): {export_ts}")

# 验证数据区
data_start = 0x2400  # 9216
entry_size = 60
expected_data_size = entry_count * entry_size
actual_data_size = len(data) - data_start
print(f"数据区起始: 0x{data_start:X} ({data_start})")
print(f"预期数据大小: {expected_data_size} ({entry_count} × {entry_size})")
print(f"实际数据大小: {actual_data_size}")
print(f"尾部剩余: {actual_data_size - expected_data_size} bytes")

# 解析第一个词条
print("\n=== 第一个词条 (offset 0x2400) ===")
off = data_start
insert_ts = struct.unpack_from('<I', data, off)[0]
jianpin = data[off+4:off+7]
reserved = data[off+7:off+10]
word_len = data[off+10]
separator = data[off+11]

print(f"插入时间戳: {insert_ts}")
print(f"Jianpin: {jianpin.hex()}")
print(f"Reserved: {reserved.hex()}")
print(f"词长度: {word_len}")
print(f"分隔符: 0x{separator:02X} (应为 0x5A)")

# 词数据 (UTF-16LE)
word_data = data[off+12:off+12+word_len*2]
word = word_data.decode('utf-16-le')
print(f"词: {word}")

# 拼音索引
py_indices_start = off + 12 + word_len * 2
py_indices = []
for i in range(word_len):
    idx = struct.unpack_from('<H', data, py_indices_start + i*2)[0]
    py_indices.append(idx)
print(f"拼音索引: {py_indices}")

# 解析前 20 词条
print(f"\n=== 解析前 20 词条 ===")
for i in range(20):
    off = data_start + i * entry_size
    insert_ts = struct.unpack_from('<I', data, off)[0]
    jianpin = data[off+4:off+7]
    word_len = data[off+10]
    separator = data[off+11]

    if word_len == 0 or word_len > 12:
        print(f"  词条 {i}: word_len={word_len} (跳过)")
        continue

    word_data = data[off+12:off+12+word_len*2]
    word = word_data.decode('utf-16-le', errors='replace')

    py_indices_start = off + 12 + word_len * 2
    py_indices = []
    for j in range(word_len):
        idx = struct.unpack_from('<H', data, py_indices_start + j*2)[0]
        py_indices.append(idx)

    print(f"  词条 {i}: [{word}] len={word_len} sep=0x{separator:02X} jianpin={jianpin.hex()} py_idx={py_indices}")
