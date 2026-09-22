setup:
    ./scripts/setup.sh

doctor:
    ./scripts/doctor.sh

build:
    docker compose build

up:
    docker compose up -d

down:
    docker compose down

restart:
    docker compose up -d --force-recreate

enable:
    ./scripts/enable-social-monitor.sh

test:
    uv run --no-project --with pytest==8.4.2 pytest -q
