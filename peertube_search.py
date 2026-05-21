#!/usr/bin/env python3
"""
PeerTube Universal Search
Searches ALL known PeerTube instances in parallel, not just SepiaSearch-indexed ones.
Usage: python peertube_search.py "your search query" [--max-instances N] [--timeout N]
"""

import asyncio
import aiohttp
import argparse
import json
import sys
from datetime import datetime

INSTANCES_API = "https://instances.joinpeertube.org/api/v1/instances?count=1000&start=0"

async def fetch_instances(session):
    """Fetch all known PeerTube instances."""
    print("Fetching instance list from instances.joinpeertube.org ...", flush=True)
    try:
        async with session.get(INSTANCES_API, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
            instances = [i["host"] for i in data.get("data", [])]
            print(f"Found {len(instances)} instances.\n", flush=True)
            return instances
    except Exception as e:
        print(f"Failed to fetch instance list: {e}", file=sys.stderr)
        return []

async def search_instance(session, host, query, timeout):
    """Search a single PeerTube instance."""
    url = f"https://{host}/api/v1/search/videos"
    params = {"search": query, "count": 10, "sort": "-match"}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                data = await resp.json()
                videos = data.get("data", [])
                if videos:
                    return host, videos
    except Exception:
        pass
    return host, []

def format_video(video, host):
    name = video.get("name", "Untitled")
    uuid = video.get("uuid", "")
    duration = video.get("duration", 0)
    mins, secs = divmod(duration, 60)
    channel = video.get("channel", {}).get("displayName", "Unknown")
    published = video.get("publishedAt", "")[:10] if video.get("publishedAt") else ""
    views = video.get("views", 0)
    url = f"https://{host}/videos/watch/{uuid}"
    return (
        f"  Title   : {name}\n"
        f"  Channel : {channel}  |  Duration: {mins}m{secs:02d}s"
        f"  |  Views: {views}  |  Date: {published}\n"
        f"  URL     : {url}\n"
    )

async def main():
    parser = argparse.ArgumentParser(description="Search all PeerTube instances")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--max-instances", type=int, default=500,
                        help="Max instances to query (default: 500)")
    parser.add_argument("--timeout", type=int, default=8,
                        help="Per-instance timeout in seconds (default: 8)")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted text")
    args = parser.parse_args()

    connector = aiohttp.TCPConnector(limit=100, ssl=False)
    headers = {"User-Agent": "PeerTubeUniversalSearch/1.0"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        instances = await fetch_instances(session)
        if not instances:
            print("No instances found. Exiting.")
            return

        instances = instances[:args.max_instances]
        print(f"Searching {len(instances)} instances for: \"{args.query}\"")
        print("(This may take a few seconds...)\n", flush=True)

        tasks = [search_instance(session, host, args.query, args.timeout) for host in instances]

        results = []
        done = 0
        for coro in asyncio.as_completed(tasks):
            host, videos = await coro
            done += 1
            if videos:
                results.append((host, videos))
                print(f"[{done}/{len(instances)}] ✓ {host} — {len(videos)} result(s)", flush=True)

        print(f"\n{'='*60}")
        print(f"Search complete. {len(results)} instance(s) returned results.")
        print(f"{'='*60}\n")

        if args.json:
            all_videos = []
            for host, videos in results:
                for v in videos:
                    v["_instance"] = host
                    all_videos.append(v)
            print(json.dumps(all_videos, indent=2))
        else:
            total = 0
            for host, videos in sorted(results, key=lambda x: -len(x[1])):
                print(f"── {host} ({len(videos)} result(s)) ──")
                for v in videos:
                    print(format_video(v, host))
                    total += 1
            print(f"Total videos found: {total}")

if __name__ == "__main__":
    asyncio.run(main())
