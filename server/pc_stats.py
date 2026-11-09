"""Reads CPU, GPU and RAM numbers from LibreHardwareMonitor's web server."""

import json
import re
import urllib.request

LHM_URL = "http://localhost:8085/data.json"
TIMEOUT_SECONDS = 1.5

CPU_TEMP = "/intelcpu/0/temperature/10"  # CPU Package
CPU_USAGE = "/intelcpu/0/load/0"  # CPU Total
CPU_CORE_CLOCK = re.compile(r"^/intelcpu/0/clock/[1-8]$")  # /clock/0 is the bus speed, not a core

GPU_TEMP = "/gpu-amd/0/temperature/0"  # GPU Core (not the much hotter GPU Memory sensor)
GPU_USAGE = "/gpu-amd/0/load/0"  # GPU Core
GPU_CLOCK = "/gpu-amd/0/clock/0"  # GPU Core
VRAM_USED = "/gpu-amd/0/smalldata/0"  # GPU Memory Used, in MB
VRAM_TOTAL = "/gpu-amd/0/smalldata/2"  # GPU Memory Total, in MB

RAM_USED = "/ram/data/0"  # "Total Memory", not "Virtual Memory", which includes the page file
RAM_AVAILABLE = "/ram/data/1"

# Goes straight to this PC, even if Windows has a proxy set up.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def parse_number(text):
    """Turns "4692,5 MHz" or "51.0 °C" into a number. This PC's regional settings use commas."""
    match = re.search(r"-?\d+(?:[.,]\d+)?", text or "")
    return float(match.group().replace(",", ".")) if match else None


def _collect_sensors(node, sensors):
    if "SensorId" in node:
        sensors[node["SensorId"]] = parse_number(node.get("Value"))
    for child in node.get("Children", []):
        _collect_sensors(child, sensors)
    return sensors


def _ghz(mhz):
    return round(mhz / 1000, 3) if mhz is not None else None


def _gb(mb):
    return round(mb / 1024, 3)


def summarize(tree):
    """Picks the dashboard's numbers out of LibreHardwareMonitor's sensor tree."""
    sensors = _collect_sensors(tree, {})

    core_clocks = [
        value for sensor_id, value in sensors.items()
        if CPU_CORE_CLOCK.match(sensor_id) and value is not None
    ]
    cpu_clock = sum(core_clocks) / len(core_clocks) if core_clocks else None

    ram_used = sensors.get(RAM_USED)
    ram_available = sensors.get(RAM_AVAILABLE)
    has_ram = ram_used is not None and ram_available is not None

    vram_used = sensors.get(VRAM_USED)
    vram_total = sensors.get(VRAM_TOTAL)
    has_vram = vram_used is not None and vram_total is not None

    return {
        "cpu": {
            "temp": sensors.get(CPU_TEMP),
            "usage": sensors.get(CPU_USAGE),
            "clock": _ghz(cpu_clock),
        },
        "gpu": {
            "temp": sensors.get(GPU_TEMP),
            "usage": sensors.get(GPU_USAGE),
            "clock": _ghz(sensors.get(GPU_CLOCK)),
        },
        "vram": {
            "used": _gb(vram_used) if has_vram else None,
            "total": _gb(vram_total) if has_vram else None,
        },
        "ram": {
            "used": ram_used if has_ram else None,
            "total": ram_used + ram_available if has_ram else None,
        },
    }


def read_pc_stats():
    """Fetches fresh readings. Raises an error if LibreHardwareMonitor can't be reached."""
    with _opener.open(LHM_URL, timeout=TIMEOUT_SECONDS) as response:
        return summarize(json.load(response))
