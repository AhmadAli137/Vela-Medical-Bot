"""Loopback-only native viewer attachment to the browser's API simulation."""
from __future__ import annotations

import copy
import ipaddress
import json
import math
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, ProxyHandler, Request, build_opener

import mujoco
import numpy as np


def validate_connection_url(value):
    parsed = urlsplit(value)
    try:
        loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
        port = parsed.port
    except ValueError:
        loopback, port = False, None
    if (parsed.scheme != "http" or not loopback or parsed.username is not None
            or parsed.password is not None or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or port == 0):
        raise ValueError("Viewer connection must be an HTTP loopback IP origin, without credentials or a path")
    return value.rstrip("/")


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise HTTPError(request.full_url, code, "Viewer connections do not follow redirects", headers, fp)


class ReferenceViewerClient:
    def __init__(self, url, timeout=5.):
        self.url = validate_connection_url(url)
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()), _NoRedirects())
        self._request("/api/session", {"role": "staff"})

    def _request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.url + path, data=body, headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Viewer response exceeds the bounded frame size")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Viewer response must be an object")
        return result

    def frame(self):
        return self._request("/api/sim/reference/frame")

    def command(self, command):
        return self._request("/api/sim/reference/control", {"command": command})


def apply_reference_frame(model, data, metadata, frame):
    """Validate a coherent snapshot completely, then run FK without stepping.

    The API owns time and control. This native consumer never integrates a
    second simulation clock or modifies transported object poses on its own.
    """
    if not isinstance(frame, dict) or not isinstance(frame.get("state"), dict):
        raise ValueError("Malformed reference frame")
    state = frame["state"]
    if state.get("model_hash") != metadata["model_hash"]:
        raise ValueError("Native visuals and API physics model hashes differ; rebuild/restart the matching scene")
    clock = state.get("simulation_time")
    if isinstance(clock, bool) or not isinstance(clock, (int, float)) or not math.isfinite(clock) or clock < 0:
        raise ValueError("Malformed simulation clock")
    arrays = {}
    for name, shape in (("qpos", (model.nq,)), ("qvel", (model.nv,)), ("ctrl", (model.nu,)),
                        ("mocap_pos", (model.nmocap, 3)), ("mocap_quat", (model.nmocap, 4))):
        try:
            value = np.asarray(frame[name], dtype=float)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Malformed reference frame {name}") from error
        if value.shape != shape or not np.isfinite(value).all():
            raise ValueError(f"Malformed reference frame {name}")
        arrays[name] = value
    if not np.allclose(np.linalg.norm(arrays["mocap_quat"], axis=1), 1., atol=1e-5):
        raise ValueError("Malformed mocap quaternion")
    for joint in range(model.njnt):
        if model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_FREE:
            start = model.jnt_qposadr[joint] + 3
            if not np.isclose(np.linalg.norm(arrays["qpos"][start:start+4]), 1., atol=1e-5):
                raise ValueError("Malformed free-body quaternion")
    for name, value in arrays.items():
        getattr(data, name)[:] = value
    data.time = clock
    mujoco.mj_forward(model, data)
    return copy.deepcopy(state)
