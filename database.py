import sqlite3
from typing import List

import dateutil.parser

from group import ChatData
from message import MessageData


class Database:
    DB_FILE = "pipeline.sqlite"

    def __init__(self) -> None:
        self.conn = sqlite3.connect(self.DB_FILE)
        self._create_db()

    def _create_db(self) -> None:
        cur = self.conn.cursor()
        with open("database_schema.sql", "r") as f:
            cur.executescript(f.read())
        self.conn.commit()

    def save_chat(self, chat_data: ChatData):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO chats (chat_id, username, title) VALUES(?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username, title=excluded.title;",
            (chat_data.chat_id, chat_data.username, chat_data.title)
        )
        self.conn.commit()
        cur.close()

    def list_messages_for_chat(self, chat_data: ChatData) -> List[MessageData]:
        cur = self.conn.cursor()
        messages = []
        for row in cur.execute(
                "SELECT chat_id, message_id, datetime, text, is_forward, "
                "file_path, file_mime_type, reply_to, sender_id, is_scheduled "
                "FROM messages WHERE chat_id = ?",
                (chat_data.chat_id,)
        ):
            messages.append(MessageData(
                row[0],
                row[1],
                dateutil.parser.parse(row[2]),
                row[3],
                bool(row[4]),
                row[5] is not None,
                row[5],
                row[6],
                row[7],
                row[8],
                bool(row[9])
            ))
        return messages

    def save_message(self, message: MessageData) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO messages (chat_id, message_id, datetime, text, is_forward, "
            "file_path, file_mime_type, reply_to, sender_id, is_scheduled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id, message_id, is_scheduled) "
            "DO UPDATE SET datetime=excluded.datetime, text=excluded.text, is_forward=excluded.is_forward, "
            "file_path=excluded.file_path, file_mime_type=excluded.file_mime_type, "
            "reply_to=excluded.reply_to, sender_id=excluded.sender_id",
            (
                message.chat_id, message.message_id, message.datetime, message.text, message.is_forward,
                message.file_path, message.file_mime_type, message.reply_to, message.sender_id
            )
        )
        self.conn.commit()

    def remove_message(self, message: MessageData) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM messages WHERE chat_id = ? AND message_id = ? AND is_scheduled = ?",
            (message.chat_id, message.message_id, message.is_scheduled)
        )
        self.conn.commit()

    def get_message_history(self, message: MessageData) -> List[MessageData]:
        pass

    def get_message_family(self, message: MessageData) -> List[MessageData]:
        pass

    def get_messages_matching_hashes(self, hashes: List[str]) -> List[MessageData]:
        pass
