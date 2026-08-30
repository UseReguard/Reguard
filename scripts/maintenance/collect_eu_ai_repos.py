"""Collect EU-based AI repos from GitHub.

Strategy:
1. Search GitHub for high-star AI repos (topics: llm, chatgpt, gpt, ai, ml, etc.)
2. Fetch owner location for each repo
3. Filter by EU country (27 EU + UK/CH/NO often grouped as "European")
4. Categorize as fullstack / backend / ai_product
5. Insert into PostgreSQL

EU countries (ISO codes):
AT BE BG HR CY CZ DE DK EE ES FI FR GR HU IE IT LT LU LV MT NL PL PT RO SE SI SK
Plus often grouped: UK GB CH NO IS LI

Usage:
    python3 scripts/collect_eu_ai_repos.py --target 100 --output /tmp/repos.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("collect_eu_repos")

# EU country codes + close European allies (UK, CH, NO, IS)
EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL",
    "PL", "PT", "RO", "SE", "SI", "SK", "ES",
    "GB", "UK", "CH", "NO", "IS",
}

# Country names → ISO codes (for parsing free-text locations)
COUNTRY_NAMES = {
    "austria": "AT", "belgium": "BE", "bulgaria": "BG", "croatia": "HR",
    "cyprus": "CY", "czech republic": "CZ", "czechia": "CZ", "denmark": "DK",
    "estonia": "EE", "finland": "FI", "france": "FR", "germany": "DE",
    "greece": "GR", "hungary": "HU", "ireland": "IE", "italy": "IT",
    "latvia": "LV", "lithuania": "LT", "luxembourg": "LU", "malta": "MT",
    "netherlands": "NL", "holland": "NL", "poland": "PL", "portugal": "PT",
    "romania": "RO", "spain": "ES", "sweden": "SE", "slovenia": "SI",
    "slovakia": "SK",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB",
    "switzerland": "CH", "norway": "NO", "iceland": "IS",
    # Common EU cities → country
    "paris": "FR", "berlin": "DE", "munich": "DE", "amsterdam": "NL",
    "stockholm": "SE", "copenhagen": "DK", "helsinki": "FI", "dublin": "IE",
    "vienna": "AT", "zurich": "CH", "geneva": "CH", "barcelona": "ES",
    "madrid": "ES", "milan": "IT", "rome": "IT", "lisbon": "PT",
    "warsaw": "PL", "prague": "CZ", "budapest": "HU", "athens": "GR",
    "brussels": "BE", "hamburg": "DE", "lyon": "FR", "munich": "DE",
}


def normalize_country(location: Optional[str]) -> Optional[str]:
    """Extract ISO country code from free-text location."""
    if not location:
        return None
    loc_lower = location.lower().strip()
    # Check ISO codes directly (e.g., "Berlin, DE")
    tokens = [t.strip().upper() for t in re.split(r"[,/]", location)]
    for token in tokens:
        if token in EU_COUNTRIES:
            # Normalize UK → GB
            return "GB" if token == "UK" else token
    # Check country names
    for name, code in COUNTRY_NAMES.items():
        if name in loc_lower:
            return "GB" if code == "UK" else code
    return None


def gh_api(endpoint: str, method: str = "GET", params: dict = None) -> dict:
    """Call GitHub API via gh CLI (handles auth automatically).

    params: dict of query/body params (each becomes -f key=value)
    """
    cmd = ["gh", "api", endpoint, "--method", method]
    if params:
        for key, value in params.items():
            cmd.extend(["-f", f"{key}={value}"])
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        log.error(f"gh api failed: {result.stderr[:200]}")
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def search_repos(query: str, per_page: int = 30, page: int = 1) -> list[dict]:
    """Search GitHub repos via REST search API."""
    result = gh_api("search/repositories", params={
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
        "page": page,
    })
    return result.get("items", [])


def fetch_owner_location(owner_login: str) -> Optional[str]:
    """Get owner's profile location from GitHub."""
    result = gh_api(f"users/{owner_login}")
    return result.get("location")


