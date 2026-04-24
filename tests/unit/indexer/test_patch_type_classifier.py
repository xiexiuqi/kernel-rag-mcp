import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.indexer.parsers.patch_type_classifier import PatchTypeClassifier, ClassificationResult


class TestPatchTypeClassifier:
    def test_bugfix_from_title(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("tcp: fix inaccurate RTO", "")
        assert "bugfix" in result.tags

    def test_bugfix_from_fixes_tag(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("some change", "Fixes: a1b2c3d")
        assert "bugfix" in result.tags

    def test_performance_from_title(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("sched: optimize vruntime update", "")
        assert "performance" in result.tags

    def test_performance_from_speedup(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("net: speedup skb allocation", "")
        assert "performance" in result.tags

    def test_regression_auto_adds_bugfix(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("fix regression in scheduler", "")
        assert "regression" in result.tags
        assert "bugfix" in result.tags

    def test_regression_with_performance_body(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify(
            "fix regression in load balance",
            "This optimizes the calculation"
        )
        assert "regression" in result.tags
        assert "bugfix" in result.tags
        assert "performance" in result.tags

    def test_feature_from_add(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("net: add MPTCP v1 support", "")
        assert "feature" in result.tags

    def test_refactor_from_cleanup(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("mm: refactor slab allocation path", "")
        assert "refactor" in result.tags

    def test_revert_from_title(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify('Revert "tcp: change RTO"', "")
        assert "revert" in result.tags

    def test_documentation_from_doc(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("doc: update scheduler documentation", "")
        assert "documentation" in result.tags

    def test_test_from_selftest(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("selftest: add TCP fastopen test", "")
        assert "test" in result.tags

    def test_security_from_cve(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("fix use-after-free in mm (CVE-2023-XXXX)", "")
        assert "security" in result.tags

    def test_stable_from_cc_stable(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("some fix", "Cc: stable@vger.kernel.org")
        assert "stable" in result.tags

    def test_stable_from_stable_tag(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("stable: fix race in tcp", "")
        assert "stable" in result.tags

    def test_non_orthogonal_multiple_tags(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify(
            "sched: fix regression in vruntime optimize",
            "This patch optimizes and fixes a regression"
        )
        assert "bugfix" in result.tags
        assert "performance" in result.tags
        assert "regression" in result.tags

    def test_no_false_positives(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify("mm: page allocation", "")
        assert result.tags == []

    def test_non_orthogonal_feature_with_performance(self):
        classifier = PatchTypeClassifier()
        result = classifier.classify(
            "net: add XDP support with optimized fast path",
            ""
        )
        assert "feature" in result.tags
        assert "performance" in result.tags


class TestClassificationResult:
    def test_tags_deduplication(self):
        result = ClassificationResult(tags=["performance", "performance", "bugfix"])
        assert result.tags.count("performance") == 1
        assert "bugfix" in result.tags

    def test_has_tag_method(self):
        result = ClassificationResult(tags=["performance", "bugfix"])
        assert result.has_tag("performance")
        assert not result.has_tag("feature")
