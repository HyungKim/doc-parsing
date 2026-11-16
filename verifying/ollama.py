"""이 PC에서 도는 Ollama에 말을 거는 부분. 파이썬 기본 기능만 쓴다(새로 설치할 것이 없다).

자료가 밖으로 나가지 않게 하는 장치
    주소      늘 127.0.0.1(이 PC 자신)로만 건다. 환경 변수로 다른 PC를 가리켜 두었어도 따르지 않는다(포트 번호만 따른다).
    프록시    회사 PC에 프록시가 잡혀 있어도 거치지 않는다.
    클라우드  Ollama에는 밖의 서버에서 도는 모델(이름에 cloud가 붙음)이 있다. 그런 모델은 여기서 거부한다.
              이 프로그램이 Ollama를 직접 켤 때는 로컬 전용(OLLAMA_NO_CLOUD=1)으로 켠다.
모델을 내려받을 때(pull)만 Ollama가 인터넷을 쓴다. 그때 나가는 것은 모델 이름뿐이다.
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

HOST = "127.0.0.1"
DEFAULT_PORT = 11434
NUM_CTX = 4096                 # 모델이 한 번에 읽는 길이(토큰). 실행 중에 바꾸면 모델을 다시 불러오므로 한 값으로 둔다
TOP_LOGPROBS = 10              # 답 자리에서 확률을 받아 볼 후보 수

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))     # 프록시를 거치지 않는다
_think_ok: Dict[str, bool] = {}                                             # 모델 → think 항목을 받아 주는가


class OllamaError(Exception):
    """Ollama와 주고받다 생긴 문제. 글은 사용자에게 그대로 보여 준다."""


class Cancelled(Exception):
    """사용자가 멈추라고 해서 도중에 그만둠."""


class Call:
    """묻고 있는 요청 하나의 손잡이. 다른 쪽(멈추기 단추)에서 cancel()을 부르면 기다리던 요청이 바로 끊긴다.

    연결이 끊기면 Ollama도 그 글의 계산을 그만둔다(끝까지 계산하느라 PC를 붙잡고 있지 않는다).
    """

    def __init__(self) -> None:
        self.conn: Optional[http.client.HTTPConnection] = None
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True
        conn = self.conn
        if conn is None:
            return
        try:
            if conn.sock is not None:
                conn.sock.shutdown(socket.SHUT_RDWR)       # 답을 기다리며 멈춰 있는 쪽을 깨운다
        except OSError:
            pass
        try:
            conn.close()
        except Exception:
            pass


def port() -> int:
    """Ollama의 포트. 환경 변수 OLLAMA_HOST에 포트가 적혀 있으면 그 번호를 쓴다(주소는 따르지 않는다)."""
    raw = (os.environ.get("OLLAMA_HOST") or "").strip()
    tail = raw.rsplit(":", 1)[-1].strip("/ ") if ":" in raw else ""
    return int(tail) if tail.isdigit() and 0 < int(tail) < 65536 else DEFAULT_PORT


def base_url() -> str:
    return "http://%s:%d" % (HOST, port())


def call(path: str, body: Optional[dict] = None, timeout: float = 30.0) -> dict:
    """Ollama에 한 번 묻고 답(JSON)을 받는다."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base_url() + path, data=data, headers={"Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    try:
        with _opener.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        text = ""
        try:
            text = json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:
            pass
        raise OllamaError("Ollama가 요청을 받지 않았습니다 (%d): %s" % (exc.code, text or exc.reason))
    except (urllib.error.URLError, OSError) as exc:
        raise OllamaError("Ollama에 연결하지 못했습니다 (%s). Ollama가 켜져 있는지 확인해 주세요." % getattr(exc, "reason", exc))
    except ValueError:
        raise OllamaError("Ollama의 답을 읽지 못했습니다")


def version() -> str:
    return str(call("/api/version", timeout=5).get("version", ""))


def find_program() -> Optional[str]:
    found = shutil.which("ollama")
    if found:
        return found
    if sys.platform.startswith("win"):
        for root in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
            if root:
                for sub in (("Programs", "Ollama", "ollama.exe"), ("Ollama", "ollama.exe")):
                    p = Path(root).joinpath(*sub)
                    if p.is_file():
                        return str(p)
    return None


