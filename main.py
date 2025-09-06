import praw
import json
import argparse
import sqlite3

parser = argparse.ArgumentParser(
    prog='Stawka (/stɔuka/, cute version of stalker)',
    description='Collections, categorizes and stalkes, posts, projects and people related to programming languages development',
    epilog="just a bit silly :3"
)
parser.add_argument("--database", action="store", default="main.db", help="database file path")
parser.add_argument("--creds", action="store", default="creds.json", help="credentials file path")
args = parser.parse_args()


db = sqlite3.connect(args.database)






def update_reddit_posts(subreddit='ProgrammingLanguages'):
    with open(args.creds, 'r') as f:
        cred = json.load(f)

    reddit = praw.Reddit(**cred)


    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reddit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reddit_id TEXT UNIQUE,
        title TEXT,
        score INTEGER,
        url TEXT,
        content TEXT,
        subreddit TEXT
    );
    """)


    s = reddit.subreddit(subreddit)
    for mode in (s.hot, s.new, s.rising):
        for post in mode(limit = 5):
            cur.execute("""
                INSERT OR IGNORE INTO reddit (reddit_id, title, score, url, content, subreddit)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (post.id, post.title, post.score, post.url, post.selftext, subreddit)
            )

    db.commit()


update_reddit_posts()
db.close()

