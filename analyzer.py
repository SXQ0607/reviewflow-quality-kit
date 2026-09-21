#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyzer.py — 稳健的 LLM 结构化抽取工具（ReviewFlow 开源核心）。

特性（取自开源社区精华，已融合进本项目）：
  - 代码本（codebook）驱动归类：给每类明确定义，提升 LLM 归类稳定性（参考 CoCode）。
  - 输出修复 + 重试反馈（参考 outputguard）：剥离 markdown 围栏、抽取 JSON、
    修复常见畸形；校验失败把错误回灌 LLM 最多重试 N 次；全失败再回落兜底规则。

仅依赖 Python 标准库（urllib / re / json）。适配任何 OpenAI 兼容 /chat/completions 网关，
默认指向本机 Ollama（qwen2.5:7b）。不绑定任何 LLM SDK、不含任何平台/客户数据。
"""
import os
import re
import json
import urllib.request
from collections import Counter

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://127.0.0.1:11434/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:7b")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))

# 示例代码本（电商评价）。换成你的类别即可复用本模块。
CODEBOOK = {
    "物流": "配送/快递相关：延迟、送错地址、物流信息不更新、签收异常",
    "包装": "外包装/缓冲相关：纸箱破损、无缓冲、边角磕坏、封箱问题",
    "质量": "商品本身功能/做工：坏了、故障、无法使用、材质差",
    "客服": "与商家沟通：回复慢、态度差、未解释清楚退换步骤",
    "描述": "与页面说明不符：尺寸色差、实物与描述不一致",
    "其他": "无实质内容或不属于以上（如『暂时没意见』）",
}


def _llm_raw(prompt):
    """调用 LLM 网关，返回模型文本。异常上抛。"""
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(LLM_ENDPOINT, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)["choices"][0]["message"]["content"]
    except Exception:
        return raw


def repair_json(text):
    """剥离 markdown 围栏 → 抽取首个 [ ] / { } → 修常见畸形。返回 (ok, obj)。
    不耦合任何 LLM SDK（参考 outputguard 的轻量修复策略）。"""
    if not text:
        return False, None
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)   # strip_fences
    s = re.sub(r"\s*```$", "", s)
    m = re.search(r"\[.*\]", s, re.S) or re.search(r"\{.*\}", s, re.S)  # extract_json
    if not m:
        return False, None
    s = m.group(0)
    s = s.replace("，", ",").replace("“", '"').replace("”", '"') \
         .replace("‘", "'").replace("’", "'")
    try:
        return True, json.loads(s)
    except Exception:
        pass
    s2 = re.sub(r",\s*([\]}])", r"\1", s)                  # fix_commas 尾逗号
    if '"' not in s2:
        s2 = s2.replace("'", '"')                           # fix_quotes
    try:
        return True, json.loads(s2)
    except Exception:
        return False, None


def llm_classify(texts, categories=None, codebook=None, max_retries=2):
    """用 LLM 给文本列表归类。texts: list[str]；返回 {index: {category, suggestion, reply}} 或 None。

    categories / codebook 不传则用内置电商示例。失败返回 None（调用方回落兜底）。"""
    cats = categories or list((codebook or CODEBOOK).keys())
    cb = codebook or CODEBOOK
    codebook_text = "\n".join(f"- {k}：{v}" for k, v in cb.items())
    numbered = "\n".join(f"{i}|{t}" for i, t in enumerate(texts, 1))
    base = (
        "你是文本分析助手。请对下列每条文本分类，并给出动作指令与回复。\n"
        "类别代码本（每条只能取其一）：\n" + codebook_text + "\n\n"
        "只输出严格 JSON 数组，不要解释文字。每条一个对象，字段：\n"
        "id(整数)、category(只能取上述类别之一)、"
        "suggestion(给执行方的动作指令，以动词开头，≤30字)、"
        "reply(得体回复，≤40字，禁止承诺赔偿或推诿)。\n"
        "无实质内容 category 填「其他」。\n"
        f"文本列表（id|文本）：\n{numbered}\n\nJSON："
    )
    last_err = ""
    for attempt in range(max_retries + 1):
        prompt = base + (f"\n\n上一次输出解析失败：{last_err}\n请重新输出合规 JSON 数组。"
                         if attempt > 0 else "")
        try:
            content = _llm_raw(prompt)
        except Exception as exc:
            last_err = f"第{attempt+1}次调用异常: {type(exc).__name__}: {str(exc)[:80]}"
            continue
        ok, arr = repair_json(content)
        if ok and isinstance(arr, list):
            out = {}
            for item in arr:
                try:
                    i = int(item.get("id"))
                except Exception:
                    continue
                cat = str(item.get("category") or "").strip()
                out[i] = {
                    "category": cat if cat in cats else "其他",
                    "suggestion": str(item.get("suggestion") or "").strip()[:120],
                    "reply": str(item.get("reply") or "").strip()[:180],
                }
            if out:
                return out
        last_err = f"第{attempt+1}次返回无法解析为JSON数组: {str(content)[:120]}"
    return None


if __name__ == "__main__":
    samples = [
        "快递晚了两天，物流不更新",
        "包装没缓冲边角磕坏",
        "客服回复太慢没说清退换步骤",
        "颜色和描述有差异",
        "暂时没有更多意见",
    ]
    res = llm_classify(samples)
    print(json.dumps(res, ensure_ascii=False, indent=2))
