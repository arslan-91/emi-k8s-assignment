# Loan EMI Calculator (Assignment 4, DS-584 Cloud Computing)

Node.js + Express app that computes loan EMI and stores every calculation in MongoDB.

## Structure

- `app/`      web application (Express + jQuery + Bootstrap)
- `k8s/`      Kubernetes manifests (added in Milestone 2 onwards)
- `scripts/`  load-test and profiling scripts (Milestone 4)
- `results/`  raw outputs of experiments (Milestone 4)

## Run locally (Milestone 1)

```powershell
docker run -d --name mongo-local -p 27017:27017 mongo:6
cd app
npm install
$env:MONGO_URL = "mongodb://localhost:27017/emidb"
npm start
```

Open http://localhost:3000

## API

- `POST /api/emi`     body: `{ "principal": 500000, "rate": 12, "months": 24 }`
- `GET  /api/history` last 10 calculations, newest first
- `GET  /health`      200 only if MongoDB is reachable

## Kubernetes

Instructions for `kubectl apply -f k8s/` will be added after Milestone 2.
