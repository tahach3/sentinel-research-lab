#!/usr/bin/env python3
"""Offline mechanical checks for n8n→host worker Docker Desktop hostname mapping."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.yml"


def _n8n_service_block(text: str) -> str:
    match = re.search(
        r"(?ms)^  n8n:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|^networks:|^volumes:|\Z)",
        text,
    )
    if not match:
        raise AssertionError("n8n service block not found in docker-compose.yml")
    return match.group(0)


def _worker_service_block(text: str) -> str:
    match = re.search(
        r"(?ms)^  srl-worker:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|^networks:|^volumes:|^secrets:|\Z)",
        text,
    )
    if not match:
        raise AssertionError("srl-worker service block not found in docker-compose.yml")
    return match.group(0)


class TestN8nNetworkTopology(unittest.TestCase):
    def setUp(self) -> None:
        self.text = COMPOSE_PATH.read_text(encoding="utf-8")
        self.n8n = _n8n_service_block(self.text)
        self.worker = _worker_service_block(self.text)

    def test_host_gateway_mapping_present(self) -> None:
        self.assertIn("extra_hosts:", self.n8n)
        self.assertRegex(
            self.n8n,
            r'extra_hosts:\n\s+-\s+"host\.docker\.internal:host-gateway"',
        )

    def test_n8n_loopback_publish_binding(self) -> None:
        self.assertIn('"127.0.0.1:5678:5678"', self.n8n)

    def test_srl_worker_uses_network_mode_service_n8n(self) -> None:
        self.assertRegex(self.worker, r'(?m)^\s*network_mode:\s*"service:n8n"\s*$')
        self.assertNotRegex(self.worker, r"(?m)^\s*ports:")
        self.assertNotRegex(self.worker, r"(?m)^\s*networks:")

    def test_worker_port_8765_not_published(self) -> None:
        self.assertNotRegex(self.text, r"0\.0\.0\.0:8765")
        self.assertNotRegex(self.text, r'"8765:8765"')
        self.assertNotRegex(self.text, r"127\.0\.0\.1:8765:8765")
        self.assertNotRegex(self.worker, r"(?m)^\s*ports:")
        self.assertIn("SRL_WORKER_HOST: 127.0.0.1", self.worker)
        self.assertIn('SRL_WORKER_PORT: "8765"', self.worker)
        self.assertIn("read_only: true", self.worker)
        self.assertNotIn("SRL_WORKER_TOKEN:", self.worker)
        self.assertIn("/run/secrets/srl_worker_token", self.worker)
        self.assertIn("SRL_WORKER_TOKEN_HOST_FILE", self.text)
        self.assertIn("dockerfile: docker/srl-worker/Dockerfile", self.worker)
        self.assertNotRegex(self.worker, r"image:\s*srl-worker:si2-option-a@sha256:")
        # Image sets PYTHONSAFEPATH=1; without PYTHONPATH, `python -m tools...` fails.
        self.assertIn("PYTHONPATH: /srl/sentinel-research-lab", self.worker)
        dockerfile = (ROOT / "docker/srl-worker/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("PYTHONSAFEPATH=1", dockerfile)
        self.assertIn("python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579", dockerfile)

    def test_no_public_worker_exposure(self) -> None:
        self.assertNotRegex(self.text, r"0\.0\.0\.0:8765")
        self.assertNotRegex(self.text, r'"8765:8765"')
        self.assertNotRegex(self.text, r"127\.0\.0\.1:8765:8765")

    def test_no_privileged_mode(self) -> None:
        self.assertNotRegex(self.text, r"(?m)^\s*privileged:\s*true\s*$")

    def test_no_host_networking(self) -> None:
        self.assertNotRegex(self.text, r"(?m)^\s*network_mode:\s*host\s*$")

    def test_no_docker_socket_mount(self) -> None:
        self.assertNotIn("/var/run/docker.sock", self.text)
        self.assertNotIn("docker.sock", self.text)

    def test_n8n_volumes_and_dependencies_preserved(self) -> None:
        self.assertIn("depends_on:", self.n8n)
        self.assertIn("postgres:", self.n8n)
        self.assertIn("condition: service_healthy", self.n8n)
        self.assertIn("srl_n8n_data:/home/node/.n8n", self.n8n)
        self.assertIn("srl_net", self.n8n)
        self.assertIn("srl_postgres_data:", self.text)
        self.assertIn("srl_n8n_data:", self.text)


if __name__ == "__main__":
    unittest.main()
