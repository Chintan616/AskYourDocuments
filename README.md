# 🌟 AskYourDocuments: Elevate Your Document Interaction to an Art Form 🌟

**Step into the future of document intelligence.** AskYourDocuments is not just a tool; it's your **personal AI-powered concierge** for navigating complex information. Imagine effortlessly transforming static PDFs, DOCX files, images, and more into dynamic conversational partners. Uncover critical insights with unprecedented speed, extract knowledge with surgical precision, and immerse yourself in a **first-class document analysis experience**, meticulously crafted for discerning professionals who accept nothing less than excellence.

---

## 🔧 Engineered With a Symphony of Premium Technologies

<p align="left">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Jupyter-F37626?style=for-the-badge&logo=jupyter&logoColor=white" alt="Jupyter"/>
  <img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" alt="JavaScript"/>
  <img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white" alt="HTML5"/>
  <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS"/>
  <img src="https://img.shields.io/badge/ChatGPT-10A37F?style=for-the-badge&logo=openai&logoColor=white" alt="ChatGPT"/>
  <img src="https://img.shields.io/badge/LangChain-000000?style=for-the-badge&logo=langchain&logoColor=white" alt="LangChain"/>
  <img src="https://img.shields.io/badge/Google_Colab-F9AB00?style=for-the-badge&logo=googlecolab&logoColor=white" alt="Google Colab"/>
</p>

---

## ✨ Experience Unparalleled Premium Features
- **Sophisticated AI-Driven Analysis:** Delve deep into PDFs, DOCX, and even images, extracting nuanced insights with our advanced AI engine.
- **Intuitive Conversational Interface:** Engage with your documents as if consulting a subject matter expert, receiving articulate and context-aware responses.
- **Exquisite & Responsive Design:** Navigate a visually stunning UI, enhanced with fluid animations and a professional aesthetic that speaks to quality.
- **Universal Format Mastery:** Effortlessly manage and interrogate a diverse range of document types within a single, unified platform.
- **Elite, Enterprise-Grade Performance:** Rely on a robust backend powered by cutting-edge AI models and sophisticated document parsing for consistently superior results.

## ⚙️ A Glimpse into Our Advanced Technical Architecture
- **Frontend Elegance:** Crafted with responsive HTML5, styled with the utility-first power of Tailwind CSS, and brought to life with dynamic JavaScript animations for a seamless user experience.
- **Backend & AI Prowess:** A formidable Python ecosystem, integrating state-of-the-art Large Language Models (LLMs) and intelligent vector embeddings for profound contextual understanding.
- **Precision Document Processing:** Leveraging advanced parsing algorithms for meticulous extraction from PDF, DOCX, XLSX, PPTX, and various image formats.
- **Flexible Deployment Pathways:** Choose between convenient local Jupyter Notebook integration for rapid prototyping or robust enterprise server deployment for scalable solutions.

## 📦 Effortless & Seamless Onboarding Journey
1. **Acquire the Foundation:** Clone the repository to your preferred local or cloud environment.
2. **Ignite the Engine:** Launch the `AskYourDocuments.ipynb` notebook within your Jupyter environment (Google Colab recommended for ease of use and primary development environment).
3. **Automated Configuration:** Execute all cells sequentially; our intuitive setup process guides you effortlessly.
4. **Unlock the Power:** Begin uploading your documents and instantly experience the transformative power of AI-driven conversational intelligence.

---

## 🚀 Ascend to a New Realm of Document Experience Today!
Don't just manage your documents – **master them**. Unearth hidden intelligence, accelerate your workflows, and redefine your relationship with information. Join the vanguard of professionals who are leveraging the unparalleled power of conversational document analysis.

**AskYourDocuments** – Where your documents transcend their static form and become your most insightful, articulate, and indispensable partners. **Dare to experience the difference.**
## ✅ Robust local environment setup (recommended)

If your notebook fails with dependency issues, use this tested workflow.

> Notebook order is now: **1) API setup block first**, then installations, then frontend/backend cells.

```bash
bash scripts/run_notebook.sh
```

This script creates a virtual environment, installs pinned dependencies from `requirements.txt`, and executes the full notebook with `AUTO_START_FLASK=0` so validation can finish without hanging on the Flask server.

### Environment variables
Set these before running the notebook:

- `GITHUB_TOKEN`: GitHub Models API token (used for both chat and embeddings).
- `AZURE_LLM_MODEL_NAME` (optional): defaults to `openai/gpt-4o-mini`.
- `HF_TOKEN`: Hugging Face token for vision/OCR model usage.
- `HF_VISION_MODEL_ID` (optional): defaults to `meta-llama/Llama-3.2-11B-Vision-Instruct:together`.
- `NGROK_AUTHTOKEN` (optional): for public tunnel.
- `AUTO_START_FLASK` (optional): `1` to launch app automatically (default in notebook), `0` for CI/non-blocking execution.

Example:

```bash
export GITHUB_TOKEN="<your_github_models_token>"
export HF_TOKEN="<your_hf_token>"
export NGROK_AUTHTOKEN="<your_ngrok_token>"
export AZURE_LLM_MODEL_NAME="openai/gpt-4o-mini"
bash scripts/run_notebook.sh
```


### If you see `403 Forbidden` during pip install
This usually means your environment's proxy cannot reach package indexes.

Try setting a reachable index mirror before running:

```bash
export PIP_INDEX_URL="https://pypi.org/simple"
# optional
export PIP_EXTRA_INDEX_URL="<your_secondary_index>"
bash scripts/run_notebook.sh
```

The runner now attempts dependency installation in three modes automatically:
1) current proxy env, 2) direct/no-proxy, 3) custom index (if `PIP_INDEX_URL` is set).
