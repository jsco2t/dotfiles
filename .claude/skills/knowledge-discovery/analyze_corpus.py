#!/usr/bin/env python3
"""Analyze a document corpus for knowledge discovery.

Reads all markdown files in a directory, extracts metadata, builds
topic clusters, and identifies gaps — outputting a structured JSON
report that an LLM can consume cheaply.

Zero external dependencies. Works with Python 3.8+ on macOS and Linux.

Usage:
    python3 analyze_corpus.py <directory> [--exclude dir1,dir2,...]
    python3 analyze_corpus.py kb/
    python3 analyze_corpus.py kb/ --exclude templates,scratch
"""

import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Directories to always skip
DEFAULT_EXCLUDES = {
    "templates", "TaskNotes", "boards", ".obsidian",
    ".git", "scratch", "xchive", "resources", ".tools",
    ".claude", "node_modules", "__pycache__",
}

# Stop words for title/heading keyword extraction
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "shall",
    "not", "no", "nor", "so", "if", "then", "than", "that", "this",
    "it", "its", "how", "what", "when", "where", "which", "who", "why",
    "as", "up", "out", "about", "into", "over", "after", "before",
    "between", "under", "through", "during", "without", "within",
    "using", "via", "vs", "set", "get", "use", "new", "old",
}


def parse_frontmatter(text):
    """Extract YAML frontmatter from markdown text.

    Parses the subset of YAML used in these docs: scalar values and
    simple lists. No external YAML library needed.
    """
    if not text.startswith("---"):
        return {}

    end = text.find("\n---", 3)
    if end == -1:
        return {}

    fm_text = text[4:end]
    result = {}
    current_key = None
    current_list = None

    for line in fm_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # List item under current key
        if stripped.startswith("- ") and current_key:
            if current_list is None:
                current_list = []
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue

        # Save any pending list
        if current_list is not None and current_key:
            result[current_key] = current_list
            current_list = None

        # Key: value pair
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            current_key = key
            if val:
                result[key] = val
            # If val is empty, next lines might be a list
            continue

    # Save final pending list
    if current_list is not None and current_key:
        result[current_key] = current_list

    return result


