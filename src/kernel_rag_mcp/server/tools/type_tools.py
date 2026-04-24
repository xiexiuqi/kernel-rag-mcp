from typing import List, Dict, Any, Optional

from ...storage.metadata_store import MetadataStore


class TypeTools:
    def __init__(self, metadata_store: MetadataStore):
        self.store = metadata_store

    def git_search_by_type(
        self,
        type_tags: List[str],
        subsys: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        all_commits = self.store.search_git_commits(limit=limit * 10)
        results = []

        for commit in all_commits:
            commit_tags = commit.get("type_tags", "")
            if not commit_tags:
                continue

            has_any = any(tag in commit_tags for tag in type_tags)
            if not has_any:
                continue

            if subsys and subsys not in commit.get("title", ""):
                continue

            date = commit.get("date", "")
            if since and date < since:
                continue
            if until and date > until:
                continue

            results.append(commit)

        return results[:limit]

    def git_type_stats(
        self,
        subsys: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None
    ) -> Dict[str, int]:
        all_commits = self.store.search_git_commits(limit=100000)
        stats = {}
        total = 0

        for commit in all_commits:
            date = commit.get("date", "")
            if since and date < since:
                continue
            if until and date > until:
                continue
            if subsys and subsys not in commit.get("title", ""):
                continue

            total += 1
            tags = commit.get("type_tags", "")
            if tags:
                for tag in tags.split(","):
                    tag = tag.strip()
                    if tag:
                        stats[tag] = stats.get(tag, 0) + 1

        stats["total"] = total
        return stats
