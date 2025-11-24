# SuppTracker Implementation Roadmap

## Overview
This roadmap consolidates the best enhancement suggestions for the SuppTracker project, focusing on improving data coverage, risk engine sophistication, user experience, and operationalization.

## Priority 1: Data Expansion

### 1.1 Expand CSV Columns
Add three new columns to `data/compounds.csv`:
- `pregnancy_risk`: Values = None, Low, Moderate, High, Contraindicated
- `renal_risk`: Values = None, Low, Moderate, High (for renal impairment)
- `hepatic_risk`: Values = None, Low, Moderate, High (for hepatic impairment)

Default existing rows to "Unknown" for these new fields.

### 1.2 Add Critical Medications
**OTC Medications:**
- Diphenhydramine, cetirizine, fexofenadine (antihistamines)
- Domperidone, ondansetron (anti-nausea, QT-prolonging)
- Hydroxyzine (antihistamine with QT risk)
- Omeprazole, pantoprazole (PPIs)

**Prescription Medications:**
- SSRIs: Fluoxetine, sertraline, citalopram (note: citalopram has QT risk)
- Antipsychotics: Haloperidol, quetiapine (QT-prolonging)
- Antibiotics: Azithromycin, erythromycin (QT-prolonging)
- Antiarrhythmics: Amiodarone, sotalol, dofetilide
- Warfarin (pregnancy contraindicated)
- Metformin (renal caution)
- Statins: Atorvastatin (hepatic caution)

**Additional Supplements:**
- Ashwagandha, bacopa, spirulina
- NAC (N-acetylcysteine)
- Coenzyme Q10
- Milk thistle, turmeric/curcumin

### 1.3 Expand Interactions Database
Add interactions for newly added compounds, particularly:
- QT-prolonging drug combinations
- Domperidone + CYP3A4 inhibitors
- Pregnancy-dangerous combinations

## Priority 2: Risk Engine Enhancements

### 2.1 User-Specific Risk Flags
Extend API endpoints (`/interaction` and `/stack/check`) to accept:
```python
flags = {
    "pregnant": boolean,
    "renal_impairment": boolean,
    "hepatic_impairment": boolean,
    "long_qt": boolean
}
```

### 2.2 Dose-Aware Logic
Implement dose factor calculation:
```python
dose_factor = min(user_dose / recommended_dose, 2.0)
risk_score *= dose_factor
```

Accept dose mappings in stack check requests:
```python
doses = {"compound_id": user_dose_value}
```

### 2.3 Enhanced Risk Calculation
Update `compute_risk` in `api/risk_api.py` to include:
- Pregnancy weight multiplier (1.5x for High risk compounds)
- Renal/hepatic risk adjustments
- QT-prolongation risk for users with long_qt flag
- Dose-based score adjustments

Add configuration weights to `risk_rules.yaml`:
```yaml
w_pregnancy: 1.5
w_renal: 1.3
w_hepatic: 1.3
w_qt: 1.4
w_dose: 1.2
```

### 2.4 Risk Response Metadata
Include explanation in API responses:
```json
{
  "risk_score": 8.5,
  "category": "avoid",
  "factors": {
    "pregnancy_flag": true,
    "dose_factor": 1.2,
    "qt_risk": "High"
  },
  "sources": ["https://...", "..."]
}
```

## Priority 3: Front-End Improvements

### 3.1 StackChecker UI Component
Create `frontend/src/components/StackChecker.tsx`:
- Autosuggest search powered by `/api/search`
- Editable dose fields for each compound
- User condition checkboxes (Pregnant, Renal impairment, etc.)
- Results table showing interactions and risk scores

### 3.2 Migrate to Tailwind + shadcn/ui
- Replace Material-UI with Tailwind CSS
- Use shadcn/ui components for:
  - Input fields with autosuggest
  - Tooltips (explain risk factors)
  - Modal dialogs
  - Buttons and forms
- Ensure responsive design and accessibility (ARIA attributes)

### 3.3 Autosuggest Search
Implement typeahead:
- Query `/api/search` on each keystroke
- Display top 10 results in dropdown
- Add compound to stack on selection

### 3.4 Tooltips and Source Links
- Add tooltip icons next to each risk indicator
- Link to supporting evidence (pull from `external_links` or `sources.csv`)
- Example: "Citalopram QT risk" links to NHS bulletin

## Priority 4: User Accounts & Personalization

### 4.1 Authentication
Implement JWT-based authentication:
- `POST /api/user/register` - email & hashed password
- `POST /api/user/login` - returns JWT token
- Use FastAPI dependency injection for protected routes

### 4.2 Saved Stacks
Endpoints:
- `GET /api/user/stacks` - retrieve user's saved stacks
- `POST /api/user/stacks` - save new stack
- `PUT /api/user/stacks/{id}` - update stack
- `DELETE /api/user/stacks/{id}` - delete stack

