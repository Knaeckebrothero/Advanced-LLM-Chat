"""
Side chats (docs/side_chats.md): conversations forked from a message of another one, to ask
about something or make an image on the side. A side chat is a conversations row with its
parent, the message it was forked from, and side_chat set; its history starts with its parent's
messages up to that message (ConversationHistoryBuilder). Made a conversation of its own, it
gets copies of those messages and of their files.
"""
import logging
from typing import Optional

from backend.database import db
from backend.services import file_store

log = logging.getLogger(__name__)


def promote(conversation_id: str, user_id: int) -> Optional[dict]:
    """
    Make a side chat a conversation of its own: its parent's messages up to the one it was
    forked from are copied into it, with copies of their files, so it no longer depends on its
    parent (which may be deleted later). Blocking (files and the database): call it in a thread.

    Returns:
        The conversation's row; a conversation that isn't a side chat as it is; None if it doesn't exist.
    """
    fork = db.get_fork(conversation_id)
    file_ids: dict[str, str] = {}
    if fork:
        for row in db.get_files_until(fork['parent_id'], user_id, fork['fork_message_id']):
            copy_id = file_store.copy_stored_file(row['file_id'])
            if copy_id:
                file_ids[row['file_id']] = copy_id
    try:
        return db.promote_side_chat(conversation_id, file_ids)
    except Exception:
        for copy_id in file_ids.values():
            file_store.remove_stored_file(copy_id)
        raise
