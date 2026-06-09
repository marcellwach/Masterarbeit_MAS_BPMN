$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Backend: FastAPI + Socket.IO mit Hot-Reload auf Port 8000
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Write-Host 'Backend starten...' -ForegroundColor Cyan; Set-Location '$root\backend'; python -m uvicorn main:socket_app --host 127.0.0.1 --port 8000 --reload"

# Frontend: Next.js Dev-Server mit Hot-Reload auf Port 3000
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Write-Host 'Frontend starten...' -ForegroundColor Cyan; Set-Location '$root\frontend'; npm run dev"

Write-Host "Backend  -> http://localhost:8000" -ForegroundColor Green
Write-Host "Frontend -> http://localhost:3000" -ForegroundColor Green
Write-Host "Warte auf Startup..." -ForegroundColor Yellow

Start-Sleep -Seconds 5
Start-Process "http://localhost:3000"
