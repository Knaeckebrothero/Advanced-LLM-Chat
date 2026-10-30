"""
Hash utility functions.
"""
import hashlib
import logging
import sqlite3
from typing import List

log = logging.getLogger(__name__)


def generate_hash(messages: List[sqlite3.Row]) -> int:
    """
    Generate a hash value based on the content of given messages. The hash value is
    calculated using the first and last characters of each message's content, as well
    as its length. A string representation of these hash components is also created
    and logged.

    :param messages: List of SQLite rows, where each row represents a message and
                     contains a 'content' field.
    :type messages: List[sqlite3.Row]
    :return: An integer hash value computed from the messages' content.
    :rtype: int
    """
    if not messages:
        log.debug("No messages provided for hash generation, returning 0")
        return 0

    hash_value = 0
    hash_chars = ""

    for message in messages:
        content = message['content']
        if not content:
            continue

        hash_value += ord(content[0])
        hash_value += ord(content[-1])
        hash_value *= len(content)
        hash_chars += content[0] + content[-1] + str(len(content))

    hash_value %= (2 ** 32)
    log.debug(f"Generated hashsum: {hash_value} (string rep: {hash_chars})")
    return hash_value


def generate_sha256_hash(content: str) -> str:
    """
    Generates a SHA-256 hash for the given content. The function encodes the
    provided string content using UTF-8 before calculating the hash and returns
    the hexdigest representation of the computed SHA-256 hash value.

    :param content: The input string to be hashed.
    :type content: str
    :return: The SHA-256 hash of the input string in hexadecimal format.
    :rtype: str
    """
    hash_result = hashlib.sha256(content.encode('utf-8')).hexdigest()
    log.debug(f"Generated SHA-256 hash: {hash_result[:16]}... (content length: {len(content)})")
    return hash_result
