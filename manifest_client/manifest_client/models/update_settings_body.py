from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.update_settings_body_agent_effort import UpdateSettingsBodyAgentEffort
  from ..models.update_settings_body_agent_model import UpdateSettingsBodyAgentModel
  from ..models.update_settings_body_routing import UpdateSettingsBodyRouting
  from ..models.update_settings_body_top_camera import UpdateSettingsBodyTopCamera
  from ..models.update_settings_body_top_fps import UpdateSettingsBodyTopFps





T = TypeVar("T", bound="UpdateSettingsBody")



@_attrs_define
class UpdateSettingsBody:
    """ 
        Attributes:
            execute_allowed (bool | Unset):
            shield_enabled (bool | Unset):
            min_clearance_mm (float | Unset):
            routing (UpdateSettingsBodyRouting | Unset):
            top_camera (UpdateSettingsBodyTopCamera | Unset):
            top_fps (UpdateSettingsBodyTopFps | Unset):
            agent_model (UpdateSettingsBodyAgentModel | Unset):
            agent_effort (UpdateSettingsBodyAgentEffort | Unset):
     """

    execute_allowed: bool | Unset = UNSET
    shield_enabled: bool | Unset = UNSET
    min_clearance_mm: float | Unset = UNSET
    routing: UpdateSettingsBodyRouting | Unset = UNSET
    top_camera: UpdateSettingsBodyTopCamera | Unset = UNSET
    top_fps: UpdateSettingsBodyTopFps | Unset = UNSET
    agent_model: UpdateSettingsBodyAgentModel | Unset = UNSET
    agent_effort: UpdateSettingsBodyAgentEffort | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.update_settings_body_agent_effort import UpdateSettingsBodyAgentEffort # noqa: PLC0415
        from ..models.update_settings_body_agent_model import UpdateSettingsBodyAgentModel # noqa: PLC0415
        from ..models.update_settings_body_routing import UpdateSettingsBodyRouting # noqa: PLC0415
        from ..models.update_settings_body_top_camera import UpdateSettingsBodyTopCamera # noqa: PLC0415
        from ..models.update_settings_body_top_fps import UpdateSettingsBodyTopFps # noqa: PLC0415
        execute_allowed = self.execute_allowed

        shield_enabled = self.shield_enabled

        min_clearance_mm = self.min_clearance_mm

        routing: dict[str, Any] | Unset = UNSET
        if not isinstance(self.routing, Unset):
            routing = self.routing.to_dict()

        top_camera: dict[str, Any] | Unset = UNSET
        if not isinstance(self.top_camera, Unset):
            top_camera = self.top_camera.to_dict()

        top_fps: dict[str, Any] | Unset = UNSET
        if not isinstance(self.top_fps, Unset):
            top_fps = self.top_fps.to_dict()

        agent_model: dict[str, Any] | Unset = UNSET
        if not isinstance(self.agent_model, Unset):
            agent_model = self.agent_model.to_dict()

        agent_effort: dict[str, Any] | Unset = UNSET
        if not isinstance(self.agent_effort, Unset):
            agent_effort = self.agent_effort.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if execute_allowed is not UNSET:
            field_dict["execute_allowed"] = execute_allowed
        if shield_enabled is not UNSET:
            field_dict["shield_enabled"] = shield_enabled
        if min_clearance_mm is not UNSET:
            field_dict["min_clearance_mm"] = min_clearance_mm
        if routing is not UNSET:
            field_dict["routing"] = routing
        if top_camera is not UNSET:
            field_dict["top_camera"] = top_camera
        if top_fps is not UNSET:
            field_dict["top_fps"] = top_fps
        if agent_model is not UNSET:
            field_dict["agent_model"] = agent_model
        if agent_effort is not UNSET:
            field_dict["agent_effort"] = agent_effort

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.update_settings_body_agent_effort import UpdateSettingsBodyAgentEffort # noqa: PLC0415
        from ..models.update_settings_body_agent_model import UpdateSettingsBodyAgentModel # noqa: PLC0415
        from ..models.update_settings_body_routing import UpdateSettingsBodyRouting # noqa: PLC0415
        from ..models.update_settings_body_top_camera import UpdateSettingsBodyTopCamera # noqa: PLC0415
        from ..models.update_settings_body_top_fps import UpdateSettingsBodyTopFps # noqa: PLC0415
        d = dict(src_dict)
        execute_allowed = d.pop("execute_allowed", UNSET)

        shield_enabled = d.pop("shield_enabled", UNSET)

        min_clearance_mm = d.pop("min_clearance_mm", UNSET)

        _routing = d.pop("routing", UNSET)
        routing: UpdateSettingsBodyRouting | Unset
        if isinstance(_routing,  Unset):
            routing = UNSET
        else:
            routing = UpdateSettingsBodyRouting.from_dict(_routing)




        _top_camera = d.pop("top_camera", UNSET)
        top_camera: UpdateSettingsBodyTopCamera | Unset
        if isinstance(_top_camera,  Unset):
            top_camera = UNSET
        else:
            top_camera = UpdateSettingsBodyTopCamera.from_dict(_top_camera)




        _top_fps = d.pop("top_fps", UNSET)
        top_fps: UpdateSettingsBodyTopFps | Unset
        if isinstance(_top_fps,  Unset):
            top_fps = UNSET
        else:
            top_fps = UpdateSettingsBodyTopFps.from_dict(_top_fps)




        _agent_model = d.pop("agent_model", UNSET)
        agent_model: UpdateSettingsBodyAgentModel | Unset
        if isinstance(_agent_model,  Unset):
            agent_model = UNSET
        else:
            agent_model = UpdateSettingsBodyAgentModel.from_dict(_agent_model)




        _agent_effort = d.pop("agent_effort", UNSET)
        agent_effort: UpdateSettingsBodyAgentEffort | Unset
        if isinstance(_agent_effort,  Unset):
            agent_effort = UNSET
        else:
            agent_effort = UpdateSettingsBodyAgentEffort.from_dict(_agent_effort)




        update_settings_body = cls(
            execute_allowed=execute_allowed,
            shield_enabled=shield_enabled,
            min_clearance_mm=min_clearance_mm,
            routing=routing,
            top_camera=top_camera,
            top_fps=top_fps,
            agent_model=agent_model,
            agent_effort=agent_effort,
        )


        update_settings_body.additional_properties = d
        return update_settings_body

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
