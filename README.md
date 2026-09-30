# Concussio Chat

Concussio Chat is a specialized AI-powered application designed to provide evidence-based guidance on concussion management. Built with a **Next.js** frontend and a **Python (FastAPI)** backend, it leverages "Living Guidelines Recommendations" to deliver tailored information to both patients and healthcare professionals.

## 🚀 Overview

The system is designed to bridge the gap between complex medical guidelines and accessible advice. It features dual interfaces:
*   **Patient Mode**: Delivers simple, patient-centered explanations without jargon.
*   **Doctor Mode**: Provides detailed, evidence-backed medical responses, including levels of evidence and citations for clinical decision-making.

## ✨ Key Features

*   **Role-Specific AI**: tailored prompt engineering ensures the tone and complexity of the answer match the user (Patient vs. Doctor).
*   **Evidence-Based**: Responses are grounded in the "Living Guidelines Recommendations" and relevant vector stores, ensuring high fidelity to medical standards.
*   **Safety First**: Built-in safeguards detect mental health emergencies (e.g., self-harm, crisis) and immediately direct users to emergency care.
*   **Modern Stack**: A responsive, fast UI built with Next.js 14 (App Router) backed by robust Python APIs.

## 🛠️ Architecture

*   **Frontend**: Next.js (App Router), Tailwind CSS, Lucide React (Icons), React Markdown.
*   **Backend**: Python FastAPI, designed to run as serverless functions or a standalone server.
*   **Data Source**: Parses `all_rec_markdown.md` for real-time RAG (Retrieval-Augmented Generation) context.

## 🏁 Getting Started

Follow these instructions to set up the project locally.

### Prerequisites

*   **Node.js** (v18+ recommended)
*   **Python** (v3.9+ recommended)
*   **Fuel IX API Key**

### 1. Installation

**Frontend Setup:**
```bash
npm install
```

**Backend Setup:**
```bash
# Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install python dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file in the root directory and add your Fuel IX API key. You can use `.env.example` as a template.

```env
FUELIX_API_KEY=sk-your-fuelix-key-here
FUELIX_API_BASE_URL=https://api.fuelix.ai/v1
```

### 3. Running Locally

To run the full application, you will need two terminal windows.

**Terminal 1 (Backend - Port 8000):**
```bash
uvicorn api.main:app --port 8000 --env-file .env
```

**Terminal 2 (Frontend - Port 3000):**
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser to start the application.

## ☁️ Deployment

This project is optimized for deployment on **Vercel**.

1.  Push your code to a GitHub repository.
2.  Import the project into Vercel.
3.  Vercel will automatically detect the **Next.js** framework and the **Python** API in the `api/` directory.
4.  Add environment variables in Vercel Project Settings:
    * `FUELIX_API_KEY` (required for the root chat and the Fuel IX admin pages)
    * `FUELIX_API_BASE_URL` (optional, default is `https://api.fuelix.ai/v1`)
    * `FUELIX_PRODUCT_ID` (optional, default is `core`)
    * `DEMO_PASSWORD` (required — see below; without it the deployment stays locked)
    * `ADMIN_PASSWORD` (required — see below; without it `/admin` stays locked)
    * `SHAREPOINT_*` (the CHEO research log — see below; `SHAREPOINT_LOG_CHATS=true` in
      production only, once the study starts)
5.  Deploy!

Notes:
* `api/main.py` is the unified FastAPI app used locally and by Vercel.
* `api/index.py` imports that unified app so Vercel can route `/api/*` requests to FastAPI while preserving the full request path.
* The route modules it combines are named `api/_*.py`, and a new one must be too. Vercel deploys
  every other `api/*.py` that defines `app` as a function of its own. That lets requests skip
  `api/main.py` and the demo-password check it applies: `/api/chat` used to be served that way.
  It also counts against the Hobby plan's limit of 12 functions per deployment.

## 🔒 Demo access

While the prototype is out for evaluation, every visitor passes three screens before the chat:

