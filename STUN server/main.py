import time
from fastapi import FastAPI, Response, status
from pydantic import BaseModel
from redis import Redis
import json

redis = Redis(host="redis", port=6380)
app = FastAPI()


class RegisterData(BaseModel):
    username: str
    ip: str
    port: str


# register path has a default response of 200, unless a new user has been created. Then we return 201.
@app.post("/register", status_code=status.HTTP_200_OK)
def register(data: RegisterData, response: Response):
    redis.set(data.username, json.dumps({"ip": data.ip, "port": data.port}))
    if redis.get(data.username) is None:
        response.status_code = status.HTTP_201_CREATED
    return {"message": "Peer registered successfully"}


# peers path returns a list of usernames. It always returns 200 on success.
@app.get("/peers", status_code=status.HTTP_200_OK)
def peers():
    # time.sleep(1)
    keys = redis.keys("*")
    return {"peers": [key.decode() for key in keys]}


# peer_info path returns the ip address given a user name. it returns 200 unless the user was not found. In that case, it sends 404.
@app.get("/peer_info", status_code=status.HTTP_200_OK)
def peer_info(username: str, response: Response):
    redisResponse = redis.get(username)
    if redisResponse is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"message": "Peer not found"}
    data: RegisterData = json.loads(redisResponse.decode())
    return {"username": username, "ip": data["ip"], "port": data["port"]}
