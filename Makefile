run:
	docker compose build && docker compose up -d
	docker network connect web_default mail-app-1
