"""Pure retrieval over service-provided evidence. No database or file access."""

import re


def tokens(text):
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        words.update(run[index : index + 2] for index in range(len(run) - 1))
    return words


def retrieve(question, evidence, budget=48000):
    query = tokens(question)
    ranked = sorted(
        enumerate(evidence), key=lambda pair: (-len(query & tokens(pair[1].quote)), pair[0])
    )
    selected, used = [], 0
    for _, item in ranked:
        cost = len(item.quote)
        if used + cost > budget or len(selected) >= 32:
            continue
        selected.append(item)
        used += cost
    return selected
