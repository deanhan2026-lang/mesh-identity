"""
Identity Sync Engine - 跨端身份同步引擎

实现多终端身份同步的核心能力：
1. 实例心跳更新
2. 失联检测与自动撤销
3. mesh inbox 广播身份变更
4. 主动拉取远程身份状态
"""

import json
import os
import re
import sys
import socket
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from did.multi_instance import MultiInstanceDIDManager
try:
    from storage.nas_storage import NASStorage
except ImportError:
    NASStorage = None


class IdentitySyncEngine:
    """跨端身份同步引擎"""

    def __init__(
        self,
        primary_did: str,
        instance_id: str,
        mesh_base: str = "Z:/qclaw/mesh",
        did_storage_path: str = "Z:/qclaw/did",
        instance_lock_path: str = "Z:/qclaw/instance.lock"
    ):
        self.primary_did = primary_did
        self.instance_id = instance_id
        self.mesh_base = Path(mesh_base)
        self.did_storage_path = Path(did_storage_path)
        self.instance_lock_path = Path(instance_lock_path)

        self.registry_path = self.mesh_base / "registry.json"
        self.inbox_base = self.mesh_base / "inbox"
        self.msg_counter_path = self.mesh_base / "msg_counter.json"

        self.mesh_reachable = self._check_mesh_reachable()

        self._multi_instance = None
        self._nas_storage = None

    def _check_mesh_reachable(self) -> bool:
        try:
            return self.mesh_base.exists()
        except Exception:
            return False

    def _init_multi_instance(self) -> MultiInstanceDIDManager:
        if self._multi_instance is None:
            self._multi_instance = MultiInstanceDIDManager(
                storage_path=str(self.did_storage_path)
            )
        return self._multi_instance

    def _init_nas_storage(self) -> Optional[NASStorage]:
        if self._nas_storage is None:
            try:
                self._nas_storage = NASStorage(base_path=str(self.mesh_base.parent))
            except Exception:
                self._nas_storage = None
        return self._nas_storage

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _hostname(self) -> str:
        try:
            return socket.gethostname()
        except Exception:
            return os.environ.get("COMPUTERNAME", "unknown")

    def _read_json(self, path: Path, default: Any = None) -> Optional[Dict]:
        try:
            if not path.exists():
                return default
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            try:
                backup = path.with_suffix(".json.bak")
                path.rename(backup)
            except Exception:
                pass
            return default
        except Exception:
            return default

    def _write_json_atomic(self, path: Path, data: Any) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.parent / (path.name + ".tmp")
            temp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            os.replace(temp, path)
            return True
        except Exception:
            return False

    def _write_text_atomic(self, path: Path, content: str) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.parent / (path.name + ".tmp")
            temp.write_text(content, encoding="utf-8")
            os.replace(temp, path)
            return True
        except Exception:
            return False

    def _load_registry(self) -> Dict:
        default = {
            "schema": "mesh-registry-v1",
            "nodes": {},
            "updated_at": self._now()
        }
        registry = self._read_json(self.registry_path, default)
        if registry is None:
            registry = default
        if "nodes" not in registry:
            registry["nodes"] = {}
        return registry

    def _save_registry(self, registry: Dict) -> bool:
        registry["updated_at"] = self._now()
        return self._write_json_atomic(self.registry_path, registry)

    def _get_next_msg_seq(self) -> int:
        counter_data = self._read_json(self.msg_counter_path, {"counter": 0})
        if counter_data is None:
            counter_data = {"counter": 0}
        counter_data["counter"] += 1
        self._write_json_atomic(self.msg_counter_path, counter_data)
        return counter_data["counter"]

    def on_instance_heartbeat(self, instance_id: str) -> Dict:
        ts = self._now()
        registry = self._load_registry()

        nodes = registry.setdefault("nodes", {})
        is_new = instance_id not in nodes

        nodes[instance_id] = {
            "lastSeen": ts,
            "status": "active",
            "hostname": self._hostname(),
            "instance_id": instance_id
        }
        self._save_registry(registry)

        lock_data = {
            "schema": "instance-lock-v1",
            "holder": instance_id,
            "hostname": self._hostname(),
            "acquired": ts,
            "lastHeartbeat": ts,
            "status": "active"
        }
        self._write_json_atomic(self.instance_lock_path, lock_data)

        if is_new:
            try:
                self.propagate_identity_change("instance_register", {
                    "instance_id": instance_id,
                    "hostname": self._hostname(),
                    "status": "active"
                })
            except Exception:
                pass

        return {
            "success": True,
            "instance_id": instance_id,
            "lastSeen": ts,
            "is_new": is_new
        }

    def detect_stale_instances(self, threshold_minutes: int = 30) -> Dict:
        registry = self._load_registry()
        nodes = registry.get("nodes", {})
        now_ts = datetime.now(timezone.utc)

        stale = []
        expired = []

        for node_id, node_info in nodes.items():
            last_seen_str = node_info.get("lastSeen", "")
            if not last_seen_str:
                continue
            try:
                last_seen = datetime.fromisoformat(last_seen_str)
                minutes_ago = (now_ts - last_seen).total_seconds() / 60
            except Exception:
                continue

            entry = {
                "name": node_id,
                "instance_id": node_id,
                "lastSeen": last_seen_str,
                "minutes_ago": round(minutes_ago, 1)
            }

            if minutes_ago > threshold_minutes * 2:
                expired.append(entry)
            elif minutes_ago > threshold_minutes:
                stale.append(entry)

        return {
            "stale": stale,
            "expired": expired,
            "timestamp": self._now()
        }

    def sync_identity_state(self) -> Dict:
        inbox_path = self.inbox_base / self.instance_id
        processed = 0
        errors = 0
        updated_nodes = []

        if not inbox_path.exists():
            return {
                "messages_processed": 0,
                "errors": 0,
                "updated_nodes": [],
                "timestamp": self._now()
            }

        registry = self._load_registry()

        try:
            msg_files = sorted([
                f for f in inbox_path.iterdir()
                if f.suffix == ".md" and f.name != "_flag.md"
            ])
        except Exception:
            msg_files = []

        for msg_file in msg_files:
            try:
                content = msg_file.read_text(encoding="utf-8")
                if not content.startswith("---"):
                    msg_file.unlink(missing_ok=True)
                    processed += 1
                    continue

                parts = content.split("---", 2)
                if len(parts) < 3:
                    msg_file.unlink(missing_ok=True)
                    processed += 1
                    continue

                frontmatter_lines = parts[1].strip().split("\n")
                meta = {}
                for line in frontmatter_lines:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        meta[key.strip()] = val.strip()

                change_type = meta.get("change_type", "")
                from_instance = meta.get("from", "")
                timestamp = meta.get("timestamp", "")

                body = parts[2]
                data = {}
                data_match = re.search(r'\*\*data\*\*:\s*(\{.*\})', body, re.DOTALL)
                if data_match:
                    try:
                        data = json.loads(data_match.group(1))
                    except Exception:
                        data = {}

                nodes = registry.setdefault("nodes", {})

                if change_type in ("instance_register", "instance_heartbeat") and from_instance:
                    if from_instance not in nodes:
                        nodes[from_instance] = {
                            "instance_id": from_instance,
                            "lastSeen": timestamp or self._now(),
                            "status": "active",
                            "hostname": data.get("hostname", from_instance)
                        }
                    else:
                        nodes[from_instance]["lastSeen"] = timestamp or self._now()
                        nodes[from_instance]["status"] = "active"
                    updated_nodes.append(from_instance)

                elif change_type == "instance_revoke" and from_instance:
                    if from_instance in nodes:
                        nodes[from_instance]["status"] = "revoked"
                        nodes[from_instance]["revoked_at"] = self._now()
                        updated_nodes.append(from_instance)

                elif change_type == "did_update" and from_instance:
                    if from_instance in nodes:
                        nodes[from_instance].update(data)
                        updated_nodes.append(from_instance)

                try:
                    msg_file.unlink()
                except Exception:
                    pass
                processed += 1

            except Exception:
                errors += 1
                try:
                    error_path = msg_file.with_suffix(".md.error")
                    msg_file.rename(error_path)
                except Exception:
                    pass

        flag_file = inbox_path / "_flag.md"
        if flag_file.exists():
            try:
                flag_file.unlink()
            except Exception:
                pass

        if updated_nodes:
            self._save_registry(registry)

        return {
            "messages_processed": processed,
            "errors": errors,
            "updated_nodes": updated_nodes,
            "timestamp": self._now()
        }

    def propagate_identity_change(self, change_type: str, data: dict) -> Dict:
        registry = self._load_registry()
        nodes = registry.get("nodes", {})
        ts = self._now()
        seq = self._get_next_msg_seq()

        if self.instance_id not in nodes:
            nodes[self.instance_id] = {
                "instance_id": self.instance_id,
                "lastSeen": ts,
                "status": "active",
                "hostname": self._hostname()
            }
            registry["nodes"] = nodes
            self._save_registry(registry)

        data_json = json.dumps(data, ensure_ascii=False)
        msg_content = f"""---
schema: mesh-identity-v1
from: {self.instance_id}
type: identity_broadcast
change_type: {change_type}
timestamp: {ts}
---

## 身份变更广播

**change_type**: {change_type}
**data**: {data_json}
"""

        all_nodes = set(nodes.keys())
        all_nodes.add(self.instance_id)

        written = []
        errors = []

        for node_name in all_nodes:
            try:
                inbox_dir = self.inbox_base / node_name
                inbox_dir.mkdir(parents=True, exist_ok=True)

                safe_ts = ts.replace(":", "").replace("-", "")
                safe_ts = safe_ts.replace("+", "_").replace(".", "_")
                msg_filename = f"msg_{seq:04d}_{self.instance_id}_{safe_ts}.md"
                msg_path = inbox_dir / msg_filename

                self._write_text_atomic(msg_path, msg_content)

                flag_content = f"""---
new_messages: true
timestamp: {ts}
---
"""
                flag_path = inbox_dir / "_flag.md"
                self._write_text_atomic(flag_path, flag_content)

                written.append(str(msg_path))
            except Exception as e:
                errors.append({"node": node_name, "error": str(e)})

        return {
            "success": len(errors) == 0,
            "total_broadcast": len(written),
            "errors": errors,
            "message_files": written,
            "seq": seq,
            "change_type": change_type
        }

    def auto_revoke_expired(self, threshold_minutes: int = 60) -> Dict:
        stale_result = self.detect_stale_instances(threshold_minutes=threshold_minutes)

        revoked = []
        errors = []

        for expired_node in stale_result.get("expired", []):
            node_id = expired_node.get("instance_id")
            if not node_id or node_id == self.instance_id:
                continue

            try:
                multi = self._init_multi_instance()
                try:
                    multi.revoke_instance(self.primary_did, node_id)
                except Exception:
                    pass

                registry = self._load_registry()
                if node_id in registry.get("nodes", {}):
                    registry["nodes"][node_id]["status"] = "revoked"
                    registry["nodes"][node_id]["revoked_at"] = self._now()
                    self._save_registry(registry)

                self.propagate_identity_change("instance_revoke", {
                    "instance_id": node_id,
                    "reason": "auto_revoke_expired",
                    "threshold_minutes": threshold_minutes
                })

                revoked.append(node_id)
            except Exception as e:
                errors.append({"instance_id": node_id, "error": str(e)})

        return {
            "success": len(errors) == 0,
            "revoked": revoked,
            "errors": errors,
            "stale_count": len(stale_result.get("stale", [])),
            "expired_count": len(stale_result.get("expired", [])),
            "timestamp": self._now()
        }

    def get_status(self) -> Dict:
        registry = self._load_registry()
        nodes = registry.get("nodes", {})
        now_ts = datetime.now(timezone.utc)

        total = len(nodes)
        active = 0
        stale_count = 0

        for node_info in nodes.values():
            if node_info.get("status") == "revoked":
                continue
            last_seen_str = node_info.get("lastSeen", "")
            if last_seen_str:
                try:
                    last_seen = datetime.fromisoformat(last_seen_str)
                    minutes_ago = (now_ts - last_seen).total_seconds() / 60
                except Exception:
                    minutes_ago = 999999
            else:
                minutes_ago = 999999

            if minutes_ago > 30:
                stale_count += 1
            else:
                active += 1

        return {
            "local_instance": self.instance_id,
            "total_registered": total,
            "active_instances": active,
            "stale_instances": stale_count,
            "last_sync": registry.get("updated_at", ""),
            "mesh_reachable": self.mesh_reachable,
            "registry_path": str(self.registry_path),
            "instance_lock_path": str(self.instance_lock_path)
        }
