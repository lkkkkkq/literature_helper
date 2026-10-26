"""Bounded lexical retrieval with bilingual concepts and page context. No model calls."""

import math
import re
from collections import Counter

# Deterministic query expansion; these are search hints, never evidence.
CONCEPTS = (
    ("诱导功率", "induced power", "induced velocity"),
    ("剖面功率", "型阻功率", "profile power"),
    ("寄生功率", "废阻功率", "parasite power", "parasitic power"),
    ("功率", "power"),
    ("推力", "thrust"),
    ("阻力", "drag"),
    ("升力", "lift"),
    ("风速", "wind velocity", "wind speed"),
    ("空速", "air velocity", "airspeed"),
    ("地速", "ground velocity"),
    ("公式", "equation", "formula", "model summary"),
    ("参数", "parameter"),
    ("计算", "computed", "calculation"),
    ("浓度", "concentration"),
    ("微塑料", "microplastic", "microplastics"),
    ("采样", "sampling"),
    ("方法", "method", "methods"),
    ("结果", "results"),
    ("局限", "limitations"),
)
STOP = {"a", "i", "p", "t", "the", "of", "and", "in", "to", "is", "for", "这三", "三个"}


def tokens(text):
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        words.update(run[index : index + 2] for index in range(len(run) - 1))
    return words - STOP


def retrieve(question, evidence, budget=48000):
    if not evidence or budget <= 0:
        return []
    if len(evidence) <= 32 and sum(len(item.quote) for item in evidence) <= budget:
        return list(evidence)
    query = tokens(question)
    concepts = [group for group in CONCEPTS if any(term in question.lower() for term in group)]
    for group in concepts:
        for term in group:
            query.update(tokens(term))
    symbols = set()
    for label, symbol in (("诱导功率", "pi"), ("剖面功率", "pp"), ("寄生功率", "ppar")):
        if label in question or symbol in query:
            symbols.add(symbol)
            query.add(symbol)
    terms = [tokens(item.quote) for item in evidence]
    counts = Counter(term for row in terms for term in row)
    weights = {term: math.log(1 + len(evidence) / (1 + counts[term])) for term in query}
    scores = []
    for item, row in zip(evidence, terms, strict=True):
        score = sum(weights[term] for term in query & row)
        score /= 1 + math.log1p(len(row)) / 8
        score += 4 * sum(any(term in item.quote.lower() for term in group) for group in concepts)
        score += 6 * len(symbols & row)
        scores.append(score)
    ranked = sorted(range(len(evidence)), key=lambda index: (-scores[index], index))
    # Do not silently substitute the beginning of a document when nothing matches.
    ranked = [index for index in ranked if scores[index] > 0]
    selected, used, seen = [], 0, set()

    def add(index):
        nonlocal used
        item = evidence[index]
        if index in seen or len(selected) >= 32 or used + len(item.quote) > budget:
            return
        selected.append(item)
        seen.add(index)
        used += len(item.quote)

    # Reserve most slots for direct hits, then fill with same/adjacent page context.
    for index in ranked[:20]:
        add(index)
    anchors = list(seen)
    nearby = []
    for index, item in enumerate(evidence):
        if index in seen or not item.locations:
            continue
        distance = min(
            (
                abs(location.page - other.page)
                for anchor in anchors
                if evidence[anchor].asset_id == item.asset_id
                for other in evidence[anchor].locations
                for location in item.locations
            ),
            default=999,
        )
        if distance <= 1:
            nearby.append((distance, -scores[index], index))
    for _, _, index in sorted(nearby):
        add(index)
    for index in ranked:
        add(index)
    return selected
