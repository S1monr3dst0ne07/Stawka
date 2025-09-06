import praw
import json
import argparse

parser = argparse.ArgumentParser(
    prog='Stawka (/stɔuka/, cute version of stalker)',
    description='Collections, categorizes and stalkes, posts, projects and people related to programming languages development',
    epilig="just a bit silly :3"
)
parser.add_argument("--database", action="store", default="main.db", help="database file path")
parser.add_argument("--creds", action="store", default="creds.json", help="credentials file path")
args = parser.parse_args()




with open(args.creds, 'r') as f:
    cred = json.load(f)

reddit = praw.Reddit(**cred)

data = {}


# Example: Get the 5 hottest posts from a subreddit
s = reddit.subreddit("ProgrammingLanguages")
for mode in (s.hot, s.new, s.rising):
    for post in mode(limit = 1000):
        if post.id in data:
            continue

        data[post.id] = {
            "title" : post.title,
            "score" : post.score,
            "url"   : post.url,
            "text"  : post.selftext,
        }


with open('data/posts.json', 'w') as f:
    json.dump(data, f, indent=2)


