"""ARCHIVED 2026-07-31 — extracted from ``core/generator.py``.

The OpenAI answer path: a Responses API call against ``gpt-5.4`` with ``file_search`` over two
OpenAI-hosted vector stores (the Living Guideline tools store and the papers store). Retired
when the app moved to Fuel IX only — the corpus now lives in Fuel IX vector stores and answers
come from ``core.fuelix_chat.generate_fuelix_answer``.

The rest of ``core/generator.py`` (``generate_follow_ups`` and its helpers) is still live and
runs on Fuel IX; only the code below was removed.

Not imported by anything. Requires the ``openai`` package, which is no longer in
``requirements.txt``. See ../README.md.
"""

import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# OpenAI-hosted vector stores. Their contents were migrated to Fuel IX by the (now deleted)
# api/migrate_openai_vector_stores_to_fuelix.py.
TOOLS_VECTOR_STORE_ID = "vs_690f8e0dc12c8191b4e662b7d94b7377"
PAPERS_VECTOR_STORE_ID = "vs_68e5590288048191946069efcdfe8f52"


def generate_answer(query, tools=False, papers=False):
    vector_store_ids = []
    if tools:
        vector_store_ids.append(TOOLS_VECTOR_STORE_ID)
    if papers:
        vector_store_ids.append(PAPERS_VECTOR_STORE_ID)
    if len(vector_store_ids) == 0:
        response = client.responses.create(
            model="gpt-5.4",
            input=query,
            reasoning={"effort": "low"},
            text={
                "verbosity": "medium",
            },
        )
    else:
        response = client.responses.create(
            model="gpt-5.4",
            input=query,
            reasoning={"effort": "low"},
            text={
                "verbosity": "medium",
            },
            tools=[{
                "type": "file_search",
                "vector_store_ids": vector_store_ids,
            }],
        )

    return response.output_text


# ``build_generator_prompt`` was removed from core/prompts.py alongside this module — it was the
# OpenAI-only entry point into ``_build_generator_prompt``, which is still live and still used by
# ``build_fuelix_assistant_instructions``. Restoring it means re-adding:
#
#     def build_generator_prompt(query, user_type, lang=None):
#         return _build_generator_prompt(
#             f"A {user_type} asked you the following question: {query}",
#             user_type,
#             lang,
#         )


if __name__ == "__main__":
    query = (
        "If an adolescent presents with suspected concussion but is also under the influence "
        "of alcohol or cannabis does this chance my examination?"
    )
    print(generate_answer(query))
