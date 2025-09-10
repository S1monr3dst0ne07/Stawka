

import sqlite3
from openai import OpenAI
import json
import argparse
from datetime import datetime


db = sqlite3.connect("ai.db")
cur = db.cursor()
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

parser = argparse.ArgumentParser(
        prog='AI Stawka',
        description='LLM based automatic scanning system',
        epilog='just a bit silly :3'
)
parser.add_argument("--session", action="store", default=None, help="specify session id to use as context for model")
args = parser.parse_args()



def get_ftime():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")



session_id = args.session if args.session else get_ftime()


#table to store chat messages
cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {session_id} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT,
        content TEXT,
        time TEXT
    );
""")


def insert_message(msg, role):
    cur.execute(f"""
        INSERT INTO {session_id} (role, content, time)
        VALUES (?, ?, ?);
    """, (role, msg, get_ftime())
    )
    db.commit()




def generate():
    cur.execute("""
        SELECT role, content FROM {session_id};
    """)
    
    messages = [
        { "role" : role, "content" : content }
        for role, content in cur.fetchall()
    ]

    print(messages)



insert_message("You are a function-calling AI.", "system")
insert_message("What is 7 + 11?", "user")
generate()
    











