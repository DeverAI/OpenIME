import json
import re
from pypinyin.constants import PINYIN_DICT

# Tone mark to tone number mapping
TONE_MARKS = {
    'ā': 'a', 'á': 'a', 'ǎ': 'a', 'à': 'a',
    'ē': 'e', 'é': 'e', 'ě': 'e', 'è': 'e',
    'ī': 'i', 'í': 'i', 'ǐ': 'i', 'ì': 'i',
    'ō': 'o', 'ó': 'o', 'ǒ': 'o', 'ò': 'o',
    'ū': 'u', 'ú': 'u', 'ǔ': 'u', 'ù': 'u',
    'ǖ': 'v', 'ǘ': 'v', 'ǚ': 'v', 'ǜ': 'v',
}

def strip_tone(py):
    """Remove tone marks from pinyin"""
    result = ''
    for ch in py:
        result += TONE_MARKS.get(ch, ch)
    return result

# Get all pinyin syllables without tones
all_pinyin = set()
for char_code, py_str in PINYIN_DICT.items():
    if isinstance(py_str, str):
        for py in py_str.split(','):
            py = py.strip()
            if py:
                no_tone = strip_tone(py)
                if len(no_tone) >= 2:
                    all_pinyin.add(no_tone)

sorted_pinyin = sorted(all_pinyin)
print(f"Total unique pinyin syllables (no tones): {len(sorted_pinyin)}")

# Save to JSON
with open(r'C:\Users\david\Documents\all_projects\OpenIME\pinyin_table.json', 'w', encoding='utf-8') as f:
    json.dump(sorted_pinyin, f, ensure_ascii=False, indent=2)
print("Saved to pinyin_table.json")

# Verify with known syllables
known = ['zhong', 'guo', 'zhongguo', 'ni', 'hao', 'shi', 'jie']
for py in known:
    idx = sorted_pinyin.index(py) if py in sorted_pinyin else -1
    print(f"  {py}: index {idx}")
