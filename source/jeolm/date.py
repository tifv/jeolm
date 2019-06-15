import abc
import re
import datetime

from typing import Any, Union, Optional

class Period:

    _date: datetime.date
    _period: Optional[int]

    def __init__( self,
        date: Union['DatePeriod', 'Period', datetime.date],
        period: Optional[int] = None
    ) -> None:
        if isinstance(date, Period):
            if period is not None:
                raise ValueError
            self._date = date.date
            self._period = date.period
        elif isinstance(date, datetime.date):
            self._date = date
            self._period = int(period) if period is not None else None
        else:
            raise TypeError(type(date))

    def __str__(self) -> str:
        if self._period is not None:
            return self._date.isoformat() + '-p' + str(self._period)
        else:
            return self._date.isoformat()

    def __repr__(self) -> str:
        return ( f'{self.__class__.__name__}'
            f'({self._date!r}, {self._period!r})' )

    _regex = re.compile(
        r'(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})[ \-]'
        r'p(?P<period>[0-9]+)' )

    @classmethod
    def from_string(cls, string: str) -> 'Period':
        match = cls._regex.fullmatch(string)
        if match is None:
            raise ValueError(string)
        year, month, day, period = ( int(match.group(name))
            for name in ('year', 'month', 'day', 'period') )
        return cls(datetime.date(year, month, day), period)

    def _cmp( self, other: Any,
        less_than: bool, equal: bool, greater_than: bool
    ) -> bool:
        """Return lt, eq, gt if self <=, ==, >= other."""
        if isinstance(other, Period):
            if self._date > other.date:
                return greater_than
            if self._date < other.date:
                return less_than
            if self._period is None:
                if other.period is None:
                    return equal
                return greater_than
            if other.period is None:
                return less_than
            if self._period > other.period:
                return greater_than
            if self._period < other.period:
                return less_than
            return equal
        elif isinstance(other, datetime.date):
            if self._date > other:
                return greater_than
            if self._date < other:
                return less_than
            if self._period is not None:
                return less_than
            return equal
        else:
            return NotImplemented

    def __eq__(self, other: Any) -> bool:
        return self._cmp(other, False, True, False)

    def __ne__(self, other: Any) -> bool:
        return self._cmp(other, True, False, True)

    def __lt__(self, other: Any) -> bool:
        return self._cmp(other, True, False, False)

    def __le__(self, other: Any) -> bool:
        return self._cmp(other, True, True, False)

    def __gt__(self, other: Any) -> bool:
        return self._cmp(other, False, False, True)

    def __ge__(self, other: Any) -> bool:
        return self._cmp(other, False, True, True)

    @property
    def date(self) -> datetime.date:
        return self._date

    @property
    def period(self) -> Optional[int]:
        return self._period

class DatePeriod(metaclass=abc.ABCMeta):
    def __new__(cls) -> 'DatePeriod':
        raise NotImplementedError

DatePeriod.register(datetime.date)
DatePeriod.register(Period)

class _NeverType:
    """A singleton class for the purpose of sorting lists of dates."""

    def __new__(cls) -> '_NeverType':
        global Never
        try:
            return Never
        except NameError:
            return super().__new__(cls)

    def _cmp( self, other: Any,
        less_than: bool, equal: bool, greater_than: bool
    ) -> bool:
        """Return lt, eq, gt if self <=, ==, >= other."""
        if other is Never:
            return equal
        else:
            return greater_than

    def __eq__(self, other: Any) -> bool:
        return self._cmp(other, False, True, False)

    def __ne__(self, other: Any) -> bool:
        return self._cmp(other, True, False, True)

    def __lt__(self, other: Any) -> bool:
        return self._cmp(other, True, False, False)

    def __le__(self, other: Any) -> bool:
        return self._cmp(other, True, True, False)

    def __gt__(self, other: Any) -> bool:
        return self._cmp(other, False, False, True)

    def __ge__(self, other: Any) -> bool:
        return self._cmp(other, False, True, True)

Never = _NeverType()

