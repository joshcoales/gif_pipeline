import asyncio
import re
from typing import Optional, List

import requests

from database import Database
from group import Group
from helpers.helpers import random_sandbox_video_path
from helpers.telegram_gif_helper import TelegramGifHelper
from message import Message
from tasks.task_worker import TaskWorker
from telegram_client import TelegramClient


class FAHelper(TelegramGifHelper):

    def __init__(self, database: Database, client: TelegramClient, worker: TaskWorker):
        super().__init__(database, client, worker)

    async def on_new_message(self, chat: Group, message: Message) -> Optional[List[Message]]:
        # If message has relevant link in it
        matching_links = re.findall(r"furaffinity.net/view/([0-9]+)", message.text, re.IGNORECASE)
        if not matching_links:
            return None
        async with self.progress_message(chat, message, "Processing FA links in message"):
            return await asyncio.gather(*(self.handle_post_link(chat, message, post_id) for post_id in matching_links))

    async def handle_post_link(self, chat: Group, message: Message, post_id: str):
        api_link = f"https://faexport.spangle.org.uk/submission/{post_id}.json"
        api_resp = requests.get(api_link, headers={"User-Agent": "Gif pipeline"})
        api_data = api_resp.json()
        file_url = api_data["download"]
        file_ext = file_url.split(".")[-1]
        if file_ext not in ["gif"]:
            return await self.send_text_reply(chat, message, "That post doesn't seem to be a gif.")
        # Download file
        resp = requests.get(file_url)
        file_path = random_sandbox_video_path(file_ext)
        with open(file_path, "wb") as f:
            f.write(resp.content)
        # If gif, convert to telegram gif
        if file_ext == "gif":
            file_path = await self.convert_video_to_telegram_gif(file_path)
        return await self.send_video_reply(chat, message, file_path)
