from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class DeviceRole(StrEnum):
    ROUTER = "router"
    MANAGED_SWITCH = "managed_switch"
    UNMANAGED_GROUP = "unmanaged_group"
    AP = "ap"
    NVR = "nvr"
    CAMERA = "camera"
    ENDPOINT = "endpoint"


class PortStatus(StrEnum):
    UP = "up"
    DOWN = "down"


class PortSpeed(StrEnum):
    M100 = "100M"
    G1 = "1G"
    G10 = "10G"


class LinkType(StrEnum):
    TRUNK = "trunk"
    ACCESS = "access"
    UNMANAGED = "unmanaged"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    subnet: Mapped[str] = mapped_column(String(64), nullable=False)
    vpn_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="online", nullable=False)


class NetworkDevice(Base):
    __tablename__ = "network_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=DeviceRole.ENDPOINT.value, nullable=False)
    # shortcut: plaintext JSON in DB, encrypt with Fernet before storing real production SNMP/API secrets
    credentials_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    cpu_usage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ram_usage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    uptime: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DevicePort(Base):
    __tablename__ = "device_ports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("network_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    port_index: Mapped[int] = mapped_column(Integer, nullable=False)
    port_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PortStatus.UP.value, nullable=False)
    speed: Mapped[str] = mapped_column(String(16), default=PortSpeed.G1.value, nullable=False)
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_uplink: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TopologyEdge(Base):
    __tablename__ = "topology_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    source_device_id: Mapped[int] = mapped_column(ForeignKey("network_devices.id", ondelete="CASCADE"), nullable=False)
    source_port: Mapped[int] = mapped_column(Integer, nullable=False)
    target_device_id: Mapped[int] = mapped_column(ForeignKey("network_devices.id", ondelete="CASCADE"), nullable=False)
    target_port: Mapped[int] = mapped_column(Integer, nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), default=LinkType.ACCESS.value, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("network_devices.id", ondelete="SET NULL"), nullable=True)
    port_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default=AlertSeverity.INFO.value, nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
