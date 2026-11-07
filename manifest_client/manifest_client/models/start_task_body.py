from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.start_task_body_effort import StartTaskBodyEffort
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.start_task_body_params import StartTaskBodyParams





T = TypeVar("T", bound="StartTaskBody")



@_attrs_define
class StartTaskBody:
    """ 
        Attributes:
            prompt (str | Unset): free text for the agent (Sol's model with the robot tools)
            routine (str | Unset): a routine id from GET /v1/routines
            params (StartTaskBodyParams | Unset): routine parameters: slot, slots, max_cycles, entry, replay_run (shadow)
            execute (bool | Unset): false: observation-only / shadow replay. true: the arms move (needs
                settings.execute_allowed) Default: False.
            effort (StartTaskBodyEffort | Unset): reasoning depth; default settings.agent_effort
            model (str | Unset): Codex model id; default settings.agent_model
            skill_id (str | Unset): Explicit saved Teach skill; validated before starting a task
     """

    prompt: str | Unset = UNSET
    routine: str | Unset = UNSET
    params: StartTaskBodyParams | Unset = UNSET
    execute: bool | Unset = False
    effort: StartTaskBodyEffort | Unset = UNSET
    model: str | Unset = UNSET
    skill_id: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.start_task_body_params import StartTaskBodyParams # noqa: PLC0415
        prompt = self.prompt

        routine = self.routine

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        execute = self.execute

        effort: str | Unset = UNSET
        if not isinstance(self.effort, Unset):
            effort = self.effort.value


        model = self.model

        skill_id = self.skill_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if prompt is not UNSET:
            field_dict["prompt"] = prompt
        if routine is not UNSET:
            field_dict["routine"] = routine
        if params is not UNSET:
            field_dict["params"] = params
        if execute is not UNSET:
            field_dict["execute"] = execute
        if effort is not UNSET:
            field_dict["effort"] = effort
        if model is not UNSET:
            field_dict["model"] = model
        if skill_id is not UNSET:
            field_dict["skill_id"] = skill_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.start_task_body_params import StartTaskBodyParams # noqa: PLC0415
        d = dict(src_dict)
        prompt = d.pop("prompt", UNSET)

        routine = d.pop("routine", UNSET)

        _params = d.pop("params", UNSET)
        params: StartTaskBodyParams | Unset
        if isinstance(_params,  Unset):
            params = UNSET
        else:
            params = StartTaskBodyParams.from_dict(_params)




        execute = d.pop("execute", UNSET)

        _effort = d.pop("effort", UNSET)
        effort: StartTaskBodyEffort | Unset
        if isinstance(_effort,  Unset):
            effort = UNSET
        else:
            effort = StartTaskBodyEffort(_effort)




        model = d.pop("model", UNSET)

        skill_id = d.pop("skill_id", UNSET)

        start_task_body = cls(
            prompt=prompt,
            routine=routine,
            params=params,
            execute=execute,
            effort=effort,
            model=model,
            skill_id=skill_id,
        )


        start_task_body.additional_properties = d
        return start_task_body

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
