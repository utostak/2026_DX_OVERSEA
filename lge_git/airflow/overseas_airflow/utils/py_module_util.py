"""
py_module_util.py — job_modules/*.py 동적 실행 공용 유틸
─────────────────────────────────────────────────────────────────
jobs_dynamic.py / batches_dynamic.py 가 공통으로 사용합니다.
(중복 코드 제거를 위해 분리)

execute_python_module func_name 처리 시,
  job_modules/<module_name>.py 를 로드하여 진입 함수(entry_func, 기본 run)를 호출합니다.
─────────────────────────────────────────────────────────────────
"""
import os
import re as _re
import logging

_log = logging.getLogger(__name__)

# job_modules 폴더는 이 파일(utils/)의 상위 디렉터리에 위치합니다.
_JOB_MODULES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "job_modules",
)


def run_python_module(params: dict, sql_text: str, context: dict):
    """job_modules/<module_name>.py 를 로드하여 진입 함수(entry_func, 기본 run)를 호출.

    진입 함수에는 시그니처에 존재하는 인자만 골라서 전달합니다.
      · params  : module_name/entry_func 를 제외한 나머지 파라미터(dict)
      · sql_text: Job 화면의 SQL 입력값(자유 텍스트)
      · context : Airflow 실행 컨텍스트
    """
    import sys
    import importlib.util
    import inspect

    params = params or {}
    module_name = (params.get("module_name") or "").strip()
    entry_func  = (params.get("entry_func") or "run").strip() or "run"
    if not module_name:
        raise ValueError("execute_python_module: 파라미터 'module_name' 이 필요합니다.")

    # 경로 구분자 통일 ('.' 또는 '\' → '/') 후 검증
    module_name = module_name.replace("\\", "/").replace(".", "/").strip("/")
    parts = [p for p in module_name.split("/") if p]
    # 경로 조작 방지: 각 경로 조각은 단순 이름만 허용 ('..' 등 차단)
    if not parts or any(not _re.match(r'^[A-Za-z0-9_]+$', p) for p in parts):
        raise ValueError(f"execute_python_module: 허용되지 않는 모듈명입니다: {module_name}")

    mod_path = os.path.join(_JOB_MODULES_DIR, *parts) + ".py"
    if not os.path.isfile(mod_path):
        raise FileNotFoundError(f"모듈 파일을 찾을 수 없습니다: {mod_path}")

    # 모듈이 위치한 디렉터리 (해당 모듈의 로컬 utils/ 등을 찾기 위한 기준 경로)
    mod_dir = os.path.dirname(mod_path)

    # ── 로컬 import 격리 처리 ─────────────────────────────────────
    # 모듈 파일(예: liw_jobs/eta_digest_email.py)은 자신의 디렉터리 기준으로
    #   `from utils.env import ...` 처럼 로컬 패키지를 import 합니다.
    # 그런데 airflow 최상위 `utils` 패키지가 이미 sys.modules 에 캐시되어 있으면
    #   로컬 utils 대신 airflow utils 를 참조해 ImportError 가 발생합니다.
    # → 실행 직전에 모듈 디렉터리를 sys.path 최상단에 넣고,
    #   충돌 가능성이 있는 최상위 패키지 이름들을 임시로 격리(pop)했다가
    #   실행이 끝나면 원상 복구합니다.

    # 모듈 디렉터리의 최상위 하위 패키지/모듈 이름 수집 (utils, .py 파일 등)
    _local_names = set()
    try:
        for _entry in os.listdir(mod_dir):
            _full = os.path.join(mod_dir, _entry)
            if os.path.isdir(_full) and os.path.isfile(os.path.join(_full, "__init__.py")):
                _local_names.add(_entry)                      # 패키지 (예: utils)
            elif _entry.endswith(".py") and _entry != "__init__.py":
                _local_names.add(_entry[:-3])                 # 단일 모듈
    except OSError:
        pass

    # 격리 대상: 로컬에 존재하면서 sys.modules 에 이미 캐시된 이름들
    _saved_modules = {}
    for _name in list(sys.modules.keys()):
        _top = _name.split(".")[0]
        if _top in _local_names:
            _saved_modules[_name] = sys.modules.pop(_name)

    _path_inserted = False
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
        _path_inserted = True

    _mod_ref = "job_modules." + ".".join(parts)
    try:
        spec = importlib.util.spec_from_file_location(_mod_ref, mod_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        fn = getattr(module, entry_func, None)
        if not callable(fn):
            raise AttributeError(f"모듈 '{module_name}' 에 호출 가능한 함수 '{entry_func}' 가 없습니다.")

        # 진입 함수에 사용할 인자만 골라 전달 (module_name/entry_func 는 제외)
        call_params = {k: v for k, v in params.items() if k not in ("module_name", "entry_func")}
        available = {"params": call_params, "sql_text": sql_text, "context": context}
        try:
            sig = inspect.signature(fn)
            kwargs = {k: v for k, v in available.items() if k in sig.parameters}
        except (TypeError, ValueError):
            kwargs = {"params": call_params}

        _log.info(f"[py_module_util] 파이썬 모듈 실행: {module_name}.{entry_func}({', '.join(kwargs)}) (cwd={mod_dir})")
        return fn(**kwargs)
    finally:
        # ── 원상 복구 ─────────────────────────────────────────────
        if _path_inserted:
            try:
                sys.path.remove(mod_dir)
            except ValueError:
                pass
        # 실행 중 로드된 로컬 이름들 제거 (airflow utils 와의 충돌 방지)
        for _name in list(sys.modules.keys()):
            if _name.split(".")[0] in _local_names:
                del sys.modules[_name]
        # 원래 캐시되어 있던 (airflow 등) 모듈들 복구
        sys.modules.update(_saved_modules)
