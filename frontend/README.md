# AgentSRE Frontend

## Install and run

Enter this `frontend` directory first.

PowerShell:

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

macOS/Linux:

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. The backend URL is configured in `.env.local` with `VITE_API_BASE_URL`.
