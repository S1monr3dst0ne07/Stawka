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
    print("fetch reddit... ")
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
        subreddit TEXT,
        self BOOLEAN
    );
    """)


    s = reddit.subreddit(subreddit)
    for mode in (s.hot, s.new, s.rising):
        print(f"mode: {mode}")
        for post in mode(limit = 10000):
            print(post.title)
            cur.execute("""
                INSERT OR IGNORE INTO reddit (reddit_id, title, score, url, content, subreddit, self)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (post.id, post.title, post.score, post.url, post.selftext, subreddit, post.is_self)
            )

    db.commit()
    print("done")


def filter_links_from_reddit():
    print("filter links from reddit... ")
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

    #process self post
    cur.execute("SELECT id, content FROM reddit WHERE self = TRUE")
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

    #process link post
    cur.execute("SELECT id, url FROM reddit WHERE self = FALSE")
    for (id, url) in cur.fetchall():
        cur.execute("""
            INSERT OR IGNORE INTO links (post_id, url)
            VALUES (?, ?)""", (id, url)
        )


    db.commit()
    print("done")

        
def filter_github_from_links():
    print("filter github from links... ")
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
    print("done")


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
        print(f"{owner}/{name}")
        response = requests.post(
            "https://api.github.com/graphql", 
            json={"query": query % {"owner": owner, "name": name}},
            headers=headers
        )

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
    print("done")




def filter_review_from_github():
    print("filter review from github... ")
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS review (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        github_id INTEGER UNIQUE,
        eligible BOOLEAN,
        status TEXT,
        desc TEXT,
        sites TEXT,


        FOREIGN KEY (github_id)
        REFERENCES github (id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    )
    """)

    cur.execute("SELECT id, star_count, issue_count, pr_count FROM github WHERE processed = TRUE")
    for (github_id, star_count, issue_count, pr_count) in cur.fetchall():
        eligible = star_count < 30 and issue_count < 20 and pr_count < 20

        cur.execute("""
            INSERT OR IGNORE INTO review (github_id, eligible, status)
            VALUES (?, ?, 'un')""", (github_id, eligible)
        )

    db.commit()
    print("done")




def interact(urls):
    profile = tempfile.mkdtemp()
    shutil.copytree(os.path.abspath(args.foxfile), profile, dirs_exist_ok=True)
    subprocess.Popen([
        args.foxpath, "-no-remote", "-profile", profile, 
        *urls
    ])

    #wait for exit
    input("any key when done browsing")

    # Read browsing history from places.sqlite
    db_path = os.path.join(profile, "places.sqlite")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM moz_places")
        history_urls = [x[0] for x in cursor.fetchall()]
        conn.close()

    print(f"urls in history: {history_urls}")
    return history_urls



def show_review(condition):
        cur = db.cursor()
        cur.execute(f"SELECT github.url, github.star_count, github.pr_count, github.commit_count, reddit.title, reddit.score, reddit.url, review.status, review.desc, review.sites FROM review INNER JOIN github ON github.id = review.github_id INNER JOIN reddit ON reddit.id = github.post_id WHERE {condition}")
        github_url, star_count, pr_count, commit_count, reddit_title, reddit_score, reddit_url, status, desc, sites = cur.fetchone() 

        print("--- full into ---")
        print(f"review status: {status}")
        print(f"review desc  : {desc}")
        print(f"review sites : {sites}")
        print(f"github url   : {github_url}")
        print(f"star   count : {star_count}")
        print(f"pr     count : {pr_count}")
        print(f"commit count : {commit_count}")
        print(f"reddit title : {reddit_title}")
        print(f"reddit score : {reddit_score}")
        print(f"reddit url   : {reddit_url}")




class commit:
    active = False
    github_url = ""


print("=== Stawka (/stɔuka/, cute stalker) ===")
while True:
    prompt = f"{commit.github_url} >>> " if commit.active else ">>> "
    comps = input(prompt).split(' ', 1)
    if not comps: continue

    head = comps[0]
    arg = comps[1] if len(comps) > 1 else None


    if head == "help":
        print("""
help            - help
exit            - exit
update          - run fetch and filter
filter          - run filter only
rev un          - review unreviewed 
rev maybe       - review with maybe status
list            - list review commits
show repo_id    - show commit with repo_id
commit          - commit current
desc x          - set description
status x        - set status
              """)

    elif head == "exit":
        break

    elif head == "update":
        word = input("warning: you're about to send packets, continue? [yes]")

        if word == "yes":
            fetch_reddit()
            filter_links_from_reddit()
            filter_github_from_links()
            fetch_github_stats()
            filter_review_from_github()

    elif head == "filter":
        filter_links_from_reddit()
        filter_github_from_links()
        filter_review_from_github()

    elif head == "list":
        status_select = "review.status"
        if arg in ('un', 'maybe', 'good', 'bad'):
            status_select = f" '{arg}'"


        cur = db.cursor()
        cur.execute(f"SELECT review.status, github.repo_id FROM review INNER JOIN github ON github.id = review.github_id WHERE review.eligible = TRUE AND review.status = {status_select}")
        for (status, id) in cur.fetchall():
            print(f"{status}: {id}")

    elif head == "rev":
        status = 'un'
        if arg in ('un', 'maybe'):
            status = arg


        cur = db.cursor()
        cur.execute(f"SELECT review.id, github.url, reddit.url FROM review INNER JOIN github on github.id = review.github_id INNER JOIN reddit ON reddit.id = github.post_id WHERE review.eligible = TRUE AND review.status = '{status}'")
        res = cur.fetchone()
        if res is None:
            print(f"no pending {status} revs")
            continue



        commit.active = True
        commit.review_id, commit.github_url, commit.reddit_url = res

        show_review(f"review.id = '{commit.review_id}'")
        print("\n")

        urls = (commit.reddit_url, commit.github_url)
        commit.sites = interact(urls)
        commit.status = None
        commit.desc = ""


    elif head == "status":
        if arg in ("maybe", "good", "bad", "un"):
            if commit.active:
                commit.status = arg
            else:
                print("no active commit")
        else:
            print(f"no such status {arg}")

    elif head == "desc":
        if commit.active:
            commit.desc = arg
        else:
            print("no active commit")

    elif head == "commit":
        if not commit.active:
            print("no active commit")
            continue

        print("--- commit info ---")
        print(f"github url: {commit.github_url}")
        print(f"opened urls: {commit.sites}")
        print(f"status: {commit.status}")
        print(f"desc: '{commit.desc}'")

        if status is None:
            print("cannot commit without status")
            continue 

        if input("finalize? [yes]") == "yes":
            cur = db.cursor()
            cur.execute(f"""
                UPDATE review
                SET status = ?, desc = ?, sites = ?
                WHERE id = {commit.review_id}""", 
                (commit.status, commit.desc, str(commit.sites))
            )
            commit.active = False
            db.commit()

    elif head == "show":
        if not arg:
            print("repo id not provided")
            continue

        show_review(f"github.repo_id = '{arg}'")









db.close()

