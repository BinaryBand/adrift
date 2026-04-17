import time
import io
import sys
import sqlite3
import os
from contextlib import redirect_stdout
from src.catalog import process_feeds, process_sources, align_episodes, merge_config
from src.app_common import load_config

def run():
    # Based on grep, load_config(name_or_path: str) -> list[PodcastConfig]
    configs = load_config("config/youtube.toml")
    # Finding 'Paul J Warburg' by matching slug or name? 
    # Let's try matching both to be sure.
    config = next((c for c in configs if c.name == 'Paul J Warburg' or getattr(c, 'slug', '') == 'paul-j-warburg'), None)
    if not config:
        print(f"Config for Paul J Warburg not found. Available names: {[c.name for c in configs]}")
        return

    # Step 2: Time separate calls
    f = io.StringIO()
    with redirect_stdout(f):
        start = time.perf_counter()
        feeds = process_feeds(config, refresh_sources=False)
        t_feeds = time.perf_counter() - start

        start = time.perf_counter()
        sources = process_sources(config, refresh_sources=False)
        t_sources = time.perf_counter() - start

        start = time.perf_counter()
        align_episodes(feeds, sources, config.name)
        t_align = time.perf_counter() - start
    
    print(f"process_feeds: {t_feeds:.4f}s")
    # print(f"  Feeds: {len(feeds)}")
    print(f"process_sources: {t_sources:.4f}s")
    # print(f"  Sources: {len(sources)}")
    print(f"align_episodes: {t_align:.4f}s")

    # Step 3 & 4: merge_config twice
    for i in range(2):
        f = io.StringIO()
        with redirect_stdout(f):
            start = time.perf_counter()
            merge_config(config, refresh_sources=False)
            t_merge = time.perf_counter() - start
        print(f"merge_config {i+1}: {t_merge:.4f}s")
        output = f.getvalue()
        # Filter output for relevant lines
        lines = [l for l in output.split('\n') if 'Using fresh cached YouTube episodes' in l or 'Fetching video info' in l]
        if lines:
            print(f"  Log patterns: {lines[:5]} ... (total {len(lines)} lines)")
        else:
            print("  No matching log patterns.")

    # Step 5: SQLite queries
    db_path = ".cache/yt-dlp/cache.sqlite3"
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        cur.execute("SELECT count(*) FROM cache WHERE key LIKE 'get_youtube_videos:%'")
        yt_videos_count = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM cache WHERE key LIKE 'get_video_info:%'")
        video_info_count = cur.fetchone()[0]
        
        # Check for Warburg specific keys (approximate)
        cur.execute("SELECT count(*) FROM cache WHERE key LIKE '%PaulJWarburg%'")
        warburg_count = cur.fetchone()[0]
        
        print(f"SQLite - get_youtube_videos count: {yt_videos_count}")
        print(f"SQLite - get_video_info count: {video_info_count}")
        print(f"SQLite - keys containing 'PaulJWarburg': {warburg_count}")
        conn.close()
    else:
        print(f"SQLite DB not found at {db_path}")

if __name__ == "__main__":
    run()
