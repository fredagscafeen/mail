pull:
	git pull
	docker compose pull
run:
	docker compose build && docker compose up -d
	docker network connect web_default mail-app-1
down:
	docker compose down
logs:
	docker compose logs -f
redeploy:
	make pull
	make run
