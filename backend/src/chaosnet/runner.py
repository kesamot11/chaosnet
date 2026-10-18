"""Runs one experiment: baseline, inject, recover (#52, design agreed 2026-10-17).

- Three separate load runs, one per phase.
- The fault is added before the inject measurement starts and removed after it ends, so
  the inject numbers contain only behaviour under the fault.
- The fault is always removed (``finally``), also on errors and on abort.
- An error ends the experiment as ``failed`` with a reason; cancelling the task (abort)
  ends it as ``aborted``.
- Heartbeats go to the watchdog while a fault is active (ADR-001, layer 3).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from chaosnet.experiments import ExperimentSpec, FaultSpec, State, judge
from chaosnet.faults import Fault, FaultDriver
from chaosnet.store import Store

# Runs load for the given number of seconds and returns the load generator summary.
Measure = Callable[[float], Awaitable[dict[str, Any]]]
Heartbeat = Callable[[], Awaitable[None]]


class Runner:
    def __init__(
        self,
        store: Store,
        driver: FaultDriver,
        measure: Measure,
        heartbeat: Heartbeat,
        *,
        heartbeat_interval_s: float = 1.0,
    ) -> None:
        self.store = store
        self.driver = driver
        self.measure = measure
        self.heartbeat = heartbeat
        self.heartbeat_interval_s = heartbeat_interval_s

    async def run(self, experiment_id: int) -> None:
        spec = ExperimentSpec.model_validate(self.store.get(experiment_id).spec)
        try:
            self.store.set_state(experiment_id, State.BASELINE)
            summary = await self.measure(spec.phases_s.baseline)
            self.store.save_result(experiment_id, State.BASELINE, summary)

            self.store.set_state(experiment_id, State.INJECT)
            await self._inject(experiment_id, spec)

            self.store.set_state(experiment_id, State.RECOVER)
            summary = await self.measure(spec.phases_s.recover)
            self.store.save_result(experiment_id, State.RECOVER, summary)

            inject = self.store.get(experiment_id).results[State.INJECT]
            self.store.save_verdict(experiment_id, judge(inject, spec.hypothesis))
            self.store.set_state(experiment_id, State.COMPLETED)
        except asyncio.CancelledError:
            self.store.set_state(experiment_id, State.ABORTED, reason="aborted by user")
            raise
        except Exception as e:
            self.store.set_state(experiment_id, State.FAILED, reason=f"{type(e).__name__}: {e}")

    async def _inject(self, experiment_id: int, spec: ExperimentSpec) -> None:
        """Measure with the fault active; the fault window equals the measurement window.

        Heartbeats start before the fault, so the watchdog lease covers it from the
        first moment. The finally block stops them and removes the fault on success,
        error and cancellation alike.
        """
        beats = asyncio.create_task(self._heartbeats())
        faults: list[Fault] = []
        try:
            faults = await self._add_fault(spec.fault)
            summary = await self.measure(spec.phases_s.inject)
            self.store.save_result(experiment_id, State.INJECT, summary)
        finally:
            beats.cancel()
            for f in faults:
                await self.driver.remove(f)

    async def _add_fault(self, fault: FaultSpec) -> list[Fault]:
        if fault.kind == "latency":
            assert fault.ms is not None
            return await self.driver.add_latency(fault.link, fault.ms, fault.direction)
        if fault.kind == "bandwidth":
            assert fault.kbps is not None
            return await self.driver.add_bandwidth(fault.link, fault.kbps, fault.direction)
        return await self.driver.add_reset_peer(fault.link, fault.direction)

    async def _heartbeats(self) -> None:
        """Send a heartbeat every interval until cancelled; a failed one is not fatal."""
        while True:
            try:
                await self.heartbeat()
            except Exception:
                pass  # the watchdog being down must not stop the experiment
            await asyncio.sleep(self.heartbeat_interval_s)


async def reconcile(store: Store, driver: FaultDriver) -> None:
    """Run on controller startup: make the records and the lab tell the truth again (#55)."""
    raise NotImplementedError