def categorize_repo(repo: dict) -> str:
    """Categorize as fullstack / backend / ai_product / ml_framework / data."""
    topics = set(t.lower() for t in repo.get("topics", []))
    desc = (repo.get("description") or "").lower()
    lang = (repo.get("language") or "").lower()

    fullstack_signals = {"fullstack", "full-stack", "webapp", "nextjs", "react", "vue", "svelte", "frontend"}
    backend_signals = {"backend", "api", "server", "fastapi", "django", "flask", "spring"}
    ai_signals = {"llm", "gpt", "chatgpt", "ai", "ml", "machine-learning", "deep-learning", "rag", "agent"}
    framework_signals = {"framework", "library", "sdk"}
    data_signals = {"data", "etl", "pipeline", "database", "analytics"}

    if topics & ai_signals and (topics & framework_signals or "framework" in desc):
        return "ml_framework"
    if topics & ai_signals and topics & fullstack_signals:
        return "fullstack"
    if topics & ai_signals and topics & backend_signals:
        return "backend"
    if topics & ai_signals:
        return "ai_product"
    if topics & fullstack_signals:
        return "fullstack"
    if topics & backend_signals:
        return "backend"
    if topics & data_signals:
        return "data"
    if lang in ("typescript", "javascript") and any(fw in desc for fw in ["react", "vue", "svelte", "next"]):
        return "fullstack"
    if lang in ("python", "go", "java") and any(fw in desc for fw in ["api", "server", "backend"]):
        return "backend"
    return "other"


def is_ai_repo(repo: dict) -> bool:
    """Verify AI nature via topics and description."""
    topics = set(t.lower() for t in repo.get("topics", []))
    desc = (repo.get("description") or "").lower()
    ai_signals = {"llm", "gpt", "chatgpt", "ai", "ml", "machine-learning",
                  "deep-learning", "rag", "agent", "neural", "nlp",
                  "computer-vision", "transformer", "diffusion"}
    ai_keywords = ["ai", "llm", "gpt", "machine learning", "deep learning",
                   "neural", "rag", "agent", "transformer", "diffusion"]
    if topics & ai_signals:
        return True
    if any(kw in desc for kw in ai_keywords):
        return True
    return False


def collect(
    target_count: int = 100,
    min_stars: int = 500,
    queries: list[str] = None,
) -> list[dict]:
    """Collect EU AI repos matching criteria."""
    if queries is None:
        queries = [
            "topic:llm stars:>500",
            "topic:gpt stars:>500",
            "topic:chatgpt stars:>500",
            "topic:rag stars:>500",
            "topic:ai-agent stars:>500",
            "topic:openai stars:>500",
            "topic:langchain stars:>500",
            "topic:huggingface stars:>500",
            "topic:stable-diffusion stars:>500",
            "topic:transformer stars:>500",
            "topic:mlops stars:>500",
            "topic:chatbot stars:>500",
            "topic:machine-learning stars:>500 language:python",
            "topic:deep-learning stars:>500 language:python",
            "topic:ai stars:>500 language:typescript",
            "topic:nlp stars:>500",
            "topic:vector-database stars:>500",
            "topic:embeddings stars:>500",
            "topic:ai-assistant stars:>500",
        ]

    seen_full_names = set()
    results = []

    for query in queries:
        if len(results) >= target_count:
            break
        log.info(f"\nQuery: {query}")
        for page in range(1, 4):  # up to 90 repos per query
            if len(results) >= target_count:
                break
            items = search_repos(query, per_page=30, page=page)
            if not items:
                break
            log.info(f"  Page {page}: {len(items)} repos")
            for repo in items:
                full_name = repo.get("full_name", "")
                if full_name in seen_full_names:
                    continue
                seen_full_names.add(full_name)
                stars = repo.get("stargazers_count", 0)
                if stars < min_stars:
                    continue
                owner = repo.get("owner", {}).get("login", "")
                if not owner:
                    continue
                location = fetch_owner_location(owner)
                country = normalize_country(location)
                if not country:
                    continue
                ai = is_ai_repo(repo)
                if not ai:
                    continue
                category = categorize_repo(repo)

                result = {
                    "github_id": repo.get("id"),
                    "full_name": full_name,
                    "owner_login": owner,
                    "owner_location": location,
                    "owner_country": country,
                    "name": repo.get("name"),
                    "description": repo.get("description"),
                    "primary_language": repo.get("language"),
                    "topics": repo.get("topics", []),
                    "stars": stars,
                    "forks": repo.get("forks_count", 0),
                    "size_kb": repo.get("size", 0),
                    "is_ai_product": True,
                    "app_category": category,
                    "created_at": repo.get("created_at"),
                    "pushed_at": repo.get("pushed_at"),
                    "default_branch": repo.get("default_branch"),
                    "html_url": repo.get("html_url"),
                    "clone_url": repo.get("clone_url"),
                    "verification_notes": f"EU country={country} from '{location}', AI via topics/desc",
                    "collection_method": "github_search",
                }
                results.append(result)
                log.info(
                    f"  ✓ [{len(results):3d}/{target_count}] {country} "
                    f"⭐{stars:6d} {category:12s} {full_name}"
                )
                if len(results) >= target_count:
                    break
            time.sleep(1)  # rate limit courtesy
    return results


