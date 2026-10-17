"""When two surface forms name the same thing.

The rule is deliberately stingy: merging two different things costs more than keeping a
duplicate (docs/05 §4.2). Two forms merge only when one is a contiguous run of tokens inside
the other and every extra token is a maker, a format, a version number or a parameter size --
never a product variant such as `pro`, `sol` or `max`.

    same_entity("mirelo sfx", "mirelo sfx 2.0")        -> True
    same_entity("gpt 6.1", "gpt 6.1 sol")              -> False
    canonical(["hy memory", "hy-memory-30b-a3b"])      -> "hy memory"
"""
from __future__ import annotations

import re

# A brand or maker that may stand before the name. `muse` and `deepseek` are here because
# posts drop them freely ("muse spark open" / "spark open"), but they are part of the name
# itself, so canonical() keeps them.
PREFIXES = {"meta", "muse", "openai", "google", "anthropic", "microsoft", "nvidia", "rtx",
            "bytedance", "alibaba", "tencent", "xai", "baidu", "deepseek"}
# The ones that are only the company: canonical() drops them.
COMPANIES = PREFIXES - {"muse", "deepseek"}
# A maker alone is a company, not a new thing: a headline that starts with "OpenAI" must
# not report "openai" as this week's new name. A version keeps it ("openai o3").
MAKERS = COMPANIES | {"huggingface", "hugging face", "mistral", "amazon", "aws", "apple", "samsung",
                      "cohere", "stability", "perplexity", "github", "adobe", "salesforce", "ibm",
                      "intel", "amd", "x", "twitter", "facebook", "instagram", "linkedin", "tiktok"}
# A delivery format or a quantization: it says where or how the thing runs, not which thing.
FORMATS = {"api", "gguf", "lora", "awq", "fp8", "comfy", "ollama", "lmstudio", "ckpt",
           "safetensors", "onnx", "ggml", "q8", "q4"}
# A product variant. `gpt 6.1` and `gpt 6.1 sol` are different things.
VARIANTS = {"pro", "sol", "max", "mini", "ultra", "lite", "turbo", "instruct", "chat",
            "vision", "thinking", "coder", "omni", "tts", "preview", "flash", "x"}
VERSION = re.compile(r"^v?\d+(\.\d+)*$")
SIZE = re.compile(r"^\d+(\.\d+)?b$|^a\d+b$")
KEEP = re.compile(r"[^a-z0-9. ]")


def _clean(s: str) -> str:
    s = s.strip()
    if "://" in s:                      # a URL names the thing in its last path segment
        parts = [p for p in s.split("://", 1)[1].split("?")[0].split("/") if p]
        if len(parts) > 1:
            s = parts[-1]
    s = re.sub(r"@\w+", " ", s)         # an @handle is not part of the name
    s = re.sub(r"[-_/]", " ", s.lower())
    return " ".join(KEEP.sub(" ", s).split())


def tokens(s: str) -> list[str]:
    return _clean(s).split()


def _key(token: str) -> str:
    """`4.0` and `4` are the same version when comparing, but keep their spelling for display."""
    m = re.fullmatch(r"(\d+(?:\.\d+)*?)\.0+", token)
    return m.group(1) if m else token


def _extra_ok(token: str) -> bool:
    return token in PREFIXES or token in FORMATS or bool(VERSION.match(token) or SIZE.match(token))


def normalize(s: str) -> str:
    return " ".join(tokens(s))


def same_entity(a: str, b: str) -> bool:
    """True when one form is the other plus a maker, a format, a version or a size."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    ka, kb = [_key(t) for t in ta], [_key(t) for t in tb]
    if ka == kb:
        return True
    if len(ka) == len(kb):
        return False
    short, long_, raw = (ka, kb, tb) if len(ka) < len(kb) else (kb, ka, ta)
    for i in range(len(long_) - len(short) + 1):
        if long_[i:i + len(short)] != short:
            continue
        extra = long_[:i] + long_[i + len(short):]
        raw_extra = raw[:i] + raw[i + len(short):]
        return all(_extra_ok(t) for t in raw_extra) and not any(t in VARIANTS for t in raw_extra)
    return False


def canonical(forms: list[str]) -> str:
    """The form to store: the longest one with the company and the format stripped off."""
    best: tuple[int, bool, str] = (-1, False, "")
    for form in forms:
        ts = tokens(form)
        while ts and ts[0] in COMPANIES:
            ts = ts[1:]
        while ts and (ts[-1] in FORMATS or SIZE.match(ts[-1]) or ts[-1] in {"ckpt", "onnx"}):
            ts = ts[:-1]
        text = " ".join(ts) or normalize(form)
        if (len(ts), text == normalize(text), text) > best:
            best = (len(ts), text == normalize(text), text)
    return best[2]


def cluster(rows: list[dict]) -> list[dict]:
    """Group rows that name the same thing. Two rows merge only when the strings agree and
    they were seen on the same day or by the same source: a name reused a week later by
    another signal is not evidence of the same entity (docs/05 §4.2)."""
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            same_place = a.get("day") == b.get("day") or a.get("source") == b.get("source")
            if same_place and same_entity(a["term"], b["term"]):
                parent[find(i)] = find(j)

    groups: dict[int, list[dict]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)
    out = []
    for members in groups.values():
        forms = [m["term"] for m in members]
        out.append({"canonical": canonical(forms), "aliases": sorted(set(forms)), "rows": members})
    return sorted(out, key=lambda c: c["canonical"])
