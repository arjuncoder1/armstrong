from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.replace_routine_body_nodes_item import ReplaceRoutineBodyNodesItem
  from ..models.replace_routine_body_recoveries_item import ReplaceRoutineBodyRecoveriesItem





T = TypeVar("T", bound="ReplaceRoutineBody")



@_attrs_define
class ReplaceRoutineBody:
    """ 
        Attributes:
            nodes (list[ReplaceRoutineBodyNodesItem] | Unset):
            recoveries (list[ReplaceRoutineBodyRecoveriesItem] | Unset):
     """

    nodes: list[ReplaceRoutineBodyNodesItem] | Unset = UNSET
    recoveries: list[ReplaceRoutineBodyRecoveriesItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.replace_routine_body_nodes_item import ReplaceRoutineBodyNodesItem # noqa: PLC0415
        from ..models.replace_routine_body_recoveries_item import ReplaceRoutineBodyRecoveriesItem # noqa: PLC0415
        nodes: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.nodes, Unset):
            nodes = []
            for nodes_item_data in self.nodes:
                nodes_item = nodes_item_data.to_dict()
                nodes.append(nodes_item)



        recoveries: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.recoveries, Unset):
            recoveries = []
            for recoveries_item_data in self.recoveries:
                recoveries_item = recoveries_item_data.to_dict()
                recoveries.append(recoveries_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if nodes is not UNSET:
            field_dict["nodes"] = nodes
        if recoveries is not UNSET:
            field_dict["recoveries"] = recoveries

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.replace_routine_body_nodes_item import ReplaceRoutineBodyNodesItem # noqa: PLC0415
        from ..models.replace_routine_body_recoveries_item import ReplaceRoutineBodyRecoveriesItem # noqa: PLC0415
        d = dict(src_dict)
        _nodes = d.pop("nodes", UNSET)
        nodes: list[ReplaceRoutineBodyNodesItem] | Unset = UNSET
        if _nodes is not UNSET:
            nodes = []
            for nodes_item_data in _nodes:
                nodes_item = ReplaceRoutineBodyNodesItem.from_dict(nodes_item_data)



                nodes.append(nodes_item)


        _recoveries = d.pop("recoveries", UNSET)
        recoveries: list[ReplaceRoutineBodyRecoveriesItem] | Unset = UNSET
        if _recoveries is not UNSET:
            recoveries = []
            for recoveries_item_data in _recoveries:
                recoveries_item = ReplaceRoutineBodyRecoveriesItem.from_dict(recoveries_item_data)



                recoveries.append(recoveries_item)


        replace_routine_body = cls(
            nodes=nodes,
            recoveries=recoveries,
        )


        replace_routine_body.additional_properties = d
        return replace_routine_body

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
