import re
from typing import Dict, List


class CausalParser:
    FIXES_PATTERN = re.compile(r'Fixes:\s*([a-f0-9]+)', re.IGNORECASE)
    INTRODUCED_BY_PATTERN = re.compile(r'Introduced-by:\s*([a-f0-9]+)', re.IGNORECASE)
    CC_STABLE_PATTERN = re.compile(r'Cc:\s*stable@', re.IGNORECASE)
    REPORTED_BY_PATTERN = re.compile(r'Reported-by:\s*(.+)')
    REVIEWED_BY_PATTERN = re.compile(r'Reviewed-by:\s*(.+)')
    TESTED_BY_PATTERN = re.compile(r'Tested-by:\s*(.+)')
    ACKET_BY_PATTERN = re.compile(r'Acked-by:\s*(.+)')
    SUGGESTED_BY_PATTERN = re.compile(r'Suggested-by:\s*(.+)')
    CO_DEV_BY_PATTERN = re.compile(r'Co-developed-by:\s*(.+)')
    BISECTED_BY_PATTERN = re.compile(r'Bisected-by:\s*(.+)')
    CHERRY_PICK_PATTERN = re.compile(r'cherry\s*picked\s*from\s*commit\s*([a-f0-9]+)', re.IGNORECASE)

    def extract_labels(self, body: str) -> Dict[str, any]:
        labels = {}

        fixes_matches = self.FIXES_PATTERN.findall(body)
        if fixes_matches:
            labels["Fixes"] = fixes_matches[0] if len(fixes_matches) == 1 else fixes_matches

        introduced_matches = self.INTRODUCED_BY_PATTERN.findall(body)
        if introduced_matches:
            labels["Introduced-by"] = introduced_matches[0] if len(introduced_matches) == 1 else introduced_matches

        if self.CC_STABLE_PATTERN.search(body):
            labels["Cc-stable"] = True

        cherry_match = self.CHERRY_PICK_PATTERN.search(body)
        if cherry_match:
            labels["Cherry-picked-from"] = cherry_match.group(1)

        for label, pattern in [
            ("Reported-by", self.REPORTED_BY_PATTERN),
            ("Reviewed-by", self.REVIEWED_BY_PATTERN),
            ("Tested-by", self.TESTED_BY_PATTERN),
            ("Acked-by", self.ACKET_BY_PATTERN),
            ("Suggested-by", self.SUGGESTED_BY_PATTERN),
            ("Co-developed-by", self.CO_DEV_BY_PATTERN),
            ("Bisected-by", self.BISECTED_BY_PATTERN),
        ]:
            matches = pattern.findall(body)
            if matches:
                labels[label] = matches

        return labels

    def is_revert(self, title: str) -> bool:
        return title.lower().startswith("revert")
