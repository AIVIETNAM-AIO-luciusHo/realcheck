"""Test app/inference.py (T016; AC-20, AC-21, AC-22; D11, D12; FR-A04).

Test phụ thuộc các tên không công khai sau của app (đổi tên thì sửa test):
- InferenceService._slots (BoundedSemaphore) và _timeout_s: không có đường công khai để
  kiểm "từ chối không chờ" và "slot đã nhả"; dùng để ghi cách acquire và nới timeout.
- Tiền tố thread "inference": kiểm loader chạy trên worker thread, không trên event loop.
- Logger "realcheck" với chuỗi "model_load_failed"/"inference_failed": kiểm lỗi được log.
- app.state.inference / app.state.scorer: gắn route thử trong test để đi qua HTTP.

Tất định: chờ bằng threading.Event và vòng poll có hạn chót, không dựa vào thời gian
thực nhạy. Scorer giả do test điều khiển; không torch, không model thật, không mạng.
"""

import asyncio
import logging
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.errors import ApiError
from app.inference import InferenceService
from app.main import create_app
from app.schemas import ErrorCode
from app.settings import Settings

IMG = Image.new("RGB", (4, 4))
TIMEOUT_S = 0.1  # đủ nhỏ để test nhanh; mọi kết luận dựa vào hành vi, không đo giờ
DEADLINE_S = 10  # hạn chót của mọi vòng chờ; chỉ tới đây khi test đã hỏng


def make_service(slots=1, timeout=TIMEOUT_S):
    return InferenceService(Settings(inference_slots=slots, model_timeout_s=timeout))


def job(scorer):
    return scorer(IMG)


def quick(image):
    return 0.2


class RecordingSlots:
    """Bọc BoundedSemaphore để ghi cách acquire được gọi: từ chối tức thì = không chờ."""

    def __init__(self, inner):
        self._inner, self.calls = inner, []

    def acquire(self, *args, **kwargs):
        assert not args, "acquire phải gọi bằng từ khóa"
        self.calls.append(kwargs)
        return self._inner.acquire(**kwargs)

    def release(self):
        self._inner.release()


def lengthen(service):
    """Nới timeout cho lần gọi cuối phải thành công, tránh MODEL_TIMEOUT giả khi CI đứng."""
    service._timeout_s = DEADLINE_S


class Gate:
    """Scorer giả: chặn tới khi test gọi release; đếm số lần gọi và số lần chạy đồng thời."""

    def __init__(self, result=0.5, exc=None):
        self.release = threading.Event()
        self.started = threading.Event()
        self.lock = threading.Lock()
        self.running = 0
        self.peak = 0
        self.calls = 0
        self.result = result
        self.exc = exc

    def __call__(self, image):
        with self.lock:
            self.running += 1
            self.calls += 1
            self.peak = max(self.peak, self.running)
        self.started.set()
        try:
            assert self.release.wait(DEADLINE_S), "test quên release scorer"
            if self.exc:
                raise self.exc
            return self.result
        finally:
            with self.lock:
                self.running -= 1


async def wait_for(predicate):
    deadline = time.monotonic() + DEADLINE_S
    while not predicate():
        assert time.monotonic() < deadline, "hết hạn chót khi chờ điều kiện"
        await asyncio.sleep(0.005)


def wait_for_sync(predicate):
    deadline = time.monotonic() + DEADLINE_S
    while not predicate():
        assert time.monotonic() < deadline, "hết hạn chót khi chờ điều kiện"
        time.sleep(0.005)


def slot_is_free(service):
    if service._slots.acquire(blocking=False):
        service._slots.release()
        return True
    return False


def error_code(info):
    return info.value.code


# ---- 1. Hết slot: từ chối ngay, không xếp hàng (D11, AC-21) ----


