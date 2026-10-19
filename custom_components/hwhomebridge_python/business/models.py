from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProductSpec:
    prod_id: str
    sub_prod_id: str
    device_type: str
    manufacturer: str
    model: str
    device_name: str
    protocol_type: int
    setup_type: int


@dataclass(frozen=True)
class ServiceRef:
    service_type: str
    service_id: str


@dataclass(frozen=True)
class BindingField:
    service_id: str
    field_name: str
    entity_id: str | None
    source: str
    attribute: str | None = None
    component: str | None = None
    value: Any | None = None
    ha_to_huawei: dict[str, Any] = field(default_factory=dict)
    huawei_to_ha: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChildPlan:
    key: str
    product: ProductSpec
    friendly_name: str | None
    room: str | None
    services: tuple[ServiceRef, ...]
    bindings: tuple[BindingField, ...]
    on_product_change: str = "block"


@dataclass(frozen=True)
class GatewayPlan:
    gateway_serial: str | None
    children: tuple[ChildPlan, ...]
