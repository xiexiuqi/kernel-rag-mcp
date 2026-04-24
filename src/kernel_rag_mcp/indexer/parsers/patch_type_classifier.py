import re
from dataclasses import dataclass
from typing import List


@dataclass
class ClassificationResult:
    tags: List[str]

    def __post_init__(self):
        self.tags = list(dict.fromkeys(self.tags))

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags


class PatchTypeClassifier:
    TITLE_PATTERNS = {
        "bugfix": ["fix", "bug", "repair", "correct"],
        "performance": ["optim", "speedup", "fast", "latency", "throughput", "scale"],
        "refactor": ["refactor", "cleanup", "simplify", "remove", "rework"],
        "feature": ["add", "support", "implement", "introduce", "new"],
        "documentation": ["doc", "comment", "docs:"],
        "test": ["selftest", "test", "kselftest"],
    }

    def classify(self, title: str, body: str = "") -> ClassificationResult:
        title_lower = title.lower()
        body_lower = body.lower()
        tags = []

        for tag, keywords in self.TITLE_PATTERNS.items():
            if any(kw in title_lower for kw in keywords):
                tags.append(tag)

        if title_lower.startswith("revert"):
            tags.append("revert")

        if "regression" in title_lower:
            tags.append("regression")
            tags.append("bugfix")
            if any(kw in body_lower for kw in ["optimize", "performance", "scalability"]):
                tags.append("performance")

        if "cve" in title_lower:
            tags.append("security")

        if re.search(r'Reported-by:\s*security@', body, re.IGNORECASE):
            tags.append("security")

        if re.search(r'Cc:\s*stable@', body, re.IGNORECASE):
            tags.append("stable")

        if title_lower.startswith("stable:") or "[patch stable]" in title_lower:
            tags.append("stable")

        if re.search(r'Fixes:\s*[a-f0-9]+', body, re.IGNORECASE):
            if "bugfix" not in tags:
                tags.append("bugfix")

        return ClassificationResult(tags=tags)
