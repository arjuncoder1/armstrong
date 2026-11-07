from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx2

from ...client import Client
from ...types import Response, UNSET
from ... import errors

from ...models.error_response import ErrorResponse
from ...models.json_object import JsonObject
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/models",
    }


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

) -> Response[ErrorResponse | JsonObject]:
    """ Served models

     Dream-wire listing: id, embodiment, cameras, backend

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | JsonObject]
     """


    kwargs = _get_kwargs(
        
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: Client,

) -> ErrorResponse | JsonObject | None:
    """ Served models

     Dream-wire listing: id, embodiment, cameras, backend

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | JsonObject
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: Client,

) -> Response[ErrorResponse | JsonObject]:
    """ Served models

     Dream-wire listing: id, embodiment, cameras, backend

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | JsonObject]
     """


    kwargs = _get_kwargs(
        
    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: Client,

) -> ErrorResponse | JsonObject | None:
    """ Served models

     Dream-wire listing: id, embodiment, cameras, backend

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx2.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | JsonObject
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
