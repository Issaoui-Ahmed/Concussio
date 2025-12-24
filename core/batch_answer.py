import pandas as pd
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__))) # Add core to path if run directly, or rely on root execution
# Actually if run as script from root `python core/batch_answer.py` path setup is tricky.
# Better to assume module usage or setup path to root.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.chatbot import ChatSession
# Replaced run_chatbot with ChatSession assuming logic update needed or just import fix.
# User asked to organize, not fix broken legacy scripts, but I shouldn't leave syntax errors.
# I'll comment out the broken function call or replace it if trivial.
# The script calls run_chatbot(question). Check if I can mock it.
def run_chatbot(q):
    return ChatSession().reply(q)

# Load the spreadsheet
input_file = "Concussion_Guidance_QA.xlsx"

df = pd.read_excel(input_file)

# Iterate over rows and fill empty answers
for index, row in df.iterrows():
    if pd.isna(row["Answer"]) or str(row["Answer"]).strip() == "":
        question = row["Question"]
        print(f"\n🧠 Processing question: {question}")
        try:
            answer = run_chatbot(question)
            df.at[index, "Answer"] = answer
        except Exception as e:
            print(f"⚠️ Error for question '{question}': {e}")
            df.at[index, "Answer"] = "Error generating answer"

# Save the updated Excel file
df.to_excel(input_file, index=False)
print(f"\n✅ Updated file saved as {input_file}")
