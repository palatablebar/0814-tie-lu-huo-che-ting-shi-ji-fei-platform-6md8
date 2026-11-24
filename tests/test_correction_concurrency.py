from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.inputs import RATE_PROFILES
from app.review.service import execute, execute_correction


def test_parallel_correction_rerun_commits_single_row(store, clean):
    barrier = Barrier(4)

    def load(_):
        barrier.wait(3)
        return execute_correction(store, clean, RATE_PROFILES["corrected"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(load, range(4)))
    assert all(result == results[0] for result in results)
    assert len(store.list()) == 1


def test_legacy_and_correction_concurrent_runs_keep_both(store, clean):
    barrier = Barrier(2)

    def run_legacy():
        barrier.wait(2)
        return execute(store, clean)

    def run_corrected():
        barrier.wait(2)
        return execute_correction(store, clean, RATE_PROFILES["corrected"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_legacy), pool.submit(run_corrected)]
        legacy, corrected = (future.result() for future in futures)
    assert legacy["id"] != corrected["id"]
    assert len(store.list()) == 2
