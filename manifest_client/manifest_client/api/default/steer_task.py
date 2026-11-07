from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx2

from ...client import Client
from ...types import Response, UNSET
from ... import errors

from ...models.error_response import ErrorResponse
from ...models.json_object import JsonObject
from ...models.steer_task_body import SteerTaskBody
from typing import cast



def _get_kwargs(
    id: str,
    *,
    body: SteerTaskBody,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/tasks/{id}/messages".format(id=quote(str(id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: Client, response: httpx2.Response) -> ErrorResponse | JsonObject:
    if response.status_code == 200:
        response_200 = JsonObject.from_dict(response.json())



        return response_200

    if response.status_code == 201:
        response_201 = JsonObject.from_dict(response.json())



        return response_201

    if response.status_code == 202:
        response_202 = JsonObject.from_dict(response.json())



        return response_202

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
    id: str,
    *,
    client: Client,
    body: SteerTaskBody,

) -> Response[ErrorResponse | JsonObject]:
    """ Steer a running prompt task

     Append message and unique message_id to the current agent turn. Does not start a second task or
    change execution permissions. Inspect messages status in GET task; sent means accepted, not physical
    completion.

    Args:
        id (str):
        body (SteerTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | JsonObject]
     """


    kwargs = _get_kwargs(
        id=id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    id: str,
    *,
    client: Client,
    body: SteerTaskBody,

) -> ErrorResponse | JsonObject | None:
    """ Steer a running prompt task

     Append message and unique message_id to the current agent turn. Does not start a second task or
    change execution permissions. Inspect messages status in GET task; sent means accepted, not physical
    completion.

    Args:
        id (str):
        body (SteerTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | JsonObject
     """


    return sync_detailed(
        id=id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    id: str,
    *,
    client: Client,
    body: SteerTaskBody,

) -> Response[ErrorResponse | JsonObject]:
    """ Steer a running prompt task

     Append message and unique message_id to the current agent turn. Does not start a second task or
    change execution permissions. Inspect messages status in GET task; sent means accepted, not physical
    completion.

    Args:
        id (str):
        body (SteerTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | JsonObject]
     """


    kwargs = _get_kwargs(
        id=id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    id: str,
    *,
    client: Client,
    body: SteerTaskBody,

) -> ErrorResponse | JsonObject | None:
    """ Steer a running prompt task

     Append message and unique message_id to the current agent turn. Does not start a second task or
    change execution permissions. Inspect messages status in GET task; sent means accepted, not physical
    completion.

    Args:
        id (str):
        body (SteerTaskBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | JsonObject
     """


    return (await asyncio_detailed(
        id=id,
client=client,
body=body,

    )).parsed
