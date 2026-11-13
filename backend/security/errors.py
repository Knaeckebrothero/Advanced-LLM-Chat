"""
What clients are told when something fails.

The log always has the whole error. A client gets it only where it helps and can't
hurt: the text of a provider's or a database's error can name internal addresses,
parts of keys, or the statement that failed.
"""
from typing import Optional


def answer_error(error: Exception, user: Optional[dict]) -> str:
    """
    What a client is told when a model could not answer.

    Signed-in users get the error's text: it usually says what to fix (an unknown model,
    a missing key, the provider's message). Guests get a general sentence, with the
    provider's HTTP status when there is one.

    :param error: The error of the answer (a provider's SDK error, a tool's, ...).
    :param user: The current user (get_current_user).
    :return: The text for the client.
    """
    if user and not user.get("is_guest"):
        return str(error) or type(error).__name__
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return f"The model could not answer (its provider returned an error {status_code}). Please try again later."
    return "The model could not answer. Please try again later."
