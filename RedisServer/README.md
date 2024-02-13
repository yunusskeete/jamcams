# Redis Server

The Redis Server is running a pull of the [_/redis](https://hub.docker.com/_/redis) Docker image on the `jamcams-net` Docker network (`docker network create jamcams-net --driver bridge`).

```bash
docker pull redis

docker run -d -it --network jamcams-net --name redis-server redis
```

Runs a detached instance of the container in the background (daemon mode).
Allocates a pseudo terminal and keeps the standard input open to interact with the container.

Default redis  port is `6379`.
The `redis-server` is accessible at `redis-server:6379` within the `jamcams-net` Docker network.
