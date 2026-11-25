# Assignment 4: Loan EMI Calculator on Kubernetes (Minikube)

## Repository Structure
- app/ : Web application, Dockerfile, .dockerignore
- k8s/ : Kubernetes YAML manifests (MongoDB StatefulSet, Services, ConfigMap, Deployment, Ingress, HPA)
- scripts/ : Load testing, profiling, and graph generation scripts
- results/ : Benchmark CSVs and generated graphs (results/graphs/)

## Run on Fresh Minikube
1. minikube start
2. minikube addons enable ingress
3. minikube addons enable metrics-server
4. kubectl apply -f k8s/
5. Map 127.0.0.1 emi.local in hosts and run minikube tunnel
