# Atalho opcional. Sem make (ex.: Windows), use o comando docker compose do comentário.
COMPOSE_TEST = docker compose -f docker-compose.yml -f docker-compose.test.yml
USER ?= cliente1988
ROLE ?= merchant

.PHONY: up up-obs down logs token test test-security lint eval load

up:            # docker compose up -d --build
	docker compose up -d --build

up-obs:        # docker compose --profile obs up -d --build
	docker compose --profile obs up -d --build

down:          # docker compose down
	docker compose down

logs:          # docker compose logs -f api
	docker compose logs -f api

token:         # docker compose exec api python scripts/issue_token.py <user> --role <role>
	docker compose exec api python scripts/issue_token.py $(USER) --role $(ROLE)

test:          # docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests
	$(COMPOSE_TEST) run --rm tests

test-security: # docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests pytest tests/security
	$(COMPOSE_TEST) run --rm tests pytest tests/security

lint:          # docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm lint
	$(COMPOSE_TEST) run --rm lint

eval:          # docker compose --profile eval run --rm eval
	docker compose --profile eval run --rm eval

load:          # docker compose --profile load run --rm k6
	docker compose --profile load run --rm k6
