import base64
import json
import requests
import uuid
from pathlib import Path
import asyncio

from fastapi import APIRouter, Form, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse
from beanie import PydanticObjectId

from database.db import Database
from models.basemodel import UserRequest, UserRequestUpdate
from library.func import get_storage_path, save_image, read_image
from library.img_process import image_processing, make_example_from_ttf
from library.get_config import get_config

from typing import List

import time


# 쓸 라우터랑 안쓸 라우터랑 분리하기?
# TODO: logging

INFERECE_SERVER_URL = get_config("Inference_URL")
EXAMPLE_TEXT = "가나다라마바사"
EXAMPLE_BG_IMG = ""
# EXAMPLE_TEXT = get_config("example_text")
# EXAMPLE_BG_IMG = get_config("example_image_PATH")


async def request_rest(id: str, cropped_img_path: str, text: str):
    inference_server_url = INFERECE_SERVER_URL
    headers = {"Content-Type": "application/json"}

    request_dict = {"inputs": {"id": id, "cropped_img_path": cropped_img_path, "text": text}}

    response = requests.post(
        inference_server_url,
        json.dumps(request_dict),
        headers=headers,
    )

    return response


user_router = APIRouter()
requests_database = Database(UserRequest)


@user_router.post("/request")
async def create_inference_request(email: str = Form(...), image_file: UploadFile = File(...)) -> dict:

    # define user id by uuid
    user_id = str(uuid.uuid4())
    # read image by pillow
    image_file = await read_image(image_file)
    # get crop image after pre-processing
    cropped_image = image_processing(image_file, brightness_adj=1.5, contrast_enhance=2)
    # make path and save original & crop image
    storage_path = get_storage_path(user_id)
    image_path = storage_path / Path("ori.jpg") #TODO 확장자는 따로 지정해줘야하나?
    cropped_image_path = storage_path / Path("crop.jpg")

    await asyncio.gather(
        save_image(image_file, str(storage_path/"ori.jpg")),
        save_image(cropped_image, str(storage_path/"crop.jpg"))
    )

    # create new db recode 
    user_request = UserRequest(
        id=user_id,
        email=email,
        original_image_path=str(image_path),
        cropped_image_path=str(cropped_image_path)
    )

    await requests_database.save(user_request)
    print(f"Request ID {user_id[:-8]} recoded to DB sucessfully.")

    #TODO Request
    response = await request_rest(id=user_id,
                                  cropped_img_path=str(cropped_image_path),
                                  text=EXAMPLE_TEXT)
    #TODO
    if response.status_code == 200:
        return {"status": "success", "uuid": user_id}
    

    return {"status": "fail"}

    #TODO 프론트에 uuid 를 보내줘야 한다
    # 1. 2개로 나눠줘야 한다 - 성공시, 실패시. 따로 메세지가 와야된다. 
    # promise 에 resove 랑 reject 이라 
    # 성공시
    # return {"code": True, "message": "sucessfully", "uuid": uuid}
    # # 실패시
    # return {"code": False, "message": "ddd"}


@user_router.get("/status/{id}")
async def get_request_status(id: str):
    user_request = await requests_database.get(id)
    
    if not user_request:
        return {"status": "fail", "message": "user_request info with ID does not exist."}
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail="user_request info with ID dose not exist."
        # )
      
    # TODO 성공시 return 을 생성중 / 완료 두개로 수정 -> log 로 저장
    # 실패는 따로. 보내주고 싶으면 보내면 된다.
    
    if user_request.example_image_path is not None:
        return {"status": "success", "message": "Completed"}
    else:
        return {"status": "success", "message": "processing"}


#TODO # 샘플링 이미지 생성 완료 신호 받기
@user_router.post("/request/{id}")
async def receive_sampling_complete_signal(id: str) -> dict:
    user_request = await requests_database.get(id)
    
    sampling_images_path_list = user_request.sampling_images_path

    print(sampling_images_path_list)

    #TODO make ttf



    #TODO make example image and save to db

    # example_image = make_example_from_ttf(text=EXAMPLE_TEXT,
    #                                       background_image_path=EXAMPLE_BG_IMG,
    #                                       ttf_file_path=None,)

    return {"message": "signal received successfully."}


#TODO 샘플 이미지 받기
@user_router.get("/sample_image/{id}")
async def get_sampled_image(id: str):
    user_request = await requests_database.get(id)



    #TODO img2ttf, ttf2exmaplei

    return 

# TODO 다운로드?

@user_router.get("/example_image/{id}")
async def get_example_image(id: str):
    user_request = await requests_database.get(id)

    if not user_request:
        return {"status": "fail", "message": "user_request info with ID dose not exist."}
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail="user_request info with ID dose not exist."
        # )
    # get example image path from db
    example_image_path = user_request.example_image_path

    if not example_image_path:
        return {"status": "fail", "message": "sample image path with ID dose not exist."}
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail="Sample image path with ID dose not exist."
        # )
    
    return FileResponse(path=example_image_path)


@user_router.get("/request/{id}", response_model=UserRequest)
async def get_request(id: str) -> UserRequest:
    user_request = await requests_database.get(id)

    if not user_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_request info with ID dose not exist."
        )
    
    return user_request


@user_router.get("/get_all_db", response_model=List[UserRequest])
async def get_all_requests() -> List[UserRequest]:
    user_requests = await requests_database.get_all()

    return user_requests


@user_router.put("/request/{id}", response_model=UserRequest)
async def update_request(id: str, body: dict) -> UserRequest:
    
    user_request = await requests_database.update(id=id, body=body)

    if not user_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_request info with ID dose not exist."
        )

    return user_request


@user_router.delete("/request/{id}")
async def delete_request(id: str) -> dict:
    user_request = await requests_database.delete(id)
    
    if not user_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_requst with ID dose not exist."
        )
    
    return {"message": "Request info deleted successfully."}
