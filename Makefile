# Alles, was man im Alltag braucht — mehr nicht.
#
#   make test                    Testlauf (Bibliothek und App)
#   make migrate                 Datenbanken anlegen bzw. fortschreiben
#   make dev APP=hoeren          Backend und Vite parallel starten
#   make backend APP=hoeren      nur das Backend
#   make frontend APP=hoeren     nur Vite

APP  ?= hoeren
PORT ?= 8000

.PHONY: test dev backend frontend migrate train release

test:
	uv run pytest

dev:
	@$(MAKE) -j2 backend frontend APP=$(APP) PORT=$(PORT)

backend:
	uv run uvicorn apps.$(APP).backend.main:app --reload --port $(PORT)

frontend:
	cd apps/$(APP)/frontend && npm run dev

migrate:
	uv run python scripts/migrate.py

train:
	@echo "App „lernen\" ist noch nicht implementiert (siehe README)." && exit 1

release:
	@echo "App „lernen\" ist noch nicht implementiert (siehe README)." && exit 1
