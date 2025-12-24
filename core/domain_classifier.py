from dotenv import load_dotenv
import os
from pydantic import BaseModel
from openai import OpenAI
from .prompts import build_domain_classifier_prompt

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def classify_domain(user_query, domain_prompt):
    

    class Domain(BaseModel):
        domain_number: int

    response = client.responses.parse(
        model="gpt-5-mini",
        input= build_domain_classifier_prompt(user_query, domain_prompt),
        text_format=Domain,
    )
    
    return response.output_parsed.domain_number

    
