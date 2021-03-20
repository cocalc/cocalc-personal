build:
	DOCKER_BUILDKIT=0  docker build -t cocalc .

build-no-cache:
	DOCKER_BUILDKIT=0  docker build --no-cache -t cocalc .


