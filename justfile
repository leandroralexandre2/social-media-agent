doctor:
    ./scripts/doctor.sh

test:
    python3 -m pytest -q

build:
    docker compose build agent

up:
    docker compose up -d --build

logs:
    docker compose logs -f agent

down:
    docker compose down

restart:
    docker compose up -d --build --force-recreate agent dev-dashboard

cloud-image tag:
    plow-agents image build ghcr.io/leandroralexandre2/social-media-agent:{{tag}}
