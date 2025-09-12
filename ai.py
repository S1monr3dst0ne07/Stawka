

import sqlite3
import ollama
import json
import argparse
from datetime import datetime


db = sqlite3.connect("ai.db")
cur = db.cursor()

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
        time TEXT,
        tool_name TEXT
    );
""")


def insert_message(msg, role, tool_name=None):
    cur.execute(f"""
        INSERT INTO {session_id} (role, content, time, tool_name)
        VALUES (?, ?, ?, ?);
    """, (role, msg, get_ftime(), tool_name)
    )
    db.commit()



running = True
class tools:
    def tool_add_two_numbers(a: int, b: int) -> int:
        return a + b


    def tool_finish(answer: str):
        global running
        print(answer)

        running = False

tool_map = { key: getattr(tools, key) for key in dir(tools) if key.startswith('tool_') }




def generate():
    cur.execute(f"""
        SELECT role, content, tool_name FROM {session_id};
    """)
    
    messages = [
        { "role" : role, "content" : content} | 
        ({"tool_name": tool_name } if tool_name is not None else {})
        for role, content, tool_name in cur.fetchall()
    ]

    print(messages)

    response = ollama.chat(
        model="mistral:instruct",
        messages=messages,
        tools=list(tool_map.values()),
        options={
            "temperature": 0,
            "num_predict": 200,      # instead of max_tokens
            "top_k": 40,
            "top_p": 0.8,
            "frequency_penalty": 1.1,
            "presence_penalty": 0.5,
            "num_ctx": 4096,
        }
    )

    return response


def insert_system_message(msg):
    insert_message(msg, "system")

def insert_system_json(obj):
    insert_system_message(json.dumps(obj))


insert_system_message("""
    You will answer the user prompt with the use of the provided tool.
""")
insert_message("What is 1 + 2 + 3?", "user")




while running:
    resp = generate()
    print(resp)

    if resp.message.tool_calls:
        for tool in resp.message.tool_calls:
            tool_name = tool.function.name 
            try:
                result = tool_map[tool_name](**tool.function.arguments) 
                print(result)
                insert_message(str(result), 'tool', tool_name=tool_name)
            except Exception as E:
                print(E)
                pass



    
db.close()











