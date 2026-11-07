from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx2

from ...client import Client
from ...types import Response, UNSET
from ... import errors

from ...models.error_response import ErrorResponse
from ...models.json_object import JsonObject
from ...models.start_task_body import StartTaskBody
from typing import cast



def _get_kwargs(
    *,
    body: StartTaskBody,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/tasks",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: Client, response: httpx2.Response) -> ErrorResponse | JsonObject:
    if response.status_code == 200:
        response_200 = JsonObject.from_dict(response.json())



        return response_200

    response_default = ErrorResponse.from_dict(response.json())



    return response_default



def _build_response(*, client: Client, response: httpx2.Response) -> Response[ErrorResponse | JsonObject]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Client,
    body: StartTaskBody,

) -> Response[ErrorResponse | JsonObject]:
    """ Start a task

     A prompt for the agent, or a routine from the decision graph. 202 with the task record.

    Args:
        body (StartTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | JsonObject]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: Client,
    body: StartTaskBody,

) -> ErrorResponse | JsonObject | None:
    """ Start a task

     A prompt for the agent, or a routine from the decision graph. 202 with the task record.

    Args:
        body (StartTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | JsonObject
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: Client,
    body: StartTaskBody,

) -> Response[ErrorResponse | JsonObject]:
    """ Start a task

     A prompt for the agent, or a routine from the decision graph. 202 with the task record.

    Args:
        body (StartTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | JsonObject]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: Client,
    body: StartTaskBody,

) -> ErrorResponse | JsonObject | None:
    """ Start a task

     A prompt for the agent, or a routine from the decision graph. 202 with the task record.

    Args:
        body (StartTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | JsonObject
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
