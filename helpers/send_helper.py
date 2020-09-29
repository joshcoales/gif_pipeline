import shutil
from typing import Optional, List, Union

from telethon import Button

from database import Database
from group import Group, Channel
from helpers.helpers import Helper, find_video_for_message
from menu_cache import MenuCache
from message import Message
from tasks.task_worker import TaskWorker
from telegram_client import TelegramClient, message_data_from_telegram


class GifSendHelper(Helper):

    def __init__(
            self,
            database: Database,
            client: TelegramClient,
            worker: TaskWorker,
            channels: List[Channel],
            menu_cache: MenuCache
    ):
        super().__init__(database, client, worker)
        self.channels = channels
        self.destination_menu_msg = None
        self.confirmation_menu_msg = None
        self.delete_menu_msg = None
        self.delete_menu_text = None
        self.menu_cache = menu_cache

    @property
    def writable_channels(self) -> List[Channel]:
        return [channel for channel in self.channels if not channel.config.read_only]

    async def on_new_message(self, chat: Group, message: Message) -> Optional[List[Message]]:
        # If a message says to send to a channel, and replies to a gif, then forward to that channel
        # `send deergifs`, `send cowgifs->deergifs`
        # Needs to handle queueing too?
        text_clean = message.text.lower().strip()
        if not text_clean.startswith("send"):
            return
        video = find_video_for_message(chat, message)
        if video is None:
            return [await self.send_text_reply(chat, message, "I'm not sure which gif you want to send.")]
        dest_str = text_clean[4:].strip()
        if not self.was_giffed(video):
            return await self.not_giffed_warning_menu(chat, message, video, dest_str)
        return await self.handle_dest_str(chat, message, video, dest_str, message.message_data.sender_id)

    async def on_callback_query(self, chat: Group, callback_query: bytes, sender_id: int) -> Optional[List[Message]]:
        split_data = callback_query.decode().split(":")
        if split_data[0] == "clear_dest_menu":
            await self.clear_destination_menu()
            return
        if split_data[0] == "clear_delete_menu":
            await self.clear_delete_menu()
            return
        if split_data[0] == "confirm_send":
            return await self.confirmation_menu(chat, split_data[1], split_data[2], sender_id)
        if split_data[0] != "send":
            return
        chat_id = split_data[2]
        message = chat.message_by_id(int(split_data[1]))
        if chat_id == "s":
            cmd_message = chat.message_by_id(int(split_data[3]))
            return await self.handle_dest_str(chat, cmd_message, message, split_data[4], sender_id)
        return await self.send_video(chat, message, chat_id, sender_id)

    def was_giffed(self, video: Message) -> bool:
        message_history = self.database.get_message_history(video.message_data)
        if len(message_history) < 2:
            return False
        latest_command = message_history[1].text
        if latest_command is not None and latest_command.strip().lower() == "gif":
            return True
        return False

    async def not_giffed_warning_menu(self, chat: Group, cmd: Message, video: Message, dest_str: str) -> List[Message]:
        await self.clear_destination_menu()
        button_data = button_data_send_str(video, cmd.message_data.sender_id, dest_str)
        menu = [
            [Button.inline("Yes, I am sure", button_data)],
            [Button.inline("No thanks!", "clear_dest_menu")]
        ]
        menu_text = "It looks like this video has not been giffed. Are you sure you want to send it?"
        menu_msg = await self.send_text_reply(chat, cmd, menu_text, buttons=menu)
        self.destination_menu_msg = menu_msg
        self.menu_cache.add_menu_msg(menu_msg, cmd.message_data.sender_id)
        return [menu_msg]

    async def handle_dest_str(
            self,
            chat: Group,
            cmd: Message,
            video: Message,
            dest_str: str,
            sender_id: int
    ) -> List[Message]:
        if dest_str == "":
            return await self.destination_menu(chat, cmd, video, sender_id)
        if "<->" in dest_str:
            destinations = dest_str.split("<->", 1)
            return await self.send_two_way_forward(chat, cmd, video, destinations[0], destinations[1], sender_id)
        if "->" in dest_str:
            destinations = dest_str.split("->", 1)
            return await self.send_forward(chat, cmd, video, destinations[0], destinations[1], sender_id)
        if "<-" in dest_str:
            destinations = dest_str.split("<-", 1)
            return await self.send_forward(chat, cmd, video, destinations[1], destinations[0], sender_id)
        return await self.send_video(chat, video, dest_str, sender_id)

    async def destination_menu(self, chat: Group, cmd: Message, video: Message, sender_id: int) -> List[Message]:
        await self.clear_destination_menu()
        menu = []
        for channel in self.writable_channels:
            admin_ids = await self.client.list_authorized_channel_posters(channel.chat_data)
            if sender_id in admin_ids:
                button_data = button_data_confirm_send(video, channel)
                menu.append([Button.inline(channel.chat_data.title, button_data)])
        if menu:
            menu_text = "Which channel should this video be sent to?"
            menu_msg = await self.send_text_reply(chat, video, menu_text, buttons=menu)
            self.destination_menu_msg = menu_msg
            self.menu_cache.add_menu_msg(menu_msg, sender_id)
            return [menu_msg]
        return [await self.send_text_reply(chat, cmd, "You do not have permission to send to any available channels.")]

    async def confirmation_menu(self, chat: Group, video_id: str, destination_id: str, sender_id: int) -> List[Message]:
        destination = self.get_destination_from_name(destination_id)
        button_data = button_data_send(int(video_id), destination.chat_data.chat_id)
        menu = [
            [Button.inline("I am sure", button_data)],
            [Button.inline("No thanks", "clear_dest_menu")]
        ]
        menu_text = f"Are you sure you want to send this video to {destination.chat_data.title}?"
        menu_msg = await self.edit_message(
            chat,
            self.destination_menu_msg,
            new_text=menu_text,
            new_buttons=menu
        )
        self.destination_menu_msg = menu_msg
        self.menu_cache.add_menu_msg(menu_msg, sender_id)
        return [menu_msg]

    async def send_two_way_forward(
            self,
            chat: Group,
            cmd_message: Message,
            video: Message,
            destination1: str,
            destination2: str,
            sender_id: int
    ) -> List[Message]:
        messages = []
        messages += await self.send_forward(chat, cmd_message, video, destination1, destination2, sender_id),
        messages += await self.send_forward(chat, cmd_message, video, destination2, destination1, sender_id)
        return messages

    async def send_forward(
            self,
            chat: Group,
            cmd_message: Message,
            video: Message,
            destination_from: str,
            destination_to: str,
            sender_id: int
    ) -> List[Message]:
        chat_from = self.get_destination_from_name(destination_from)
        if chat_from is None:
            return [await self.send_text_reply(chat, cmd_message, f"Unrecognised destination from: {destination_from}")]
        chat_to = self.get_destination_from_name(destination_to)
        if chat_to is None:
            return [await self.send_text_reply(chat, cmd_message, f"Unrecognised destination to: {destination_to}")]
        # Check permissions in both groups
        from_admin_ids = await self.client.list_authorized_channel_posters(chat_from.chat_data)
        to_admin_ids = await self.client.list_authorized_channel_posters(chat_to.chat_data)
        if sender_id not in from_admin_ids or sender_id not in to_admin_ids:
            error_text = f"You need to be an admin of both channels to send a forwarded video."
            return [await self.send_text_reply(chat, cmd_message, error_text)]
        # Send initial message
        initial_message = await self.send_message(chat_from, video_path=video.message_data.file_path)
        # Forward message
        new_message = await self.forward_message(chat_to, initial_message)
        # Delete initial message
        await self.client.delete_message(initial_message.message_data)
        initial_message.delete(self.database)
        confirm_text = f"This gif has been sent to {chat_to.chat_data.title} via {chat_from.chat_data.title}"
        confirm_message = await self.after_send_delete_menu(chat, video, confirm_text, sender_id)
        # Remove menu
        await self.clear_destination_menu()
        messages = [new_message]
        if confirm_message:
            messages.append(confirm_message)
        return messages

    async def send_video(
            self,
            chat: Group,
            video: Message,
            destination_id: Union[str, int],
            sender_id: int
    ) -> List[Message]:
        destination = self.get_destination_from_name(destination_id)
        if destination is None:
            return [await self.send_text_reply(chat, video, f"Unrecognised destination: {destination_id}")]
        dest_admin_ids = await self.client.list_authorized_channel_posters(destination.chat_data)
        if sender_id not in dest_admin_ids:
            return [await self.send_text_reply(chat, video, "You do not have permission to post in that channel.")]
        new_message = await self.send_message(destination, video_path=video.message_data.file_path)
        confirm_text = f"This gif has been sent to {destination.chat_data.title}."
        confirm_message = await self.after_send_delete_menu(chat, video, confirm_text, sender_id)
        # Remove menu
        await self.clear_destination_menu()
        messages = [new_message]
        if confirm_message:
            messages.append(confirm_message)
        return messages

    def get_destination_from_name(self, destination_id: Union[str, int]) -> Optional[Group]:
        destination = None
        for channel in self.writable_channels:
            if channel.chat_data.username == destination_id:
                destination = channel
                break
            if str(channel.chat_data.chat_id) == str(destination_id):
                destination = channel
                break
        return destination

    async def forward_message(self, destination: Group, message: Message) -> Message:
        msg = await self.client.forward_message(destination.chat_data, message.message_data)
        message_data = message_data_from_telegram(msg)
        if message.has_video:
            # Copy file
            new_path = message_data.expected_file_path(destination.chat_data)
            shutil.copyfile(message.message_data.file_path, new_path)
            message_data.file_path = new_path
        # Set up message object
        new_message = await Message.from_message_data(message_data, destination.chat_data, self.client)
        self.database.save_message(new_message.message_data)
        destination.add_message(new_message)
        return new_message

    async def after_send_delete_menu(
            self,
            chat: Group,
            reply_to: Message,
            text: str,
            sender_id: int
    ) -> Optional[Message]:
        admin_ids = await self.client.list_authorized_to_delete(chat.chat_data)
        if sender_id not in admin_ids:
            return None
        full_text = text + "\nWould you like to delete the message family?"
        menu = [
            [Button.inline("Yes please", f"delete:{reply_to.message_data.message_id}")],
            [Button.inline("No thanks", f"clear_delete_menu")]
        ]
        message = await self.send_text_reply(chat, reply_to, full_text, buttons=menu)
        self.delete_menu_text = text
        self.delete_menu_msg = message
        self.menu_cache.add_menu_msg(message, sender_id)
        return message

    async def clear_destination_menu(self) -> None:
        if self.destination_menu_msg is not None:
            await self.client.delete_message(self.destination_menu_msg.message_data)
            self.destination_menu_msg.delete(self.database)
            self.destination_menu_msg = None

    async def clear_confirmation_menu(self) -> None:
        if self.confirmation_menu_msg is not None:
            await self.client.delete_message(self.confirmation_menu_msg.message_data)
            self.confirmation_menu_msg.delete(self.database)
            self.confirmation_menu_msg = None

    async def clear_delete_menu(self) -> None:
        if self.delete_menu_msg is not None:
            await self.client.edit_message(
                self.delete_menu_msg.chat_data,
                self.delete_menu_msg.message_data,
                self.delete_menu_text,
                new_buttons=None
            )
            self.delete_menu_msg.delete(self.database)
            self.delete_menu_msg = None


def button_data_send_str(video: Message, sender_id: int, dest_str: str) -> str:
    return f"send:{video.message_data.message_id}:s:{sender_id}:{dest_str}"


def button_data_send(video_id: int, dest_id: int) -> str:
    return f"send:{video_id}:{dest_id}"


def button_data_confirm_send(video: Message, channel: Channel) -> str:
    return f"confirm_send:{video.message_data.message_id}:{channel.chat_data.chat_id}"
