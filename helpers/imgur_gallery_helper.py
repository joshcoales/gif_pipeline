import asyncio
import re
from typing import Optional, List, Dict

import requests

from database import Database
from group import Group
from helpers.helpers import Helper, random_sandbox_video_path
from message import Message
from tasks.task_worker import TaskWorker
from telegram_client import TelegramClient


class ImgurGalleryHelper(Helper):

    def __init__(self, database: Database, client: TelegramClient, worker: TaskWorker, imgur_client_id: str):
        super().__init__(database, client, worker)
        self.imgur_client_id = imgur_client_id

    async def on_new_message(self, chat: Group, message: Message) -> Optional[List[Message]]:
        # If message has imgur gallery/album link in it
        matching_links = re.findall(r"imgur.com/(?:gallery|a)/([0-9a-z]+)", message.text, re.IGNORECASE)
        if not matching_links:
            return None
        async with self.progress_message(chat, message, "Processing imgur gallery links in message"):
            galleries = await asyncio.gather(*(
                self.handle_gallery_link(chat, message, gallery_id) for gallery_id in matching_links
            ))
            return [message for gallery in galleries for message in gallery]

    async def handle_gallery_link(self, chat: Group, message: Message, gallery_id: str) -> List[Message]:
        api_url = "https://api.imgur.com/3/album/{}".format(gallery_id)
        api_key = f"Client-ID {self.imgur_client_id}"
        api_resp = requests.get(api_url, headers={"Authorization": api_key})
        api_data = api_resp.json()
        images = [image for image in api_data["data"]["images"] if "mp4" in image]
        if len(images) == 0:
            return [await self.send_text_reply(chat, message, "That imgur gallery contains no videos.")]
        return await asyncio.gather(*(self.send_imgur_video(chat, message, image) for image in images))

    async def send_imgur_video(self, chat: Group, message: Message, image: Dict[str, str]) -> Message:
        file_url = image["mp4"]
        file_ext = file_url.split(".")[-1]
        resp = requests.get(file_url)
        file_path = random_sandbox_video_path(file_ext)
        with open(file_path, "wb") as f:
            f.write(resp.content)
        return await self.send_video_reply(chat, message, file_path)