def extract_wiki_links(text):
    """Extract wiki-link targets from markdown, skipping code blocks."""
    links = []
    in_code_block = False

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Match [[target]] or [[target|alias]] or [[target#heading]]
        for match in re.finditer(r"\[\[([^\]|#]+)", line):
            target = match.group(1).strip()
            if target and not target.endswith("/"):
                links.append(target)

    return links


def extract_keywords(title):
    """Extract meaningful keywords from a title string."""
    if not title:
        return []
    # Split on non-alphanumeric, lowercase, filter stops and short words
    words = re.findall(r"[a-zA-Z0-9]+", title.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def count_words(text):
    """Rough word count of the body (excluding frontmatter and code blocks)."""
    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]

    # Strip code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    return len(text.split())


def parse_date(date_str):
    """Parse an ISO 8601 date string, tolerant of timezone offsets."""
    if not date_str:
        return None
    # Strip timezone for simpler parsing
    date_str = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def scan_directory(directory, excludes):
    """Scan a directory for markdown files, returning document metadata."""
    docs = []
    dir_path = Path(directory)

    for root, dirs, files in os.walk(dir_path):
        # Prune excluded directories
        dirs[:] = [
            d for d in dirs
            if d not in excludes and not d.startswith(".")
        ]

        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue

            fpath = Path(root) / fname
            rel_path = str(fpath.relative_to(dir_path.parent)
                           if dir_path.parent != fpath.parent
                           else fpath.relative_to(dir_path.parent))

            try:
                text = fpath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            fm = parse_frontmatter(text)
            title = fm.get("title", fname.replace(".md", ""))
            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]

            createdate = parse_date(fm.get("createdate", ""))
            wiki_links = extract_wiki_links(text)
            keywords = extract_keywords(title)
            words = count_words(text)

            docs.append({
                "file": str(fpath.relative_to(dir_path.parent)),
                "filename": fname.replace(".md", ""),
                "title": title,
                "tags": tags,
                "keywords": keywords,
                "createdate": createdate.isoformat() if createdate else None,
                "wiki_links": wiki_links,
                "word_count": words,
                "id": fm.get("id", ""),
            })

    return docs


def build_clusters(docs):
    """Build document clusters based on weighted tag similarity.

    Uses IDF-weighted tag overlap so that specific tags (nfs, kerberos,
    podman) carry more weight than broad tags (linux, networking, go).
    Documents must share enough "informative" tag weight to cluster.
    """
    n = len(docs)
    if n == 0:
        return []

    # Compute IDF for each tag: log(N / doc_freq)
    tag_doc_freq = Counter()
    for doc in docs:
        tag_doc_freq.update(set(doc["tags"]))

    tag_idf = {}
    for tag, freq in tag_doc_freq.items():
        tag_idf[tag] = math.log(n / freq) if freq > 0 else 0

    # Tags with IDF < 1.0 appear in >36% of docs — too generic alone
    # but still contribute partial weight
    GENERIC_IDF_THRESHOLD = 1.0

    def informative_tags(tags):
        """Return tags with IDF above the generic threshold."""
        return {t for t in tags if tag_idf.get(t, 0) >= GENERIC_IDF_THRESHOLD}

    def shared_weight(tags_a, tags_b):
        """Weighted overlap score between two tag sets."""
        shared = set(tags_a) & set(tags_b)
        return sum(tag_idf.get(t, 0) for t in shared)

    # Minimum weight to connect two documents.
    # Two specific tags (IDF ~3.0 each) = 6.0, which is a strong signal.
    # One specific + one moderate = ~4.5, still decent.
    MIN_CONNECT_WEIGHT = 4.0

    # Union-find
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Pairwise comparison using weighted overlap
    for i in range(n):
        for j in range(i + 1, n):
            w = shared_weight(docs[i]["tags"], docs[j]["tags"])
            if w >= MIN_CONNECT_WEIGHT:
                union(i, j)

    # Also cluster by wiki-links (strong signal)
    filename_to_idx = {doc["filename"]: i for i, doc in enumerate(docs)}
    for i, doc in enumerate(docs):
        for link in doc["wiki_links"]:
            if link in filename_to_idx:
                union(i, filename_to_idx[link])

    # Collect clusters
    cluster_map = defaultdict(list)
    for i in range(n):
        cluster_map[find(i)].append(i)

    # Recursively sub-cluster any group >20 docs with increasing
    # thresholds until all clusters are manageable
    final_clusters = []
    MAX_CLUSTER_SIZE = 20

    def refine(members, weight):
        if len(members) <= MAX_CLUSTER_SIZE:
            final_clusters.append(members)
            return
        subs = _sub_cluster(
            members, docs, tag_idf, filename_to_idx,
            min_weight=weight,
        )
        for sub in subs:
            if len(sub) > MAX_CLUSTER_SIZE:
                refine(sub, weight + 2.0)
            else:
                final_clusters.append(sub)

    for members in cluster_map.values():
        if len(members) < 2:
            continue
        refine(members, 6.0)

    # Build output
    clusters = []
    for members in final_clusters:
        if len(members) < 2:
            continue

        member_docs = [docs[i] for i in members]

        # Name by most informative (highest IDF) shared tags
        cluster_tags = Counter()
        for doc in member_docs:
            for t in doc["tags"]:
                if tag_idf.get(t, 0) >= GENERIC_IDF_THRESHOLD:
                    cluster_tags[t] += 1

        top_tags = [t for t, _ in cluster_tags.most_common(3)]
        cluster_name = " + ".join(top_tags) if top_tags else "misc"

        clusters.append({
            "name": cluster_name,
            "size": len(members),
            "tags": [t for t, _ in cluster_tags.most_common(8)],
            "documents": [
                {"file": doc["file"], "title": doc["title"]}
                for doc in member_docs
            ],
        })

    clusters.sort(key=lambda c: c["size"], reverse=True)
    return clusters


def _sub_cluster(members, docs, tag_idf, filename_to_idx, min_weight):
    """Re-cluster a large group with a tighter similarity threshold."""
    n = len(members)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        doc_i = docs[members[i]]
        for j in range(i + 1, n):
            doc_j = docs[members[j]]
            shared = set(doc_i["tags"]) & set(doc_j["tags"])
            w = sum(tag_idf.get(t, 0) for t in shared)
            if w >= min_weight:
                union(i, j)

    # Wiki-links within this group
    member_filenames = {docs[m]["filename"]: i for i, m in enumerate(members)}
    for i, m in enumerate(members):
        for link in docs[m]["wiki_links"]:
            if link in member_filenames:
                union(i, member_filenames[link])

    sub_map = defaultdict(list)
    for i in range(n):
        sub_map[find(i)].append(members[i])

    return list(sub_map.values())


def find_new_branches(docs, clusters, recency_days=90):
    """Identify recent documents that aren't in a large cluster.

    These are 'new topic branches' — the user started exploring
    something but hasn't built depth yet.
    """
    # Which docs are in clusters of size >= 3?
    clustered_files = set()
    for cluster in clusters:
        if cluster["size"] >= 3:
            for doc in cluster["documents"]:
                clustered_files.add(doc["file"])

    now = datetime.now()
    new_branches = []

    for doc in docs:
        if doc["file"] in clustered_files:
            continue
        if not doc["createdate"]:
            continue

        created = parse_date(doc["createdate"])
        if not created:
            continue

        age_days = (now - created).days
        if age_days <= recency_days:
            new_branches.append({
                "file": doc["file"],
                "title": doc["title"],
                "tags": doc["tags"],
                "age_days": age_days,
                "word_count": doc["word_count"],
            })

    new_branches.sort(key=lambda d: d["age_days"])
    return new_branches


def find_high_value_isolates(docs, clusters):
    """Identify documents not in clusters but likely high-value.

    Heuristics for 'high value':
    - Longer documents (more depth/effort invested)
    - Documents with unique tag combinations (bridge topics)
    - Documents whose tags span multiple clusters
    """
    clustered_files = set()
    for cluster in clusters:
        for doc in cluster["documents"]:
            clustered_files.add(doc["file"])

    # Build a map of which clusters each tag appears in
    tag_to_clusters = defaultdict(set)
    for i, cluster in enumerate(clusters):
        for tag in cluster["tags"]:
            tag_to_clusters[tag].add(i)

    isolates = []
    for doc in docs:
        if doc["file"] in clustered_files:
            continue

        # Score based on word count and tag-cluster bridging
        bridge_score = 0
        for tag in doc["tags"]:
            bridge_score += len(tag_to_clusters.get(tag, set()))

        # Longer docs with more cross-cluster tags score higher
        value_score = (
            min(doc["word_count"] / 200, 5)  # depth, capped at 5
            + bridge_score                    # cross-cluster relevance
        )

        isolates.append({
            "file": doc["file"],
            "title": doc["title"],
            "tags": doc["tags"],
            "word_count": doc["word_count"],
            "value_score": round(value_score, 1),
        })

    isolates.sort(key=lambda d: d["value_score"], reverse=True)
    return isolates[:15]  # Top 15 high-value isolates


def find_cluster_gaps(clusters, tag_freq):
    """Identify potential knowledge gaps within clusters.

    Looks for tags that appear in a cluster's documents but have
    low overall coverage, suggesting the topic exists but isn't
    well-explored.
    """
    gaps = []
    for cluster in clusters:
        if cluster["size"] < 3:
            continue

        cluster_tags = set(cluster["tags"])
        for tag in cluster_tags:
            freq = tag_freq.get(tag, 0)
            # Tags that appear in the cluster but have few docs overall
            if 1 <= freq <= 2:
                gaps.append({
                    "cluster": cluster["name"],
                    "tag": tag,
                    "doc_count": freq,
                    "note": f"'{tag}' appears in cluster "
                            f"'{cluster['name']}' but only has "
                            f"{freq} doc(s) total",
                })

    return gaps


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_corpus.py <directory> "
              "[--exclude dir1,dir2,...]", file=sys.stderr)
        sys.exit(1)

    directory = sys.argv[1]
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Parse --exclude flag
    excludes = set(DEFAULT_EXCLUDES)
    for i, arg in enumerate(sys.argv[2:], 2):
        if arg == "--exclude" and i + 1 < len(sys.argv):
            excludes.update(sys.argv[i + 1].split(","))

    docs = scan_directory(directory, excludes)
    if not docs:
        print(json.dumps({"error": "No markdown files found"}))
        sys.exit(1)

    # Tag frequency across all docs
    tag_freq = Counter()
    for doc in docs:
        tag_freq.update(doc["tags"])

    clusters = build_clusters(docs)
    new_branches = find_new_branches(docs, clusters)
    high_value = find_high_value_isolates(docs, clusters)
    gaps = find_cluster_gaps(clusters, tag_freq)

    report = {
        "summary": {
            "total_documents": len(docs),
            "total_clusters": len(clusters),
            "clustered_documents": sum(c["size"] for c in clusters),
            "unclustered_documents": len(docs) - sum(
                c["size"] for c in clusters
            ),
            "new_branches": len(new_branches),
            "directory": directory,
        },
        "tag_frequency": [
            {"tag": t, "count": c}
            for t, c in tag_freq.most_common(30)
        ],
        "clusters": clusters,
        "new_topic_branches": new_branches,
        "high_value_isolates": high_value,
        "cluster_gaps": gaps,
    }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
