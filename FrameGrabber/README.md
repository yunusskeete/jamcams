```bash
docker build -t jamcams-frame-grabber -f build/dockerfile .

docker run --network jamcams-net jamcams-frame-grabber
```