def test_het_slot_tu_choi_ngay_khong_xep_hang_va_khong_goi_scorer():
    async def go():
        service = make_service(timeout=DEADLINE_S)
        slots = service._slots = RecordingSlots(service._slots)
        busy, other = Gate(), Gate()
        first = asyncio.create_task(service.run(busy, job))
        await wait_for(busy.started.is_set)
        with pytest.raises(ApiError) as info:
            await service.run(other, job)
        assert error_code(info) == ErrorCode.SERVICE_BUSY
        assert other.calls == 0  # không xếp hàng: scorer thứ hai chưa từng chạy
        assert [call.get("blocking", True) for call in slots.calls] == [False, False]
        assert not any("timeout" in call for call in slots.calls)  # không chờ slot
        assert busy.calls == 1 and busy.peak == 1
        busy.release.set()
        assert await first == 0.5
        assert await service.run(quick, job) == 0.2

    asyncio.run(go())


# ---- 2. Timeout giữ slot tới khi việc thật sự xong (D12, FR-A04, AC-21) ----


def test_timeout_giu_slot_va_nha_khi_scorer_cu_xong():
    async def go():
        service = make_service()
        old = Gate()
        with pytest.raises(ApiError) as info:
            await service.run(old, job)
        assert error_code(info) == ErrorCode.MODEL_TIMEOUT
        nxt = Gate()
        with pytest.raises(ApiError) as info:
            await service.run(nxt, job)
        assert error_code(info) == ErrorCode.SERVICE_BUSY
        assert nxt.calls == 0 and old.peak == 1  # không chạy song song
        old.release.set()
        await wait_for(lambda: slot_is_free(service))
        lengthen(service)
        assert await service.run(quick, job) == 0.2

    asyncio.run(go())


def test_loi_scorer_sau_timeout_van_nha_slot():
    async def go():
        service = make_service()
        old = Gate(exc=RuntimeError("boom"))
        with pytest.raises(ApiError) as info:
            await service.run(old, job)
        assert error_code(info) == ErrorCode.MODEL_TIMEOUT
        old.release.set()
        await wait_for(lambda: slot_is_free(service))
        lengthen(service)
        assert await service.run(quick, job) == 0.2

    asyncio.run(go())


# ---- 3. Hủy request không rò slot ----


def test_huy_request_giu_slot_toi_khi_scorer_xong_roi_nha():
    async def go():
        service = make_service(timeout=DEADLINE_S)
        gate = Gate()
        task = asyncio.create_task(service.run(gate, job))
        await wait_for(gate.started.is_set)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not slot_is_free(service)  # scorer còn chạy nên slot còn giữ
        gate.release.set()
        await wait_for(lambda: slot_is_free(service))  # xong thì nhả, không rò
        assert await service.run(quick, job) == 0.2

    asyncio.run(go())


# ---- 4. Lỗi scorer thành MODEL_ERROR, không lộ chi tiết (AC-20) ----


def test_loi_scorer_thanh_model_error_va_nha_slot():
    async def go():
        service = make_service(timeout=DEADLINE_S)

        def bad(image):
            raise ValueError("secret-path /models/x.joblib")

        with pytest.raises(ApiError) as info:
            await service.run(bad, job)
        assert error_code(info) == ErrorCode.MODEL_ERROR
        assert info.value.message is None  # message mặc định trong ERROR_TABLE
        await wait_for(lambda: slot_is_free(service))

    asyncio.run(go())