**Password → Demo/testing notice → Disclaimer → Chatbot**

*   **Password** — set `DEMO_PASSWORD` in `.env` locally and in the Vercel project env. The
    check runs on the server (`lib/demoAccess.ts`), so a locked visitor is never sent the app's
    markup, and the same cookie is required by `/api/chat`, `/api/followups` and
    `/api/translate` (`api/demo_access.py`), so the endpoints cannot be driven around the UI.
    It is a session cookie: closing the browser re-asks.
*   **Demo/testing notice and disclaimer** — acknowledged once per browser session, in that
    order (`lib/entryFlow.ts`).

With `DEMO_PASSWORD` unset the app fails closed: the gate renders with an explanation and the
API answers 503. To take the prototype public later, drop the `isDemoUnlocked()` check from the
two layouts and the `GATED_PATHS` entries from `api/demo_access.py`.

`/admin` sits behind that password **and** a second one:

**Demo password → Admin password → Admin tools**

*   **Admin password** — set `ADMIN_PASSWORD` in `.env` and in the Vercel project env. Every
    invited tester holds the demo password, while the admin pages rerun the content pipeline,
    rewrite the resource pairings and delete Fuel IX vector stores, so the tooling has a secret
    of its own (`lib/adminAccess.ts`, cookie `concussio_admin_access`). It stacks on the demo
    gate rather than replacing it, and fails closed the same way.

    It is mostly a **page gate**. `/api/admin/*`, `/api/fuelix/*`, `/api/scraping` and the
    writing half of `/api/resource-links` are still reachable by anyone holding the demo cookie
    — as they were before this password existed (see `GATED_PATHS` in `api/demo_access.py`).
    Gating them too means teaching the Python middleware about the admin cookie and splitting
    `/api/resource-links`, whose `GET` the public app depends on. The exception is the research
    log below: `api/admin_access.py` recomputes the admin cookie for its endpoints, which write
    into CHEO's SharePoint.

## 🧾 Research log (CHEO REB study)

Every chat exchange is written as one JSON file into a CHEO SharePoint folder, and nowhere else
(`core/research_log.py`). A file holds exactly what the approved protocol lists, and nothing
more:

| Field | Protocol wording |
|---|---|
| `session_id` | Randomly generated session ID. Made in the browser, one per conversation |
| `timestamp` | Timestamp. When the question reached the server, UTC |
| `user_type` | User type selected |
| `question`, `answer` | Content of the conversation. `answer` is `null` when the chatbot failed |

Adding a field is a protocol amendment, not a code change.

*   **How it gets there.** `core/sharepoint.py` signs in to Microsoft Graph as the app
    registration CHEO created, with a certificate (no user, no client secret), and writes with
    the `Sites.Selected` permission plus a `write` grant on the one site. The write happens in
    the same request that produced the answer, before the answer is sent.
*   **Nowhere else.** No local copy, no retry queue, and no conversation text in the server's
    logs. A failed write logs the error alone and drops the record. It never costs the
    participant the answer.
*   **Switched on per deployment.** `SHAREPOINT_LOG_CHATS=true` turns chat logging on. Set it in
    the production env when the study starts and nowhere else, so developers' and preview
    deployments' chats stay out of the study folder. The batch tool's questions stay out too
    (`log: false`, honoured only with the admin cookie).
*   **Configuration.** The `SHAREPOINT_*` variables in `.env.example`. CHEO's actual values
    live only in `.env` and the Vercel env, never in the repository.
*   **Testing.** `/admin/research-log` → **Run test**. It signs in, checks the token's
    permission, opens the site and folder, writes a `TEST_…` record through the same code a
    chat uses, then reads the file back and compares it byte for byte. Each step reports what
    failed and, where it is on CHEO's side, what they still need to do. That test file is the
    only thing the app ever reads back from the folder.

## 📜 License

This project is for educational and guidance purposes. Always consult a qualified healthcare professional for medical advice.
