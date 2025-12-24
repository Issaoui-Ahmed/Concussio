from dotenv import load_dotenv
import os
from openai import OpenAI
from .prompts import build_generator_prompt



load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
    
def generate_answer(query, tools = False, papers = False):
    vector_store_ids = []
    if tools:
        vector_store_ids.append("vs_690f8e0dc12c8191b4e662b7d94b7377")
    if papers:
        vector_store_ids.append("vs_68e5590288048191946069efcdfe8f52")
    if len(vector_store_ids) == 0:
            response = client.responses.create(
            model="gpt-5.2",
            input=query,
            reasoning={"effort": "low"},
            text={
            "verbosity": "medium",  
        })
    else:
        response = client.responses.create(
            model="gpt-5.2",
            input=query,
            reasoning={"effort": "low"},
            text={
            "verbosity": "medium",  
        },
            tools=[{
            "type": "file_search",
            "vector_store_ids": vector_store_ids
        }])
    
    return response.output_text



if __name__ == "__main__":
    query = "If an adolescent presents with suspected concussion but is also under the influence of alcohol or cannabis does this chance my examination?"
    rec_markdown = """jj"""
    print(generate_answer(query))

