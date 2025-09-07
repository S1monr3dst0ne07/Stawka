import praw
import json
import argparse
import sqlite3
import urlextract
import urllib.parse
import requests
import subprocess
import tempfile
import os
import time
import shutil

parser = argparse.ArgumentParser(
    prog='Stawka (/stɔuka/, cute version of stalker)',
    description='Collections, categorizes and stalkes, posts, projects and people related to programming languages development',
    epilog="just a bit silly :3"
)
parser.add_argument("--database", action="store", default="main.db", help="database file path")
parser.add_argument("--github-token", dest = "github_token", action="store", default="creds/github.txt", help = "github access token file path")
parser.add_argument("--reddit-creds", dest = "reddit_creds", action="store", default="creds/reddit.json", help = "reddit credential file path")
parser.add_argument("--fox-path", dest = "foxpath", action="store", default=r"C:\Program Files\Mozilla Firefox\firefox.exe", help = "firefox executable path")
parser.add_argument("--fox-file", dest = "foxfile", action="store", default="fox_file", help = "firefox profile (instance will use copy)")
args = parser.parse_args()


db = sqlite3.connect(args.database)






def fetch_reddit(subreddit='ProgrammingLanguages'):
    with open(args.reddit_creds, 'r') as f:
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
    for (id, content_raw) in cur.fetchall():
        #unescape
        content = content_raw.replace("\\_", "_").replace("\\~", "~")

        links = [
            urllib.parse.unquote(l).strip('.')
            for l in extor.find_urls(content)]
        if len(links) == 0:
            continue

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
        owner_name TEXT UNIQUE,
        repo_name TEXT  UNIQUE,
        repo_id TEXT , 
        post_id INTEGER,
        readme TEXT,
        star_count INTEGER,
        issue_count INTEGER,
        pr_count INTEGER,
        commit_count INTEGER,
        processed BOOLEAN,

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

        path_comps = url_comps.path.strip('/').split('/')
        if len(path_comps) < 2: 
            continue

        owner, repo, *_ = path_comps
        repo_id = f"{owner}/{repo}"

        cur.execute("""
            INSERT OR IGNORE INTO github (
                post_id, url, processed, 
                owner_name, repo_name, repo_id)
            VALUES (?, ?, FALSE, ?, ?, ?)""", 
            (post_id, url, owner, repo, repo_id)
        )

    db.commit()


def fetch_github_stats():
    print("Fetching github stats...")
    cur = db.cursor()

    with open(args.github_token, 'r') as f:
        gh_token = f.read()

    headers = {"Authorization": f"Bearer {gh_token}"}
    query = '''
    {
      repository(owner: "%(owner)s", name: "%(name)s") {
        stargazerCount
        forkCount
        issues { totalCount }
        pullRequests { totalCount }
        defaultBranchRef {
          target {
            ... on Commit {
              history { totalCount }
            }
          }
        }
      }
    }
    '''

    cur.execute("SELECT id, owner_name, repo_name FROM github WHERE processed = FALSE")
    for (row_id, owner, name) in cur.fetchall():
        response = requests.post(
            "https://api.github.com/graphql", 
            json={"query": query % {"owner": owner, "name": name}},
            headers=headers
        )

        print(response.status_code)
        print(response.json()) 
        print(owner, name)


        repo_data = response.json()["data"]["repository"]
        if repo_data is None:
            #TODO: handle errors
            continue


        star_count   = repo_data["stargazerCount"]
        issue_count  = repo_data["issues"]["totalCount"]
        pr_count     = repo_data["pullRequests"]["totalCount"]
        commit_count = repo_data["defaultBranchRef"]["target"]["history"]["totalCount"]


        response = requests.get(
            f"https://api.github.com/repos/{owner}/{name}/readme",
            headers = {**headers, "Accept": "application/vnd.github.v3.raw"},
        )

        readme       = response.text

        cur.execute(f"""
            UPDATE github
            SET readme = ?, star_count = ?, issue_count = ?, pr_count = ?, commit_count = ?, processed = TRUE
            WHERE id = {row_id}""", (readme, star_count, issue_count, pr_count, commit_count)
        )

        db.commit()




def user_interact():
    

    profile = tempfile.mkdtemp()
    shutil.copytree(os.path.abspath(args.foxfile), profile, dirs_exist_ok=True)
    subprocess.Popen([args.foxpath, "-no-remote", "-profile", profile])

    #wait for exit
    input("any key to continue")

    # Read browsing history from places.sqlite
    db_path = os.path.join(profile, "places.sqlite")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM moz_places")
        for row in cursor.fetchall():
            print(row)
        conn.close()



#filter_links_from_reddit()
#filter_github_from_links()
#fetch_github_stats()
user_interact()



db.close()

