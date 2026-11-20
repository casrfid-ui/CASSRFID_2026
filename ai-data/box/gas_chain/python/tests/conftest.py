import numpy as np
import pytest

from gas_chain import Config, GasChain, NSTEP


class Sensor:
    """Synthetic BME680: clean air with a little noise, plus helpers to inject events."""

    def __init__(self, seed=0, noise=0.01, base_ln=np.linspace(11.5, 13.5, NSTEP)):
        self.rng = np.random.default_rng(seed)
        self.noise = noise
        self.base_ln = np.array(base_ln, float)
        self.temp, self.rh = 25.0, 50.0

    def scan(self, drop=0.0, temp=None, rh=None):
        """drop: ln-unit resistance drop (scalar or per step) caused by smoke."""
        ln = self.base_ln - np.asarray(drop, float) + self.rng.normal(0, self.noise, NSTEP)
        t = np.full(NSTEP, self.temp if temp is None else temp)
        h = np.full(NSTEP, self.rh if rh is None else rh)
        return np.exp(ln), t, h


@pytest.fixture
def sensor():
    return Sensor()


@pytest.fixture
def ready_chain(sensor):
    """A chain past burn-in and warm-up, on clean air."""
    chain = GasChain(Config())
    for _ in range(30):
        chain.update(*sensor.scan(), 30)
    assert not chain.update(*sensor.scan(), 30).warmup
    return chain
