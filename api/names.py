"""Alias matching shared by Ask (find the system in a question) and upload (find known entities)."""
import re

GENERIC = {"api", "lumen", "service", "app", "the"}


def system_aliases(name):
    low = name.lower()
    aliases = {low}
    core = [t for t in re.findall(r"[a-z0-9]+", low) if t not in GENERIC]
    if core:
        aliases.add(" ".join(core))
        for t in core:
            if len(t) >= 4:
                aliases.add(t)
    return aliases


def person_aliases(name):
    low = name.lower()
    aliases = {low}
    parts = low.split()
    if len(parts) > 1:
        aliases.add(parts[0])
    return aliases


def _has(text_low, alias):
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text_low) is not None


def find_in_text(text, alias_map):
    """alias_map: {key: set(aliases)}. Returns keys found, longest alias match first."""
    low = text.lower()
    hits = []
    for key, aliases in alias_map.items():
        best = max((len(a) for a in aliases if _has(low, a)), default=0)
        if best:
            hits.append((best, key))
    hits.sort(key=lambda h: -h[0])
    return [k for _, k in hits]


def unique_alias_index(entities, alias_fn):
    """entities: [(id, name)]. Returns {alias: id} dropping aliases shared by more than one entity."""
    seen, dup = {}, set()
    for eid, name in entities:
        for a in alias_fn(name):
            if a in seen and seen[a] != eid:
                dup.add(a)
            seen[a] = eid
    return {a: i for a, i in seen.items() if a not in dup}
