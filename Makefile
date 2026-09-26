.PHONY: install test api web trueforge iam-mcp seed-demo setup moto-server

install:
	pip install -r server/requirements.txt
	cd apps/web && npm install

test:
	cd server && python -m pytest -q

api:
	cd server && uvicorn main:app --reload --port 8010

web:
	cd apps/web && npm run dev

iam-mcp:
	python integrations/aws-iam-mcp/server.py

trueforge:
	npx -y @truefoundry/trueforge@latest

moto-server:
	moto_server -p 5555

seed-demo:
	python scripts/seed_demo_iam.py

setup:
	python scripts/setup_trueforge.py