Stack schema:
```json
{
  "name": "My Morning Stack",
  "compounds": [{"id": "...", "dose": 500}],
  "conditions": {"pregnant": false}
}
```

### 4.3 User Profile & Conditions
- `GET/POST /api/user/profile`
- Store chronic conditions to auto-apply in risk calculations
- Allow custom contraindications and allergies

## Priority 5: Operationalization

### 5.1 Docker Containerization
Create `Dockerfile`:
```dockerfile
# Stage 1: Build frontend
FROM node:18 AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ ./api/
COPY data/ ./data/
COPY --from=frontend-build /app/frontend/build ./static
EXPOSE 80
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "80"]
```

Create `docker-compose.yml` for local development:
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:80"
    environment:
      - DATABASE_URL=postgresql://...
  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=secret
```

### 5.2 CI/CD with GitHub Actions
Create `.github/workflows/ci.yml`:
```yaml
name: CI/CD
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest _tests_/ --cov=api
      - name: Lint
        run: flake8 api/
  
  build-deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Build Docker image
        run: docker build -t supptracker:latest .
      - name: Deploy to Railway
        run: railway up
```

### 5.3 Testing Suite
Create test files:
- `_tests_/test_csv_parsing.py` - verify new columns load correctly
- `_tests_/test_risk_engine.py` - test pregnancy/renal/hepatic/dose adjustments
- `_tests_/test_api_endpoints.py` - integration tests for all endpoints

Example test:
```python
def test_pregnancy_risk_adjustment():
    risk = compute_risk(
        compound_a='warfarin',
        compound_b='vitamin_k',
        flags={'pregnant': True}
    )
    assert risk.score > base_score * 1.5
    assert 'pregnancy_flag' in risk.factors
```

## Priority 6: Monetization Strategy

### 6.1 Freemium Model
- **Free tier:** Basic search, pair-wise interactions, stack size ≤ 5
- **Premium tier ($9.99/month):**
  - Unlimited stack size
  - Saved stacks and profiles
  - Advanced risk analytics
  - Personalized recommendations
  - Priority support

### 6.2 Paid API Access
- **Starter:** 1,000 requests/month - $29/month
- **Professional:** 10,000 requests/month - $99/month
- **Enterprise:** Custom pricing, SLA guarantees

Provide API dashboard at `/api/dashboard` for key management and usage metrics.

### 6.3 Partnerships & Licensing
- License interaction database to academic researchers
- Partner with nutraceutical companies for evidence generation
- Sponsored search results (clearly labeled)
- Integration partnerships with health tracking apps

## Implementation Timeline

### Phase 1 (Weeks 1-2): Data Foundation
- [ ] Add new CSV columns (pregnancy_risk, renal_risk, hepatic_risk)
- [ ] Expand compounds dataset with 30+ new OTC/prescription drugs
- [ ] Add 20+ new interactions
- [ ] Fix CSV validation error in row 39

### Phase 2 (Weeks 3-4): Risk Engine
- [ ] Implement user flags (pregnant, renal/hepatic impairment, long_qt)
- [ ] Add dose-aware logic
- [ ] Update risk_rules.yaml with new weights
- [ ] Write comprehensive unit tests

### Phase 3 (Weeks 5-6): Front-End
- [ ] Create StackChecker component
- [ ] Implement autosuggest search
- [ ] Migrate to Tailwind + shadcn/ui
- [ ] Add tooltips and source links

### Phase 4 (Weeks 7-8): User Accounts
- [ ] Implement JWT authentication
- [ ] Create user stack management endpoints
- [ ] Build profile/conditions management
- [ ] Add frontend login/register pages

### Phase 5 (Weeks 9-10): Operationalization
- [ ] Create Dockerfile and docker-compose.yml
- [ ] Set up GitHub Actions CI/CD
- [ ] Deploy to Railway/AWS
- [ ] Configure monitoring and logging

### Phase 6 (Weeks 11-12): Monetization
- [ ] Implement premium subscription with Stripe
- [ ] Create API key management system
- [ ] Build usage analytics dashboard
- [ ] Launch marketing website

## Success Metrics
- **Dataset:** 150+ compounds, 150+ interactions
- **Test Coverage:** >80% code coverage
- **Performance:** API response time <200ms p95
- **Accessibility:** WCAG 2.1 AA compliance
- **Deployment:** Automated CI/CD with <5min build time

## Documentation
Keep updated:
- `README.md` - project overview, local setup
- `docs/API.md` - endpoint documentation
- `docs/RISK_MODEL.md` - risk calculation methodology
- `docs/CONTRIBUTING.md` - contribution guidelines
- `CHANGELOG.md` - version history

## References
- NHS QT Prolongation Bulletin
- Stockley's Drug Interactions
- Clinical pharmacology databases (Drugs.com, Examine.com)
- HIPAA/GDPR compliance guidelines
