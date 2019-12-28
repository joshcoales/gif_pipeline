import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Optional

from channel import Message, Video
from telegram_client import TelegramClient


def find_video_for_message(message: Message) -> Optional[Video]:
    # If given message has a video, return that
    if message.has_video:
        return message.video
    # If it's a reply, return the video in that message
    if message.is_reply:
        reply_to = message.reply_to_msg_id
        reply_to_msg = message.channel.messages[reply_to]
        return reply_to_msg.video
    # Otherwise, get the video from the message above it?
    messages_above = [k for k, v in message.channel.messages.items() if k < message.message_id and v.has_video]
    if messages_above:
        return message.channel.messages[max(messages_above)].video
    return None


class Helper(ABC):

    def __init__(self, client: TelegramClient):
        self.client = client

    async def send_text_reply(self, message: Message, text: str) -> Message:
        msg = await self.client.send_text_message(message.chat_id, text, reply_to_msg_id=message.message_id)
        new_message = await Message.from_telegram_message(message.channel, msg)
        message.channel[new_message.message_id] = new_message
        await new_message.initialise_directory(self.client)
        return new_message

    async def send_video_reply(self, message: Message, video_path: str, text: str = None) -> Message:
        msg = await self.client.send_video_message(
            message.chat_id, video_path, text,
            reply_to_msg_id=message.message_id
        )
        new_message = await Message.from_telegram_message(message.channel, msg)
        message.channel[new_message.message_id] = new_message
        file_ext = video_path.split(".")[-1]
        new_path = f"{message.directory}/{Video.FILE_NAME}.{file_ext}"
        os.rename(video_path, new_path)
        await new_message.initialise_directory(self.client)
        return new_message

    @contextmanager
    def progress_message(self, message: Message, text: str = None):
        if text is None:
            text = f"In progress. {self.name} is working on this."
        msg = self.client.synchronise_async(self.send_text_reply(message, text))
        yield
        self.client.synchronise_async(self.client.delete_message(message.chat_id, msg.message_id))

    @abstractmethod
    async def on_new_message(self, message: Message):
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__


class DuplicateHelper(Helper):

    def __init__(self, client: TelegramClient):
        # Initialise, get all channels, get all videos, decompose all, add to the master hash
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If message has a video, decompose it if necessary, then check images against master hash
        pass


class TelegramGifHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If message has text which is a link to a gif, download it, then convert it
        # If a message has text saying gif, and is a reply to a video, convert that video
        pass


class TwitterDownloadHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message has a twitter link, and the twitter link has a video, download it
        pass


class YoutubeDownloadHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message has a youtube link, download it
        pass


class RedditDownloadHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message has text with a reddit link, and the reddit post has a video, download it
        pass


class GfycatDownloadHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message has text with a gfycat link, download it
        pass


class VideoCutHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message has text saying to cut, with times?
        # Maybe `cut start:end`, or `cut out start:end` and is a reply to a video, then cut it
        pass


class VideoRotateHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message has text saying to rotate, and is a reply to a video, then cut it
        # `rotate left`, `rotate right`, `flip horizontal`?, `rotate 90`, `rotate 180`
        pass


class VideoCropHelper(Helper):
    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message has text saying to crop, some percentages maybe?
        # And is a reply to a video, then crop it
        pass


class GifSendHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message says to send to a channel, and replies to a gif, then forward to that channel
        # `send deergifs`, `send cowgifs->deergifs`
        # Needs to handle queueing too?
        pass


class ArchiveHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message says to archive, move to archive channel
        pass


class DeleteHelper(Helper):

    def __init__(self, client: TelegramClient):
        super().__init__(client)

    async def on_new_message(self, message: Message):
        # If a message says to delete, delete it and delete local files
        pass
