

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
parser.add_argument("--drop", action="store_true", help="drop chat session tables")
args = parser.parse_args()


if args.drop:
    cur.execute("SELECT name from sqlite_master where type = 'table';")
    for (name,) in cur.fetchall():
        if name.startswith("session_"):
            print(f"dropping: {name}")
            cur.execute(f"DROP TABLE '{name}'")


def get_ftime():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")



session_id = args.session if args.session else f"'session_{get_ftime()}'"


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
    cur.execute(f"""
        SELECT role, content FROM {session_id};
    """)
    
    messages = [
        { "role" : role, "content" : content }
        for role, content in cur.fetchall()
    ]

    result = client.chat.completions.create(
        model="mistral",
        messages = messages,
        temperature=0.7,       
        max_tokens=512,        
        top_p=0.8,             
        frequency_penalty=1.1, 
        presence_penalty=0.5
    )

    response = result.choices[0].message.content
    insert_message(response, "assistant")

    return response


def insert_schema():
    insert_message("""
    You are a function-calling AI.
    You will always respond with a function call in JSON format.
    You will ALWAYS respond in JSON.

    Function call format: (what you'll be responding with)
    {
        "function": "<name>",
        "arguments": { ... }
    }


    Available Functions:
    - add(a: int, b: int)
        Takes two integers, computes their sum.
    - done(answer: string)
        To be called when answer to user prompt has been found.


    """, "system")

def insert_system_message(msg):
    insert_message(msg, "system")


insert_message("What is 1 + 2 + 3?", "user")

running = True
def done(answer):
    global running
    print(answer)

    running = False

funcs = {
    "add": lambda a, b: a + b,
    "done": done,
}

while running:
    resp_txt = generate()
    print(resp_txt)

    try:
        resp = json.loads(resp_txt)
        print(reps)

        fn = resp["function"]
        args = resp["arguments"]

    except:
        insert_system_message("Error: You have responsed with a malformed response, please adhere to the provided schema.")
        insert_schema()
        continue


    if fn not in funcs:
        insert_system_message("Error: You have responsed with a call to '{fn}', which is a function that does NOT exist.")
        continue

    try:
        funcs[fn](**args)
    except:
        insert_system_message("Error: You have responsed with a call to '{fn}' while not providing the correct parameters for such a call.")



    
db.close()











