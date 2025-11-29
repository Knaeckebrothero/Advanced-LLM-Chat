"""
Authentication-related models.
"""
from typing import Optional
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


class GuestLoginRequest(BaseModel):
    """
    Represents a request for guest login.

    This class is used to encapsulate the data required for a guest login request,
    including any relevant details necessary for processing the request. Guests
    are typically users who do not have registered accounts but need limited access
    to the system or application.

    :ivar ip_address: IP address of the guest initiating the login request.
    :type ip_address: str
    """
    ip_address: str


class LoginResponse(BaseModel):
    """
    Represents the response after a successful login attempt.

    This class models the structure of a typical login response, providing
    details about the user, an accompanying message, and an optional token
    for authentication. It serves as the return type for login operations
    and ensures standardized output.

    :ivar user: A dictionary containing the authenticated user's details.
    :type user: dict
    :ivar message: A message conveying information about the login operation.
    :type message: str
    :ivar token: An optional token for authenticating subsequent requests.
    :type token: Optional[str]
    """
    user: dict
    message: str
    token: Optional[str] = None
