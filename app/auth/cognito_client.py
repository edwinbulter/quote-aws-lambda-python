"""Thin wrapper over boto3 cognito-idp Admin* calls.

Replaces the old User/UserRole SQLAlchemy tables: Cognito is now the
identity store (username/email/password) and the USER/ADMIN group
membership is the roles store. See doc/auth-flow.md for the full
route -> Cognito API mapping this implements.
"""

from dataclasses import dataclass
from datetime import datetime

from botocore.exceptions import ClientError

from app.models import UserSummary


class UsernameExistsError(Exception):
    pass


class EmailExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


@dataclass
class AuthTokens:
    id_token: str
    access_token: str
    refresh_token: str | None
    expires_in: int


def _client():
    from app.aws_clients import cognito_idp_client

    return cognito_idp_client()


def _pool_id() -> str:
    from flask import current_app

    return current_app.config["COGNITO_USER_POOL_ID"]


def _client_id() -> str:
    from flask import current_app

    return current_app.config["COGNITO_APP_CLIENT_ID"]


def register(username: str, email: str, password: str) -> None:
    client = _client()
    try:
        client.admin_create_user(
            UserPoolId=_pool_id(),
            Username=username,
            UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
            MessageAction="SUPPRESS",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "UsernameExistsException":
            raise UsernameExistsError(username) from exc
        if code == "AliasExistsException":
            raise EmailExistsError(email) from exc
        raise

    client.admin_set_user_password(UserPoolId=_pool_id(), Username=username, Password=password, Permanent=True)
    client.admin_add_user_to_group(UserPoolId=_pool_id(), Username=username, GroupName="USER")


def authenticate(identifier: str, password: str) -> AuthTokens:
    client = _client()
    try:
        resp = client.admin_initiate_auth(
            UserPoolId=_pool_id(),
            ClientId=_client_id(),
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": identifier, "PASSWORD": password},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            raise InvalidCredentialsError(identifier) from exc
        raise

    result = resp["AuthenticationResult"]
    return AuthTokens(
        id_token=result["IdToken"],
        access_token=result["AccessToken"],
        refresh_token=result.get("RefreshToken"),
        expires_in=result["ExpiresIn"],
    )


def refresh(refresh_token: str) -> AuthTokens:
    client = _client()
    try:
        resp = client.admin_initiate_auth(
            UserPoolId=_pool_id(),
            ClientId=_client_id(),
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": refresh_token},
        )
    except ClientError as exc:
        raise InvalidCredentialsError("refresh_token") from exc

    result = resp["AuthenticationResult"]
    return AuthTokens(
        id_token=result["IdToken"],
        access_token=result["AccessToken"],
        refresh_token=refresh_token,
        expires_in=result["ExpiresIn"],
    )


def change_password(username: str, current_password: str, new_password: str) -> None:
    # Verify the current password the same way login does, since there's
    # no direct "verify password" admin API.
    authenticate(username, current_password)
    _client().admin_set_user_password(
        UserPoolId=_pool_id(), Username=username, Password=new_password, Permanent=True
    )


def delete_user(username: str) -> None:
    try:
        _client().admin_delete_user(UserPoolId=_pool_id(), Username=username)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
            raise UserNotFoundError(username) from exc
        raise


def user_exists(username: str) -> bool:
    try:
        _client().admin_get_user(UserPoolId=_pool_id(), Username=username)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
            return False
        raise


def disable_user(username: str) -> None:
    _client().admin_disable_user(UserPoolId=_pool_id(), Username=username)


def enable_user(username: str) -> None:
    _client().admin_enable_user(UserPoolId=_pool_id(), Username=username)


def list_groups_for_user(username: str) -> set[str]:
    client = _client()
    groups: set[str] = set()
    kwargs = {"UserPoolId": _pool_id(), "Username": username}
    while True:
        resp = client.admin_list_groups_for_user(**kwargs)
        groups.update(g["GroupName"] for g in resp.get("Groups", []))
        token = resp.get("NextToken")
        if not token:
            break
        kwargs["NextToken"] = token
    return groups


def add_user_to_group(username: str, group: str) -> bool:
    """Idempotent grant. Returns True if the user wasn't already a member."""
    if group in list_groups_for_user(username):
        return False
    _client().admin_add_user_to_group(UserPoolId=_pool_id(), Username=username, GroupName=group)
    return True


def remove_user_from_group(username: str, group: str) -> bool:
    """Idempotent revoke. Returns True if the user was actually a member."""
    if group not in list_groups_for_user(username):
        return False
    _client().admin_remove_user_from_group(UserPoolId=_pool_id(), Username=username, GroupName=group)
    return True


def _attr(attrs: list[dict], name: str) -> str | None:
    for a in attrs:
        if a["Name"] == name:
            return a["Value"]
    return None


def list_users_in_group(group: str) -> set[str]:
    client = _client()
    usernames: set[str] = set()
    kwargs = {"UserPoolId": _pool_id(), "GroupName": group}
    while True:
        resp = client.list_users_in_group(**kwargs)
        usernames.update(u["Username"] for u in resp.get("Users", []))
        token = resp.get("NextToken")
        if not token:
            break
        kwargs["NextToken"] = token
    return usernames


def list_users() -> list[UserSummary]:
    client = _client()
    user_roles: dict[str, set[str]] = {}
    for group in ("USER", "ADMIN"):
        for username in list_users_in_group(group):
            user_roles.setdefault(username, set()).add(group)

    summaries: list[UserSummary] = []
    kwargs = {"UserPoolId": _pool_id()}
    while True:
        resp = client.list_users(**kwargs)
        for u in resp.get("Users", []):
            username = u["Username"]
            summaries.append(
                UserSummary(
                    username=username,
                    email=_attr(u.get("Attributes", []), "email") or "",
                    roles=sorted(user_roles.get(username, set())),
                    is_active=u.get("Enabled", True),
                    created_at=u.get("UserCreateDate").replace(tzinfo=None)
                    if isinstance(u.get("UserCreateDate"), datetime)
                    else None,
                    updated_at=u.get("UserLastModifiedDate").replace(tzinfo=None)
                    if isinstance(u.get("UserLastModifiedDate"), datetime)
                    else None,
                )
            )
        token = resp.get("PaginationToken")
        if not token:
            break
        kwargs["PaginationToken"] = token
    summaries.sort(key=lambda s: s.username)
    return summaries
