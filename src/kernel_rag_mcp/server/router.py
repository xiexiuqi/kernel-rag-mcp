class IntentRouter:
    def classify(self, query: str) -> str:
        q = query.lower()

        if "这行代码" in query and "引入" in query:
            return "blame"
        if "在哪一行" in query or "where is" in q or "line" in q:
            return "exact_symbol"
        if "config_" in q and ("编译" in query or "valid" in q or "能编译" in query):
            return "config_valid"
        if "bug" in q and ("commit" in q or "引入" in query or "regression" in q or "生命周期" in query):
            return "causal"
        if "演进" in query or "evolution" in q:
            return "feature_evolution"
        if "之间" in query and "哪些" in query:
            return "patch_type"
        if "性能优化" in query or ("performance" in q and "optimization" in q):
            return "performance"
        if "影响" in query or "impact" in q or "affect" in q:
            return "impact"
        if "变了什么" in query or ("history" in q and ("之间" in query or "between" in q)):
            return "history"
        if "为什么" in query or "why" in q or ("设计" in query and "怎么" not in query):
            return "mixed"

        return "semantic"
