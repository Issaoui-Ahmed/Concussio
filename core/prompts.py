
def build_domain_classifier_prompt(query, domain_prompt):
    return f""" User query: {query}
        selects exactly one domain from the list below that best matches the user's query. 
        output a json with the domain number.\n\n"
        "if the user's query does not match any of the domains, return -1 "
        "Domains:\n"
        "{domain_prompt}\n\n"
        """    


def build_generator_prompt(query):
    # Default to patient or legacy behavior
    return build_patient_prompt(query)

def build_patient_prompt(query):
    with open("all_rec_markdown.md", "r", encoding="utf-8") as f:
        recommendations_markdown = f.read()
    return f"""
    Respond to the user`s query
    user`s query: {query}

    The user is a patient. so the answer should be patient centered, simple and easy to understand.

respond in this way :
TLDR: This section should provide a very concise direct response.
Elaboration: it should be mainly based on the living guidelines recommendations (the recommendations below). It should be addressing the point of the question exactly.  
it should be grounded. when you mention any information, you should include its reference (embed references in the answer, not separately). 
To reference information, don`t use links. When you reference recommendations, and include their level of evidence if they have one. 
If the direct answer would be benefit from information from the "tools", do a file search in the "Living guideline tools" vector store and retrieve the relavant information. And when you mention a tool, you must include its link (for example, if the user asked "how do I do a physical assesment", it would be very helphul to answer based on "Tool 2.1 Physical Examination" )
Useful resources: here you list the useful and relevant resources with links. Make sure the links mentioned are directly linked with the answer (relevant). 
Any links mentioned in the "Direct answer" or "Useful resources" should be part of the following whitelist:
Tool 1.2: Concussion Recognition Tool 6. To help identify concussion in children, adolescents, and adults (2023)
Tool 1.3: Manage Acute and Prolonged Symptoms Algorithm
Tool 2.0: Living Guideline Return to Activity Sports and School Protocol (2023)
Tool 2.1 Physical Examination
Tool 2.2 PECARN Management Algorithm for Children after Head Trauma.
Tool 2.3 CATCH2 Rule
Tool 2.4: Algorithm for the Management of the Pediatric Patient ≥ 2 years with Minor Head Trauma
Tool 2.5: “Four P’s” – Prioritize, Plan, Pace, and Position
Tool 2.6: Post-Concussion Information Sheet (2024)
Tool 2.7: Strategies to Promote Good Sleep and Alertness
Tool 6.1: Post-Concussion headache algorithm
Tool 6.2: General Considerations Regarding Pharmacotherapy
Tool 6.3: Approved Medications for Pediatric Indications
Tool 7.1: Managing Post-Concussion Sleep Disturbances Algorithm
Tool 7.2: Factors That May Influence the Child/Adolescent’s Sleep/Wake Cycle
Tool 8.1: Post-Concussion Mental Health Considerations Algorithm
Tool 8.2: Management of Prolonged Mental Health Disorders Algorithm
Tool 10.1: Post-Concussion Vestibular (balance/dizziness) and Vision Disturbances Algorithm
Tool 12.1: Concussion Implications and Interventions for the Classroom
Tool 12.2: Template: Letter of Accommodation from the Concussion Care Team to the School
Tool 12.3: Template Letter of Accommodation from Physician to School
Tool 12.4: Sample Letter/Email from School to Parents
Tool 15.1: Considerations for Telemedicine and Virtual Care Algorithm 
Tool 15.2 Considerations for a virtual physical examination for medical assessment and follow-up of concussion patients
Tool 15.3: Virtual Care Exam Training Resource. A training manual to assist front-line healthcare professionals who are caring for patients that cannot be seen in person or have already had an in-person assessment and require follow-up.
If the user’s query includes mention of self-harm, suicidal thoughts, suicide attempt, acute depressive episode, or mental health crisis, the response must instruct the health professional to direct the patient (or family) to seek immediate emergency care. The instruction must state that if the patient is experiencing a mental health, addictions, or substance use medical emergency, they should call 911 or go to the nearest hospital emergency department.

if the user`s query cannot be answered based on the living guidelines recommendations, say: "Your query cannot be answered through the living guideline recommendations"

Living Guidelines Recommendations: "{recommendations_markdown}" 
    """

def build_doctor_prompt(query):
    with open("all_rec_markdown.md", "r", encoding="utf-8") as f:
        recommendations_markdown = f.read()
    return f"""
    Respond to the user`s query
    user`s query: {query}
    Review the living guidelines recommendations and the vector stores you have access to. To formulte an answer.
    The response should be based only on the information I provide (the living guidelines recommendations), and the vector stores you have access to.
    The user is a doctor. so the answer should be doctor centered.

The answer should be in this format:
TLDR: This section should provide a very concise direct response.
Elaboration: In this section, you will elaborate based on two things: living guidelines recommendations (the recommendations below) and the the vector store that contains the tools.
Complementary elaboration: In this section, use the vecotr store called "Key papers to include" to retrieve additional relevant information to the question. use APA 7 in-text citation in this part. if there is not any relevant information in the files, skip this part

Follow these rules:
- When you mention anything (recommendation, tool, paper) refernece it in-text. And don`t use links to reference.
- When you reference recommendations, include their level of evidence if they have one. 

If the user’s query includes mention of self-harm, suicidal thoughts, suicide attempt, acute depressive episode, or mental health crisis, the response must instruct the health professional to direct the patient (or family) to seek immediate emergency care. The instruction must state that if the patient is experiencing a mental health, addictions, or substance use medical emergency, they should call 911 or go to the nearest hospital emergency department.

if the user`s query cannot be answered based on the living guidelines recommendations, say: "Your query cannot be answered through the living guideline recommendations"

Living Guidelines Recommendations: "{recommendations_markdown}" 
    """