def insert_to_postgres(repos: list[dict]) -> None:
    """Insert collected repos into PostgreSQL — one transaction per insert."""
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ.get("PG_USER", "eu_ai_compliance"),
        dbname=os.environ.get("PG_DB", "eu_ai_compliance"),
    )
    conn.autocommit = False
    cur = conn.cursor()
    inserted = 0
    failed = 0
    for repo in repos:
        # Each insert in its own transaction — failure doesn't poison the rest
        try:
            conn.rollback()  # clear any prior aborted state
            cur.execute("""
                INSERT INTO eu_ai_repos (
                    github_id, full_name, owner_login, owner_location, owner_country,
                    name, description, primary_language, languages, topics,
                    stars, forks, size_kb, is_ai_product, app_category,
                    created_at, pushed_at, default_branch, html_url, clone_url,
                    verification_notes, collection_method
                ) VALUES (
                    %(github_id)s, %(full_name)s, %(owner_login)s, %(owner_location)s, %(owner_country)s,
                    %(name)s, %(description)s, %(primary_language)s, %(languages)s, %(topics)s,
                    %(stars)s, %(forks)s, %(size_kb)s, %(is_ai_product)s, %(app_category)s,
                    %(created_at)s, %(pushed_at)s, %(default_branch)s, %(html_url)s, %(clone_url)s,
                    %(verification_notes)s, %(collection_method)s
                )
                ON CONFLICT (github_id) DO NOTHING
            """, {
                **repo,
                "languages": json.dumps(repo.get("languages") or {}),
                "topics": json.dumps(repo.get("topics") or []),
            })
            conn.commit()
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"Insert failed for {repo.get('full_name')}: {str(e)[:100]}")
    cur.close()
    conn.close()
    log.info(f"Inserted {inserted}/{len(repos)} repos into PostgreSQL ({failed} failed)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=int, default=100, help="Target number of repos")
    p.add_argument("--min-stars", type=int, default=500, help="Minimum star count")
    p.add_argument("--output", help="Save to JSON file (in addition to postgres)")
    p.add_argument("--dry-run", action="store_true", help="Don't insert to DB")
    args = p.parse_args()

    repos = collect(target_count=args.target, min_stars=args.min_stars)
    log.info(f"\n=== Collected {len(repos)} EU AI repos ===")

    # Distribution
    from collections import Counter
    by_country = Counter(r["owner_country"] for r in repos)
    by_category = Counter(r["app_category"] for r in repos)
    by_language = Counter(r["primary_language"] for r in repos)
    log.info("\nBy country:")
    for c, n in by_country.most_common(10):
        log.info(f"  {c}: {n}")
    log.info("\nBy category:")
    for c, n in by_category.most_common():
        log.info(f"  {c}: {n}")
    log.info("\nBy language:")
    for l, n in by_language.most_common(10):
        log.info(f"  {l}: {n}")

    if args.output:
        Path(args.output).write_text(json.dumps(repos, indent=2, default=str))
        log.info(f"\nSaved to {args.output}")

    if not args.dry_run:
        insert_to_postgres(repos)


if __name__ == "__main__":
    main()
