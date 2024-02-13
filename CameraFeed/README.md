```bash
docker build -t jamcams-camera-feed -f build/dockerfile .

docker run --network jamcams-net jamcams-camera-feed
```