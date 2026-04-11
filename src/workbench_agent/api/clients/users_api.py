"""
Users domain client: lookup and ``get_user_permissions_list`` (Workbench
``group: users``).

**Errors:** The API uses ``status`` ``"1"`` / ``"0"``. The default
``BaseAPI._send_request`` raises ``ApiError`` with message
``API Error: <error>`` and the full JSON in ``details`` when ``status`` is
``"0"``, before control returns to these methods. If ``_send_request`` is
mocked to return a failure body, methods here raise ``Failed to …: <error>``
instead (same ``details``).
"""

import logging
from typing import Any, Dict, List, NoReturn, Optional

from workbench_agent.api.exceptions import ApiError

logger = logging.getLogger("workbench-agent")

_GROUP = "users"


def _raise_users_api_error(response: dict, prefix: str) -> NoReturn:
    err = response.get("error", f"Unexpected response: {response}")
    raise ApiError(f"{prefix}: {err}", details=response)


def _normalize_permissions_list_data(data: Any, *, operation: str) -> List[Dict[str, Any]]:
    """Normalize list / map / single-object ``data`` to a list of dicts."""
    if data is None:
        logger.warning(
            "users.%s: success but ``data`` is null or absent", operation
        )
        return []
    if isinstance(data, list):
        if not all(isinstance(item, dict) for item in data):
            logger.warning(
                "users.%s: list contains non-dict elements: %s",
                operation,
                data,
            )
            return [x for x in data if isinstance(x, dict)]
        return data
    if isinstance(data, dict):
        if not data:
            return []
        if all(isinstance(v, dict) for v in data.values()):
            return list(data.values())
        return [data]
    logger.warning(
        "users.%s: unexpected 'data' type: %s", operation, type(data)
    )
    return []


class UsersClient:
    """User lookup and permission listing (``group: users``)."""

    def __init__(self, base_api):
        """
        Args:
            base_api: BaseAPI instance for HTTP requests.
        """
        self._api = base_api
        logger.debug("UsersClient initialized")

    def get_information(self, searched_username: str) -> Dict[str, Any]:
        """
        Look up a user by username.

        Success ``data`` includes id, username, name, surename (API spelling),
        avatar, and when permitted email, language, phone, mobile,
        is_deleted (boolean). Without USERS_EDIT_ANY, email, phone, mobile,
        is_deleted, and language may be omitted.

        Raises:
            ApiError: Unknown user — ``RequestData.Base.issues_while_parsing_request``
                with ``data`` listing e.g. ``UserTrait.username_not_valid``.
        """
        logger.debug("users.get_information: %s", searched_username)
        response = self._api._send_request(
            {
                "group": _GROUP,
                "action": "get_information",
                "data": {"searched_username": searched_username},
            }
        )

        if response.get("status") == "1" and "data" in response:
            return response["data"]

        _raise_users_api_error(
            response,
            f"Failed to get information for user '{searched_username}'",
        )

    def get_user_permissions_list(
        self,
        *,
        searched_username: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Permissions for a user. Pass exactly one of ``searched_username`` or
        ``user_id``.

        Success ``data`` is usually an array of objects (``id``, ``group``,
        ``code``, ``name``, ``description``, ``created``, ``updated``,
        ``role_id``, ``status``); ``status`` and ``role_id`` may be null.

        Raises:
            ApiError: Unknown user — ``User not found``, ``data`` null.
            ValueError: Neither or both identifiers provided.
        """
        has_username = searched_username is not None
        has_user_id = user_id is not None
        if has_username == has_user_id:
            raise ValueError(
                "Provide exactly one of searched_username or user_id."
            )
        action = "get_user_permissions_list"
        if searched_username is not None:
            logger.debug("users.%s: username=%s", action, searched_username)
            data = {"searched_username": searched_username}
        else:
            logger.debug("users.%s: user_id=%s", action, user_id)
            data = {"user_id": user_id}

        response = self._api._send_request(
            {"group": _GROUP, "action": action, "data": data}
        )

        if response.get("status") == "1":
            items = _normalize_permissions_list_data(
                response.get("data"), operation=action
            )
            logger.debug("users.%s: %d item(s)", action, len(items))
            return items

        _raise_users_api_error(response, "Failed to list user permissions")