def test_http_loi_scorer_khong_lo_stacktrace_ten_exception_hay_duong_dan(caplog):
    gate = Gate(exc=ValueError("secret-path /models/x.joblib"))
    gate.release.set()
    app = create_app(scorer=gate, settings=Settings(model_timeout_s=DEADLINE_S))

    @app.get("/t")
    async def route():
        return {"s": await app.state.inference.run(app.state.scorer, job)}

    with (
        caplog.at_level(logging.ERROR, logger="realcheck"),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.get("/t")
    assert "inference_failed" in caplog.text  # lỗi chỉ vào log, không vào response
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "MODEL_ERROR"
    for leak in ("Traceback", "ValueError", "secret-path", "/models/", "File "):
        assert leak not in response.text


def test_api_error_cua_job_di_thang_khong_bi_boc_thanh_model_error():
    async def go():
        service = make_service(timeout=DEADLINE_S)

        def failing_job(scorer):
            raise ApiError(ErrorCode.IMAGE_TOO_SMALL)

        with pytest.raises(ApiError) as info:
            await service.run(quick, failing_job)
        assert error_code(info) == ErrorCode.IMAGE_TOO_SMALL

    asyncio.run(go())


def test_scorer_none_la_model_not_ready_va_khong_giu_slot():
    async def go():
        service = make_service()
        with pytest.raises(ApiError) as info:
            await service.run(None, job)
        assert error_code(info) == ErrorCode.MODEL_NOT_READY
        assert slot_is_free(service)

    asyncio.run(go())


# ---- 5. Không bao giờ vượt số slot đồng thời ----


@pytest.mark.parametrize("slots", [1, 2, 3])
def test_khong_bao_gio_chay_qua_slots_dong_thoi(slots):
    async def go():
        service = make_service(slots, timeout=DEADLINE_S)
        lock = threading.Lock()
        state = {"running": 0, "peak": 0}

        def scorer(image):
            with lock:
                state["running"] += 1
                state["peak"] = max(state["peak"], state["running"])
            time.sleep(0.002)
            with lock:
                state["running"] -= 1
            return 0.5

        results = await asyncio.gather(
            *[service.run(scorer, job) for _ in range(40)], return_exceptions=True
        )
        ok = [r for r in results if r == 0.5]
        busy = [r for r in results if isinstance(r, ApiError)]
        assert len(ok) + len(busy) == 40 and ok
        assert all(b.code == ErrorCode.SERVICE_BUSY for b in busy)
        assert state["peak"] <= slots

    asyncio.run(go())


def test_slots_2_hai_chay_ba_bi_tu_choi():
    async def go():
        service = make_service(2, DEADLINE_S)
        gate = Gate()
        a = asyncio.create_task(service.run(gate, job))
        b = asyncio.create_task(service.run(gate, job))
        await wait_for(lambda: gate.running == 2)
        with pytest.raises(ApiError) as info:
            await service.run(gate, job)
        assert error_code(info) == ErrorCode.SERVICE_BUSY
        assert gate.calls == 2
        gate.release.set()
        assert await a == 0.5 and await b == 0.5

    asyncio.run(go())


# ---- 6. Event loop không bị chặn khi scorer chậm ----


def test_event_loop_van_chay_khi_scorer_cham():
    async def go():
        service = make_service(timeout=DEADLINE_S)
        gate = Gate()
        task = asyncio.create_task(service.run(gate, job))
        await wait_for(gate.started.is_set)
        ticks = 0
        for _ in range(
            20
        ):  # nếu run chặn loop thì không tới được đây (scorer đang treo)
            await asyncio.sleep(0)
            ticks += 1
        assert ticks == 20 and gate.running == 1 and not task.done()
        gate.release.set()
        assert await task == 0.5

    asyncio.run(go())


def test_http_health_tra_loi_khi_scorer_dang_ban_va_slot_nha_sau_timeout():
    gate = Gate()
    app = create_app(
        scorer=gate, settings=Settings(inference_slots=1, model_timeout_s=TIMEOUT_S)
    )

    @app.get("/t")
    async def route():
        return {"s": await app.state.inference.run(app.state.scorer, job)}

    with TestClient(app) as client:
        r = client.get("/t")
        assert r.status_code == 504 and r.json()["error"]["code"] == "MODEL_TIMEOUT"
        r = client.get("/t")
        assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICE_BUSY"
        assert client.get("/health").status_code == 200
        gate.release.set()
        wait_for_sync(lambda: slot_is_free(app.state.inference))
        lengthen(app.state.inference)
        assert client.get("/t").json() == {"s": 0.5}


# ---- 7. Loader (AC-20) ----


def test_load_loi_tra_none_va_ghi_log_khong_dung_process(caplog):
    async def go():
        service = make_service()

        def bad():
            raise OSError("hong")

        with caplog.at_level(logging.ERROR, logger="realcheck"):
            assert await service.load(bad) is None
        assert await service.load(lambda: quick) is quick

    asyncio.run(go())
    assert "model_load_failed" in caplog.text


def test_load_chay_tren_worker_thread_khong_phai_event_loop():
    async def go():
        service = make_service()
        box = {}

        def loader():
            box["thread"] = threading.current_thread()
            return quick

        await service.load(loader)
        assert box["thread"].name.startswith("inference")
        assert box["thread"] is not threading.main_thread()

    asyncio.run(go())


def test_health_503_khi_loader_loi_va_200_khi_loader_ok():
    seen = []

    def good():
        seen.append(threading.current_thread().name)
        return quick

    def bad():
        raise RuntimeError("x")

    with TestClient(create_app(loader=good)) as client:
        assert client.get("/health").status_code == 200
    assert seen[0].startswith("inference")
    with TestClient(create_app(loader=bad)) as client:
        r = client.get("/health")
        assert r.status_code == 503 and r.json()["model_ready"] is False


def test_scorer_tiem_vao_thang_loader():
    def never():
        raise AssertionError("loader không được gọi khi đã có scorer")

    with TestClient(create_app(scorer=quick, loader=never)) as client:
        assert client.get("/health").status_code == 200


# ---- 8. close() ----


def test_close_hai_lan_roi_run_va_load_sau_close():
    async def go():
        service = make_service()
        service.close()
        service.close()
        with pytest.raises(ApiError) as info:
            await service.run(quick, job)
        assert error_code(info) == ErrorCode.MODEL_NOT_READY
        assert slot_is_free(service)  # submit lỗi thì trả lại slot
        assert await service.load(lambda: quick) is None

    asyncio.run(go())


def test_close_khi_scorer_dang_chay_khong_chan_va_viec_van_xong():
    async def go():
        service = make_service(timeout=DEADLINE_S)
        gate = Gate()
        task = asyncio.create_task(service.run(gate, job))
        await wait_for(gate.started.is_set)
        service.close()  # nếu chờ việc đang chạy thì treo ở đây (gate chưa release)
        assert gate.running == 1
        gate.release.set()
        assert await task == 0.5

    asyncio.run(go())


# ---- 9. Không rò tài nguyên, không kéo torch ----


def test_create_app_nhieu_lan_khong_them_thread_hay_log_handler():
    # So tập chứ không so số lượng: số thread của pytest có thể đổi giữa chừng.
    logger = logging.getLogger("realcheck")
    threads_before, handlers_before = set(threading.enumerate()), list(logger.handlers)
    for _ in range(20):
        create_app(scorer=quick)
    assert set(threading.enumerate()) <= threads_before
    assert len(logger.handlers) <= max(1, len(handlers_before))


def test_import_app_inference_khong_keo_torch():
    code = (
        "import sys, app.inference\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('torch', 'clip', 'open_clip', 'transformers')]\n"
        "print(bad)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


# ---- 10. Giới hạn đã biết (D12, FR-A04): thread không hủy được ----


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Giới hạn đã biết của D12/FR-A04: thread CLIP không hủy được, "
        "ThreadPoolExecutor không daemon nên process không thoát khi scorer treo "
        "vô hạn. Khi Quang đổi sang daemon thread hoặc cách khác khiến process "
        "thoát, ca này XPASS (strict) làm CI đỏ để nhắc gỡ marker này."
    ),
    raises=pytest.fail.Exception,  # sai cwd/ImportError ở con phải FAIL, không xfail oan
)
def test_process_thoat_duoc_khi_scorer_treo_vo_han():
    child = (
        "import asyncio, threading\n"
        "from PIL import Image\n"
        "from app.errors import ApiError\n"
        "from app.inference import InferenceService\n"
        "from app.settings import Settings\n"
        "forever = threading.Event()\n"
        "service = InferenceService(Settings(model_timeout_s=0.1))\n"
        "async def main():\n"
        "    try:\n"
        "        await service.run(lambda i: forever.wait(),"
        " lambda s: s(Image.new('RGB', (2, 2))))\n"
        "    except ApiError:\n"
        "        pass\n"
        "asyncio.run(main())\n"
        "service.close()\n"
    )
    try:
        # subprocess.run giết con khi quá hạn nên không bao giờ làm treo CI
        subprocess.run([sys.executable, "-c", child], timeout=5, check=True)
    except subprocess.TimeoutExpired:
        pytest.fail("process không thoát: thread scorer treo giữ interpreter sống")
