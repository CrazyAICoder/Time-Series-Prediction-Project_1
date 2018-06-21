"""
Module for generating random events
"""

import datetime
import math
import random

from abc import (
    ABCMeta,
    abstractmethod,
)

def day_saw_variate(ts):
    """
    Sawtooth variate function with 24h-period
    """
    t0 = datetime.datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0).timestamp()
    return (ts - t0) / (24 * 3600)

def day_sin_variate(ts):
    """
    Sinusoid variate function with 24h-period
    """
    t0 = datetime.datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0).timestamp()
    return math.sin(2 * math.pi * (ts - t0) / (24 * 3600))

def randfloat(lo, hi):
    """
    Return random float between `lo` and `hi`
    """
    return lo + random.random() * (hi - lo)

class EventGenerator(metaclass=ABCMeta):
    """
    Random event generator
    """

    def __init__(self, base=1, amplitude=1, sigma=1, trend=0):
        self.base = base
        self.amplitude = amplitude
        self.sigma = sigma
        self.trend = trend

    @abstractmethod
    def variate(self, ts):
        """
        Return average rate for this timestamp
        """

    def generate_ts(self, from_ts, to_ts, step=0.001):
        """
        Generate timestamps between `from_ts` and `to_ts`.
        """

        from_ms = int(from_ts * 1000)
        to_ms = int(to_ts * 1000)
        step_ms = int(step * 1000)

        increase = step * self.trend / 3600

        for ts_ms in range(from_ms, to_ms, step_ms):
            ts = ts_ms / 1000
            self.base += increase

            avg = self.variate(ts)
            nb_events = random.normalvariate(avg, self.sigma)

            if nb_events <= 0:
                continue

            p = nb_events - int(nb_events)
            extra = 1 if random.random() <= p else 0
            nb_events = int(nb_events) + extra

            for i in range(nb_events):
                yield ts + i * step / nb_events


class FlatEventGenerator(EventGenerator):
    def variate(self, ts):
        return self.base


class SawEventGenerator(EventGenerator):
    """
    Random event generator with sawtooth shape
    """

    def variate(self, ts):
        return self.base + self.amplitude * day_saw_variate(ts)


class SinEventGenerator(EventGenerator):
    """
    Random event generator with sinusoid shape
    """

    def variate(self, ts):
        return self.base + self.amplitude * day_sin_variate(ts)

class PatternGenerator(EventGenerator):
    """
    Random event generator with a LoudML shape
    """

    MARGIN = 6
    PATTERN = \
"""
              e
   w y       p
  a   o     a
 r     u   h
d       r s
"""

    def __init__(self, base=1, amplitude=8, sigma=1, trend=0):
        super().__init__(
            base=base,
            amplitude=amplitude,
            sigma=sigma,
            trend=trend,
        )

        PATTERN = self.PATTERN.rstrip().splitlines()
        values = [0] * len(max(PATTERN, key=len))

        for i, line in enumerate(reversed(PATTERN)):
            value = (i + 1) / len(PATTERN)

            print(line)
            for j, char in enumerate(line):
                values[j] = max(values[j], 0 if char == ' ' else value)

        self._values = [0] * self.MARGIN + values + [0] * self.MARGIN

    def variate(self, ts):
        t0 = datetime.datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        x = int(len(self._values) * (ts - t0) / (24 * 3600)) % len(self._values)

        return self.base + self.amplitude * self._values[x]

class LoudMLEventGenerator(PatternGenerator):
    """
    Random event generator with a LoudML shape
    """

    MARGIN = 6
    PATTERN = \
"""
XX                                                    XX         XXX               XXX
XX                                                    XX        X   X             X   X
XX                                                    XX        X   X             X   X
XX                                                    XX       X     X           X     X
XX        XXXX        XX            XX        XXXX    XX       X     X           X     X
XX     XXXXXXXXXX     XX            XX     XXXXXXXXXX XX      X       X         X       X
XX   XXXXXXXXXXXXXX   XX            XX   XXXXXXXXXXXXXXX      X       X         X       X
XX  XXXXXXXXXXXXXXXX  XX            XX  XXXXXXXXXXXXXXXX     X         X       X         X
XX  XXXXXXXXXXXXXXXX  XX            XX  XXXXXXXXXXXXXXXX     X         X       X         X
XX  XXXXXXXXXXXXXXXX  XX            XX  XXXXXXXXXXXXXXXX    X           X     X           X
XX  XXXXXXXXXXXXXXXX  XX            XX  XXXXXXXXXXXXXXXX    X           X     X           X
XX  XXXXXXXXXXXXXXXX  XXX          XXX  XXXXXXXXXXXXXXXX   X             X   X             XXXXXXXXXXXXXXX
XX  XXXXXXXXXXXXXXXX  XXXX        XXXX  XXXXXXXXXXXXXXXX   X             X   X             XXXXXXXXXXXXXXXXX
XX  XXXXXXXXXXXXXXXX  XXXXXXXXXXXXXXXX  XXXXXXXXXXXXXXXX  X               XXX               XXXXXXXXXXXXXXXXX
XX  XXXXXXXXXXXXXXXX  XXXXXXXXXXXXXXXX  XXXXXXXXXXXXXXXX  X                                 XXXXXXXXXXXXXXXXX
"""


class CamelEventGenerator(PatternGenerator):
    """
    Random event generator with a camel shape
    """

    MARGIN = 0
    PATTERN = \
"""
                             XXX
                 XX         X   X
               XX  XX       X    X
              X      X     X      X
             X        XX  X        XX
            X           XX           X
           X                          X
          X                           X
        XX                             X
      XX                                X
   XXX                                   XXX
XXX                                         XXX
"""

def example():
    """
    Example of EventGenerator usage
    """

    to_ts = datetime.datetime.now().timestamp()
    from_ts = to_ts - 10
    generator = EventGenerator(lo=0, hi=10, sigma=1)
    for ts in generator.generate_ts(from_ts, to_ts):
        yield {
            'timestamp': ts,
            'foo': random.random(),
        }
