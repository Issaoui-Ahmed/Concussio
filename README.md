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
5.  Deploy!

Notes:
* `api/main.py` is the unified FastAPI app used locally and by Vercel.
* `api/index.py` imports that unified app so Vercel can route `/api/*` requests to FastAPI while preserving the full request path.

## 🔒 Demo access

While the prototype is out for evaluation, every visitor passes three screens before the chat:

**Password → Demo/testing notice → Disclaimer → Chatbot**

*   **Password** — set `DEMO_PASSWORD` in `.env` locally and in the Vercel project env. The
    check runs on the server (`lib/demoAccess.ts`), so a locked visitor is never sent the app's
    markup, and the same cookie is required by `/api/chat`, `/api/followups` and
    `/api/translate` (`api/demo_access.py`), so the endpoints cannot be driven around the UI.
    `/admin` is behind the same password. It is a session cookie: closing the browser re-asks.
*   **Demo/testing notice and disclaimer** — acknowledged once per browser session, in that
    order (`lib/entryFlow.ts`).

With `DEMO_PASSWORD` unset the app fails closed: the gate renders with an explanation and the
API answers 503. To take the prototype public later, drop the `isDemoUnlocked()` check from the
two layouts and the `GATED_PATHS` entries from `api/demo_access.py`.

## 📜 License

This project is for educational and guidance purposes. Always consult a qualified healthcare professional for medical advice.