def ensure_running(log: Callable[[str], None]) -> dict:
    """Ollama가 켜져 있는지 보고, 꺼져 있으면 로컬 전용으로 켜 본다. 반환: {"ok", "version", "started", "error"}"""
    try:
        return {"ok": True, "version": version(), "started": False, "error": ""}
    except OllamaError:
        pass
    program = find_program()
    if not program:
        return {"ok": False, "version": "", "started": False,
                "error": "Ollama를 찾지 못했습니다. Ollama가 설치되어 있는지 확인해 주세요."}
    log("Ollama가 꺼져 있어 로컬 전용으로 켭니다…")
    env = dict(os.environ, OLLAMA_NO_CLOUD="1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    try:
        subprocess.Popen([program, "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, creationflags=flags)
    except OSError as exc:
        return {"ok": False, "version": "", "started": False, "error": "Ollama를 켜지 못했습니다: %s" % exc}
    for _ in range(40):
        time.sleep(0.5)
        try:
            return {"ok": True, "version": version(), "started": True, "error": ""}
        except OllamaError:
            continue
    return {"ok": False, "version": "", "started": True, "error": "Ollama를 켰지만 응답이 없습니다. 잠시 뒤 다시 해 주세요."}


# ---------------------------------------------------------------- 모델

def is_cloud_name(name: str) -> bool:
    """밖의 서버에서 도는 모델의 이름인가 (예: gemma4:cloud)."""
    return "cloud" in name.lower()


def _same(a: str, b: str) -> bool:
    norm = lambda n: n if ":" in n else n + ":latest"
    return norm(a.strip().lower()) == norm(b.strip().lower())


def has_thinking(name: str, capabilities: list) -> bool:
    """켜고 끌 수 있는 생각 모드가 있는 모델인가.

    Ollama가 적어 둔 능력만으로는 알 수 없다. qwen3:4b-instruct처럼 생각하지 않는 모델에도 '생각 모드 있음'이라고 적혀 나오는
    버전이 있다(같은 모델을 두고 목록과 상세 정보가 서로 다르게 답하기도 한다). 이름에 instruct가 든 모델은 바로 답하도록 만든 판이므로 없다고 본다.
    """
    return "thinking" in (capabilities or []) and "instruct" not in name.lower()


def models() -> List[dict]:
    """받아 둔 모델 가운데 글을 쓰는 모델. [{"name", "size", "digest", "params", "quant", "thinking", "cloud"}]"""
    out = []
    for m in call("/api/tags", timeout=15).get("models") or []:
        caps = m.get("capabilities") or []
        details = m.get("details") or {}
        if caps and "completion" not in caps:      # 임베딩 전용 모델은 뺀다
            continue
        if not caps and details.get("family") == "bert":
            continue
        name = m.get("name") or m.get("model") or ""
        cloud = bool(m.get("remote_host") or m.get("remote_model")) or is_cloud_name(name)
        out.append({"name": name, "size": int(m.get("size") or 0), "digest": str(m.get("digest") or "")[:12],
                    "params": details.get("parameter_size", ""), "quant": details.get("quantization_level", ""),
                    "thinking": has_thinking(name, caps), "cloud": cloud})
    return out


def find_model(name: str, listed: Optional[List[dict]] = None) -> Optional[dict]:
    for m in (models() if listed is None else listed):
        if _same(m["name"], name):
            return m
    return None


def check_model(name: str, listed: Optional[List[dict]] = None) -> dict:
    """쓸 수 있는 모델인지 확인한다. 클라우드 모델이거나 받아 두지 않은 모델이면 OllamaError"""
    if is_cloud_name(name):
        raise OllamaError("'%s' 은(는) 밖의 서버에서 도는 클라우드 모델이라 쓰지 않습니다. 자료가 이 PC 밖으로 나가기 때문입니다." % name)
    m = find_model(name, listed)
    if m is None:
        raise OllamaError("'%s' 모델을 아직 받지 않았습니다. 화면의 '받기'를 누르거나 명령 창에서 ollama pull %s 를 실행해 주세요." % (name, name))
    if m["cloud"]:
        raise OllamaError("'%s' 은(는) 밖의 서버에서 도는 클라우드 모델이라 쓰지 않습니다." % name)
    return m


def license_of(name: str) -> str:
    """모델에 적힌 라이선스(예: apache-2.0). 모르면 빈 글"""
    try:
        info = call("/api/show", {"model": name}, timeout=20)
    except OllamaError:
        return ""
    lic = str((info.get("model_info") or {}).get("general.license") or "").strip()
    if lic:
        return lic
    for line in str(info.get("license") or "").splitlines():
        if line.strip():
            return line.strip()[:60]
    return ""


def pull(name: str, progress: Callable[[str], None], stop=None) -> None:
    """모델을 내려받는다(이때만 Ollama가 인터넷을 쓴다). stop이 켜지면 그만둔다(받던 부분은 Ollama가 남겨 두어 다음에 이어 받는다)."""
    if is_cloud_name(name):
        raise OllamaError("클라우드 모델은 받지 않습니다: %s" % name)
    req = urllib.request.Request(base_url() + "/api/pull", data=json.dumps({"model": name, "stream": True}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _opener.open(req, timeout=120) as r:
            for raw in r:
                if stop is not None and stop.is_set():
                    raise Cancelled()
                try:
                    msg = json.loads(raw.decode("utf-8"))
                except ValueError:
                    continue
                if msg.get("error"):
                    raise OllamaError("모델을 받지 못했습니다: %s" % msg["error"])
                total, done = msg.get("total") or 0, msg.get("completed") or 0
                if total:
                    progress("%s 받는 중: %.1f / %.1f GB (%d%%)" % (name, done / 1e9, total / 1e9, int(100 * done / total)))
                elif msg.get("status"):
                    progress("%s: %s" % (name, msg["status"]))
    except urllib.error.HTTPError as exc:
        raise OllamaError("모델을 받지 못했습니다 (%d)" % exc.code)
    except (urllib.error.URLError, OSError) as exc:
        raise OllamaError("모델을 받는 중 연결이 끊겼습니다 (%s)" % getattr(exc, "reason", exc))


def unload(name: str) -> None:
    """모델을 메모리에서 내린다(다음 모델을 올릴 자리를 만든다)."""
    try:
        call("/api/generate", {"model": name, "keep_alive": 0}, timeout=60)
    except OllamaError:
        pass


# ---------------------------------------------------------------- 묻기

def _ask(body: dict, timeout: float, handle: Optional[Call]) -> dict:
    """/api/chat 에 묻는다. 프록시를 거치지 않는 직접 연결이고, handle.cancel()로 도중에 끊을 수 있다."""
    if handle is not None and handle.cancelled:
        raise Cancelled()
    conn = http.client.HTTPConnection(HOST, port(), timeout=timeout)
    if handle is not None:
        handle.conn = conn
    try:
        conn.request("POST", "/api/chat", json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
        if handle is not None and handle.cancelled:
            raise Cancelled()
        resp = conn.getresponse()
        status, raw = resp.status, resp.read()
    except Cancelled:
        raise
    except socket.timeout:
        raise OllamaError("Ollama의 답을 %d초 동안 받지 못했습니다" % timeout)
    except (OSError, http.client.HTTPException) as exc:
        if handle is not None and handle.cancelled:
            raise Cancelled()
        raise OllamaError("Ollama에 연결하지 못했습니다 (%s). Ollama가 켜져 있는지 확인해 주세요." % exc)
    finally:
        if handle is not None:
            handle.conn = None
        try:
            conn.close()
        except Exception:
            pass
    try:
        out = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        raise OllamaError("Ollama의 답을 읽지 못했습니다")
    if status >= 400:
        raise OllamaError("Ollama가 요청을 받지 않았습니다 (%d): %s" % (status, out.get("error", "")))
    return out


def chat(model: str, system: str, user: str, max_tokens: int, think: bool = False, handle: Optional[Call] = None,
         timeout: float = 900.0) -> dict:
    """글 하나를 묻는다. 늘 같은 답이 나오게 온도 0으로 한다. think: 답하기 전에 생각(풀이)을 쓰게 할지. 기본은 끔(켜면 훨씬 느리다).

    반환: {"content", "thinking", "logprobs"(토큰마다 후보와 확률. 못 받으면 빈 목록),
           "in"(입력 토큰), "out"(출력 토큰), "load_s", "in_s", "out_s", "total_s"}
    """
    body = {"model": model, "stream": False, "keep_alive": "30m", "logprobs": True, "top_logprobs": TOP_LOGPROBS,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "seed": 1, "num_predict": int(max_tokens), "num_ctx": NUM_CTX}}
    if think or _think_ok.get(model, True):
        body["think"] = bool(think)
    try:
        out = _ask(body, timeout, handle)
    except OllamaError as exc:
        if "think" not in body or "think" not in str(exc).lower():
            raise
        if think:
            raise OllamaError("'%s' 은(는) 생각 모드가 없는 모델입니다" % model)
        _think_ok[model] = False                       # 생각 모드가 없는 모델은 그 항목을 빼고 다시 묻는다
        del body["think"]
        out = _ask(body, timeout, handle)
    msg = out.get("message") or {}
    sec = lambda key: float(out.get(key) or 0) / 1e9
    return {"content": str(msg.get("content") or ""), "thinking": str(msg.get("thinking") or ""),
            "logprobs": out.get("logprobs") or [],
            "in": int(out.get("prompt_eval_count") or 0), "out": int(out.get("eval_count") or 0),
            "load_s": sec("load_duration"), "in_s": sec("prompt_eval_duration"), "out_s": sec("eval_duration"),
            "total_s": sec("total_duration")}
