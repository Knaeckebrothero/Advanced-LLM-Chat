"""
Authentication-related models.
"""
from pydantic import BaseModel


class MockLoginRequest(BaseModel):
    """
    Represents a mock login request.

    This class is utilized for creating a mock representation of a login
    request. It can be extended or used in testing environments to simulate
    user login with essential credentials or tokenized data.

    :ivar email: The email address of the user attempting to login.
    :type email: str
    """
    email: str
    # In real implementation, this might include IDP tokens, SAML response, etc.


class LoginResponse(BaseModel):
    """
    Represents the response after a successful login attempt.

    This class models the structure of a typical login response, providing
    details about the user and an accompanying message. The session itself is
    only in the HttpOnly cookie, never in the body, where scripts could read it.

    :ivar user: A dictionary containing the authenticated user's details.
    :type user: dict
    :ivar message: A message conveying information about the login operation.
    :type message: str
    """
    user: dict
    message: str
