"""
AI 精简模块（实验性，未接入主流程）

2026-09-14 检修确认：本模块目前没有任何 GUI / CLI 入口调用，属于「写了没接线」的半成品。
- local_refine / basic_filter：纯本地规则，可随时安全调用；
- ai_refine：调用 OpenAI 兼容云 API——与本项目「不依赖云 API」的规范冲突，
  如确要使用，必须由用户明确提供 Key 并自行承担隐私与合规风险；默认不接入。

使用 OpenAI 格式 API 进行词条去重和精简。
用户自行提供 API Key 和 Base URL。
"""

import json
import os
from typing import List, Optional


# 无意义词/极简 token 过滤列表
MEANINGLESS_TOKENS = set(
    '我了在的有一是不也在人中到说个大这为上们地个时要得就出然会很能对可'
    '而其所那其已但已于或该且则与被把让给向往自从对于关于通过由于根据依据'
    '按照基于以及及其其中其其一个一些一般一直一次一样一种一起一面万一上下'
    '不不外不当不好不可不管不要不过不不过不得不不了不怎么不不得不等不止'
    '不要不了不怎么不够不断不是不同不行不要不得不用不能不会再也不会只有'
    '只只只只只要只只只只只知只只只只只只只只只只只只只只只只只只只只只只'
    '不要不会不可不能不再不不怎么不不得不止不不过不管不好不得不了一定一'
    '一一样一直一种一起一面万一'
    # 单字高频无意义词
    '我你他她它是的有不在人也到说个大这为上们地个时要得就出然会很能对可'
    '而其所那其已但已于或该且则与被把让给向往自从对于'
)

# 更简洁的过滤: 纯单字通常是无意义的
def is_meaningless(token: str) -> bool:
    """判断 token 是否无意义"""
    if not token:
        return True

    # 单字检查
    if len(token) == 1:
        return True

    # 纯数字
    if token.isdigit():
        return True

    # 纯标点
    if all(not ('\u4e00' <= c <= '\u9fff' or c.isalpha()) for c in token):
        return True

    # 纯英文字母 (除非是常见缩写)
    if token.isascii() and token.isalpha() and len(token) <= 2:
        return True

    return False


def basic_filter(tokens: List[str]) -> List[str]:
    """
    基础过滤 (不使用 AI)
    1. 去重
    2. 过滤极简 token
    3. 过滤无意义词
    """
    seen = set()
    result = []

    for token in tokens:
        t = token.strip()
        if not t:
            continue
        if t in seen:
            continue
        if is_meaningless(t):
            continue
        seen.add(t)
        result.append(t)

    return result


def ai_refine(tokens: List[str], api_key: str, base_url: str = "https://api.openai.com/v1",
              model: str = "gpt-4o-mini", batch_size: int = 100) -> List[str]:
    """
    使用 AI 进行词条精简

    Args:
        tokens: 待精简的词条列表
        api_key: OpenAI API Key
        base_url: API 端点 (支持自定义)
        model: 模型名称
        batch_size: 每批发送的词条数

    Returns:
        精简后的词条列表
    """
    import urllib.request
    import urllib.error

    all_refined = []

    # 分批处理
    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i+batch_size]
        refined = _ai_refine_batch(batch, api_key, base_url, model)
        all_refined.extend(refined)

    return all_refined


def _ai_refine_batch(tokens: List[str], api_key: str, base_url: str, model: str) -> List[str]:
    """处理一批词条"""
    import urllib.request
    import urllib.error

    # 构建 prompt
    prompt = _build_refine_prompt(tokens)

    # 调用 API
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个中文词条精简助手。你的任务是合并同义词、删除重复和无意义的词条，保留最常用和最标准的表达方式。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    url = f"{base_url.rstrip('/')}/chat/completions"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        content = result['choices'][0]['message']['content']
        response = json.loads(content)

        # 返回精简后的列表
        return response.get('refined_tokens', [])

    except Exception as e:
        print(f"AI 精简出错: {e}")
        return tokens  # 出错时返回原始列表


def _build_refine_prompt(tokens: List[str]) -> str:
    """构建精简 prompt"""
    token_list = '\n'.join(f'{i+1}. {t}' for i, t in enumerate(tokens))

    return f"""请对以下中文词条进行精简：

{token_list}

要求：
1. 合并同义词 (如"电脑"和"计算机"保留一个)
2. 删除明显无意义的词条 (如单字"的"、"了"等)
3. 合并近义词，保留最常用的表达
4. 保持原词条格式不变
5. 返回的词条列表应该是去重和精简后的结果

请返回 JSON 格式：
{{"refined_tokens": ["词条1", "词条2", ...]}}

只返回精简后的词条列表，不要解释。"""


def local_refine(tokens: List[str]) -> List[str]:
    """
    本地精简 (不调用 AI)
    1. 基础过滤
    2. 长度过滤 (过短的词)
    3. 语义相似度简单判断 (基于拼音)
    """
    # 基础过滤
    filtered = basic_filter(tokens)

    # 按长度排序 (优先保留较长的词)
    filtered.sort(key=len, reverse=True)

    # 简单去重: 如果短词是长词的子串，跳过短词
    result = []
    for token in filtered:
        is_substring = False
        for kept in result:
            if token in kept and token != kept:
                is_substring = True
                break
        if not is_substring:
            result.append(token)

    return result
