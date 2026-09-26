"""Load a device from devices.yaml, the profile of the NOS it runs, and its driver.

A profile is a `nos.yaml` or `nos.json` file anywhere under nos_rehearsal/nos/,
usually next to its driver. Both files are validated strictly, so a typo or an
unknown driver stops the server at startup instead of silently weakening a guard.
"""

import os
import re
from pathlib import Path
from typing import Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from nos_rehearsal import settings
from nos_rehearsal.nos import DRIVERS
from nos_rehearsal.nos.base import NosDriver

PROFILE_FILENAMES = ("nos.yaml", "nos.yml", "nos.json")
ENV_REFERENCE = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")

ValueType = Literal["string", "string-list", "number", "boolean"]
ModelT = TypeVar("ModelT", bound=BaseModel)


class ProfileError(RuntimeError):
    """A device or NOS profile file is missing or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Check(_Strict):
    id: str
    description: str


class NosProfile(_Strict):
    id: str
    name: str
    vendor: str
    driver: str
    value_types: list[ValueType]
    leaf_depth: int | None = None
    protected_paths: list[str]
    sample_config: Path | None = None
    checks: list[Check] = []

    @field_validator("driver")
    @classmethod
    def _driver_is_registered(cls, driver: str) -> str:
        if driver not in DRIVERS:
            raise ValueError(f"unknown driver {driver!r}; registered drivers: {sorted(DRIVERS)}")
        return driver

    @field_validator("protected_paths")
    @classmethod
    def _paths_are_pointers(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if not path.startswith("/"):
                raise ValueError(f"protected path {path!r} must be a JSON Pointer starting with '/'")
        return paths


class Device(_Strict):
    name: str
    nos: str
    connection: dict[str, str] = {}


class _DevicesFile(_Strict):
    devices: list[Device]


def load_device(name: str = "") -> tuple[Device, NosProfile]:
    """The device called `name`, or the only device when `name` is empty, with its NOS profile."""
    devices = _parse(settings.DEVICES_PATH, _DevicesFile).devices
    if name:
        device = next((device for device in devices if device.name == name), None)
        if device is None:
            raise ProfileError(f"No device named {name!r} in devices.yaml; known: {[d.name for d in devices]}")
    elif len(devices) == 1:
        device = devices[0]
    else:
        raise ProfileError("devices.yaml must list exactly one device, or set DEVICE in .env to pick one.")

    profiles = load_profiles()
    if device.nos not in profiles:
        raise ProfileError(f"Device {device.name} runs unknown NOS {device.nos!r}; known: {sorted(profiles)}")
    return device, profiles[device.nos]


def load_profiles() -> dict[str, NosProfile]:
    profiles: dict[str, NosProfile] = {}
    paths = sorted(path for filename in PROFILE_FILENAMES for path in settings.NOS_DIR.rglob(filename))
    for path in paths:
        profile = _parse(path, NosProfile)
        if profile.id in profiles:
            raise ProfileError(f"Two profiles use the NOS id {profile.id!r}; the second is {path}")
        profiles[profile.id] = profile
    return profiles


def create_driver(device: Device, profile: NosProfile) -> NosDriver:
    connection = {key: _expand_env(value) for key, value in device.connection.items()}
    try:
        return DRIVERS[profile.driver](**connection)
    except TypeError as error:
        raise ProfileError(
            f"Connection settings of {device.name} do not fit driver {profile.driver}: {error}"
        ) from error


def _parse(path: Path, model: type[ModelT]) -> ModelT:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ProfileError(f"Cannot read {path}: {error}") from error
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise ProfileError(f"Invalid {path.relative_to(settings.REPO_ROOT)}:\n{error}") from error


def _expand_env(value: str) -> str:
    """Replace ${NAME} or ${NAME:-default} with the environment value."""

    def replace(match: re.Match[str]) -> str:
        name, default = match.groups()
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise ProfileError(f"Environment variable {name} is not set (used in devices.yaml)")

    return ENV_REFERENCE.sub(replace, value)
