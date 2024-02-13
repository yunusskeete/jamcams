# Kafka Server

The Kafka Server is running a pull of the [bitnami/kafka](https://hub.docker.com/r/bitnami/kafka) Docker image on the `jamcams-net` Docker network (`docker network create jamcams-net --driver bridge`).

```bash
docker pull bitnami/kafka

docker run -d --name kafka-server --hostname kafka-server \
    --network jamcams-net \
    -e KAFKA_CFG_NODE_ID=0 \
    -e KAFKA_CFG_PROCESS_ROLES=controller,broker \
    -e KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
    -e KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
    -e KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=0@kafka-server:9093 \
    -e KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER \
    bitnami/kafka:latest

docker run -it --rm \
    --network jamcams-net \
    bitnami/kafka:latest kafka-topics.sh --list  --bootstrap-server kafka-server:9092
```

Default Kafka broker port is `9092`.
The `kafka-server` is accessible at `kafka-server:9092` within the `jamcams-net` Docker network.
