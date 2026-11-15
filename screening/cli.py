"""screen.py(계산)와 label.py(정답 붙이는 화면)가 함께 쓰는 설정과 실행."""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent      # 프로그램 폴더

NEED = ["numpy", "sklearn", "torch", "transformers", "sentence_transformers", "huggingface_hub"]


@dataclass
class Config:
    out_dir: Path
    models: Optional[str]            # 쉼표로 나눈 모델 이름. 없으면 기본 세 가지
    sentences: Path
    labels: Path
    target: float                    # '예' 가운데 이 비율 이상을 찾아내도록 문턱을 맞춘다
    max_len: int
    download: bool
    models_dir: Path
    options: Path = ROOT / "screen_options.txt"    # 설정 파일
    test_docs: Path = ROOT / "screen_test_docs.txt"   # 시험용 문서 목록
    title_weight: float = 0.0        # 쪽 제목 점수를 섞는 비율. 0이면 반영하지 않음


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("out_dir", nargs="?", default="out", help="추출 결과 폴더 (기본: out)")
    parser.add_argument("--models", help="돌릴 모델을 고름. 쉼표로 나눔: bge-m3,kure-v1,me5-small (기본은 이 셋). "
                             "bge-m3-zeroshot 은 느려서 기본에서 빠져 있고 여기에 이름을 적을 때만 돕니다")
    parser.add_argument("--sentences", help="기준 문장 파일 (기본: 프로그램 폴더의 screen_sentences.txt)")
    parser.add_argument("--labels", help="정답 파일 (기본: 프로그램 폴더의 labels/labels.json)")
    parser.add_argument("--recall", type=float, default=0.9, help="놓치지 않으려는 '예'의 비율 (기본 0.9 = 90%%)")
    parser.add_argument("--max-len", type=int, default=512, help="모델에 넣는 글의 최대 길이(토큰). 기본 512")
    parser.add_argument("--models-dir", help="모델 파일을 두는 폴더 (기본: 프로그램 폴더의 models)")
    parser.add_argument("--no-download", action="store_true", help="모델 파일이 없어도 내려받지 않음")
    parser.add_argument("--title-weight", type=float, help="쪽 제목 점수를 글 점수에 섞는 비율 0~0.9 (기본: 설정 파일의 값, 처음에는 0 = 반영 안 함)")
    parser.add_argument("--options", help="설정 파일 (기본: 프로그램 폴더의 screen_options.txt)")
    parser.add_argument("--test-docs", help="시험용 문서 목록 파일 (기본: 프로그램 폴더의 screen_test_docs.txt)")


def config_from(args: argparse.Namespace) -> Config:
    if not 0 < args.recall <= 1:
        raise SystemExit("--recall 은 0보다 크고 1 이하여야 합니다 (예: 0.9)")
    from .options import check_title_weight, read_options
    options_file = Path(args.options) if args.options else ROOT / "screen_options.txt"
    try:
        saved = read_options(options_file)
        title_weight = saved["title_weight"] if args.title_weight is None else check_title_weight(args.title_weight)
    except ValueError as exc:
        raise SystemExit("[오류] %s" % exc)
    return Config(
        options=options_file,
        test_docs=Path(args.test_docs) if args.test_docs else ROOT / "screen_test_docs.txt",
        title_weight=title_weight,
        out_dir=Path(args.out_dir),
        models=args.models,
        sentences=Path(args.sentences) if args.sentences else ROOT / "screen_sentences.txt",
        labels=Path(args.labels) if args.labels else ROOT / "labels" / "labels.json",
        target=args.recall,
        max_len=args.max_len,
        download=not args.no_download,
        models_dir=Path(args.models_dir) if args.models_dir else ROOT / "models",
    )


