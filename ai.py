

import sqlite3
import ollama
import json
import jsonfinder
import argparse
from datetime import datetime
import sys


ai_db = sqlite3.connect("ai.db")
ai_cur = ai_db.cursor()

user_db = sqlite3.connect("user.db")
user_cur = user_db.cursor()


parser = argparse.ArgumentParser(
        prog='AI Stawka',
        description='LLM based automatic scanning system',
        epilog='just a bit silly :3'
)
parser.add_argument("--session", action="store", default=None, help="specify session id to use as context for model")
parser.add_argument("--drop", action="store_true", help="drop chat session tables")
parser.add_argument("--user", action="store", required=True, help="subject")
args = parser.parse_args()




if args.drop:
    ai_cur.execute("SELECT name from sqlite_master where type = 'table';")
    for (name,) in ai_cur.fetchall():
        if name.startswith("session_"):
            print(f"dropping: {name}")
            ai_cur.execute(f"DROP TABLE '{name}'")


def get_ftime():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")



session_id_raw = args.session if args.session else f"session_{get_ftime()}"
session_id = f"'{session_id_raw}'"


#table to store chat messages
ai_cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {session_id} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT,
        content TEXT,
        time TEXT,
        tool_name TEXT
    );
""")


def insert_message(msg, role, tool_name=None):
    ai_cur.execute(f"""
        INSERT INTO {session_id} (role, content, time, tool_name)
        VALUES (?, ?, ?, ?);
    """, (role, msg, get_ftime(), tool_name)
    )
    ai_db.commit()

def insert_system_message(msg):
    insert_message(msg, "system")




def get_post_titles_prompt():
    user_cur.execute(f"SELECT title FROM '{args.user}';")

    posts = "".join(
        f"- '{title}' \n"
        for (title,) in 
        user_cur.fetchall()
    )
    return f"Information, Post list: \n{posts}"


running = True
class tools:
    def tool_get_post_content(post_title: str) -> str:
        user_cur.execute(
            f"SELECT content FROM '{args.user}' where title = '{post_title}';")

        (content,) = user_cur.fetchone()
        insert_system_message(
            f"Information, Post content of '{post_title}': \n '{content}'")



    def tool_finish(answer: str, rationale: str):
        global running
        print(answer)
        print(answer)

        running = False

    def tool_think(thought: str):
        insert_system_message(f"Information, Thought: {thought}")


    @staticmethod
    def call(tool_name, tool_args):
        print(f"tool call: {tool_name}({tool_args})")
        try:
            tools.get_tool_map()[tool_name](**tool_args)
        except Exception as E:
            print(E)
        
       
    @staticmethod
    def get_tool_map():
        return { 
            key: getattr(tools, key) 
            for key in dir(tools) 
            if key.startswith('tool_') 
        }

    @staticmethod
    def get_tool_list():
        return list(tools.get_tool_map().values())


post_titles_prompt = get_post_titles_prompt()
system_prompt = f"""
    You will answer the user prompt using the provided information.
    You will prioritize previously provided information over requesting new information.
    If the provided information doesn't answer the question, you will call `tool_get_post_content` to fetch an additional post.
    Once you have found the answer, you will call `tool_finish` with it.
    You will consider ALL of the information, before coming to a conclusion.
    You will NOT explain, you will merely call a tool.
"""
user_prompt = "Is the poster queer?"


def generate():
    ai_cur.execute(f"""
        SELECT role, content, tool_name FROM {session_id};
    """)
    
    messages = [
        { "role" : role, "content" : content} 
        # | ({"tool_name": tool_name } if tool_name is not None else {})
        for role, content, tool_name in ai_cur.fetchall()
    ] + [
        { "role" : "system", "content" : post_titles_prompt },
        { "role" : "system", "content" : system_prompt      },
        { "role" : "user",   "content" : user_prompt        },
    ]

    print(messages)

    response = ollama.chat(
        model="mistral:7b-instruct",
        messages=messages,
        tools=tools.get_tool_list(),
        options={
            "temperature": 0.5,
            "num_predict": 200,      # instead of max_tokens
            "top_p": 0.95,
            "top_k": 20,
            "frequency_penalty": 1.1,
            "presence_penalty": 0.5,
            "num_ctx": 4096,
        }
    )

    return response




while running:
    print("\n\n")
    resp = generate()
    print(resp)

    #parsed tool calls
    if resp.message.tool_calls:
        for call in resp.message.tool_calls:
            tools.call(
                tool_name = call.function.name,
                tool_args = call.function.arguments,
            )

    #unparsed tool calls
    matches = jsonfinder.jsonfinder(resp.message.content)
    for (_, _, match) in matches:
        if match is None:
            continue 
        print(f"matches: {match}")
        for call in match:
            if 'name' in call and 'arguments' in call:
                tools.call(
                    tool_name = call['name'],
                    tool_args = call['arguments']
                )







    
ai_db.close()











