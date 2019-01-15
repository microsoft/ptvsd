import typing
from dataclasses import dataclass, field


@dataclass
class Thing:
    a: typing.Any
    b: typing.Any
    c: typing.Any = field(init=False, repr=False)

    def __post_init__(self):
        self.c = self.a + self.b  # break here


Thing(a=1, b=2)
print('TEST SUCEEDED!')