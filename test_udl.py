"""测试 UDL 解析与构建"""
import os
import sys

# 确保拼音表已加载
from udl_core import UdlFile, load_pinyin_table, get_default_udl_path

# 加载拼音表
load_pinyin_table()
print(f"拼音表加载完成: {len([p for p in __import__('udl_core').PINYIN_TABLE])} 个音节")

# 读取当前用户的 UDL 文件
udl_path = get_default_udl_path()
print(f"\nUDL 文件路径: {udl_path}")
print(f"文件存在: {os.path.exists(udl_path)}")

if os.path.exists(udl_path):
    udl = UdlFile()
    entries = udl.read(udl_path)
    print(f"读取到 {len(entries)} 个词条")

    # 显示前 20 个词条
    print("\n=== 前 20 个词条 ===")
    for i, e in enumerate(entries[:20]):
        py_str = ' '.join(e.pinyin) if e.pinyin else '?'
        print(f"  {i}: [{e.word}] py={py_str} jp={e.jianpin_str}")

    # 显示统计信息
    print(f"\n=== 统计 ===")
    print(f"总词条数: {len(entries)}")
    word_lens = [len(e.word) for e in entries]
    print(f"平均词长: {sum(word_lens)/len(word_lens):.1f} 字")
    print(f"最长词: {max(word_lens)} 字")
    print(f"最短词: {min(word_lens)} 字")

    # 词长分布
    from collections import Counter
    len_dist = Counter(word_lens)
    print("词长分布:")
    for length in sorted(len_dist.keys()):
        print(f"  {length}字: {len_dist[length]} 个")

    # 测试导出为 JSON
    import json
    json_path = os.path.join(os.path.dirname(__file__), 'udl_export.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(udl.to_dict_list(), f, ensure_ascii=False, indent=2)
    print(f"\n导出 JSON: {json_path}")

    # 测试构建 UDL
    test_path = os.path.join(os.path.dirname(__file__), 'test_output.dat')
    udl.write(test_path)
    print(f"测试写入: {test_path}")

    # 验证写入的文件
    udl2 = UdlFile()
    entries2 = udl2.read(test_path)
    print(f"验证读取: {len(entries2)} 个词条")

    # 清理
    os.remove(test_path)
    os.remove(json_path)
    print("测试文件已清理")

print("\n测试完成!")