def setup_env(models_dir: Path) -> None:
    """모델 라이브러리가 쓰는 임시 폴더를 모델 폴더 안으로 돌린다(C: 드라이브에 쌓이지 않게). 모델을 불러오기 전에 불러야 한다."""
    os.environ.setdefault("HF_HOME", str(Path(models_dir) / ".hf"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")


def missing_packages() -> list:
    import importlib.util
    return [n for n in NEED if importlib.util.find_spec(n) is None]


def check_ready(cfg: Config) -> None:
    """실행에 필요한 것이 없으면 무엇을 해야 하는지 알려 주고 끝낸다."""
    missing = missing_packages()
    if missing:
        raise SystemExit("[오류] 걸러내기에 필요한 라이브러리가 없습니다: %s\n       install_screen.bat 을 먼저 실행해 주세요." % ", ".join(missing))
    if not list(Path(cfg.out_dir).glob("*.units.json")):
        raise SystemExit("[오류] %s 폴더에 추출 결과(이름.units.json)가 없습니다.\n       run.bat 으로 문서를 먼저 추출해 주세요." % cfg.out_dir)


def execute(cfg: Config, log: Callable[[str], None]) -> Tuple[object, Path]:
    """계산 → 학습 → 수치 → 리포트. 반환: (결과, 첫 화면 파일)"""
    setup_env(cfg.models_dir)
    from . import report, run
    from .testdocs import read_test_docs
    res = run.run(cfg.out_dir, ROOT, cfg.models, cfg.sentences, cfg.labels, cfg.target, cfg.max_len, cfg.download, log, cfg.models_dir,
                  cfg.title_weight, read_test_docs(cfg.test_docs))
    if not any(r.ok for r in res.runs):            # 하나도 못 돌렸으면 지난 결과를 덮어쓰지 않는다
        raise SystemExit("[오류] 돌릴 수 있는 모델이 없습니다. install_screen.bat 을 실행했는지 확인해 주세요.\n" +
                         "\n".join("       %s: %s" % (r.spec["label"], r.error) for r in res.runs))
    run.write_scores(res, Path(cfg.out_dir) / "screen" / "scores.json")
    # 학습 기록: 이번 결과를 지금 화면(out/screen)과, 기록 폴더(out/screen/history/번호_때)에 함께 만든다
    from . import history
    entries, entry, is_new = history.prepare(res)
    saved = "이 결과는 학습 기록 %d번에 %s" % (entry["n"], "새로 저장했습니다" if is_new else "다시 저장했습니다(학습 상태가 지난번과 같음)")
    index = report.write_all(res, ROOT, note="<div class=\"note\"><b>%s.</b> <a href=\"history.html\"><b>학습 기록 보기 (%d번)</b></a> · "
                             "학습할 때마다의 결과가 남아 있어 지난 결과와 견줘 볼 수 있습니다.</div>" % (saved, len(entries)))
    report.write_all(res, ROOT, dest=history.folder(res) / entry["dir"], up="../../../",
                     note="<div class=\"note old\"><b>저장된 학습 기록 #%d</b> · %s에 학습했을 때의 결과입니다. 지금의 결과가 아닐 수 있습니다. · "
                          "<a href=\"../../history.html\"><b>기록 목록</b></a> · <a href=\"../../index.html\">지금의 비교 화면</a></div>" % (entry["n"], entry["made"]))
    history.save(res, entries)
    report.write_history(res, entries, Path(cfg.out_dir) / "screen" / "history.html", history.what_changed)
    res.record = {"n": entry["n"], "new": is_new, "count": len(entries), "text": saved}
    return res, index


def download_only(cfg: Config, log: Callable[[str], None]) -> int:
    """모델 파일만 내려받는다. 반환: 받지 못한 모델의 수"""
    setup_env(cfg.models_dir)
    from . import models
    failed = 0
    for spec in models.pick_models(cfg.models):
        try:
            if models.is_ready(spec, cfg.models_dir):
                log("이미 있음: %s" % spec["label"])
            else:
                models.ensure_model(spec, cfg.models_dir, log, True)
                log("받음: %s" % spec["label"])
        except models.ModelMissing as exc:
            failed += 1
            log("[오류] %s: %s" % (spec["label"], exc))
    return failed
