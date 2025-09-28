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
  "compound1": "Warfarin",
  "compound2": "Vitamin K",
  "interaction_severity": "high",
  "risk_score": 8.5,
  "description": "Vitamin K can significantly reduce warfarin effectiveness",
  "recommendation": "Consult healthcare provider before combining"
}
```

## 💻 Local Development

### Backend (FastAPI)

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.risk_api:app --reload --host 0.0.0.0 --port 8000
```

**Environment Variables:**

| Variable | Purpose | Default |
|----------|---------|--------|
| `SUPPTRACKER_DATA_DIR` | Override data folder location | `<repo>/data` |
| `RISK_RULES_PATH` | Alternative YAML rule set path | `api/rules.yaml` |

### Frontend (React + Vite)

```bash
npm install
npm run dev     # Development server
npm run build   # Production build
npm run preview # Preview production build
```

**Configuration:**
• `VITE_API_BASE` - API base URL (auto-detects if unset)

### Docker Deployment

```bash
docker compose build
docker compose up
```

Access: UI at http://localhost:5173, API at http://localhost:8000

## 🤖 ChatGPT Integration

SuppTracker is designed to work seamlessly with ChatGPT and other AI assistants:

### For Users:

• Ask ChatGPT: "Check if I can safely take [supplement A] with [supplement B]"  
• ChatGPT can query our API to provide evidence-based interaction information  
• Get personalized supplement stack analysis through AI-powered conversations  

### For Developers:

• Integrate our API into ChatGPT plugins or custom AI applications  
• Use structured JSON responses for easy AI processing  
• Enable natural language supplement interaction queries  

### Example ChatGPT Prompt:

```
"I'm taking these supplements: [list]. Can you check for interactions using the SuppTracker API at https://supptracker-production.up.railway.app/api and provide safety recommendations?"
```

## 📚 API Documentation

### Endpoints

#### 🔍 Search Supplements
```
GET /api/search?query={search_term}&limit={max_results}
```

#### ⚠️ Check Interaction
```
GET /api/interaction?compound1={name1}&compound2={name2}
```

#### 🏥 Health Check
```
GET /api/health
```

#### 📖 Interactive Documentation
Visit `/docs` for complete Swagger/OpenAPI documentation with live testing interface.

## 🏗️ Project Structure

```
supptracker/
├── api/              # FastAPI backend application
├── frontend/         # React frontend application
├── data/             # Supplement data and risk rules
├── tests/            # Test suites
├── docker/           # Docker configurations
└── .github/          # CI/CD workflows
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=api tests/

# Run frontend tests
npm test
```

## 🛡️ Safety & Disclaimers

⚠️ **Important**: This tool is for informational purposes only and does not replace professional medical advice. Always consult healthcare providers before making supplement decisions.

• Risk assessments are based on available research data  
• Individual responses may vary  
• Not all potential interactions are included  
• Regular data updates ensure current information  

## 🤝 Contributing

We welcome contributions! Whether you're fixing bugs, adding features, or improving documentation:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and test thoroughly
4. Commit with clear messages (`git commit -m 'Add amazing feature'`)
5. Push to your branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

### Areas for Contribution:

• 🔬 Expand the supplement interaction database  
• 📱 Improve mobile user experience  
• 🧠 Enhance AI/ChatGPT integration features  
• 🔧 Add new API endpoints  
• 📚 Improve documentation  
• 🧪 Add more comprehensive tests  

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
