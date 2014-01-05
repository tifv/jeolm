from jeolm.records import RecordPath
from .flags import FlagContainer, UnutilizedFlagError

class TargetError(ValueError):
    pass

class Target:
    __slots__ = ['path', 'flags']

    def __new__(cls, path, flags, *, origin=None):
        instance = super().__new__(cls)
        instance.path = RecordPath(path)
        if not isinstance(flags, FlagContainer):
            flags = FlagContainer(flags, origin=origin)
        elif origin is not None:
            raise RuntimeError(origin)
        instance.flags = flags
        return instance

    @property
    def key(self):
        return (self.path, self.flags.as_set)

    def __hash__(self):
        raise NotImplementedError('you do not need this')

    def __str__(self):
        return '{self.path!s}{self.flags!s}'.format(self=self)

    def __repr__(self):
        return ( '{self.__class__.__qualname__}'
            '({self.path!r}, {self.flags!r})'
            .format(self=self) )

    def flags_union(self, iterable, *, origin=None, **kwargs):
        return self.__class__( self.path,
            self.flags.union(iterable, origin=origin, **kwargs) )

    def flags_difference(self, iterable, *, origin=None, **kwargs):
        return self.__class__( self.path,
            self.flags.difference(iterable, origin=origin, **kwargs) )

    def flags_clean_copy(self, *, origin):
        return self.__class__(self.path, self.flags.clean_copy(origin=origin))

    def path_derive(self, *pathparts):
        return self.__class__(RecordPath(self.path, *pathparts), self.flags)

    def check_unutilized_flags(self):
        try:
            self.flags.check_unutilized_flags()
        except UnutilizedFlagError as error:
            raise TargetError( "Unutilized flags in target {target}"
                .format(target=self)
            ) from error

