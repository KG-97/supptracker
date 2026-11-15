# 🧬 SuppTracker - Smart Supplement Interaction Checker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-00a2ff.svg)](https://fastapi.tiangolo.com) [![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org) [![Live](https://img.shields.io/badge/Live-Railway-green.svg)](https://supptracker-production.up.railway.app)

**🚀 Live App**: [https://supptracker-production.up.railway.app](https://supptracker-production.up.railway.app)  
**📡 Public API**: `https://supptracker-production.up.railway.app/api`

A comprehensive supplement interaction tracking system that helps users make informed decisions about supplement combinations. Built with modern web technologies and designed for both developers and end-users.

## ✨ Features

• 🔍 **Smart Search**: Find supplements by name, synonyms, or active compounds  
• ⚠️ **Risk Analysis**: Get detailed risk assessments for supplement pairs  
• 📋 **Stack Checker**: Analyze entire supplement stacks for potential interactions  
• 📱 **Responsive UI**: Clean, accessible interface that works on all devices  
• 🔌 **Public API**: RESTful API for developers to integrate interaction checking  
• 🤖 **ChatGPT Ready**: Structured data perfect for AI-powered health assistants  
• ⚡ **Real-time**: Instant interaction analysis with severity scoring  
• 📊 **Evidence-based**: Risk assessments based on research data
• 🧾 **Broader Coverage**: Includes cardiometabolic interactions like omega-3 with warfarin, calcium with levothyroxine, and melatonin with antihypertensives
• 🧠 **Gemini-backed research search**: Query curated documentation with semantic relevance scoring

## 🚀 Quick Start

### Try the Live App
Visit [https://supptracker-production.up.railway.app](https://supptracker-production.up.railway.app) to start checking supplement interactions immediately.

### Use the Public API

```bash
# Search for supplements
curl https://supptracker-production.up.railway.app/api/search?query=vitamin

# Check interaction between two supplements
curl https://supptracker-production.up.railway.app/api/interaction?compound1=Warfarin&compound2=Vitamin%20K

# Get API documentation
curl https://supptracker-production.up.railway.app/docs
```

### Example API Response

```json
{
  "interactions": [
    {
      "compound_1": "Warfarin",
      "compound_2": "Vitamin K",
      "severity": "high",
      "description": "May reduce anticoagulant effectiveness",
      "recommendation": "Monitor INR closely"
    }
  ]
}
```

## 🔧 Gemini Embeddings Document Search

This project includes a **Gemini-powered document search API** that uses Google's embeddings for semantic search.

### Setting Up Gemini API

1. **Get a Gemini API Key**:
   - Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Sign in with your Google account
   - Click "Get API key" or "Create API key"
   - Copy your API key

2. **Set the API Key as Environment Variable**:

   **For Local Development:**
   ```bash
   # Linux/macOS
   export GEMINI_API_KEY="your-api-key-here"
   
   # Windows (Command Prompt)
   set GEMINI_API_KEY=your-api-key-here
   
   # Windows (PowerShell)
   $env:GEMINI_API_KEY="your-api-key-here"
   ```

   **For Production (Railway/Docker):**
   - Add `GEMINI_API_KEY` as an environment variable in your deployment platform
   - For Railway: Settings → Variables → Add `GEMINI_API_KEY`
   - For Docker: Use `-e GEMINI_API_KEY=your-key` or add to docker-compose.yml

3. **Install Dependencies**:
   ```bash
   pip install google-generativeai numpy
   ```
   
   Or use the updated `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

4. **Use the Gemini Doc Search Endpoint**:

   ```bash
   curl -X POST https://supptracker-production.up.railway.app/api/gemini-doc-search \
     -H "Content-Type: application/json" \
     -d '{
       "documents": [
         "Vitamin D helps with calcium absorption",
         "Omega-3 fatty acids support heart health",
         "Magnesium aids in muscle relaxation"
       ],
       "query": "What helps with bone health?"
     }'
   ```

   **Response:**
   ```json
   {
     "results": [
       {
         "document": "Vitamin D helps with calcium absorption",
         "index": 0,
         "similarity_score": 0.87
       },
       {
         "document": "Magnesium aids in muscle relaxation",
         "index": 2,
         "similarity_score": 0.42
       },
       {
         "document": "Omega-3 fatty acids support heart health",
         "index": 1,
         "similarity_score": 0.31
       }
     ]
   }
   ```

### How It Works

The Gemini document search uses:
- **Google's text-embedding-004 model** for generating embeddings
- **Cosine similarity** for ranking documents by relevance
- **FastAPI route** at `/api/gemini-doc-search`
- Supports multiple documents and returns ranked results

## 💻 For Developers

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/KG-97/supptracker.git
cd supptracker

| Variable | Purpose | Default |
|----------|---------|--------|
| `SUPPTRACKER_DATA_DIR` | Override data folder location | `<repo>/data` |
| `RISK_RULES_PATH` | Alternative YAML rule set path | `api/rules.yaml` |
| `SUPPTRACKER_DOCS_DIR` | Override document corpus for knowledge-base search | `<repo>/docs` |
| `GEMINI_API_KEY` | Gemini API key for embeddings (fallback search is used when unset) | _not set_ |
| `GEMINI_EMBEDDING_MODEL` | Gemini embedding model identifier | `gemini-pro-embeddings` |

### Frontend (React + Vite)
# Backend setup
cd backend
pip install -r requirements.txt
uvicorn app:app --reload

# Frontend setup (new terminal)
cd frontend
npm install
npm start
```

The API will be available at `http://localhost:8000` and the frontend at `http://localhost:3000`.

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: `https://supptracker-production.up.railway.app/docs`
- **ReDoc**: `https://supptracker-production.up.railway.app/redoc`

### Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search` | GET | Search for supplements by name or synonym |
| `/api/compounds/{compound_id}` | GET | Retrieve compound details with related interaction summaries |
| `/api/interaction` | GET | Check interaction between two compounds |
| `/api/stack` | POST | Analyze a complete supplement stack |
| `/api/gemini-doc-search` | POST | Semantic document search using Gemini embeddings |
| `/health` | GET | Health check endpoint |

The compound detail endpoint accepts IDs, common names, or synonyms and
returns the canonical record augmented with a sorted list of related
interactions, including computed risk scores and citation metadata. This makes
it easy to surface the highest-risk partners for a given supplement in a single
request.

### Example Stack Check

```python
import requests

stack = {
    "supplements": ["Vitamin D", "Calcium", "Magnesium", "Omega-3"]
}

response = requests.post(
    "https://supptracker-production.up.railway.app/api/stack",
    json=stack
)

print(response.json())
```

## 📚 Technology Stack

### Backend
- **FastAPI**: Modern, fast web framework for building APIs
- **Python 3.11+**: Latest Python features and performance
- **Pandas**: Data manipulation and analysis
- **Google Generative AI**: Embeddings for semantic search
- **NumPy**: Numerical computations for similarity calculations
- **Uvicorn**: ASGI server for production

### Frontend
- **React 18**: Modern UI library with hooks
- **Material-UI**: Polished component library
- **Axios**: HTTP client for API calls
- **React Router**: Client-side routing

### Deployment
- **Railway**: Cloud platform for deployment
- **Docker**: Containerization for consistency
- **GitHub Actions**: CI/CD automation

## 🔬 Data Sources

Our interaction data is compiled from:
- Clinical research papers
- Drug-supplement interaction databases
- Peer-reviewed medical literature
- Expert clinical guidelines

## ⚠️ Disclaimer

This tool is for informational purposes only and should not replace professional medical advice. Always consult with a healthcare provider before starting, stopping, or changing any supplement regimen.

**Important Notes:**
- Risk assessments are based on available research data  
- Individual responses may vary  
- Not all potential interactions are included  
- Regular data updates ensure current information  

## 🤝 Contributing

We welcome contributions! Whether you're fixing bugs, adding features, or improving documentation:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and test thoroughly
4. Commit with clear messages (`git commit -m 'Add amazing feature'`)
5. Push to your branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

### Areas for Contribution:
- 🔬 Expand the supplement interaction database  
- 📱 Improve mobile user experience  
- 🧠 Enhance AI/ChatGPT integration features  
- 🔧 Add new API endpoints  
- 📚 Improve documentation  
- 🧪 Add more comprehensive tests  

## 📄 License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## 🚀 Deployment Status

• ✅ **Repository**: Public and ready  
• ✅ **Issues & Discussions**: Enabled  
• ✅ **CI/CD**: Automated testing and deployment  
• ✅ **📡 Production**: Deployed on Railway  
• ✅ **Live Application**: [https://supptracker-production.up.railway.app](https://supptracker-production.up.railway.app)  
• ✅ **Public API**: Available at `/api` endpoint  
• ✅ **API Documentation**: Interactive docs at `/docs`  
• ✅ **Monitoring**: Health checks and logging active  

---

Built with ❤️ for safer supplement use

For questions, issues, or feature requests, please use [GitHub Discussions](https://github.com/KG-97/supptracker/discussions) or [open an issue](https://github.com/KG-97/supptracker/issues).
