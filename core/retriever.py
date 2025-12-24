import os
import requests
from dotenv import load_dotenv
from .domain_classifier import classify_domain

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def retrieve(user_query):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    # Step 1: Get all domain names
    r = requests.get(f"{SUPABASE_URL}/rest/v1/Domains?select=id,name,intro", headers=headers)
    rows = r.json()

    markdown_output = ""
    for row in rows:
        markdown_output += f"## {row['name']} (Number: {row['id']})\n{row['intro']}\n\n"

    result = classify_domain(user_query, markdown_output)
    if result == -1:
        return -1

    # Step 2: Retrieve the selected record
    r2 = requests.get(f"{SUPABASE_URL}/rest/v1/Domains?id=eq.{result}&select=rec_markdown", headers=headers)
    rec = r2.json()
    return rec[0]['rec_markdown']

def retrieve_all(user_query):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

    # # Step 1: Get all domain names for classification step
    # r = requests.get(f"{SUPABASE_URL}/rest/v1/Domains?select=id,name,intro", headers=headers)
    # rows = r.json()

    # markdown_output = ""
    # for row in rows:
    #     markdown_output += f"## {row['name']} (Number: {row['id']})\n{row['intro']}\n\n"

    # # Classification step
    # result = classify_domain(user_query, markdown_output)
    # if result == -1:
    #     return -1

    # Step 2: Retrieve all name + rec_markdown fields
    r2 = requests.get(f"{SUPABASE_URL}/rest/v1/Domains?select=name,rec_markdown", headers=headers)
    rows2 = r2.json()

    # Build combined output
    combined_output = ""
    for row in rows2:
        if row.get("rec_markdown"):
            combined_output += f"## {row['name']}\n{row['rec_markdown']}\n\n---\n\n"

    # Remove last trailing separator if needed
    combined_output = combined_output.rstrip("\n- ")

    return combined_output




if __name__ == "__main__":
    query = "hi"
    rec = retrieve_all(query)
    with open("all_rec_markdown.md", "w", encoding="utf-8", newline="") as file:
        file.write(rec)

