
def build_domain_classifier_prompt(query, domain_prompt):
    return f""" User query: {query}
        selects exactly one domain from the list below that best matches the user's query. 
        output a json with the domain number.\n\n"
        "if the user's query does not match any of the domains, return -1 "
        "Domains:\n"
        "{domain_prompt}\n\n"
        """    

def build_generator_prompt(query, user_type):
    with open("all_rec_markdown.md", "r", encoding="utf-8") as f:
        recommendations_markdown = f.read()
    
    personalization = ""
    
    if user_type == "patient":
        personalization = """
        The patient doesn`t have any medical knowledge. so the answer should be patient centered, simple and easy to understand.
        """
    elif user_type == "Healthcare Professional" or user_type == "doctor":
        personalization = """
        Target Audience: Healthcare professionals
        Language Style: Professional and clinical
        Sentence Structure: Short, precise sentences
        Content Focus: Evidence based recommendations, clinical steps, linked tools
        What to Avoid: Oversimplified language
        """
    elif user_type == "Parent or Caregiver":
        personalization = """
        Target Audience: Parents and caregivers
        Language Style: Clear, calm, and supportive. Reassuring.
        Sentence Structure: Short, plain sentences
        Content Focus: What to do, what to expect, when to seek care
        What to Avoid: Medical jargon without definitions
        """
    elif user_type == "Youth":
        personalization = """
        Target Audience: Youth
        Language Style: Clear, calm, and reassuring
        Sentence Structure: Short, simple sentences
        Content Focus: What they can do, what is safe, next steps
        What to Avoid: Complex terms and long explanations, Medical terminology and diagnostic language
        """
    elif user_type == "Teacher":
        personalization = """
        Target Audience: Teachers
        Language Style: Clear and instructional
        Sentence Structure: Short, direct sentences
        Content Focus: Classroom supports, return to learn steps, when to send for medical assessment, safety steps
        What to Avoid: Medical terminology and diagnostic language
        """
    elif user_type == "Coach":
        personalization = """
        Target Audience: Coaches
        Language Style: Clear and directive
        Sentence Structure: Short, direct sentences
        Content Focus: Return to sport steps, safety decisions, when to send for medical assessment
        What to Avoid: Medical terminology and diagnostic language
        """

    return f""" You are a helphul assistant. 
    A {user_type} asked you the following question: {query}
    Review the living guidelines recommendations and the vector stores you have access to. To formulte an answer.
    The response should be based only on the information I provide (the living guidelines recommendations), and the vector stores you have access to.
    {personalization}

The answer should be in this format:
Summary: This section should provide a very concise direct response.
Living Guidelines Recommendations: In this section, you will elaborate based on two things: living guidelines recommendations (the recommendations below) and the Living guideline tools in the "Living guideline tools" vectore store.
Information From the Literature: In this section, use the vecotr store called "Key papers to include" to retrieve additional relevant information to the question. use APA 7 in-text citation in this part. if there is not any relevant information in the files, skip this part

Follow these rules:
- When you mention a recommendation or a paper, refernece it in-text. And don`t use links to reference.
- When you reference recommendations, include their level of evidence if they have one. 
- Everytime a tool is mentioned, include its link right after the mention. 
- In the "Information From the Literature" section, stick to the APA 7 citation style.

Safeguards:
- If the user’s query includes mention of self-harm, suicidal thoughts, suicide attempt, acute depressive episode, or mental health crisis, the response must instruct the health professional to direct the patient (or family) to seek immediate emergency care. The instruction must state that if the patient is experiencing a mental health, addictions, or substance use medical emergency, they should call 911 or go to the nearest hospital emergency department.

if the user`s query cannot be answered based on the living guidelines recommendations, say: "Your query cannot be answered through the living guideline recommendations"

Living Guidelines Recommendations:"{recommendations_markdown}" 
    """    