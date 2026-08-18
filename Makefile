# Alles, was man im Alltag braucht — mehr nicht.
#
#   make test                    Testlauf (Bibliothek und App)
#   make migrate                 Datenbanken anlegen bzw. fortschreiben
#   make dev APP=hoeren          Backend und Vite parallel starten
#   make backend APP=hoeren      nur das Backend
#   make frontend APP=hoeren     nur Vite
#   make install APP=hoeren      Frontend-Abhängigkeiten installieren

APP  ?= hoeren
PORT ?= 8000

FRONTEND     = apps/$(APP)/frontend
NODE_MODULES = $(FRONTEND)/node_modules

.PHONY: test dev backend frontend install migrate train release

test:
	uv run pytest

dev:
	@$(MAKE) -j2 backend frontend APP=$(APP) PORT=$(PORT)

backend:
	uv run uvicorn apps.$(APP).backend.main:app --reload --port $(PORT)

frontend: $(NODE_MODULES)
	cd $(FRONTEND) && npm run dev

install: $(NODE_MODULES)

# Ohne node_modules sucht „npm run dev" das Kommando vite über $$PATH und
# findet auf Debian/Ubuntu womöglich den gleichnamigen Trace-Viewer statt
# des Dev-Servers (siehe docs/betrieb.md). Darum hier erzwungen — „npm ci"
# statt „npm install", weil package-lock.json bewusst im Git liegt.
$(NODE_MODULES): $(FRONTEND)/package-lock.json
	cd $(FRONTEND) && npm ci
	@touch $@

migrate:
	uv run python scripts/migrate.py

train:
	@echo "App „lernen\" ist noch nicht implementiert (siehe README)." && exit 1

release:
	@echo "App „lernen\" ist noch nicht implementiert (siehe README)." && exit 1
