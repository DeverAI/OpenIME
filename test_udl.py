"""真机 UDL 只读体检工具（开发者工具，不属于回归测试套件）

只读当前用户的真实 ChsPinyinUDL.dat 做统计；所有生成物（导出 JSON、
测试写盘副本）一律写到 %TEMP% 下，绝不写入项目目录、绝不改动真机词库。
回归测试请跑 test_logic_expected.py / test_fixes.py / test_round3.py 等。
"""
import json
import os
import tempfile
from collections import Counter

from udl_core import UdlFile, load_pinyin_table, get_default_udl_path

load_pinyin_table()
print(f"拼音表加载完成: {len(__import__('udl_core').PINYIN_TABLE)} 个音节")

udl_path = get_default_udl_path()
print(f"\nUDL 文件路径(只读): {udl_path}")
print(f"文件存在: {os.path.exists(udl_path)}")

if os.path.exists(udl_path):
    udl = UdlFile()
    entries = udl.read(udl_path)  # 只读
    print(f"读取到 {len(entries)} 个词条")

    print("\n=== 前 20 个词条 ===")
    for i, e in enumerate(entries[:20]):
        py_str = ' '.join(e.pinyin) if e.pinyin else '?'
        print(f"  {i}: [{e.word}] py={py_str} jp={e.jianpin_str}")

    word_lens = [len(e.word) for e in entries]
    print(f"\n=== 统计 ===")
    print(f"总词条数: {len(entries)}")
    print(f"平均词长: {sum(word_lens)/len(word_lens):.1f} 字")
    print(f"最长词: {max(word_lens)} 字")
    print(f"最短词: {min(word_lens)} 字")
    for length in sorted(Counter(word_lens).keys()):
        print(f"  {length}字: {Counter(word_lens)[length]} 个")

    # 产物全部放临时目录，随系统清理
    out_dir = tempfile.mkdtemp(prefix="openime_udl_tool_")
    json_path = os.path.join(out_dir, "udl_export.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(udl.to_dict_list(), f, ensure_ascii=False, indent=2)
    print(f"\n导出 JSON(临时目录): {json_path}")

    test_path = os.path.join(out_dir, "test_output.dat")
    udl.write(test_path)
    entries2 = UdlFile().read(test_path)
    print(f"测试写入并回读(临时目录): {len(entries2)} 个词条 == {len(entries) if len(entries2)==len(entries) else '不一致!'}")

print("\n体检完成（真机文件未被修改）")
