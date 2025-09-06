import praw
import json
import argparse
import sqlite3
import urlextract
import urllib.parse

parser = argparse.ArgumentParser(
    prog='Stawka (/stɔuka/, cute version of stalker)',
    description='Collections, categorizes and stalkes, posts, projects and people related to programming languages development',
    epilog="just a bit silly :3"
)
parser.add_argument("--database", action="store", default="main.db", help="database file path")
parser.add_argument("--creds", action="store", default="creds.json", help="credentials file path")
args = parser.parse_args()


db = sqlite3.connect(args.database)






def update_reddit(subreddit='ProgrammingLanguages'):
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
        for post in mode(limit = 10000):
            cur.execute("""
                INSERT OR IGNORE INTO reddit (reddit_id, title, score, url, content, subreddit)
                VALUES (?, ?, ?, ?, ?, ?);
                """, (post.id, post.title, post.score, post.url, post.selftext, subreddit)
            )

    db.commit()


def filter_links_from_reddit():
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        post_id INTEGER,
        FOREIGN KEY (post_id)
        REFERENCES reddit (id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    )
    """)

    extor = urlextract.URLExtract()

    cur.execute("SELECT id, content FROM reddit")
    for (id, content) in cur.fetchall():
        links = extor.find_urls(content)
        stream = zip(iter(lambda: id, 1), links)
        cur.executemany("""
            INSERT OR IGNORE INTO links (post_id, url)
            VALUES (?, ?)""", stream
        )

    db.commit()

        
def filter_github_from_links():
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS github (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT,
        resolvable BOOLEAN,
        owner_name TEXT,
        repo_name TEXT,
        repo_id TEXT , 
        post_id INTEGER,
        readme TEXT,
        star_count INTEGER,
        issue_count INTEGER,
        pr_count INTEGER,
        commit_count INTEGER,

        FOREIGN KEY (post_id)
        REFERENCES reddit (id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    )
    """)

    cur.execute("SELECT url, post_id FROM links")
    for (url, post_id) in cur.fetchall():
        url_comps = urllib.parse.urlparse(url)  

        if url_comps.netloc != 'github.com':
            continue

        cur.execute("""
            INSERT OR IGNORE INTO github (post_id, url, resolvable)
            VALUES (?, ?, FALSE)""", (post_id, url)
        )
        row_id = cur.lastrowid

        path_comps = url_comps.path.strip('/').split('/')
        if len(path_comps) < 2: continue

        owner, repo, *_ = path_comps
        repo_id = f"{owner}/{repo}"
        cur.execute("""
            UPDATE github
            SET owner_name = ?, repo_name = ?, repo_id = ?, resolvable = TRUE
            WHERE id = ?""", (owner, repo, repo_id, row_id)
        )

    db.commit()



filter_github_from_links()
db.close()

